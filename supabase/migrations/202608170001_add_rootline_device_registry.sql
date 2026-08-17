create table if not exists app_private.rootline_device_registry (
  device_key text primary key,
  contract_version text not null,
  device_record jsonb not null,
  commissioning_stage text not null,
  standing_authority_id text,
  standing_authority_version text,
  authority_revoked boolean not null default false,
  evidence_digest text not null,
  registry_generation bigint not null check (registry_generation > 0),
  updated_at timestamptz not null default now(),
  check (commissioning_stage in (
    'registered','provider_discovered','readback_proven','bounded_actuation_ready',
    'physical_identity_proven','fail_stop_proven','replay_proven',
    'operational_dependencies_proven','supervised','standing_active')),
  check ((commissioning_stage = 'standing_active') =
    (standing_authority_id is not null and standing_authority_version is not null
      and authority_revoked = false))
);

create table if not exists app_private.rootline_device_registry_history (
  device_key text not null references app_private.rootline_device_registry(device_key),
  registry_generation bigint not null check (registry_generation > 0),
  device_record jsonb not null,
  evidence_digest text not null,
  recorded_at timestamptz not null default now(),
  primary key(device_key,registry_generation)
);

create table if not exists app_private.rootline_device_commissioning_evidence (
  evidence_id text primary key,
  source text not null check (source in ('canonical','provider','physical_review')),
  observed_at timestamptz not null,
  evidence_sha256 text not null check (length(evidence_sha256)=64),
  current boolean not null default true,
  evidence_payload jsonb not null,
  recorded_at timestamptz not null default now()
);

create table if not exists app_private.rootline_standing_authorities (
  standing_authority_id text not null,
  version text not null,
  issuer text not null,
  policy_sha256 text not null check (length(policy_sha256)=64),
  active boolean not null default false,
  revoked boolean not null default false,
  policy_payload jsonb not null,
  recorded_at timestamptz not null default now(),
  primary key(standing_authority_id,version),
  check (not (active and revoked))
);

create table if not exists app_private.rootline_device_evidence_events (
  event_id text primary key,
  evidence_id text not null references app_private.rootline_device_commissioning_evidence(evidence_id),
  event_type text not null check (event_type='invalidated'),
  reason text not null,
  recorded_at timestamptz not null default now()
);

create table if not exists app_private.rootline_authority_events (
  event_id text primary key,
  standing_authority_id text not null,
  version text not null,
  event_type text not null check (event_type in ('revoked','superseded')),
  reason text not null,
  recorded_at timestamptz not null default now(),
  foreign key(standing_authority_id,version) references
    app_private.rootline_standing_authorities(standing_authority_id,version)
);

create or replace function app_private.reject_rootline_device_history_mutation()
returns trigger language plpgsql as $$
begin
  raise exception 'rootline_device_registry_history_append_only';
end;
$$;
drop trigger if exists rootline_device_registry_history_append_only
  on app_private.rootline_device_registry_history;
create trigger rootline_device_registry_history_append_only
before update or delete on app_private.rootline_device_registry_history
for each row execute function app_private.reject_rootline_device_history_mutation();
drop trigger if exists rootline_device_evidence_append_only
  on app_private.rootline_device_commissioning_evidence;
create trigger rootline_device_evidence_append_only
before update or delete on app_private.rootline_device_commissioning_evidence
for each row execute function app_private.reject_rootline_device_history_mutation();
drop trigger if exists rootline_standing_authority_append_only
  on app_private.rootline_standing_authorities;
create trigger rootline_standing_authority_append_only
before update or delete on app_private.rootline_standing_authorities
for each row execute function app_private.reject_rootline_device_history_mutation();
drop trigger if exists rootline_device_evidence_events_append_only
  on app_private.rootline_device_evidence_events;
create trigger rootline_device_evidence_events_append_only
before update or delete on app_private.rootline_device_evidence_events
for each row execute function app_private.reject_rootline_device_history_mutation();
drop trigger if exists rootline_authority_events_append_only
  on app_private.rootline_authority_events;
create trigger rootline_authority_events_append_only
before update or delete on app_private.rootline_authority_events
for each row execute function app_private.reject_rootline_device_history_mutation();

revoke all on app_private.rootline_device_registry from public, anon, authenticated;
revoke all on app_private.rootline_device_registry_history from public, anon, authenticated;
revoke all on app_private.rootline_device_commissioning_evidence from public, anon, authenticated;
revoke all on app_private.rootline_standing_authorities from public, anon, authenticated;
revoke all on app_private.rootline_device_evidence_events from public, anon, authenticated;
revoke all on app_private.rootline_authority_events from public, anon, authenticated;

insert into app_private.rootline_device_registry(
  device_key,contract_version,device_record,commissioning_stage,evidence_digest,registry_generation)
values(
  'ifttt_ewelink:ewelink_owner_account:100204d497:2','rootline_device_spine.v1',
  '{"adapter_profile":"ifttt_ewelink_relay","channel":2,"commissioning_stage":"bounded_actuation_ready","dependencies":["injection_off","verified_shutdown","daily_verified_minutes_cap"],"device_id":"100204d497","device_type":"independent_mixer_valve","manual_isolation":"co_located_manual_valve_owner_reported","maximum_runtime_seconds":300,"native_fail_stop_seconds":300,"physical_effect":"fertilizer_recirculation","physical_name":"Kunsmis Meng","provider":"ifttt_ewelink","provider_account_binding":"ewelink_owner_account","readback":"provider_state","registry_generation":1,"safe_state":"OFF","standing_authority":false}'::jsonb,
  'bounded_actuation_ready','b7c1ecb3d2965c938d10e8ab0045d9bebec88c9a817fd6826759e452d20523e4',1)
on conflict(device_key) do nothing;

insert into app_private.rootline_device_registry_history(
  device_key,registry_generation,device_record,evidence_digest)
select device_key,registry_generation,device_record,evidence_digest
from app_private.rootline_device_registry
where device_key='ifttt_ewelink:ewelink_owner_account:100204d497:2'
on conflict(device_key,registry_generation) do nothing;

insert into app_private.migration_log(migration_id,description)
values('202608170001_add_rootline_device_registry',
 'Canonical typed ROOTLINE device commissioning registry; no execution authority')
on conflict(migration_id) do nothing;
