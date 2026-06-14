create table if not exists public.oom_sakkie_sales_leads (
    lead_id text primary key,
    campaign_id text references public.oom_sakkie_sales_campaigns(campaign_id),
    draft_id text references public.oom_sakkie_sales_outreach_drafts(draft_id),
    send_design_id text references public.oom_sakkie_sales_send_design_requests(send_design_id),
    status text not null check (status in (
        'new',
        'interested',
        'asked_price',
        'needs_callback',
        'deposit_pending',
        'not_interested',
        'order_ready_for_approval',
        'closed'
    )),
    mode text not null check (mode = 'sales_lead_tracking_only'),
    campaign_source text not null check (campaign_source in (
        'ready_meat_preorder',
        'social_post',
        'direct_known_buyer',
        'inbound_chatwoot',
        'whatsapp_status',
        'manual_owner_note',
        'other'
    )),
    lead_label text not null check (length(trim(lead_label)) > 0),
    contact_label text not null default '',
    channel text not null default 'chatwoot_whatsapp',
    chatwoot_conversation_id text not null default '',
    whatsapp_window_state text not null check (whatsapp_window_state in (
        'unknown',
        'open',
        'closed',
        'template_required',
        'manual_owner_only'
    )),
    last_inbound_at timestamptz,
    opt_in_state text not null default 'unknown',
    interest_json jsonb not null default '{}'::jsonb,
    next_owner_action text not null default '',
    linked_order_id text not null default '',
    linked_preorder_id text not null default '',
    created_by text not null default 'sam_or_owner_review',
    sends_customer_message boolean not null default false,
    calls_chatwoot boolean not null default false,
    calls_n8n boolean not null default false,
    creates_quote boolean not null default false,
    creates_order boolean not null default false,
    changes_stock boolean not null default false,
    dispatch_enabled boolean not null default false,
    changes_runtime_now boolean not null default false,
    changes_prompt_now boolean not null default false,
    physical_controls_enabled boolean not null default false,
    customer_public_output_enabled boolean not null default false,
    writes_farm_data boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_sales_leads_no_authority_check check (
        sends_customer_message = false
        and calls_chatwoot = false
        and calls_n8n = false
        and creates_quote = false
        and creates_order = false
        and changes_stock = false
        and dispatch_enabled = false
        and changes_runtime_now = false
        and changes_prompt_now = false
        and physical_controls_enabled = false
        and customer_public_output_enabled = false
        and writes_farm_data = false
    )
);

create table if not exists public.oom_sakkie_sales_lead_events (
    event_id text primary key,
    lead_id text not null references public.oom_sakkie_sales_leads(lead_id),
    event_type text not null check (event_type in (
        'review_note',
        'status_observed',
        'owner_followup_needed',
        'deposit_followup_needed',
        'linked_order_observed',
        'closed'
    )),
    notes text not null default '',
    recorded_by text not null default 'owner',
    status_observed text not null default '',
    sends_customer_message boolean not null default false,
    calls_chatwoot boolean not null default false,
    calls_n8n boolean not null default false,
    creates_quote boolean not null default false,
    creates_order boolean not null default false,
    changes_stock boolean not null default false,
    dispatch_enabled boolean not null default false,
    changes_runtime_now boolean not null default false,
    changes_prompt_now boolean not null default false,
    physical_controls_enabled boolean not null default false,
    customer_public_output_enabled boolean not null default false,
    writes_farm_data boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_sales_lead_events_no_authority_check check (
        sends_customer_message = false
        and calls_chatwoot = false
        and calls_n8n = false
        and creates_quote = false
        and creates_order = false
        and changes_stock = false
        and dispatch_enabled = false
        and changes_runtime_now = false
        and changes_prompt_now = false
        and physical_controls_enabled = false
        and customer_public_output_enabled = false
        and writes_farm_data = false
    )
);

create index if not exists idx_oom_sakkie_sales_leads_created_at
    on public.oom_sakkie_sales_leads(created_at desc);

create index if not exists idx_oom_sakkie_sales_leads_status
    on public.oom_sakkie_sales_leads(status, created_at desc);

create index if not exists idx_oom_sakkie_sales_lead_events_lead_created
    on public.oom_sakkie_sales_lead_events(lead_id, created_at desc);

drop trigger if exists trg_oom_sakkie_sales_leads_no_update on public.oom_sakkie_sales_leads;
create trigger trg_oom_sakkie_sales_leads_no_update
    before update on public.oom_sakkie_sales_leads
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_sales_leads_no_delete on public.oom_sakkie_sales_leads;
create trigger trg_oom_sakkie_sales_leads_no_delete
    before delete on public.oom_sakkie_sales_leads
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_sales_lead_events_no_update on public.oom_sakkie_sales_lead_events;
create trigger trg_oom_sakkie_sales_lead_events_no_update
    before update on public.oom_sakkie_sales_lead_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_sales_lead_events_no_delete on public.oom_sakkie_sales_lead_events;
create trigger trg_oom_sakkie_sales_lead_events_no_delete
    before delete on public.oom_sakkie_sales_lead_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();
