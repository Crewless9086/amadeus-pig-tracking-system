create table if not exists public.oom_sakkie_meat_reconciliation_events (
    reconciliation_event_id text primary key,
    lead_id text not null references public.oom_sakkie_sales_leads(lead_id),
    reservation_id text not null references public.oom_sakkie_meat_carcass_reservations(reservation_id),
    order_id text not null default '',
    event_type text not null check (event_type in (
        'packed_weight_recorded',
        'final_balance_draft',
        'balance_requested',
        'balance_confirmed_in_bank',
        'balance_note'
    )),
    actual_packed_weight_kg numeric(12, 3),
    price_per_kg numeric(12, 2),
    final_amount numeric(12, 2),
    deposit_confirmed_amount numeric(12, 2),
    balance_due numeric(12, 2),
    balance_confirmed_amount numeric(12, 2),
    payment_reference text not null default '',
    message text not null default '',
    notes_json jsonb not null default '{}'::jsonb,
    recorded_by text not null default 'Farm App',
    created_at timestamptz not null default now()
);

create index if not exists idx_oom_sakkie_meat_reconciliation_events_lead
    on public.oom_sakkie_meat_reconciliation_events(lead_id, created_at desc);

create index if not exists idx_oom_sakkie_meat_reconciliation_events_reservation
    on public.oom_sakkie_meat_reconciliation_events(reservation_id, created_at desc);

drop trigger if exists trg_oom_sakkie_meat_reconciliation_events_no_update on public.oom_sakkie_meat_reconciliation_events;
create trigger trg_oom_sakkie_meat_reconciliation_events_no_update
    before update on public.oom_sakkie_meat_reconciliation_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_meat_reconciliation_events_no_delete on public.oom_sakkie_meat_reconciliation_events;
create trigger trg_oom_sakkie_meat_reconciliation_events_no_delete
    before delete on public.oom_sakkie_meat_reconciliation_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();
