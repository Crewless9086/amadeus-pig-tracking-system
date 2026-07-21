-- Pig lifecycle audit rail.
--
-- Additive and unapplied. This creates immutable lifecycle evidence only;
-- it does not mutate current pig state, perform a lifecycle action, or change any
-- read, write, sales, reservation, slaughter, customer, or notification flow.

create table if not exists public.pig_lifecycle_events (
    lifecycle_event_id text primary key,
    pig_id text not null references public.pigs(pig_id) on delete restrict,
    lifecycle_event_type text not null check (lifecycle_event_type in (
        'entered_farm', 'weaned', 'purpose_changed', 'status_changed',
        'exited_farm', 'lifecycle_correction', 'other'
    )),
    effective_at timestamptz not null,
    recorded_at timestamptz not null default now(),
    actor_reference text not null check (btrim(actor_reference) <> ''),
    source_system text not null check (source_system in (
        'farm_staff', 'owner', 'import', 'system', 'other'
    )),
    source_reference text not null check (btrim(source_reference) <> ''),
    event_note text not null default '',
    event_payload jsonb not null default '{}'::jsonb check (jsonb_typeof(event_payload) = 'object'),
    idempotency_key text not null unique check (btrim(idempotency_key) <> ''),
    supersedes_lifecycle_event_id text references public.pig_lifecycle_events(lifecycle_event_id) on delete restrict,
    created_at timestamptz not null default now(),
    check (supersedes_lifecycle_event_id is null or supersedes_lifecycle_event_id <> lifecycle_event_id),
    check (effective_at <= recorded_at)
);

create index if not exists pig_lifecycle_events_pig_effective_idx
    on public.pig_lifecycle_events(pig_id, effective_at desc, lifecycle_event_id);
create index if not exists pig_lifecycle_events_supersedes_idx
    on public.pig_lifecycle_events(supersedes_lifecycle_event_id)
    where supersedes_lifecycle_event_id is not null;

alter table public.pig_lifecycle_events enable row level security;

create or replace function public.pig_lifecycle_events_validate_supersession()
returns trigger
language plpgsql
as $$
begin
    if new.supersedes_lifecycle_event_id is not null and not exists (
        select 1
        from public.pig_lifecycle_events prior_event
        where prior_event.lifecycle_event_id = new.supersedes_lifecycle_event_id
          and prior_event.pig_id = new.pig_id
    ) then
        raise exception 'pig lifecycle correction must supersede an event for the same pig';
    end if;
    return new;
end;
$$;

drop trigger if exists trg_pig_lifecycle_events_validate_supersession on public.pig_lifecycle_events;
create trigger trg_pig_lifecycle_events_validate_supersession
    before insert on public.pig_lifecycle_events
    for each row execute function public.pig_lifecycle_events_validate_supersession();

drop trigger if exists trg_pig_lifecycle_events_no_update_delete on public.pig_lifecycle_events;
create or replace function public.pig_lifecycle_events_block_update_delete()
returns trigger
language plpgsql
as $$
begin
    raise exception 'pig lifecycle events are append-only';
end;
$$;

create trigger trg_pig_lifecycle_events_no_update_delete
    before update or delete on public.pig_lifecycle_events
    for each row execute function public.pig_lifecycle_events_block_update_delete();

insert into app_private.migration_log (migration_id, description)
values (
    '202607210001_create_pig_lifecycle_events',
    'Create append-only pig lifecycle audit events without changing lifecycle state.'
)
on conflict (migration_id) do nothing;
