alter table public.mating_events
    add column if not exists breeding_cycle_state text,
    add column if not exists exposure_group_identity text,
    add column if not exists exposure_planned_removal_on date,
    add column if not exists exposure_actual_removal_on date;

alter table public.mating_events drop constraint if exists mating_events_breeding_cycle_state_check;
alter table public.mating_events add constraint mating_events_breeding_cycle_state_check check (
    source_exposure_identity is null or (
        breeding_cycle_state in ('Exposure Active','Exposure Complete')
        and service_window_end >= service_window_start
        and exposure_planned_removal_on >= service_window_start
        and (
            (breeding_cycle_state = 'Exposure Active'
                and exposure_actual_removal_on is null
                and exposure_planned_removal_on = service_window_end)
            or (breeding_cycle_state = 'Exposure Complete'
                and exposure_actual_removal_on is not null
                and exposure_actual_removal_on >= service_window_start
                and exposure_actual_removal_on = service_window_end)
        )
    )
) not valid;

create unique index if not exists mating_events_one_active_exposure_cycle_per_sow_uq
    on public.mating_events(sow_pig_id)
    where source_exposure_identity is not null and breeding_cycle_state='Exposure Active';

comment on column public.mating_events.breeding_cycle_state is
    'Exposure Active from physical IN; Exposure Complete after attributable physical UIT.';
comment on column public.mating_events.exposure_planned_removal_on is
    'Planned UIT used for the provisional service/farrowing window while exposure is active.';
comment on column public.mating_events.exposure_actual_removal_on is
    'Attributable actual UIT; NULL while animals remain together.';

-- Existing exposure-linked rows are not silently classified. The governed
-- correction/update path supplies attributable IN/UIT evidence first; a later
-- migration may validate the constraint once legacy coverage is complete.

insert into app_private.migration_log(migration_id,description)
values('202608120005_add_active_exposure_cycle_state',
       'Create exposure-linked breeding cycles at IN and complete the same cycle at UIT.')
on conflict(migration_id) do nothing;
