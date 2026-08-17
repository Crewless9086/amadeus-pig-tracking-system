create table if not exists app_private.oom_manager_cases (
  case_id text primary key,
  dedupe_key text not null unique,
  specialist text not null check (specialist in ('ROOTLINE','HERDMASTER','SAM','BEACON','RUNTIME')),
  urgency text not null check (urgency in ('critical','urgent','due','planned','watch')),
  status text not null check (status in ('open','delegated','waiting_reassessment','exception','completed','contained')),
  evidence_digest text not null check (length(evidence_digest)=64),
  evidence_refs jsonb not null,
  unknowns jsonb not null default '[]'::jsonb,
  summary text not null,
  next_action text not null,
  next_reassessment_at timestamptz not null,
  generation bigint not null check (generation > 0),
  assigned_worker_id text,
  lease_until timestamptz,
  last_heartbeat_at timestamptz,
  last_delivery_digest text,
  last_delivery_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (jsonb_typeof(evidence_refs)='array' and jsonb_array_length(evidence_refs)>0),
  check (jsonb_typeof(unknowns)='array')
);

create index if not exists oom_manager_cases_due_idx
  on app_private.oom_manager_cases(status,next_reassessment_at)
  where status in ('open','delegated','waiting_reassessment','exception');

create table if not exists app_private.oom_manager_case_events (
  event_id text primary key,
  case_id text not null references app_private.oom_manager_cases(case_id),
  generation bigint not null check (generation > 0),
  event_type text not null check (event_type in (
    'created','evidence_changed','claimed','heartbeat','delegated','reassessment_scheduled',
    'delivery_confirmed','delivery_suppressed','completed','contained','exception')),
  event_payload jsonb not null,
  occurred_at timestamptz not null default now()
);

create index if not exists oom_manager_case_events_case_idx
  on app_private.oom_manager_case_events(case_id,occurred_at,event_id);

create table if not exists app_private.oom_manager_worker_cycles (
  cycle_id text primary key,
  worker_id text not null,
  trigger_identity text not null,
  source_revision text not null,
  started_at timestamptz not null,
  heartbeat_at timestamptz not null,
  next_cycle_at timestamptz not null,
  status text not null check (status in ('started','completed','contained','failed')),
  case_counts jsonb not null default '{}'::jsonb,
  completed_at timestamptz
);

create or replace function app_private.reject_oom_manager_case_event_mutation()
returns trigger language plpgsql as $$
begin
  raise exception 'oom_manager_case_events_append_only';
end;
$$;
drop trigger if exists oom_manager_case_events_append_only on app_private.oom_manager_case_events;
create trigger oom_manager_case_events_append_only before update or delete
on app_private.oom_manager_case_events for each row
execute function app_private.reject_oom_manager_case_event_mutation();

revoke all on app_private.oom_manager_cases from public, anon, authenticated;
revoke all on app_private.oom_manager_case_events from public, anon, authenticated;
revoke all on app_private.oom_manager_worker_cycles from public, anon, authenticated;

insert into app_private.migration_log(migration_id,description)
values('202608170002_create_oom_manager_case_runtime',
 'Canonical Oom Sakkie manager cases, append-only lifecycle events and supervised worker cycles')
on conflict(migration_id) do nothing;
