create table if not exists public.beacon_organic_publication_authorization_events (
    authorization_event_id text primary key,
    authorization_version text not null,
    authorization_generation_id text not null,
    binding_id text not null references public.beacon_organic_publication_bindings(binding_id),
    event_status text not null check (event_status in (
        'awaiting_owner_authorization', 'owner_authorized',
        'closed_pre_meta_caption_drift', 'attempt_claimed',
        'contained', 'confirmed'
    )),
    transport_sha256 text not null check (transport_sha256 ~ '^[0-9a-f]{64}$'),
    payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
    expected_attempt_identity text not null,
    predecessor_generation_id text not null default '',
    reason text not null default '',
    created_at timestamptz not null default now(),
    unique (authorization_generation_id, event_status)
);

create or replace function public.prevent_beacon_publication_authorization_mutation()
returns trigger language plpgsql as $$
begin
    raise exception 'Beacon organic publication authorizations are append-only';
end;
$$;

drop trigger if exists prevent_beacon_publication_authorizations_update
    on public.beacon_organic_publication_authorization_events;
create trigger prevent_beacon_publication_authorizations_update
    before update on public.beacon_organic_publication_authorization_events
    for each row execute function public.prevent_beacon_publication_authorization_mutation();
drop trigger if exists prevent_beacon_publication_authorizations_delete
    on public.beacon_organic_publication_authorization_events;
create trigger prevent_beacon_publication_authorizations_delete
    before delete on public.beacon_organic_publication_authorization_events
    for each row execute function public.prevent_beacon_publication_authorization_mutation();

alter table public.beacon_organic_publication_authorization_events enable row level security;
revoke all privileges on table public.beacon_organic_publication_authorization_events
    from public, anon, authenticated, service_role;
grant select, insert on table public.beacon_organic_publication_authorization_events
    to service_role;
revoke all privileges on function
    public.prevent_beacon_publication_authorization_mutation()
    from public, anon, authenticated;
grant execute on function
    public.prevent_beacon_publication_authorization_mutation()
    to service_role;
