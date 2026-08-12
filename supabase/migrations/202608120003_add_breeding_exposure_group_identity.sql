alter table public.pig_breeding_exposure_events
    add column if not exists exposure_group_identity text;

alter table public.pig_breeding_exposure_events
    drop constraint if exists pig_breeding_exposure_started_group_required;
alter table public.pig_breeding_exposure_events
    add constraint pig_breeding_exposure_started_group_required check (
        event_kind <> 'started' or btrim(coalesce(exposure_group_identity, '')) <> ''
    ) not valid;

create index if not exists pig_breeding_exposure_group_chronology_idx
    on public.pig_breeding_exposure_events(exposure_group_identity, occurred_on, exposure_event_id)
    where exposure_group_identity is not null;

insert into app_private.migration_log(migration_id,description)
values('202608120003_add_breeding_exposure_group_identity',
       'Bind individual natural-exposure starts to one governed shared group identity.')
on conflict(migration_id) do nothing;
