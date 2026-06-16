create table if not exists public.oom_sakkie_meat_carcass_reservations (
    reservation_id text primary key,
    lead_id text not null references public.oom_sakkie_sales_leads(lead_id),
    order_id text not null default '',
    pig_id text not null,
    tag_number text not null default '',
    product_type text not null check (product_type in ('half_carcass', 'full_carcass', 'custom_cut')),
    carcass_side text not null check (carcass_side in ('half_a', 'half_b', 'full')),
    cut_set text not null default '',
    status text not null check (status in (
        'half_reserved_pending_pair',
        'full_carcass_committed',
        'deposit_pending',
        'ready_for_slaughter_booking',
        'cancelled'
    )),
    estimated_packed_weight text not null default '',
    estimated_total numeric(12, 2),
    currency text not null default 'ZAR',
    match_snapshot_json jsonb not null default '{}'::jsonb,
    created_by text not null default 'Butcher',
    created_at timestamptz not null default now()
);

create table if not exists public.oom_sakkie_meat_deposit_events (
    deposit_event_id text primary key,
    lead_id text not null references public.oom_sakkie_sales_leads(lead_id),
    reservation_id text not null references public.oom_sakkie_meat_carcass_reservations(reservation_id),
    order_id text not null default '',
    event_type text not null check (event_type in (
        'deposit_requested_draft',
        'deposit_confirmed',
        'balance_confirmed',
        'payment_note'
    )),
    amount numeric(12, 2),
    payment_reference text not null default '',
    payment_method text not null default '',
    notes text not null default '',
    recorded_by text not null default 'Farm App',
    created_at timestamptz not null default now()
);

create table if not exists public.oom_sakkie_meat_instruction_drafts (
    instruction_draft_id text primary key,
    lead_id text not null references public.oom_sakkie_sales_leads(lead_id),
    reservation_id text not null references public.oom_sakkie_meat_carcass_reservations(reservation_id),
    order_id text not null default '',
    instruction_type text not null check (instruction_type in ('abattoir_booking', 'butcher_cut_sheet')),
    status text not null default 'draft' check (status in ('draft', 'approved_to_send', 'sent', 'cancelled')),
    recipient_label text not null default '',
    draft_message text not null default '',
    instruction_payload_json jsonb not null default '{}'::jsonb,
    created_by text not null default 'Butcher',
    created_at timestamptz not null default now()
);

create index if not exists idx_oom_sakkie_meat_reservations_lead
    on public.oom_sakkie_meat_carcass_reservations(lead_id, created_at desc);

create index if not exists idx_oom_sakkie_meat_reservations_pig
    on public.oom_sakkie_meat_carcass_reservations(pig_id, created_at desc);

create index if not exists idx_oom_sakkie_meat_deposits_reservation
    on public.oom_sakkie_meat_deposit_events(reservation_id, created_at desc);

create index if not exists idx_oom_sakkie_meat_instruction_drafts_reservation
    on public.oom_sakkie_meat_instruction_drafts(reservation_id, created_at desc);

drop trigger if exists trg_oom_sakkie_meat_reservations_no_update on public.oom_sakkie_meat_carcass_reservations;
create trigger trg_oom_sakkie_meat_reservations_no_update
    before update on public.oom_sakkie_meat_carcass_reservations
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_meat_reservations_no_delete on public.oom_sakkie_meat_carcass_reservations;
create trigger trg_oom_sakkie_meat_reservations_no_delete
    before delete on public.oom_sakkie_meat_carcass_reservations
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_meat_deposits_no_update on public.oom_sakkie_meat_deposit_events;
create trigger trg_oom_sakkie_meat_deposits_no_update
    before update on public.oom_sakkie_meat_deposit_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_meat_deposits_no_delete on public.oom_sakkie_meat_deposit_events;
create trigger trg_oom_sakkie_meat_deposits_no_delete
    before delete on public.oom_sakkie_meat_deposit_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_meat_instruction_drafts_no_update on public.oom_sakkie_meat_instruction_drafts;
create trigger trg_oom_sakkie_meat_instruction_drafts_no_update
    before update on public.oom_sakkie_meat_instruction_drafts
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_meat_instruction_drafts_no_delete on public.oom_sakkie_meat_instruction_drafts;
create trigger trg_oom_sakkie_meat_instruction_drafts_no_delete
    before delete on public.oom_sakkie_meat_instruction_drafts
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();
