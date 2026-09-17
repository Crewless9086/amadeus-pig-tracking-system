-- Recover exact historical B/C commissioning facts into the canonical registry.
-- This migration grants no standing authority and sends no hardware command.
select pg_advisory_xact_lock(hashtext('202608170004_recover_rootline_bc_commissioning_evidence'));

create temporary table rootline_bc_recovered on commit drop as
select p.zone_id, p.execution_id, a.acceptance_id, a.observed_at,
       encode(digest(convert_to(p.payload::text,'UTF8'),'sha256'),'hex') evidence_sha256,
       p.payload
from (
  select x.zone_id, x.execution_id,
         jsonb_build_object('zone_id',x.zone_id,'execution_id',x.execution_id,
           'water_flow',x.water_flow,'stopped_flow',x.stopped_flow,
           'physically_off_now',x.physically_off_now,
           'verified_runtime_seconds',x.verified_runtime_seconds,
           'provider_start_state',x.provider_start_state,
           'provider_shutdown_state',x.provider_shutdown_state,
           'shutdown_verified',x.shutdown_verified) payload,
         q.acceptance_id, q.observed_at
  from public.sam_live_stock_conversation_review_events e
  cross join lateral jsonb_to_record(e.review_json->'rootline_physical_acceptance')
    as q(action text, acceptance_id text, observed_at timestamptz, observations jsonb)
  cross join lateral jsonb_to_recordset(q.observations)
    as x(zone_id text, execution_id text, water_flow text, stopped_flow text,
      physically_off_now boolean, verified_runtime_seconds integer,
      provider_start_state text, provider_shutdown_state text, shutdown_verified boolean)
  where e.event_source='rootline_physical_acceptance' and q.action='record_acceptance'
    and q.acceptance_id='ROOTLINE-PHYSICAL-3ACCC82F844FA65D5FD3E6BD'
) p
join lateral (select p.acceptance_id, p.observed_at) a on true
where (p.zone_id,p.execution_id) in (
 ('B12345','ROOTLINE-EXECUTION-8CF9AD2989F15CC5BDC696AE'),
 ('C12345','ROOTLINE-EXECUTION-79A473B14C98D5E58B9DD2D5'))
  and p.payload->>'water_flow'='normal' and p.payload->>'stopped_flow'='normal'
  and (p.payload->>'physically_off_now')::boolean
  and (p.payload->>'verified_runtime_seconds')::integer=3599
  and p.payload->>'provider_start_state'='ON'
  and p.payload->>'provider_shutdown_state'='OFF'
  and (p.payload->>'shutdown_verified')::boolean;

do $$ begin
  if (select count(*) from rootline_bc_recovered) <> 2
      or (select count(distinct zone_id) from rootline_bc_recovered) <> 2
      or not exists(select 1 from rootline_bc_recovered where zone_id='B12345'
        and execution_id='ROOTLINE-EXECUTION-8CF9AD2989F15CC5BDC696AE')
      or not exists(select 1 from rootline_bc_recovered where zone_id='C12345'
        and execution_id='ROOTLINE-EXECUTION-79A473B14C98D5E58B9DD2D5') then
    raise exception 'rootline_bc_historical_commissioning_evidence_unproven';
  end if;
end $$;

insert into app_private.rootline_device_commissioning_evidence(
 evidence_id,source,observed_at,evidence_sha256,current,evidence_payload)
select 'ROOTLINE-BC-RECOVERED-'||zone_id, 'canonical', observed_at,
 evidence_sha256, true, payload from rootline_bc_recovered
on conflict(evidence_id) do nothing;

do $$ begin
  if exists (
    select 1 from rootline_bc_recovered x
    left join app_private.rootline_device_commissioning_evidence e
      on e.evidence_id='ROOTLINE-BC-RECOVERED-'||x.zone_id
    where e.evidence_id is null or e.source<>'canonical' or not e.current
      or e.observed_at<>x.observed_at or e.evidence_sha256<>x.evidence_sha256
      or e.evidence_payload<>x.payload
  ) then
    raise exception 'rootline_bc_recovered_evidence_conflict';
  end if;
end $$;

with updates as (
 select case zone_id when 'B12345' then
   'ifttt_ewelink:ewelink_owner_account:100204e9bc:1' else
   'ifttt_ewelink:ewelink_owner_account:100204e9bc:2' end device_key,
   zone_id, execution_id, acceptance_id, evidence_sha256 from rootline_bc_recovered
), material as (
 select r.device_key, jsonb_set(jsonb_set(jsonb_set(jsonb_set(r.device_record,
   '{commissioning_stage}','"supervised"'),'{registry_generation}','2'),
   '{historical_commissioning_evidence}',jsonb_build_object(
     'evidence_id','ROOTLINE-BC-RECOVERED-'||u.zone_id,
     'execution_id',u.execution_id,'acceptance_id',u.acceptance_id,
     'evidence_sha256',u.evidence_sha256)),
   '{standing_authority}','false') record
 from app_private.rootline_device_registry r join updates u using(device_key)
 where r.registry_generation=1 and r.commissioning_stage='registered'
), digested as (
 select device_key,record,encode(digest(convert_to(regexp_replace(regexp_replace(
   record::text,': ',':','g'),', ',',','g'),'UTF8'),'sha256'),'hex') digest from material
)
update app_private.rootline_device_registry r set device_record=d.record,
 commissioning_stage='supervised',evidence_digest=d.digest,registry_generation=2,updated_at=now()
from digested d where r.device_key=d.device_key;

do $$ begin
  if (select count(*) from app_private.rootline_device_registry r
      join rootline_bc_recovered x on r.device_key=case x.zone_id
        when 'B12345' then 'ifttt_ewelink:ewelink_owner_account:100204e9bc:1'
        else 'ifttt_ewelink:ewelink_owner_account:100204e9bc:2' end
      where r.registry_generation=2 and r.commissioning_stage='supervised'
        and r.device_record->>'standing_authority'='false'
        and r.device_record->'historical_commissioning_evidence'->>'evidence_id'=
          'ROOTLINE-BC-RECOVERED-'||x.zone_id
        and r.device_record->'historical_commissioning_evidence'->>'execution_id'=x.execution_id
        and r.device_record->'historical_commissioning_evidence'->>'acceptance_id'=x.acceptance_id
        and r.device_record->'historical_commissioning_evidence'->>'evidence_sha256'=x.evidence_sha256
     ) <> 2 then
    raise exception 'rootline_bc_registry_recovery_postcondition_failed';
  end if;
end $$;

insert into app_private.rootline_device_registry_history(
 device_key,registry_generation,device_record,evidence_digest)
select device_key,registry_generation,device_record,evidence_digest
from app_private.rootline_device_registry where registry_generation=2
  and device_key like 'ifttt_ewelink:ewelink_owner_account:100204e9bc:%'
on conflict(device_key,registry_generation) do nothing;

do $$ begin
  if (select count(distinct r.device_key)
      from app_private.rootline_device_registry r
      join app_private.rootline_device_registry_history h
        on h.device_key=r.device_key and h.registry_generation=r.registry_generation
       and h.device_record=r.device_record and h.evidence_digest=r.evidence_digest
      where r.registry_generation=2 and r.device_key in (
        'ifttt_ewelink:ewelink_owner_account:100204e9bc:1',
        'ifttt_ewelink:ewelink_owner_account:100204e9bc:2')) <> 2 then
    raise exception 'rootline_bc_registry_history_conflict';
  end if;
end $$;

insert into app_private.migration_log(migration_id,description)
values('202608170004_recover_rootline_bc_commissioning_evidence',
 'Semantically recover exact B/C identity, flow and OFF proof; no standing authority')
on conflict(migration_id) do nothing;
