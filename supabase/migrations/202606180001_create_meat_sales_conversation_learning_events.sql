create table if not exists public.meat_sales_conversation_learning_events (
    learning_event_id text primary key,
    lead_id text not null default '',
    chatwoot_conversation_id text not null default '',
    channel text not null default 'chatwoot_whatsapp',
    source_agent text not null default 'sam_meat_backend',
    event_source text not null default 'chatwoot_inbound',
    event_type text not null check (event_type in (
        'sam_inbound_observation',
        'owner_review_note',
        'conversion_observed',
        'loss_observed'
    )),
    customer_message_excerpt text not null default '',
    sam_reply_excerpt text not null default '',
    customer_wanted_json jsonb not null default '{}'::jsonb,
    captured_facts_json jsonb not null default '{}'::jsonb,
    missing_facts_json jsonb not null default '[]'::jsonb,
    objections_json jsonb not null default '[]'::jsonb,
    confusion_signals_json jsonb not null default '[]'::jsonb,
    sam_misses_json jsonb not null default '[]'::jsonb,
    conversion_signal text not null default 'unknown' check (conversion_signal in (
        'unknown',
        'new_interest',
        'qualified_interest',
        'needs_followup',
        'booking_review_requested',
        'deposit_proof_received_unverified',
        'lost_or_not_fit'
    )),
    improvement_suggestion text not null default '',
    campaign_source text not null default '',
    recorded_by text not null default 'sales_conversation_learning_loop',
    applies_learning_now boolean not null default false,
    changes_prompt_now boolean not null default false,
    changes_runtime_now boolean not null default false,
    sends_customer_message boolean not null default false,
    calls_chatwoot boolean not null default false,
    calls_n8n boolean not null default false,
    calls_meta boolean not null default false,
    creates_quote boolean not null default false,
    creates_invoice boolean not null default false,
    creates_order boolean not null default false,
    changes_stock boolean not null default false,
    reserves_stock boolean not null default false,
    dispatch_enabled boolean not null default false,
    physical_controls_enabled boolean not null default false,
    customer_public_output_enabled boolean not null default false,
    writes_farm_data boolean not null default false,
    created_at timestamptz not null default now(),
    constraint meat_sales_conversation_learning_no_authority_check check (
        applies_learning_now = false
        and changes_prompt_now = false
        and changes_runtime_now = false
        and sends_customer_message = false
        and calls_chatwoot = false
        and calls_n8n = false
        and calls_meta = false
        and creates_quote = false
        and creates_invoice = false
        and creates_order = false
        and changes_stock = false
        and reserves_stock = false
        and dispatch_enabled = false
        and physical_controls_enabled = false
        and customer_public_output_enabled = false
        and writes_farm_data = false
    )
);

create index if not exists idx_meat_sales_learning_lead_created
    on public.meat_sales_conversation_learning_events(lead_id, created_at desc);

create index if not exists idx_meat_sales_learning_conversation_created
    on public.meat_sales_conversation_learning_events(chatwoot_conversation_id, created_at desc);

create index if not exists idx_meat_sales_learning_type_created
    on public.meat_sales_conversation_learning_events(event_type, created_at desc);

create index if not exists idx_meat_sales_learning_conversion_created
    on public.meat_sales_conversation_learning_events(conversion_signal, created_at desc);

create or replace function public.prevent_meat_sales_conversation_learning_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'meat_sales_conversation_learning_events is append-only';
end;
$$;

drop trigger if exists prevent_meat_sales_learning_update on public.meat_sales_conversation_learning_events;
create trigger prevent_meat_sales_learning_update
    before update on public.meat_sales_conversation_learning_events
    for each row
    execute function public.prevent_meat_sales_conversation_learning_mutation();

drop trigger if exists prevent_meat_sales_learning_delete on public.meat_sales_conversation_learning_events;
create trigger prevent_meat_sales_learning_delete
    before delete on public.meat_sales_conversation_learning_events
    for each row
    execute function public.prevent_meat_sales_conversation_learning_mutation();
