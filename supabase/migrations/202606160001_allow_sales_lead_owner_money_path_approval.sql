alter table public.oom_sakkie_sales_lead_events
    drop constraint if exists oom_sakkie_sales_lead_events_event_type_check;

alter table public.oom_sakkie_sales_lead_events
    add constraint oom_sakkie_sales_lead_events_event_type_check check (event_type in (
        'review_note',
        'status_observed',
        'owner_followup_needed',
        'owner_money_path_approved',
        'deposit_followup_needed',
        'linked_order_observed',
        'closed'
    ));
