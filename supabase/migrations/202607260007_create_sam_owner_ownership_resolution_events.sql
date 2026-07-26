create table if not exists public.sam_owner_ownership_resolution_events (
    resolution_event_id text primary key,
    resolution_id text not null,
    event_type text not null check (event_type in ('claim', 'result')),
    target_mode text not null check (target_mode in ('HUMAN','AUTO_GENERAL','AUTO_SPECIALIST')),
    work_item_id text not null,
    work_event_id text not null,
    account_id text not null,
    conversation_id text not null,
    contact_id text not null,
    inbox_id text not null,
    observation_hash text not null,
    chronology_hash text not null,
    latest_inbound_message_id text not null,
    unanswered_count integer not null check (unanswered_count >= 0),
    review_event_id text not null,
    window_evidence_hash text not null,
    actor_id text not null,
    outcome text not null,
    reason text not null default '',
    prior_event_id text references public.sam_owner_ownership_resolution_events(resolution_event_id),
    created_at timestamptz not null,
    contains_customer_content boolean not null default false,
    sends_customer_message boolean not null default false,
    calls_telegram boolean not null default false,
    creates_template boolean not null default false,
    mutates_business_state boolean not null default false,
    constraint sam_owner_resolution_no_authority check (
      contains_customer_content=false and sends_customer_message=false
      and calls_telegram=false and creates_template=false
      and mutates_business_state=false
    ),
    unique (resolution_id, event_type)
);
create index if not exists idx_sam_owner_resolution_conversation
  on public.sam_owner_ownership_resolution_events(conversation_id, created_at desc);

create or replace function public.prevent_sam_owner_resolution_mutation()
returns trigger language plpgsql as $$
begin
  raise exception 'SAM owner ownership-resolution evidence is append-only';
end;
$$;
drop trigger if exists prevent_sam_owner_resolution_update
  on public.sam_owner_ownership_resolution_events;
create trigger prevent_sam_owner_resolution_update
before update on public.sam_owner_ownership_resolution_events
for each row execute function public.prevent_sam_owner_resolution_mutation();
drop trigger if exists prevent_sam_owner_resolution_delete
  on public.sam_owner_ownership_resolution_events;
create trigger prevent_sam_owner_resolution_delete
before delete on public.sam_owner_ownership_resolution_events
for each row execute function public.prevent_sam_owner_resolution_mutation();

alter table public.sam_owner_ownership_resolution_events enable row level security;
revoke all privileges on table public.sam_owner_ownership_resolution_events
  from public, anon, authenticated, service_role;
revoke all privileges on function public.prevent_sam_owner_resolution_mutation()
  from public, anon, authenticated, service_role;
grant select, insert on public.sam_owner_ownership_resolution_events to service_role;
