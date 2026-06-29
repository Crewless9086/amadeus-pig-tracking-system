-- GS-MIG-9 litter and piglet lifecycle cutover support.
--
-- Additive only. Adds canonical fields needed by existing litter/piglet
-- lifecycle workflows before their write path can prefer Supabase.

alter table public.pigs
    add column if not exists litter_size_born integer,
    add column if not exists litter_size_weaned integer,
    add column if not exists wean_date date,
    add column if not exists wean_weight_kg numeric(10,3),
    add column if not exists earmarked boolean,
    add column if not exists earmark_date date;

alter table public.litters
    add column if not exists wean_date date;

create index if not exists pigs_litter_id_idx on public.pigs(litter_id);
create index if not exists pigs_wean_date_idx on public.pigs(wean_date);
create index if not exists litters_wean_date_idx on public.litters(wean_date);

create or replace view public.pig_current_state as
select
    pig.pig_id,
    pig.tag_number,
    pig.pig_name,
    pig.status,
    pig.on_farm,
    pig.animal_type,
    pig.sex,
    pig.date_of_birth,
    pig.litter_id,
    pig.purpose,
    latest_weight.weight_kg as current_weight_kg,
    latest_weight.weight_date as last_weight_date,
    coalesce(latest_location.to_pen_id, pig.initial_pen_id) as current_pen_id,
    pen.pen_name as current_pen_name,
    pig.wean_date,
    pig.wean_weight_kg,
    pig.litter_size_born,
    pig.litter_size_weaned
from public.pigs pig
left join public.pig_latest_weight_events latest_weight on latest_weight.pig_id = pig.pig_id
left join public.pig_latest_location_events latest_location on latest_location.pig_id = pig.pig_id
left join public.pens pen on pen.pen_id = coalesce(latest_location.to_pen_id, pig.initial_pen_id);

insert into app_private.migration_log (migration_id, description)
values (
    '202606290003_add_litter_lifecycle_fields',
    'Add canonical litter lifecycle fields for Supabase-first piglet/litter workflows'
)
on conflict (migration_id) do nothing;
