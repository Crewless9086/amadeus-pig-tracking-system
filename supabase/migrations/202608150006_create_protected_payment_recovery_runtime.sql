create table if not exists app_private.oom_protected_payment_recovery_leases (
  callback_token text primary key references app_private.oom_protected_action_claims(callback_token),
  worker_id text not null,
  cycle_id text not null,
  lease_until timestamptz not null,
  heartbeat_at timestamptz not null,
  attempt_count integer not null default 0 check (attempt_count > 0),
  last_status text not null,
  last_result jsonb
);

create table if not exists app_private.oom_protected_payment_recovery_cycles (
  cycle_id text primary key,
  worker_id text not null,
  trigger_kind text not null check (trigger_kind = 'render_cron'),
  started_at timestamptz not null,
  heartbeat_at timestamptz not null,
  completed_at timestamptz,
  next_cycle_at timestamptz not null,
  status text not null,
  result jsonb
);

revoke all on app_private.oom_protected_payment_recovery_leases from public, anon, authenticated;
revoke all on app_private.oom_protected_payment_recovery_cycles from public, anon, authenticated;

insert into app_private.migration_log(migration_id,description)
values('202608150006_create_protected_payment_recovery_runtime',
       'Durable leased scheduler recovery for confirmed SAM payment claims')
on conflict(migration_id) do nothing;
