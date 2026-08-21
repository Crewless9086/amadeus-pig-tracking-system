-- Canonical Documents ownership for the bounded weekly-sheet Green pilot.
-- This migration is source-only until separately approved and applied.
create schema if not exists app_private;

create table if not exists app_private.document_print_jobs (
    job_id text primary key,
    document_id text not null,
    document_version text not null,
    document_revision integer not null check (document_revision > 0),
    document_type text not null check (document_type = 'farm.weekly_weight_sheet.v1'),
    generator_id text not null check (generator_id = 'web.print_sheets.v1'),
    pdf_sha256 text not null check (pdf_sha256 ~ '^[0-9a-f]{64}$'),
    canonical_input_sha256 text not null check (canonical_input_sha256 ~ '^[0-9a-f]{64}$'),
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
    command_kind text check (command_kind in ('continue','cancel')),
    command_receipt_id text unique,
    command_authorized_at timestamptz,
    state text not null default 'prepared' check (state in
      ('prepared','authorized','claimed','submitting','submitted','provider_completed','held','ambiguous','cancelled','physically_confirmed')),
    retry_deadline timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (document_id, document_version),
    unique (authorization_receipt_id)
);

create table if not exists app_private.document_print_job_events (
    event_id uuid primary key default gen_random_uuid(),
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
  p_worker_id text, p_lease_seconds integer default 300)
returns setof app_private.document_print_jobs
language plpgsql security definer set search_path = pg_catalog, app_private as $$
declare v_job_id text; v_token text := encode(gen_random_bytes(24), 'hex');
begin
  if p_worker_id is null or p_lease_seconds not between 30 and 300 then
    raise exception 'invalid claim';
  end if;
  select job_id into v_job_id from app_private.document_print_jobs
   where state = 'authorized' and retry_deadline > clock_timestamp()
     and authorization_expires_at > clock_timestamp()
   order by created_at, job_id for update skip locked limit 1;
  if v_job_id is null then return; end if;
  update app_private.document_print_jobs set state='claimed', lease_owner=p_worker_id,
    lease_token=v_token, lease_expires_at=clock_timestamp()+make_interval(secs=>p_lease_seconds),
    updated_at=clock_timestamp() where job_id=v_job_id;
  insert into app_private.document_print_job_events(job_id,event_type,actor_id,worker_id,metadata_json)
    values(v_job_id,'lease_claimed','documents-claim-service',p_worker_id,jsonb_build_object('lease_token_sha256',encode(digest(v_token,'sha256'),'hex')));
  return query select * from app_private.document_print_jobs where job_id=v_job_id;
end; $$;

create or replace function app_private.transition_document_print_job(
  p_job_id text, p_lease_token text, p_document_version text, p_pdf_sha256 text,
  p_authorization_receipt_id text, p_target_state text, p_event_id uuid, p_metadata jsonb default '{}'::jsonb)
returns app_private.document_print_jobs
language plpgsql security definer set search_path = pg_catalog, app_private as $$
declare v_job app_private.document_print_jobs;
begin
  select * into v_job from app_private.document_print_jobs where job_id=p_job_id for update;
  if not found or v_job.lease_token is distinct from p_lease_token or
     v_job.lease_expires_at <= clock_timestamp() or v_job.document_version<>p_document_version or
     v_job.pdf_sha256<>p_pdf_sha256 or v_job.authorization_receipt_id<>p_authorization_receipt_id then
    raise exception 'lease fence or binding invalid';
  end if;
  if p_target_state not in ('claimed','submitting','submitted','provider_completed','held','ambiguous','cancelled','physically_confirmed') then
    raise exception 'transition invalid';
  end if;
  insert into app_private.document_print_job_events(event_id,job_id,event_type,actor_id,worker_id,metadata_json)
    values(p_event_id,p_job_id,'state_'||p_target_state,'documents-worker',v_job.lease_owner,p_metadata)
    on conflict(event_id) do nothing;
  if not found then return v_job; end if;
  update app_private.document_print_jobs set state=p_target_state,updated_at=clock_timestamp()
    where job_id=p_job_id returning * into v_job;
  return v_job;
end; $$;

create or replace function app_private.claim_document_print_command(
  p_worker_id text, p_lease_seconds integer default 300)
returns setof app_private.document_print_jobs
language plpgsql security definer set search_path = pg_catalog, app_private as $$
declare v_job_id text; v_token text := encode(gen_random_bytes(24), 'hex');
begin
  select job_id into v_job_id from app_private.document_print_jobs
   where command_kind in ('continue','cancel') and command_receipt_id is not null
     and command_authorized_at > clock_timestamp()-interval '5 minutes'
     and authorization_expires_at > clock_timestamp()
     and ((command_kind='continue' and state='held') or
          (command_kind='cancel' and state in ('claimed','submitting','submitted','held','ambiguous')))
   order by command_authorized_at,job_id for update skip locked limit 1;
  if v_job_id is null then return; end if;
  update app_private.document_print_jobs set lease_owner=p_worker_id,lease_token=v_token,
    lease_expires_at=clock_timestamp()+make_interval(secs=>least(greatest(p_lease_seconds,30),300)),
    updated_at=clock_timestamp() where job_id=v_job_id;
  return query select * from app_private.document_print_jobs where job_id=v_job_id;
end; $$;

revoke all on function app_private.claim_document_print_job(text,integer) from public, anon, authenticated;
revoke all on function app_private.transition_document_print_job(text,text,text,text,text,text,uuid,jsonb) from public, anon, authenticated;
revoke all on function app_private.claim_document_print_command(text,integer) from public, anon, authenticated;

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
