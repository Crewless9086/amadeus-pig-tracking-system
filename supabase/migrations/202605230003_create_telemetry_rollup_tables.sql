-- Phase 10.3W2 telemetry rollup schema.
-- Purpose: create empty daily/monthly/yearly rollup tables for power, weather, and irrigation.
-- This migration generates no rollup data, deletes no raw telemetry, changes no live workflows,
-- and creates no irrigation command/control endpoint.

create table if not exists public.power_daily_rollups (
    rollup_id text primary key,
    source_id text not null references public.telemetry_sources(source_id) on delete restrict,
    rollup_date date not null,
    source_window_start timestamptz,
    source_window_end timestamptz,
    sample_count integer not null default 0 check (sample_count >= 0),
    expected_sample_count integer not null default 0 check (expected_sample_count >= 0),
    coverage_pct numeric(6, 2) check (coverage_pct is null or (coverage_pct >= 0 and coverage_pct <= 100)),
    battery_soc_min_pct numeric(5, 2),
    battery_soc_max_pct numeric(5, 2),
    battery_soc_avg_pct numeric(5, 2),
    load_power_avg_w numeric(12, 3),
    load_power_max_w numeric(12, 3),
    solar_power_avg_w numeric(12, 3),
    solar_power_max_w numeric(12, 3),
    grid_active_minutes numeric(10, 2) not null default 0,
    generator_active_minutes numeric(10, 2) not null default 0,
    no_solar_minutes numeric(10, 2) not null default 0,
    estimated_solar_kwh numeric(12, 4),
    estimated_load_kwh numeric(12, 4),
    estimated_grid_import_kwh numeric(12, 4),
    estimated_grid_export_kwh numeric(12, 4),
    estimated_generator_kwh numeric(12, 4),
    energy_calculation_method text not null default 'sample_integration_estimated',
    tariff_zar_per_kwh numeric(10, 4) not null default 9.10,
    estimated_value_zar numeric(12, 2),
    limitations jsonb not null default '[]'::jsonb,
    calculation_version text not null default 'rollup_schema_v1',
    metadata jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, rollup_date)
);

create table if not exists public.weather_daily_rollups (
    rollup_id text primary key,
    source_id text not null references public.telemetry_sources(source_id) on delete restrict,
    rollup_date date not null,
    source_window_start timestamptz,
    source_window_end timestamptz,
    sample_count integer not null default 0 check (sample_count >= 0),
    expected_sample_count integer not null default 0 check (expected_sample_count >= 0),
    coverage_pct numeric(6, 2) check (coverage_pct is null or (coverage_pct >= 0 and coverage_pct <= 100)),
    temperature_min_c numeric(6, 2),
    temperature_max_c numeric(6, 2),
    temperature_avg_c numeric(6, 2),
    humidity_avg_pct numeric(5, 2),
    rain_total_mm numeric(10, 3),
    rain_rate_max_mm_h numeric(10, 3),
    wind_speed_max_kmh numeric(10, 3),
    wind_gust_max_kmh numeric(10, 3),
    pressure_min_hpa numeric(10, 3),
    pressure_max_hpa numeric(10, 3),
    irrigation_caution_minutes numeric(10, 2) not null default 0,
    flags jsonb not null default '{}'::jsonb,
    calculation_version text not null default 'rollup_schema_v1',
    metadata jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, rollup_date)
);

create table if not exists public.irrigation_daily_rollups (
    rollup_id text primary key,
    source_id text not null references public.telemetry_sources(source_id) on delete restrict,
    rollup_date date not null,
    daily_plan_id text references public.irrigation_daily_plans(daily_plan_id) on delete set null,
    source_window_start timestamptz,
    source_window_end timestamptz,
    planned_zone_count integer not null default 0 check (planned_zone_count >= 0),
    completed_zone_count integer not null default 0 check (completed_zone_count >= 0),
    skipped_zone_count integer not null default 0 check (skipped_zone_count >= 0),
    paused_zone_count integer not null default 0 check (paused_zone_count >= 0),
    planned_minutes numeric(10, 2) not null default 0,
    completed_minutes numeric(10, 2) not null default 0,
    active_runtime_minutes numeric(10, 2) not null default 0,
    weather_hold_minutes numeric(10, 2) not null default 0,
    power_hold_minutes numeric(10, 2) not null default 0,
    tank_hold_minutes numeric(10, 2) not null default 0,
    manual_override_count integer not null default 0 check (manual_override_count >= 0),
    event_count integer not null default 0 check (event_count >= 0),
    fertilizer_injection_minutes numeric(10, 2) not null default 0,
    fertilizer_injection_cycles integer not null default 0 check (fertilizer_injection_cycles >= 0),
    fertilizer_mixer_minutes numeric(10, 2) not null default 0,
    tank_full_count integer not null default 0 check (tank_full_count >= 0),
    tank_empty_count integer not null default 0 check (tank_empty_count >= 0),
    tank_status_notes text,
    notes text,
    calculation_version text not null default 'rollup_schema_v1',
    metadata jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, rollup_date)
);

create table if not exists public.power_monthly_rollups (
    rollup_id text primary key,
    source_id text not null references public.telemetry_sources(source_id) on delete restrict,
    rollup_month date not null,
    included_day_count integer not null default 0 check (included_day_count >= 0),
    expected_day_count integer not null default 0 check (expected_day_count >= 0),
    coverage_pct numeric(6, 2) check (coverage_pct is null or (coverage_pct >= 0 and coverage_pct <= 100)),
    estimated_solar_kwh numeric(12, 4),
    estimated_load_kwh numeric(12, 4),
    estimated_grid_import_kwh numeric(12, 4),
    estimated_grid_export_kwh numeric(12, 4),
    estimated_generator_kwh numeric(12, 4),
    grid_active_minutes numeric(12, 2) not null default 0,
    generator_active_minutes numeric(12, 2) not null default 0,
    max_load_power_w numeric(12, 3),
    max_solar_power_w numeric(12, 3),
    battery_soc_avg_pct numeric(5, 2),
    tariff_zar_per_kwh numeric(10, 4) not null default 9.10,
    estimated_value_zar numeric(12, 2),
    calculation_version text not null default 'rollup_schema_v1',
    metadata jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, rollup_month)
);

create table if not exists public.weather_monthly_rollups (
    rollup_id text primary key,
    source_id text not null references public.telemetry_sources(source_id) on delete restrict,
    rollup_month date not null,
    included_day_count integer not null default 0 check (included_day_count >= 0),
    expected_day_count integer not null default 0 check (expected_day_count >= 0),
    coverage_pct numeric(6, 2) check (coverage_pct is null or (coverage_pct >= 0 and coverage_pct <= 100)),
    temperature_min_c numeric(6, 2),
    temperature_max_c numeric(6, 2),
    temperature_avg_c numeric(6, 2),
    rain_total_mm numeric(12, 3),
    wind_speed_max_kmh numeric(10, 3),
    wind_gust_max_kmh numeric(10, 3),
    irrigation_caution_minutes numeric(12, 2) not null default 0,
    calculation_version text not null default 'rollup_schema_v1',
    metadata jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, rollup_month)
);

create table if not exists public.irrigation_monthly_rollups (
    rollup_id text primary key,
    source_id text not null references public.telemetry_sources(source_id) on delete restrict,
    rollup_month date not null,
    included_day_count integer not null default 0 check (included_day_count >= 0),
    expected_day_count integer not null default 0 check (expected_day_count >= 0),
    coverage_pct numeric(6, 2) check (coverage_pct is null or (coverage_pct >= 0 and coverage_pct <= 100)),
    planned_zone_count integer not null default 0,
    completed_zone_count integer not null default 0,
    skipped_zone_count integer not null default 0,
    paused_zone_count integer not null default 0,
    planned_minutes numeric(12, 2) not null default 0,
    completed_minutes numeric(12, 2) not null default 0,
    active_runtime_minutes numeric(12, 2) not null default 0,
    weather_hold_minutes numeric(12, 2) not null default 0,
    power_hold_minutes numeric(12, 2) not null default 0,
    tank_hold_minutes numeric(12, 2) not null default 0,
    fertilizer_injection_minutes numeric(12, 2) not null default 0,
    fertilizer_injection_cycles integer not null default 0,
    fertilizer_mixer_minutes numeric(12, 2) not null default 0,
    tank_full_count integer not null default 0,
    tank_empty_count integer not null default 0,
    calculation_version text not null default 'rollup_schema_v1',
    metadata jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, rollup_month)
);

create table if not exists public.power_yearly_rollups (
    rollup_id text primary key,
    source_id text not null references public.telemetry_sources(source_id) on delete restrict,
    rollup_year integer not null check (rollup_year >= 2000),
    included_month_count integer not null default 0 check (included_month_count >= 0),
    expected_month_count integer not null default 12 check (expected_month_count >= 0),
    coverage_pct numeric(6, 2) check (coverage_pct is null or (coverage_pct >= 0 and coverage_pct <= 100)),
    estimated_solar_kwh numeric(14, 4),
    estimated_load_kwh numeric(14, 4),
    estimated_grid_import_kwh numeric(14, 4),
    estimated_grid_export_kwh numeric(14, 4),
    estimated_generator_kwh numeric(14, 4),
    estimated_value_zar numeric(14, 2),
    calculation_version text not null default 'rollup_schema_v1',
    metadata jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, rollup_year)
);

create table if not exists public.weather_yearly_rollups (
    rollup_id text primary key,
    source_id text not null references public.telemetry_sources(source_id) on delete restrict,
    rollup_year integer not null check (rollup_year >= 2000),
    included_month_count integer not null default 0 check (included_month_count >= 0),
    expected_month_count integer not null default 12 check (expected_month_count >= 0),
    coverage_pct numeric(6, 2) check (coverage_pct is null or (coverage_pct >= 0 and coverage_pct <= 100)),
    temperature_min_c numeric(6, 2),
    temperature_max_c numeric(6, 2),
    temperature_avg_c numeric(6, 2),
    rain_total_mm numeric(14, 3),
    wind_speed_max_kmh numeric(10, 3),
    wind_gust_max_kmh numeric(10, 3),
    irrigation_caution_minutes numeric(14, 2) not null default 0,
    calculation_version text not null default 'rollup_schema_v1',
    metadata jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, rollup_year)
);

create table if not exists public.irrigation_yearly_rollups (
    rollup_id text primary key,
    source_id text not null references public.telemetry_sources(source_id) on delete restrict,
    rollup_year integer not null check (rollup_year >= 2000),
    included_month_count integer not null default 0 check (included_month_count >= 0),
    expected_month_count integer not null default 12 check (expected_month_count >= 0),
    coverage_pct numeric(6, 2) check (coverage_pct is null or (coverage_pct >= 0 and coverage_pct <= 100)),
    planned_zone_count integer not null default 0,
    completed_zone_count integer not null default 0,
    skipped_zone_count integer not null default 0,
    paused_zone_count integer not null default 0,
    planned_minutes numeric(14, 2) not null default 0,
    completed_minutes numeric(14, 2) not null default 0,
    active_runtime_minutes numeric(14, 2) not null default 0,
    weather_hold_minutes numeric(14, 2) not null default 0,
    power_hold_minutes numeric(14, 2) not null default 0,
    tank_hold_minutes numeric(14, 2) not null default 0,
    fertilizer_injection_minutes numeric(14, 2) not null default 0,
    fertilizer_injection_cycles integer not null default 0,
    fertilizer_mixer_minutes numeric(14, 2) not null default 0,
    tank_full_count integer not null default 0,
    tank_empty_count integer not null default 0,
    calculation_version text not null default 'rollup_schema_v1',
    metadata jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, rollup_year)
);

create index if not exists idx_power_daily_rollups_source_date on public.power_daily_rollups(source_id, rollup_date desc);
create index if not exists idx_weather_daily_rollups_source_date on public.weather_daily_rollups(source_id, rollup_date desc);
create index if not exists idx_irrigation_daily_rollups_source_date on public.irrigation_daily_rollups(source_id, rollup_date desc);
create index if not exists idx_power_monthly_rollups_source_month on public.power_monthly_rollups(source_id, rollup_month desc);
create index if not exists idx_weather_monthly_rollups_source_month on public.weather_monthly_rollups(source_id, rollup_month desc);
create index if not exists idx_irrigation_monthly_rollups_source_month on public.irrigation_monthly_rollups(source_id, rollup_month desc);
create index if not exists idx_power_yearly_rollups_source_year on public.power_yearly_rollups(source_id, rollup_year desc);
create index if not exists idx_weather_yearly_rollups_source_year on public.weather_yearly_rollups(source_id, rollup_year desc);
create index if not exists idx_irrigation_yearly_rollups_source_year on public.irrigation_yearly_rollups(source_id, rollup_year desc);

comment on table public.power_daily_rollups is 'Daily power rollup storage. Estimated kWh only until approved counters/rules are implemented.';
comment on table public.weather_daily_rollups is 'Daily weather rollup storage for local station trend summaries.';
comment on table public.irrigation_daily_rollups is 'Daily irrigation rollup storage, including fertilizer and tank placeholders. Not a command queue.';
comment on table public.power_monthly_rollups is 'Monthly power summary storage derived from accepted daily rollups.';
comment on table public.weather_monthly_rollups is 'Monthly weather summary storage derived from accepted daily rollups.';
comment on table public.irrigation_monthly_rollups is 'Monthly irrigation summary storage derived from accepted daily rollups.';
comment on table public.power_yearly_rollups is 'Yearly power summary storage derived from accepted monthly rollups.';
comment on table public.weather_yearly_rollups is 'Yearly weather summary storage derived from accepted monthly rollups.';
comment on table public.irrigation_yearly_rollups is 'Yearly irrigation summary storage derived from accepted monthly rollups.';

insert into app_private.migration_log (migration_id, description)
values (
    '202605230003_create_telemetry_rollup_tables',
    'Create empty telemetry rollup tables for power, weather, and irrigation daily/monthly/yearly summaries.'
)
on conflict (migration_id) do nothing;
