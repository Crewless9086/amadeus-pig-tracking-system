create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

create table if not exists public.charlie_mission_replacement_authorizations (
    authorization_digest text primary key check (length(authorization_digest) = 64),
    replacement_identity text not null,
    contract_digest text not null check (length(contract_digest) = 64),
    predecessor_set_digest text not null check (length(predecessor_set_digest) = 64),
    transaction_digest text not null check (length(transaction_digest) = 64),
    owner_identity_hash text not null check (length(owner_identity_hash) = 64),
    authorization_json jsonb not null,
    issued_at timestamptz not null,
    expires_at timestamptz not null,
    recorded_at timestamptz not null default now(),
    check (expires_at > issued_at and expires_at <= issued_at + interval '15 minutes'),
    unique (replacement_identity, transaction_digest)
);

create table if not exists public.charlie_mission_replacement_batches (
    replacement_identity text primary key,
    successor_mission_id text not null unique references public.charlie_missions(mission_id) on delete restrict,
    contract_digest text not null check (length(contract_digest) = 64),
    predecessor_set_digest text not null check (length(predecessor_set_digest) = 64),
    transaction_digest text not null unique check (length(transaction_digest) = 64),
    owner_authorization_digest text not null references public.charlie_mission_replacement_authorizations(authorization_digest) on delete restrict,
    owner_identity_hash text not null check (length(owner_identity_hash) = 64),
    owner_authorization_json jsonb not null,
    successor_contract_json jsonb not null,
    predecessor_allowlist_json jsonb not null,
    result_json jsonb not null,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_mission_replacement_bindings (
    replacement_identity text not null references public.charlie_mission_replacement_batches(replacement_identity) on delete restrict,
    successor_mission_id text not null references public.charlie_missions(mission_id) on delete restrict,
    predecessor_mission_id text primary key references public.charlie_missions(mission_id) on delete restrict,
    expected_status text not null,
    expected_content_digest text not null check (length(expected_content_digest) = 64),
    expected_metadata_generation text not null,
    predecessor_snapshot_json jsonb not null,
    unfinished_value_reference text not null,
    created_at timestamptz not null default now(),
    unique (replacement_identity, predecessor_mission_id)
);

create table if not exists public.charlie_mission_replacement_audit_events (
    event_id text primary key,
    replacement_identity text not null references public.charlie_mission_replacement_batches(replacement_identity) on delete restrict,
    event_type text not null check (event_type in ('replacement_committed','predecessor_bound')),
    mission_id text not null references public.charlie_missions(mission_id) on delete restrict,
    transaction_digest text not null check (length(transaction_digest) = 64),
    evidence_json jsonb not null,
    created_at timestamptz not null default now(),
    unique (replacement_identity, event_type, mission_id)
);

create or replace function public.charlie_sha256(p_value text)
returns text language sql immutable strict
set search_path = public, extensions, pg_temp
as $$ select encode(extensions.digest(convert_to(p_value, 'UTF8'), 'sha256'), 'hex') $$;

create or replace function public.charlie_mission_replacement_content_digest(p_mission public.charlie_missions)
returns text language sql immutable strict
set search_path = public, extensions, pg_temp
as $$
    select public.charlie_sha256(jsonb_build_object(
        'mission_id',p_mission.mission_id,'status',p_mission.status,'source',p_mission.source,
        'source_message_id',p_mission.source_message_id,'telegram_user_id',p_mission.telegram_user_id,
        'telegram_chat_id',p_mission.telegram_chat_id,'raw_text',p_mission.raw_text,'title',p_mission.title,
        'urgency',p_mission.urgency,'mission_type',p_mission.mission_type,
        'approval_level',p_mission.approval_level,'selected_next_step',p_mission.selected_next_step,
        'owner_decision',p_mission.owner_decision,'codex_chat_write_status',p_mission.codex_chat_write_status,
        'metadata_json',p_mission.metadata_json
    )::text)
$$;

create or replace function public.charlie_mission_replacement_metadata_generation(p_mission public.charlie_missions)
returns text language sql immutable strict
set search_path = public, extensions, pg_temp
as $$
    select coalesce(
        nullif(p_mission.metadata_json->'orchestration'->>'generation_identity',''),
        nullif(p_mission.metadata_json->'review_packet'->>'review_generation',''),
        'legacy-sha256:' || public.charlie_sha256(p_mission.metadata_json::text)
    )
$$;

create or replace function public.prevent_charlie_replacement_history_mutation()
returns trigger language plpgsql security invoker set search_path = public, pg_temp
as $$ begin raise exception 'charlie_mission_replacement_history_is_append_only'; end $$;

do $$
declare t text;
begin
  foreach t in array array['charlie_mission_replacement_authorizations','charlie_mission_replacement_batches','charlie_mission_replacement_bindings','charlie_mission_replacement_audit_events'] loop
    execute format('drop trigger if exists prevent_%I_update on public.%I',t,t);
    execute format('create trigger prevent_%I_update before update on public.%I for each row execute function public.prevent_charlie_replacement_history_mutation()',t,t);
    execute format('drop trigger if exists prevent_%I_delete on public.%I',t,t);
    execute format('create trigger prevent_%I_delete before delete on public.%I for each row execute function public.prevent_charlie_replacement_history_mutation()',t,t);
  end loop;
end $$;

create or replace function public.append_charlie_mission_replacement_authorization(
    p_authorization_canonical text,
    p_authorization_digest text
)
returns text
language plpgsql
security definer
set search_path = public, extensions, pg_temp
as $$
declare auth_payload jsonb;
begin
    auth_payload := p_authorization_canonical::jsonb || jsonb_build_object('authorization_digest',p_authorization_digest);
    if public.charlie_sha256(p_authorization_canonical) <> p_authorization_digest
       or auth_payload->>'version' <> 'charlie_many_to_one_replacement_v1'
       or coalesce(auth_payload->>'signature','') !~ '^[0-9a-f]{64}$'
       or coalesce(auth_payload->>'owner_identity_hash','') !~ '^[0-9a-f]{64}$'
       or coalesce(auth_payload->>'contract_digest','') !~ '^[0-9a-f]{64}$'
       or coalesce(auth_payload->>'predecessor_set_digest','') !~ '^[0-9a-f]{64}$'
       or coalesce(auth_payload->>'transaction_digest','') !~ '^[0-9a-f]{64}$'
       or (auth_payload->>'expires_at')::timestamptz <= now()
       or (auth_payload->>'issued_at')::timestamptz > now() + interval '30 seconds'
       or (auth_payload->>'expires_at')::timestamptz > (auth_payload->>'issued_at')::timestamptz + interval '15 minutes'
    then raise exception 'replacement_owner_authorization_invalid'; end if;
    insert into public.charlie_mission_replacement_authorizations(
        authorization_digest,replacement_identity,contract_digest,predecessor_set_digest,
        transaction_digest,owner_identity_hash,authorization_json,issued_at,expires_at)
    values(p_authorization_digest,auth_payload->>'replacement_identity',auth_payload->>'contract_digest',
        auth_payload->>'predecessor_set_digest',auth_payload->>'transaction_digest',
        auth_payload->>'owner_identity_hash',auth_payload,
        (auth_payload->>'issued_at')::timestamptz,(auth_payload->>'expires_at')::timestamptz)
    on conflict do nothing;
    if not exists(select 1 from public.charlie_mission_replacement_authorizations where authorization_digest=p_authorization_digest and authorization_json=auth_payload) then
        raise exception 'replacement_owner_authorization_conflict';
    end if;
    return p_authorization_digest;
end;
$$;

create or replace function public.prevent_bound_charlie_predecessor_mutation()
returns trigger language plpgsql security definer set search_path = public, pg_temp
as $$
begin
    if exists(select 1 from public.charlie_mission_replacement_bindings where predecessor_mission_id=old.mission_id) then
        raise exception 'charlie_replaced_predecessor_is_immutable';
    end if;
    return new;
end;
$$;

drop trigger if exists prevent_bound_charlie_predecessor_update on public.charlie_missions;
create trigger prevent_bound_charlie_predecessor_update before update on public.charlie_missions
for each row execute function public.prevent_bound_charlie_predecessor_mutation();

create or replace function public.apply_charlie_many_to_one_replacement(
    p_replacement_identity text,
    p_contract_canonical text,
    p_predecessors_canonical text,
    p_contract_digest text,
    p_predecessor_set_digest text,
    p_transaction_digest text,
    p_owner_authorization jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions, pg_temp
as $$
declare
    contract jsonb;
    predecessors jsonb;
    predecessor jsonb;
    predecessor_row public.charlie_missions%rowtype;
    successor_id text;
    result jsonb;
    prior public.charlie_mission_replacement_batches%rowtype;
    grant_row public.charlie_mission_replacement_authorizations%rowtype;
    expected_transaction text;
    predecessor_count integer;
    distinct_predecessor_count integer;
    selected_agents jsonb;
    workflow_agents jsonb;
begin
    if current_setting('transaction_isolation') <> 'serializable' then raise exception 'replacement_serializable_transaction_required'; end if;
    perform pg_advisory_xact_lock(hashtextextended(p_replacement_identity, 0));
    if public.charlie_sha256(p_contract_canonical) <> p_contract_digest then raise exception 'replacement_contract_digest_mismatch'; end if;
    if public.charlie_sha256(p_predecessors_canonical) <> p_predecessor_set_digest then raise exception 'replacement_predecessor_digest_mismatch'; end if;
    expected_transaction := public.charlie_sha256('charlie_many_to_one_replacement_v1|'||p_replacement_identity||'|'||p_contract_digest||'|'||p_predecessor_set_digest);
    if p_replacement_identity <> 'CHARLIE-REPLACEMENT-BATCH-' || upper(substr(public.charlie_sha256('charlie_many_to_one_replacement_v1|'||p_contract_digest||'|'||p_predecessor_set_digest),1,24)) then raise exception 'replacement_identity_not_deterministic'; end if;
    if expected_transaction <> p_transaction_digest then raise exception 'replacement_transaction_digest_mismatch'; end if;
    if p_owner_authorization->>'contract_digest' <> p_contract_digest
       or p_owner_authorization->>'predecessor_set_digest' <> p_predecessor_set_digest
       or p_owner_authorization->>'transaction_digest' <> p_transaction_digest
       or p_owner_authorization->>'replacement_identity' <> p_replacement_identity
       or p_owner_authorization->>'version' <> 'charlie_many_to_one_replacement_v1'
       or coalesce(p_owner_authorization->>'owner_identity_hash','') !~ '^[0-9a-f]{64}$'
       or coalesce(p_owner_authorization->>'authorization_digest','') !~ '^[0-9a-f]{64}$'
    then raise exception 'replacement_owner_authorization_invalid'; end if;

    contract := p_contract_canonical::jsonb;
    predecessors := p_predecessors_canonical::jsonb;
    successor_id := contract->>'mission_id';
    if contract->>'status' <> 'paused' then raise exception 'replacement_successor_status_not_paused'; end if;
    if coalesce(successor_id,'')='' or coalesce(contract->>'raw_text','')='' or coalesce(contract->>'title','')=''
       or coalesce(contract->>'urgency','')='' or coalesce(contract->>'mission_type','')=''
       or coalesce(contract->>'approval_level','')='' or jsonb_typeof(contract->'metadata_json') <> 'object'
    then raise exception 'replacement_successor_contract_incomplete'; end if;
    if coalesce((contract->'metadata_json'->'orchestration_binding'->>'validated')::boolean,false) is not true
       or contract->'metadata_json'->'orchestration'->>'version' <> 'charlie_adaptive_orchestration_v1'
       or coalesce(contract->'metadata_json'->'orchestration'->>'generation_identity','') !~ '^[0-9a-f]{24}$'
       or contract->'metadata_json'->'orchestration_binding'->>'generation_identity'
          is distinct from contract->'metadata_json'->'orchestration'->>'generation_identity'
    then raise exception 'replacement_successor_orchestration_invalid'; end if;
    select jsonb_agg(item->>'agent' order by ord) into selected_agents
      from jsonb_array_elements(contract->'metadata_json'->'orchestration'->'selected_agents') with ordinality selected(item,ord);
    select jsonb_agg(item->>'agent' order by ord) into workflow_agents
      from jsonb_array_elements(contract->'metadata_json'->'agent_workflow') with ordinality workflow(item,ord);
    if selected_agents is null or selected_agents is distinct from workflow_agents
       or exists(select 1 from jsonb_array_elements(contract->'metadata_json'->'orchestration'->'selected_agents') item where coalesce(item->>'agent','')='')
    then raise exception 'replacement_successor_orchestration_invalid'; end if;
    if jsonb_typeof(predecessors) <> 'array' or jsonb_array_length(predecessors) < 1 then raise exception 'replacement_predecessor_allowlist_required'; end if;
    select count(*),count(distinct item->>'mission_id') into predecessor_count, distinct_predecessor_count
      from jsonb_array_elements(predecessors) item;
    if predecessor_count <> distinct_predecessor_count then raise exception 'replacement_duplicate_predecessor'; end if;
    if exists(select 1 from jsonb_array_elements(predecessors) item where
        coalesce(item->>'mission_id','')='' or coalesce(item->>'expected_status','') not in ('new','triaged','planned','blocked','pr_ready','paused')
        or coalesce(item->>'expected_content_digest','') !~ '^[0-9a-f]{64}$'
        or coalesce(item->>'expected_metadata_generation','')=''
        or coalesce(item->>'unfinished_value_reference','')='')
    then raise exception 'replacement_predecessor_contract_incomplete'; end if;
    select * into grant_row from public.charlie_mission_replacement_authorizations
      where authorization_digest=p_owner_authorization->>'authorization_digest' for share;
    if not found or grant_row.authorization_json <> p_owner_authorization
       or grant_row.replacement_identity <> p_replacement_identity
       or grant_row.contract_digest <> p_contract_digest
       or grant_row.predecessor_set_digest <> p_predecessor_set_digest
       or grant_row.transaction_digest <> p_transaction_digest
    then raise exception 'replacement_owner_authorization_not_granted'; end if;
    select * into prior from public.charlie_mission_replacement_batches where replacement_identity=p_replacement_identity for share;
    if found then
        if prior.transaction_digest <> p_transaction_digest or prior.owner_authorization_digest <> grant_row.authorization_digest then raise exception 'replacement_identity_collision'; end if;
        return prior.result_json || jsonb_build_object('replayed',true,'rows_changed',0);
    end if;
    if grant_row.expires_at <= now() then raise exception 'replacement_owner_authorization_stale'; end if;
    successor_id := contract->>'mission_id';
    if exists(select 1 from public.charlie_missions where mission_id=successor_id) then raise exception 'replacement_successor_identity_collision'; end if;

    for predecessor in select value from jsonb_array_elements(predecessors) order by value->>'mission_id' loop
        perform pg_advisory_xact_lock(hashtextextended(predecessor->>'mission_id',0));
        select * into predecessor_row from public.charlie_missions where mission_id=predecessor->>'mission_id' for update;
        if not found then raise exception 'replacement_predecessor_missing'; end if;
        if predecessor_row.status not in ('new','triaged','planned','blocked','pr_ready','paused')
           or predecessor_row.status <> predecessor->>'expected_status' then raise exception 'replacement_predecessor_status_changed'; end if;
        if public.charlie_mission_replacement_content_digest(predecessor_row) <> predecessor->>'expected_content_digest' then raise exception 'replacement_predecessor_content_changed'; end if;
        if public.charlie_mission_replacement_metadata_generation(predecessor_row) <> predecessor->>'expected_metadata_generation' then raise exception 'replacement_predecessor_generation_changed'; end if;
        if exists(select 1 from public.charlie_mission_replacement_bindings where predecessor_mission_id=predecessor_row.mission_id) then raise exception 'replacement_predecessor_already_bound'; end if;
    end loop;

    insert into public.charlie_missions(mission_id,status,source,source_message_id,telegram_user_id,telegram_chat_id,raw_text,title,urgency,mission_type,approval_level,selected_next_step,owner_decision,codex_chat_write_status,metadata_json)
    values(successor_id,'paused',coalesce(contract->>'source','charlie_reconciliation'),contract->>'source_message_id',contract->>'telegram_user_id',contract->>'telegram_chat_id',contract->>'raw_text',contract->>'title',coalesce(contract->>'urgency','P1'),contract->>'mission_type',contract->>'approval_level',contract->>'selected_next_step',contract->>'owner_decision',contract->>'codex_chat_write_status',
      contract->'metadata_json' || jsonb_build_object('many_to_one_replacement',jsonb_build_object('replacement_identity',p_replacement_identity,'contract_digest',p_contract_digest,'predecessor_set_digest',p_predecessor_set_digest,'transaction_digest',p_transaction_digest,'activation_authorized',false)));

    result := jsonb_build_object('success',true,'status','many_to_one_replacement_created','replacement_identity',p_replacement_identity,'successor_mission_id',successor_id,'successor_status','paused','predecessor_count',predecessor_count,'transaction_digest',p_transaction_digest,'replayed',false,'rows_changed',predecessor_count+1);
    insert into public.charlie_mission_replacement_batches values(p_replacement_identity,successor_id,p_contract_digest,p_predecessor_set_digest,p_transaction_digest,p_owner_authorization->>'authorization_digest',p_owner_authorization->>'owner_identity_hash',p_owner_authorization,contract,predecessors,result,now());
    for predecessor in select value from jsonb_array_elements(predecessors) order by value->>'mission_id' loop
        select * into predecessor_row from public.charlie_missions where mission_id=predecessor->>'mission_id';
        insert into public.charlie_mission_replacement_bindings(replacement_identity,successor_mission_id,predecessor_mission_id,expected_status,expected_content_digest,expected_metadata_generation,predecessor_snapshot_json,unfinished_value_reference)
        values(p_replacement_identity,successor_id,predecessor_row.mission_id,predecessor->>'expected_status',predecessor->>'expected_content_digest',predecessor->>'expected_metadata_generation',to_jsonb(predecessor_row),predecessor->>'unfinished_value_reference');
        insert into public.charlie_mission_replacement_audit_events values('CHARLIE-REPLACE-AUDIT-'||upper(substr(public.charlie_sha256(p_replacement_identity||'|bound|'||predecessor_row.mission_id),1,24)),p_replacement_identity,'predecessor_bound',predecessor_row.mission_id,p_transaction_digest,jsonb_build_object('expected',predecessor,'snapshot_digest',public.charlie_mission_replacement_content_digest(predecessor_row)),now());
    end loop;
    insert into public.charlie_mission_replacement_audit_events values('CHARLIE-REPLACE-AUDIT-'||upper(substr(public.charlie_sha256(p_replacement_identity||'|committed'),1,24)),p_replacement_identity,'replacement_committed',successor_id,p_transaction_digest,jsonb_build_object('owner_authorization_digest',p_owner_authorization->>'authorization_digest','owner_authorization',p_owner_authorization,'predecessor_count',predecessor_count,'successor_status','paused'),now());
    return result;
end;
$$;

do $$ begin
 if not exists(select 1 from pg_roles where rolname='charlie_mission_replacement_writer') then create role charlie_mission_replacement_writer nologin nosuperuser nocreatedb nocreaterole noinherit; end if;
 if not exists(select 1 from pg_roles where rolname='charlie_mission_replacement_authorizer') then create role charlie_mission_replacement_authorizer nologin nosuperuser nocreatedb nocreaterole noinherit; end if;
end $$;
alter table public.charlie_mission_replacement_authorizations enable row level security;
alter table public.charlie_mission_replacement_batches enable row level security;
alter table public.charlie_mission_replacement_bindings enable row level security;
alter table public.charlie_mission_replacement_audit_events enable row level security;
revoke all on public.charlie_mission_replacement_authorizations,public.charlie_mission_replacement_batches,public.charlie_mission_replacement_bindings,public.charlie_mission_replacement_audit_events from public,anon,authenticated,service_role,charlie_mission_replacement_writer,charlie_mission_replacement_authorizer;
grant select on public.charlie_mission_replacement_authorizations to charlie_mission_replacement_writer,charlie_mission_replacement_authorizer;
grant select on public.charlie_missions,public.charlie_mission_replacement_batches,public.charlie_mission_replacement_bindings,public.charlie_mission_replacement_audit_events to charlie_mission_replacement_writer;
grant select on public.charlie_mission_replacement_batches,public.charlie_mission_replacement_bindings,public.charlie_mission_replacement_audit_events to service_role;
grant select on public.charlie_mission_replacement_bindings to charlie_owner_execution_hold_writer;
drop policy if exists charlie_replacement_writer_read_batches on public.charlie_mission_replacement_batches;
create policy charlie_replacement_writer_read_batches on public.charlie_mission_replacement_batches for select to charlie_mission_replacement_writer,service_role using(true);
drop policy if exists charlie_replacement_writer_read_bindings on public.charlie_mission_replacement_bindings;
create policy charlie_replacement_writer_read_bindings on public.charlie_mission_replacement_bindings for select to charlie_mission_replacement_writer,service_role using(true);
drop policy if exists charlie_hold_writer_read_bindings on public.charlie_mission_replacement_bindings;
create policy charlie_hold_writer_read_bindings on public.charlie_mission_replacement_bindings for select to charlie_owner_execution_hold_writer using(true);
drop policy if exists charlie_replacement_writer_read_audit on public.charlie_mission_replacement_audit_events;
create policy charlie_replacement_writer_read_audit on public.charlie_mission_replacement_audit_events for select to charlie_mission_replacement_writer,service_role using(true);
drop policy if exists charlie_replacement_authorization_read on public.charlie_mission_replacement_authorizations;
create policy charlie_replacement_authorization_read on public.charlie_mission_replacement_authorizations for select to charlie_mission_replacement_writer,charlie_mission_replacement_authorizer using(true);
revoke all on function public.append_charlie_mission_replacement_authorization(text,text) from public,anon,authenticated,service_role,charlie_mission_replacement_writer;
grant execute on function public.append_charlie_mission_replacement_authorization(text,text) to charlie_mission_replacement_authorizer;
revoke all on function public.apply_charlie_many_to_one_replacement(text,text,text,text,text,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.apply_charlie_many_to_one_replacement(text,text,text,text,text,text,jsonb) to charlie_mission_replacement_writer;

insert into app_private.migration_log(migration_id,description) values('202608020001_create_charlie_many_to_one_replacements','Create append-only atomic many-to-one CORE mission replacement rail.') on conflict(migration_id) do nothing;
