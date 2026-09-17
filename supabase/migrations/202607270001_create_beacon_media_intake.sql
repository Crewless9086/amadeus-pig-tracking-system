-- BEACON-MEDIA-INTAKE-1: additive, private, append-only Telegram provenance.
-- Applying this migration is a separate production authorization.

create table public.beacon_media_intake_groups (
    intake_group_id text primary key,
    contract_version text not null check (contract_version = 'beacon_media_intake_v1'),
    source_channel text not null check (source_channel = 'telegram_owner_private'),
    owner_principal text not null,
    private_chat_identity_hmac text not null check (length(private_chat_identity_hmac) = 64),
    telegram_update_id bigint not null,
    telegram_message_id bigint not null,
    telegram_media_group_id text,
    owner_explanation text not null default '',
    source_message_at timestamptz not null,
    capture_time timestamptz,
    capture_time_state text not null check (capture_time_state in ('unknown', 'approximate', 'exact_owner_confirmed')),
    intake_at timestamptz not null default now(),
    completion_mode text not null check (completion_mode in ('single_item', 'explicit_owner_album_completion')),
    completion_code_sha256 text unique check (
        completion_code_sha256 is null or length(completion_code_sha256) = 64
    ),
    publish boolean not null default false check (publish = false),
    public_use_approved boolean not null default false check (public_use_approved = false),
    meta_call boolean not null default false check (meta_call = false),
    send boolean not null default false check (send = false),
    advertise boolean not null default false check (advertise = false),
    boost boolean not null default false check (boost = false),
    spend boolean not null default false check (spend = false),
    unique (private_chat_identity_hmac, telegram_update_id),
    unique (private_chat_identity_hmac, telegram_message_id)
);

create table public.beacon_media_intake_items (
    intake_item_id text primary key,
    intake_group_id text not null references public.beacon_media_intake_groups(intake_group_id),
    source_identity_sha256 text not null unique check (length(source_identity_sha256) = 64),
    private_chat_identity_hmac text not null check (length(private_chat_identity_hmac) = 64),
    telegram_update_id bigint not null,
    telegram_message_id bigint not null,
    telegram_file_id text not null,
    telegram_file_unique_id text,
    original_filename text not null default '',
    declared_mime_type text not null default '',
    media_kind text not null check (media_kind in ('photo', 'video')),
    source_order_key bigint not null,
    capture_time timestamptz,
    capture_time_state text not null check (capture_time_state in ('unknown', 'approximate', 'exact_owner_confirmed')),
    created_at timestamptz not null default now(),
    unique (intake_group_id, source_order_key),
    unique (private_chat_identity_hmac, telegram_update_id),
    unique (private_chat_identity_hmac, telegram_message_id)
);

create table public.beacon_media_intake_album_members (
    intake_group_id text not null references public.beacon_media_intake_groups(intake_group_id),
    intake_item_id text not null unique references public.beacon_media_intake_items(intake_item_id),
    album_position integer not null check (album_position > 0),
    recorded_at timestamptz not null default now(),
    primary key (intake_group_id, album_position)
);

create table public.beacon_media_binaries (
    binary_asset_id text primary key,
    content_sha256 text not null unique check (length(content_sha256) = 64),
    observed_mime_type text not null check (observed_mime_type in ('image/jpeg', 'image/png')),
    byte_size bigint not null check (byte_size > 0 and byte_size <= 8388608),
    width integer not null check (width > 0 and width <= 12000),
    height integer not null check (height > 0 and height <= 12000),
    duration_seconds numeric,
    perceptual_hash text,
    storage_bucket text not null check (storage_bucket = 'beacon-raw-intake'),
    storage_path text not null unique,
    storage_readback_sha256 text not null check (storage_readback_sha256 = content_sha256),
    thumbnail_storage_path text,
    thumbnail_sha256 text,
    validation_version text not null,
    created_at timestamptz not null default now(),
    check ((width::bigint * height::bigint) <= 40000000),
    check ((thumbnail_storage_path is null) = (thumbnail_sha256 is null))
);

create table public.beacon_media_source_links (
    source_link_id text primary key,
    intake_item_id text not null unique references public.beacon_media_intake_items(intake_item_id),
    binary_asset_id text not null references public.beacon_media_binaries(binary_asset_id),
    beacon_asset_id text references public.beacon_media_assets(asset_id),
    exact_duplicate_of_item_id text references public.beacon_media_intake_items(intake_item_id),
    linked_at timestamptz not null default now()
);

create table public.beacon_media_intake_events (
    event_id text primary key,
    intake_group_id text not null references public.beacon_media_intake_groups(intake_group_id),
    intake_item_id text references public.beacon_media_intake_items(intake_item_id),
    event_type text not null check (event_type in (
        'pending', 'stream_validated', 'storage_uploaded', 'storage_verified',
        'stored', 'failed', 'quarantined', 'album_completed',
        'album_completion_offered',
        'reconciliation_required', 'reconciled'
    )),
    evidence_sha256 text not null check (length(evidence_sha256) = 64),
    evidence_json jsonb not null,
    recorded_at timestamptz not null default now(),
    unique (intake_item_id, event_type, evidence_sha256)
);

create table public.beacon_media_understanding_events (
    observation_event_id text primary key,
    binary_asset_id text not null references public.beacon_media_binaries(binary_asset_id),
    asset_sha256 text not null check (length(asset_sha256) = 64),
    source_type text not null check (source_type in ('owner_context', 'model_observation', 'manual_review')),
    observer_identity text not null,
    observer_version text not null,
    confidence_state text not null check (confidence_state in ('unavailable', 'suggested', 'evidence_supported', 'owner_confirmed')),
    observation_json jsonb not null,
    observed_at timestamptz not null,
    check (asset_sha256 = lower(asset_sha256))
);

create table public.beacon_media_library_events (
    library_event_id text primary key,
    binary_asset_id text not null references public.beacon_media_binaries(binary_asset_id),
    event_type text not null check (event_type in (
        'library_accepted', 'library_rejected', 'archived',
        'owner_context_recorded', 'public_use_approved', 'public_use_revoked'
    )),
    owner_principal text not null,
    owner_action_id text not null,
    decision_identity_sha256 text not null check (length(decision_identity_sha256) = 64),
    notes text not null default '',
    predecessor_event_id text references public.beacon_media_library_events(library_event_id),
    public_use_approved boolean not null default false check (public_use_approved = false),
    publish boolean not null default false check (publish = false),
    recorded_at timestamptz not null default now(),
    unique (binary_asset_id, owner_principal, owner_action_id),
    unique (binary_asset_id, event_type, decision_identity_sha256)
);

create index idx_beacon_media_intake_items_group_order
    on public.beacon_media_intake_items(intake_group_id, source_order_key);
create index idx_beacon_media_intake_events_group_time
    on public.beacon_media_intake_events(intake_group_id, recorded_at desc);
create index idx_beacon_media_source_links_binary
    on public.beacon_media_source_links(binary_asset_id);
create index idx_beacon_media_library_events_binary_time
    on public.beacon_media_library_events(binary_asset_id, recorded_at desc);
create index idx_beacon_media_understanding_binary_time
    on public.beacon_media_understanding_events(binary_asset_id, observed_at desc);

create view public.beacon_media_intake_current_state
with (security_invoker = true) as
select g.intake_group_id, g.intake_at, g.owner_explanation,
       count(distinct i.intake_item_id) as received_count,
       count(distinct case when e.event_type = 'stored' then i.intake_item_id end) as stored_count,
       count(distinct case when e.event_type in ('failed', 'quarantined', 'reconciliation_required')
                           then i.intake_item_id end) as attention_count,
       bool_or(e.event_type = 'album_completed') as album_completed
from public.beacon_media_intake_groups g
left join public.beacon_media_intake_items i using (intake_group_id)
left join public.beacon_media_intake_events e using (intake_group_id)
group by g.intake_group_id, g.intake_at, g.owner_explanation;

create function public.prevent_beacon_media_intake_mutation()
returns trigger language plpgsql set search_path = pg_catalog, public as $$
begin
    raise exception 'BEACON media intake evidence is append-only';
end;
$$;

do $$
declare table_name text;
begin
  foreach table_name in array array[
    'beacon_media_intake_groups', 'beacon_media_intake_items',
    'beacon_media_intake_album_members', 'beacon_media_binaries',
    'beacon_media_source_links', 'beacon_media_intake_events',
    'beacon_media_understanding_events', 'beacon_media_library_events'
  ] loop
    execute format('create trigger %I before update or delete on public.%I for each row execute function public.prevent_beacon_media_intake_mutation()',
                   'prevent_' || table_name || '_mutation', table_name);
    execute format('alter table public.%I enable row level security', table_name);
    execute format('revoke all on table public.%I from public', table_name);
    execute format('revoke all on table public.%I from anon', table_name);
    execute format('revoke all on table public.%I from authenticated', table_name);
    execute format('revoke all on table public.%I from service_role', table_name);
    execute format('grant select, insert on table public.%I to service_role', table_name);
  end loop;
end;
$$;

revoke all on table public.beacon_media_intake_current_state from public, anon, authenticated;
grant select on table public.beacon_media_intake_current_state to service_role;
revoke all on function public.prevent_beacon_media_intake_mutation() from public, anon, authenticated, service_role;
