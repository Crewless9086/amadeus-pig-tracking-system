-- Canonical Documents ownership for the bounded weekly-sheet Green pilot.
-- This migration is source-only until separately approved and applied.
create schema if not exists app_private;

-- Resolve pgcrypto by its catalog-owned extension schema, never by caller
-- search_path. Supabase commonly installs it in extensions; disposable review
-- databases may use another schema.
create or replace function app_private.pgcrypto_random_hex(p_bytes integer)
returns text language plpgsql security definer set search_path=pg_catalog,app_private as $$
declare v_schema name; v_result text;
begin
  if p_bytes not between 16 and 64 then raise exception 'random byte count invalid'; end if;
  select n.nspname into v_schema from pg_catalog.pg_extension e
    join pg_catalog.pg_namespace n on n.oid=e.extnamespace where e.extname='pgcrypto';
  if v_schema is null then raise exception 'pgcrypto extension required'; end if;
  execute format('select encode(%I.gen_random_bytes($1),''hex'')',v_schema)
    into v_result using p_bytes;
  return v_result;
end; $$;

create table if not exists app_private.document_print_jobs (
    job_id text primary key,
    document_id text not null,
    document_version text not null,
    document_revision integer not null check (document_revision > 0),
    document_type text not null check (document_type = 'farm.weekly_weight_sheet.v1'),
    generator_id text not null check (generator_id = 'web.print_sheets.v1'),
    pdf_sha256 text not null check (pdf_sha256 ~ '^[0-9a-f]{64}$'),
    canonical_input_sha256 text not null check (canonical_input_sha256 ~ '^[0-9a-f]{64}$'),
    pdf_bytes bytea not null check (octet_length(pdf_bytes) between 64 and 5242880),
    retrieval_url text not null,
    options_json jsonb not null check (options_json = '{"media":"A4","copies":1,"color":"monochrome","sides":"one-sided"}'::jsonb),
    authenticated_principal_id text not null,
    requester text not null,
    request_channel text not null,
    green_id text not null,
    printer_id text not null,
    cups_queue_id text not null,
    registry_version text not null,
    authorization_receipt_id text,
    authorization_expires_at timestamptz,
    lease_owner text,
    lease_token text unique,
    lease_expires_at timestamptz,
    attempt_id text,
    cups_job_id text,
    provider_id text,
    command_kind text check (command_kind in ('continue','cancel')),
    command_receipt_id text unique,
    command_authorized_at timestamptz,
    command_status text check (command_status in ('accepted','in_progress','completed')),
    command_outcome text check (command_outcome in ('continued','cancelled','ambiguous')),
    command_accepted_at timestamptz,
    command_completed_at timestamptz,
    state text not null default 'prepared' check (state in
      ('prepared','authorized','claimed','submitting','submitted','provider_completed','held','ambiguous','cancelled','physically_confirmed')),
    retry_deadline timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (document_id, document_version),
    unique (authorization_receipt_id)
);

create table if not exists app_private.document_print_job_events (
    event_id uuid primary key default (md5(random()::text || clock_timestamp()::text)::uuid),
    job_id text not null references app_private.document_print_jobs(job_id),
    event_type text not null,
    event_at timestamptz not null default now(),
    actor_id text not null,
    worker_id text,
    attempt_id text,
    cups_job_id text,
    evidence_sha256 text,
    metadata_json jsonb not null default '{}'::jsonb,
    unique (job_id, event_type, attempt_id, cups_job_id, evidence_sha256)
);

create index if not exists idx_document_print_jobs_state_retry
  on app_private.document_print_jobs(state, retry_deadline);
create index if not exists idx_document_print_events_job_time
  on app_private.document_print_job_events(job_id, event_at, event_id);

revoke all on app_private.document_print_jobs from public, anon, authenticated;
revoke all on app_private.document_print_job_events from public, anon, authenticated;

comment on table app_private.document_print_jobs is
  'Canonical Documents print-job identity; local Green SQLite is recovery state only.';
comment on table app_private.document_print_job_events is
  'Append-only, content-free audit metadata for protected print lifecycle evidence.';

-- API roles call these SECURITY DEFINER functions through a bounded Documents
-- service endpoint. No worker receives direct table authority.
create or replace function app_private.claim_document_print_job(
  p_green_id text, p_worker_id text, p_lease_seconds integer default 300)
returns setof app_private.document_print_jobs
language plpgsql security definer set search_path = pg_catalog, app_private as $$
declare v_job_id text; v_token text := app_private.pgcrypto_random_hex(24);
begin
  if p_worker_id is null or p_lease_seconds not between 30 and 300 then
    raise exception 'invalid claim';
  end if;
  select job_id into v_job_id from app_private.document_print_jobs
   where state = 'authorized' and green_id=p_green_id and retry_deadline > clock_timestamp()
     and authorization_expires_at > clock_timestamp()
   order by created_at, job_id for update skip locked limit 1;
  if v_job_id is null then return; end if;
  update app_private.document_print_jobs set state='claimed', lease_owner=p_worker_id,
    lease_token=v_token, lease_expires_at=clock_timestamp()+make_interval(secs=>p_lease_seconds),
    updated_at=clock_timestamp() where job_id=v_job_id;
  insert into app_private.document_print_job_events(job_id,event_type,actor_id,worker_id,metadata_json)
    values(v_job_id,'lease_claimed','documents-claim-service',p_worker_id,jsonb_build_object('lease_token_fingerprint',md5(v_token)));
  return query select * from app_private.document_print_jobs where job_id=v_job_id;
end; $$;

create or replace function app_private.transition_document_print_job(
  p_job_id text, p_lease_token text, p_document_version text, p_pdf_sha256 text,
  p_authorization_receipt_id text, p_target_state text, p_event_id uuid,
  p_green_id text,p_worker_id text,p_metadata jsonb default '{}'::jsonb)
returns app_private.document_print_jobs
language plpgsql security definer set search_path = pg_catalog, app_private as $$
declare v_job app_private.document_print_jobs;
        v_event app_private.document_print_job_events;
        v_attempt_id text;
        v_cups_job_id text;
        v_provider_id text;
begin
  select * into v_job from app_private.document_print_jobs where job_id=p_job_id for update;
  if not found or v_job.lease_token is distinct from p_lease_token or
     v_job.green_id is distinct from p_green_id or v_job.lease_owner is distinct from p_worker_id or
     v_job.lease_expires_at <= clock_timestamp() or v_job.document_version<>p_document_version or
     v_job.pdf_sha256<>p_pdf_sha256 or v_job.authorization_receipt_id<>p_authorization_receipt_id then
    raise exception 'lease fence or binding invalid';
  end if;
  if p_metadata is null or jsonb_typeof(p_metadata) <> 'object'
     or exists (select 1 from jsonb_object_keys(p_metadata) as key
                where key not in ('attempt_id','cups_job_id','provider_id','observed_at','reason')) then
    raise exception 'transition metadata invalid';
  end if;
  select * into v_event from app_private.document_print_job_events where event_id=p_event_id;
  if found then
    if v_event.job_id<>p_job_id or v_event.event_type<>'state_'||p_target_state
       or v_event.worker_id is distinct from v_job.lease_owner
       or v_event.metadata_json is distinct from p_metadata then
      raise exception 'transition replay identity invalid';
    end if;
    return v_job;
  end if;
  -- This is the ordinary Green worker rail.  It may advance only one lawful
  -- provider lifecycle edge (or enter a fail-safe hold).  Physical proof and
  -- protected cancellation are deliberately outside this credential/function.
  if not ((v_job.state='claimed' and p_target_state in ('submitting','held','ambiguous')) or
          (v_job.state='submitting' and p_target_state in ('submitted','held','ambiguous')) or
          (v_job.state='submitted' and p_target_state in ('provider_completed','held','ambiguous'))) then
    raise exception 'state transition invalid';
  end if;
  v_attempt_id := nullif(p_metadata->>'attempt_id','');
  v_cups_job_id := nullif(p_metadata->>'cups_job_id','');
  v_provider_id := nullif(p_metadata->>'provider_id','');
  if exists (select 1 from jsonb_each(p_metadata) as item
             where jsonb_typeof(item.value)<>'string') or
     (v_attempt_id is not null and v_attempt_id !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') or
     (v_cups_job_id is not null and v_cups_job_id !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') or
     (v_provider_id is not null and (length(v_provider_id)>512 or v_provider_id !~ '^ipps://[^[:space:]]+$')) or
     (p_metadata ? 'observed_at' and nullif(p_metadata->>'observed_at','') is null) or
     (p_metadata ? 'reason' and (nullif(p_metadata->>'reason','') is null or length(p_metadata->>'reason')>160)) then
    raise exception 'transition metadata identity invalid';
  end if;
  if (v_job.attempt_id is not null and v_attempt_id is not null and v_job.attempt_id<>v_attempt_id) or
     (v_job.cups_job_id is not null and v_cups_job_id is not null and v_job.cups_job_id<>v_cups_job_id) or
     (v_job.provider_id is not null and v_provider_id is not null and v_job.provider_id<>v_provider_id) then
    raise exception 'transition immutable identity invalid';
  end if;
  if p_target_state='submitting' and (v_attempt_id is null or v_cups_job_id is not null or v_provider_id is not null) then
    raise exception 'submitting identity invalid';
  end if;
  if p_target_state='submitted' and
     (coalesce(v_job.attempt_id,v_attempt_id) is null or v_cups_job_id is null or v_provider_id is null) then
    raise exception 'submitted identity invalid';
  end if;
  if p_target_state='provider_completed' and
     (v_job.attempt_id is null or v_job.cups_job_id is null or v_job.provider_id is null or
      v_attempt_id is distinct from v_job.attempt_id or v_cups_job_id is distinct from v_job.cups_job_id or
      v_provider_id is distinct from v_job.provider_id) then
    raise exception 'provider completion identity invalid';
  end if;
  insert into app_private.document_print_job_events(event_id,job_id,event_type,actor_id,worker_id,attempt_id,cups_job_id,metadata_json)
    values(p_event_id,p_job_id,'state_'||p_target_state,'documents-worker',v_job.lease_owner,
      coalesce(v_attempt_id,v_job.attempt_id),coalesce(v_cups_job_id,v_job.cups_job_id),p_metadata)
    on conflict(event_id) do nothing;
  if not found then return v_job; end if;
  update app_private.document_print_jobs set state=p_target_state,
    attempt_id=coalesce(v_attempt_id,attempt_id),
    cups_job_id=coalesce(v_cups_job_id,cups_job_id),
    provider_id=coalesce(v_provider_id,provider_id),updated_at=clock_timestamp()
    where job_id=p_job_id returning * into v_job;
  return v_job;
end; $$;

create or replace function app_private.transition_document_print_command(
  p_job_id text, p_lease_token text, p_document_version text, p_pdf_sha256 text,
  p_authorization_receipt_id text, p_command_receipt_id text, p_command_kind text,
  p_target_state text,p_green_id text,p_worker_id text)
returns jsonb language plpgsql security definer set search_path = pg_catalog, app_private as $$
declare v_job app_private.document_print_jobs;
begin
  select * into v_job from app_private.document_print_jobs where job_id=p_job_id for update;
  if not found then raise exception 'command job missing'; end if;
  -- Completed outcomes remain protected command data.  A takeover may read the
  -- durable outcome only after claim_document_print_command has issued the
  -- recovering worker a current lease; this path never authorizes or resumes
  -- provider work.
  if v_job.lease_token is distinct from p_lease_token or v_job.lease_expires_at<=clock_timestamp()
     or v_job.green_id is distinct from p_green_id or v_job.lease_owner is distinct from p_worker_id
     or v_job.document_version<>p_document_version or v_job.pdf_sha256<>p_pdf_sha256
     or v_job.authorization_receipt_id<>p_authorization_receipt_id
     or v_job.command_receipt_id<>p_command_receipt_id or v_job.command_kind<>p_command_kind then
    raise exception 'command fence or binding invalid';
  end if;
  if v_job.command_receipt_id=p_command_receipt_id and v_job.command_kind=p_command_kind
     and v_job.command_status='completed' then
    return jsonb_build_object('state',v_job.state,'command_status','completed',
      'command_outcome',v_job.command_outcome,'command_replay',true,
      'command_receipt_id',p_command_receipt_id,'attempt_id',v_job.attempt_id,
      'cups_job_id',v_job.cups_job_id,'provider_id',v_job.provider_id);
  end if;
  if p_target_state='accepted' then
    if v_job.command_status in ('accepted','in_progress') then
      return jsonb_build_object('state',v_job.state,'command_status','in_progress',
        'command_replay',true,'command_receipt_id',p_command_receipt_id,
        'attempt_id',v_job.attempt_id,'cups_job_id',v_job.cups_job_id,
        'provider_id',v_job.provider_id);
    end if;
    if not ((p_command_kind='continue' and v_job.state='held') or
            (p_command_kind='cancel' and v_job.state in ('claimed','submitting','submitted','held','ambiguous'))) then
      raise exception 'command acceptance invalid';
    end if;
    insert into app_private.document_print_job_events(job_id,event_type,actor_id,worker_id,attempt_id,cups_job_id,metadata_json)
      values(p_job_id,'command_'||p_command_kind||'_accepted','documents-command-service',v_job.lease_owner,
        v_job.attempt_id,v_job.cups_job_id,jsonb_build_object('command_receipt_id',p_command_receipt_id,
        'authorization_receipt_id',v_job.authorization_receipt_id,'document_version',v_job.document_version,
        'pdf_sha256',v_job.pdf_sha256,'provider_id',v_job.provider_id));
    update app_private.document_print_jobs set command_status='in_progress',command_accepted_at=clock_timestamp(),
      updated_at=clock_timestamp() where job_id=p_job_id returning * into v_job;
    return jsonb_build_object('state',v_job.state,'command_status','in_progress',
      'command_replay',false,'command_receipt_id',p_command_receipt_id,
      'attempt_id',v_job.attempt_id,'cups_job_id',v_job.cups_job_id,'provider_id',v_job.provider_id);
  end if;
  if v_job.command_status not in ('accepted','in_progress') or
     not ((p_command_kind='continue' and p_target_state='continued') or
          (p_command_kind='cancel' and p_target_state in ('cancelled','ambiguous'))) then
    raise exception 'command completion invalid';
  end if;
  insert into app_private.document_print_job_events(job_id,event_type,actor_id,worker_id,attempt_id,cups_job_id,metadata_json)
    values(p_job_id,'command_'||p_command_kind||'_completed','documents-command-service',v_job.lease_owner,
      v_job.attempt_id,v_job.cups_job_id,jsonb_build_object('command_receipt_id',p_command_receipt_id,
      'command_outcome',p_target_state,'provider_id',v_job.provider_id));
  update app_private.document_print_jobs set
    state=case when p_target_state='continued' then 'claimed' else p_target_state end,
    command_status='completed',command_outcome=p_target_state,command_completed_at=clock_timestamp(),updated_at=clock_timestamp()
    where job_id=p_job_id returning * into v_job;
  return jsonb_build_object('state',v_job.state,'command_status','completed',
    'command_outcome',v_job.command_outcome,'command_replay',false,
    'command_receipt_id',p_command_receipt_id,'attempt_id',v_job.attempt_id,
    'cups_job_id',v_job.cups_job_id,'provider_id',v_job.provider_id);
end; $$;

create or replace function app_private.renew_document_print_job_lease(
  p_job_id text,p_lease_token text,p_worker_id text,p_lease_seconds integer,
  p_document_version text,p_pdf_sha256 text,p_authorization_receipt_id text)
returns app_private.document_print_jobs language plpgsql security definer set search_path=pg_catalog,app_private as $$
declare v_job app_private.document_print_jobs;
begin
  select * into v_job from app_private.document_print_jobs where job_id=p_job_id for update;
  if not found then raise exception 'lease renewal job missing'; end if;
  if v_job.lease_token is distinct from p_lease_token or v_job.lease_owner<>p_worker_id
     or v_job.lease_expires_at<=clock_timestamp() or p_lease_seconds not between 30 and 300
     or v_job.state not in ('claimed','submitting','submitted','held')
     or v_job.document_version<>p_document_version or v_job.pdf_sha256<>p_pdf_sha256
     or v_job.authorization_receipt_id<>p_authorization_receipt_id then raise exception 'lease renewal invalid'; end if;
  update app_private.document_print_jobs set lease_expires_at=clock_timestamp()+make_interval(secs=>p_lease_seconds),updated_at=clock_timestamp()
    where job_id=p_job_id returning * into v_job; return v_job;
end; $$;

create or replace function app_private.recover_document_print_job_lease(
  p_job_id text,p_worker_id text,p_lease_seconds integer,p_document_version text,
  p_pdf_sha256 text,p_authorization_receipt_id text)
returns app_private.document_print_jobs language plpgsql security definer set search_path=pg_catalog,app_private as $$
declare v_job app_private.document_print_jobs; v_token text:=app_private.pgcrypto_random_hex(24);
begin
  select * into v_job from app_private.document_print_jobs where job_id=p_job_id for update;
  if not found then raise exception 'lease recovery job missing'; end if;
  if v_job.lease_expires_at>clock_timestamp() or p_lease_seconds not between 30 and 300
     or v_job.state not in ('claimed','submitting','submitted','held')
     or v_job.document_version<>p_document_version or v_job.pdf_sha256<>p_pdf_sha256
     or v_job.authorization_receipt_id<>p_authorization_receipt_id then raise exception 'lease recovery invalid'; end if;
  update app_private.document_print_jobs set lease_owner=p_worker_id,lease_token=v_token,
    lease_expires_at=clock_timestamp()+make_interval(secs=>p_lease_seconds),updated_at=clock_timestamp()
    where job_id=p_job_id returning * into v_job;
  insert into app_private.document_print_job_events(job_id,event_type,actor_id,worker_id,attempt_id,cups_job_id,metadata_json)
    values(p_job_id,'lease_recovered','documents-claim-service',p_worker_id,v_job.attempt_id,v_job.cups_job_id,
      jsonb_build_object('provider_id',v_job.provider_id)); return v_job;
end; $$;

create or replace function app_private.claim_document_print_command(
  p_green_id text, p_worker_id text, p_lease_seconds integer default 300)
returns setof app_private.document_print_jobs
language plpgsql security definer set search_path = pg_catalog, app_private as $$
declare v_job_id text; v_token text := app_private.pgcrypto_random_hex(24);
begin
  select job_id into v_job_id from app_private.document_print_jobs
   where green_id=p_green_id and command_kind in ('continue','cancel') and command_receipt_id is not null
     and (command_status in ('accepted','in_progress','completed') or
       (command_status is null and command_authorized_at > clock_timestamp()-interval '5 minutes'
        and authorization_expires_at > clock_timestamp()))
     and (lease_expires_at is null or lease_expires_at<=clock_timestamp() or lease_owner=p_worker_id)
     and ((command_kind='continue' and state in ('held','claimed')) or
          (command_kind='cancel' and state in ('claimed','submitting','submitted','held','ambiguous','cancelled')))
   order by command_authorized_at,job_id for update skip locked limit 1;
  if v_job_id is null then return; end if;
  update app_private.document_print_jobs set lease_owner=p_worker_id,lease_token=v_token,
    lease_expires_at=clock_timestamp()+make_interval(secs=>least(greatest(p_lease_seconds,30),300)),
    updated_at=clock_timestamp() where job_id=v_job_id;
  return query select * from app_private.document_print_jobs where job_id=v_job_id;
end; $$;

revoke all on function app_private.claim_document_print_job(text,text,integer) from public, anon, authenticated;
revoke all on function app_private.transition_document_print_job(text,text,text,text,text,text,uuid,text,text,jsonb) from public, anon, authenticated;
revoke all on function app_private.claim_document_print_command(text,text,integer) from public, anon, authenticated;
revoke all on function app_private.transition_document_print_command(text,text,text,text,text,text,text,text,text,text) from public, anon, authenticated;
revoke all on function app_private.renew_document_print_job_lease(text,text,text,integer,text,text,text) from public, anon, authenticated;
revoke all on function app_private.recover_document_print_job_lease(text,text,integer,text,text,text) from public, anon, authenticated;

create or replace function app_private.reject_document_print_event_mutation()
returns trigger language plpgsql as $$
begin
  raise exception 'document_print_job_events is append-only';
end;
$$;
drop trigger if exists trg_document_print_events_append_only on app_private.document_print_job_events;
create trigger trg_document_print_events_append_only before update or delete
on app_private.document_print_job_events for each row
execute function app_private.reject_document_print_event_mutation();

create or replace function app_private.create_authorized_document_print_job(
  p_job jsonb, p_pdf_bytes bytea, p_authenticated_principal_id text,
  p_requester text, p_request_channel text)
returns app_private.document_print_jobs
language plpgsql security definer set search_path=pg_catalog,app_private as $$
declare v_job app_private.document_print_jobs; v_pdf_digest text;
begin
  if p_job is null or jsonb_typeof(p_job)<>'object' or p_pdf_bytes is null
     or octet_length(p_pdf_bytes) not between 64 and 5242880
     or p_authenticated_principal_id !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'
     or p_requester not in ('oom_sakkie') or p_request_channel not in ('telegram','browser','voice')
     or p_job->>'document_type'<>'farm.weekly_weight_sheet.v1'
     or p_job->>'generator_id'<>'web.print_sheets.v1'
     or p_job->>'retrieval_url' is null
     or p_job->'options' is distinct from '{"media":"A4","copies":1,"color":"monochrome","sides":"one-sided"}'::jsonb
     or p_job->>'authorization_receipt_id' is null
     or (p_job->>'authorization_expires_at')::timestamptz<=clock_timestamp()
     or (p_job->>'retry_deadline')::timestamptz<=clock_timestamp() then
    raise exception 'authorized document job invalid';
  end if;
  execute format('select encode(%I.digest($1,''sha256''),''hex'')',
    (select n.nspname from pg_catalog.pg_extension e join pg_catalog.pg_namespace n
      on n.oid=e.extnamespace where e.extname='pgcrypto')) into v_pdf_digest using p_pdf_bytes;
  if v_pdf_digest is distinct from p_job->>'pdf_sha256' then raise exception 'pdf digest mismatch'; end if;
  insert into app_private.document_print_jobs(
    job_id,document_id,document_version,document_revision,document_type,generator_id,
    pdf_sha256,canonical_input_sha256,pdf_bytes,retrieval_url,options_json,authenticated_principal_id,requester,
    request_channel,green_id,printer_id,cups_queue_id,registry_version,
    authorization_receipt_id,authorization_expires_at,state,retry_deadline)
  values(p_job->>'job_id',p_job->>'document_id',p_job->>'document_version',
    (p_job->>'document_revision')::integer,p_job->>'document_type',p_job->>'generator_id',
    p_job->>'pdf_sha256',p_job->>'canonical_input_sha256',p_pdf_bytes,p_job->>'retrieval_url',
    p_job->'options',
    p_authenticated_principal_id,p_requester,p_request_channel,p_job->>'green_id',
    p_job->>'printer_id',p_job->>'cups_queue_id',p_job->>'registry_version',
    p_job->>'authorization_receipt_id',(p_job->>'authorization_expires_at')::timestamptz,
    'authorized',(p_job->>'retry_deadline')::timestamptz)
  on conflict(job_id) do nothing returning * into v_job;
  if not found then
    select * into v_job from app_private.document_print_jobs where job_id=p_job->>'job_id';
    if v_job.document_id is distinct from p_job->>'document_id'
       or v_job.document_version is distinct from p_job->>'document_version'
       or v_job.document_revision is distinct from (p_job->>'document_revision')::integer
       or v_job.document_type is distinct from p_job->>'document_type'
       or v_job.generator_id is distinct from p_job->>'generator_id'
       or v_job.pdf_sha256 is distinct from p_job->>'pdf_sha256'
       or v_job.canonical_input_sha256 is distinct from p_job->>'canonical_input_sha256'
       or v_job.retrieval_url is distinct from p_job->>'retrieval_url'
       or v_job.options_json is distinct from p_job->'options'
       or v_job.authenticated_principal_id is distinct from p_authenticated_principal_id
       or v_job.requester is distinct from p_requester
       or v_job.request_channel is distinct from p_request_channel
       or v_job.green_id is distinct from p_job->>'green_id'
       or v_job.printer_id is distinct from p_job->>'printer_id'
       or v_job.cups_queue_id is distinct from p_job->>'cups_queue_id'
       or v_job.registry_version is distinct from p_job->>'registry_version'
       or v_job.authorization_receipt_id is distinct from p_job->>'authorization_receipt_id'
       or v_job.authorization_expires_at is distinct from (p_job->>'authorization_expires_at')::timestamptz
       or v_job.retry_deadline is distinct from (p_job->>'retry_deadline')::timestamptz then
      raise exception 'document job replay binding conflict';
    end if;
  else
    insert into app_private.document_print_job_events(job_id,event_type,actor_id,metadata_json)
      values(v_job.job_id,'job_authorized',p_authenticated_principal_id,
        jsonb_build_object('document_version',v_job.document_version,'pdf_sha256',v_job.pdf_sha256,
          'authorization_receipt_id',v_job.authorization_receipt_id,'requester',v_job.requester));
  end if;
  return v_job;
end; $$;

create or replace function app_private.read_document_print_job(
  p_job_id text,p_lease_token text,p_green_id text,p_worker_id text)
returns app_private.document_print_jobs language plpgsql security definer
set search_path=pg_catalog,app_private as $$
declare v_job app_private.document_print_jobs;
begin
  select * into v_job from app_private.document_print_jobs where job_id=p_job_id;
  if not found or v_job.lease_token is distinct from p_lease_token
     or v_job.green_id is distinct from p_green_id
     or v_job.lease_owner is distinct from p_worker_id
     or v_job.lease_expires_at<=clock_timestamp() then raise exception 'job read fence invalid'; end if;
  v_job.pdf_bytes:=null; return v_job;
end; $$;

create or replace function app_private.read_document_print_pdf(
  p_document_id text,p_document_version text,p_green_id text,p_worker_id text)
returns bytea language plpgsql security definer set search_path=pg_catalog,app_private as $$
declare v_pdf bytea;
begin
  select pdf_bytes into v_pdf from app_private.document_print_jobs
   where document_id=p_document_id and document_version=p_document_version
     and green_id=p_green_id and lease_owner=p_worker_id and lease_expires_at>clock_timestamp()
     and state in ('claimed','submitting','submitted');
  return v_pdf;
end; $$;

do $$ begin
  if not exists(select 1 from pg_roles where rolname='documents_green_worker_executor') then
    create role documents_green_worker_executor nologin noinherit;
  end if;
  if not exists(select 1 from pg_roles where rolname='documents_api_executor') then
    create role documents_api_executor nologin noinherit;
  end if;
end $$;
revoke all on schema app_private from public,anon,authenticated;
revoke all on function app_private.pgcrypto_random_hex(integer) from public,anon,authenticated;
grant usage on schema app_private to documents_green_worker_executor,documents_api_executor;
grant execute on function app_private.claim_document_print_job(text,text,integer),
  app_private.claim_document_print_command(text,text,integer),
  app_private.transition_document_print_job(text,text,text,text,text,text,uuid,text,text,jsonb),
  app_private.transition_document_print_command(text,text,text,text,text,text,text,text,text,text),
  app_private.renew_document_print_job_lease(text,text,text,integer,text,text,text),
  app_private.recover_document_print_job_lease(text,text,integer,text,text,text),
  app_private.read_document_print_job(text,text,text,text),
  app_private.read_document_print_pdf(text,text,text,text)
  to documents_green_worker_executor;
grant execute on function app_private.create_authorized_document_print_job(jsonb,bytea,text,text,text)
  to documents_api_executor;
revoke all on function app_private.create_authorized_document_print_job(jsonb,bytea,text,text,text),
  app_private.read_document_print_job(text,text,text,text),app_private.read_document_print_pdf(text,text,text,text)
  from public,anon,authenticated;
