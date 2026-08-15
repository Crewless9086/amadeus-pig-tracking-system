alter table public.beacon_media_library_events
  add column if not exists intake_group_id text references public.beacon_media_intake_groups(intake_group_id),
  add column if not exists album_review_contract_version text,
  add column if not exists album_digest_sha256 text,
  add column if not exists album_position integer,
  add column if not exists album_decision_type text,
  add column if not exists approved_use_scope text,
  add column if not exists understanding_event_id text references public.beacon_media_understanding_events(observation_event_id);

alter table public.beacon_media_library_events
  add constraint beacon_media_library_events_album_envelope_check check (
    (intake_group_id is null and album_review_contract_version is null
      and album_digest_sha256 is null and album_position is null and album_decision_type is null
      and approved_use_scope is null and understanding_event_id is null)
    or
    (intake_group_id is not null
      and album_review_contract_version = 'beacon_private_album_review_v1'
      and album_digest_sha256 ~ '^[0-9a-f]{64}$'
      and album_position > 0
      and understanding_event_id is not null
      and album_decision_type in ('library','public_use')
      and ((album_decision_type = 'library' and approved_use_scope is null)
        or (album_decision_type = 'public_use'
          and approved_use_scope = 'organic_farm_awareness_only')))
  );

create index if not exists idx_beacon_media_library_events_album_position
  on public.beacon_media_library_events(intake_group_id, album_digest_sha256, album_position);

revoke all on public.beacon_media_library_events from public, anon, authenticated;

insert into app_private.migration_log(migration_id,description)
values('202608150008_add_beacon_album_review_envelope',
 'Bind album Library/public-use decisions to exact album version, digest, order and approved scope')
on conflict(migration_id) do nothing;
