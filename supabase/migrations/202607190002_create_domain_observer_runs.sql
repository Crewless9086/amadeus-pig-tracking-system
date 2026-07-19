create table if not exists public.domain_observer_runs (
    run_id text primary key,
    observer_key text not null,
    domain text not null,
    trigger_type text not null check (trigger_type in ('schedule','event','manual')),
    status text not null check (status in ('observed','evidence_incomplete','failed')),
    authority_tier text not null default 'observe' check (authority_tier = 'observe'),
    source_refs_json jsonb not null default '[]'::jsonb,
    freshness text not null default 'unknown',
    facts_json jsonb not null default '[]'::jsonb,
    gaps_json jsonb not null default '[]'::jsonb,
    recommendations_json jsonb not null default '[]'::jsonb,
    writes_authorized boolean not null default false check (writes_authorized = false),
    sends_authorized boolean not null default false check (sends_authorized = false),
    ran_at timestamptz not null,
    created_at timestamptz not null default now()
);

create table if not exists public.domain_observer_feedback (
    feedback_id text primary key,
    run_id text not null references public.domain_observer_runs(run_id) on delete cascade,
    recommendation_id text not null,
    useful boolean not null,
    owner_note text not null default '',
    recorded_by text not null default 'charl',
    created_at timestamptz not null default now(),
    unique (recommendation_id, recorded_by)
);

create index if not exists idx_domain_observer_runs_key_time on public.domain_observer_runs(observer_key, ran_at desc);
alter table public.domain_observer_runs enable row level security;
alter table public.domain_observer_feedback enable row level security;

insert into app_private.migration_log (migration_id, description)
values ('202607190002_create_domain_observer_runs', 'Create proposal-only observer telemetry and false-positive feedback for Agentic Business OS Phase 4.')
on conflict (migration_id) do nothing;
