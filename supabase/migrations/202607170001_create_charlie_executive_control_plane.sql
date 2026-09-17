create table if not exists public.charlie_executive_goals (
    goal_id text primary key,
    title text not null,
    objective text not null default '',
    business_area text not null default 'system',
    priority integer not null default 50 check (priority between 0 and 100),
    status text not null default 'active' check (status in ('draft','active','paused','achieved','cancelled')),
    success_metrics_json jsonb not null default '[]'::jsonb,
    constraints_json jsonb not null default '[]'::jsonb,
    created_by text not null default 'charl',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.charlie_delegation_policies (
    policy_id text primary key,
    capability text not null,
    scope_json jsonb not null default '{}'::jsonb,
    authority_tier text not null check (authority_tier in ('auto','charlie_delegated','charl_human')),
    enabled boolean not null default false,
    expires_at timestamptz,
    max_actions integer not null default 0,
    max_cost numeric not null default 0,
    rollback_required boolean not null default true,
    deterministic_gate_required boolean not null default true,
    granted_by text not null default 'charl',
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (capability, authority_tier)
);

create table if not exists public.charlie_control_commands (
    command_id text primary key,
    idempotency_key text not null unique,
    mission_id text references public.charlie_missions(mission_id) on delete set null,
    goal_id text references public.charlie_executive_goals(goal_id) on delete set null,
    command_type text not null,
    authority_tier text not null,
    policy_id text references public.charlie_delegation_policies(policy_id) on delete set null,
    status text not null default 'planned' check (status in ('planned','authorized','running','succeeded','failed','blocked','cancelled')),
    payload_json jsonb not null default '{}'::jsonb,
    result_json jsonb not null default '{}'::jsonb,
    error_text text not null default '',
    attempt_count integer not null default 1,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz
);

create table if not exists public.charlie_recovery_cases (
    recovery_id text primary key,
    mission_id text not null references public.charlie_missions(mission_id) on delete cascade,
    fingerprint text not null,
    block_class text not null,
    responsible_stage text not null,
    status text not null default 'scheduled' check (status in ('scheduled','running','resolved','exhausted','owner_required','cancelled')),
    attempt_count integer not null default 0,
    attempt_limit integer not null default 3,
    next_attempt_at timestamptz,
    deadline_at timestamptz,
    evidence_json jsonb not null default '{}'::jsonb,
    resolution_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (mission_id, fingerprint)
);

create table if not exists public.charlie_capability_trust (
    capability_key text primary key,
    scope_json jsonb not null default '{}'::jsonb,
    runs integer not null default 0,
    clean_passes integer not null default 0,
    recoveries integer not null default 0,
    escaped_defects integer not null default 0,
    human_edits integer not null default 0,
    rollbacks integer not null default 0,
    tier text not null default 'watch' check (tier in ('watch','queue','delegated','auto')),
    evidence_version text not null default '',
    last_result text not null default '',
    last_evaluated_at timestamptz,
    updated_at timestamptz not null default now()
);

create table if not exists public.charlie_eval_registry (
    eval_id text primary key,
    mission_class text not null,
    version text not null,
    status text not null default 'active' check (status in ('draft','active','retired')),
    scenarios_json jsonb not null default '[]'::jsonb,
    required_gates_json jsonb not null default '[]'::jsonb,
    minimum_pass_rate numeric not null default 1,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (mission_class, version)
);

create table if not exists public.charlie_research_radar (
    research_id text primary key,
    business_area text not null,
    topic text not null,
    source_url text not null,
    source_kind text not null default 'primary',
    observed_at timestamptz not null,
    summary text not null default '',
    applicability text not null default 'unreviewed',
    proposal_mission_id text references public.charlie_missions(mission_id) on delete set null,
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (business_area, topic, source_url)
);

create table if not exists public.charlie_notification_outbox (
    outbox_id text primary key,
    idempotency_key text not null unique,
    channel text not null,
    recipient_key text not null default 'owner',
    event_type text not null,
    payload_json jsonb not null default '{}'::jsonb,
    status text not null default 'pending' check (status in ('pending','sending','sent','failed','dead_letter')),
    attempt_count integer not null default 0,
    next_attempt_at timestamptz,
    last_error text not null default '',
    created_at timestamptz not null default now(),
    sent_at timestamptz
);

create index if not exists idx_charlie_control_commands_status_created on public.charlie_control_commands(status, created_at);
create index if not exists idx_charlie_recovery_cases_status_next on public.charlie_recovery_cases(status, next_attempt_at);
create index if not exists idx_charlie_outbox_status_next on public.charlie_notification_outbox(status, next_attempt_at);
create index if not exists idx_charlie_goals_status_priority on public.charlie_executive_goals(status, priority desc);

insert into public.charlie_delegation_policies (
    policy_id, capability, authority_tier, enabled, max_actions, max_cost,
    rollback_required, deterministic_gate_required, granted_by, metadata_json
) values
    ('POLICY-CORE-INTERNAL-RECOVERY', 'core.internal_recovery', 'auto', true, 1000, 0, true, true, 'charl', '{"scope":"recoverable_non_red_core_blocks","approved_program":"charlie_executive_control_plane"}'::jsonb),
    ('POLICY-CORE-QUEUE-CONTINUE', 'core.queue_continue', 'auto', true, 1000, 0, true, true, 'charl', '{"scope":"continue_unrelated_approved_work","approved_program":"charlie_executive_control_plane"}'::jsonb),
    ('POLICY-CORE-OWNER-NOTIFY', 'core.owner_notify', 'auto', true, 1000, 0, true, true, 'charl', '{"scope":"mission_and_incident_notifications","approved_program":"charlie_executive_control_plane"}'::jsonb)
on conflict (capability, authority_tier) do update set
    metadata_json = excluded.metadata_json,
    updated_at = now();

insert into app_private.migration_log (migration_id, description)
values ('202607170001_create_charlie_executive_control_plane', 'Create CHARLIE executive goals, delegation, durable commands, recovery, trust, eval, research, and notification outbox rails.')
on conflict (migration_id) do nothing;
