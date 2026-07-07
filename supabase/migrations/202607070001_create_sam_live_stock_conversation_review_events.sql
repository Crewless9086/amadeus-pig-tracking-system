create table if not exists public.sam_live_stock_conversation_review_events (
    review_event_id text primary key,
    chatwoot_conversation_id text not null default '',
    chatwoot_message_id text not null default '',
    customer_name text not null default '',
    channel text not null default 'chatwoot',
    source_agent text not null default 'sam_live_stock_backend',
    event_source text not null default 'chatwoot_inbound',
    customer_message_excerpt text not null default '',
    sam_reply_excerpt text not null default '',
    score integer not null default 0,
    confidence_target integer not null default 96,
    safe_to_send boolean not null default false,
    owner_send_required boolean not null default false,
    no_reply_recommended boolean not null default false,
    escalation_required boolean not null default false,
    conversation_mode_recommendation text not null default 'AUTO',
    recommended_action text not null default '',
    review_json jsonb not null default '{}'::jsonb,
    facts_json jsonb not null default '{}'::jsonb,
    decision_json jsonb not null default '{}'::jsonb,
    applies_learning_now boolean not null default false,
    changes_prompt_now boolean not null default false,
    changes_runtime_now boolean not null default false,
    sends_customer_message boolean not null default false,
    calls_chatwoot boolean not null default false,
    calls_telegram boolean not null default false,
    creates_order boolean not null default false,
    reserves_stock boolean not null default false,
    changes_stock boolean not null default false,
    writes_farm_data boolean not null default false,
    created_at timestamptz not null default now(),
    constraint sam_live_stock_review_no_authority_check check (
        applies_learning_now = false
        and changes_prompt_now = false
        and changes_runtime_now = false
        and sends_customer_message = false
        and calls_chatwoot = false
        and calls_telegram = false
        and creates_order = false
        and reserves_stock = false
        and changes_stock = false
        and writes_farm_data = false
    )
);

create index if not exists idx_sam_live_stock_review_conversation_created
    on public.sam_live_stock_conversation_review_events(chatwoot_conversation_id, created_at desc);

create index if not exists idx_sam_live_stock_review_score_created
    on public.sam_live_stock_conversation_review_events(score, created_at desc);

create index if not exists idx_sam_live_stock_review_escalation_created
    on public.sam_live_stock_conversation_review_events(escalation_required, created_at desc);

create or replace function public.prevent_sam_live_stock_review_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'sam_live_stock_conversation_review_events is append-only';
end;
$$;

drop trigger if exists prevent_sam_live_stock_review_update on public.sam_live_stock_conversation_review_events;
create trigger prevent_sam_live_stock_review_update
    before update on public.sam_live_stock_conversation_review_events
    for each row
    execute function public.prevent_sam_live_stock_review_mutation();

drop trigger if exists prevent_sam_live_stock_review_delete on public.sam_live_stock_conversation_review_events;
create trigger prevent_sam_live_stock_review_delete
    before delete on public.sam_live_stock_conversation_review_events
    for each row
    execute function public.prevent_sam_live_stock_review_mutation();
