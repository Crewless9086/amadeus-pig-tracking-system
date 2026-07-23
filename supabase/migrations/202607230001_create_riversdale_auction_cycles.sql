-- Unapplied: explicit owner approval is required before use.
-- This records only owner-confirmed auction cycles and advisory cohort snapshots.
create table if not exists public.riversdale_auction_cycles (
    auction_cycle_id text primary key,
    auction_date date not null unique,
    operating_confirmed boolean not null default false,
    owner_confirmed_by text,
    owner_confirmed_at timestamptz,
    owner_note text not null default '',
    candidate_snapshot_json jsonb not null default '[]'::jsonb,
    candidate_snapshot_hash text not null default '',
    created_at timestamptz not null default now(),
    check ((operating_confirmed = false and owner_confirmed_by is null and owner_confirmed_at is null)
        or (operating_confirmed = true and owner_confirmed_by is not null and owner_confirmed_at is not null))
);
alter table public.riversdale_auction_cycles enable row level security;

-- This is the canonical one-pig/one-active-outlet rail. Every future protected
-- outlet writer (customer sale, reservation, auction, meat, breeding, health
-- hold, or keep-growing) must claim this row in the same transaction as its
-- own domain record. The partial unique index is the durable fail-closed
-- boundary: an animal cannot have two active outlet claims.
create table if not exists public.pig_active_outlets (
    outlet_assignment_id text primary key,
    pig_id text not null,
    outlet_type text not null check (outlet_type in (
        'customer_sale', 'reservation', 'riversdale_auction', 'meat',
        'breeding', 'health_hold', 'keep_growing', 'abattoir'
    )),
    source_record_id text not null,
    active boolean not null default true,
    evidence_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    released_at timestamptz,
    check ((active = true and released_at is null) or (active = false and released_at is not null)),
    unique (outlet_assignment_id, pig_id)
);
create unique index if not exists pig_active_outlets_one_active_pig_unique
    on public.pig_active_outlets (pig_id) where active;
alter table public.pig_active_outlets enable row level security;

-- Advisory membership is distinct from a reservation or sale. Each member is
-- bound to the canonical active-outlet claim when an owner-approved execution
-- rail is introduced; this advisory build itself does not insert either row.
create table if not exists public.riversdale_auction_cohort_members (
    auction_cycle_id text not null references public.riversdale_auction_cycles(auction_cycle_id),
    pig_id text not null,
    outlet_assignment_id text not null unique,
    active boolean not null default true,
    evidence_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    primary key (auction_cycle_id, pig_id),
    foreign key (outlet_assignment_id, pig_id)
        references public.pig_active_outlets(outlet_assignment_id, pig_id)
);
create unique index if not exists riversdale_auction_active_cohort_pig_unique
    on public.riversdale_auction_cohort_members (pig_id) where active;
alter table public.riversdale_auction_cohort_members enable row level security;

create or replace function app_private.enforce_riversdale_auction_cycle_integrity()
returns trigger language plpgsql as $$
begin
    if new.auction_cycle_id is distinct from old.auction_cycle_id
       or new.auction_date is distinct from old.auction_date
       or new.created_at is distinct from old.created_at then
        raise exception 'riversdale auction cycle identity is immutable';
    end if;
    if old.operating_confirmed and new.operating_confirmed is distinct from true then
        raise exception 'confirmed auction cycle cannot be reverted';
    end if;
    return new;
end;
$$;
create trigger riversdale_auction_cycle_integrity before update on public.riversdale_auction_cycles
for each row execute function app_private.enforce_riversdale_auction_cycle_integrity();

insert into app_private.migration_log (migration_id, description)
values ('202607230001_create_riversdale_auction_cycles', 'Create owner-confirmed advisory Riversdale auction cycle rail.')
on conflict (migration_id) do nothing;
