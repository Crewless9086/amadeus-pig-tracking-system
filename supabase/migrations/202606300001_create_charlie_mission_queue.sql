create table if not exists public.charlie_missions (
    mission_id text primary key,
    status text not null default 'new',
    source text not null default 'telegram',
    source_message_id text,
    telegram_user_id text,
    telegram_chat_id text,
    raw_text text not null,
    title text not null,
    urgency text not null,
    mission_type text not null,
    approval_level text not null,
    selected_next_step text,
    owner_decision text,
    codex_chat_write_status text,
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.charlie_mission_events (
    event_id text primary key,
    mission_id text not null references public.charlie_missions(mission_id) on delete cascade,
    event_type text not null,
    notes text,
    recorded_by text not null default 'charlie_relay',
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_charlie_missions_status_created
    on public.charlie_missions(status, created_at desc);

create index if not exists idx_charlie_missions_source_created
    on public.charlie_missions(source, created_at desc);

create index if not exists idx_charlie_mission_events_mission_created
    on public.charlie_mission_events(mission_id, created_at desc);

insert into app_private.migration_log (migration_id, description)
values (
    '202606300001_create_charlie_mission_queue',
    'Create CHARLIE Build Relay durable mission queue tables.'
)
on conflict (migration_id) do nothing;
