-- Admit the existing HERDMASTER farrowing executor through the canonical
-- protected-action spine.  This is an append-only schema migration: it does
-- not create a claim, record a litter, or mutate any farm fact.

do $$
declare
  constraint_oid oid;
  current_action_kinds text[];
  predecessor_action_kinds constant text[] := array[
    'beacon_campaign_review',
    'beacon_media_review',
    'beacon_private_album_finish',
    'documents_green_physical_acceptance',
    'documents_green_print',
    'grouped_weights',
    'herdmaster_breeding_grouped',
    'mortality',
    'rootline_delegated_family',
    'rootline_fertilizer_mixer_commissioning',
    'rootline_fertilizer_mixer_presence_refresh',
    'rootline_irrigation_segment',
    'sam_sale_payment'
  ]::text[];
  target_action_kinds constant text[] := array[
    'beacon_campaign_review',
    'beacon_media_review',
    'beacon_private_album_finish',
    'documents_green_physical_acceptance',
    'documents_green_print',
    'grouped_weights',
    'herdmaster_breeding_grouped',
    'herdmaster_record_farrowing_litter',
    'mortality',
    'rootline_delegated_family',
    'rootline_fertilizer_mixer_commissioning',
    'rootline_fertilizer_mixer_presence_refresh',
    'rootline_irrigation_segment',
    'sam_sale_payment'
  ]::text[];
begin
  select c.oid into constraint_oid
    from pg_catalog.pg_constraint c
    join pg_catalog.pg_class t on t.oid = c.conrelid
    join pg_catalog.pg_namespace n on n.oid = t.relnamespace
   where n.nspname = 'app_private'
     and t.relname = 'oom_protected_action_claims'
     and c.contype = 'c'
     and c.conname = 'oom_protected_action_claims_action_kind_check';

  if constraint_oid is null then
    raise exception 'canonical protected action-kind constraint is missing';
  end if;

  select array_agg(action_kind order by action_kind)
    into current_action_kinds
    from (
      select distinct (matches.value)[1] as action_kind
        from regexp_matches(
          pg_catalog.pg_get_constraintdef(constraint_oid),
          '''([^'']+)''',
          'g'
        ) as matches(value)
    ) extracted;

  if current_action_kinds = target_action_kinds then
    -- Exact direct-SQL replay: retain the already-applied target unchanged.
    null;
  elsif current_action_kinds = predecessor_action_kinds then
    alter table app_private.oom_protected_action_claims
      drop constraint oom_protected_action_claims_action_kind_check;
    alter table app_private.oom_protected_action_claims
      add constraint oom_protected_action_claims_action_kind_check
      check (action_kind in (
        'mortality',
        'grouped_weights',
        'herdmaster_breeding_grouped',
        'herdmaster_record_farrowing_litter',
        'rootline_irrigation_segment',
        'sam_sale_payment',
        'beacon_private_album_finish',
        'beacon_media_review',
        'rootline_fertilizer_mixer_commissioning',
        'rootline_fertilizer_mixer_presence_refresh',
        'rootline_delegated_family',
        'beacon_campaign_review',
        'documents_green_print',
        'documents_green_physical_acceptance'
      ));
  else
    raise exception 'canonical protected action-kind constraint mismatch: %',
      current_action_kinds;
  end if;
end
$$;

revoke all on app_private.oom_protected_action_claims
  from public, anon, authenticated;

insert into app_private.migration_log(migration_id, description)
values (
  '202608220002_allow_herdmaster_farrowing_protected_claims',
  'Admit exact-preview HERDMASTER farrowing claims through the canonical protected action spine.'
)
on conflict(migration_id) do nothing;
