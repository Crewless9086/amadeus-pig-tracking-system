create table if not exists app_private.beacon_protected_publication_consumers (
  consumer_id text primary key,
  callback_token text not null unique references app_private.oom_protected_action_claims(callback_token),
  worker_id text not null,
  status text not null check(status in ('claimed','confirmed','contained_failed','contained_ambiguous','contained')),
  outcome_json jsonb not null default '{}'::jsonb,
  claimed_at timestamptz not null,
  updated_at timestamptz not null,
  finished_at timestamptz
);
revoke all on app_private.beacon_protected_publication_consumers from public, anon, authenticated;
insert into app_private.migration_log(migration_id,description)
values('202608190002_create_beacon_protected_publication_consumer',
 'Durably claim each genuine protected BEACON approval for one deployed Meta attempt')
on conflict(migration_id) do nothing;
