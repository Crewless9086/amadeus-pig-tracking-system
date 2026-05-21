-- Phase 10.2H sales transaction schema extension.
-- Purpose: create empty transaction tables for livestock, slaughter, and future meat/carcass sales.
-- This migration imports no data and does not change the live Google Sheets-backed app.

create table if not exists public.sales_transactions (
    sale_id text primary key,
    sale_date timestamptz not null,
    sale_stream text not null check (sale_stream in ('Livestock', 'Slaughter', 'Meat')),
    buyer_name text,
    buyer_phone_raw text,
    buyer_phone_normalized text,
    destination text,
    linked_order_id text references public.orders(order_id) on delete set null,
    pig_count integer not null default 0 check (pig_count >= 0),
    gross_total numeric(12, 2),
    deductions_total numeric(12, 2) not null default 0,
    net_total numeric(12, 2),
    currency text not null default 'ZAR',
    payment_status text not null default 'Unpaid' check (
        payment_status in ('Unpaid', 'Deposit_Paid', 'Part_Paid', 'Paid', 'Cancelled')
    ),
    payment_method text,
    sale_status text not null default 'Draft' check (
        sale_status in ('Draft', 'Confirmed', 'Completed', 'Cancelled')
    ),
    notes text,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    source_sheet_row integer,
    import_batch_id text
);

create table if not exists public.sales_transaction_items (
    sale_item_id text primary key,
    sale_id text not null references public.sales_transactions(sale_id) on delete restrict,
    item_type text not null default 'Pig' check (item_type in ('Pig', 'Carcass', 'Cut', 'Box', 'Other')),
    pig_id text,
    tag_number text,
    order_line_id text references public.order_lines(order_line_id) on delete set null,
    description text,
    quantity numeric(12, 3) not null default 1 check (quantity >= 0),
    live_weight_kg numeric(10, 3),
    carcass_weight_kg numeric(10, 3),
    packed_weight_kg numeric(10, 3),
    unit_price numeric(12, 2),
    pricing_basis text check (
        pricing_basis is null
        or pricing_basis in ('Per_Pig', 'Per_Kg_Live', 'Per_Kg_Carcass', 'Per_Kg_Packed', 'Per_Item')
    ),
    line_total numeric(12, 2),
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_sales_transactions_sale_date on public.sales_transactions(sale_date);
create index if not exists idx_sales_transactions_sale_stream on public.sales_transactions(sale_stream);
create index if not exists idx_sales_transactions_sale_status on public.sales_transactions(sale_status);
create index if not exists idx_sales_transactions_payment_status on public.sales_transactions(payment_status);
create index if not exists idx_sales_transactions_linked_order_id on public.sales_transactions(linked_order_id);
create index if not exists idx_sales_transactions_buyer_phone_normalized on public.sales_transactions(buyer_phone_normalized);

create index if not exists idx_sales_transaction_items_sale_id on public.sales_transaction_items(sale_id);
create index if not exists idx_sales_transaction_items_pig_id on public.sales_transaction_items(pig_id);
create index if not exists idx_sales_transaction_items_order_line_id on public.sales_transaction_items(order_line_id);
create index if not exists idx_sales_transaction_items_item_type on public.sales_transaction_items(item_type);

comment on table public.sales_transactions is 'Sale transaction headers for livestock, slaughter/abattoir, and future meat/carcass sales. Google Sheets remains live until cutover.';
comment on table public.sales_transaction_items is 'Sale transaction item rows linking pigs/order lines/products, weights, pricing basis, and line totals.';

insert into app_private.migration_log (migration_id, description)
values (
    '202605210003_create_sales_transaction_tables',
    'Create empty sales transaction tables for livestock, slaughter, and future meat/carcass sales.'
)
on conflict (migration_id) do nothing;
