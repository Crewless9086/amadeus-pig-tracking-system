-- Security hardening: enable Row-Level Security on all current public tables.
-- Purpose: resolve Supabase advisor warning rls_disabled_in_public.
--
-- The Amadeus web app accesses Supabase through the Flask backend using DATABASE_URL.
-- The browser must not read/write these tables directly through the Supabase Data API.
-- Therefore this migration enables RLS and intentionally creates no anon/auth policies.
--
-- Do not use FORCE ROW LEVEL SECURITY here: backend/server database roles must continue
-- to operate through direct Postgres connections while the app remains backend-owned.

do $$
declare
    table_record record;
begin
    for table_record in
        select schemaname, tablename
        from pg_tables
        where schemaname = 'public'
          and tablename in (
              'orders',
              'sales_pricing',
              'order_lines',
              'order_intakes',
              'order_intake_items',
              'order_documents',
              'order_status_logs',
              'sales_transactions',
              'sales_transaction_items',
              'telemetry_sources',
              'power_readings_5min',
              'power_latest_state',
              'telemetry_alerts',
              'weather_readings',
              'weather_latest_state',
              'weather_forecast_snapshots',
              'irrigation_zones',
              'irrigation_daily_plans',
              'irrigation_plan_items',
              'irrigation_state_snapshots',
              'irrigation_events',
              'irrigation_auxiliary_devices',
              'irrigation_auxiliary_tasks',
              'irrigation_sensor_states',
              'power_daily_rollups',
              'weather_daily_rollups',
              'irrigation_daily_rollups',
              'power_monthly_rollups',
              'weather_monthly_rollups',
              'irrigation_monthly_rollups',
              'power_yearly_rollups',
              'weather_yearly_rollups',
              'irrigation_yearly_rollups'
          )
    loop
        execute format(
            'alter table %I.%I enable row level security',
            table_record.schemaname,
            table_record.tablename
        );
    end loop;
end $$;

insert into app_private.migration_log (migration_id, description)
values (
    '202605270001_enable_rls_on_public_tables',
    'Enable RLS on all current public tables and leave browser/API access closed by default.'
)
on conflict (migration_id) do nothing;
