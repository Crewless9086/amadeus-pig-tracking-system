create table if not exists public.charlie_owner_bindings (
    binding_id text primary key,
    telegram_user_id text not null unique,
    telegram_chat_id text not null unique,
    channel text not null default 'telegram',
    status text not null default 'active' check (status in ('active','revoked')),
    verified_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    metadata_json jsonb not null default '{}'::jsonb
);

create table if not exists public.charlie_conversation_threads (
    thread_id text primary key,
    binding_id text not null references public.charlie_owner_bindings(binding_id) on delete cascade,
    status text not null default 'active' check (status in ('active','closed')),
    title text not null default 'Private CHARLIE conversation',
    summary text not null default '',
    open_context_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(binding_id, status)
);

create table if not exists public.charlie_conversation_messages (
    message_id text primary key,
    thread_id text not null references public.charlie_conversation_threads(thread_id) on delete cascade,
    telegram_update_id text,
    telegram_message_id text,
    role text not null check (role in ('owner','charlie','system','tool')),
    content text not null default '',
    media_json jsonb not null default '[]'::jsonb,
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique(telegram_update_id, role)
);

create table if not exists public.charlie_owner_intents (
    intent_id text primary key,
    thread_id text not null references public.charlie_conversation_threads(thread_id) on delete cascade,
    owner_message_id text references public.charlie_conversation_messages(message_id) on delete set null,
    intent_type text not null,
    confidence numeric not null default 0,
    args_json jsonb not null default '{}'::jsonb,
    risk_flags_json jsonb not null default '[]'::jsonb,
    status text not null default 'planned' check (status in ('planned','executed','clarification','blocked','failed')),
    created_at timestamptz not null default now(),
    completed_at timestamptz
);

create table if not exists public.charlie_tool_executions (
    execution_id text primary key,
    intent_id text not null references public.charlie_owner_intents(intent_id) on delete cascade,
    idempotency_key text not null unique,
    tool_name text not null,
    authority_tier text not null,
    status text not null check (status in ('authorized','succeeded','failed','blocked')),
    args_json jsonb not null default '{}'::jsonb,
    result_json jsonb not null default '{}'::jsonb,
    error_text text not null default '',
    created_at timestamptz not null default now(),
    completed_at timestamptz
);

create table if not exists public.charlie_approval_bundles (
    bundle_id text primary key,
    thread_id text references public.charlie_conversation_threads(thread_id) on delete set null,
    status text not null default 'pending' check (status in ('pending','approved','rejected','deferred','expired','executed')),
    title text not null,
    summary text not null default '',
    decisions_json jsonb not null default '[]'::jsonb,
    recommendation_json jsonb not null default '{}'::jsonb,
    state_hash text not null,
    expires_at timestamptz not null,
    decided_at timestamptz,
    executed_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists public.charlie_owner_preferences (
    preference_id text primary key,
    preference_key text not null unique,
    preference_value_json jsonb not null,
    status text not null default 'proposed' check (status in ('proposed','approved','rejected','retired')),
    source_message_id text references public.charlie_conversation_messages(message_id) on delete set null,
    approved_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.charlie_brief_subscriptions (
    subscription_id text primary key,
    binding_id text not null references public.charlie_owner_bindings(binding_id) on delete cascade,
    brief_type text not null,
    local_time time not null,
    timezone text not null default 'Africa/Johannesburg',
    enabled boolean not null default true,
    last_delivery_date date,
    created_at timestamptz not null default now(),
    unique(binding_id, brief_type)
);

create table if not exists public.charlie_inbound_updates (
    update_key text primary key,
    telegram_update_id text not null unique,
    callback_query_id text,
    binding_id text references public.charlie_owner_bindings(binding_id) on delete set null,
    status text not null default 'processing' check (status in ('processing','processed','failed','ignored')),
    result_json jsonb not null default '{}'::jsonb,
    received_at timestamptz not null default now(),
    completed_at timestamptz
);

create index if not exists idx_charlie_messages_thread_created on public.charlie_conversation_messages(thread_id, created_at desc);
create index if not exists idx_charlie_intents_thread_created on public.charlie_owner_intents(thread_id, created_at desc);
create index if not exists idx_charlie_bundles_status_expiry on public.charlie_approval_bundles(status, expires_at);

insert into public.charlie_delegation_policies (
    policy_id, capability, authority_tier, enabled, max_actions, max_cost,
    rollback_required, deterministic_gate_required, granted_by, metadata_json
) values
    ('POLICY-CHARLIE-MISSION-CREATE', 'charlie.mission.create', 'charlie_delegated', true, 0, 0, true, true, 'charl', '{"scope":"create_new_owner_work_missions_only"}'::jsonb),
    ('POLICY-CHARLIE-MISSION-DECIDE', 'charlie.mission.internal_decision', 'charlie_delegated', true, 0, 0, true, true, 'charl', '{"scope":"explicit_owner_instruction_or_fresh_approval_bundle_only"}'::jsonb),
    ('POLICY-CHARLIE-BRIEF', 'charlie.owner_brief', 'auto', true, 0, 0, false, true, 'charl', '{"scope":"private_owner_summaries_only"}'::jsonb)
on conflict (capability, authority_tier) do update set enabled = excluded.enabled, metadata_json = excluded.metadata_json, updated_at = now();

insert into app_private.migration_log (migration_id, description)
values ('202607170002_create_charlie_private_executive_interface', 'Create private CHARLIE owner identity, conversation, intent, tool, approval, preference, briefing, and inbound dedupe rails.')
on conflict (migration_id) do nothing;
