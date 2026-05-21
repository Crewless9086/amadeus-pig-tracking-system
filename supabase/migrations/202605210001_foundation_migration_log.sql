-- Phase 10.1B foundation baseline.
-- Purpose: prove checked-in SQL migrations can be reviewed, run, and verified
-- before creating any real business tables.

create schema if not exists app_private;

create table if not exists app_private.migration_log (
    migration_id text primary key,
    description text not null,
    applied_at timestamptz not null default now()
);

insert into app_private.migration_log (migration_id, description)
values (
    '202605210001_foundation_migration_log',
    'Create internal migration log for Supabase foundation baseline.'
)
on conflict (migration_id) do nothing;
