do $$
begin
  if exists(select 1 from pg_constraint c join pg_class t on t.oid=c.conrelid
    join pg_namespace n on n.oid=t.relnamespace
    where n.nspname='app_private' and t.relname='oom_protected_action_claims'
      and c.contype='c' and c.conname='oom_protected_action_claims_action_kind_check') then
    alter table app_private.oom_protected_action_claims
      drop constraint oom_protected_action_claims_action_kind_check;
  end if;
  alter table app_private.oom_protected_action_claims
    add constraint oom_protected_action_claims_action_kind_check
    check (action_kind in ('mortality','grouped_weights','herdmaster_breeding_grouped',
                           'rootline_irrigation_segment','sam_sale_payment',
                           'beacon_private_album_finish','beacon_media_review'));
end $$;

revoke all on app_private.oom_protected_action_claims from public, anon, authenticated;
insert into app_private.migration_log(migration_id,description)
values('202608150007_allow_beacon_media_review_claims',
 'Allow owner-bound BEACON Library and public-use review claims')
on conflict(migration_id) do nothing;
