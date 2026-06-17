alter table public.oom_sakkie_meat_deposit_events
    drop constraint if exists oom_sakkie_meat_deposit_events_event_type_check;

alter table public.oom_sakkie_meat_deposit_events
    add constraint oom_sakkie_meat_deposit_events_event_type_check
    check (event_type in (
        'deposit_requested_draft',
        'pop_received_unverified',
        'pop_rejected',
        'deposit_confirmed_in_bank',
        'deposit_confirmed',
        'balance_confirmed',
        'payment_note'
    ));
