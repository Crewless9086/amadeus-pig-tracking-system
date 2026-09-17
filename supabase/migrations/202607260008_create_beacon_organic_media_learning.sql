create table if not exists public.beacon_organic_media_learning_events (
    event_id text primary key check (
        length(event_id) between 1 and 200
        and event_id ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]*$'
    ),
    event_kind text not null check (event_kind in (
        'media_understanding', 'post_understanding',
        'performance_snapshot', 'graduation_evaluation',
        'confirmed_publication', 'policy_evaluation',
        'owner_usefulness_rating', 'publication_reliability'
    )),
    facebook_post_id text not null check (
        length(facebook_post_id) between 1 and 200
        and facebook_post_id ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]*$'
    ),
    channel text not null check (channel = 'Facebook'),
    objective text not null check (objective = 'farm_awareness'),
    measurement_window text not null default '' check (
        measurement_window in (
            '', 'publication_baseline', 'approximately_24_hours',
            '72_hours', '7_days'
        )
    ),
    evidence_key text not null unique check (
        length(evidence_key) between 1 and 200
        and evidence_key ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]*$'
    ),
    payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
    payload_json jsonb not null check (
        jsonb_typeof(payload_json) = 'object'
        and payload_json ->> 'event_kind' = event_kind
        and payload_json ->> 'facebook_post_id' = facebook_post_id
        and payload_json ->> 'channel' = channel
        and payload_json ->> 'objective' = objective
        and payload_json ->> 'measurement_window' = measurement_window
        and payload_json @> '{
          "publish": false, "retry": false, "schedule": false,
          "meta_write": false, "boost": false, "advertise": false,
          "spend": false, "send": false, "business_data_mutation": false
        }'::jsonb
    ),
    recommendation_only boolean not null default true check (recommendation_only),
    owner_review_candidate_only boolean not null default true check (owner_review_candidate_only),
    publish boolean not null default false check (not publish),
    retry boolean not null default false check (not retry),
    schedule boolean not null default false check (not schedule),
    meta_write boolean not null default false check (not meta_write),
    boost boolean not null default false check (not boost),
    advertise boolean not null default false check (not advertise),
    spend boolean not null default false check (not spend),
    send boolean not null default false check (not send),
    created_at timestamptz not null default now()
);

create or replace function public.prevent_beacon_organic_media_learning_mutation()
returns trigger language plpgsql as $$
begin
  raise exception 'Beacon organic media learning is append-only';
end;
$$;

drop trigger if exists prevent_beacon_organic_media_learning_update
on public.beacon_organic_media_learning_events;
create trigger prevent_beacon_organic_media_learning_update
before update on public.beacon_organic_media_learning_events
for each row execute function public.prevent_beacon_organic_media_learning_mutation();
drop trigger if exists prevent_beacon_organic_media_learning_delete
on public.beacon_organic_media_learning_events;
create trigger prevent_beacon_organic_media_learning_delete
before delete on public.beacon_organic_media_learning_events
for each row execute function public.prevent_beacon_organic_media_learning_mutation();

alter table public.beacon_organic_media_learning_events enable row level security;
revoke all on table public.beacon_organic_media_learning_events
from public, anon, authenticated, service_role;
grant select, insert on table public.beacon_organic_media_learning_events to service_role;
revoke all on function public.prevent_beacon_organic_media_learning_mutation()
from public, anon, authenticated, service_role;
