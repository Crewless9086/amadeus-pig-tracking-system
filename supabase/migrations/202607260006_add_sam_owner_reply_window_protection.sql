alter table public.sam_owner_work_item_events
    add column if not exists window_state text not null default 'unavailable',
    add column if not exists reply_authority_state text not null default 'unavailable',
    add column if not exists window_reason text not null default 'window_evidence_unavailable',
    add column if not exists provider_identity_class text not null default 'unavailable',
    add column if not exists window_evidence_hash text not null default '',
    add column if not exists expires_at_utc timestamptz,
    add column if not exists expires_at_johannesburg timestamptz,
    add column if not exists remaining_seconds integer,
    add column if not exists warning_threshold_hours integer not null default 6,
    add column if not exists urgent_threshold_hours integer not null default 2,
    add column if not exists alert_band text not null default 'none',
    add column if not exists ordinary_reply_allowed boolean not null default false,
    add column if not exists send_reply_action_visible boolean not null default false,
    add column if not exists template_required boolean not null default false;

alter table public.sam_owner_work_item_events
    drop constraint if exists sam_owner_work_window_state_check,
    add constraint sam_owner_work_window_state_check check (
      window_state in (
        'open','approaching_expiry','expired','unavailable','not_applicable'
      )
    ),
    drop constraint if exists sam_owner_work_alert_band_check,
    add constraint sam_owner_work_alert_band_check check (
      alert_band in ('none','warning','urgent','missed_window','withheld')
    ),
    drop constraint if exists sam_owner_work_window_threshold_check,
    add constraint sam_owner_work_window_threshold_check check (
      urgent_threshold_hours > 0
      and warning_threshold_hours > urgent_threshold_hours
      and warning_threshold_hours < 24
    ),
    drop constraint if exists sam_owner_work_reply_authority_check,
    add constraint sam_owner_work_reply_authority_check check (
      (ordinary_reply_allowed = false or window_state in ('open','approaching_expiry'))
      and (send_reply_action_visible = false or ordinary_reply_allowed = true)
      and (template_required = false or window_state = 'expired')
    );

create index if not exists idx_sam_owner_work_window_priority
    on public.sam_owner_work_item_events(
      actionable, expires_at_utc asc, window_state, observed_at desc
    );

create table if not exists public.sam_owner_window_alert_events (
    alert_event_id text primary key,
    alert_deduplication_hash text not null unique,
    work_item_id text not null,
    observation_hash text not null,
    conversation_id text not null,
    contact_id text not null,
    inbox_id text not null,
    window_contract_version text not null,
    window_state text not null,
    reply_authority_state text not null,
    alert_band text not null check (
      alert_band in ('warning','urgent','missed_window','withheld')
    ),
    expires_at_utc timestamptz,
    reason text not null,
    prepared_at timestamptz not null,
    delivery_enabled boolean not null default false,
    delivered boolean not null default false,
    contains_customer_content boolean not null default false,
    sends_customer_message boolean not null default false,
    changes_conversation_ownership boolean not null default false,
    calls_telegram boolean not null default false,
    uses_template boolean not null default false,
    mutates_business_state boolean not null default false,
    created_at timestamptz not null default now(),
    constraint sam_owner_window_alert_no_authority check (
      delivery_enabled = false
      and delivered = false
      and contains_customer_content = false
      and sends_customer_message = false
      and changes_conversation_ownership = false
      and calls_telegram = false
      and uses_template = false
      and mutates_business_state = false
    )
);

create index if not exists idx_sam_owner_window_alert_work_item
    on public.sam_owner_window_alert_events(
      work_item_id, prepared_at desc, alert_event_id desc
    );

drop trigger if exists prevent_sam_owner_window_alert_update
    on public.sam_owner_window_alert_events;
create trigger prevent_sam_owner_window_alert_update
    before update on public.sam_owner_window_alert_events
    for each row execute function public.prevent_sam_owner_queue_mutation();
drop trigger if exists prevent_sam_owner_window_alert_delete
    on public.sam_owner_window_alert_events;
create trigger prevent_sam_owner_window_alert_delete
    before delete on public.sam_owner_window_alert_events
    for each row execute function public.prevent_sam_owner_queue_mutation();

alter table public.sam_owner_window_alert_events enable row level security;

revoke all privileges on table public.sam_owner_window_alert_events
    from public, anon, authenticated, service_role;
grant select, insert on public.sam_owner_window_alert_events to service_role;
