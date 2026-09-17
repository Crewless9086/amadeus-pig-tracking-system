-- Internal/customer meat production traceability and pilot costing.
-- Production batches are operational records, not customer sales or revenue.

create table if not exists public.meat_processing_batches (
    batch_id text primary key,
    batch_code text not null unique,
    batch_kind text not null check (batch_kind in ('Internal_Pilot', 'Customer_Order', 'Stock_Production')),
    status text not null check (status in (
        'Planned', 'Selected', 'Sent_To_Abattoir', 'Carcass_Received',
        'At_Butcher', 'Cutting', 'Packed', 'Completed', 'Cancelled'
    )),
    intended_disposition text not null check (intended_disposition in ('Internal_Use', 'Customer_Sale', 'Stock')),
    abattoir_name text,
    butcher_name text,
    slaughter_date date,
    butcher_date date,
    notes text,
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.meat_processing_batch_pigs (
    batch_pig_id text primary key,
    batch_id text not null references public.meat_processing_batches(batch_id) on delete restrict,
    pig_id text not null references public.pigs(pig_id) on delete restrict,
    tag_number text,
    live_weight_kg numeric(10, 3),
    carcass_weight_kg numeric(10, 3),
    head_included boolean not null default false,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (batch_id, pig_id)
);

create table if not exists public.meat_processing_batch_events (
    event_id text primary key,
    batch_id text not null references public.meat_processing_batches(batch_id) on delete restrict,
    pig_id text references public.pigs(pig_id) on delete restrict,
    event_type text not null check (event_type in (
        'batch_created', 'pig_selected', 'departed_farm', 'arrived_abattoir',
        'slaughtered', 'carcass_weighed', 'delivered_to_butcher',
        'cutting_started', 'packed', 'completed', 'note'
    )),
    event_date date not null,
    location_label text,
    notes text,
    metadata_json jsonb not null default '{}'::jsonb,
    recorded_by text not null,
    created_at timestamptz not null default now()
);

create table if not exists public.meat_processing_batch_costs (
    cost_id text primary key,
    batch_id text not null references public.meat_processing_batches(batch_id) on delete restrict,
    cost_type text not null check (cost_type in (
        'Pig_Production', 'Transport', 'Abattoir', 'Butchery',
        'Packaging', 'Cold_Storage', 'Labour', 'Other'
    )),
    supplier_name text,
    amount numeric(12, 2) not null check (amount >= 0),
    cost_date date not null,
    notes text,
    recorded_by text not null,
    created_at timestamptz not null default now()
);

create table if not exists public.meat_processing_batch_outputs (
    output_id text primary key,
    batch_id text not null references public.meat_processing_batches(batch_id) on delete restrict,
    output_type text not null check (output_type in ('Cut', 'Offal', 'Bone', 'Fat', 'Head', 'Waste', 'Other')),
    cut_name text not null,
    pack_count integer not null default 0 check (pack_count >= 0),
    weight_kg numeric(10, 3) not null check (weight_kg >= 0),
    counts_toward_packed_yield boolean not null default true,
    disposition text not null check (disposition in ('Internal_Use', 'Frozen', 'Sample', 'Sold', 'Waste', 'Other')),
    notes text,
    recorded_by text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_meat_processing_batches_status
    on public.meat_processing_batches(status, updated_at desc);
create index if not exists idx_meat_processing_batch_pigs_pig
    on public.meat_processing_batch_pigs(pig_id, created_at desc);
create index if not exists idx_meat_processing_batch_events_batch
    on public.meat_processing_batch_events(batch_id, event_date, created_at);
create index if not exists idx_meat_processing_batch_costs_batch
    on public.meat_processing_batch_costs(batch_id, cost_date, created_at);
create index if not exists idx_meat_processing_batch_outputs_batch
    on public.meat_processing_batch_outputs(batch_id, created_at);

alter table public.meat_processing_batches enable row level security;
alter table public.meat_processing_batch_pigs enable row level security;
alter table public.meat_processing_batch_events enable row level security;
alter table public.meat_processing_batch_costs enable row level security;
alter table public.meat_processing_batch_outputs enable row level security;

drop trigger if exists trg_meat_processing_batch_events_no_update on public.meat_processing_batch_events;
create trigger trg_meat_processing_batch_events_no_update
    before update or delete on public.meat_processing_batch_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

insert into app_private.migration_log (migration_id, description)
values (
    '202607130001_create_meat_processing_batches',
    'Create meat production batches, pig links, append-only stages, costs, and cut outputs.'
)
on conflict (migration_id) do nothing;
