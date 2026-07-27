-- Owner-confirmed, append-only livestock commercial availability evidence.
-- This records observation evidence only. It cannot change animal, customer,
-- reservation, allocation, order, quote, stock, movement or business state.

create table if not exists public.sam_live_stock_availability_observation_events (
    observation_event_id text primary key,
    cohort_hash text not null check (cohort_hash ~ '^[0-9a-f]{64}$'),
    contract_version text not null,
    evaluator_version text not null,
    observed_at timestamptz not null,
    expires_at timestamptz not null,
    observer_principal text not null check (btrim(observer_principal) <> ''),
    source text not null check (source in (
        'owner_weighing_review', 'owner_physical_stock_review'
    )),
    row_count integer not null check (row_count >= 0),
    eligible_totals_json jsonb not null check (jsonb_typeof(eligible_totals_json) = 'object'),
    exclusions_json jsonb not null check (jsonb_typeof(exclusions_json) = 'object'),
    unresolved_count integer not null check (unresolved_count >= 0),
    lineage_json jsonb not null check (jsonb_typeof(lineage_json) = 'array'),
    created_at timestamptz not null default now(),
    check (observed_at <= created_at),
    check (expires_at > observed_at),
    unique (cohort_hash, observed_at, observer_principal)
);

create index if not exists sam_live_stock_availability_observed_idx
    on public.sam_live_stock_availability_observation_events(
        observed_at desc, created_at desc, observation_event_id
    );

alter table public.sam_live_stock_availability_observation_events enable row level security;

revoke all privileges on table public.sam_live_stock_availability_observation_events from public;
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all privileges on table public.sam_live_stock_availability_observation_events from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all privileges on table public.sam_live_stock_availability_observation_events from authenticated;
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        revoke all privileges on table public.sam_live_stock_availability_observation_events from service_role;
        grant select, insert on table public.sam_live_stock_availability_observation_events to service_role;
    end if;
end;
$$;

create or replace function public.sam_live_stock_availability_observations_block_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'SAM livestock availability observations are append-only';
end;
$$;

drop trigger if exists trg_sam_live_stock_availability_observations_immutable
    on public.sam_live_stock_availability_observation_events;
create trigger trg_sam_live_stock_availability_observations_immutable
    before update or delete on public.sam_live_stock_availability_observation_events
    for each row execute function public.sam_live_stock_availability_observations_block_mutation();

revoke all privileges on function public.sam_live_stock_availability_observations_block_mutation()
    from public;
do $$
declare
    role_name text;
begin
    foreach role_name in array array['anon', 'authenticated', 'service_role'] loop
        if exists (select 1 from pg_roles where rolname = role_name) then
            execute format(
                'revoke all privileges on function public.sam_live_stock_availability_observations_block_mutation() from %I',
                role_name
            );
        end if;
    end loop;
end;
$$;

insert into app_private.migration_log (migration_id, description)
values (
    '202607270003_create_sam_live_stock_availability_observations',
    'Create append-only owner-confirmed SAM Livestock commercial availability observation evidence.'
)
on conflict (migration_id) do nothing;
