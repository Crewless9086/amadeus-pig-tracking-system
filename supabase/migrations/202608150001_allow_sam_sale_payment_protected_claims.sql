do $$
declare constraint_name text;
begin
  select c.conname into constraint_name from pg_constraint c
  join pg_class t on t.oid=c.conrelid join pg_namespace n on n.oid=t.relnamespace
  where n.nspname='app_private' and t.relname='oom_protected_action_claims'
    and c.contype='c' and pg_get_constraintdef(c.oid) ilike '%action_kind%';
  if constraint_name is not null then
    execute format('alter table app_private.oom_protected_action_claims drop constraint %I',constraint_name);
  end if;
  alter table app_private.oom_protected_action_claims
    add constraint oom_protected_action_claims_action_kind_check
    check (action_kind in ('mortality','grouped_weights','herdmaster_breeding_grouped',
                           'rootline_irrigation_segment','sam_sale_payment'));
end $$;
revoke all on app_private.oom_protected_action_claims from public, anon, authenticated;
insert into app_private.migration_log(migration_id,description)
values('202608150001_allow_sam_sale_payment_protected_claims',
 'Allow exact owner-confirmed SAM sale-payment claims')
on conflict(migration_id) do nothing;
