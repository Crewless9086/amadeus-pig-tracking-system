-- GS-MIG-1 canonical farm schema.
--
-- Additive only. This migration creates empty canonical farm tables and
-- read-only views needed to move operational pig data away from Google Sheets.
-- It imports no data and changes no existing production records.

create table if not exists public.pens (
    pen_id text primary key,
    pen_name text,
    pen_type text,
    capacity integer,
    is_active boolean not null default true,
    pen_notes text,
    source_sheet_row integer,
    import_batch_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.pigs (
    pig_id text primary key,
    tag_number text,
    pig_name text,
    status text,
    on_farm boolean,
    animal_type text,
    sex text,
    date_of_birth date,
    birth_month text,
    birth_year integer,
    breed_type text,
    colour_markings text,
    mother_pig_id text,
    father_pig_id text,
    litter_id text,
    initial_pen_id text,
    purpose text,
    notes text,
    source_sheet_row integer,
    import_batch_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.farm_products (
    product_id text primary key,
    product_name text,
    product_category text,
    default_dose text,
    dose_unit text,
    default_withdrawal_days integer,
    supplier text,
    batch_tracking_required boolean not null default false,
    is_active boolean not null default true,
    product_notes text,
    source_sheet_row integer,
    import_batch_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.app_settings (
    setting_key text primary key,
    setting_value text,
    description text,
    source_sheet_row integer,
    import_batch_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.pig_weight_events (
    weight_event_id text primary key,
    pig_id text not null references public.pigs(pig_id),
    weight_date date not null,
    weight_kg numeric not null check (weight_kg > 0),
    weighed_by text,
    scale_used text,
    condition_notes text,
    stage_at_weighing text,
    source text not null default 'google_sheets_import',
    source_sheet_row integer,
    import_batch_id text,
    bulk_batch_id uuid references public.bulk_weight_batches(batch_id),
    bulk_row_id uuid references public.bulk_weight_batch_rows(row_id),
    created_at timestamptz not null default now(),
    unique (pig_id, weight_date, source, source_sheet_row)
);

create table if not exists public.pig_location_events (
    location_event_id text primary key,
    pig_id text not null references public.pigs(pig_id),
    move_date date not null,
    from_pen_id text references public.pens(pen_id),
    to_pen_id text references public.pens(pen_id),
    reason_for_move text,
    moved_by text,
    group_batch_id text,
    move_notes text,
    source text not null default 'google_sheets_import',
    source_sheet_row integer,
    import_batch_id text,
    bulk_batch_id uuid references public.bulk_weight_batches(batch_id),
    bulk_row_id uuid references public.bulk_weight_batch_rows(row_id),
    created_at timestamptz not null default now(),
    unique (pig_id, move_date, from_pen_id, to_pen_id, source, source_sheet_row)
);

create table if not exists public.pig_medical_events (
    medical_event_id text primary key,
    pig_id text not null references public.pigs(pig_id),
    treatment_date date not null,
    treatment_type text,
    product_id text references public.farm_products(product_id),
    product_name text,
    dose text,
    dose_unit text,
    route text,
    reason_for_treatment text,
    batch_lot_number text,
    withdrawal_days integer,
    withdrawal_end_date date,
    given_by text,
    follow_up_required boolean not null default false,
    follow_up_date date,
    medical_notes text,
    source_sheet_row integer,
    import_batch_id text,
    created_at timestamptz not null default now()
);

create table if not exists public.litters (
    litter_id text primary key,
    farrowing_date date,
    sow_pig_id text references public.pigs(pig_id),
    boar_pig_id text references public.pigs(pig_id),
    sow_tag_number text,
    boar_tag_number text,
    total_born integer,
    born_alive integer,
    stillborn_count integer,
    mummified_count integer,
    male_count integer,
    female_count integer,
    unknown_sex_count integer,
    weaned_count integer,
    litter_status text,
    litter_notes text,
    source_sheet_row integer,
    import_batch_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.mating_events (
    mating_id text primary key,
    sow_pig_id text references public.pigs(pig_id),
    sow_tag_number text,
    boar_pig_id text references public.pigs(pig_id),
    boar_tag_number text,
    mating_date date,
    mating_method text,
    exposure_group text,
    expected_pregnancy_check_date date,
    pregnancy_check_date date,
    pregnancy_check_result text,
    expected_farrowing_date date,
    farrowing_date date,
    outcome text,
    related_litter_id text references public.litters(litter_id),
    mating_notes text,
    source_sheet_row integer,
    import_batch_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists pigs_status_idx on public.pigs(status);
create index if not exists pigs_on_farm_idx on public.pigs(on_farm);
create index if not exists pigs_tag_number_idx on public.pigs(tag_number);
create index if not exists pens_is_active_idx on public.pens(is_active);
create index if not exists pig_weight_events_pig_date_idx on public.pig_weight_events(pig_id, weight_date desc);
create index if not exists pig_location_events_pig_date_idx on public.pig_location_events(pig_id, move_date desc);
create index if not exists pig_location_events_to_pen_idx on public.pig_location_events(to_pen_id);
create index if not exists pig_medical_events_pig_date_idx on public.pig_medical_events(pig_id, treatment_date desc);
create index if not exists litters_farrowing_date_idx on public.litters(farrowing_date desc);
create index if not exists mating_events_sow_date_idx on public.mating_events(sow_pig_id, mating_date desc);

create or replace view public.pig_latest_weight_events as
select *
from (
    select
        weight_event.*,
        row_number() over (
            partition by weight_event.pig_id
            order by weight_event.weight_date desc, weight_event.created_at desc, weight_event.weight_event_id desc
        ) as latest_rank
    from public.pig_weight_events weight_event
) ranked_weights
where latest_rank = 1;

create or replace view public.pig_latest_location_events as
select *
from (
    select
        location_event.*,
        row_number() over (
            partition by location_event.pig_id
            order by location_event.move_date desc, location_event.created_at desc, location_event.location_event_id desc
        ) as latest_rank
    from public.pig_location_events location_event
) ranked_locations
where latest_rank = 1;

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
    pen.pen_name as current_pen_name
from public.pigs pig
left join public.pig_latest_weight_events latest_weight on latest_weight.pig_id = pig.pig_id
left join public.pig_latest_location_events latest_location on latest_location.pig_id = pig.pig_id
left join public.pens pen on pen.pen_id = coalesce(latest_location.to_pen_id, pig.initial_pen_id);

alter table public.pens enable row level security;
alter table public.pigs enable row level security;
alter table public.farm_products enable row level security;
alter table public.app_settings enable row level security;
alter table public.pig_weight_events enable row level security;
alter table public.pig_location_events enable row level security;
alter table public.pig_medical_events enable row level security;
alter table public.litters enable row level security;
alter table public.mating_events enable row level security;

insert into app_private.migration_log (migration_id, description)
values (
    '202606290001_create_farm_canonical_tables',
    'Create canonical farm tables for Google Sheets to Supabase migration dry-run and future cutover'
)
on conflict (migration_id) do nothing;
