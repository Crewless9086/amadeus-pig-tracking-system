create table if not exists public.bulk_weight_batches (
    batch_id uuid primary key,
    client_draft_id text not null default '',
    weight_date date not null,
    status text not null default 'staged' check (status in ('staged', 'processing', 'partial', 'complete', 'failed', 'cancelled')),
    visible_row_count integer not null default 0 check (visible_row_count >= 0),
    actionable_row_count integer not null default 0 check (actionable_row_count >= 0),
    weight_row_count integer not null default 0 check (weight_row_count >= 0),
    movement_row_count integer not null default 0 check (movement_row_count >= 0),
    skipped_row_count integer not null default 0 check (skipped_row_count >= 0),
    success_count integer not null default 0 check (success_count >= 0),
    failed_count integer not null default 0 check (failed_count >= 0),
    duplicate_count integer not null default 0 check (duplicate_count >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz,
    source text not null default 'bulk_weights_web',
    notes text,
    error_summary text,
    payload_summary_json jsonb not null default '{}'::jsonb
);

create table if not exists public.bulk_weight_batch_rows (
    row_id uuid primary key,
    batch_id uuid not null references public.bulk_weight_batches(batch_id) on delete cascade,
    row_index integer not null check (row_index >= 0),
    pig_id text not null default '',
    pig_name text,
    weight_kg numeric,
    from_pen_id text,
    to_pen_id text,
    movement_type text,
    status text not null default 'staged' check (status in ('staged', 'skipped', 'processing', 'success', 'failed', 'duplicate', 'blocked')),
    status_reason text,
    processed_at timestamptz,
    result_json jsonb not null default '{}'::jsonb,
    original_row_json jsonb not null default '{}'::jsonb,
    idempotency_key text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint bulk_weight_batch_rows_batch_row_unique unique (batch_id, row_index),
    constraint bulk_weight_batch_rows_idempotency_unique unique (idempotency_key)
);

create index if not exists bulk_weight_batches_status_idx on public.bulk_weight_batches(status);
create index if not exists bulk_weight_batches_created_at_idx on public.bulk_weight_batches(created_at desc);
create index if not exists bulk_weight_batch_rows_batch_id_idx on public.bulk_weight_batch_rows(batch_id);
create index if not exists bulk_weight_batch_rows_status_idx on public.bulk_weight_batch_rows(status);
create index if not exists bulk_weight_batch_rows_created_at_idx on public.bulk_weight_batch_rows(created_at desc);

insert into app_private.migration_log (migration_id, description)
values ('202606280001_create_bulk_weight_batch_tables', 'Create durable bulk weight batch staging and row audit tables')
on conflict (migration_id) do nothing;
