-- Additive shared-sales schema. Do not apply without separate owner approval.
-- Legacy rows remain nullable and use application read compatibility only.

alter table public.orders
    add column if not exists order_stream text,
    add column if not exists livestock_details jsonb not null default '{}'::jsonb,
    add column if not exists meat_details jsonb not null default '{}'::jsonb,
    add column if not exists slaughter_details jsonb not null default '{}'::jsonb;

alter table public.orders drop constraint if exists orders_order_stream_check;
alter table public.orders add constraint orders_order_stream_check
    check (order_stream is null or order_stream in ('Livestock', 'Meat', 'Slaughter'));

create index if not exists idx_orders_order_stream on public.orders(order_stream);

comment on column public.orders.order_stream is
    'Explicit shared-flow stream. Null is reserved for legacy rows pending reviewed backfill.';
comment on column public.orders.livestock_details is
    'Livestock extension: pig/category/weight/sex/price/reservation/collection snapshots.';
comment on column public.orders.meat_details is
    'Meat extension: product/cut/weights/price/deposit/delivery/batch/packing/cold-chain data.';
comment on column public.orders.slaughter_details is
    'Slaughter extension without implicit livestock lifecycle authority.';

insert into app_private.migration_log (migration_id, description)
values ('202607150001_add_shared_order_stream',
        'Add validated Order stream and typed extension envelopes without backfilling legacy rows.')
on conflict (migration_id) do nothing;
