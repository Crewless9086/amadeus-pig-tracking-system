alter table app_private.oom_protected_action_claims
  add column if not exists delivery_state text not null default 'claim_created',
  add column if not exists delivery_attempt_id text,
  add column if not exists delivery_attempted_at timestamptz,
  add column if not exists provider_accepted_at timestamptz,
  add column if not exists delivery_confirmed_at timestamptz,
  add column if not exists delivery_ambiguous_at timestamptz,
  add column if not exists delivery_result jsonb;

alter table app_private.oom_protected_action_claims drop constraint if exists
  oom_protected_action_claims_delivery_state_check;
alter table app_private.oom_protected_action_claims add constraint
  oom_protected_action_claims_delivery_state_check check (delivery_state in
  ('claim_created','delivery_pending','provider_accepted','delivery_confirmed',
   'delivery_ambiguous','completed','contained','cancelled','expired'));
create unique index if not exists oom_protected_action_delivery_attempt_unique
  on app_private.oom_protected_action_claims(delivery_attempt_id)
  where delivery_attempt_id is not null;
revoke all on app_private.oom_protected_action_claims from public, anon, authenticated;
insert into app_private.migration_log(migration_id,description)
values('202608160004_add_protected_delivery_lifecycle',
 'Recoverable serialized provider-card delivery on the canonical protected-action spine')
on conflict(migration_id) do nothing;
