-- Activate only the owner's narrow B/C irrigation policy. This issues no command.
select pg_advisory_xact_lock(hashtext('202608180001_activate_rootline_bc_standing_authority'));

do $$ begin
 if (select count(*) from app_private.rootline_device_registry where device_key in
  ('ifttt_ewelink:ewelink_owner_account:100204e9bc:1','ifttt_ewelink:ewelink_owner_account:100204e9bc:2')
  and registry_generation=2 and commissioning_stage='supervised'
  and device_record->>'standing_authority'='false'
  and device_record->'historical_commissioning_evidence'->>'evidence_id'=
   'ROOTLINE-BC-RECOVERED-'||case (device_record->>'channel')::integer when 1 then 'B12345' else 'C12345' end)<>2 then
  raise exception 'rootline_bc_generation_2_supervised_evidence_unproven';
 end if;
end $$;

with p(payload) as (values(jsonb_build_object(
 'contract_version','rootline_bc_standing_authority.v1',
 'device_keys',jsonb_build_array('ifttt_ewelink:ewelink_owner_account:100204e9bc:1','ifttt_ewelink:ewelink_owner_account:100204e9bc:2'),
 'zone_ids',jsonb_build_array('B12345','C12345'),'allowed_channels',jsonb_build_array(1,2),
 'provider','ifttt_ewelink','provider_account_binding','ewelink_owner_account','device_id','100204e9bc',
 'maximum_runtime_seconds',3599,'native_fail_stop_seconds',3599,
 'simultaneous_outputs_allowed',false,'mutual_exclusion_required',true,
 'sequence','one B or C segment; verified OFF before any next segment',
 'fresh_reservoir_storage_required',true,'fresh_weather_and_rain_hold_required',true,
 'current_plan_identity_required',true,'application_timeout_required',true,
 'provider_on_off_readback_required',true,
 'emergency_off_owner','deployed ROOTLINE irrigation coordinator',
 'emergency_off_procedure','exact provider OFF; authoritative OFF readback; contain zone and alert if uncertain',
 'provider_fail_stop_proven',true,'physical_fail_safe_proven',true,
 'power_restoration_off_proven',true,'automatic_on_retry',false,
 'revocation','canonical revoked or superseded authority event',
 'replay_policy','same execution or segment identity is silent and never issues another ON',
 'owner_intent','Charl directed deployed ROOTLINE to run routine B/C irrigation automatically inside every protected gate',
 'explicit_exclusions',jsonb_build_array('fertilizer_injection','fertilizer_mixing','borehole_pump'))))
insert into app_private.rootline_standing_authorities(
 standing_authority_id,version,issuer,policy_sha256,active,revoked,policy_payload)
select 'ROOTLINE-BC-IRRIGATION-AUTO','1','owner_policy',
 encode(digest(convert_to(payload::text,'UTF8'),'sha256'),'hex'),true,false,payload from p
on conflict(standing_authority_id,version) do nothing;

do $$ begin
 if not exists(select 1 from app_private.rootline_standing_authorities
  where standing_authority_id='ROOTLINE-BC-IRRIGATION-AUTO' and version='1'
  and issuer='owner_policy' and active and not revoked
  and policy_sha256=encode(digest(convert_to(policy_payload::text,'UTF8'),'sha256'),'hex')
  and policy_payload->>'contract_version'='rootline_bc_standing_authority.v1'
  and policy_payload->'device_keys' ?& array['ifttt_ewelink:ewelink_owner_account:100204e9bc:1','ifttt_ewelink:ewelink_owner_account:100204e9bc:2']
  and jsonb_array_length(policy_payload->'device_keys')=2
  and policy_payload->'zone_ids' ?& array['B12345','C12345'] and jsonb_array_length(policy_payload->'zone_ids')=2
  and policy_payload->>'provider'='ifttt_ewelink' and policy_payload->>'device_id'='100204e9bc'
  and (policy_payload->>'maximum_runtime_seconds')::integer=3599
  and (policy_payload->>'simultaneous_outputs_allowed')::boolean=false
  and (policy_payload->>'mutual_exclusion_required')::boolean
  and (policy_payload->>'fresh_reservoir_storage_required')::boolean
  and (policy_payload->>'fresh_weather_and_rain_hold_required')::boolean
  and (policy_payload->>'current_plan_identity_required')::boolean
  and (policy_payload->>'application_timeout_required')::boolean
  and (policy_payload->>'provider_on_off_readback_required')::boolean
  and (policy_payload->>'automatic_on_retry')::boolean=false
  and policy_payload->'explicit_exclusions' ?& array['fertilizer_injection','fertilizer_mixing','borehole_pump']) then
  raise exception 'rootline_bc_policy_conflict';
 end if;
end $$;

with src as (
 select r.*,e.evidence_id,e.source evidence_source,e.observed_at,e.evidence_sha256,a.policy_sha256
 from app_private.rootline_device_registry r
 join app_private.rootline_device_commissioning_evidence e
  on e.evidence_id=r.device_record->'historical_commissioning_evidence'->>'evidence_id' and e.current
 join app_private.rootline_standing_authorities a
  on a.standing_authority_id='ROOTLINE-BC-IRRIGATION-AUTO' and a.version='1'
 where r.device_key in ('ifttt_ewelink:ewelink_owner_account:100204e9bc:1','ifttt_ewelink:ewelink_owner_account:100204e9bc:2')),
refs as (select src.*,jsonb_build_object('source',evidence_source,'evidence_id',evidence_id,
 'observed_at',observed_at,'sha256',evidence_sha256) ref from src),
material as (select device_key,jsonb_set(jsonb_set(jsonb_set(jsonb_set(jsonb_set(device_record,
 '{commissioning_stage}','"standing_active"'),'{standing_authority}','true'),'{registry_generation}','3'),
 '{commissioning_evidence}',jsonb_build_object('supervised',ref)),'{authority_envelope}',jsonb_build_object(
 'standing_authority_id','ROOTLINE-BC-IRRIGATION-AUTO','version','1','issuer','owner_policy',
 'policy_sha256',policy_sha256,'revoked',false)) record from refs),
digested as (select device_key,record,encode(digest(convert_to(regexp_replace(regexp_replace(
 record::text,': ',':','g'),', ',',','g'),'UTF8'),'sha256'),'hex') digest from material)
update app_private.rootline_device_registry r set device_record=d.record,commissioning_stage='standing_active',
 standing_authority_id='ROOTLINE-BC-IRRIGATION-AUTO',standing_authority_version='1',authority_revoked=false,
 evidence_digest=d.digest,registry_generation=3,updated_at=now() from digested d where r.device_key=d.device_key;

insert into app_private.rootline_device_registry_history(device_key,registry_generation,device_record,evidence_digest)
select device_key,registry_generation,device_record,evidence_digest from app_private.rootline_device_registry
where registry_generation=3 and standing_authority_id='ROOTLINE-BC-IRRIGATION-AUTO'
on conflict(device_key,registry_generation) do nothing;

do $$ begin
 if (select count(*) from app_private.rootline_device_registry r join app_private.rootline_device_registry_history h
  using(device_key,registry_generation) where r.standing_authority_id='ROOTLINE-BC-IRRIGATION-AUTO'
  and r.registry_generation=3 and r.commissioning_stage='standing_active'
  and r.device_record->>'standing_authority'='true' and h.device_record=r.device_record
  and h.evidence_digest=r.evidence_digest)<>2 then raise exception 'rootline_bc_authority_postcondition_failed'; end if;
 if exists(select 1 from app_private.rootline_device_registry where standing_authority_id='ROOTLINE-BC-IRRIGATION-AUTO'
  and device_key not in ('ifttt_ewelink:ewelink_owner_account:100204e9bc:1','ifttt_ewelink:ewelink_owner_account:100204e9bc:2')) then
  raise exception 'rootline_bc_policy_scope_expanded'; end if;
end $$;

insert into app_private.migration_log(migration_id,description) values(
 '202608180001_activate_rootline_bc_standing_authority','Activate revocable B/C-only automatic irrigation authority')
on conflict(migration_id) do nothing;
