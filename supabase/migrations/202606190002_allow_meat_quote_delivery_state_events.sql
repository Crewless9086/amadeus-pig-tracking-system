alter table public.oom_sakkie_sales_lead_events
    drop constraint if exists oom_sakkie_sales_lead_events_event_type_check;

alter table public.oom_sakkie_sales_lead_events
    add constraint oom_sakkie_sales_lead_events_event_type_check check (event_type in (
        'review_note',
        'status_observed',
        'owner_followup_needed',
        'owner_money_path_approved',
        'owner_customer_followup_send_approved',
        'customer_followup_send_attempted',
        'customer_followup_sent',
        'customer_followup_send_failed',
        'sam_meat_autoreply_attempted',
        'sam_meat_autoreply_sent',
        'sam_meat_autoreply_failed',
        'estimated_quote_send_attempted',
        'estimated_quote_chatwoot_accepted',
        'estimated_quote_template_required',
        'estimated_quote_sent',
        'estimated_quote_send_failed',
        'customer_booking_confirmed',
        'draft_order_created',
        'deposit_followup_needed',
        'linked_order_observed',
        'closed'
    ));
