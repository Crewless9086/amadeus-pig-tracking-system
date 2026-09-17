create table if not exists public.beacon_organic_publication_bindings (
    binding_id text primary key,
    binding_version text not null,
    weekly_packet_id text not null unique,
    owner_decision_event_id text not null unique references
        public.beacon_weekly_review_decision_events(decision_event_id),
    execution_publish_packet_id text not null unique,
    canonical_sha256 text not null check (canonical_sha256 ~ '^[0-9a-f]{64}$'),
    caption_sha256 text not null check (caption_sha256 ~ '^[0-9a-f]{64}$'),
    media_order_sha256 text not null check (media_order_sha256 ~ '^[0-9a-f]{64}$'),
    exact_media_order_json jsonb not null,
    owner_confirmed_subject text not null,
    channel text not null,
    target_page_id text not null,
    bound_at timestamptz not null,
    created_at timestamptz not null default now()
);

create or replace function public.prevent_beacon_publication_binding_mutation()
returns trigger language plpgsql as $$
begin
    raise exception 'Beacon organic publication bindings are append-only';
end;
$$;

drop trigger if exists prevent_beacon_publication_bindings_update
    on public.beacon_organic_publication_bindings;
create trigger prevent_beacon_publication_bindings_update
    before update on public.beacon_organic_publication_bindings
    for each row execute function public.prevent_beacon_publication_binding_mutation();
drop trigger if exists prevent_beacon_publication_bindings_delete
    on public.beacon_organic_publication_bindings;
create trigger prevent_beacon_publication_bindings_delete
    before delete on public.beacon_organic_publication_bindings
    for each row execute function public.prevent_beacon_publication_binding_mutation();

alter table public.beacon_organic_publication_bindings enable row level security;
revoke all privileges on table public.beacon_organic_publication_bindings
    from public, anon, authenticated;
revoke all privileges on table public.beacon_organic_publication_bindings
    from service_role;
grant select, insert on table public.beacon_organic_publication_bindings
    to service_role;
revoke all privileges on function
    public.prevent_beacon_publication_binding_mutation()
    from public, anon, authenticated;
grant execute on function
    public.prevent_beacon_publication_binding_mutation()
    to service_role;
