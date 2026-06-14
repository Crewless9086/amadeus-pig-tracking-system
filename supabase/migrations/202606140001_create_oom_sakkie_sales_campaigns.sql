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
