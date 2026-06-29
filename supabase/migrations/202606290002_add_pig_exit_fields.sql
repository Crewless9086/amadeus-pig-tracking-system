-- GS-MIG-8 sales transaction lifecycle support.
--
-- Additive only. These nullable columns preserve legacy PIG_MASTER exit
-- metadata when slaughter sales mark pigs off farm in Supabase.

alter table public.pigs
    add column if not exists exit_date date,
    add column if not exists exit_reason text,
    add column if not exists exit_order_id text,
    add column if not exists carcass_weight_kg numeric(10, 3);

create index if not exists pigs_exit_order_id_idx on public.pigs(exit_order_id);
create index if not exists pigs_exit_date_idx on public.pigs(exit_date);

comment on column public.pigs.exit_date is 'Date the pig left the farm through sale, slaughter, removal, or another terminal event.';
comment on column public.pigs.exit_reason is 'Human-readable reason for the terminal off-farm event.';
comment on column public.pigs.exit_order_id is 'Order or sale identifier linked to the terminal off-farm event when available.';
comment on column public.pigs.carcass_weight_kg is 'Recorded carcass weight for slaughter/abattoir outcomes when available.';

insert into app_private.migration_log (migration_id, description)
values (
    '202606290002_add_pig_exit_fields',
    'Add nullable pig exit metadata fields needed for Supabase-backed slaughter sale lifecycle updates.'
)
on conflict (migration_id) do nothing;
