-- OP-004 reusable append-only medical correction rail and active order-line guard.
-- No historical medical row is updated or deleted.

create table if not exists public.pig_medical_correction_events (
    correction_event_id text primary key,
    pig_id text not null references public.pigs(pig_id) on delete restrict,
    original_medical_event_id text not null references public.pig_medical_events(medical_event_id) on delete restrict,
    retained_medical_event_id text references public.pig_medical_events(medical_event_id) on delete restrict,
    resolution text not null check (resolution in (
        'duplicate_record', 'separate_administration', 'unknown_veterinary_review'
    )),
    factual_basis text not null check (btrim(factual_basis) <> ''),
    recorded_by text not null check (btrim(recorded_by) <> ''),
    recorded_at timestamptz not null default now(),
    idempotency_key text not null unique check (btrim(idempotency_key) <> ''),
    supersedes_correction_event_id text references public.pig_medical_correction_events(correction_event_id) on delete restrict,
    check (retained_medical_event_id is null or retained_medical_event_id <> original_medical_event_id),
    check ((resolution = 'duplicate_record' and retained_medical_event_id is not null)
        or (resolution <> 'duplicate_record' and retained_medical_event_id is null)),
    check (supersedes_correction_event_id is null or supersedes_correction_event_id <> correction_event_id)
);

create table if not exists public.herdmaster_transfer_evidence_receipts (
    idempotency_key text primary key check (btrim(idempotency_key) <> ''),
    action_version text not null,
    actor_id text not null check (btrim(actor_id) <> ''),
    preview_digest text not null check (btrim(preview_digest) <> ''),
    submitted_answers_digest text not null check (btrim(submitted_answers_digest) <> ''),
    action_envelope jsonb not null,
    executed_at timestamptz not null default now()
);

create index if not exists pig_medical_correction_original_idx
    on public.pig_medical_correction_events(original_medical_event_id, recorded_at desc);
create unique index if not exists pig_medical_correction_one_successor_idx
    on public.pig_medical_correction_events(supersedes_correction_event_id)
    where supersedes_correction_event_id is not null;

create or replace function public.validate_pig_medical_correction_event()
returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from public.pig_medical_events m
        where m.medical_event_id = new.original_medical_event_id and m.pig_id = new.pig_id
    ) then raise exception 'medical correction original must belong to the same pig'; end if;
    if new.retained_medical_event_id is not null and not exists (
        select 1 from public.pig_medical_events m
        where m.medical_event_id = new.retained_medical_event_id and m.pig_id = new.pig_id
    ) then raise exception 'medical correction retained event must belong to the same pig'; end if;
    if new.supersedes_correction_event_id is not null and not exists (
        select 1 from public.pig_medical_correction_events c
        where c.correction_event_id = new.supersedes_correction_event_id
          and c.original_medical_event_id = new.original_medical_event_id and c.pig_id = new.pig_id
    ) then raise exception 'medical correction supersession must retain pig and original event'; end if;
    if new.supersedes_correction_event_id is not null and exists (
        select 1 from public.pig_medical_correction_events successor
        where successor.supersedes_correction_event_id = new.supersedes_correction_event_id
    ) then raise exception 'medical correction already has a successor'; end if;
    if new.supersedes_correction_event_id is null and exists (
        select 1 from public.pig_medical_correction_events current_event
        where current_event.pig_id = new.pig_id
          and current_event.original_medical_event_id = new.original_medical_event_id
          and not exists (select 1 from public.pig_medical_correction_events successor
                          where successor.supersedes_correction_event_id = current_event.correction_event_id)
    ) then raise exception 'medical correction requires explicit supersession of the current correction'; end if;
    return new;
end $$;

drop trigger if exists validate_pig_medical_correction_event on public.pig_medical_correction_events;
create trigger validate_pig_medical_correction_event
before insert on public.pig_medical_correction_events
for each row execute function public.validate_pig_medical_correction_event();

create or replace function public.block_pig_medical_correction_mutation()
returns trigger language plpgsql as $$ begin
    raise exception 'pig medical correction events are append-only';
end $$;

drop trigger if exists block_pig_medical_correction_mutation on public.pig_medical_correction_events;
create trigger block_pig_medical_correction_mutation
before update or delete on public.pig_medical_correction_events
for each row execute function public.block_pig_medical_correction_mutation();

drop trigger if exists block_herdmaster_transfer_evidence_receipt_mutation
    on public.herdmaster_transfer_evidence_receipts;
create trigger block_herdmaster_transfer_evidence_receipt_mutation
before update or delete on public.herdmaster_transfer_evidence_receipts
for each row execute function public.block_pig_medical_correction_mutation();

alter table public.pig_medical_correction_events enable row level security;
alter table public.herdmaster_transfer_evidence_receipts enable row level security;
revoke all privileges on public.pig_medical_correction_events from public;
revoke all privileges on public.herdmaster_transfer_evidence_receipts from public;
do $$ begin
    if exists (select 1 from pg_roles where rolname='anon') then
        revoke all privileges on public.pig_medical_correction_events from anon;
        revoke all privileges on public.herdmaster_transfer_evidence_receipts from anon;
    end if;
    if exists (select 1 from pg_roles where rolname='authenticated') then
        revoke all privileges on public.pig_medical_correction_events from authenticated;
        revoke all privileges on public.herdmaster_transfer_evidence_receipts from authenticated;
    end if;
    if exists (select 1 from pg_roles where rolname='service_role') then
        revoke all privileges on public.pig_medical_correction_events from service_role;
        grant select, insert on public.pig_medical_correction_events to service_role;
        revoke all privileges on public.herdmaster_transfer_evidence_receipts from service_role;
        grant select, insert on public.herdmaster_transfer_evidence_receipts to service_role;
    end if;
end $$;

-- Production reconciliation proved zero existing duplicate active order/pig pairs.
create unique index if not exists order_lines_one_active_pig_per_order_idx
    on public.order_lines(order_id, pig_id)
    where pig_id is not null and lower(coalesce(line_status, '')) not in ('cancelled', 'removed');

insert into app_private.migration_log(migration_id, description)
values ('202608160001_create_medical_correction_and_order_line_guard',
        'Create append-only medical corrections and transaction-safe active order-line uniqueness')
on conflict (migration_id) do nothing;
