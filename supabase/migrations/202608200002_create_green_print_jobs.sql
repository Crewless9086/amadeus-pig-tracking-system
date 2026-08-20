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
    state text not null default 'prepared' check (state in
      ('prepared','authorized','claimed','submitted','provider_completed','held','ambiguous','cancelled','physically_confirmed')),
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
