create table if not exists public.beacon_media_assets (
    asset_id text primary key,
    mode text not null default 'beacon_media_asset_metadata_only' check (mode = 'beacon_media_asset_metadata_only'),
    storage_bucket text not null default 'beacon-raw-intake',
    storage_path text not null default '',
    original_filename text not null default '',
    media_type text not null default 'unknown' check (media_type in ('image', 'video', 'document', 'unknown')),
    mime_type text not null default '',
    file_size_bytes bigint not null default 0 check (file_size_bytes >= 0),
    source text not null default 'farm_app_upload' check (source in (
        'farm_app_upload',
        'telegram_upload',
        'folder_import',
        'whatsapp_media',
        'owner_note',
        'other'
    )),
    source_reference text not null default '',
    uploader_label text not null default '',
    title text not null default '',
    description text not null default '',
    sale_stream_relevance_json jsonb not null default '[]'::jsonb,
    subject_tags_json jsonb not null default '[]'::jsonb,
    location_context text not null default '',
    quality_score integer check (quality_score is null or (quality_score >= 0 and quality_score <= 100)),
    privacy_risk text not null default 'unknown' check (privacy_risk in ('unknown', 'low', 'medium', 'high')),
    safety_flags_json jsonb not null default '[]'::jsonb,
    public_use_approved boolean not null default false,
    approval_status text not null default 'needs_review' check (approval_status in (
        'needs_review',
        'approved',
        'rejected',
        'archived'
    )),
    campaign_usage_count integer not null default 0 check (campaign_usage_count >= 0),
    notes text not null default '',
    created_by text not null default 'beacon_media_library',
    sends_customer_message boolean not null default false,
    posts_publicly boolean not null default false,
    calls_chatwoot boolean not null default false,
    calls_meta boolean not null default false,
    calls_n8n boolean not null default false,
    creates_quote boolean not null default false,
    creates_invoice boolean not null default false,
    creates_order boolean not null default false,
    changes_stock boolean not null default false,
    reserves_stock boolean not null default false,
    dispatch_enabled boolean not null default false,
    changes_runtime_now boolean not null default false,
    changes_prompt_now boolean not null default false,
    physical_controls_enabled boolean not null default false,
    customer_public_output_enabled boolean not null default false,
    writes_farm_data boolean not null default false,
    created_at timestamptz not null default now(),
    constraint beacon_media_assets_no_public_or_customer_authority check (
        sends_customer_message = false
        and posts_publicly = false
        and calls_chatwoot = false
        and calls_meta = false
        and calls_n8n = false
        and creates_quote = false
        and creates_invoice = false
        and creates_order = false
        and changes_stock = false
        and reserves_stock = false
        and dispatch_enabled = false
        and changes_runtime_now = false
        and changes_prompt_now = false
        and physical_controls_enabled = false
        and customer_public_output_enabled = false
        and writes_farm_data = false
    )
);

create table if not exists public.beacon_media_asset_events (
    event_id text primary key,
    asset_id text not null references public.beacon_media_assets(asset_id),
    event_type text not null check (event_type in (
        'intake_registered',
        'review_note',
        'approved_public_use',
        'rejected_public_use',
        'archived',
        'tags_updated',
        'quality_reviewed',
        'campaign_usage_observed'
    )),
    notes text not null default '',
    recorded_by text not null default 'beacon_media_library',
    approval_status text not null default '',
    public_use_approved boolean not null default false,
    sale_stream_relevance_json jsonb not null default '[]'::jsonb,
    subject_tags_json jsonb not null default '[]'::jsonb,
    quality_score integer check (quality_score is null or (quality_score >= 0 and quality_score <= 100)),
    privacy_risk text not null default '' check (privacy_risk in ('', 'unknown', 'low', 'medium', 'high')),
    safety_flags_json jsonb not null default '[]'::jsonb,
    campaign_id text not null default '',
    sends_customer_message boolean not null default false,
    posts_publicly boolean not null default false,
    calls_chatwoot boolean not null default false,
    calls_meta boolean not null default false,
    calls_n8n boolean not null default false,
    creates_quote boolean not null default false,
    creates_invoice boolean not null default false,
    creates_order boolean not null default false,
    changes_stock boolean not null default false,
    reserves_stock boolean not null default false,
    dispatch_enabled boolean not null default false,
    changes_runtime_now boolean not null default false,
    changes_prompt_now boolean not null default false,
    physical_controls_enabled boolean not null default false,
    customer_public_output_enabled boolean not null default false,
    writes_farm_data boolean not null default false,
    created_at timestamptz not null default now(),
    constraint beacon_media_asset_events_no_public_or_customer_authority check (
        sends_customer_message = false
        and posts_publicly = false
        and calls_chatwoot = false
        and calls_meta = false
        and calls_n8n = false
        and creates_quote = false
        and creates_invoice = false
        and creates_order = false
        and changes_stock = false
        and reserves_stock = false
        and dispatch_enabled = false
        and changes_runtime_now = false
        and changes_prompt_now = false
        and physical_controls_enabled = false
        and customer_public_output_enabled = false
        and writes_farm_data = false
    )
);

create index if not exists idx_beacon_media_assets_created
    on public.beacon_media_assets(created_at desc);

create index if not exists idx_beacon_media_assets_approval_created
    on public.beacon_media_assets(approval_status, created_at desc);

create index if not exists idx_beacon_media_assets_media_type_created
    on public.beacon_media_assets(media_type, created_at desc);

create index if not exists idx_beacon_media_asset_events_asset_created
    on public.beacon_media_asset_events(asset_id, created_at desc);

create index if not exists idx_beacon_media_asset_events_type_created
    on public.beacon_media_asset_events(event_type, created_at desc);

create or replace function public.prevent_beacon_media_asset_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'beacon media library records are append-only in this phase';
end;
$$;

drop trigger if exists prevent_beacon_media_assets_update on public.beacon_media_assets;
create trigger prevent_beacon_media_assets_update
    before update on public.beacon_media_assets
    for each row
    execute function public.prevent_beacon_media_asset_mutation();

drop trigger if exists prevent_beacon_media_assets_delete on public.beacon_media_assets;
create trigger prevent_beacon_media_assets_delete
    before delete on public.beacon_media_assets
    for each row
    execute function public.prevent_beacon_media_asset_mutation();

drop trigger if exists prevent_beacon_media_asset_events_update on public.beacon_media_asset_events;
create trigger prevent_beacon_media_asset_events_update
    before update on public.beacon_media_asset_events
    for each row
    execute function public.prevent_beacon_media_asset_mutation();

drop trigger if exists prevent_beacon_media_asset_events_delete on public.beacon_media_asset_events;
create trigger prevent_beacon_media_asset_events_delete
    before delete on public.beacon_media_asset_events
    for each row
    execute function public.prevent_beacon_media_asset_mutation();
