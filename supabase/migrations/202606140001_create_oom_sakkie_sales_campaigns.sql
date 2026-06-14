create table if not exists public.oom_sakkie_sales_campaigns (
    campaign_id text primary key,
    status text not null check (status = 'pending_owner_review'),
    mode text not null check (mode = 'owner_review_sales_campaign_only'),
    source_tool text not null,
    campaign_title text not null check (length(trim(campaign_title)) > 0),
    opportunity_json jsonb not null default '{}'::jsonb,
    draft_json jsonb not null default '{}'::jsonb,
    owner_questions_json jsonb not null default '[]'::jsonb,
    risks_json jsonb not null default '[]'::jsonb,
    next_action text not null default '',
    created_by text not null default 'ledger',
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
    constraint oom_sakkie_sales_campaigns_no_authority_check check (
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

create table if not exists public.oom_sakkie_sales_campaign_events (
    event_id text primary key,
    campaign_id text not null references public.oom_sakkie_sales_campaigns(campaign_id),
    event_type text not null check (event_type in ('review_note', 'approved_for_customer_outreach', 'rejected', 'deferred')),
    notes text not null default '',
    recorded_by text not null default 'owner',
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
    constraint oom_sakkie_sales_campaign_events_no_authority_check check (
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

create index if not exists idx_oom_sakkie_sales_campaigns_created_at
    on public.oom_sakkie_sales_campaigns(created_at desc);

create index if not exists idx_oom_sakkie_sales_campaign_events_campaign_created
    on public.oom_sakkie_sales_campaign_events(campaign_id, created_at desc);

create or replace function public.oom_sakkie_sales_campaigns_block_update_delete()
returns trigger
language plpgsql
as $$
begin
    raise exception 'oom_sakkie_sales_campaign tables are append-only';
end;
$$;

drop trigger if exists trg_oom_sakkie_sales_campaigns_no_update on public.oom_sakkie_sales_campaigns;
create trigger trg_oom_sakkie_sales_campaigns_no_update
    before update on public.oom_sakkie_sales_campaigns
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_sales_campaigns_no_delete on public.oom_sakkie_sales_campaigns;
create trigger trg_oom_sakkie_sales_campaigns_no_delete
    before delete on public.oom_sakkie_sales_campaigns
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_sales_campaign_events_no_update on public.oom_sakkie_sales_campaign_events;
create trigger trg_oom_sakkie_sales_campaign_events_no_update
    before update on public.oom_sakkie_sales_campaign_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_sales_campaign_events_no_delete on public.oom_sakkie_sales_campaign_events;
create trigger trg_oom_sakkie_sales_campaign_events_no_delete
    before delete on public.oom_sakkie_sales_campaign_events
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

create table if not exists public.oom_sakkie_sales_outreach_drafts (
    draft_id text primary key,
    campaign_id text not null references public.oom_sakkie_sales_campaigns(campaign_id),
    status text not null check (status = 'pending_owner_review'),
    mode text not null check (mode = 'owner_review_customer_outreach_draft_only'),
    audience_label text not null default 'known meat buyers',
    draft_text text not null check (length(trim(draft_text)) > 0),
    owner_checks_json jsonb not null default '[]'::jsonb,
    source_campaign_snapshot_json jsonb not null default '{}'::jsonb,
    created_by text not null default 'ledger',
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
    constraint oom_sakkie_sales_outreach_drafts_one_per_campaign_audience unique (campaign_id, audience_label),
    constraint oom_sakkie_sales_outreach_drafts_no_authority_check check (
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

create index if not exists idx_oom_sakkie_sales_outreach_drafts_created_at
    on public.oom_sakkie_sales_outreach_drafts(created_at desc);

create index if not exists idx_oom_sakkie_sales_outreach_drafts_campaign
    on public.oom_sakkie_sales_outreach_drafts(campaign_id, created_at desc);

drop trigger if exists trg_oom_sakkie_sales_outreach_drafts_no_update on public.oom_sakkie_sales_outreach_drafts;
create trigger trg_oom_sakkie_sales_outreach_drafts_no_update
    before update on public.oom_sakkie_sales_outreach_drafts
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_sales_outreach_drafts_no_delete on public.oom_sakkie_sales_outreach_drafts;
create trigger trg_oom_sakkie_sales_outreach_drafts_no_delete
    before delete on public.oom_sakkie_sales_outreach_drafts
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

create table if not exists public.oom_sakkie_sales_send_design_requests (
    send_design_id text primary key,
    draft_id text not null references public.oom_sakkie_sales_outreach_drafts(draft_id),
    status text not null check (status = 'pending_owner_review'),
    mode text not null check (mode = 'customer_send_design_request_only'),
    target_transport text not null check (target_transport in ('sam_chatwoot_whatsapp_review', 'manual_owner_send_review')),
    design_summary text not null default '',
    required_owner_checks_json jsonb not null default '[]'::jsonb,
    source_draft_snapshot_json jsonb not null default '{}'::jsonb,
    created_by text not null default 'owner',
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
    constraint oom_sakkie_sales_send_design_one_per_draft_transport unique (draft_id, target_transport),
    constraint oom_sakkie_sales_send_design_no_authority_check check (
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

create index if not exists idx_oom_sakkie_sales_send_design_created_at
    on public.oom_sakkie_sales_send_design_requests(created_at desc);

drop trigger if exists trg_oom_sakkie_sales_send_design_no_update on public.oom_sakkie_sales_send_design_requests;
create trigger trg_oom_sakkie_sales_send_design_no_update
    before update on public.oom_sakkie_sales_send_design_requests
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_sales_send_design_no_delete on public.oom_sakkie_sales_send_design_requests;
create trigger trg_oom_sakkie_sales_send_design_no_delete
    before delete on public.oom_sakkie_sales_send_design_requests
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();
