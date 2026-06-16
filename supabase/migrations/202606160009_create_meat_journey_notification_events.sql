create table if not exists public.oom_sakkie_meat_journey_notification_events (
    notification_event_id text primary key,
    lead_id text not null references public.oom_sakkie_sales_leads(lead_id),
    fulfillment_event_id text not null default '',
    stage text not null default '',
    event_type text not null check (event_type in (
        'draft_created',
        'approved_to_send',
        'send_attempted',
        'sent',
        'send_failed',
        'template_required',
        'skipped'
    )),
    message_hash text not null default '',
    message text not null default '',
    target_channel text not null default 'chatwoot_whatsapp',
    requires_template boolean not null default false,
    transport_result_json jsonb not null default '{}'::jsonb,
    notes_json jsonb not null default '{}'::jsonb,
    recorded_by text not null default 'Farm App',
    created_at timestamptz not null default now()
);

create index if not exists idx_oom_sakkie_meat_journey_notifications_lead
    on public.oom_sakkie_meat_journey_notification_events(lead_id, created_at desc);

create index if not exists idx_oom_sakkie_meat_journey_notifications_hash
    on public.oom_sakkie_meat_journey_notification_events(lead_id, message_hash, created_at desc);

drop trigger if exists trg_oom_sakkie_meat_journey_notifications_no_update on public.oom_sakkie_meat_journey_notification_events;
create trigger trg_oom_sakkie_meat_journey_notifications_no_update
    before update on public.oom_sakkie_meat_journey_notification_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_meat_journey_notifications_no_delete on public.oom_sakkie_meat_journey_notification_events;
create trigger trg_oom_sakkie_meat_journey_notifications_no_delete
    before delete on public.oom_sakkie_meat_journey_notification_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();
