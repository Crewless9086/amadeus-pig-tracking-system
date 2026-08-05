"""Existing-store runtime coordinator for proactive HERDMASTER evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Callable, Mapping, Sequence

from modules.oom_sakkie.herdmaster_management_adapter import (
    ZERO_AUTHORITY, consume_herdmaster_management_round, validate_management_authority,
)
import hashlib
import json
from modules.oom_sakkie.farm_manager_loop import SpecialistResult
from modules.pig_weights.mating_routes import load_current_breeding_operating_loop

EVENT_SOURCE = "oom_sakkie_herdmaster_management_consumer"
OBSERVATION_SOURCE = "oom_sakkie_owner_observation"


def consume_current_herdmaster_management(*, authority: Any, owner_user_id: str,
        now: datetime | None = None, canonical_loader=load_current_breeding_operating_loop,
        observation_loader=None, active_loader=None, prior_loader=None, recorder=None,
        retain_replay_result=False):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    auth = validate_management_authority(
        authority, str(owner_user_id), now, trusted_now=now)
    if not auth:
        return _contained("authenticated_manager_context_denied", now)
    try:
        observations = (observation_loader or _load_observations)(str(owner_user_id))
        active = (active_loader or _load_active_lifecycles)(str(owner_user_id))
        prior = (prior_loader or _load_prior_consumptions)(
            str(owner_user_id), str(auth["context"].get("digest") or ""))
        canonical = canonical_loader()
    except Exception:
        return _contained("herdmaster_management_runtime_evidence_unavailable", now)
    result = consume_herdmaster_management_round(authority=authority,
        expected_owner_user_id=str(owner_user_id), canonical_round=canonical,
        invocation_at=now, trusted_now=now, attributable_owner_observations=observations,
        active_lifecycles=active, prior_consumptions=prior)
    if (retain_replay_result
            and result.get("status") == "herdmaster_management_round_replay_suppressed"):
        replay = consume_herdmaster_management_round(authority=authority,
            expected_owner_user_id=str(owner_user_id), canonical_round=canonical,
            invocation_at=now, trusted_now=now,
            attributable_owner_observations=observations,
            active_lifecycles=active, prior_consumptions=())
        if isinstance(replay.get("specialist_result"), SpecialistResult):
            result = {**replay, "status": "herdmaster_management_round_replay_suppressed"}
    if result.get("status") == "herdmaster_management_round_consumed":
        try:
            recorded = (recorder or _record_consumption)(result)
        except Exception:
            return _contained("herdmaster_management_consumption_persistence_failed", now)
        if (not isinstance(recorded, Mapping) or recorded.get("success") is not True
                or recorded.get("created") not in {True, False}):
            return _contained("herdmaster_management_consumption_persistence_unproven", now)
        if recorded.get("created") is False:
            return {**result, "status": "herdmaster_management_round_replay_suppressed",
                "specialist_result": None, "accepted_work_item_count": 0}
    return result


def _connect():
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)


def _load_observations(owner_user_id):
    with _connect() as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'owner_observation'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s order by created_at,review_event_id""", (OBSERVATION_SOURCE,))
            rows = [row[0] for row in cursor.fetchall() if isinstance(row[0], dict)]
    return [row for row in rows if row.get("authenticated_owner") is True
            and str(row.get("owner_user_id") or "") == str(owner_user_id)
            and row.get("provider_message_id") and row.get("provider_timestamp")]


def _load_active_lifecycles(owner_user_id):
    with _connect() as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select h.review_json->'herdmaster_health_loss',
                       f.review_json->'family_message_lifecycle'->>'telegram_message_id'
                from public.sam_live_stock_conversation_review_events h
                left join lateral (
                    select review_json from public.sam_live_stock_conversation_review_events f
                    where f.event_source='oom_sakkie_family_message_lifecycle'
                      and f.review_json->'family_message_lifecycle'->>'card_mission_id'
                          = h.review_json->'herdmaster_health_loss'->>'mission_id'
                      and f.review_json->'family_message_lifecycle'->>'state' in ('delivered','updated')
                    order by f.created_at desc,f.review_event_id desc limit 1
                ) f on true
                where h.event_source='oom_sakkie_herdmaster_health_loss_runtime'
                  and h.review_json->'herdmaster_health_loss'->>'owner_user_id'=%s
                order by h.created_at,h.review_event_id""", (str(owner_user_id),))
            rows = [(row[0], str(row[1] or "")) for row in cursor.fetchall() if isinstance(row[0], dict)]
    active = {}
    for row, card_message_id in rows:
        identity = ((row.get("preview") or {}).get("evaluator") or {}).get("identity") or {}
        pig_id = str(identity.get("pig_id") or "")
        if not pig_id:
            continue
        lifecycle_id = str(row.get("mission_id") or "")
        if row.get("status") in {"waiting_for_input", "preview_ready", "waiting_for_confirmation",
                                  "preview_correction_pending"} and card_message_id:
            observations = (((row.get("preview") or {}).get("evaluator") or {}).get("observations") or [])
            reported_dead = _retained_owner_reported_death(row, observations, owner_user_id)
            projected = {"pig_id": pig_id, "lifecycle_id": lifecycle_id,
                "state": str(row.get("status")), "card_message_id": card_message_id,
                "tag_number": str(identity.get("tag_number") or identity.get("name") or pig_id),
                "provider_timestamp": str(row.get("provider_timestamp") or ""),
                "current_question": str((((row.get("preview") or {}).get("evaluator") or {}).get(
                    "smallest_missing_follow_up_question") or "")),
                "owner_text": str(row.get("owner_text") or ""), "reported_dead": reported_dead}
            active[pig_id] = _retain_active_mortality_context(active.get(pig_id), projected)
        else:
            # Chronology is ordered. A later terminal lifecycle for an animal
            # supersedes stale earlier active projections for that animal.
            active.pop(pig_id, None)
    return list(active.values())


def _retain_active_mortality_context(previous, current):
    """A later lifecycle projection cannot erase earlier proven death context."""
    previous_id=str(previous.get("lifecycle_id") or "") if isinstance(previous,dict) else ""
    current_id=str(current.get("lifecycle_id") or "")
    if (not previous_id or not current_id or previous_id != current_id
            or previous.get("reported_dead") is not True):
        return current
    return {**current, "reported_dead": True, "current_question": ""}


def _retained_owner_reported_death(row, observations, owner_user_id):
    if str(row.get("owner_user_id") or "") != str(owner_user_id):
        return False
    if any(isinstance(item, dict) and item.get("fact") == "animal_reported_dead"
           and item.get("value") is True for item in observations or ()):
        return True
    semantic = row.get("semantic_interpretation")
    if not isinstance(semantic, dict):
        return False
    # Older health/loss evaluators retained the authenticated natural death
    # report and its semantic binding without projecting animal_reported_dead.
    # This supports manager coordination only; it grants no canonical write.
    verbatim = str(row.get("owner_text_verbatim") or "").strip()
    retained_sha = str(row.get("retained_owner_text_sha256") or "").strip().lower()
    if retained_sha and hashlib.sha256(verbatim.encode("utf-8")).hexdigest() != retained_sha:
        return False
    identity = ((row.get("preview") or {}).get("evaluator") or {}).get("identity") or {}
    def entity_alias(value):
        normalized = " ".join(str(value or "").casefold().split())
        return normalized[4:] if normalized.startswith("pig ") else normalized
    references = {entity_alias(value) for value in semantic.get("entity_refs") or ()
                  if entity_alias(value)}
    identifiers = {entity_alias(identity.get(key)) for key in ("pig_id", "tag_number", "name")
                   if entity_alias(identity.get(key))}
    if not references.intersection(identifiers):
        return False
    try:
        from modules.pig_weights.herdmaster_natural_health_loss_intake import _parse_report
        parsed = _parse_report(verbatim, datetime.fromisoformat(
            str(row.get("provider_timestamp") or "").replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return False
    deterministic_death = any(item.get("fact") == "animal_reported_dead" and item.get("value") is True
                              for item in parsed.get("observed") or () if isinstance(item, dict))
    return (bool(verbatim)
        and bool(str(row.get("provider_message_id") or "").strip())
        and bool(str(row.get("provider_timestamp") or "").strip())
        and semantic.get("domain") == "herd_health"
        and semantic.get("intent") == "report_death"
        and float(semantic.get("confidence") or 0) >= 0.8
        and semantic.get("continuation") is True
        and semantic.get("needs_clarification") is False
        and deterministic_death)


def _load_prior_consumptions(owner_user_id, invocation_context_digest):
    owner_hash = hashlib.sha256(json.dumps({"owner_user_id": str(owner_user_id)},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with _connect() as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'herdmaster_management_consumption'->'binding'
                from public.sam_live_stock_conversation_review_events where event_source=%s
                  and review_json->'herdmaster_management_consumption'->'binding'->>'authenticated_owner_identity_sha256'=%s
                  and review_json->'herdmaster_management_consumption'->'binding'->'invocation_context'->>'digest'=%s
                order by created_at,review_event_id""", (EVENT_SOURCE, owner_hash, invocation_context_digest))
            bindings = [row[0] for row in cursor.fetchall() if isinstance(row[0], dict)]
    return [{"management_round_identity": row.get("management_round_identity"),
        "deduplication_key": row.get("deduplication_key"), "result_digest": row.get("result_digest"),
        "evidence_generation": row.get("evidence_generation"),
        "active_case_digest": (row.get("active_case_deduplication_state") or {}).get("digest"),
        "invocation_context_digest": (row.get("invocation_context") or {}).get("digest")} for row in bindings]


def _record_consumption(result):
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    binding = dict(result["binding"])
    identity = _consumption_claim_identity(binding)
    event = build_sam_live_stock_review_event({"conversation_id": identity}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "internal_management_consumption"}, event_source=EVENT_SOURCE)
    event["review_event_id"] = identity; event["chatwoot_conversation_id"] = identity
    event["review_json"] = {"herdmaster_management_consumption": {"binding": binding,
        "accepted_work_item_ids": [item.item_id for item in result["specialist_result"].work_items],
        "zero_authority": True}}
    event["decision_json"]={}; event["facts_json"]={}; event["customer_message_excerpt"]=""; event["sam_reply_excerpt"]=""
    saved, status = record_sam_live_stock_review_event(event)
    if status >= 400 or saved.get("success") is not True:
        raise RuntimeError("herdmaster_management_consumption_persistence_failed")
    return saved


def _consumption_claim_identity(binding):
    claim_binding = {key: binding.get(key) for key in (
        "authenticated_owner_identity_sha256", "management_round_identity",
        "deduplication_key", "result_digest", "evidence_generation")}
    claim_binding["active_case_digest"] = (binding.get("active_case_deduplication_state") or {}).get("digest")
    claim_binding["invocation_context_digest"] = (binding.get("invocation_context") or {}).get("digest")
    return "OOM-HERD-MGMT-" + hashlib.sha256(json.dumps(claim_binding, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest().upper()


def _contained(reason, now):
    return {"success": False, "status": "herdmaster_management_runtime_contained",
        "systemic_exception": {"reason": reason, "observed_at": now.isoformat()},
        "specialist_result": None, "accepted_work_item_count": 0, **ZERO_AUTHORITY}
