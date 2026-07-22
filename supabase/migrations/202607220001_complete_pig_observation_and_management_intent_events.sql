-- Complete the Herdmaster evidence and planning rails.
--
-- Additive and unapplied. Observation events remain factual evidence only.
-- Management intents record non-executing farm plans only. Neither rail changes
-- pig purpose/lifecycle/current state, orders, sales, reservations, slaughter,
-- customer messages, notifications, or any other operational projection.

alter table public.pig_observation_events
    add column if not exists confidence numeric(4, 3) not null default 1.000
        check (confidence >= 0 and confidence <= 1),
    add column if not exists evidence_reference text;

create table if not exists public.pig_management_intent_events (
    management_intent_event_id text primary key,
    pig_id text not null references public.pigs(pig_id) on delete restrict,
    intended_at timestamptz not null,
    recorded_at timestamptz not null default now(),
    author_reference text not null check (btrim(author_reference) <> ''),
    intent_type text not null check (intent_type in (
        'sell_after_weaning', 'sell_when_ready', 'retain_for_breeding',
        'hold_for_review', 'other'
    )),
    intent_status text not null default 'advisory' check (intent_status = 'advisory'),
    rationale text not null check (btrim(rationale) <> ''),
    confidence numeric(4, 3) not null check (confidence >= 0 and confidence <= 1),
    observation_event_id text references public.pig_observation_events(observation_event_id) on delete restrict,
    evidence_reference text,
    source_system text not null check (source_system in ('farm_staff', 'owner', 'import', 'other')),
    source_reference text not null default '',
    idempotency_key text not null unique check (btrim(idempotency_key) <> ''),
    supersedes_management_intent_event_id text references public.pig_management_intent_events(management_intent_event_id) on delete restrict,
    created_at timestamptz not null default now(),
    check (supersedes_management_intent_event_id is null or supersedes_management_intent_event_id <> management_intent_event_id),
    check (intended_at <= recorded_at)
);

create index if not exists pig_management_intent_events_pig_intended_idx
    on public.pig_management_intent_events(pig_id, intended_at desc, management_intent_event_id);
create index if not exists pig_management_intent_events_observation_idx
    on public.pig_management_intent_events(observation_event_id)
    where observation_event_id is not null;
create index if not exists pig_management_intent_events_supersedes_idx
    on public.pig_management_intent_events(supersedes_management_intent_event_id)
    where supersedes_management_intent_event_id is not null;

alter table public.pig_management_intent_events enable row level security;

-- Capture is performed only by the authenticated application backend.  There is
-- deliberately no authenticated/anon browser write policy: a browser must use
-- the protected backend route, which derives the actor instead of trusting a
-- client-supplied author.
drop policy if exists pig_observation_events_service_role_insert on public.pig_observation_events;
create policy pig_observation_events_service_role_insert
    on public.pig_observation_events
    for insert
    to service_role
    with check (true);

drop policy if exists pig_management_intent_events_service_role_insert on public.pig_management_intent_events;
create policy pig_management_intent_events_service_role_insert
    on public.pig_management_intent_events
    for insert
    to service_role
    with check (true);

create or replace function public.pig_management_intent_events_validate_references()
returns trigger
language plpgsql
as $$
begin
    if new.observation_event_id is not null and not exists (
        select 1
        from public.pig_observation_events observation_event
        where observation_event.observation_event_id = new.observation_event_id
          and observation_event.pig_id = new.pig_id
    ) then
        raise exception 'pig management intent evidence must reference an observation for the same pig';
    end if;

    if new.supersedes_management_intent_event_id is not null and not exists (
        select 1
        from public.pig_management_intent_events prior_event
        where prior_event.management_intent_event_id = new.supersedes_management_intent_event_id
          and prior_event.pig_id = new.pig_id
    ) then
        raise exception 'pig management intent correction must supersede an event for the same pig';
    end if;
    return new;
end;
$$;

drop trigger if exists trg_pig_management_intent_events_validate_references on public.pig_management_intent_events;
create trigger trg_pig_management_intent_events_validate_references
    before insert on public.pig_management_intent_events
    for each row execute function public.pig_management_intent_events_validate_references();

create or replace function public.pig_management_intent_events_block_update_delete()
returns trigger
language plpgsql
as $$
begin
    raise exception 'pig management intent events are append-only';
end;
$$;

drop trigger if exists trg_pig_management_intent_events_no_update_delete on public.pig_management_intent_events;
create trigger trg_pig_management_intent_events_no_update_delete
    before update or delete on public.pig_management_intent_events
    for each row execute function public.pig_management_intent_events_block_update_delete();

insert into app_private.migration_log (migration_id, description)
values (
    '202607220001_complete_pig_observation_and_management_intent_events',
    'Add observation confidence/evidence fields and a separate append-only advisory pig management-intent rail without operational writes.'
)
on conflict (migration_id) do nothing;
