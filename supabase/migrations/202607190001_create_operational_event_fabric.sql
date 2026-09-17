create table if not exists public.operational_events (
    event_id text primary key,
    idempotency_key text not null unique,
    schema_version text not null default '1',
    event_type text not null,
    domain text not null check (domain in ('leads','conversations','orders','payments','animals','campaigns','missions','incidents','approvals','outcomes')),
    aggregate_type text not null,
    aggregate_id text not null,
    source_system text not null,
    source_record_id text not null default '',
    authority_tier text not null check (authority_tier in ('read','observe','draft','owner_approved','bounded_auto','red_zone')),
    privacy_class text not null check (privacy_class in ('internal','owner_private','customer_personal','sensitive_business')),
    actor_type text not null default 'system',
    actor_id text not null default '',
    correlation_id text not null default '',
    causation_id text not null default '',
    occurred_at timestamptz not null,
    recorded_at timestamptz not null default now(),
    freshness_at timestamptz not null,
    payload_json jsonb not null,
    provenance_json jsonb not null check (provenance_json ? 'source_ref'),
    created_at timestamptz not null default now()
);

create table if not exists public.operational_projection_checkpoints (
    projection_name text primary key,
    projection_version text not null,
    last_event_id text references public.operational_events(event_id) on delete restrict,
    last_occurred_at timestamptz,
    state_hash text not null default '',
    replayed_event_count bigint not null default 0,
    updated_at timestamptz not null default now()
);

create index if not exists idx_operational_events_aggregate_time
    on public.operational_events(domain, aggregate_type, aggregate_id, occurred_at, event_id);
create index if not exists idx_operational_events_correlation
    on public.operational_events(correlation_id) where correlation_id <> '';
create index if not exists idx_operational_events_recorded
    on public.operational_events(recorded_at, event_id);

alter table public.operational_events enable row level security;
alter table public.operational_projection_checkpoints enable row level security;

insert into app_private.migration_log (migration_id, description)
values ('202607190001_create_operational_event_fabric', 'Create additive typed operational events and deterministic projection checkpoints for Agentic Business OS Phase 3.')
on conflict (migration_id) do nothing;
