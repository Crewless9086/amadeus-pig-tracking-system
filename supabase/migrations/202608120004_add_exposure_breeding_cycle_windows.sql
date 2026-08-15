-- Extend the canonical mating/cycle representation for completed natural
-- exposure without fabricating an exact service or conception date.
alter table public.mating_events
    add column if not exists source_exposure_identity text,
    add column if not exists service_window_start date,
    add column if not exists service_window_end date,
    add column if not exists service_date_basis text,
    add column if not exists expected_farrowing_window_start date,
    add column if not exists expected_farrowing_window_end date;

create unique index if not exists mating_events_source_exposure_identity_uq
    on public.mating_events(source_exposure_identity)
    where source_exposure_identity is not null;

alter table public.mating_events
    drop constraint if exists mating_events_exposure_window_truth_check;
alter table public.mating_events
    add constraint mating_events_exposure_window_truth_check check (
        source_exposure_identity is null
        or (
            mating_date is null
            and service_date_basis = 'exposure_window_estimate'
            and service_window_start is not null
            and service_window_end >= service_window_start
            and expected_farrowing_date is null
            and expected_farrowing_window_start = service_window_start + 114
            and expected_farrowing_window_end = service_window_end + 114
        )
    );

comment on column public.mating_events.source_exposure_identity is
    'Completed natural exposure that created this open breeding cycle exactly once.';
comment on column public.mating_events.service_window_start is
    'Earliest supported possible service date; not an observed exact service date.';
comment on column public.mating_events.service_window_end is
    'Latest supported possible service date; not an observed exact service date.';
comment on column public.mating_events.service_date_basis is
    'Evidence basis for date precision; exposure_window_estimate never asserts exact service or conception.';

insert into app_private.migration_log(migration_id,description)
values('202608120004_add_exposure_breeding_cycle_windows',
       'Represent completed natural exposure as one canonical open breeding cycle with service and expected-farrowing windows.')
on conflict(migration_id) do nothing;
