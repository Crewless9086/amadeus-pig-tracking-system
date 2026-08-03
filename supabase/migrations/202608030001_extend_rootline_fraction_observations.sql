alter table public.rootline_tank_observations
    add column storage_fraction_numerator integer,
    add column storage_fraction_denominator integer,
    add column reservoir_fraction_numerator integer,
    add column reservoir_fraction_denominator integer,
    add column provider_message_id text;

do $$ declare constraint_name text;
begin
  select c.conname into constraint_name
    from pg_constraint c
   where c.conrelid='public.rootline_tank_observations'::regclass
     and c.contype='c'
     and pg_get_constraintdef(c.oid) like '%storage_reported_count IS NOT NULL%reservoir_reported_count IS NOT NULL%';
  if constraint_name is not null then
    execute format('alter table public.rootline_tank_observations drop constraint %I',constraint_name);
  end if;
end $$;

alter table public.rootline_tank_observations
    add constraint rootline_tank_observation_value_required check (
      storage_reported_count is not null or reservoir_reported_count is not null
      or storage_fraction_numerator is not null or reservoir_fraction_numerator is not null),
    add constraint rootline_storage_fraction_valid check (
      (storage_fraction_numerator is null) = (storage_fraction_denominator is null)
      and (storage_fraction_numerator is null or
           (storage_fraction_denominator > 0 and storage_fraction_numerator between 0 and storage_fraction_denominator))),
    add constraint rootline_reservoir_fraction_valid check (
      (reservoir_fraction_numerator is null) = (reservoir_fraction_denominator is null)
      and (reservoir_fraction_numerator is null or
           (reservoir_fraction_denominator > 0 and reservoir_fraction_numerator between 0 and reservoir_fraction_denominator))),
    add constraint rootline_fraction_provider_required check (
      (storage_fraction_numerator is null and reservoir_fraction_numerator is null)
      or (provider_message_id is not null and btrim(provider_message_id) <> ''));

insert into app_private.migration_log (migration_id,description)
values ('202608030001_extend_rootline_fraction_observations',
        'Preserve provider-bound owner tank fractions without converting them to fixed tank counts.')
on conflict (migration_id) do nothing;
