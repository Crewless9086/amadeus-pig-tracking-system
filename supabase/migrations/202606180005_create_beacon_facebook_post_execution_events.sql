create table if not exists public.beacon_facebook_post_execution_events (
    execution_event_id text primary key,
    mode text not null default 'beacon_facebook_page_post_execution_gate' check (mode = 'beacon_facebook_page_post_execution_gate'),
    publish_packet_id text not null default '',
    channel text not null default 'Facebook',
    exact_text text not null default '',
    owner_confirmation text not null default '',
    execution_status text not null default 'not_attempted' check (execution_status in (
        'not_attempted',
        'facebook_posting_disabled',
        'facebook_page_credentials_missing',
        'owner_confirmation_required',
        'publish_packet_id_required',
        'exact_text_required',
        'channel_not_facebook',
        'facebook_page_post_sent',
        'facebook_page_post_failed',
        'record_only_before_send'
    )),
    facebook_post_id text not null default '',
    facebook_response_json jsonb not null default '{}'::jsonb,
    records_evidence boolean not null default true,
    owner_exact_confirmation_required boolean not null default true,
    sends_customer_message boolean not null default false,
    posts_publicly boolean not null default true,
    calls_chatwoot boolean not null default false,
    calls_meta boolean not null default true,
    calls_n8n boolean not null default false,
    boosts_post boolean not null default false,
    spends_money boolean not null default false,
    creates_quote boolean not null default false,
    creates_invoice boolean not null default false,
    creates_order boolean not null default false,
    changes_stock boolean not null default false,
    reserves_stock boolean not null default false,
    dispatch_enabled boolean not null default false,
    changes_runtime_now boolean not null default false,
    changes_prompt_now boolean not null default false,
    physical_controls_enabled boolean not null default false,
    customer_public_output_enabled boolean not null default true,
    writes_farm_data boolean not null default false,
    recorded_by text not null default 'beacon_facebook_post_execution_gate',
    created_at timestamptz not null default now(),
    constraint beacon_facebook_post_execution_no_money_or_customer_dm check (
        records_evidence = true
        and owner_exact_confirmation_required = true
        and sends_customer_message = false
        and posts_publicly = true
        and calls_chatwoot = false
        and calls_meta = true
        and calls_n8n = false
        and boosts_post = false
        and spends_money = false
        and creates_quote = false
        and creates_invoice = false
        and creates_order = false
        and changes_stock = false
        and reserves_stock = false
        and dispatch_enabled = false
        and changes_runtime_now = false
        and changes_prompt_now = false
        and physical_controls_enabled = false
        and customer_public_output_enabled = true
        and writes_farm_data = false
    )
);

create index if not exists idx_beacon_facebook_post_execution_packet_created
    on public.beacon_facebook_post_execution_events(publish_packet_id, created_at desc);

create index if not exists idx_beacon_facebook_post_execution_status_created
    on public.beacon_facebook_post_execution_events(execution_status, created_at desc);

create or replace function public.prevent_beacon_facebook_post_execution_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'beacon facebook post execution evidence is append-only';
end;
$$;

drop trigger if exists prevent_beacon_facebook_post_execution_events_update on public.beacon_facebook_post_execution_events;
create trigger prevent_beacon_facebook_post_execution_events_update
    before update on public.beacon_facebook_post_execution_events
    for each row
    execute function public.prevent_beacon_facebook_post_execution_mutation();

drop trigger if exists prevent_beacon_facebook_post_execution_events_delete on public.beacon_facebook_post_execution_events;
create trigger prevent_beacon_facebook_post_execution_events_delete
    before delete on public.beacon_facebook_post_execution_events
    for each row
    execute function public.prevent_beacon_facebook_post_execution_mutation();
