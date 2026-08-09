-- Separate append-only crop-water ledger. Existing irrigation_events debt is untouched.
create table if not exists public.irrigation_water_balance_events (
  event_id text primary key,
  zone_id text not null check (zone_id in ('B12345','C12345')),
  activation_at timestamptz not null,
  complete_through timestamptz not null,
  evidence_digest text not null check (evidence_digest ~ '^[0-9a-f]{64}$'),
  rule_version text not null,
  balance_json jsonb not null,
  created_at timestamptz not null default now(),
  check (complete_through >= activation_at),
  unique (zone_id,evidence_digest)
);

create table if not exists public.rootline_water_balance_learning_proposals (
  proposal_id text primary key,
  current_rule_version text not null,
  proposal_sha256 text not null check (proposal_sha256 ~ '^[0-9a-f]{64}$'),
  proposal_json jsonb not null,
  status text not null default 'review_required' check (status='review_required'),
  created_at timestamptz not null default now()
);

create or replace function public.rootline_water_balance_block_mutation()
returns trigger language plpgsql as $$ begin
  raise exception 'ROOTLINE water-balance ledgers are append-only';
end $$;

drop trigger if exists trg_rootline_water_balance_no_mutation on public.irrigation_water_balance_events;
create trigger trg_rootline_water_balance_no_mutation before update or delete
on public.irrigation_water_balance_events for each row execute function public.rootline_water_balance_block_mutation();
drop trigger if exists trg_rootline_water_balance_proposal_no_mutation on public.rootline_water_balance_learning_proposals;
create trigger trg_rootline_water_balance_proposal_no_mutation before update or delete
on public.rootline_water_balance_learning_proposals for each row execute function public.rootline_water_balance_block_mutation();

create or replace function public.rootline_append_water_balance_event(
  p_event_id text,p_zone_id text,p_activation_at timestamptz,p_complete_through timestamptz,
  p_evidence_digest text,p_balance jsonb) returns boolean
language plpgsql security definer set search_path=public,pg_temp as $$ begin
  if p_zone_id not in ('B12345','C12345')
    or p_balance->>'contract_version'<>'rootline_zone_water_balance.v1'
    or p_balance->>'rule_version'<>'rootline_effective_rainfall_provisional_v1'
    or p_balance->>'evidence_digest'<>p_evidence_digest
    or p_balance->>'zone_id'<>p_zone_id
    or p_complete_through<p_activation_at then
    raise exception 'invalid ROOTLINE water balance';
  end if;
  insert into public.irrigation_water_balance_events(event_id,zone_id,activation_at,
    complete_through,evidence_digest,rule_version,balance_json)
  values(p_event_id,p_zone_id,p_activation_at,p_complete_through,p_evidence_digest,
    p_balance->>'rule_version',p_balance) on conflict(event_id) do nothing;
  return found;
end $$;

revoke insert,update,delete,truncate on public.irrigation_water_balance_events,
  public.rootline_water_balance_learning_proposals from public,anon,authenticated,service_role;
revoke execute on function public.rootline_append_water_balance_event(
  text,text,timestamptz,timestamptz,text,jsonb) from public,anon,authenticated;
grant execute on function public.rootline_append_water_balance_event(
  text,text,timestamptz,timestamptz,text,jsonb) to service_role;

insert into app_private.migration_log(migration_id,description)
values('202608090001_create_rootline_water_balance_ledger',
  'Add separate append-only effective-rainfall water-balance and reviewed learning-proposal ledgers.')
on conflict(migration_id) do nothing;
