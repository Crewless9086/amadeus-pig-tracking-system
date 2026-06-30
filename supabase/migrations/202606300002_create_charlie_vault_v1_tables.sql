create table if not exists public.charlie_vault_projects (
    project_id text primary key,
    project_key text not null unique,
    name text not null,
    domain text not null default 'software',
    status text not null default 'active',
    owner_notes text,
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.charlie_vault_artifacts (
    artifact_id text primary key,
    mission_id text not null references public.charlie_missions(mission_id) on delete cascade,
    project_id text references public.charlie_vault_projects(project_id) on delete set null,
    agent_name text not null,
    artifact_type text not null,
    title text not null,
    summary text,
    artifact_path text,
    content_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_agent_runs (
    run_id text primary key,
    mission_id text not null references public.charlie_missions(mission_id) on delete cascade,
    execution_id text not null,
    agent_name text not null,
    status text not null,
    attempt integer not null default 1,
    current_action text,
    files_inspected jsonb not null default '[]'::jsonb,
    commands_run jsonb not null default '[]'::jsonb,
    stdout_tail text,
    stderr_tail text,
    changed_files jsonb not null default '[]'::jsonb,
    artifact_id text references public.charlie_vault_artifacts(artifact_id) on delete set null,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_handoff_reports (
    handoff_id text primary key,
    mission_id text not null references public.charlie_missions(mission_id) on delete cascade,
    from_agent text not null,
    to_agent text,
    status text not null,
    summary text,
    risks jsonb not null default '[]'::jsonb,
    tests jsonb not null default '[]'::jsonb,
    changed_files jsonb not null default '[]'::jsonb,
    quality_gate_json jsonb not null default '{}'::jsonb,
    report_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_quality_gates (
    gate_id text primary key,
    mission_id text not null references public.charlie_missions(mission_id) on delete cascade,
    agent_name text not null,
    gate_name text not null,
    status text not null,
    reason text,
    evidence_json jsonb not null default '{}'::jsonb,
    checked_at timestamptz not null default now()
);

create table if not exists public.charlie_owner_decisions (
    decision_id text primary key,
    mission_id text not null references public.charlie_missions(mission_id) on delete cascade,
    decision text not null,
    target_stage text,
    comments text,
    approval_level text,
    recorded_by text not null default 'owner',
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_deployments (
    deployment_id text primary key,
    mission_id text not null references public.charlie_missions(mission_id) on delete cascade,
    release_status text not null,
    pr_reference text,
    merge_result_json jsonb not null default '{}'::jsonb,
    verify_url text,
    verify_status text,
    verify_result_json jsonb not null default '{}'::jsonb,
    deployed_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_audit_log (
    audit_id text primary key,
    mission_id text references public.charlie_missions(mission_id) on delete set null,
    actor text not null,
    action text not null,
    tool_name text,
    permission_level text,
    risk_level text not null default 'normal',
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_charlie_vault_artifacts_mission_created
    on public.charlie_vault_artifacts(mission_id, created_at desc);

create index if not exists idx_charlie_agent_runs_mission_agent_created
    on public.charlie_agent_runs(mission_id, agent_name, created_at desc);

create index if not exists idx_charlie_handoff_reports_mission_created
    on public.charlie_handoff_reports(mission_id, created_at desc);

create index if not exists idx_charlie_quality_gates_mission_agent
    on public.charlie_quality_gates(mission_id, agent_name, checked_at desc);

create index if not exists idx_charlie_owner_decisions_mission_created
    on public.charlie_owner_decisions(mission_id, created_at desc);

create index if not exists idx_charlie_deployments_mission_created
    on public.charlie_deployments(mission_id, created_at desc);

create index if not exists idx_charlie_audit_log_mission_created
    on public.charlie_audit_log(mission_id, created_at desc);

insert into app_private.migration_log (migration_id, description)
values (
    '202606300002_create_charlie_vault_v1_tables',
    'Create CHARLIE Vault v1 structured tables for projects, artifacts, agent runs, handoffs, gates, owner decisions, deployments, and audit log.'
)
on conflict (migration_id) do nothing;
