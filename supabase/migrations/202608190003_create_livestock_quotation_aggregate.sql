-- One intake-linked quotation aggregate; no allocation, reservation or order side effects.
create table if not exists public.livestock_quotations (
    quotation_id text primary key,
    intake_id text references public.order_intakes(intake_id) on delete restrict,
    customer_request_id text,
    journey text not null check (journey in ('budgetary_quotation', 'sales_quotation')),
    quotation_basis text,
    status text not null check (status in ('issued', 'superseded', 'expired', 'voided')),
    issued_at timestamptz not null,
    valid_until date not null,
    issued_by text not null,
    supersedes_quotation_id text references public.livestock_quotations(quotation_id) on delete restrict,
    superseded_by_quotation_id text references public.livestock_quotations(quotation_id) on delete restrict,
    requested_items_snapshot jsonb not null,
    totals_snapshot jsonb not null,
    price_snapshot_digest text not null,
    issue_digest text not null unique,
    document_id text references public.order_documents(document_id) on delete set null,
    created_at timestamptz not null default now(),
    check ((journey = 'sales_quotation' and quotation_basis = 'current_availability')
        or (journey = 'budgetary_quotation' and quotation_basis is null))
);

create table if not exists public.livestock_quotation_lines (
    quotation_line_id text primary key,
    quotation_id text not null references public.livestock_quotations(quotation_id) on delete restrict,
    request_item_key text not null,
    category text not null,
    weight_range text not null,
    sex text,
    quantity integer not null check (quantity > 0),
    unit_price numeric(12,2) not null check (unit_price >= 0),
    subtotal numeric(12,2) not null check (subtotal >= 0),
    currency text not null default 'ZAR',
    pricing_id text references public.sales_pricing(pricing_id) on delete restrict,
    price_effective_from timestamptz,
    price_effective_to timestamptz,
    price_source text,
    created_at timestamptz not null default now(),
    unique (quotation_id, request_item_key)
);

create index if not exists idx_livestock_quotations_intake on public.livestock_quotations(intake_id, issued_at desc);
create index if not exists idx_livestock_quotations_status on public.livestock_quotations(status, valid_until);

comment on table public.livestock_quotations is 'Immutable issue-time livestock quotation snapshots. Allocation, reservation and orders are separate aggregates.';
comment on table public.livestock_quotation_lines is 'Immutable price snapshots resolved from effective-dated canonical sales_pricing at issue time.';

create or replace function public.guard_livestock_quotation_snapshot()
returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'Issued livestock quotation snapshots cannot be deleted';
    end if;
    if old.journey is distinct from new.journey
       or old.quotation_basis is distinct from new.quotation_basis
       or old.issued_at is distinct from new.issued_at
       or old.valid_until is distinct from new.valid_until
       or old.requested_items_snapshot is distinct from new.requested_items_snapshot
       or old.totals_snapshot is distinct from new.totals_snapshot
       or old.price_snapshot_digest is distinct from new.price_snapshot_digest
       or old.issue_digest is distinct from new.issue_digest then
        raise exception 'Issued livestock quotation content is immutable; create a superseding quotation';
    end if;
    return new;
end $$;

drop trigger if exists trg_guard_livestock_quotation_snapshot on public.livestock_quotations;
create trigger trg_guard_livestock_quotation_snapshot
before update or delete on public.livestock_quotations
for each row execute function public.guard_livestock_quotation_snapshot();

create or replace function public.reject_livestock_quotation_line_mutation()
returns trigger language plpgsql as $$
begin
    raise exception 'Livestock quotation price snapshots are immutable; create a superseding quotation';
end $$;

drop trigger if exists trg_reject_livestock_quotation_line_mutation on public.livestock_quotation_lines;
create trigger trg_reject_livestock_quotation_line_mutation
before update or delete on public.livestock_quotation_lines
for each row execute function public.reject_livestock_quotation_line_mutation();

insert into app_private.migration_log (migration_id, description)
values ('202608190003_create_livestock_quotation_aggregate', 'Create the intake-linked three-journey livestock quotation aggregate and immutable price snapshots.')
on conflict (migration_id) do nothing;
