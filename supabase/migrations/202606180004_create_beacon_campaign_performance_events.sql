create table if not exists public.beacon_campaign_performance_events (
    performance_event_id text primary key,
    mode text not null default 'beacon_campaign_performance_evidence_only' check (mode = 'beacon_campaign_performance_evidence_only'),
    manual_post_event_id text not null default '',
    publish_packet_id text not null default '',
    channel text not null default '',
    measurement_window text not null default '',
    spend_amount numeric(12, 2) not null default 0 check (spend_amount >= 0),
    spend_currency text not null default 'ZAR',
    reach integer not null default 0 check (reach >= 0),
    impressions integer not null default 0 check (impressions >= 0),
    reactions integer not null default 0 check (reactions >= 0),
    comments integer not null default 0 check (comments >= 0),
    shares integer not null default 0 check (shares >= 0),
    messages_to_sam integer not null default 0 check (messages_to_sam >= 0),
    qualified_buyer_leads integer not null default 0 check (qualified_buyer_leads >= 0),
    booking_review_requests integer not null default 0 check (booking_review_requests >= 0),
    notes text not null default '',
    recommended_action text not null default 'wait_for_more_data' check (recommended_action in (
        'light_boost_owner_review',
        'do_not_boost',
        'wait_for_more_data',
        'owner_review_required'
    )),
    recommendation_reason text not null default '',
    recommended_spend_amount numeric(12, 2) not null default 0 check (recommended_spend_amount >= 0),
    recommended_duration_days integer not null default 0 check (recommended_duration_days >= 0),
    max_spend_cap_amount numeric(12, 2) not null default 500 check (max_spend_cap_amount >= 0),
    cost_per_message numeric(12, 2),
    cost_per_qualified_lead numeric(12, 2),
    records_evidence boolean not null default true,
    recommends_boost boolean not null default false,
    boost_requires_owner_approval boolean not null default true,
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
    recorded_by text not null default 'beacon_performance_tracking',
    created_at timestamptz not null default now(),
    constraint beacon_campaign_performance_events_evidence_only_authority check (
        records_evidence = true
        and boost_requires_owner_approval = true
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
    ),
    constraint beacon_campaign_performance_recommendation_cap check (
        recommended_spend_amount <= max_spend_cap_amount
    )
);

create index if not exists idx_beacon_campaign_performance_packet_created
    on public.beacon_campaign_performance_events(publish_packet_id, created_at desc);

create index if not exists idx_beacon_campaign_performance_manual_post_created
    on public.beacon_campaign_performance_events(manual_post_event_id, created_at desc);

create index if not exists idx_beacon_campaign_performance_action_created
    on public.beacon_campaign_performance_events(recommended_action, created_at desc);

create or replace function public.prevent_beacon_campaign_performance_event_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'beacon campaign performance evidence is append-only in this phase';
end;
$$;

drop trigger if exists prevent_beacon_campaign_performance_events_update on public.beacon_campaign_performance_events;
create trigger prevent_beacon_campaign_performance_events_update
    before update on public.beacon_campaign_performance_events
    for each row
    execute function public.prevent_beacon_campaign_performance_event_mutation();

drop trigger if exists prevent_beacon_campaign_performance_events_delete on public.beacon_campaign_performance_events;
create trigger prevent_beacon_campaign_performance_events_delete
    before delete on public.beacon_campaign_performance_events
    for each row
    execute function public.prevent_beacon_campaign_performance_event_mutation();
