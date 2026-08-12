-- Append-only actual boar exposure facts. An exposure is not a mating,
-- service, conception, pregnancy, movement, or litter event.
create table if not exists public.pig_breeding_exposure_events (
    exposure_event_id text primary key,
    exposure_identity text not null,
    event_kind text not null check (event_kind in ('started','removed')),
    sow_pig_id text not null references public.pigs(pig_id) on delete restrict,
    boar_pig_id text not null references public.pigs(pig_id) on delete restrict,
    occurred_on date not null,
    planned_removal_on date,
    observer_reference text not null check (btrim(observer_reference) <> ''),
    source_reference text not null check (btrim(source_reference) <> ''),
    idempotency_key text not null unique check (btrim(idempotency_key) <> ''),
    created_at timestamptz not null default now(),
    unique(exposure_identity,event_kind),
    check ((event_kind='started' and planned_removal_on is not null and planned_removal_on >= occurred_on)
        or (event_kind='removed' and planned_removal_on is null))
);

create index if not exists pig_breeding_exposure_sow_chronology_idx
    on public.pig_breeding_exposure_events(sow_pig_id, occurred_on desc, exposure_event_id);

alter table public.pig_breeding_exposure_events enable row level security;
revoke all privileges on table public.pig_breeding_exposure_events from public;
do $$ begin
  if exists(select 1 from pg_roles where rolname='anon') then
    revoke all privileges on table public.pig_breeding_exposure_events from anon;
  end if;
  if exists(select 1 from pg_roles where rolname='authenticated') then
    revoke all privileges on table public.pig_breeding_exposure_events from authenticated;
  end if;
  if exists(select 1 from pg_roles where rolname='service_role') then
    revoke all privileges on table public.pig_breeding_exposure_events from service_role;
    grant select, insert on public.pig_breeding_exposure_events to service_role;
  end if;
end $$;

insert into app_private.migration_log(migration_id,description)
values('202608120001_create_breeding_exposure_events',
       'Create append-only actual boar exposure facts separate from mating/service chronology.')
on conflict(migration_id) do nothing;
