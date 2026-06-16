create table if not exists public.oom_sakkie_meat_instruction_events (
    instruction_event_id text primary key,
    lead_id text not null references public.oom_sakkie_sales_leads(lead_id),
    instruction_draft_id text not null references public.oom_sakkie_meat_instruction_drafts(instruction_draft_id),
    reservation_id text not null default '',
    event_type text not null check (event_type in (
        'approved_to_send',
        'send_attempted',
        'sent',
        'send_failed',
        'exception_review_required',
        'exception_review_resolved'
    )),
    message_hash text not null default '',
    approved_message text not null default '',
    target_channel text not null default '',
    recipient_label text not null default '',
    notes_json jsonb not null default '{}'::jsonb,
    recorded_by text not null default 'Farm App',
    created_at timestamptz not null default now()
);

create index if not exists idx_oom_sakkie_meat_instruction_events_lead
    on public.oom_sakkie_meat_instruction_events(lead_id, created_at desc);

create index if not exists idx_oom_sakkie_meat_instruction_events_draft
    on public.oom_sakkie_meat_instruction_events(instruction_draft_id, created_at desc);

drop trigger if exists trg_oom_sakkie_meat_instruction_events_no_update on public.oom_sakkie_meat_instruction_events;
create trigger trg_oom_sakkie_meat_instruction_events_no_update
    before update on public.oom_sakkie_meat_instruction_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_meat_instruction_events_no_delete on public.oom_sakkie_meat_instruction_events;
create trigger trg_oom_sakkie_meat_instruction_events_no_delete
    before delete on public.oom_sakkie_meat_instruction_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();
