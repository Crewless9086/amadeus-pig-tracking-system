create table if not exists public.beacon_manual_post_events (
    manual_post_event_id text primary key,
    mode text not null default 'beacon_manual_public_post_evidence_only' check (mode = 'beacon_manual_public_post_evidence_only'),
    publish_packet_id text not null default '',
    channel text not null default '',
    post_url text not null default '',
    posted_at timestamptz,
    posted_by text not null default '',
    campaign_label text not null default '',
    evidence_notes text not null default '',
    initial_metrics_json jsonb not null default '{}'::jsonb,
    records_evidence boolean not null default true,
    sends_customer_message boolean not null default false,
    posts_publicly boolean not null default false,
    calls_chatwoot boolean not null default false,
    calls_meta boolean not null default false,
    calls_n8n boolean not null default false,
    boosts_post boolean not null default false,
    spends_money boolean not null default false,
    creates_quote boolean not null default false,
    creates_invoice boolean not null default false,
    creates_order boolean not null default false,
    changes_stock boolean not null default false,
    reserves_stock boolean not null default false,
    dispatch_enabled boolean not null default false,
    changes_runtime_now boolean not null default false,
    changes_prompt_now boolean not null default false,
    physical_controls_enabled boolean not null default false,
    customer_public_output_enabled boolean not null default false,
    writes_farm_data boolean not null default false,
    created_at timestamptz not null default now(),
    constraint beacon_manual_post_events_evidence_only_authority check (
        records_evidence = true
        and sends_customer_message = false
        and posts_publicly = false
        and calls_chatwoot = false
        and calls_meta = false
        and calls_n8n = false
        and boosts_post = false
        and spends_money = false
        and creates_quote = false
        and creates_invoice = false
        and creates_order = false
        and changes_stock = false
        and reserves_stock = false
        and dispatch_enabled = false
        and changes_runtime_now = false
        and changes_prompt_now = false
        and physical_controls_enabled = false
        and customer_public_output_enabled = false
        and writes_farm_data = false
    )
);

create index if not exists idx_beacon_manual_post_events_packet_created
    on public.beacon_manual_post_events(publish_packet_id, created_at desc);

create index if not exists idx_beacon_manual_post_events_channel_created
    on public.beacon_manual_post_events(channel, created_at desc);

create or replace function public.prevent_beacon_manual_post_event_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'beacon manual post evidence is append-only in this phase';
end;
$$;

drop trigger if exists prevent_beacon_manual_post_events_update on public.beacon_manual_post_events;
create trigger prevent_beacon_manual_post_events_update
    before update on public.beacon_manual_post_events
    for each row
    execute function public.prevent_beacon_manual_post_event_mutation();

drop trigger if exists prevent_beacon_manual_post_events_delete on public.beacon_manual_post_events;
create trigger prevent_beacon_manual_post_events_delete
    before delete on public.beacon_manual_post_events
    for each row
    execute function public.prevent_beacon_manual_post_event_mutation();
