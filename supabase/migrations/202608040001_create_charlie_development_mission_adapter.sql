create extension if not exists pgcrypto;

create or replace function public.charlie_development_canonical_json(p_value jsonb)
returns text language plpgsql immutable set search_path=public,pg_temp as $$
declare rendered text;
begin
  if jsonb_typeof(p_value)='object' then
    select '{'||coalesce(string_agg(to_jsonb(key)::text||':'||public.charlie_development_canonical_json(value),',' order by key),'')||'}'
      into rendered from jsonb_each(p_value);
    return rendered;
  elsif jsonb_typeof(p_value)='array' then
    select '['||coalesce(string_agg(public.charlie_development_canonical_json(value),',' order by ordinal),'')||']'
      into rendered from jsonb_array_elements(p_value) with ordinality rows(value,ordinal);
    return rendered;
  end if;
  return p_value::text;
end $$;

create table if not exists public.charlie_development_authorization_grants (
    authorization_digest text primary key check (authorization_digest ~ '^[0-9a-f]{64}$'),
    action text not null check (action in ('authorize_insert','release')),
    mission_id text not null,
    proposal_digest text not null check (proposal_digest ~ '^[0-9a-f]{64}$'),
    plan_id text not null,
    signed_envelope_json jsonb not null,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_development_command_results (
    command_digest text primary key check (command_digest ~ '^[0-9a-f]{64}$'),
    mission_id text not null,
    operation text not null,
    proposal_digest text not null,
    command_json jsonb not null,
    result_json jsonb not null,
    created_at timestamptz not null default now()
);
alter table public.charlie_development_command_results add column if not exists command_json jsonb;
drop trigger if exists charlie_development_results_append_only on public.charlie_development_command_results;
update public.charlie_development_command_results set command_json='{}'::jsonb where command_json is null;
alter table public.charlie_development_command_results alter column command_json set not null;
create table if not exists public.charlie_development_dispatch_grants (
    dispatch_grant_digest text primary key check (dispatch_grant_digest ~ '^[0-9a-f]{64}$'),
    mission_id text not null,
    proposal_digest text not null check (proposal_digest ~ '^[0-9a-f]{64}$'),
    plan_id text not null,
    worker_id text not null,
    worker_role text not null,
    dispatch_id text not null,
    signed_envelope_json jsonb not null,
    created_at timestamptz not null default now()
);
create table if not exists public.charlie_development_lineage_grants (
    proof_digest text primary key check (proof_digest ~ '^[0-9a-f]{64}$'),
    mission_id text not null,
    proposal_digest text not null check (proposal_digest ~ '^[0-9a-f]{64}$'),
    base_revision text not null check (base_revision ~ '^[0-9a-f]{40}$'),
    candidate_revision text not null check (candidate_revision ~ '^[0-9a-f]{40}$'),
    changed_files jsonb not null,
    proof_json jsonb not null,
    created_at timestamptz not null default now()
);

revoke all on public.charlie_development_authorization_grants from public, anon, authenticated, service_role;
revoke all on public.charlie_development_command_results from public, anon, authenticated, service_role;
revoke all on public.charlie_development_dispatch_grants from public, anon, authenticated, service_role;
revoke all on public.charlie_development_lineage_grants from public, anon, authenticated, service_role;

do $$ begin
  if not exists(select 1 from pg_roles where rolname='charlie_development_mission_authorizer') then
    create role charlie_development_mission_authorizer nologin;
  end if;
  if not exists(select 1 from pg_roles where rolname='charlie_development_mission_writer') then
    create role charlie_development_mission_writer nologin;
  end if;
  if not exists(select 1 from pg_roles where rolname='charlie_development_dispatch_authorizer') then
    create role charlie_development_dispatch_authorizer nologin;
  end if;
  if not exists(select 1 from pg_roles where rolname='charlie_development_lineage_authorizer') then
    create role charlie_development_lineage_authorizer nologin;
  end if;
end $$;

create or replace function public.append_charlie_development_lineage_grant(
    p_mission_id text, p_proposal_digest text, p_proof jsonb
) returns text language plpgsql security definer set search_path=public,pg_temp as $$
declare existing jsonb; pd text := p_proof->>'proof_digest';
begin
  if not ((current_setting('role',true) in ('none','') and session_user='postgres')
          or current_setting('role',true)='charlie_development_lineage_authorizer'
          or session_user='charlie_development_lineage_authorizer') then
    raise exception 'development_lineage_authorizer_role_required';
  end if;
  if pd !~ '^[0-9a-f]{64}$' or p_proposal_digest !~ '^[0-9a-f]{64}$'
     or encode(digest(convert_to(public.charlie_development_canonical_json(p_proof-'proof_digest'::text),'UTF8'),'sha256'),'hex')<>pd
     or p_proof->>'verified_by'<>'charlie_repo_gate'
     or p_proof->>'mission_id'<>p_mission_id or p_proof->>'proposal_digest'<>p_proposal_digest
     or p_proof->>'base_revision' !~ '^[0-9a-f]{40}$'
     or p_proof->>'candidate_revision' !~ '^[0-9a-f]{40}$'
     or jsonb_typeof(p_proof->'changed_files')<>'array' then
    raise exception 'development_lineage_grant_invalid';
  end if;
  select proof_json into existing from public.charlie_development_lineage_grants where proof_digest=pd;
  if existing is not null then
    if existing<>p_proof then raise exception 'development_lineage_grant_collision'; end if;
    return pd;
  end if;
  insert into public.charlie_development_lineage_grants
    (proof_digest,mission_id,proposal_digest,base_revision,candidate_revision,changed_files,proof_json)
  values(pd,p_mission_id,p_proposal_digest,p_proof->>'base_revision',p_proof->>'candidate_revision',p_proof->'changed_files',p_proof);
  return pd;
end $$;

create or replace function public.append_charlie_development_authorization(
    p_envelope jsonb, p_authorization_digest text
) returns text language plpgsql security definer set search_path=public,pg_temp as $$
declare existing jsonb;
begin
  if not ((current_setting('role',true) in ('none','') and session_user='postgres')
          or current_setting('role',true)='charlie_development_mission_authorizer'
          or session_user='charlie_development_mission_authorizer') then
    raise exception 'development_authorizer_role_required';
  end if;
  if p_authorization_digest !~ '^[0-9a-f]{64}$'
     or encode(digest(convert_to(public.charlie_development_canonical_json(p_envelope),'UTF8'),'sha256'),'hex')<>p_authorization_digest then
    raise exception 'development_authorization_digest_invalid';
  end if;
  if p_envelope->>'action' not in ('authorize_insert','release')
     or p_envelope->>'mission_id' is null or p_envelope->>'proposal_digest' !~ '^[0-9a-f]{64}$'
     or p_envelope->>'plan_id' is null or p_envelope->>'owner_identity_hash' !~ '^[0-9a-f]{64}$'
     or p_envelope->>'signature' !~ '^[0-9a-f]{64}$'
     or (p_envelope->>'issued_at')::timestamptz > now()+interval '30 seconds'
     or (p_envelope->>'expires_at')::timestamptz <= now()
     or (p_envelope->>'expires_at')::timestamptz > (p_envelope->>'issued_at')::timestamptz+interval '15 minutes' then
    raise exception 'development_authorization_envelope_invalid';
  end if;
  select signed_envelope_json into existing from public.charlie_development_authorization_grants
   where authorization_digest=p_authorization_digest;
  if existing is not null then
    if existing <> p_envelope then raise exception 'development_authorization_collision'; end if;
    return p_authorization_digest;
  end if;
  insert into public.charlie_development_authorization_grants
    (authorization_digest,action,mission_id,proposal_digest,plan_id,signed_envelope_json)
  values (p_authorization_digest,p_envelope->>'action',p_envelope->>'mission_id',
          p_envelope->>'proposal_digest',p_envelope->>'plan_id',p_envelope);
  return p_authorization_digest;
end $$;

create or replace function public.append_charlie_development_dispatch_grant(
    p_envelope jsonb, p_dispatch_grant_digest text
) returns text language plpgsql security definer set search_path=public,pg_temp as $$
declare existing jsonb;
begin
  if not ((current_setting('role',true) in ('none','') and session_user='postgres')
          or current_setting('role',true)='charlie_development_dispatch_authorizer'
          or session_user='charlie_development_dispatch_authorizer') then
    raise exception 'development_dispatch_authorizer_role_required';
  end if;
  if p_dispatch_grant_digest !~ '^[0-9a-f]{64}$'
     or encode(digest(convert_to(public.charlie_development_canonical_json(p_envelope),'UTF8'),'sha256'),'hex')<>p_dispatch_grant_digest
     or p_envelope->>'proposal_digest' !~ '^[0-9a-f]{64}$'
     or p_envelope->>'mission_id' is null or p_envelope->>'plan_id' is null
     or p_envelope->>'worker_id' is null or p_envelope->>'worker_role' is null
     or p_envelope->>'dispatch_id' is null or p_envelope->>'signature' !~ '^[0-9a-f]{64}$'
     or (p_envelope->>'issued_at')::timestamptz > now()+interval '30 seconds'
     or (p_envelope->>'expires_at')::timestamptz <= (p_envelope->>'issued_at')::timestamptz
     or (p_envelope->>'expires_at')::timestamptz > (p_envelope->>'issued_at')::timestamptz+interval '15 minutes' then
    raise exception 'development_dispatch_grant_invalid';
  end if;
  select signed_envelope_json into existing from public.charlie_development_dispatch_grants
   where dispatch_grant_digest=p_dispatch_grant_digest;
  if existing is not null then
    if existing <> p_envelope then raise exception 'development_dispatch_grant_collision'; end if;
    return p_dispatch_grant_digest;
  end if;
  insert into public.charlie_development_dispatch_grants
    (dispatch_grant_digest,mission_id,proposal_digest,plan_id,worker_id,worker_role,dispatch_id,signed_envelope_json)
  values(p_dispatch_grant_digest,p_envelope->>'mission_id',p_envelope->>'proposal_digest',p_envelope->>'plan_id',
         p_envelope->>'worker_id',p_envelope->>'worker_role',p_envelope->>'dispatch_id',p_envelope);
  return p_dispatch_grant_digest;
end $$;

create or replace function public.apply_charlie_development_command(p_command jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare
  op text := p_command->>'operation'; mid text := p_command->>'mission_id';
  pd text := p_command->>'proposal_digest'; cd text := p_command->>'command_digest';
  auth text := p_command->>'authorization_digest'; md jsonb; st text; coord jsonb;
  prior jsonb; prior_command jsonb; result jsonb; event_json jsonb; event_id text; proposal jsonb;
begin
  if not ((current_setting('role',true) in ('none','') and session_user='postgres')
          or current_setting('role',true)='charlie_development_mission_writer'
          or session_user='charlie_development_mission_writer') then
    raise exception 'development_writer_role_required';
  end if;
  if op not in ('authorize_insert','release','dispatch','event') or mid is null
     or pd !~ '^[0-9a-f]{64}$' or cd !~ '^[0-9a-f]{64}$' then
    raise exception 'development_command_invalid';
  end if;
  if encode(digest(convert_to(p_command->>'command_canonical','UTF8'),'sha256'),'hex') <> cd
     or (p_command->>'command_canonical')::jsonb <> (p_command - 'command_canonical'::text - 'command_digest'::text) then
    raise exception 'development_command_digest_invalid';
  end if;
  if encode(digest(convert_to(p_command->>'proposal_canonical','UTF8'),'sha256'),'hex') <> pd then
    raise exception 'development_proposal_digest_invalid';
  end if;
  proposal := (p_command->>'proposal_canonical')::jsonb;
  if proposal->>'version'<>'charlie_development_mission_adapter_v1'
     or proposal->'mission'->>'mission_id'<>mid
     or proposal->'plan'->>'plan_id'<>p_command->>'plan_id' then
    raise exception 'development_proposal_binding_invalid';
  end if;
  perform pg_advisory_xact_lock(hashtext(mid));
  select result_json,command_json into prior,prior_command from public.charlie_development_command_results where command_digest=cd;
  if prior is not null then
    if prior_command<>p_command then raise exception 'development_command_identity_collision'; end if;
    for event_json in select value from jsonb_array_elements(coalesce(p_command->'events','[]'::jsonb)) loop
      if not exists(select 1 from public.charlie_mission_events e
                    where e.event_id=event_json->>'event_id'
                      and e.metadata_json->>'event_digest'=event_json->>'event_digest') then
        raise exception 'development_replay_evidence_incomplete';
      end if;
    end loop;
    return prior || jsonb_build_object('replayed',true,'rows_changed',0);
  end if;

  if op in ('authorize_insert','release') and not exists(
      select 1 from public.charlie_development_authorization_grants g
       where g.authorization_digest=auth and g.action=op and g.mission_id=mid
         and g.proposal_digest=pd and g.plan_id=p_command->>'plan_id'
         and (g.signed_envelope_json->>'expires_at')::timestamptz>now()) then
    raise exception 'development_authorization_grant_missing';
  end if;

  if op='authorize_insert' then
    if exists(select 1 from public.charlie_missions where mission_id=mid) then
      raise exception 'development_mission_identity_collision';
    end if;
    md := p_command->'metadata';
    coord := md->'development_coordination';
    if p_command->'mission'<>proposal->'mission'
       or coord->'plan'<>proposal->'plan'
       or coord->'scope'<>proposal->'mission'->'expected_files'
       or coord->'declared_artifacts'<>proposal->'mission'->'expected_files'
       or coord->>'acknowledgement_timeout_seconds'<>proposal->'mission'->>'acknowledgement_timeout_seconds'
       or coord->'parent_lineage'<>proposal->'mission'->'parent_lineage'
       or coord->>'selected_worker'<>proposal->'plan'->'agents'->>0
       or coord->>'state'<>'owner_authorized' or coord->>'proposal_digest'<>pd
       or coord->>'authorization_digest'<>auth
       or jsonb_array_length(coord->'plan'->'agents')<>1
       or md->'agentic_architecture_packet'->>'ordinary_farm_routing'<>'false'
       or md->'intake'->>'mission_kind'<>'software_development' then
      raise exception 'development_insert_contract_invalid';
    end if;
    insert into public.charlie_missions
      (mission_id,status,source,raw_text,title,urgency,mission_type,approval_level,metadata_json,created_at,updated_at)
    values(mid,'paused','charlie_core_governed',p_command->'mission'->>'raw_text',
      p_command->'mission'->>'title',p_command->'mission'->>'urgency',
      p_command->'mission'->>'mission_type','LEVEL 3',md,now(),now());
  else
    select status,metadata_json into st,md from public.charlie_missions where mission_id=mid for update;
    if not found then raise exception 'development_mission_not_found'; end if;
    coord := md->'development_coordination';
    if coord->>'proposal_digest'<>pd then raise exception 'development_persisted_contract_mismatch'; end if;
    if op='release' and (st<>'paused' or coord->>'state'<>'owner_authorized'
          or p_command->'new_coordination'->>'state'<>'released'
          or p_command->'new_coordination'->>'proposal_digest'<>pd
          or p_command->'new_coordination'->>'release_authorization_digest'<>auth
          or ((p_command->'new_coordination')-'{state,release_authorization_digest}'::text[])
             <>(coord-'{state,release_authorization_digest}'::text[])
          or p_command->>'new_status'<>'paused') then
      raise exception 'development_release_state_invalid';
    elsif op='dispatch' and (st<>'paused' or coord->>'state'<>'released'
          or p_command->>'new_status'<>'paused'
          or p_command->'dispatch_grant'->>'worker_role'<>coord->>'selected_worker'
          or not exists(select 1 from public.charlie_development_dispatch_grants g
                        where g.dispatch_grant_digest=p_command->'dispatch_grant'->>'dispatch_grant_digest'
                          and g.mission_id=mid and g.proposal_digest=pd and g.plan_id=p_command->>'plan_id'
                          and g.worker_id=p_command->'dispatch_grant'->>'worker_id'
                          and g.worker_role=p_command->'dispatch_grant'->>'worker_role'
                          and g.dispatch_id=p_command->'dispatch_grant'->>'dispatch_id'
                          and g.signed_envelope_json=((p_command->'dispatch_grant')-'dispatch_grant_digest'::text)
                          and (g.signed_envelope_json->>'expires_at')::timestamptz>now())) then
      raise exception 'development_dispatch_contract_invalid';
    elsif op='event' then
      if p_command->>'expected_state'<>coord->>'state' then raise exception 'development_event_state_invalid'; end if;
      if p_command->'new_coordination'->>'proposal_digest'<>pd then raise exception 'development_event_contract_invalid'; end if;
      if p_command->>'event_kind' not in ('acknowledged','started','waiting_for_evidence','completed','contain_missing_ack') then
        raise exception 'development_event_kind_invalid';
      end if;
      if ((p_command->'new_coordination')-'{state,last_event_id,receipt}'::text[])
           <>(coord-'{state,last_event_id,receipt}'::text[])
         or p_command->'new_coordination'->>'last_event_id'<>p_command->>'event_identity'
         or (p_command->>'event_kind'<>'acknowledged'
             and p_command->'new_coordination'->'receipt' is distinct from coord->'receipt') then
        raise exception 'development_event_frozen_coordination_invalid';
      end if;
      if p_command->>'dispatch_grant_digest'<>coord->'dispatch_grant'->>'dispatch_grant_digest' then
        raise exception 'development_dispatch_binding_invalid';
      end if;
      if p_command->>'event_kind'='acknowledged' and not (
           st='paused' and p_command->>'new_status'='paused' and coord->>'state'='released'
           and p_command->'new_coordination'->>'state'='acknowledged'
           and p_command->'new_coordination'->'receipt'->>'worker_id'=coord->'dispatch_grant'->>'worker_id'
           and p_command->'new_coordination'->'receipt'->>'worker_role'=coord->'dispatch_grant'->>'worker_role'
           and p_command->'new_coordination'->'receipt'->>'dispatch_id'=coord->'dispatch_grant'->>'dispatch_id'
           and (p_command->'new_coordination'->'receipt'->>'acknowledged_at')::timestamptz between now()-interval '5 minutes' and now()+interval '30 seconds') then
        raise exception 'development_acknowledgement_contract_invalid';
      elsif p_command->>'event_kind'='started' and not (
           st='paused' and coord->>'state'='acknowledged' and p_command->'new_coordination'->>'state'='started'
           and p_command->>'new_status'='in_progress'
           and p_command->'events'->0->'metadata'->>'worker_id'=coord->'dispatch_grant'->>'worker_id'
           and p_command->'events'->0->'metadata'->>'dispatch_id'=coord->'dispatch_grant'->>'dispatch_id'
           and (p_command->'events'->0->'metadata'->>'heartbeat_at')::timestamptz between now()-interval '5 minutes' and now()+interval '30 seconds') then
        raise exception 'development_start_contract_invalid';
      elsif p_command->>'event_kind'='waiting_for_evidence' and not (
           st='in_progress' and p_command->>'new_status'='in_progress'
           and coord->>'state' in ('started','waiting_for_evidence')
           and p_command->'new_coordination'->>'state'='waiting_for_evidence'
           and p_command->'events'->0->'metadata'->>'worker_id'=coord->'dispatch_grant'->>'worker_id'
           and p_command->'events'->0->'metadata'->>'dispatch_id'=coord->'dispatch_grant'->>'dispatch_id'
           and (p_command->'events'->0->'metadata'->>'heartbeat_at')::timestamptz between now()-interval '5 minutes' and now()+interval '30 seconds') then
        raise exception 'development_progress_contract_invalid';
      elsif p_command->>'event_kind'='completed' and not (
           st='in_progress' and coord->>'state' in ('started','waiting_for_evidence')
           and p_command->'new_coordination'->>'state'='completed_with_artifact'
           and p_command->>'new_status'='pr_ready'
           and p_command->'events'->0->'metadata'->>'worker_id'=coord->'dispatch_grant'->>'worker_id'
           and p_command->'events'->0->'metadata'->>'dispatch_id'=coord->'dispatch_grant'->>'dispatch_id'
           and p_command->'events'->0->'metadata'->'artifact'->>'base_revision'=proposal->'mission'->>'source_base_revision'
           and p_command->'events'->0->'metadata'->'artifact'->>'candidate_revision' ~ '^[0-9a-f]{40}$'
           and p_command->'events'->0->'metadata'->'artifact'->'changed_files'=coord->'declared_artifacts'
           and p_command->'events'->0->'metadata'->'artifact'->'repository_lineage'->>'verified_by'='charlie_repo_gate'
           and p_command->'events'->0->'metadata'->'artifact'->'repository_lineage'->>'proof_digest' ~ '^[0-9a-f]{64}$'
           and exists(select 1 from public.charlie_development_lineage_grants lg
                      where lg.proof_digest=p_command->'events'->0->'metadata'->'artifact'->'repository_lineage'->>'proof_digest'
                        and lg.mission_id=mid and lg.proposal_digest=pd
                        and lg.base_revision=p_command->'events'->0->'metadata'->'artifact'->>'base_revision'
                        and lg.candidate_revision=p_command->'events'->0->'metadata'->'artifact'->>'candidate_revision'
                        and lg.changed_files=p_command->'events'->0->'metadata'->'artifact'->'changed_files')
           and jsonb_array_length(p_command->'events'->0->'metadata'->'artifact'->'artifact_evidence')=jsonb_array_length(coord->'declared_artifacts')
           and not exists(select 1 from jsonb_array_elements(coord->'declared_artifacts') declared
                          where not exists(select 1 from jsonb_array_elements(p_command->'events'->0->'metadata'->'artifact'->'artifact_evidence') evidence
                                           where evidence->>'path'=declared#>>'{}'))
           and not exists(select 1 from jsonb_array_elements(p_command->'events'->0->'metadata'->'artifact'->'artifact_evidence') evidence
                          where evidence->>'commit_sha' !~ '^[0-9a-f]{40}$'
                             or evidence->>'commit_sha'<>p_command->'events'->0->'metadata'->'artifact'->>'candidate_revision'
                             or coalesce(evidence->>'result_identity','')='')) then
        raise exception 'development_completion_contract_invalid';
      elsif p_command->>'event_kind'='contain_missing_ack' and not (
           st in ('paused','blocked') and coord->>'state' in ('released','contained')
           and p_command->'new_coordination'->>'state'='contained'
           and p_command->>'new_status'='blocked'
           and p_command->'events'->0->'metadata'->>'worker_id'=coord->'dispatch_grant'->>'worker_id'
           and p_command->'events'->0->'metadata'->>'dispatch_id'=coord->'dispatch_grant'->>'dispatch_id'
           and (p_command->'events'->0->'metadata'->>'acknowledgement_deadline')::timestamptz
               =(coord->'dispatch_grant'->>'issued_at')::timestamptz
                 + make_interval(secs=>(coord->>'acknowledgement_timeout_seconds')::int)
           and (p_command->'events'->0->'metadata'->>'observed_at')::timestamptz
               >=(p_command->'events'->0->'metadata'->>'acknowledgement_deadline')::timestamptz
           and (p_command->'events'->0->'metadata'->>'observed_at')::timestamptz
               between now()-interval '5 minutes' and now()+interval '30 seconds') then
        raise exception 'development_containment_contract_invalid';
      end if;
    end if;
    md := jsonb_set(md,'{development_coordination}',
      case when op='dispatch' then jsonb_set(coord,'{dispatch_grant}',p_command->'dispatch_grant',true)
           else p_command->'new_coordination' end,true);
    update public.charlie_missions set status=coalesce(p_command->>'new_status',st),metadata_json=md,updated_at=now() where mission_id=mid;
  end if;

  for event_json in select value from jsonb_array_elements(coalesce(p_command->'events','[]'::jsonb)) loop
    event_id := event_json->>'event_id';
    if event_id is null or event_json->>'event_digest' !~ '^[0-9a-f]{64}$'
       or encode(digest(convert_to(event_json->>'metadata_canonical','UTF8'),'sha256'),'hex')<>event_json->>'event_digest'
       or (event_json->>'metadata_canonical')::jsonb<>(event_json->'metadata')-'event_digest'::text then
      raise exception 'development_event_invalid';
    end if;
    insert into public.charlie_mission_events(event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at)
    values(event_id,mid,'mission_updated',event_json->>'notes','charlie_core_adapter',event_json->'metadata',now());
  end loop;
  if jsonb_array_length(coalesce(p_command->'events','[]'::jsonb))=0 then raise exception 'development_event_incomplete'; end if;
  result := jsonb_build_object('success',true,'operation',op,'mission_id',mid,'rows_changed',1,'replayed',false);
  insert into public.charlie_development_command_results(command_digest,mission_id,operation,proposal_digest,command_json,result_json)
  values(cd,mid,op,pd,p_command,result);
  return result;
end $$;

create or replace function public.read_charlie_development_mission(p_mission_id text)
returns jsonb language plpgsql security definer stable set search_path=public,pg_temp as $$
declare row_json jsonb;
begin
  if not ((current_setting('role',true) in ('none','') and session_user='postgres')
          or current_setting('role',true)='charlie_development_mission_writer'
          or session_user='charlie_development_mission_writer') then
    raise exception 'development_writer_role_required';
  end if;
  select jsonb_build_object('status',status,'metadata',metadata_json) into row_json
  from public.charlie_missions where mission_id=p_mission_id and source='charlie_core_governed';
  return row_json;
end $$;

create or replace function public.read_charlie_development_event(p_event_id text)
returns jsonb language plpgsql security definer stable set search_path=public,pg_temp as $$
declare row_json jsonb;
begin
  if not ((current_setting('role',true) in ('none','') and session_user='postgres')
          or current_setting('role',true)='charlie_development_mission_writer'
          or session_user='charlie_development_mission_writer') then
    raise exception 'development_writer_role_required';
  end if;
  select metadata_json into row_json from public.charlie_mission_events
   where event_id=p_event_id and recorded_by='charlie_core_adapter';
  return row_json;
end $$;

revoke all on function public.append_charlie_development_authorization(jsonb,text) from public, anon, authenticated, service_role;
revoke all on function public.append_charlie_development_dispatch_grant(jsonb,text) from public, anon, authenticated, service_role;
revoke all on function public.append_charlie_development_lineage_grant(text,text,jsonb) from public, anon, authenticated, service_role;
revoke all on function public.apply_charlie_development_command(jsonb) from public, anon, authenticated, service_role;
revoke all on function public.read_charlie_development_mission(text) from public, anon, authenticated, service_role;
revoke all on function public.read_charlie_development_event(text) from public, anon, authenticated, service_role;
grant execute on function public.append_charlie_development_authorization(jsonb,text) to charlie_development_mission_authorizer;
grant execute on function public.append_charlie_development_dispatch_grant(jsonb,text) to charlie_development_dispatch_authorizer;
grant execute on function public.append_charlie_development_lineage_grant(text,text,jsonb) to charlie_development_lineage_authorizer;
grant execute on function public.apply_charlie_development_command(jsonb) to charlie_development_mission_writer;
grant execute on function public.read_charlie_development_mission(text) to charlie_development_mission_writer;
grant execute on function public.read_charlie_development_event(text) to charlie_development_mission_writer;

create or replace function public.reject_charlie_development_history_change() returns trigger
language plpgsql as $$ begin raise exception 'charlie_development_history_append_only'; end $$;
drop trigger if exists charlie_development_authorization_append_only on public.charlie_development_authorization_grants;
create trigger charlie_development_authorization_append_only before update or delete on public.charlie_development_authorization_grants
for each row execute function public.reject_charlie_development_history_change();
drop trigger if exists charlie_development_results_append_only on public.charlie_development_command_results;
create trigger charlie_development_results_append_only before update or delete on public.charlie_development_command_results
for each row execute function public.reject_charlie_development_history_change();
drop trigger if exists charlie_development_dispatch_append_only on public.charlie_development_dispatch_grants;
create trigger charlie_development_dispatch_append_only before update or delete on public.charlie_development_dispatch_grants
for each row execute function public.reject_charlie_development_history_change();
drop trigger if exists charlie_development_lineage_append_only on public.charlie_development_lineage_grants;
create trigger charlie_development_lineage_append_only before update or delete on public.charlie_development_lineage_grants
for each row execute function public.reject_charlie_development_history_change();

insert into app_private.migration_log(migration_id,description)
values('202608040001_create_charlie_development_mission_adapter','Add exact owner-gated CORE development adapter through existing mission and event stores.')
on conflict(migration_id) do nothing;
