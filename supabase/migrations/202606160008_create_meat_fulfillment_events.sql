create table if not exists public.oom_sakkie_meat_fulfillment_events (
    fulfillment_event_id text primary key,
    lead_id text not null references public.oom_sakkie_sales_leads(lead_id),
    reservation_id text not null default '',
    order_id text not null default '',
    event_type text not null check (event_type in (
        'customer_waiting_half_pair',
        'customer_window_open',
        'customer_template_required',
        'customer_journey_update_planned',
        'customer_journey_update_sent',
        'abattoir_slot_requested',
        'abattoir_slot_confirmed',
        'butcher_slot_requested',
        'butcher_slot_confirmed',
        'delivery_required',
        'delivery_address_requested',
        'delivery_address_captured',
        'delivery_scheduled',
        'delivery_driver_assigned',
        'delivery_on_way',
        'delivery_arrived',
        'delivery_completed',
        'delivery_failed',
        'exception_review_required',
        'exception_review_resolved'
    )),
    actor_role text not null default '',
    actor_label text not null default '',
    customer_channel text not null default '',
    whatsapp_window_state text not null default '',
    requires_template boolean not null default false,
    scheduled_date text not null default '',
    scheduled_window text not null default '',
    location_label text not null default '',
    delivery_zone text not null default '',
    assigned_to text not null default '',
    customer_message_state text not null default '',
    address_json jsonb not null default '{}'::jsonb,
    notes_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_oom_sakkie_meat_fulfillment_events_lead
    on public.oom_sakkie_meat_fulfillment_events(lead_id, created_at desc);

create index if not exists idx_oom_sakkie_meat_fulfillment_events_reservation
    on public.oom_sakkie_meat_fulfillment_events(reservation_id, created_at desc);

drop trigger if exists trg_oom_sakkie_meat_fulfillment_events_no_update on public.oom_sakkie_meat_fulfillment_events;
create trigger trg_oom_sakkie_meat_fulfillment_events_no_update
    before update on public.oom_sakkie_meat_fulfillment_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_meat_fulfillment_events_no_delete on public.oom_sakkie_meat_fulfillment_events;
create trigger trg_oom_sakkie_meat_fulfillment_events_no_delete
    before delete on public.oom_sakkie_meat_fulfillment_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();
