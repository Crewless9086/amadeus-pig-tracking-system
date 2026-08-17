-- Canonical device identity only.  These rows grant no execution or standing authority.
-- B and C deliberately stop at registered: historical flags/baselines are not
-- commissioning evidence.  Supervised physical commissioning must advance them.
select pg_advisory_xact_lock(hashtext('202608170003_seed_rootline_operational_devices'));

create temporary table rootline_operational_device_seed on commit drop as
with seed(device_key, commissioning_stage, device_record) as (values
  ('ifttt_ewelink:ewelink_owner_account:100204e9bc:1', 'registered',
   '{"adapter_profile":"ifttt_ewelink_relay","channel":1,"commissioning_stage":"registered","dependencies":["fresh_water_truth","fresh_weather_truth","fresh_plan_truth","provider_off_readback"],"device_id":"100204e9bc","device_type":"gravity_irrigation_valve","manual_isolation":"manual_valve_available","maximum_runtime_seconds":3599,"native_fail_stop_seconds":3599,"physical_effect":"B12345 irrigation water flow","physical_name":"B12345 / B Camp","provider":"ifttt_ewelink","provider_account_binding":"ewelink_owner_account","readback":"provider_state","registry_generation":1,"safe_state":"OFF","standing_authority":false}'::jsonb),
  ('ifttt_ewelink:ewelink_owner_account:100204e9bc:2', 'registered',
   '{"adapter_profile":"ifttt_ewelink_relay","channel":2,"commissioning_stage":"registered","dependencies":["fresh_water_truth","fresh_weather_truth","fresh_plan_truth","provider_off_readback"],"device_id":"100204e9bc","device_type":"gravity_irrigation_valve","manual_isolation":"manual_valve_available","maximum_runtime_seconds":3599,"native_fail_stop_seconds":3599,"physical_effect":"C12345 irrigation water flow","physical_name":"C12345 / C Camp","provider":"ifttt_ewelink","provider_account_binding":"ewelink_owner_account","readback":"provider_state","registry_generation":1,"safe_state":"OFF","standing_authority":false}'::jsonb),
  ('ifttt_ewelink:ewelink_owner_account:100204d497:1', 'registered',
   '{"adapter_profile":"ifttt_ewelink_relay","channel":1,"commissioning_stage":"registered","dependencies":["exactly_one_active_bc_zone","verified_water_preflow","mixer_off","verified_shutdown","clean_water_flush"],"device_id":"100204d497","device_type":"flow_dependent_injection_valve","manual_isolation":"co_located_manual_valve_owner_reported","maximum_runtime_seconds":120,"native_fail_stop_seconds":120,"physical_effect":"fertilizer injection","physical_name":"Kunsmis In","provider":"ifttt_ewelink","provider_account_binding":"ewelink_owner_account","readback":"provider_state","registry_generation":1,"safe_state":"OFF","standing_authority":false}'::jsonb),
  ('ewelink:ewelink_owner_account:1002851416:1', 'registered',
   '{"adapter_profile":"ewelink_minir4","channel":1,"commissioning_stage":"registered","dependencies":["online_provider_identity","tank_full","dry_run_protection","pump_current_protection","manual_isolation","power_loss_fail_safe"],"device_id":"1002851416","device_type":"pump","manual_isolation":"Unknown","maximum_runtime_seconds":0,"native_fail_stop_seconds":0,"physical_effect":"Borehole 1 pump power","physical_name":"Borehole MINI R4","provider":"ewelink","provider_account_binding":"ewelink_owner_account","readback":"provider_state","registry_generation":1,"safe_state":"OFF","standing_authority":false}'::jsonb)
), material as (
  select device_key, commissioning_stage, device_record,
    encode(digest(convert_to(regexp_replace(regexp_replace(device_record::text,
      ': ', ':', 'g'), ', ', ',', 'g'), 'UTF8'), 'sha256'), 'hex') as evidence_digest
  from seed
)
select * from material;

insert into app_private.rootline_device_registry(
  device_key, contract_version, device_record, commissioning_stage,
  evidence_digest, registry_generation)
select device_key, 'rootline_device_spine.v1', device_record,
  commissioning_stage, evidence_digest, 1
from rootline_operational_device_seed
on conflict(device_key) do nothing;

do $$
begin
  if exists (
    select 1 from rootline_operational_device_seed s
    left join app_private.rootline_device_registry r using(device_key)
    where r.device_key is null or r.contract_version <> 'rootline_device_spine.v1'
      or r.device_record <> s.device_record or r.commissioning_stage <> s.commissioning_stage
      or r.evidence_digest <> s.evidence_digest or r.registry_generation <> 1
      or r.standing_authority_id is not null or r.standing_authority_version is not null
      or r.authority_revoked
  ) then
    raise exception 'rootline_operational_device_seed_conflict';
  end if;
end;
$$;

insert into app_private.rootline_device_registry_history(
  device_key, registry_generation, device_record, evidence_digest)
select r.device_key, r.registry_generation, r.device_record, r.evidence_digest
from app_private.rootline_device_registry r
join rootline_operational_device_seed s using(device_key)
on conflict(device_key, registry_generation) do nothing;

do $$
begin
  if exists (
    select 1 from rootline_operational_device_seed s
    left join app_private.rootline_device_registry_history h
      on h.device_key=s.device_key and h.registry_generation=1
    where h.device_key is null or h.device_record <> s.device_record
      or h.evidence_digest <> s.evidence_digest
  ) then
    raise exception 'rootline_operational_device_history_conflict';
  end if;
end;
$$;

insert into app_private.migration_log(migration_id, description)
values('202608170003_seed_rootline_operational_devices',
 'Typed ROOTLINE B/C, injection and borehole identities; uncommissioned and no authority')
on conflict(migration_id) do nothing;
