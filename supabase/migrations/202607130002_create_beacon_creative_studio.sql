-- Additive schema only. This migration must not be applied without separate owner approval.

alter table public.beacon_media_assets
    add column if not exists content_sha256 text not null default '',
    add column if not exists content_hash_provenance text not null default '';

alter table public.beacon_media_assets
    drop constraint if exists beacon_media_assets_media_type_check;
alter table public.beacon_media_assets
    add constraint beacon_media_assets_media_type_check
    check (media_type in ('image', 'video', 'audio', 'document', 'unknown'));

alter table public.beacon_media_assets
    drop constraint if exists beacon_media_assets_source_check;
alter table public.beacon_media_assets
    add constraint beacon_media_assets_source_check
    check (source in ('farm_app_upload', 'telegram_upload', 'folder_import', 'whatsapp_media',
                      'owner_note', 'creative_studio_mock', 'other'));

create table if not exists public.beacon_creative_jobs (
    job_id text primary key,
    idempotency_key text not null unique,
    request_sha256 text not null check (request_sha256 ~ '^[0-9a-f]{64}$'),
    provider text not null check (provider in ('elevenlabs', 'happy_horse_1_0')),
    exact_prompt text not null check (length(btrim(exact_prompt)) > 0),
    prompt_sha256 text not null check (prompt_sha256 ~ '^[0-9a-f]{64}$'),
    parameters_json jsonb not null default '{}'::jsonb,
    parameters_canonical_json text not null,
    parameters_sha256 text not null check (parameters_sha256 ~ '^[0-9a-f]{64}$'),
    source_lineage_sha256 text not null check (source_lineage_sha256 ~ '^[0-9a-f]{64}$'),
    recorded_by text not null check (recorded_by = 'authenticated_owner_admin'),
    provider_enabled boolean not null default false check (provider_enabled = false),
    network_enabled boolean not null default false check (network_enabled = false),
    credential_access boolean not null default false check (credential_access = false),
    source_transfer boolean not null default false check (source_transfer = false),
    spends_money boolean not null default false check (spends_money = false),
    posts_publicly boolean not null default false check (posts_publicly = false),
    sends_customer_message boolean not null default false check (sends_customer_message = false),
    writes_farm_data boolean not null default false check (writes_farm_data = false),
    created_at timestamptz not null default now()
);

create table if not exists public.beacon_creative_job_sources (
    job_source_id bigint generated always as identity primary key,
    job_id text not null references public.beacon_creative_jobs(job_id),
    asset_id text not null references public.beacon_media_assets(asset_id),
    source_position integer not null check (source_position >= 0),
    content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz not null default now(),
    unique (job_id, asset_id),
    unique (job_id, source_position)
);

create table if not exists public.beacon_creative_provider_attempts (
    attempt_id text primary key,
    job_id text not null references public.beacon_creative_jobs(job_id),
    provider text not null check (provider in ('elevenlabs', 'happy_horse_1_0')),
    model_identifier text not null default 'provider-disabled-mock-v1',
    manifest_json jsonb not null,
    manifest_sha256 text not null check (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    provider_enabled boolean not null default false check (provider_enabled = false),
    network_enabled boolean not null default false check (network_enabled = false),
    credential_access boolean not null default false check (credential_access = false),
    source_transfer boolean not null default false check (source_transfer = false),
    actual_cost numeric(14,4) not null default 0 check (actual_cost = 0),
    created_at timestamptz not null default now()
);

create table if not exists public.beacon_creative_cost_events (
    cost_event_id text primary key,
    attempt_id text not null references public.beacon_creative_provider_attempts(attempt_id),
    estimated_cost numeric(14,4) not null default 0 check (estimated_cost >= 0),
    actual_cost numeric(14,4) not null default 0 check (actual_cost = 0),
    currency text not null default 'ZAR',
    estimate_source text not null check (length(btrim(estimate_source)) > 0),
    recorded_by text not null check (recorded_by = 'authenticated_owner_admin'),
    created_at timestamptz not null default now()
);

create table if not exists public.beacon_creative_variants (
    variant_id text primary key,
    attempt_id text not null references public.beacon_creative_provider_attempts(attempt_id),
    asset_id text not null references public.beacon_media_assets(asset_id),
    storage_bucket text not null check (storage_bucket = 'beacon-raw-intake'),
    storage_path text not null,
    media_type text not null check (media_type in ('audio', 'video')),
    mime_type text not null,
    content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
    approval_status text not null default 'needs_review' check (approval_status = 'needs_review'),
    public_use_approved boolean not null default false check (public_use_approved = false),
    campaign_selectable boolean not null default false check (campaign_selectable = false),
    created_at timestamptz not null default now()
);

create table if not exists public.beacon_creative_review_events (
    review_event_id text primary key,
    job_id text not null references public.beacon_creative_jobs(job_id),
    review_type text not null check (review_type in (
        'brand', 'privacy', 'safety', 'animal_product_fidelity',
        'provider_disclosure', 'evaluation', 'owner_public_use'
    )),
    decision text not null check (decision in ('approved', 'rejected')),
    notes text not null default '',
    recorded_by text not null check (recorded_by = 'authenticated_owner_admin'),
    approval_executes_action boolean not null default false check (approval_executes_action = false),
    provider_enabled boolean not null default false check (provider_enabled = false),
    spends_money boolean not null default false check (spends_money = false),
    posts_publicly boolean not null default false check (posts_publicly = false),
    schedules_publication boolean not null default false check (schedules_publication = false),
    sends_customer_message boolean not null default false check (sends_customer_message = false),
    writes_farm_data boolean not null default false check (writes_farm_data = false),
    created_at timestamptz not null default now()
);

create index if not exists idx_beacon_creative_jobs_created
    on public.beacon_creative_jobs(created_at desc);
create index if not exists idx_beacon_creative_reviews_job_type_created
    on public.beacon_creative_review_events(job_id, review_type, created_at desc);

create or replace function public.prevent_beacon_creative_record_mutation()
returns trigger language plpgsql as $$
begin
    raise exception 'Beacon Creative Studio records are append-only';
end;
$$;

do $$
declare table_name text;
begin
    foreach table_name in array array[
        'beacon_creative_jobs', 'beacon_creative_job_sources',
        'beacon_creative_provider_attempts', 'beacon_creative_cost_events',
        'beacon_creative_variants', 'beacon_creative_review_events'
    ] loop
        execute format('drop trigger if exists %I on public.%I', 'prevent_' || table_name || '_update', table_name);
        execute format('create trigger %I before update on public.%I for each row execute function public.prevent_beacon_creative_record_mutation()', 'prevent_' || table_name || '_update', table_name);
        execute format('drop trigger if exists %I on public.%I', 'prevent_' || table_name || '_delete', table_name);
        execute format('create trigger %I before delete on public.%I for each row execute function public.prevent_beacon_creative_record_mutation()', 'prevent_' || table_name || '_delete', table_name);
    end loop;
end;
$$;
