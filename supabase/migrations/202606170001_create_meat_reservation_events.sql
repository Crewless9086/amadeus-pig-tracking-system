create table if not exists public.oom_sakkie_meat_reservation_events (
    reservation_event_id text primary key,
    lead_id text not null references public.oom_sakkie_sales_leads(lead_id),
    reservation_id text not null references public.oom_sakkie_meat_carcass_reservations(reservation_id),
    event_type text not null check (event_type in (
        'reservation_cancelled',
        'reservation_reinstated',
        'reservation_note'
    )),
    reason text not null default '',
    notes_json jsonb not null default '{}'::jsonb,
    recorded_by text not null default 'Farm App',
    created_at timestamptz not null default now()
);

create index if not exists idx_oom_sakkie_meat_reservation_events_lead
    on public.oom_sakkie_meat_reservation_events(lead_id, created_at desc);

create index if not exists idx_oom_sakkie_meat_reservation_events_reservation
    on public.oom_sakkie_meat_reservation_events(reservation_id, created_at desc);

drop trigger if exists trg_oom_sakkie_meat_reservation_events_no_update on public.oom_sakkie_meat_reservation_events;
create trigger trg_oom_sakkie_meat_reservation_events_no_update
    before update on public.oom_sakkie_meat_reservation_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_meat_reservation_events_no_delete on public.oom_sakkie_meat_reservation_events;
create trigger trg_oom_sakkie_meat_reservation_events_no_delete
    before delete on public.oom_sakkie_meat_reservation_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();
