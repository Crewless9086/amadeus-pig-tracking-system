-- Append-only separation of historical review identity, transport truth and
-- current customer obligation. Existing SAM review rows remain untouched.

create extension if not exists pgcrypto;

create table if not exists public.sam_review_obligation_resolution_events (
  resolution_event_id text primary key,
  contract_version text not null check (contract_version='sam_review_obligation_resolution_v1'),
  review_event_id text not null references public.sam_live_stock_conversation_review_events(review_event_id),
  account_id text not null check (account_id<>''),
  inbox_id text not null check (inbox_id<>''),
  contact_id text not null check (contact_id<>''),
  conversation_id text not null check (conversation_id<>''),
  inbound_message_id text not null check (inbound_message_id<>''),
  review_decision_sha256 text not null check (review_decision_sha256 ~ '^[0-9a-f]{64}$'),
  represented_pig_id text not null check (represented_pig_id='PIG-2026-1AC2'),
  governed_disposition_operation_id text not null check (governed_disposition_operation_id<>''),
  represented_identity_status text not null check (
    represented_identity_status in ('current','superseded','conflicting','unknown')
  ),
  canonical_same_animal_pig_id text,
  alias_evidence_id text,
  outgoing_message_id text,
  bound_reply_to_inbound_id text,
  outgoing_content_sha256 text check (
    outgoing_content_sha256 is null or outgoing_content_sha256 ~ '^[0-9a-f]{64}$'
  ),
  response_class_evidence_id text,
  communication_delivery_status text not null check (
    communication_delivery_status in (
      'not_attempted','attempt_claimed','chatwoot_accepted_unverified',
      'provider_delivered','provider_read','provider_failed',
      'provider_outcome_ambiguous','unknown'
    )
  ),
  delivery_evidence_id text not null,
  delivery_evidence_sha256 text not null check (
    delivery_evidence_sha256 ~ '^[0-9a-f]{64}$'
  ),
  delivery_conversation_id text,
  delivery_inbound_message_id text,
  delivery_outgoing_message_id text,
  customer_obligation_status text not null check (
    customer_obligation_status in (
      'active_replan_required','delivered_attempt_requires_content_resolution',
      'completed_by_attributable_supported_reply',
      'corrective_replan_required_after_reply','superseded_by_later_inbound',
      'quarantined_no_retry','closed_window_reengagement_required',
      'protected_owner_action_required','unknown_fail_closed'
    )
  ),
  obligation_evidence_id text not null,
  obligation_evidence_sha256 text not null check (
    obligation_evidence_sha256 ~ '^[0-9a-f]{64}$'
  ),
  quarantine_evidence_id text not null,
  quarantine_evidence_sha256 text not null check (quarantine_evidence_sha256 ~ '^[0-9a-f]{64}$'),
  protected_decision_evidence_id text not null,
  protected_decision_evidence_sha256 text not null check (protected_decision_evidence_sha256 ~ '^[0-9a-f]{64}$'),
  whatsapp_window_evidence_id text not null,
  whatsapp_window_evidence_sha256 text not null check (whatsapp_window_evidence_sha256 ~ '^[0-9a-f]{64}$'),
  resolution_action text not null check (
    resolution_action in (
      'active','completed','quarantined','protected',
      'corrective_replanning','indeterminate'
    )
  ),
  chronology_cutoff_at timestamptz not null,
  chronology_sha256 text not null check (chronology_sha256 ~ '^[0-9a-f]{64}$'),
  successor_work_item_id text,
  content_relied_on_superseded_identity boolean not null default false,
  source_generation text not null check (source_generation<>''),
  service_authority text not null check (service_authority='sam_review_obligation_resolver'),
  resolution_errors jsonb not null default '[]'::jsonb check (jsonb_typeof(resolution_errors)='array'),
  event_payload_sha256 text not null check (event_payload_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  constraint sam_review_same_animal_alias_evidence check (
    canonical_same_animal_pig_id is null or alias_evidence_id is not null
  ),
  constraint sam_review_zigay_child_alias_prohibited check (
    represented_pig_id <> 'PIG-2026-1AC2' or canonical_same_animal_pig_id is null
  ),
  constraint sam_review_outgoing_attribution_complete check (
    (outgoing_message_id is null and bound_reply_to_inbound_id is null
      and outgoing_content_sha256 is null and response_class_evidence_id is null)
    or
    (outgoing_message_id is not null and bound_reply_to_inbound_id is not null
      and outgoing_content_sha256 is not null and response_class_evidence_id is not null)
  ),
  constraint sam_review_delivery_identity_complete check (
    communication_delivery_status in ('not_attempted','unknown')
    or (delivery_conversation_id=conversation_id
        and delivery_inbound_message_id=inbound_message_id)
  ),
  constraint sam_review_terminal_delivery_outgoing_complete check (
    communication_delivery_status not in ('provider_delivered','provider_read')
    or (delivery_outgoing_message_id is not null and
        (outgoing_message_id is null or delivery_outgoing_message_id=outgoing_message_id))
  ),
  constraint sam_review_successor_binding check (
    customer_obligation_status <> 'superseded_by_later_inbound'
    or successor_work_item_id is not null
  ),
  constraint sam_review_resolution_deterministic_identity check (
    resolution_event_id = 'SAM-REVIEW-RESOLUTION-'
      || upper(substr(event_payload_sha256,1,24))
  )
);

create index if not exists idx_sam_review_resolution_review_cutoff
  on public.sam_review_obligation_resolution_events(
    review_event_id, chronology_cutoff_at desc, created_at desc
  );

create or replace function public.prevent_sam_review_resolution_mutation()
returns trigger language plpgsql as $$
begin
  raise exception 'sam_review_obligation_resolution_events is append-only';
end;
$$;

drop trigger if exists prevent_sam_review_resolution_update
  on public.sam_review_obligation_resolution_events;
create trigger prevent_sam_review_resolution_update
  before update on public.sam_review_obligation_resolution_events
  for each row execute function public.prevent_sam_review_resolution_mutation();
drop trigger if exists prevent_sam_review_resolution_delete
  on public.sam_review_obligation_resolution_events;
create trigger prevent_sam_review_resolution_delete
  before delete on public.sam_review_obligation_resolution_events
  for each row execute function public.prevent_sam_review_resolution_mutation();

create or replace function public.record_sam_review_obligation_resolution(p_event jsonb)
returns boolean language plpgsql security definer set search_path=public as $$
declare
  expected_hash text;
  computed_hash text;
  existing_hash text;
  latest_cutoff timestamptz;
  stored_decision_sha text;
  stored_conversation_id text;
  stored_inbound_id text;
begin
  if session_user <> 'service_role'
     and current_setting('role', true) <> 'service_role' then
    raise exception 'service-only SAM review resolution procedure';
  end if;
  if p_event->>'contract_version' <> 'sam_review_obligation_resolution_v1' then
    raise exception 'unsupported SAM review resolution contract';
  end if;
  expected_hash := p_event->>'event_payload_sha256';
  computed_hash := encode(digest(convert_to(jsonb_build_array(
    p_event->>'contract_version',p_event->>'review_event_id',p_event->>'account_id',
    p_event->>'inbox_id',p_event->>'contact_id',p_event->>'conversation_id',
    p_event->>'inbound_message_id',p_event->>'review_decision_sha256',
    p_event->>'represented_pig_id',p_event->>'governed_disposition_operation_id',
    p_event->>'represented_identity_status',nullif(p_event->>'canonical_same_animal_pig_id',''),
    nullif(p_event->>'alias_evidence_id',''),nullif(p_event->>'outgoing_message_id',''),
    nullif(p_event->>'bound_reply_to_inbound_id',''),nullif(p_event->>'outgoing_content_sha256',''),
    nullif(p_event->>'response_class_evidence_id',''),p_event->>'communication_delivery_status',
    p_event->>'delivery_evidence_id',p_event->>'delivery_evidence_sha256',
    p_event->>'customer_obligation_status',nullif(p_event->>'delivery_conversation_id',''),
    nullif(p_event->>'delivery_inbound_message_id',''),nullif(p_event->>'delivery_outgoing_message_id',''),
    p_event->>'obligation_evidence_id',p_event->>'obligation_evidence_sha256',
    p_event->>'quarantine_evidence_id',p_event->>'quarantine_evidence_sha256',
    p_event->>'protected_decision_evidence_id',p_event->>'protected_decision_evidence_sha256',
    p_event->>'whatsapp_window_evidence_id',p_event->>'whatsapp_window_evidence_sha256',
    p_event->>'resolution_action',p_event->>'chronology_cutoff_at',p_event->>'chronology_sha256',
    nullif(p_event->>'successor_work_item_id',''),
    coalesce((p_event->>'content_relied_on_superseded_identity')::boolean,false),
    p_event->>'source_generation',p_event->>'service_authority',
    coalesce(p_event->'resolution_errors','[]'::jsonb)
  )::text,'UTF8'),'sha256'),'hex');
  if expected_hash !~ '^[0-9a-f]{64}$'
     or expected_hash <> computed_hash
     or p_event->>'resolution_event_id' <> 'SAM-REVIEW-RESOLUTION-'
        || upper(substr(expected_hash,1,24)) then
    raise exception 'deterministic resolution identity required';
  end if;
  perform pg_advisory_xact_lock(hashtextextended(p_event->>'review_event_id', 0));
  select encode(digest(convert_to(decision_json::text,'UTF8'),'sha256'),'hex'),
         chatwoot_conversation_id,chatwoot_message_id
    into stored_decision_sha,stored_conversation_id,stored_inbound_id
    from public.sam_live_stock_conversation_review_events
   where review_event_id=p_event->>'review_event_id';
  if stored_decision_sha is null
     or stored_decision_sha <> p_event->>'review_decision_sha256'
     or stored_conversation_id <> p_event->>'conversation_id'
     or stored_inbound_id <> p_event->>'inbound_message_id' then
    raise exception 'immutable review identity or payload mismatch';
  end if;
  select event_payload_sha256 into existing_hash
    from public.sam_review_obligation_resolution_events
   where resolution_event_id=p_event->>'resolution_event_id';
  if existing_hash is not null then
    if existing_hash <> expected_hash then
      raise exception 'resolution identity payload conflict';
    end if;
    return false;
  end if;
  select max(chronology_cutoff_at) into latest_cutoff
    from public.sam_review_obligation_resolution_events
   where review_event_id=p_event->>'review_event_id';
  if latest_cutoff is not null
     and (p_event->>'chronology_cutoff_at')::timestamptz < latest_cutoff then
    raise exception 'stale chronology resolution rejected';
  end if;
  if latest_cutoff is not null
     and (p_event->>'chronology_cutoff_at')::timestamptz = latest_cutoff then
    raise exception 'conflicting resolution at identical chronology cutoff rejected';
  end if;
  insert into public.sam_review_obligation_resolution_events(
    resolution_event_id,contract_version,review_event_id,account_id,inbox_id,
    contact_id,conversation_id,inbound_message_id,review_decision_sha256,
    represented_pig_id,governed_disposition_operation_id,
    represented_identity_status,canonical_same_animal_pig_id,alias_evidence_id,
    outgoing_message_id,bound_reply_to_inbound_id,outgoing_content_sha256,
    response_class_evidence_id,communication_delivery_status,
    delivery_evidence_id,delivery_evidence_sha256,customer_obligation_status,
    delivery_conversation_id,delivery_inbound_message_id,delivery_outgoing_message_id,
    obligation_evidence_id,obligation_evidence_sha256,resolution_action,
    quarantine_evidence_id,quarantine_evidence_sha256,
    protected_decision_evidence_id,protected_decision_evidence_sha256,
    whatsapp_window_evidence_id,whatsapp_window_evidence_sha256,
    chronology_cutoff_at,chronology_sha256,successor_work_item_id,
    content_relied_on_superseded_identity,source_generation,service_authority,resolution_errors,
    event_payload_sha256
  ) values (
    p_event->>'resolution_event_id',p_event->>'contract_version',p_event->>'review_event_id',
    p_event->>'account_id',p_event->>'inbox_id',p_event->>'contact_id',
    p_event->>'conversation_id',p_event->>'inbound_message_id',
    p_event->>'review_decision_sha256',p_event->>'represented_pig_id',
    p_event->>'governed_disposition_operation_id',p_event->>'represented_identity_status',
    nullif(p_event->>'canonical_same_animal_pig_id',''),nullif(p_event->>'alias_evidence_id',''),
    nullif(p_event->>'outgoing_message_id',''),nullif(p_event->>'bound_reply_to_inbound_id',''),
    nullif(p_event->>'outgoing_content_sha256',''),nullif(p_event->>'response_class_evidence_id',''),
    p_event->>'communication_delivery_status',p_event->>'delivery_evidence_id',
    p_event->>'delivery_evidence_sha256',p_event->>'customer_obligation_status',
    nullif(p_event->>'delivery_conversation_id',''),nullif(p_event->>'delivery_inbound_message_id',''),
    nullif(p_event->>'delivery_outgoing_message_id',''),
    p_event->>'obligation_evidence_id',p_event->>'obligation_evidence_sha256',
    p_event->>'resolution_action',p_event->>'quarantine_evidence_id',
    p_event->>'quarantine_evidence_sha256',p_event->>'protected_decision_evidence_id',
    p_event->>'protected_decision_evidence_sha256',p_event->>'whatsapp_window_evidence_id',
    p_event->>'whatsapp_window_evidence_sha256',(p_event->>'chronology_cutoff_at')::timestamptz,
    p_event->>'chronology_sha256',nullif(p_event->>'successor_work_item_id',''),
    coalesce((p_event->>'content_relied_on_superseded_identity')::boolean,false),
    p_event->>'source_generation',p_event->>'service_authority',
    coalesce(p_event->'resolution_errors','[]'::jsonb),expected_hash
  );
  return true;
end;
$$;

create or replace view public.current_sam_review_obligation_resolutions as
select distinct on (event.review_event_id)
  event.*
from public.sam_review_obligation_resolution_events event
order by event.review_event_id,event.chronology_cutoff_at desc,event.created_at desc,event.resolution_event_id desc;

create or replace view public.current_resolved_sam_live_stock_review_events as
select
  review.*,
  resolution.represented_pig_id,
  resolution.represented_identity_status,
  resolution.canonical_same_animal_pig_id,
  resolution.communication_delivery_status,
  resolution.customer_obligation_status,
  resolution.resolution_action,
  resolution.chronology_cutoff_at,
  resolution.chronology_sha256,
  resolution.successor_work_item_id,
  resolution.content_relied_on_superseded_identity,
  resolution.resolution_event_id
from public.sam_live_stock_conversation_review_events review
join public.current_sam_review_obligation_resolutions resolution
  on resolution.review_event_id=review.review_event_id;

-- Keep PR #634's containment until an exact resolution exists. A resolved
-- historical inventory action is never restored as send authority: active,
-- protected and quarantined obligations reappear only as non-sending work.
create or replace view public.current_actionable_sam_live_stock_review_events as
select
  review.review_event_id,review.chatwoot_conversation_id,
  review.chatwoot_message_id,review.customer_name,review.channel,
  review.source_agent,review.event_source,review.customer_message_excerpt,
  case when resolution.resolution_event_id is null then review.sam_reply_excerpt else '' end as sam_reply_excerpt,
  review.score,review.confidence_target,
  case when resolution.resolution_event_id is null then review.safe_to_send else false end as safe_to_send,
  case when resolution.resolution_event_id is not null then false
       else review.owner_send_required end as owner_send_required,
  case when resolution.communication_delivery_status in (
         'chatwoot_accepted_unverified','provider_outcome_ambiguous'
       ) then true
       when resolution.resolution_action in ('completed','quarantined') then true
       when resolution.resolution_event_id is not null then false
       else review.no_reply_recommended end as no_reply_recommended,
  case when resolution.resolution_action in ('protected','indeterminate') then true
       when resolution.resolution_event_id is not null then false
       else review.escalation_required end as escalation_required,
  review.conversation_mode_recommendation,
  case
    when resolution.resolution_action='active' then 'replan_from_current_canonical_inventory'
    when resolution.resolution_action='corrective_replanning' then 'corrective_replan_from_current_canonical_inventory'
    when resolution.resolution_action='quarantined' then 'delivery_quarantined_do_not_retry'
    when resolution.resolution_action='protected' then 'owner_decision_required'
    when resolution.resolution_action='indeterminate' then 'indeterminate_fail_closed'
    else review.recommended_action
  end as recommended_action,
  review.review_json,review.facts_json,review.decision_json,
  review.applies_learning_now,review.changes_prompt_now,review.changes_runtime_now,
  review.sends_customer_message,review.calls_chatwoot,review.calls_telegram,
  review.creates_order,review.reserves_stock,review.changes_stock,
  review.writes_farm_data,review.created_at,
  resolution.represented_pig_id,resolution.represented_identity_status,
  resolution.canonical_same_animal_pig_id,
  resolution.communication_delivery_status,
  resolution.customer_obligation_status,resolution.resolution_action,
  resolution.chronology_cutoff_at,resolution.chronology_sha256,
  resolution.successor_work_item_id,
  resolution.content_relied_on_superseded_identity,
  resolution.resolution_event_id
from public.sam_live_stock_conversation_review_events review
left join public.current_sam_review_obligation_resolutions resolution
  on resolution.review_event_id=review.review_event_id
where (
  not exists (
    select 1 from public.litter_supersessions correction
    cross join lateral jsonb_array_elements_text(
      correction.historical_reference_row_ids
    ) historical_review(review_event_id)
    where historical_review.review_event_id=review.review_event_id
  )
  or resolution.resolution_event_id is not null
)
and coalesce(resolution.resolution_action,'active') <> 'completed';

-- Refresh protection for every newly introduced table. This rail is the one
-- governed exception: it must preserve the exact superseded historical ID,
-- and its service-only insert procedure plus append-only triggers are the
-- stronger authority boundary for that reference.
select public.refresh_litter_supersession_write_guards();
drop trigger if exists reject_superseded_pig_fact
  on public.sam_review_obligation_resolution_events;

revoke all on public.sam_review_obligation_resolution_events from public;
revoke all on function public.record_sam_review_obligation_resolution(jsonb) from public;
do $$ begin
  if exists(select 1 from pg_roles where rolname='service_role') then
    execute 'grant select on public.sam_review_obligation_resolution_events to service_role';
    execute 'grant select on public.current_sam_review_obligation_resolutions to service_role';
    execute 'grant select on public.current_resolved_sam_live_stock_review_events to service_role';
    execute 'grant select on public.current_actionable_sam_live_stock_review_events to service_role';
    execute 'grant execute on function public.record_sam_review_obligation_resolution(jsonb) to service_role';
  end if;
end $$;
