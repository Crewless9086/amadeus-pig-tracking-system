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

-- A batch snapshot is the exact object approved by the owner.  It may move
-- forward through the lifecycle, but its decisions and approval provenance
-- may never be edited or replayed under a prior approval.
create or replace function app_private.enforce_pig_purpose_correction_batch_integrity()
returns trigger
language plpgsql
as $$
begin
    if new.batch_id is distinct from old.batch_id
       or new.idempotency_key is distinct from old.idempotency_key
       or new.decisions_json is distinct from old.decisions_json
       or new.decision_hash is distinct from old.decision_hash
       or new.created_by is distinct from old.created_by
       or new.created_at is distinct from old.created_at then
        raise exception 'pig purpose correction batch snapshot is immutable';
    end if;

    if old.status = 'draft'
       and new.status = 'owner_approved'
       and new.owner_approved_by is not null
       and new.owner_approved_at is not null
       and new.executed_by is null
       and new.executed_at is null then
        return new;
    end if;

    if old.status = 'owner_approved'
       and new.status = 'executed'
       and new.owner_approved_by = old.owner_approved_by
       and new.owner_approved_at = old.owner_approved_at
       and new.executed_by is not null
       and new.executed_at is not null then
        return new;
    end if;

    raise exception 'invalid pig purpose correction batch state transition';
end;
$$;

create trigger pig_purpose_correction_batch_integrity
before update on public.pig_purpose_correction_batches
for each row execute function app_private.enforce_pig_purpose_correction_batch_integrity();

insert into app_private.migration_log (migration_id, description) values ('202607220001_create_pig_purpose_correction_batches', 'Create owner-approved purpose correction batch rail.') on conflict (migration_id) do nothing;
