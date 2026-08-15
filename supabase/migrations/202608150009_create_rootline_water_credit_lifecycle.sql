-- Append-only measured/calibrated water-credit truth. No hardware authority.
create table if not exists public.irrigation_water_volume_evidence (
  evidence_id text primary key,
  evidence_type text not null check (evidence_type in ('measured_volume','governed_calibration')),
  zone_id text not null check (zone_id in ('B12345','C12345')),
  evidence_sha256 text not null check (evidence_sha256 ~ '^[0-9a-f]{64}$'),
  evidence_json jsonb not null,
  created_at timestamptz not null default now(),
  check (evidence_json->>'contract_version' = 'rootline_water_volume_evidence.v1'),
  check (evidence_json->>'evidence_id' = evidence_id),
  check (evidence_json->>'evidence_type' = evidence_type),
  check (evidence_json->>'zone_id' = zone_id),
  check (evidence_json->>'evidence_sha256' = evidence_sha256),
  check ((evidence_json->>'verified')::boolean is true),
  check (evidence_json->>'source' in ('verified_flow_meter','verified_volume_measurement','commissioned_zone_calibration'))
);

create table if not exists public.irrigation_water_credit_events (
  credit_id text primary key,
  execution_id text not null unique,
  zone_id text not null check (zone_id in ('B12345','C12345')),
  physical_acceptance_sha256 text not null check (physical_acceptance_sha256 ~ '^[0-9a-f]{64}$'),
  credit_sha256 text not null check (credit_sha256 ~ '^[0-9a-f]{64}$'),
  credit_json jsonb not null,
  created_at timestamptz not null default now(),
  unique (execution_id, physical_acceptance_sha256),
  check (credit_json->>'contract_version' = 'rootline_water_credit.v1'),
  check (credit_json->>'execution_id' = execution_id),
  check (credit_json->>'zone_id' = zone_id),
  check (credit_json->>'physical_acceptance_sha256' = physical_acceptance_sha256),
  check (credit_json->>'credit_sha256' = credit_sha256),
  check ((credit_json->>'delivered_volume_litres')::numeric > 0),
  check (credit_json->>'credit_method' in ('measured_volume','governed_calibration'))
);

create or replace function public.rootline_water_credit_block_mutation()
returns trigger language plpgsql as $$ begin
  raise exception 'ROOTLINE water-credit ledger is append-only';
end $$;
drop trigger if exists trg_rootline_water_credit_no_mutation on public.irrigation_water_credit_events;
create trigger trg_rootline_water_credit_no_mutation before update or delete
on public.irrigation_water_credit_events for each row execute function public.rootline_water_credit_block_mutation();
drop trigger if exists trg_rootline_water_volume_evidence_no_mutation on public.irrigation_water_volume_evidence;
create trigger trg_rootline_water_volume_evidence_no_mutation before update or delete
on public.irrigation_water_volume_evidence for each row execute function public.rootline_water_credit_block_mutation();

create or replace function public.rootline_append_water_volume_evidence(
  p_evidence_id text, p_evidence_type text, p_zone_id text,
  p_evidence_sha256 text, p_evidence jsonb
) returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare stored public.irrigation_water_volume_evidence%rowtype;
begin
  insert into public.irrigation_water_volume_evidence(
    evidence_id,evidence_type,zone_id,evidence_sha256,evidence_json)
  values(p_evidence_id,p_evidence_type,p_zone_id,p_evidence_sha256,p_evidence)
  on conflict (evidence_id) do nothing;
  if found then return true; end if;
  select * into stored from public.irrigation_water_volume_evidence where evidence_id=p_evidence_id;
  if stored.evidence_type is distinct from p_evidence_type or stored.zone_id is distinct from p_zone_id
    or stored.evidence_sha256 is distinct from p_evidence_sha256 or stored.evidence_json is distinct from p_evidence then
    raise exception 'ROOTLINE water volume evidence replay conflict';
  end if;
  return false;
end $$;

create or replace function public.rootline_append_water_credit_event(
  p_credit_id text, p_execution_id text, p_zone_id text,
  p_acceptance_sha256 text, p_credit_sha256 text, p_credit jsonb
) returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare stored public.irrigation_water_credit_events%rowtype;
begin
  if p_credit->>'credit_id' is distinct from p_credit_id
    or p_credit->>'execution_id' is distinct from p_execution_id
    or p_credit->>'zone_id' is distinct from p_zone_id
    or p_credit->>'physical_acceptance_sha256' is distinct from p_acceptance_sha256
    or p_credit->>'credit_sha256' is distinct from p_credit_sha256 then
    raise exception 'invalid ROOTLINE water credit';
  end if;
  insert into public.irrigation_water_credit_events(
    credit_id,execution_id,zone_id,physical_acceptance_sha256,credit_sha256,credit_json)
  values(p_credit_id,p_execution_id,p_zone_id,p_acceptance_sha256,p_credit_sha256,p_credit)
  on conflict (credit_id) do nothing;
  if found then return true; end if;
  select * into stored from public.irrigation_water_credit_events where credit_id=p_credit_id;
  if stored.execution_id is distinct from p_execution_id
    or stored.zone_id is distinct from p_zone_id
    or stored.physical_acceptance_sha256 is distinct from p_acceptance_sha256
    or stored.credit_sha256 is distinct from p_credit_sha256
    or stored.credit_json is distinct from p_credit then
    raise exception 'ROOTLINE water credit replay conflict';
  end if;
  return false;
end $$;

revoke insert,update,delete,truncate on public.irrigation_water_credit_events,
  public.irrigation_water_volume_evidence from public,anon,authenticated,service_role;
revoke execute on function public.rootline_append_water_credit_event(text,text,text,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.rootline_append_water_credit_event(text,text,text,text,text,jsonb) to service_role;
revoke execute on function public.rootline_append_water_volume_evidence(text,text,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.rootline_append_water_volume_evidence(text,text,text,text,jsonb) to service_role;

insert into app_private.migration_log(migration_id,description)
values('202608150009_create_rootline_water_credit_lifecycle',
 'Append-only ROOTLINE water credit bound to exact execution and accepted physical evidence; litres require measurement or calibration.')
on conflict (migration_id) do nothing;
