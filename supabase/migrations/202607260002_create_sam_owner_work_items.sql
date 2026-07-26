create table if not exists public.sam_owner_work_item_events (
    work_event_id text primary key,
    work_item_id text not null,
    account_id text not null,
    conversation_id text not null,
    contact_id text not null,
    inbox_id text not null,
    ownership_mode text not null,
    latest_message_id text not null,
    latest_message_at timestamptz,
    latest_inbound_message_id text not null default '',
    latest_outgoing_message_id text not null default '',
    chronology_hash text not null,
    observation_hash text not null,
    unanswered_inbound_bundle_json jsonb not null default '[]'::jsonb,
    unanswered_count integer not null check (unanswered_count >= 0),
    classification text not null,
    missed_message_classification text not null,
    lane text not null check (lane in ('GENERAL', 'SPECIALIST', 'PROTECTED')),
    actionable boolean not null,
    withheld_reasons_json jsonb not null default '[]'::jsonb,
    review_event_id text not null default '',
    reviewed_inbound_message_id text not null default '',
    protected_markers_json jsonb not null default '[]'::jsonb,
    specialist_markers_json jsonb not null default '[]'::jsonb,
    event_type text not null check (event_type in ('actionable', 'withheld')),
    source text not null,
    prior_event_id text references public.sam_owner_work_item_events(work_event_id),
    observed_at timestamptz not null,
    created_at timestamptz not null default now(),
    contains_customer_content boolean not null default false,
    sends_customer_message boolean not null default false,
    changes_conversation_ownership boolean not null default false,
    calls_telegram boolean not null default false,
    mutates_business_state boolean not null default false,
    constraint sam_owner_work_no_authority check (
        contains_customer_content = false
        and sends_customer_message = false
        and changes_conversation_ownership = false
        and calls_telegram = false
        and mutates_business_state = false
    )
);

create unique index if not exists uq_sam_owner_work_item_observation
    on public.sam_owner_work_item_events(
        work_item_id, observation_hash
    );
create unique index if not exists uq_sam_owner_work_item_prior_transition
    on public.sam_owner_work_item_events(work_item_id, prior_event_id)
    where prior_event_id is not null;
create index if not exists idx_sam_owner_work_item_latest
    on public.sam_owner_work_item_events(
        work_item_id, observed_at desc, created_at desc, work_event_id desc
    );
create index if not exists idx_sam_owner_work_actionable
    on public.sam_owner_work_item_events(actionable, lane, observed_at desc);

create table if not exists public.sam_owner_backlog_report_events (
    report_id text primary key,
    report_date date not null,
    snapshot_hash text not null,
    total_current_items integer not null check (total_current_items >= 0),
    actionable_count integer not null check (actionable_count >= 0),
    classification_counts_json jsonb not null default '{}'::jsonb,
    withheld_reason_counts_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    contains_customer_content boolean not null default false,
    sends_customer_message boolean not null default false,
    mutates_business_state boolean not null default false,
    constraint sam_owner_backlog_report_no_authority check (
        contains_customer_content = false
        and sends_customer_message = false
        and mutates_business_state = false
    ),
    unique (report_date, snapshot_hash)
);

create or replace function public.prevent_sam_owner_queue_mutation()
returns trigger language plpgsql as $$
begin
    raise exception 'SAM owner queue evidence is append-only';
end;
$$;

drop trigger if exists prevent_sam_owner_work_update on public.sam_owner_work_item_events;
create trigger prevent_sam_owner_work_update before update on public.sam_owner_work_item_events
for each row execute function public.prevent_sam_owner_queue_mutation();
drop trigger if exists prevent_sam_owner_work_delete on public.sam_owner_work_item_events;
create trigger prevent_sam_owner_work_delete before delete on public.sam_owner_work_item_events
for each row execute function public.prevent_sam_owner_queue_mutation();
drop trigger if exists prevent_sam_owner_report_update on public.sam_owner_backlog_report_events;
create trigger prevent_sam_owner_report_update before update on public.sam_owner_backlog_report_events
for each row execute function public.prevent_sam_owner_queue_mutation();
drop trigger if exists prevent_sam_owner_report_delete on public.sam_owner_backlog_report_events;
create trigger prevent_sam_owner_report_delete before delete on public.sam_owner_backlog_report_events
for each row execute function public.prevent_sam_owner_queue_mutation();

alter table public.sam_owner_work_item_events enable row level security;
alter table public.sam_owner_backlog_report_events enable row level security;

revoke all privileges on table public.sam_owner_work_item_events
    from public, anon, authenticated, service_role;
revoke all privileges on table public.sam_owner_backlog_report_events
    from public, anon, authenticated, service_role;
revoke all privileges on function public.prevent_sam_owner_queue_mutation()
    from public, anon, authenticated, service_role;

grant select, insert on public.sam_owner_work_item_events to service_role;
grant select, insert on public.sam_owner_backlog_report_events to service_role;
