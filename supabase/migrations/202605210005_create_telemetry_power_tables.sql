-- Phase 10.3C telemetry power schema.
-- Purpose: create the first empty telemetry tables for Sunsynk power current-state reads.
-- This migration imports no data, changes no logger, and does not change live n8n workflows.

create table if not exists public.telemetry_sources (
    source_id text primary key,
    source_type text not null check (source_type in ('power', 'weather', 'forecast', 'irrigation')),
    provider text not null,
    display_name text not null,
    external_ref text,
    timezone text not null default 'Africa/Johannesburg',
    stale_after_minutes integer not null default 15 check (stale_after_minutes > 0),
    active boolean not null default true,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.power_readings_5min (
    reading_id text primary key,
    source_id text not null references public.telemetry_sources(source_id) on delete restrict,
    reading_at timestamptz not null,
    battery_soc_pct numeric(5, 2) check (
        battery_soc_pct is null or (battery_soc_pct >= 0 and battery_soc_pct <= 100)
    ),
    battery_power_w numeric(12, 3),
    solar_power_w numeric(12, 3),
    pv1_power_w numeric(12, 3),
    pv2_power_w numeric(12, 3),
    load_power_w numeric(12, 3),
    grid_power_w numeric(12, 3),
    generator_power_w numeric(12, 3),
    inverter_output_w numeric(12, 3),
    grid_active boolean,
    generator_active boolean,
    battery_charging boolean,
    battery_discharging boolean,
    raw_payload jsonb,
    ingested_at timestamptz not null default now(),
    import_batch_id text,
    unique (source_id, reading_at)
);

create table if not exists public.power_latest_state (
    source_id text primary key references public.telemetry_sources(source_id) on delete restrict,
    reading_at timestamptz not null,
    battery_soc_pct numeric(5, 2) check (
        battery_soc_pct is null or (battery_soc_pct >= 0 and battery_soc_pct <= 100)
    ),
    battery_power_w numeric(12, 3),
    solar_power_w numeric(12, 3),
    pv1_power_w numeric(12, 3),
    pv2_power_w numeric(12, 3),
    load_power_w numeric(12, 3),
    grid_power_w numeric(12, 3),
    generator_power_w numeric(12, 3),
    inverter_output_w numeric(12, 3),
    battery_state text not null default 'unknown' check (
        battery_state in ('charging', 'discharging', 'idle', 'unknown')
    ),
    grid_state text not null default 'unknown' check (
        grid_state in ('using_grid', 'not_using_grid', 'exporting', 'unknown')
    ),
    generator_state text not null default 'unknown' check (
        generator_state in ('on', 'off', 'unknown')
    ),
    flags jsonb not null default '{}'::jsonb,
    summary_status text not null default 'ok' check (
        summary_status in ('ok', 'warning', 'stale', 'unavailable')
    ),
    summary_headline text,
    summary_notes jsonb not null default '[]'::jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists public.telemetry_alerts (
    alert_id text primary key,
    source_id text references public.telemetry_sources(source_id) on delete set null,
    area text not null check (area in ('power', 'weather', 'forecast', 'irrigation', 'system')),
    alert_type text not null,
    severity text not null check (severity in ('info', 'warning', 'critical')),
    message text not null,
    event_at timestamptz not null,
    resolved_at timestamptz,
    status text not null default 'Open' check (status in ('Open', 'Resolved', 'Ignored')),
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_telemetry_sources_source_type on public.telemetry_sources(source_type);
create index if not exists idx_telemetry_sources_provider on public.telemetry_sources(provider);
create index if not exists idx_power_readings_5min_source_reading_at on public.power_readings_5min(source_id, reading_at desc);
create index if not exists idx_power_latest_state_reading_at on public.power_latest_state(reading_at desc);
create index if not exists idx_telemetry_alerts_area_event_at on public.telemetry_alerts(area, event_at desc);
create index if not exists idx_telemetry_alerts_source_event_at on public.telemetry_alerts(source_id, event_at desc);
create index if not exists idx_telemetry_alerts_status_severity on public.telemetry_alerts(status, severity);

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
    'sunsynk-main-inverter',
    'power',
    'sunsynk',
    'Amadeus Sunsynk Inverter',
    '2111244718',
    'Africa/Johannesburg',
    15,
    '{"phase":"10.3C","purpose":"first power telemetry source"}'::jsonb
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

comment on table public.telemetry_sources is 'Telemetry source registry for power, weather, forecast, irrigation, and future devices. Contains no secrets.';
comment on table public.power_readings_5min is 'Recent normalized Sunsynk power readings for debug and future rollups. Not an Oom Sakkie direct answer source.';
comment on table public.power_latest_state is 'One latest power state row per source for fast backend/Oom Sakkie current-state answers.';
comment on table public.telemetry_alerts is 'Shared telemetry alert and event history for power, weather, forecast, irrigation, and system events.';

insert into app_private.migration_log (migration_id, description)
values (
    '202605210005_create_telemetry_power_tables',
    'Create first telemetry power tables for Sunsynk current-state read model.'
)
on conflict (migration_id) do nothing;
