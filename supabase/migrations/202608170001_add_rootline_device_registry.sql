create table if not exists app_private.rootline_device_registry (
  device_key text primary key,
  contract_version text not null,
  device_record jsonb not null,
  commissioning_stage text not null,
  standing_authority_id text,
  standing_authority_version text,
  authority_revoked boolean not null default false,
  evidence_digest text not null,
  updated_at timestamptz not null default now(),
  check (commissioning_stage in (
    'registered','provider_discovered','readback_proven','bounded_actuation_ready',
    'physical_identity_proven','fail_stop_proven','replay_proven',
    'operational_dependencies_proven','supervised','standing_active')),
  check ((commissioning_stage = 'standing_active') =
    (standing_authority_id is not null and standing_authority_version is not null
      and authority_revoked = false))
);

revoke all on app_private.rootline_device_registry from public, anon, authenticated;

insert into app_private.migration_log(migration_id,description)
values('202608170001_add_rootline_device_registry',
 'Canonical typed ROOTLINE device commissioning registry; no execution authority')
on conflict(migration_id) do nothing;
