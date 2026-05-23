-- Phase 10.3T irrigation import compatibility.
-- Purpose: allow the read-only irrigation sheet import to preserve the source row for latest-state records.
-- This migration does not import data and does not create any hardware-control path.

alter table if exists public.irrigation_state_snapshots
    add column if not exists source_sheet_row integer;

insert into app_private.migration_log (migration_id, description)
values (
    '202605230002_add_irrigation_state_source_sheet_row',
    'Add source_sheet_row trace column to irrigation_state_snapshots for sheet import compatibility.'
)
on conflict (migration_id) do nothing;
