-- Unapplied: explicit owner approval is required before use.
-- This records only owner-confirmed auction cycles and advisory cohort snapshots.
create table if not exists public.riversdale_auction_cycles (
    auction_cycle_id text primary key,
    auction_date date,
    operating_confirmed boolean not null,
    decision_status text not null check (decision_status in ('confirmed_operating', 'confirmed_not_operating')),
    owner_confirmed_by text not null,
    owner_confirmed_at timestamptz not null,
    location text not null default '',
    organizer_details text not null default '',
    entry_deadline date,
    commission_percent numeric(7,4) check (commission_percent is null or commission_percent >= 0),
    auction_fees numeric(14,2) check (auction_fees is null or auction_fees >= 0),
    transport_estimate numeric(14,2) check (transport_estimate is null or transport_estimate >= 0),
    currency text not null default 'ZAR',
    owner_note text not null default '',
    idempotency_key text not null unique,
    decision_hash text not null check (length(decision_hash) = 64),
    candidate_snapshot_json jsonb not null default '[]'::jsonb,
    candidate_snapshot_hash text not null default '',
    created_at timestamptz not null default now(),
    check ((operating_confirmed and decision_status = 'confirmed_operating' and auction_date is not null)
        or (not operating_confirmed and decision_status = 'confirmed_not_operating'))
);
alter table public.riversdale_auction_cycles enable row level security;
revoke all privileges on table public.riversdale_auction_cycles from public;
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on public.riversdale_auction_cycles from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on public.riversdale_auction_cycles from authenticated;
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        grant select, insert on public.riversdale_auction_cycles to service_role;
    end if;
end;
$$;

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
revoke all privileges on table public.pig_active_outlets from public;

-- Keep the canonical claim rail aligned with the existing protected Supabase
-- writers.  These triggers are deliberately database-side so a writer cannot
-- create its domain record and then fail open before making the outlet claim.
-- A legacy Sheets fallback is not a canonical protected writer and must not be
-- represented as an active claim without a separately approved cutover.
create or replace function app_private.claim_pig_active_outlet(
    p_assignment_id text,
    p_pig_id text,
    p_outlet_type text,
    p_source_record_id text,
    p_evidence jsonb default '{}'::jsonb
)
returns void language plpgsql as $$
begin
    if coalesce(trim(p_pig_id), '') = '' then
        return;
    end if;
    insert into public.pig_active_outlets (
        outlet_assignment_id, pig_id, outlet_type, source_record_id, active,
        evidence_json, released_at
    ) values (
        p_assignment_id, p_pig_id, p_outlet_type, p_source_record_id, true,
        coalesce(p_evidence, '{}'::jsonb), null
    )
    on conflict (outlet_assignment_id) do update set
        pig_id = excluded.pig_id,
        outlet_type = excluded.outlet_type,
        source_record_id = excluded.source_record_id,
        active = true,
        evidence_json = excluded.evidence_json,
        released_at = null;
end;
$$;

create or replace function app_private.release_pig_active_outlet(p_assignment_id text)
returns void language plpgsql as $$
begin
    update public.pig_active_outlets
    set active = false, released_at = now()
    where outlet_assignment_id = p_assignment_id and active;
end;
$$;

create or replace function app_private.sync_order_line_active_outlet()
returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        perform app_private.release_pig_active_outlet('reservation:' || old.order_line_id);
        return old;
    end if;
    if new.reserved_status = 'Reserved' or new.line_status = 'Reserved' then
        perform app_private.claim_pig_active_outlet(
            'reservation:' || new.order_line_id, new.pig_id, 'reservation',
            new.order_line_id,
            jsonb_build_object('writer', 'public.order_lines', 'order_id', new.order_id)
        );
    else
        perform app_private.release_pig_active_outlet('reservation:' || new.order_line_id);
    end if;
    return new;
end;
$$;

create or replace function app_private.sync_sales_transaction_item_active_outlet()
returns trigger language plpgsql as $$
declare
    v_stream text;
    v_status text;
    v_outlet text;
begin
    if tg_op = 'DELETE' then
        perform app_private.release_pig_active_outlet('sale:' || old.sale_item_id);
        return old;
    end if;
    select sale_stream, sale_status into v_stream, v_status
    from public.sales_transactions where sale_id = new.sale_id;
    if new.pig_id is null or coalesce(trim(new.pig_id), '') = '' or v_status = 'Cancelled' then
        perform app_private.release_pig_active_outlet('sale:' || new.sale_item_id);
        return new;
    end if;
    v_outlet := case v_stream
        when 'Slaughter' then 'abattoir'
        when 'Meat' then 'meat'
        else 'customer_sale'
    end;
    -- A completed sale supersedes its own order-line reservation in this same
    -- transaction; a different outlet claim still fails at the unique index.
    if new.order_line_id is not null then
        perform app_private.release_pig_active_outlet('reservation:' || new.order_line_id);
    end if;
    perform app_private.claim_pig_active_outlet(
        'sale:' || new.sale_item_id, new.pig_id, v_outlet, new.sale_id,
        jsonb_build_object('writer', 'public.sales_transaction_items', 'sale_id', new.sale_id)
    );
    return new;
end;
$$;

create or replace function app_private.release_cancelled_sales_transaction_outlets()
returns trigger language plpgsql as $$
begin
    if new.sale_status = 'Cancelled' and old.sale_status is distinct from 'Cancelled' then
        update public.pig_active_outlets
        set active = false, released_at = now()
        where active and evidence_json ->> 'sale_id' = new.sale_id;
    end if;
    return new;
end;
$$;

create or replace function app_private.sync_meat_batch_pig_active_outlet()
returns trigger language plpgsql as $$
declare
    v_status text;
begin
    if tg_op = 'DELETE' then
        perform app_private.release_pig_active_outlet('meat:' || old.batch_pig_id);
        return old;
    end if;
    select status into v_status from public.meat_processing_batches where batch_id = new.batch_id;
    if v_status = 'Cancelled' then
        perform app_private.release_pig_active_outlet('meat:' || new.batch_pig_id);
        return new;
    end if;
    perform app_private.claim_pig_active_outlet(
        'meat:' || new.batch_pig_id, new.pig_id, 'meat', new.batch_id,
        jsonb_build_object('writer', 'public.meat_processing_batch_pigs', 'batch_id', new.batch_id)
    );
    return new;
end;
$$;

do $$
begin
    if to_regclass('public.order_lines') is not null then
        execute 'create trigger pig_active_outlet_from_order_line after insert or update or delete on public.order_lines for each row execute function app_private.sync_order_line_active_outlet()';
    end if;
    if to_regclass('public.sales_transaction_items') is not null then
        execute 'create trigger pig_active_outlet_from_sales_item after insert or update or delete on public.sales_transaction_items for each row execute function app_private.sync_sales_transaction_item_active_outlet()';
    end if;
    if to_regclass('public.sales_transactions') is not null then
        execute 'create trigger pig_active_outlet_from_sales_header after update of sale_status on public.sales_transactions for each row execute function app_private.release_cancelled_sales_transaction_outlets()';
    end if;
    if to_regclass('public.meat_processing_batch_pigs') is not null then
        execute 'create trigger pig_active_outlet_from_meat_batch after insert or update or delete on public.meat_processing_batch_pigs for each row execute function app_private.sync_meat_batch_pig_active_outlet()';
    end if;
end;
$$;

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
revoke all privileges on table public.riversdale_auction_cohort_members from public;

create or replace function app_private.enforce_riversdale_auction_cycle_integrity()
returns trigger language plpgsql as $$
begin
    raise exception 'riversdale auction decisions are append-only';
end;
$$;
create trigger riversdale_auction_cycle_integrity before update or delete on public.riversdale_auction_cycles
for each row execute function app_private.enforce_riversdale_auction_cycle_integrity();

-- Supabase client roles and PostgreSQL PUBLIC have no direct mutation path.
-- The server service role is the only database principal used by the guarded
-- owner-admin route and by existing protected domain writers.
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all privileges on table public.pig_active_outlets from anon;
        revoke all privileges on table public.riversdale_auction_cohort_members from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all privileges on table public.pig_active_outlets from authenticated;
        revoke all privileges on table public.riversdale_auction_cohort_members from authenticated;
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        revoke all privileges on table public.riversdale_auction_cycles from service_role;
        revoke all privileges on table public.pig_active_outlets from service_role;
        revoke all privileges on table public.riversdale_auction_cohort_members from service_role;
        grant select, insert on table public.riversdale_auction_cycles to service_role;
        grant select, insert, update on table public.pig_active_outlets to service_role;
        grant select, insert, update on table public.riversdale_auction_cohort_members to service_role;
    end if;
end;
$$;

revoke all privileges on function app_private.claim_pig_active_outlet(text, text, text, text, jsonb)
    from public;
revoke all privileges on function app_private.release_pig_active_outlet(text)
    from public;
revoke all privileges on function app_private.sync_order_line_active_outlet()
    from public;
revoke all privileges on function app_private.sync_sales_transaction_item_active_outlet()
    from public;
revoke all privileges on function app_private.release_cancelled_sales_transaction_outlets()
    from public;
revoke all privileges on function app_private.sync_meat_batch_pig_active_outlet()
    from public;
revoke all privileges on function app_private.enforce_riversdale_auction_cycle_integrity()
    from public;

do $$
declare
    role_name text;
begin
    foreach role_name in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = role_name) then
            execute format(
                'revoke all privileges on function app_private.claim_pig_active_outlet(text, text, text, text, jsonb) from %I',
                role_name
            );
            execute format(
                'revoke all privileges on function app_private.release_pig_active_outlet(text) from %I',
                role_name
            );
            execute format(
                'revoke all privileges on function app_private.sync_order_line_active_outlet() from %I',
                role_name
            );
            execute format(
                'revoke all privileges on function app_private.sync_sales_transaction_item_active_outlet() from %I',
                role_name
            );
            execute format(
                'revoke all privileges on function app_private.release_cancelled_sales_transaction_outlets() from %I',
                role_name
            );
            execute format(
                'revoke all privileges on function app_private.sync_meat_batch_pig_active_outlet() from %I',
                role_name
            );
            execute format(
                'revoke all privileges on function app_private.enforce_riversdale_auction_cycle_integrity() from %I',
                role_name
            );
        end if;
    end loop;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        grant execute on function app_private.claim_pig_active_outlet(text, text, text, text, jsonb)
            to service_role;
        grant execute on function app_private.release_pig_active_outlet(text)
            to service_role;
    end if;
end;
$$;

insert into app_private.migration_log (migration_id, description)
values ('202607230001_create_riversdale_auction_cycles', 'Create owner-confirmed advisory Riversdale auction cycle rail.')
on conflict (migration_id) do nothing;
