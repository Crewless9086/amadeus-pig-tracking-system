-- Phase 10.3R irrigation telemetry/control-readiness schema.
-- Purpose: create empty irrigation data tables before dashboards, adaptive planning, fertilizer logic, tank sensors, or hardware control.
-- This migration imports no data, changes no n8n workflows, and creates no command/control endpoint.

insert into public.telemetry_sources (
    source_id,
    source_type,
    provider,
    display_name,
    external_ref,
    timezone,
    stale_after_minutes,
    metadata
)
values (
    'irrigation-controller-main',
    'irrigation',
    'n8n_sheet_bridge',
    'Amadeus Irrigation Controller',
    null,
    'Africa/Johannesburg',
    60,
    '{"phase":"10.3R","purpose":"irrigation data foundation; read-only first"}'::jsonb
)
on conflict (source_id) do update set
    source_type = excluded.source_type,
    provider = excluded.provider,
    display_name = excluded.display_name,
    external_ref = excluded.external_ref,
    timezone = excluded.timezone,
    stale_after_minutes = excluded.stale_after_minutes,
    metadata = public.telemetry_sources.metadata || excluded.metadata,
    updated_at = now();

create table if not exists public.irrigation_zones (
    zone_id text primary key,
    source_id text references public.telemetry_sources(source_id) on delete set null,
    zone_name text not null,
    zone_type text not null default 'watering' check (
        zone_type in ('watering', 'drip', 'sprinkler', 'support', 'unknown')
    ),
    crop_context text,
    location_notes text,
    summer_minutes numeric(8, 2) check (summer_minutes is null or summer_minutes >= 0),
    winter_minutes numeric(8, 2) check (winter_minutes is null or winter_minutes >= 0),
    priority integer,
    active boolean not null default true,
    metadata jsonb not null default '{}'::jsonb,
    source_sheet_row integer,
    import_batch_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.irrigation_daily_plans (
    daily_plan_id text primary key,
    plan_date date not null,
    source_id text references public.telemetry_sources(source_id) on delete set null,
    plan_status text not null default 'Draft' check (
        plan_status in ('Draft', 'Planned', 'Running', 'Completed', 'Paused', 'Cancelled', 'Superseded')
    ),
    plan_source text not null default 'Unknown' check (
        plan_source in ('n8n', 'backend', 'manual', 'import', 'Unknown')
    ),
    total_planned_minutes numeric(10, 2) check (
        total_planned_minutes is null or total_planned_minutes >= 0
    ),
    created_reason text,
    weather_snapshot jsonb not null default '{}'::jsonb,
    power_snapshot jsonb not null default '{}'::jsonb,
    metadata jsonb not null default '{}'::jsonb,
    source_sheet_row integer,
    import_batch_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (plan_date, plan_source, import_batch_id)
);

create table if not exists public.irrigation_plan_items (
    plan_item_id text primary key,
    daily_plan_id text not null references public.irrigation_daily_plans(daily_plan_id) on delete cascade,
    zone_id text references public.irrigation_zones(zone_id) on delete set null,
    planned_start_at timestamptz,
    planned_minutes numeric(8, 2) check (planned_minutes is null or planned_minutes >= 0),
    actual_start_at timestamptz,
    actual_end_at timestamptz,
    actual_minutes numeric(8, 2) check (actual_minutes is null or actual_minutes >= 0),
    item_status text not null default 'Planned' check (
        item_status in ('Planned', 'Running', 'Done', 'Completed', 'Paused', 'Skipped', 'Cancelled', 'Blocked')
    ),
    water_score numeric(8, 3),
    priority integer,
    reason text,
    metadata jsonb not null default '{}'::jsonb,
    source_sheet_row integer,
    import_batch_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.irrigation_state_snapshots (
    state_snapshot_id text primary key,
    source_id text references public.telemetry_sources(source_id) on delete set null,
    snapshot_at timestamptz not null default now(),
    current_status text not null default 'UNKNOWN' check (
        current_status in ('IDLE', 'RUNNING', 'PAUSED', 'BLOCKED', 'PLANNED', 'DONE', 'COMPLETED', 'SKIPPED', 'UNKNOWN')
    ),
    current_zone_id text references public.irrigation_zones(zone_id) on delete set null,
    next_zone_id text references public.irrigation_zones(zone_id) on delete set null,
    last_zone_completed text,
    remaining_minutes numeric(8, 2) check (remaining_minutes is null or remaining_minutes >= 0),
    pause_reason text,
    raw_state jsonb not null default '{}'::jsonb,
    import_batch_id text,
    created_at timestamptz not null default now()
);

create table if not exists public.irrigation_events (
    irrigation_event_id text primary key,
    source_id text references public.telemetry_sources(source_id) on delete set null,
    event_at timestamptz not null,
    event_type text not null,
    actor text,
    daily_plan_id text references public.irrigation_daily_plans(daily_plan_id) on delete set null,
    plan_item_id text references public.irrigation_plan_items(plan_item_id) on delete set null,
    zone_id text references public.irrigation_zones(zone_id) on delete set null,
    planned_minutes numeric(8, 2) check (planned_minutes is null or planned_minutes >= 0),
    actual_minutes numeric(8, 2) check (actual_minutes is null or actual_minutes >= 0),
    reason text,
    weather_snapshot jsonb not null default '{}'::jsonb,
    power_snapshot jsonb not null default '{}'::jsonb,
    details jsonb not null default '{}'::jsonb,
    source_sheet_row integer,
    import_batch_id text,
    created_at timestamptz not null default now()
);

create table if not exists public.irrigation_auxiliary_devices (
    auxiliary_device_id text primary key,
    source_id text references public.telemetry_sources(source_id) on delete set null,
    device_name text not null,
    device_type text not null check (
        device_type in ('fertilizer_injection_valve', 'fertilizer_mixer', 'pump', 'filter', 'other')
    ),
    active boolean not null default true,
    default_runtime_minutes numeric(8, 2) check (
        default_runtime_minutes is null or default_runtime_minutes >= 0
    ),
    schedule_rule text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.irrigation_auxiliary_tasks (
    auxiliary_task_id text primary key,
    auxiliary_device_id text not null references public.irrigation_auxiliary_devices(auxiliary_device_id) on delete restrict,
    related_daily_plan_id text references public.irrigation_daily_plans(daily_plan_id) on delete set null,
    related_plan_item_id text references public.irrigation_plan_items(plan_item_id) on delete set null,
    task_date date,
    planned_start_at timestamptz,
    planned_minutes numeric(8, 2) check (planned_minutes is null or planned_minutes >= 0),
    actual_start_at timestamptz,
    actual_end_at timestamptz,
    task_status text not null default 'Planned' check (
        task_status in ('Planned', 'Running', 'Done', 'Paused', 'Skipped', 'Cancelled', 'Blocked')
    ),
    reason text,
    metadata jsonb not null default '{}'::jsonb,
    import_batch_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.irrigation_sensor_states (
    sensor_state_id text primary key,
    source_id text references public.telemetry_sources(source_id) on delete set null,
    sensor_id text not null,
    sensor_name text,
    sensor_type text not null check (
        sensor_type in ('tank_full', 'tank_empty', 'tank_level', 'pressure', 'flow', 'manual_flag', 'other')
    ),
    status text not null default 'unknown',
    value_numeric numeric(12, 3),
    value_text text,
    reading_at timestamptz not null,
    details jsonb not null default '{}'::jsonb,
    import_batch_id text,
    created_at timestamptz not null default now()
);

create index if not exists idx_irrigation_zones_active_priority on public.irrigation_zones(active, priority);
create index if not exists idx_irrigation_daily_plans_plan_date on public.irrigation_daily_plans(plan_date desc);
create index if not exists idx_irrigation_plan_items_plan_status on public.irrigation_plan_items(daily_plan_id, item_status);
create index if not exists idx_irrigation_plan_items_zone on public.irrigation_plan_items(zone_id, item_status);
create index if not exists idx_irrigation_state_snapshots_snapshot_at on public.irrigation_state_snapshots(snapshot_at desc);
create index if not exists idx_irrigation_events_event_at on public.irrigation_events(event_at desc);
create index if not exists idx_irrigation_events_zone_event_at on public.irrigation_events(zone_id, event_at desc);
create index if not exists idx_irrigation_auxiliary_tasks_date_status on public.irrigation_auxiliary_tasks(task_date, task_status);
create index if not exists idx_irrigation_sensor_states_sensor_reading on public.irrigation_sensor_states(sensor_id, reading_at desc);

comment on table public.irrigation_zones is 'Irrigation zone configuration and planning inputs. Data model only; no hardware control.';
comment on table public.irrigation_daily_plans is 'Daily irrigation plan headers. First migration imports no plans.';
comment on table public.irrigation_plan_items is 'Zone-level daily plan items and status readbacks.';
comment on table public.irrigation_state_snapshots is 'Read-only state snapshots from the current irrigation path.';
comment on table public.irrigation_events is 'Append-only irrigation event/audit log.';
comment on table public.irrigation_auxiliary_devices is 'Non-zone irrigation support devices such as fertilizer injection valves and mixer.';
comment on table public.irrigation_auxiliary_tasks is 'Planned support tasks for auxiliary devices. Not a command queue.';
comment on table public.irrigation_sensor_states is 'Tank and future sensor state history for planning and safety gates.';

insert into app_private.migration_log (migration_id, description)
values (
    '202605230001_create_irrigation_tables',
    'Create empty irrigation data model tables for zones, plans, state, events, auxiliary devices, tasks, and sensor states.'
)
on conflict (migration_id) do nothing;
