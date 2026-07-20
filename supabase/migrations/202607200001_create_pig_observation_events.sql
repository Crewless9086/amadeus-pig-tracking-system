-- Herdmaster human pig-observation fact rail.
--
-- Additive and unapplied. This creates factual observation evidence only;
-- it does not change pig lifecycle, purpose, medical, sales, reservation,
-- slaughter, customer, or notification state.

create table if not exists public.pig_observation_events (
    observation_event_id text primary key,
    pig_id text not null references public.pigs(pig_id) on delete restrict,
    observed_at timestamptz not null,
    recorded_at timestamptz not null default now(),
    observer_reference text not null check (btrim(observer_reference) <> ''),
    observation_category text not null check (observation_category in (
        'behaviour', 'body_condition', 'feeding_drinking', 'environment',
        'welfare', 'data_quality', 'other'
    )),
    severity text not null default 'informational' check (severity in (
        'informational', 'attention', 'urgent'
    )),
    factual_note text not null check (btrim(factual_note) <> ''),
    measurements_json jsonb not null default '{}'::jsonb check (jsonb_typeof(measurements_json) = 'object'),
    source_system text not null check (source_system in ('farm_staff', 'owner', 'import', 'other')),
    source_reference text not null default '',
    idempotency_key text not null unique check (btrim(idempotency_key) <> ''),
    supersedes_observation_event_id text references public.pig_observation_events(observation_event_id) on delete restrict,
    created_at timestamptz not null default now(),
    check (supersedes_observation_event_id is null or supersedes_observation_event_id <> observation_event_id),
    check (observed_at <= recorded_at)
);

create index if not exists pig_observation_events_pig_observed_idx
    on public.pig_observation_events(pig_id, observed_at desc, observation_event_id);
create index if not exists pig_observation_events_supersedes_idx
    on public.pig_observation_events(supersedes_observation_event_id)
    where supersedes_observation_event_id is not null;

alter table public.pig_observation_events enable row level security;

create or replace function public.pig_observation_events_validate_supersession()
returns trigger
language plpgsql
as $$
begin
    if new.supersedes_observation_event_id is not null and not exists (
        select 1
        from public.pig_observation_events prior_event
        where prior_event.observation_event_id = new.supersedes_observation_event_id
          and prior_event.pig_id = new.pig_id
    ) then
        raise exception 'pig observation correction must supersede an event for the same pig';
    end if;
    return new;
end;
$$;

drop trigger if exists trg_pig_observation_events_validate_supersession on public.pig_observation_events;
create trigger trg_pig_observation_events_validate_supersession
    before insert on public.pig_observation_events
    for each row execute function public.pig_observation_events_validate_supersession();

drop trigger if exists trg_pig_observation_events_no_update_delete on public.pig_observation_events;
create trigger trg_pig_observation_events_no_update_delete
    before update or delete on public.pig_observation_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

insert into app_private.migration_log (migration_id, description)
values (
    '202607200001_create_pig_observation_events',
    'Create append-only factual human pig observation events for read-only Herdmaster decision support.'
)
on conflict (migration_id) do nothing;
