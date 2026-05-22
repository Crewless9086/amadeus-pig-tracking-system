-- Phase 10.3J2 weather/forecast telemetry schema.
-- Purpose: create weather station and forecast tables beside the existing power telemetry path.
-- This migration imports no data, changes no logger, and does not change live n8n workflows.

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
values
(
    'weather-station-main',
    'weather',
    'weather_com_pws',
    'Amadeus Local Weather Station',
    null,
    'Africa/Johannesburg',
    30,
    '{"phase":"10.3J2","purpose":"weather station current-state read model"}'::jsonb
),
(
    'open-meteo-forecast-main',
    'forecast',
    'open_meteo',
    'Amadeus Forecast',
    null,
    'Africa/Johannesburg',
    360,
    '{"phase":"10.3J2","purpose":"forecast read model"}'::jsonb
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

create table if not exists public.weather_readings (
    reading_id text primary key,
    source_id text not null references public.telemetry_sources(source_id) on delete restrict,
    reading_at timestamptz not null,
    temperature_c numeric(6, 2),
    humidity_pct numeric(5, 2) check (
        humidity_pct is null or (humidity_pct >= 0 and humidity_pct <= 100)
    ),
    wind_speed_kmh numeric(8, 3),
    wind_gust_kmh numeric(8, 3),
    wind_direction_deg numeric(6, 2) check (
        wind_direction_deg is null or (wind_direction_deg >= 0 and wind_direction_deg <= 360)
    ),
    rain_rate_mm_h numeric(8, 3),
    rain_today_mm numeric(8, 3),
    pressure_hpa numeric(8, 3),
    raw_payload jsonb,
    ingested_at timestamptz not null default now(),
    import_batch_id text,
    unique (source_id, reading_at)
);

create table if not exists public.weather_latest_state (
    source_id text primary key references public.telemetry_sources(source_id) on delete restrict,
    reading_at timestamptz not null,
    temperature_c numeric(6, 2),
    humidity_pct numeric(5, 2) check (
        humidity_pct is null or (humidity_pct >= 0 and humidity_pct <= 100)
    ),
    wind_speed_kmh numeric(8, 3),
    wind_gust_kmh numeric(8, 3),
    wind_direction_deg numeric(6, 2) check (
        wind_direction_deg is null or (wind_direction_deg >= 0 and wind_direction_deg <= 360)
    ),
    rain_rate_mm_h numeric(8, 3),
    rain_today_mm numeric(8, 3),
    pressure_hpa numeric(8, 3),
    flags jsonb not null default '{}'::jsonb,
    summary_status text not null default 'ok' check (
        summary_status in ('ok', 'caution', 'warning', 'stale', 'unavailable')
    ),
    summary_headline text,
    summary_notes jsonb not null default '[]'::jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists public.weather_forecast_snapshots (
    forecast_snapshot_id text primary key,
    source_id text not null references public.telemetry_sources(source_id) on delete restrict,
    forecast_run_at timestamptz not null,
    timezone text not null default 'Africa/Johannesburg',
    forecast_date date not null,
    offset_days integer not null check (offset_days >= 0),
    temp_max_c numeric(6, 2),
    temp_min_c numeric(6, 2),
    rain_sum_mm numeric(8, 3),
    rain_probability_max_pct numeric(5, 2) check (
        rain_probability_max_pct is null or (rain_probability_max_pct >= 0 and rain_probability_max_pct <= 100)
    ),
    wind_max_kmh numeric(8, 3),
    gust_max_kmh numeric(8, 3),
    flags jsonb not null default '{}'::jsonb,
    raw_payload jsonb,
    ingested_at timestamptz not null default now(),
    import_batch_id text,
    unique (source_id, forecast_run_at, forecast_date)
);

create index if not exists idx_weather_readings_source_reading_at on public.weather_readings(source_id, reading_at desc);
create index if not exists idx_weather_latest_state_reading_at on public.weather_latest_state(reading_at desc);
create index if not exists idx_weather_forecast_source_run_date on public.weather_forecast_snapshots(source_id, forecast_run_at desc, forecast_date asc);
create index if not exists idx_weather_forecast_date on public.weather_forecast_snapshots(forecast_date asc);

comment on table public.weather_readings is 'Normalized local weather station readings. Not an Oom Sakkie direct answer source.';
comment on table public.weather_latest_state is 'One latest weather state row per source for fast backend/Oom Sakkie current-state answers.';
comment on table public.weather_forecast_snapshots is 'Open-Meteo forecast periods by forecast run. Backend read endpoints choose latest run.';

insert into app_private.migration_log (migration_id, description)
values (
    '202605220001_create_telemetry_weather_tables',
    'Create telemetry weather and forecast tables for current weather and short forecast read models.'
)
on conflict (migration_id) do nothing;
