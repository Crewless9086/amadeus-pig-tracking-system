create table if not exists app_private.sam_live_stock_operating_runtime (
  singleton boolean primary key default true check (singleton),
  worker_id text not null,
  cycle_id text not null,
  lease_until timestamptz not null,
  heartbeat_at timestamptz not null,
  last_cycle_at timestamptz,
  next_cycle_at timestamptz not null,
  last_status text not null,
  last_result jsonb not null default '{}'::jsonb
  ,activated_at timestamptz not null default now()
);

create table if not exists app_private.sam_live_stock_shadow_proposals (
  account_id text not null,
  conversation_id text not null,
  inbound_message_id text not null,
  contact_id text not null,
  cycle_id text not null,
  worker_id text not null,
  response_text text not null,
  response_digest text not null,
  decision jsonb not null,
  status text not null check (status in ('shadow_proposed','shadow_no_reply')),
  observed_at timestamptz not null,
  created_at timestamptz not null default now(),
  primary key (account_id, conversation_id, inbound_message_id)
);

create table if not exists app_private.sam_live_stock_obligations (
  account_id text not null,
  conversation_id text not null,
  inbound_message_id text not null,
  contact_id text not null,
  lane text not null,
  state text not null,
  eligible boolean not null,
  protected boolean not null,
  provider_state text not null,
  latest_inbound_at timestamptz,
  due_follow_up_at timestamptz,
  last_cycle_id text not null,
  worker_id text not null,
  observed_at timestamptz not null,
  primary key (account_id,conversation_id,inbound_message_id)
);

revoke all on app_private.sam_live_stock_operating_runtime from public, anon, authenticated;
revoke all on app_private.sam_live_stock_shadow_proposals from public, anon, authenticated;
revoke all on app_private.sam_live_stock_obligations from public, anon, authenticated;

create or replace function app_private.acquire_sam_live_stock_operating_cycle(
  p_worker_id text, p_cycle_id text, p_now timestamptz, p_next_cycle_at timestamptz)
returns table(acquired boolean, next_cycle_at timestamptz, activated_at timestamptz)
language plpgsql security definer set search_path = pg_catalog, app_private as $$
begin
  insert into app_private.sam_live_stock_operating_runtime
    (singleton,worker_id,cycle_id,lease_until,heartbeat_at,next_cycle_at,last_status)
  values (true,p_worker_id,p_cycle_id,p_now + interval '90 seconds',p_now,p_next_cycle_at,'running')
  on conflict (singleton) do update set
    worker_id=excluded.worker_id, cycle_id=excluded.cycle_id,
    lease_until=excluded.lease_until, heartbeat_at=excluded.heartbeat_at,
    next_cycle_at=excluded.next_cycle_at, last_status='running'
  where sam_live_stock_operating_runtime.lease_until <= p_now
     or sam_live_stock_operating_runtime.worker_id = p_worker_id;
  return query select r.worker_id=p_worker_id and r.cycle_id=p_cycle_id,
    r.next_cycle_at, r.activated_at
    from app_private.sam_live_stock_operating_runtime r where r.singleton;
end $$;

create or replace function app_private.project_sam_live_stock_obligations(
  p_rows jsonb,p_cycle_id text,p_worker_id text,p_observed_at timestamptz)
returns void language sql security definer set search_path = pg_catalog, app_private as $$
  insert into app_private.sam_live_stock_obligations
    (account_id,conversation_id,inbound_message_id,contact_id,lane,state,eligible,
     protected,provider_state,latest_inbound_at,due_follow_up_at,last_cycle_id,
     worker_id,observed_at)
  select coalesce(r->>'account_id',''),coalesce(r->>'conversation_id',''),
    coalesce(r->>'inbound_message_id',''),coalesce(r->>'contact_id',''),
    coalesce(r->>'final_route',''),coalesce(r->>'disposition','unknown'),
    coalesce((r->>'eligible')::boolean,false),
    coalesce((r->>'owner_decision_required')::boolean,false),
    coalesce(r->>'provider_state',''),
    case when coalesce((r->>'latest_inbound_at')::bigint,0)>0
      then to_timestamp((r->>'latest_inbound_at')::bigint) end,
    case when coalesce((r->>'eligible')::boolean,false)
      then p_observed_at + interval '4 hours' end,
    p_cycle_id,p_worker_id,p_observed_at
  from jsonb_array_elements(coalesce(p_rows,'[]'::jsonb)) r
  where coalesce(r->>'conversation_id','')<>''
  on conflict (account_id,conversation_id,inbound_message_id) do update set
    lane=excluded.lane,state=excluded.state,eligible=excluded.eligible,
    protected=excluded.protected,provider_state=excluded.provider_state,
    latest_inbound_at=excluded.latest_inbound_at,
    due_follow_up_at=case when excluded.eligible then
      coalesce(sam_live_stock_obligations.due_follow_up_at,excluded.due_follow_up_at)
      else null end,
    last_cycle_id=excluded.last_cycle_id,worker_id=excluded.worker_id,
    observed_at=excluded.observed_at
$$;

create or replace function app_private.record_sam_live_stock_shadow_proposal(p jsonb)
returns void language sql security definer set search_path = pg_catalog, app_private as $$
  insert into app_private.sam_live_stock_shadow_proposals
    (account_id,conversation_id,inbound_message_id,contact_id,cycle_id,worker_id,
     response_text,response_digest,decision,status,observed_at)
  values (p->>'account_id',p->>'conversation_id',p->>'inbound_message_id',p->>'contact_id',
          p->>'cycle_id',p->>'worker_id',p->>'response_text',p->>'response_digest',
          coalesce(p->'decision','{}'::jsonb),p->>'status',(p->>'observed_at')::timestamptz)
  on conflict (account_id,conversation_id,inbound_message_id) do nothing
$$;

create or replace function app_private.sam_live_stock_shadow_proposal_exists(
  p_account_id text,p_conversation_id text,p_inbound_message_id text)
returns table(present boolean)
language sql stable security definer set search_path = pg_catalog, app_private as $$
  select exists(select 1 from app_private.sam_live_stock_shadow_proposals s
    where s.account_id=p_account_id and s.conversation_id=p_conversation_id
      and s.inbound_message_id=p_inbound_message_id)
$$;

create or replace function app_private.complete_sam_live_stock_operating_cycle(
  p_worker_id text,p_cycle_id text,p_now timestamptz,p_next_cycle_at timestamptz,
  p_status text,p_result jsonb)
returns void language sql security definer set search_path = pg_catalog, app_private as $$
  update app_private.sam_live_stock_operating_runtime set
    heartbeat_at=p_now,last_cycle_at=p_now,next_cycle_at=p_next_cycle_at,
    lease_until=p_now,last_status=p_status,last_result=coalesce(p_result,'{}'::jsonb)
  where singleton and worker_id=p_worker_id and cycle_id=p_cycle_id
$$;

revoke all on function app_private.acquire_sam_live_stock_operating_cycle(text,text,timestamptz,timestamptz) from public,anon,authenticated;
revoke all on function app_private.record_sam_live_stock_shadow_proposal(jsonb) from public,anon,authenticated;
revoke all on function app_private.sam_live_stock_shadow_proposal_exists(text,text,text) from public,anon,authenticated;
revoke all on function app_private.project_sam_live_stock_obligations(jsonb,text,text,timestamptz) from public,anon,authenticated;
revoke all on function app_private.complete_sam_live_stock_operating_cycle(text,text,timestamptz,timestamptz,text,jsonb) from public,anon,authenticated;

insert into app_private.migration_log(migration_id,description)
values('202608160001_create_sam_live_stock_operating_loop',
       'Leased Render-owned SAM Livestock shadow inbox loop and exact proposal evidence')
on conflict(migration_id) do nothing;
