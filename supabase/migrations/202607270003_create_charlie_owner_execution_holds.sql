create table if not exists public.charlie_owner_execution_hold_events (
    event_id text primary key,
    hold_id text not null,
    mission_id text not null references public.charlie_missions(mission_id) on delete restrict,
    generation_identity text not null,
    event_type text not null check (event_type in ('hold_created', 'hold_released')),
    reason text not null,
    owner_identity_hash text not null check (length(owner_identity_hash) = 64),
    authorization_identity text not null check (length(authorization_identity) = 64),
    release_of_event_id text references public.charlie_owner_execution_hold_events(event_id) on delete restrict,
    evidence_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    check (
        (event_type = 'hold_created' and release_of_event_id is null)
        or
        (event_type = 'hold_released' and release_of_event_id is not null)
    ),
    unique (hold_id, event_type),
    unique (release_of_event_id)
);

create index if not exists idx_charlie_owner_execution_holds_mission_created
    on public.charlie_owner_execution_hold_events(mission_id, created_at desc);

create or replace function public.validate_charlie_owner_execution_hold_event()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    created_event public.charlie_owner_execution_hold_events%rowtype;
begin
    perform pg_advisory_xact_lock(hashtextextended(new.mission_id, 0));
    if new.event_type = 'hold_released' then
        select *
          into created_event
          from public.charlie_owner_execution_hold_events
         where event_id = new.release_of_event_id
         for share;
        if not found
           or created_event.event_type <> 'hold_created'
           or created_event.hold_id <> new.hold_id
           or created_event.mission_id <> new.mission_id
           or created_event.generation_identity <> new.generation_identity then
            raise exception 'owner_execution_hold_release_identity_invalid';
        end if;
    end if;
    return new;
end;
$$;

drop trigger if exists validate_charlie_owner_execution_hold_events_insert
    on public.charlie_owner_execution_hold_events;
create trigger validate_charlie_owner_execution_hold_events_insert
before insert on public.charlie_owner_execution_hold_events
for each row execute function public.validate_charlie_owner_execution_hold_event();

create or replace function public.prevent_held_charlie_mission_mutation()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    perform pg_advisory_xact_lock(hashtextextended(old.mission_id, 0));
    if exists (
        select 1
          from public.charlie_owner_execution_hold_events as hold_event
         where hold_event.mission_id = old.mission_id
           and hold_event.event_type = 'hold_created'
           and not exists (
               select 1
                 from public.charlie_owner_execution_hold_events as release_event
                where release_event.release_of_event_id = hold_event.event_id
                  and release_event.event_type = 'hold_released'
           )
    ) then
        raise exception 'owner_execution_hold_active';
    end if;
    return new;
end;
$$;

drop trigger if exists prevent_held_charlie_mission_update on public.charlie_missions;
create trigger prevent_held_charlie_mission_update
before update on public.charlie_missions
for each row execute function public.prevent_held_charlie_mission_mutation();

create or replace function public.prevent_charlie_owner_execution_hold_mutation()
returns trigger
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
    raise exception 'charlie_owner_execution_hold_events is append-only';
end;
$$;

drop trigger if exists prevent_charlie_owner_execution_hold_events_update
    on public.charlie_owner_execution_hold_events;
create trigger prevent_charlie_owner_execution_hold_events_update
before update on public.charlie_owner_execution_hold_events
for each row execute function public.prevent_charlie_owner_execution_hold_mutation();

drop trigger if exists prevent_charlie_owner_execution_hold_events_delete
    on public.charlie_owner_execution_hold_events;
create trigger prevent_charlie_owner_execution_hold_events_delete
before delete on public.charlie_owner_execution_hold_events
for each row execute function public.prevent_charlie_owner_execution_hold_mutation();

alter table public.charlie_owner_execution_hold_events enable row level security;
revoke all on public.charlie_owner_execution_hold_events from public, anon, authenticated;
grant select, insert on public.charlie_owner_execution_hold_events to service_role;
revoke update, delete, truncate on public.charlie_owner_execution_hold_events from service_role;

insert into app_private.migration_log (migration_id, description)
values (
    '202607270003_create_charlie_owner_execution_holds',
    'Create append-only, generation-bound CHARLIE owner execution hold and release evidence.'
)
on conflict (migration_id) do nothing;
