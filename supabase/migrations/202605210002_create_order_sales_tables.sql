-- Phase 10.2A order/sales schema baseline.
-- Purpose: create empty business tables for the first Supabase boundary.
-- This migration imports no data and does not change the live Google Sheets-backed app.

create table if not exists public.orders (
    order_id text primary key,
    order_date timestamptz,
    customer_name text,
    customer_phone_raw text,
    customer_phone_normalized text,
    customer_channel text,
    customer_language text,
    order_source text,
    requested_category text,
    requested_weight_range text,
    requested_sex text,
    requested_quantity integer,
    quoted_total numeric(12, 2),
    final_total numeric(12, 2),
    order_status text not null default 'Draft',
    approval_status text,
    payment_status text,
    payment_method text,
    collection_method text,
    collection_location text,
    collection_date timestamptz,
    reserved_pig_count integer not null default 0,
    conversation_id text,
    notes text,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    source_sheet_row integer,
    import_batch_id text
);

create table if not exists public.sales_pricing (
    pricing_id text primary key,
    sale_category text not null,
    weight_band text not null,
    sex text,
    unit_price numeric(12, 2) not null,
    currency text not null default 'ZAR',
    effective_from timestamptz not null,
    effective_to timestamptz,
    active boolean not null default true,
    change_reason text,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    source_sheet_row integer,
    import_batch_id text
);

create table if not exists public.order_lines (
    order_line_id text primary key,
    order_id text not null references public.orders(order_id) on delete restrict,
    pig_id text,
    tag_number text,
    sale_category text,
    weight_band text,
    sex text,
    current_weight_kg numeric(10, 3),
    unit_price numeric(12, 2),
    pricing_id text references public.sales_pricing(pricing_id) on delete set null,
    line_status text not null default 'Draft',
    reserved_status text not null default 'Not_Reserved',
    request_item_key text,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    source_sheet_row integer,
    import_batch_id text
);

create table if not exists public.order_intakes (
    intake_id text primary key,
    conversation_id text not null,
    account_id text,
    contact_id text,
    customer_name text,
    customer_phone_raw text,
    customer_phone_normalized text,
    customer_channel text,
    customer_language text,
    draft_order_id text references public.orders(order_id) on delete set null,
    intake_status text not null default 'Open',
    collection_location text,
    collection_time_text text,
    collection_date date,
    collection_time time,
    payment_method text,
    quote_requested boolean not null default false,
    order_commitment boolean not null default false,
    missing_fields jsonb not null default '[]'::jsonb,
    next_action text,
    ready_for_draft boolean not null default false,
    ready_for_quote boolean not null default false,
    last_customer_message text,
    last_updated_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    closed_at timestamptz,
    closed_reason text,
    notes text,
    source_sheet_row integer,
    import_batch_id text
);

create table if not exists public.order_intake_items (
    intake_item_id text primary key,
    intake_id text not null references public.order_intakes(intake_id) on delete restrict,
    conversation_id text,
    item_key text not null,
    quantity integer,
    category text,
    weight_range text,
    sex text,
    intent_type text,
    status text not null default 'active',
    linked_order_line_ids jsonb not null default '[]'::jsonb,
    last_match_status text,
    matched_quantity integer,
    replaced_by_item_key text,
    removal_reason text,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    removed_at timestamptz,
    source_sheet_row integer,
    import_batch_id text,
    unique (intake_id, item_key)
);

create table if not exists public.order_documents (
    document_id text primary key,
    order_id text not null references public.orders(order_id) on delete restrict,
    document_type text not null,
    document_ref text not null,
    payment_ref text,
    version integer not null default 1,
    document_status text not null default 'Generated',
    payment_method text,
    vat_rate numeric(6, 4),
    subtotal_ex_vat numeric(12, 2),
    vat_amount numeric(12, 2),
    total numeric(12, 2),
    valid_until date,
    google_drive_file_id text,
    google_drive_url text,
    file_name text,
    future_storage_bucket text,
    future_storage_path text,
    created_at timestamptz not null default now(),
    created_by text,
    sent_at timestamptz,
    sent_by text,
    notes text,
    source_sheet_row integer,
    import_batch_id text,
    unique (document_ref)
);

create table if not exists public.order_status_logs (
    status_log_id text primary key,
    order_id text references public.orders(order_id) on delete set null,
    status_date timestamptz,
    old_status text,
    new_status text,
    changed_by text,
    change_source text,
    notes text,
    created_at timestamptz not null default now(),
    source_sheet_row integer,
    import_batch_id text
);

create index if not exists idx_orders_order_status on public.orders(order_status);
create index if not exists idx_orders_conversation_id on public.orders(conversation_id);
create index if not exists idx_orders_customer_phone_normalized on public.orders(customer_phone_normalized);
create index if not exists idx_orders_created_at on public.orders(created_at);

create index if not exists idx_sales_pricing_lookup on public.sales_pricing(sale_category, weight_band, sex, active, effective_from);
create index if not exists idx_sales_pricing_active on public.sales_pricing(active);

create index if not exists idx_order_lines_order_id on public.order_lines(order_id);
create index if not exists idx_order_lines_pig_id on public.order_lines(pig_id);
create index if not exists idx_order_lines_request_item_key on public.order_lines(request_item_key);
create index if not exists idx_order_lines_line_status on public.order_lines(line_status);
create index if not exists idx_order_lines_reserved_status on public.order_lines(reserved_status);

create index if not exists idx_order_intakes_conversation_id on public.order_intakes(conversation_id);
create index if not exists idx_order_intakes_draft_order_id on public.order_intakes(draft_order_id);
create index if not exists idx_order_intakes_intake_status on public.order_intakes(intake_status);

create index if not exists idx_order_intake_items_intake_id on public.order_intake_items(intake_id);
create index if not exists idx_order_intake_items_status on public.order_intake_items(status);

create index if not exists idx_order_documents_order_id on public.order_documents(order_id);
create index if not exists idx_order_documents_document_ref on public.order_documents(document_ref);
create index if not exists idx_order_documents_document_status on public.order_documents(document_status);

create index if not exists idx_order_status_logs_order_id on public.order_status_logs(order_id);
create index if not exists idx_order_status_logs_created_at on public.order_status_logs(created_at);

comment on table public.orders is 'Order headers migrated from ORDER_MASTER. Google Sheets remains live until cutover.';
comment on table public.order_lines is 'Order line and reservation state migrated from ORDER_LINES. Unit prices are historical snapshots.';
comment on table public.order_intakes is 'Sales conversation intake headers migrated from ORDER_INTAKE_STATE.';
comment on table public.order_intake_items is 'Sales conversation intake item rows migrated from ORDER_INTAKE_ITEMS.';
comment on table public.order_documents is 'Quote and invoice metadata migrated from ORDER_DOCUMENTS. PDF files remain in Google Drive initially.';
comment on table public.order_status_logs is 'Append-only order lifecycle audit trail migrated from ORDER_STATUS_LOG.';
comment on table public.sales_pricing is 'Effective-dated pricing reference migrated from SALES_PRICING.';

insert into app_private.migration_log (migration_id, description)
values (
    '202605210002_create_order_sales_tables',
    'Create empty order/sales business tables for the first Supabase migration boundary.'
)
on conflict (migration_id) do nothing;
