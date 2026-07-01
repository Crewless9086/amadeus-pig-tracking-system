create table if not exists public.charlie_vault_projects (
    project_id text primary key,
    project_key text not null,
    name text not null,
    purpose text not null default '',
    owner_label text not null default 'CHARL',
    workflow_template text not null default 'software_build',
    status text not null default 'active',
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.charlie_vault_artifacts (
    artifact_id text primary key,
    mission_id text not null,
    project_id text,
    artifact_type text not null,
    title text not null default '',
    summary text not null default '',
    content_json jsonb not null default '{}'::jsonb,
    source_refs jsonb not null default '[]'::jsonb,
    confidence text not null default '',
    created_by_agent text not null default '',
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_agent_runs (
    run_id text primary key,
    mission_id text not null,
    agent text not null,
    stage text not null default '',
    status text not null default 'pending',
    model_provider text not null default '',
    model_name text not null default '',
    started_at timestamptz,
    completed_at timestamptz,
    cost_estimate numeric,
    token_usage_json jsonb not null default '{}'::jsonb,
    tool_calls_json jsonb not null default '[]'::jsonb,
    metadata_json jsonb not null default '{}'::jsonb
);

create table if not exists public.charlie_handoff_reports (
    handoff_id text primary key,
    mission_id text not null,
    agent text not null,
    stage text not null,
    status text not null default '',
    report_json jsonb not null,
    validation_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_quality_gates (
    gate_id text primary key,
    mission_id text not null,
    gate_name text not null,
    stage text not null default '',
    status text not null,
    reason text not null default '',
    evidence_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_owner_decisions (
    decision_id text primary key,
    mission_id text not null,
    decision text not null,
    approval_level text not null default '',
    comments text not null default '',
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_deployments (
    deployment_id text primary key,
    mission_id text not null,
    commit_sha text not null default '',
    pr_url text not null default '',
    verify_url text not null default '',
    status text not null default 'pending',
    verified_at timestamptz,
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_audit_log (
    audit_id text primary key,
    mission_id text,
    actor text not null default 'charlie_core',
    action text not null,
    target text not null default '',
    risk_level text not null default '',
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_lessons (
    lesson_id text primary key,
    mission_id text,
    source_stage text not null default '',
    failure text not null default '',
    improvement text not null default '',
    target text not null default 'prompt_or_test_or_workflow_update',
    status text not null default 'queued',
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_income_stream_reviews (
    review_id text primary key,
    mission_id text not null,
    business_model_json jsonb not null default '{}'::jsonb,
    risk_register_json jsonb not null default '[]'::jsonb,
    readiness_json jsonb not null default '{}'::jsonb,
    owner_gate_status text not null default 'pending',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_charlie_vault_artifacts_mission on public.charlie_vault_artifacts (mission_id);
create index if not exists idx_charlie_agent_runs_mission on public.charlie_agent_runs (mission_id);
create index if not exists idx_charlie_handoff_reports_mission on public.charlie_handoff_reports (mission_id);
create index if not exists idx_charlie_quality_gates_mission on public.charlie_quality_gates (mission_id);
create index if not exists idx_charlie_owner_decisions_mission on public.charlie_owner_decisions (mission_id);
create index if not exists idx_charlie_deployments_mission on public.charlie_deployments (mission_id);
create index if not exists idx_charlie_lessons_mission on public.charlie_lessons (mission_id);
create index if not exists idx_charlie_income_stream_reviews_mission on public.charlie_income_stream_reviews (mission_id);
