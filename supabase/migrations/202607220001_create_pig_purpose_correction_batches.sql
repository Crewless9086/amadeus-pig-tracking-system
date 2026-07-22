create table if not exists public.pig_purpose_correction_batches (
    batch_id text primary key,
    idempotency_key text not null unique,
    status text not null check (status in ('draft','owner_approved','executed')),
    decisions_json jsonb not null,
    decision_hash text not null,
    created_by text not null,
    created_at timestamptz not null default now(),
    owner_approved_by text,
    owner_approved_at timestamptz,
    executed_by text,
    executed_at timestamptz,
    check ((status = 'draft' and owner_approved_at is null and executed_at is null) or (status = 'owner_approved' and owner_approved_at is not null and executed_at is null) or (status = 'executed' and owner_approved_at is not null and executed_at is not null))
);
alter table public.pig_purpose_correction_batches enable row level security;
insert into app_private.migration_log (migration_id, description) values ('202607220001_create_pig_purpose_correction_batches', 'Create owner-approved purpose correction batch rail.') on conflict (migration_id) do nothing;
