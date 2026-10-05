-- Admit the shared HERDMASTER purpose review and correction adapter through the canonical
-- protected-action spine.  This is an append-only schema migration: it does
-- not create a claim, record a litter, or mutate any farm fact.

do $$
declare
  constraint_oid oid;
  current_constraint_definition text;
  current_action_kinds text[];
  matched_target_action_kinds text[];
  target_sql_literals text;
  predecessor_action_kinds constant text[] := array[
    'beacon_campaign_review',
    'beacon_media_review',
    'beacon_private_album_finish',
    'documents_green_physical_acceptance',
    'documents_green_print',
    'grouped_weights',
    'herdmaster_breeding_grouped',
    'herdmaster_record_farrowing_litter',
    'herdmaster_record_litter_first_treatment',
    'herdmaster_record_litter_piglet_deaths',
    'herdmaster_record_litter_weaning',
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
    'herdmaster_purpose_correction',
    'herdmaster_purpose_review',
    'herdmaster_record_farrowing_litter',
    'herdmaster_record_litter_first_treatment',
    'herdmaster_record_litter_piglet_deaths',
    'herdmaster_record_litter_weaning',
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

  current_constraint_definition := regexp_replace(
    pg_catalog.pg_get_constraintdef(constraint_oid),
    '\s+',
    '',
    'g'
  );
  if current_constraint_definition !~
    E'^CHECK\\(\\(action_kind=ANY\\(ARRAY\\[(''[a-z0-9_]+''::text)(,''[a-z0-9_]+''::text)*\\]\\)\\)\\)$' then
    raise exception 'canonical protected action-kind constraint structure mismatch: %',
      current_constraint_definition;
  end if;

  select array_agg(action_kind order by action_kind)
    into current_action_kinds
    from (
      select (matches.value)[1] as action_kind
        from regexp_matches(
          pg_catalog.pg_get_constraintdef(constraint_oid),
          '''([^'']+)''',
          'g'
        ) as matches(value)
    ) extracted;

  -- The freshly observed canonical predecessor has exactly the same retained
  -- kinds except litter weaning. Do not apply that unrelated capability here.
  if current_action_kinds = target_action_kinds
     or current_action_kinds = array_remove(target_action_kinds, 'herdmaster_record_litter_weaning') then
    -- Exact 19- or 18-kind replay; preserve the matched existing capability set.
    null;
  elsif current_action_kinds = predecessor_action_kinds
     or current_action_kinds = array_remove(predecessor_action_kinds, 'herdmaster_record_litter_weaning') then
    matched_target_action_kinds := case
      when current_action_kinds = predecessor_action_kinds then target_action_kinds
      else array_remove(target_action_kinds, 'herdmaster_record_litter_weaning')
    end;
    select string_agg(quote_literal(kind), ',' order by kind)
      into target_sql_literals from unnest(matched_target_action_kinds) kind;
    alter table app_private.oom_protected_action_claims
      drop constraint oom_protected_action_claims_action_kind_check;
    execute 'alter table app_private.oom_protected_action_claims '
      || 'add constraint oom_protected_action_claims_action_kind_check '
      || 'check (action_kind in (' || target_sql_literals || '))';
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
  '20261004232451_allow_herdmaster_purpose_protected_claims',
  'Admit exact-preview HERDMASTER purpose review and correction claims; no farm facts or delegated permissions are changed.'
)
on conflict(migration_id) do nothing;
