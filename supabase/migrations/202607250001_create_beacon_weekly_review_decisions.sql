create table if not exists public.beacon_weekly_review_decision_events (
    decision_event_id text primary key,
    packet_id text not null,
    packet_version text not null,
    canonical_sha256 text not null check (canonical_sha256 ~ '^[0-9a-f]{64}$'),
    caption_sha256 text not null check (caption_sha256 ~ '^[0-9a-f]{64}$'),
    exact_caption text not null,
    ordered_media_ids_json jsonb not null,
    owner_confirmed_subject text not null,
    album_story text not null,
    channel text not null,
    proposed_publication_datetime text not null default '',
    proposed_timezone text not null default '',
    supersedes_packet_id text not null default '',
    decision_status text not null check (decision_status in (
        'owner_approved', 'changes_requested', 'owner_rejected'
    )),
    owner_notes text not null default '',
    owner_identity text not null,
    decision_at timestamptz not null default now(),
    publication_authority_status text not null default 'publication_not_authorized'
        check (publication_authority_status = 'publication_not_authorized'),
    publish boolean not null default false check (publish = false),
    meta_call boolean not null default false check (meta_call = false),
    upload boolean not null default false check (upload = false),
    scheduled boolean not null default false check (scheduled = false),
    send boolean not null default false check (send = false),
    spend boolean not null default false check (spend = false),
    business_data_mutation boolean not null default false
        check (business_data_mutation = false),
    created_at timestamptz not null default now(),
    unique (packet_id)
);

create index if not exists idx_beacon_weekly_review_decisions_created
    on public.beacon_weekly_review_decision_events(created_at desc);

create or replace function public.prevent_beacon_weekly_review_decision_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'Beacon weekly review decisions are append-only';
end;
$$;

drop trigger if exists prevent_beacon_weekly_review_decisions_update
    on public.beacon_weekly_review_decision_events;
create trigger prevent_beacon_weekly_review_decisions_update
    before update on public.beacon_weekly_review_decision_events
    for each row execute function public.prevent_beacon_weekly_review_decision_mutation();

drop trigger if exists prevent_beacon_weekly_review_decisions_delete
    on public.beacon_weekly_review_decision_events;
create trigger prevent_beacon_weekly_review_decisions_delete
    before delete on public.beacon_weekly_review_decision_events
    for each row execute function public.prevent_beacon_weekly_review_decision_mutation();

-- Browser/client roles must never bypass the owner-admin application route.
alter table public.beacon_weekly_review_decision_events enable row level security;

revoke all privileges on table
    public.beacon_weekly_review_decision_events
    from public, anon, authenticated;
revoke all privileges on table
    public.beacon_weekly_review_decision_events
    from service_role;
grant select, insert on table
    public.beacon_weekly_review_decision_events
    to service_role;

revoke all privileges on function
    public.prevent_beacon_weekly_review_decision_mutation()
    from public, anon, authenticated;
grant execute on function
    public.prevent_beacon_weekly_review_decision_mutation()
    to service_role;
