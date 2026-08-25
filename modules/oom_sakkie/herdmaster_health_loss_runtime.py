"""Authenticated natural HERDMASTER health/welfare intake for Oom Sakkie.

This is the operational bridge from the existing private Telegram gateway to
the reviewed zero-I/O HERDMASTER evaluator.  It reads canonical farm evidence
and records only private intake lifecycle evidence; it grants no farm write or
medical authority.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from modules.oom_sakkie.herdmaster_health_loss_preview import prepare_health_loss_owner_preview
from modules.pig_weights.farm_supabase_read_service import (
    get_litter_register_rows,
    get_mating_overview,
    get_pig_master_rows,
)
from modules.pig_weights.herdmaster_health_loss_recording import confirm_health_loss_preview
from modules.pig_weights.pig_welfare_case_runtime import (
    append_welfare_case_context,
    load_open_welfare_case_contexts,
    welfare_case_runtime_enabled,
)


EVENT_SOURCE = "oom_sakkie_herdmaster_health_loss_runtime"
CONTEXT_WINDOW = timedelta(hours=24)
HEALTH_PATTERN = re.compile(
    r"\b(?:pig|tag|vark)\s*[a-z0-9-]+\b.*\b(?:"
    r"not eating|won't eat|wont eat|laying down|lying down|acting weird|"
    r"sick|ill|injured|limping|bleeding|dead|died|farrowing|stillborn|"
    r"infection|vomit|diarrh|cough|breath|cannot stand|can't stand|"
    r"dood|gesterf|siek|beseer|eet nie|mank|bloei"
    r")\b|\b(?:sick|injured|dead|died|farrowing|stillborn|dood|gesterf|siek|beseer)\b",
    re.I,
)
FOLLOW_UP_PATTERN = re.compile(
    r"\b(?:cannot|can't|cant|yes|no|seen alive|last seen|stand|standing|breathe|breathing|"
    r"drink|drinking|water|bleed|bleeding|distress|responsive|unresponsive|"
    r"removed|buried|disposed|cremated|body|verwyder|begrawe|weggegooi|liggaam)\b",
    re.I,
)
UNRELATED_OPERATIONAL_PATTERN = re.compile(
    r"\b(?:reservoir|storage tanks?|borehole|irrigation|valves?|b camp|c camp|"
    r"solar|soc|grid|inverter|power|fertili[sz]er)\b", re.I,
)
ENTITY_PATTERN = re.compile(
    r"\b(?:pig|tag|vark)\b(?:\s+(?:nr|no|number|nommer))?\s*#?\s*([a-z0-9-]+)\b", re.I)
CONFIRMATION_PATTERN = re.compile(r"^CONFIRM HERD-[A-Z0-9-]+$")
CORRECTION_PATTERN = re.compile(
    r"\b(?:correction|incorrect|wrong|must be|should be|mark(?:ed)? as|"
    r"no longer|exact time .{0,24}unknown|do not record this yet|don't record this yet)\b",
    re.I,
)
DECLINE_PATTERN = re.compile(r"^(?:cancel|decline|stop|do not record|don't record)[.! ]*$", re.I)


class ActiveContextLoadError(RuntimeError):
    pass


def handle_authenticated_health_loss_message(
    parsed: Mapping[str, Any], gateway_authority, *, connect_factory=None, context_store=None,
    claim_creator=None
):
    """Return one useful owner response, or ``handled=False`` for other intents."""
    parsed = parsed if isinstance(parsed, Mapping) else {}
    text = str(parsed.get("text") or "").strip()
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), Mapping) else {}
    provider_message_id = str(parsed.get("provider_message_id") or "").strip()
    provider_timestamp = str(parsed.get("provider_timestamp") or "").strip()
    output_language = "af" if str(parsed.get("output_language") or "en").casefold().startswith("af") else "en"
    explicit_health = bool(HEALTH_PATTERN.search(text) or (
        semantic.get("domain") == "herd_health" and not semantic.get("needs_clarification")))
    confirmation_shaped = bool(CONFIRMATION_PATTERN.fullmatch(text))
    plausible_follow_up = bool(
        FOLLOW_UP_PATTERN.search(text)
        and not UNRELATED_OPERATIONAL_PATTERN.search(text)
    ) or bool(semantic.get("domain") == "herd_health" and semantic.get("continuation")
              and not semantic.get("needs_clarification"))
    reply_to_message_id = str(parsed.get("reply_to_message_id") or "").strip()
    # Active-case persistence belongs only to this specialist boundary.  Do
    # not make unrelated read-only gateway traffic depend on its store merely
    # to establish that HERDMASTER is not applicable.
    explicit_entity = bool(ENTITY_PATTERN.search(text))
    if (not explicit_health and not plausible_follow_up and not confirmation_shaped
            and not explicit_entity and not reply_to_message_id):
        return {"handled": False, "status": "health_loss_intake_not_applicable"}, 200
    try:
        contexts = _load_active_contexts(
            str(parsed.get("telegram_chat_id") or ""),
            owner_user_id=str(parsed.get("telegram_user_id") or ""),
            context_store=context_store)
    except ActiveContextLoadError:
        return {"handled": True, "success": False, "status": "health_loss_active_context_unavailable",
            "answer": _health_loss_message(output_language, "active_context_unavailable"),
            "records_audit_trace": False, "writes_farm_data": False,
            "protected_actions_performed": False}, 503
    stale_confirmation = next((row for row in contexts
        if confirmation_shaped and text.removeprefix("CONFIRM ") in {
            str(value) for value in row.get("invalidated_operation_ids") or []
        }), None)
    if stale_confirmation:
        return {"handled": True, "success": False,
            "status": "health_loss_stale_confirmation_invalidated",
            "answer": _health_loss_message(output_language, "stale_confirmation"),
            "mission_id": str(stale_confirmation.get("mission_id") or ""),
            "card_mission_id": str(stale_confirmation.get("mission_id") or ""),
            "records_audit_trace": True, "writes_farm_data": False,
            "protected_actions_performed": False}, 409
    active, ambiguity, superseded = _resolve_active_context(
        text, contexts, provider_message_id,
        reply_to_message_id=reply_to_message_id,
        provider_timestamp=provider_timestamp,
        entity_refs=semantic.get("entity_refs") or ())
    if ambiguity:
        if all(str(row.get("status") or "").startswith("waiting_for_context")
               for row in ambiguity):
            return {"handled": True, "success": True,
                    "status": "health_loss_pending_context_ambiguous",
                    "answer": _health_loss_message(output_language, "pending_ambiguous"),
                    "question_count": 1, "writes_farm_data": False,
                    "protected_actions_performed": False}, 200
        ambiguity_id = "OOM-HERDMASTER-CONTEXT-" + hashlib.sha256(
            f"{parsed.get('telegram_user_id')}|{parsed.get('telegram_chat_id')}|{provider_message_id}".encode()
        ).hexdigest()[:24].upper()
        pending = {
            "chat_id": str(parsed.get("telegram_chat_id") or ""),
            "owner_user_id": str(parsed.get("telegram_user_id") or ""),
            "provider_message_id": provider_message_id,
            "provider_timestamp": provider_timestamp,
            "mission_id": ambiguity_id,
            "status": "waiting_for_context",
            "pending_text": text,
            "pending_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "candidate_bindings": [{"mission_id": str(row.get("mission_id") or ""),
                                     "tag_number": _context_tag(row)} for row in ambiguity],
            "event_phase": "context_disambiguation_pending",
        }
        stored = _record_lifecycle_event(pending, context_store=context_store)
        if stored.get("success") is not True:
            return {"handled": True, "success": False,
                    "status": "health_loss_context_persistence_failed",
                    "writes_farm_data": False, "protected_actions_performed": False}, 503
        return {"handled": True, "success": True, "status": "health_loss_context_disambiguation_required",
            "answer": _health_loss_message(output_language, "identity_required"),
            "question_count": 1,
            "retained_owner_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "mission_id": ambiguity_id, "card_mission_id": ambiguity_id,
            "records_audit_trace": False, "writes_farm_data": False,
            "protected_actions_performed": False}, 200
    active_status = str((active or {}).get("status") or "")
    superseded = sorted(set(superseded) | {
        str(value) for value in (active or {}).get("superseded_duplicate_missions") or []
        if str(value or "")
    })
    superseded_bindings = list((active or {}).get("superseded_duplicate_bindings") or [])
    known_binding_ids = {str(value.get("mission_id") or "") for value in superseded_bindings
                         if isinstance(value, Mapping)}
    active_tag = _context_tag(active or {})
    for mission in superseded:
        target = next((row for row in contexts if str(row.get("mission_id") or "") == mission), None)
        if target and mission not in known_binding_ids and active_tag and _context_tag(target) == active_tag:
            superseded_bindings.append({"mission_id": mission,
                "provider_message_id": str(target.get("provider_message_id") or ""),
                "tag_number": active_tag})
    confirmation = bool(active and active_status in {"preview_ready", "waiting_for_confirmation", "completed"}
                        and text == "CONFIRM " + str(active.get("operation_id") or ""))
    follow_up = bool(active and not confirmation and active_status in {
        "waiting_for_input", "preview_ready", "waiting_for_confirmation",
        "preview_correction_pending",
    })
    if (not explicit_health and not follow_up and not confirmation
            and not explicit_entity and not reply_to_message_id):
        return {"handled": False, "status": "health_loss_intake_not_applicable"}, 200
    if reply_to_message_id and not active:
        return {"handled": False, "status": "health_loss_reply_without_active_context"}, 200
    if explicit_entity and not active and not explicit_health:
        return {"handled": False, "status": "health_loss_entity_without_active_context"}, 200

    if not provider_message_id or not provider_timestamp:
        return {"handled": True, "success": False, "status": "health_loss_provider_identity_required",
                "answer": _health_loss_message(output_language, "provider_identity_required")}, 409
    if active and not _chronology_allows(active, provider_message_id, provider_timestamp):
        return {"handled": True, "success": False, "status": "health_loss_follow_up_chronology_conflict",
            "answer": _health_loss_message(output_language, "chronology_conflict"),
            "mission_id": str(active.get("mission_id") or ""),
            "card_mission_id": str(active.get("mission_id") or ""),
            "records_audit_trace": False, "writes_farm_data": False,
            "protected_actions_performed": False}, 409

    if active_status != "preview_correction_pending" and active and ((str(active.get("provider_message_id") or "") == provider_message_id
                    and str(active.get("provider_timestamp") or "") == provider_timestamp)
                   or (str(active.get("clarification_provider_message_id") or "") == provider_message_id
                       and str(active.get("clarification_provider_timestamp") or "") == provider_timestamp)):
        result = _existing_lifecycle_result(active)
        result.update({"status": "health_loss_inbound_replay_suppressed",
                       "answer": "", "suppress_owner_delivery": True,
                       "replay_suppressed": True})
        return result, 200

    consumed_pending_context = ""
    evidence_provider_message_id = provider_message_id
    evidence_provider_timestamp = provider_timestamp
    if active and explicit_entity and not explicit_health and not plausible_follow_up:
        pending = active.get("_pending_clarification") if isinstance(
            active.get("_pending_clarification"), Mapping) else None
        if pending:
            if not _timestamp_strictly_after(provider_timestamp,
                                             str(pending.get("provider_timestamp") or "")):
                return {"handled": True, "success": False,
                        "status": "health_loss_context_resolution_chronology_conflict",
                        "writes_farm_data": False, "protected_actions_performed": False}, 409
            claimed = bool(active.get("_pending_claimed")) or _claim_pending_context(
                pending, active, parsed, context_store=context_store)
            if not claimed:
                return {"handled": True, "success": False,
                        "status": "health_loss_context_consumption_already_claimed",
                        "writes_farm_data": False, "protected_actions_performed": False}, 409
            consumed_pending_context = str(pending.get("mission_id") or "")
            evidence_provider_message_id = str(pending.get("provider_message_id") or "")
            evidence_provider_timestamp = str(pending.get("provider_timestamp") or "")
            text = str(pending.get("pending_text") or "")
            plausible_follow_up = True
            active = {key: value for key, value in active.items() if key != "_pending_clarification"}
        else:
            clarification = {**dict(active),
            "provider_message_id": provider_message_id,
            "provider_timestamp": provider_timestamp,
            "clarification_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "event_phase": "entity_clarification_retained"}
            stored = _record_lifecycle_event(clarification, context_store=context_store)
            if stored.get("success") is not True:
                return {"handled": True, "success": False,
                        "status": "health_loss_lifecycle_persistence_failed"}, 503
            result = _existing_lifecycle_result(active)
            result.update({"status": "health_loss_entity_clarification_retained",
                           "answer": "", "suppress_owner_delivery": True})
            return result, 200

    if confirmation:
        if parsed.get("callback_confirmation") is True:
            active_preview=active.get("preview") if isinstance(active.get("preview"),Mapping) else {}
            binding=active_preview.get("confirmation_binding") if isinstance(
                active_preview.get("confirmation_binding"),Mapping) else {}
            evaluator=active_preview.get("evaluator") if isinstance(active_preview.get("evaluator"),Mapping) else {}
            active_identity=evaluator.get("identity") if isinstance(evaluator.get("identity"),Mapping) else {}
            if (str(parsed.get("protected_preview_sha256") or "")!=str(binding.get("preview_sha256") or "")
                    or dict(parsed.get("protected_preview_identity") or {})!=dict(active_identity)):
                return {"handled":True,"success":False,"status":"health_loss_protected_preview_binding_mismatch",
                  "answer":_health_loss_message(output_language, "binding_mismatch"),
                  "writes_farm_data":False,"protected_actions_performed":False},409
        recorded, recorded_status = confirm_health_loss_preview(
            active, text, actor_id=str(parsed.get("telegram_user_id") or ""),
            evidence_loader=lambda: load_canonical_health_loss_evidence(connect_factory=connect_factory),
            connect_factory=connect_factory,
        )
        mission_id = str(active.get("mission_id") or "")
        answer = _health_loss_message(output_language,
            "observation_recorded" if recorded.get("success") else "recording_contained")
        if recorded.get("success") and str(recorded.get("status") or "").startswith("mortality_lifecycle_"):
            answer = ("✅ <b>PIG LIFECYCLE UPDATED</b>\n\n"
                      "The confirmed outcome was recorded once: the pig is Deceased and no longer current/on farm. "
                      "The current pen and availability projections will exclude the pig. Historical records remain preserved. "
                       "Exact time of death, cause, diagnosis and treatment remain Unknown.")
            answer = _mortality_completion_message(
                recorded, str(active.get("output_language") or "en"))
        lifecycle = {**dict(active), "provider_message_id": provider_message_id,
            "provider_timestamp": provider_timestamp,
            "status": "completed" if recorded.get("success") else "contained",
            "owner_text": answer, "recording_result": recorded,
            "event_phase": "recording_completed" if recorded.get("success") else "recording_contained"}
        persisted = _record_lifecycle_event(lifecycle, context_store=context_store)
        if persisted.get("success") is not True:
            return {"handled": True, "success": False,
                "status": "health_loss_completion_persistence_pending",
                "answer": _health_loss_message(output_language, "completion_recovery"),
                "mission_id": mission_id, "card_mission_id": mission_id,
                "records_audit_trace": False,
                "writes_farm_data": bool(recorded.get("writes_farm_data")),
                "rows_created": int(recorded.get("rows_created") or 0),
                "protected_actions_performed": bool(recorded.get("writes_farm_data"))}, 503
        return {"handled": True, "success": recorded.get("success") is True,
            "status": lifecycle["status"], "answer": answer, "mission_id": mission_id,
            "card_mission_id": mission_id, "records_audit_trace": True,
            "writes_farm_data": bool(recorded.get("writes_farm_data")),
            "rows_created": int(recorded.get("rows_created") or 0),
            "protected_actions_performed": bool(recorded.get("writes_farm_data"))}, recorded_status

    active_for_message = active if follow_up else None
    owner_intent = _classify_preview_owner_intent(text, active_for_message)
    correction_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if (active_for_message and owner_intent == "corrects_preview"
            and str(active_for_message.get("provider_message_id") or "") == provider_message_id
            and str(active_for_message.get("correction_digest") or "") == correction_digest
            and active_status == "preview_ready"):
        return _existing_lifecycle_result(active_for_message), 200
    if active_for_message and owner_intent == "declines_preview":
        mission_id = str(active_for_message.get("mission_id") or "")
        lifecycle = {**dict(active_for_message), "provider_message_id": provider_message_id,
            "provider_timestamp": provider_timestamp, "status": "contained",
            "owner_intent": owner_intent,
            "invalidated_operation_ids": sorted(set(
                list(active_for_message.get("invalidated_operation_ids") or [])
                + [str(active_for_message.get("operation_id") or "")]
            )),
            "owner_text": _health_loss_message(output_language, "cancelled"),
            "event_phase": "preview_declined"}
        stored = _record_lifecycle_event(lifecycle, context_store=context_store)
        if stored.get("success") is not True:
            return {"handled": True, "success": False,
                    "status": "health_loss_lifecycle_persistence_failed"}, 503
        return {"handled": True, "success": True, "status": "contained",
            "answer": lifecycle["owner_text"], "mission_id": mission_id,
            "card_mission_id": mission_id, "records_audit_trace": True,
            "writes_farm_data": False, "protected_actions_performed": False}, 200

    previous_operation_id = ""
    preview_history = list((active_for_message or {}).get("preview_history") or [])
    resuming_correction = bool(active_for_message
        and active_status == "preview_correction_pending"
        and str(active_for_message.get("provider_message_id") or "") == provider_message_id
        and str(active_for_message.get("correction_digest") or "") == correction_digest)
    if active_for_message and owner_intent == "corrects_preview":
        previous_operation_id = str(active_for_message.get("operation_id") or "")
        old_preview = active_for_message.get("preview") if isinstance(active_for_message.get("preview"), Mapping) else {}
        if not resuming_correction:
            preview_history.append({
                "operation_id": previous_operation_id,
                "preview_sha256": str((old_preview.get("confirmation_binding") or {}).get("preview_sha256") or ""),
                "provider_message_id": str(active_for_message.get("provider_message_id") or ""),
                "status": "invalidated_by_owner_correction",
                "invalidated_by_provider_message_id": provider_message_id,
                "preview": old_preview,
            })
            pending = {**dict(active_for_message), "provider_message_id": provider_message_id,
                "provider_timestamp": provider_timestamp, "status": "preview_correction_pending",
                "owner_intent": owner_intent, "correction_digest": correction_digest,
                "preview_history": preview_history,
                "invalidated_operation_ids": sorted(set(
                    list(active_for_message.get("invalidated_operation_ids") or [])
                    + ([previous_operation_id] if previous_operation_id else [])
                )), "event_phase": "preview_invalidated"}
            invalidated = _record_lifecycle_event(pending, context_store=context_store)
            if invalidated.get("success") is not True:
                return {"handled": True, "success": False,
                        "status": "health_loss_preview_invalidation_failed",
                        "writes_farm_data": False, "protected_actions_performed": False}, 503
    context_text = str((active_for_message or {}).get("combined_text") or "").strip()
    joiner = "Owner correction:" if owner_intent == "corrects_preview" else "Follow-up:"
    semantic_observation = str(semantic.get("observation") or "").strip()
    interpreted = (f" Semantic interpretation pending owner preview confirmation: {semantic_observation}"
                   if semantic.get("domain") == "herd_health"
                   and float(semantic.get("confidence") or 0) >= 0.8
                   and semantic_observation else "")
    current_text = (text + interpreted).strip()
    combined_text = f"{context_text} {joiner} {current_text}".strip() if context_text else current_text
    evidence = load_canonical_health_loss_evidence(connect_factory=connect_factory)
    envelope = {
        "gateway_authority": gateway_authority,
        "provider_message_id": evidence_provider_message_id,
        "provider_timestamp": evidence_provider_timestamp,
        "provider_timezone": "Africa/Johannesburg",
        "output_language": output_language,
        "text": combined_text,
    }
    preview = prepare_health_loss_owner_preview(envelope, evidence)
    owner_text = _owner_message(preview)
    mission_id = str((active_for_message or {}).get("mission_id") or "") or "OOM-HERDMASTER-" + hashlib.sha256(
        f"{parsed.get('telegram_user_id')}|{parsed.get('telegram_chat_id')}|{provider_message_id}".encode()
    ).hexdigest()[:24].upper()
    lifecycle = {
        "chat_id": str(parsed.get("telegram_chat_id") or ""),
        "owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "provider_message_id": provider_message_id,
        "provider_timestamp": provider_timestamp,
        "evidence_provider_message_id": evidence_provider_message_id,
        "evidence_provider_timestamp": evidence_provider_timestamp,
        "combined_text": combined_text,
        "owner_text_verbatim": text,
        "semantic_interpretation": dict(semantic) if semantic else {},
        "status": "waiting_for_input" if int(preview.get("question_count") or 0) else "preview_ready",
        "operation_id": str((preview.get("confirmation_binding") or {}).get("operation_id") or ""),
        "evidence_generation": str(evidence.get("evidence_generation") or ""),
        "owner_text": owner_text,
        "output_language": output_language,
        "preview": preview,
        "mission_id": mission_id,
        "owner_intent": owner_intent,
        "correction_digest": correction_digest if owner_intent == "corrects_preview" else "",
        "preview_history": preview_history,
        "invalidated_operation_ids": sorted(set(
            list((active_for_message or {}).get("invalidated_operation_ids") or [])
            + ([previous_operation_id] if previous_operation_id else [])
        )),
        "event_phase": "preview_corrected" if owner_intent == "corrects_preview" else "preview_generated",
        "superseded_duplicate_missions": superseded,
        "superseded_duplicate_bindings": superseded_bindings,
        "consumed_context_missions": sorted(set(
            list((active_for_message or {}).get("consumed_context_missions") or [])
            + ([consumed_pending_context] if consumed_pending_context else [])
        )),
    }
    stored = _record_lifecycle_event(lifecycle, context_store=context_store)
    if stored.get("success") is not True:
        return {"handled": True, "success": False, "status": "health_loss_lifecycle_persistence_failed"}, 503
    welfare_case = stored.get("welfare_case") or {
        "success": True, "status": "welfare_case_test_store_not_applicable", "rows_created": 0,
    }
    protected={}
    if lifecycle["status"]=="preview_ready" and lifecycle["operation_id"] and (claim_creator or os.getenv("DATABASE_URL")):
        from modules.oom_sakkie.protected_action_claims import (
            build_buttons, create_claim, protected_card_mission_id)
        creator=claim_creator or create_claim
        try:
            claim=creator(action_kind="mortality",owner_user_id=lifecycle["owner_user_id"],
              private_chat_id=lifecycle["chat_id"],mission_id=mission_id,
              provider_message_id=provider_message_id,evidence_generation=lifecycle["evidence_generation"],
              preview_payload={"operation_id":lifecycle["operation_id"],
                "preview_sha256":str((preview.get("confirmation_binding") or {}).get("preview_sha256") or ""),
                "identity":(preview.get("evaluator") or {}).get("identity") or {},
                "event_family":str((preview.get("evaluator") or {}).get("event_family") or ""),
                "effect_kind":("mortality" if _preview_is_mortality(preview)
                               else "health_observation")})
            protected={"preview_digest":claim["preview_digest"],"callback_token":claim["callback_token"],
                       "action_kind":str(claim.get("action_kind") or "mortality"),
                       "card_mission_id":protected_card_mission_id(
                           mission_id, claim["preview_digest"]),
                       "reply_markup":build_buttons(claim["callback_token"],grouped=False,
                           language=output_language)}
        except Exception:
            return {"handled":True,"success":False,"status":"health_loss_protected_claim_unavailable",
                    "answer":_health_loss_message(output_language, "claim_unavailable"),
                    "writes_farm_data":False},503
    return {
        "handled": True,
        "success": True,
        "status": lifecycle["status"],
        "answer": owner_text,
        "tool_used": "herdmaster_health_loss_preview",
        "question_count": int(preview.get("question_count") or 0),
        "operation_id": lifecycle["operation_id"],
        "owner_intent": owner_intent,
        "invalidated_operation_ids": lifecycle["invalidated_operation_ids"],
        "mission_id": mission_id,
        "card_mission_id": mission_id,
        "superseded_duplicate_missions": superseded,
        "superseded_duplicate_bindings": superseded_bindings,
        "records_audit_trace": True,
        "writes_farm_data": False,
        "protected_actions_performed": False,
        "welfare_case": welfare_case,
        "welfare_case_id": str(welfare_case.get("welfare_case_id") or ""),
        "welfare_case_persistence_degraded": welfare_case.get("success") is not True,
        **protected,
    }, 200


def _classify_preview_owner_intent(text: str, active: Mapping[str, Any] | None) -> str:
    if not active:
        return "new_report"
    if DECLINE_PATTERN.fullmatch(text.strip()):
        return "declines_preview"
    if CORRECTION_PATTERN.search(text):
        return "corrects_preview"
    if text.strip().endswith("?"):
        return "asks_question"
    return "adds_evidence"


def _preview_is_mortality(preview: Mapping[str, Any]) -> bool:
    evaluator = preview.get("evaluator") if isinstance(preview.get("evaluator"), Mapping) else {}
    if str(evaluator.get("event_family") or "") in {
            "found_dead", "mortality", "maternal_death", "compound_loss"}:
        return True
    return any(isinstance(fact, Mapping)
               and fact.get("fact") == "animal_reported_dead"
               and fact.get("value") is True
               for effect in evaluator.get("canonical_effects") or []
               if isinstance(effect, Mapping)
               for fact in (effect.get("facts") or {}).get("observed", []))


def _health_loss_message(language: str, key: str) -> str:
    messages = {
        "en": {
            "active_context_unavailable": "<b>HERDMASTER FOLLOW-UP PAUSED</b>\n\nI could not safely read the active animal-case history. Nothing new was recorded.",
            "stale_confirmation": "<b>OLD HERDMASTER PREVIEW EXPIRED</b>\n\nThat confirmation belongs to an earlier corrected preview. Nothing was recorded. Use the current preview.",
            "pending_ambiguous": "<b>HERDMASTER - WHICH UPDATE?</b>\n\nMore than one pending update could match. Reply to the exact question card.",
            "identity_required": "<b>HERDMASTER NEEDS ONE IDENTITY</b>\n\nName the pig or tag once so I can bind this update safely. Nothing was recorded.",
            "provider_identity_required": "<b>HERDMASTER MESSAGE NOT ACCEPTED</b>\n\nThe authenticated message identity or timestamp is missing. Nothing was recorded.",
            "chronology_conflict": "<b>HERDMASTER FOLLOW-UP PAUSED</b>\n\nThis update conflicts with the active case chronology. Nothing was recorded.",
            "binding_mismatch": "<b>HERDMASTER PREVIEW CHANGED</b>\n\nThe protected preview no longer matches the active mortality case. Nothing was recorded.",
            "observation_recorded": "<b>HERDMASTER OBSERVATION RECORDED</b>\n\nThe confirmed factual observation was recorded once. No diagnosis or treatment was added.",
            "recording_contained": "<b>HERDMASTER RECORDING PAUSED</b>\n\nNothing was written. Refresh the exact preview before confirmation.",
            "completion_recovery": "<b>HERDMASTER COMPLETION NEEDS RECOVERY</b>\n\nThe farm operation completed, but the visible completion could not be saved. Do not repeat the farm action.",
            "cancelled": "<b>HERDMASTER PREVIEW CANCELLED</b>\n\nNothing was recorded.",
            "claim_unavailable": "<b>HERDMASTER CONFIRMATION UNAVAILABLE</b>\n\nThe preview was retained, but its protected buttons could not be stored safely. Nothing was recorded.",
        },
        "af": {
            "active_context_unavailable": "<b>HERDMASTER-OPVOLG OPGESKORT</b>\n\nEk kon nie die aktiewe diersaak se geskiedenis veilig lees nie. Niks nuuts is aangeteken nie.",
            "stale_confirmation": "<b>OU HERDMASTER-VOORSKOU HET VERVAL</b>\n\nDaardie bevestiging behoort aan 'n vroeere gekorrigeerde voorskou. Niks is aangeteken nie. Gebruik die huidige voorskou.",
            "pending_ambiguous": "<b>HERDMASTER - WATTER OPDATERING?</b>\n\nMeer as een hangende opdatering kan pas. Antwoord op die presiese vraagkaart.",
            "identity_required": "<b>HERDMASTER BENODIG EEN IDENTITEIT</b>\n\nNoem die vark of oorplaatjie een keer sodat ek die opdatering veilig kan koppel. Niks is aangeteken nie.",
            "provider_identity_required": "<b>HERDMASTER-BOODSKAP NIE AANVAAR NIE</b>\n\nDie geverifieerde boodskapidentiteit of tydstempel ontbreek. Niks is aangeteken nie.",
            "chronology_conflict": "<b>HERDMASTER-OPVOLG OPGESKORT</b>\n\nHierdie opdatering bots met die aktiewe saak se tydlyn. Niks is aangeteken nie.",
            "binding_mismatch": "<b>HERDMASTER-VOORSKOU HET VERANDER</b>\n\nDie beskermde voorskou pas nie meer by die aktiewe vrektesaak nie. Niks is aangeteken nie.",
            "observation_recorded": "<b>HERDMASTER-WAARNEMING AANGETEKEN</b>\n\nDie bevestigde feitelike waarneming is een keer aangeteken. Geen diagnose of behandeling is bygevoeg nie.",
            "recording_contained": "<b>HERDMASTER-AANTEKENING OPGESKORT</b>\n\nNiks is geskryf nie. Verfris die presiese voorskou voor bevestiging.",
            "completion_recovery": "<b>HERDMASTER-VOLTOOIING BENODIG HERSTEL</b>\n\nDie plaasaksie is voltooi, maar die sigbare voltooiing kon nie gestoor word nie. Moenie die aksie herhaal nie.",
            "cancelled": "<b>HERDMASTER-VOORSKOU GEKANSELLEER</b>\n\nNiks is aangeteken nie.",
            "claim_unavailable": "<b>HERDMASTER-BEVESTIGING NIE BESKIKBAAR NIE</b>\n\nDie voorskou is behou, maar die beskermde knoppies kon nie veilig gestoor word nie. Niks is aangeteken nie.",
        },
    }
    selected = "af" if str(language).casefold().startswith("af") else "en"
    return messages[selected][key]


def _mortality_completion_message(recorded: Mapping[str, Any], language: str) -> str:
    af = str(language).casefold().startswith("af")
    name = html.escape(str(recorded.get("pig_name") or recorded.get("tag_number") or
               ("Die vark" if af else "The pig")))
    if af:
        heading = (f"VARK {name} AANGETEKEN" if name.casefold() != "die vark"
                   else "VARK AANGETEKEN")
        lines = [f"<b>{heading}</b>", "",
                 "Die bevestigde afsterwe is een keer aangeteken en die vark is nie meer op die plaas beskikbaar nie."]
        if recorded.get("welfare_case_closed"):
            lines.append("Die verwante lewende-welsynsaak is met afsterwe as rede gesluit.")
        if recorded.get("living_checks_reconciled"):
            lines.append("Toekomstige lewende-dier kontroles wat nie meer geldig is nie, is afgesluit.")
        lines.append("Oorsaak en presiese tyd bly Onbekend.")
        if int(recorded.get("preserved_distinct_work") or 0):
            lines.append("Afsonderlike wegdoenings- of biosekuriteitswerk bly sigbaar omdat dit nog oop is.")
    else:
        lines = [f"<b>{name} - DEATH RECORDED</b>", "",
                 "The confirmed death was recorded once and the pig is no longer available on farm."]
        if recorded.get("welfare_case_closed"):
            lines.append("The related living-welfare case was closed with death as the reason.")
        if recorded.get("living_checks_reconciled"):
            lines.append("Future living-animal checks that no longer apply were closed.")
        lines.append("Cause and exact time remain Unknown.")
        if int(recorded.get("preserved_distinct_work") or 0):
            lines.append("Separate disposal or biosecurity work stays visible because it is still open.")
    return "\n".join(lines)


def mortality_completion_recovery_result(stored: Mapping[str, Any],
                                          preview_payload: Mapping[str, Any],
                                          language: str) -> dict:
    """Recompose owner presentation from a completed claim without farm I/O."""
    identity = preview_payload.get("identity") if isinstance(
        preview_payload.get("identity"), Mapping) else {}
    presentation_facts = {**dict(stored),
        "pig_name": str(identity.get("name") or identity.get("pig_name") or ""),
        "tag_number": str(identity.get("tag_number") or identity.get("tag") or "")}
    return {**dict(stored),
        "answer": _mortality_completion_message(presentation_facts, language),
        "recipient_render_contract": "specialist_structured_recipient_v1",
        "recipient_language": "af" if str(language).casefold().startswith("af") else "en",
        "owner_visible_completion_policy": "verified_edit_or_new_message",
        "writes_farm_data": False, "rows_created": 0,
        "delivery_recovery_required": True}


def _existing_lifecycle_result(active: Mapping[str, Any]) -> dict:
    preview = active.get("preview") if isinstance(active.get("preview"), Mapping) else {}
    return {"handled": True, "success": True,
        "status": str(active.get("status") or "preview_ready"),
        "answer": str(active.get("owner_text") or ""),
        "tool_used": "herdmaster_health_loss_preview",
        "question_count": int(preview.get("question_count") or 0),
        "operation_id": str(active.get("operation_id") or ""),
        "mission_id": str(active.get("mission_id") or ""),
        "card_mission_id": str(active.get("mission_id") or ""),
        "owner_intent": str(active.get("owner_intent") or "adds_evidence"),
        "invalidated_operation_ids": list(active.get("invalidated_operation_ids") or []),
        "records_audit_trace": True, "writes_farm_data": False,
        "protected_actions_performed": False}


def load_canonical_health_loss_evidence(*, connect_factory=None):
    animals = []
    for row in get_pig_master_rows(connect_factory=connect_factory):
        animals.append({
            "pig_id": str(row.get("Pig_ID") or ""),
            "name": str(row.get("Pig_Name") or ""),
            "tag_number": str(row.get("Tag_Number") or ""),
            "lifecycle_status": str(row.get("Status") or "Unknown"),
            "on_farm": str(row.get("On_Farm") or "").lower() == "yes",
            "availability": str(row.get("Purpose") or "Unknown"),
            "pen": str(row.get("Current_Pen_ID") or "Unknown"),
            "birth_date": str(row.get("Date_Of_Birth") or ""),
            "lifecycle_effective_date": str(row.get("Exit_Date") or ""),
        })
    matings = [{
        "mating_id": str(row.get("mating_id") or ""),
        "sow_pig_id": str(row.get("sow_pig_id") or ""),
        "boar_pig_id": str(row.get("boar_pig_id") or ""),
        "date": str(row.get("mating_date") or ""),
        "is_open": str(row.get("is_open") or "").lower() in {"yes", "true", "1"},
    } for row in get_mating_overview(connect_factory=connect_factory)]
    litters = [{
        "litter_id": str(row.get("Litter_ID") or ""),
        "sow_pig_id": str(row.get("Sow_Pig_ID") or ""),
        "farrowing_date": str(row.get("Farrowing_Date") or ""),
    } for row in get_litter_register_rows(connect_factory=connect_factory)]
    material = json.dumps({"animals": animals, "matings": matings, "litters": litters}, sort_keys=True, separators=(",", ":"))
    return {
        "evidence_generation": hashlib.sha256(material.encode()).hexdigest(),
        "as_of_timestamp": datetime.now(timezone.utc).isoformat(),
        "animals": animals,
        "matings": matings,
        "litters": litters,
    }


def _owner_message(preview: Mapping[str, Any]) -> str:
    # The pure composer owns every visible fragment and its recipient language.
    # Do not wrap it with a second, hard-coded English projection.
    if str(preview.get("owner_text") or "").strip():
        return str(preview["owner_text"])
    evaluator = preview.get("evaluator") if isinstance(preview.get("evaluator"), Mapping) else {}
    identity = evaluator.get("identity") if isinstance(evaluator.get("identity"), Mapping) else {}
    question = str(evaluator.get("smallest_missing_follow_up_question") or preview.get("owner_text") or "").strip()
    if not preview.get("success") and question:
        return f"⚠️ <b>ANIMAL CHECK NEEDED</b>\n\n{question}"
    if int(preview.get("question_count") or 0) > 0:
        label = str(identity.get("tag_number") or identity.get("name") or "the pig")
        action = str((evaluator.get("immediate_welfare_priority") or {}).get("action") or "Please check the animal now.")
        return (
            f"🚨 <b>PIG {label} NEEDS CHECKING</b>\n\n"
            "I’ve matched the report to the herd record and retained what you already told me.\n\n"
            f"<b>Check now:</b> {action}\n\n<b>One update needed:</b> {question}"
        )
    return (
        "✅ <b>HERDMASTER PREVIEW READY</b>\n\n"
        + str(preview.get("owner_text") or "")
    )


def _record_lifecycle_event(lifecycle: Mapping[str, Any], *, context_store=None):
    event_id = "OOM-HERD-HEALTH-" + hashlib.sha256(
        (
            f"{lifecycle.get('chat_id')}|{lifecycle.get('provider_message_id')}|"
            f"{lifecycle.get('mission_id')}|{lifecycle.get('event_phase') or 'lifecycle'}"
        ).encode()
    ).hexdigest()[:24].upper()
    if context_store is not None:
        return context_store("record", event_id, dict(lifecycle))
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    event = build_sam_live_stock_review_event(
        {"conversation_id": "oom-health-" + str(lifecycle.get("chat_id"))}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "herdmaster_health_loss_intake"},
        event_source=EVENT_SOURCE,
    )
    event["review_event_id"] = event_id
    event["review_json"] = {"herdmaster_health_loss": dict(lifecycle)}
    event["decision_json"] = {}
    event["facts_json"] = {}
    event["customer_message_excerpt"] = ""
    event["sam_reply_excerpt"] = ""
    result, status = record_sam_live_stock_review_event(event)
    stored = status < 400 and result.get("success") is True
    welfare_case = None
    if stored and welfare_case_runtime_enabled():
        welfare_case = append_welfare_case_context(lifecycle)
    return {**result, "success": stored, "welfare_case": welfare_case}


def _claim_pending_context(pending, target, parsed, *, context_store=None):
    claim = {**dict(pending),
        "status": "waiting_for_context_consumption",
        "resolution_provider_message_id": str(parsed.get("provider_message_id") or ""),
        "resolution_provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "resolution_text_sha256": hashlib.sha256(
            str(parsed.get("text") or "").encode("utf-8")).hexdigest(),
        "target_mission_id": str(target.get("mission_id") or ""),
        "event_phase": "context_consumption_claimed"}
    recorded = _record_lifecycle_event(claim, context_store=context_store)
    return recorded.get("success") is True and recorded.get("created") is not False


def _load_active_context(chat_id: str, *, context_store=None):
    contexts = _load_active_contexts(chat_id, context_store=context_store)
    return contexts[0] if contexts else None


def _load_active_contexts(chat_id: str, *, owner_user_id="", context_store=None):
    if not chat_id:
        return []
    if context_store is not None:
        try:
            value = context_store("load", chat_id, None)
        except Exception as exc:
            raise ActiveContextLoadError("active_context_read_failed") from exc
        rows = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
        return _dedupe_active_contexts(rows, owner_user_id=owner_user_id)
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise ActiveContextLoadError("active_context_store_unavailable")
    try:
        durable = []
        if welfare_case_runtime_enabled():
            try:
                durable = load_open_welfare_case_contexts(chat_id, owner_user_id)
            except Exception:
                # The runtime can be deployed before the separately governed
                # migration is applied. Preserve the existing bounded chronology.
                durable = []
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                owner_clause = ("and h.review_json->'herdmaster_health_loss'->>'owner_user_id' = %s"
                                if owner_user_id else "")
                params = ((EVENT_SOURCE, "oom-health-" + chat_id, owner_user_id)
                          if owner_user_id else (EVENT_SOURCE, "oom-health-" + chat_id))
                cursor.execute(
                    f"""
                    select h.review_json->'herdmaster_health_loss', h.created_at,
                      (select f.review_json->'family_message_lifecycle'->>'telegram_message_id'
                       from public.sam_live_stock_conversation_review_events f
                       where f.event_source = 'oom_sakkie_family_message_lifecycle'
                         and f.review_json->'family_message_lifecycle'->>'card_mission_id' =
                             h.review_json->'herdmaster_health_loss'->>'mission_id'
                         and f.review_json->'family_message_lifecycle'->>'state' in ('delivered','updated')
                       order by f.created_at desc, f.review_event_id desc limit 1)
                    from public.sam_live_stock_conversation_review_events h
                    where h.event_source = %s
                      and h.chatwoot_conversation_id = %s
                      {owner_clause}
                    order by h.created_at desc
                    limit 100
                    """,
                    params,
                )
                rows = cursor.fetchall()
        current = []
        now = datetime.now(timezone.utc)
        for value, created_at, card_message_id in rows:
            if not isinstance(value, dict):
                continue
            if created_at and now - created_at.astimezone(timezone.utc) > CONTEXT_WINDOW:
                continue
            current.append({**value, "card_message_id": str(card_message_id or "")})
        return _dedupe_active_contexts(durable + current, owner_user_id=owner_user_id)
    except Exception as exc:
        raise ActiveContextLoadError("active_context_read_failed") from exc


def _dedupe_active_contexts(rows, *, owner_user_id=""):
    latest = {}
    for row in rows:
        status = str(row.get("status") or "")
        mission = str(row.get("mission_id") or "")
        bound_owner = str(row.get("owner_user_id") or "")
        if owner_user_id and bound_owner and bound_owner != owner_user_id:
            continue
        if status not in {"waiting_for_context", "waiting_for_context_consumption",
                          "waiting_for_input", "preview_ready",
                          "waiting_for_confirmation", "preview_correction_pending",
                          "completed"} or not mission or mission in latest:
            continue
        latest[mission] = row
    superseded = set(); validated_by_source = {mission: [] for mission in latest}
    for source_mission, row in latest.items():
        source_tag = _context_tag(row)
        for binding in row.get("superseded_duplicate_bindings") or []:
            if not isinstance(binding, Mapping):
                continue
            target_mission = str(binding.get("mission_id") or "")
            target = latest.get(target_mission)
            target_provider = str(binding.get("provider_message_id") or "")
            target_tag = str(binding.get("tag_number") or "").casefold()
            if (target and source_tag and target_tag == source_tag
                    and _context_tag(target) == source_tag and target_provider
                    and str(target.get("provider_message_id") or "") == target_provider):
                superseded.add(target_mission)
                validated_by_source[source_mission].append({"mission_id": target_mission,
                    "provider_message_id": target_provider, "tag_number": target_tag})
    return [{**row,
             "superseded_duplicate_missions": sorted(value["mission_id"] for value in validated_by_source[mission]),
             "superseded_duplicate_bindings": validated_by_source[mission]}
            for mission, row in latest.items() if mission not in superseded]


def _context_tag(context):
    preview = context.get("preview") if isinstance(context.get("preview"), Mapping) else {}
    evaluator = preview.get("evaluator") if isinstance(preview.get("evaluator"), Mapping) else {}
    identity = evaluator.get("identity") if isinstance(evaluator.get("identity"), Mapping) else {}
    return str(identity.get("tag_number") or "").casefold()


def _context_missing(context):
    preview = context.get("preview") if isinstance(context.get("preview"), Mapping) else {}
    evaluator = preview.get("evaluator") if isinstance(preview.get("evaluator"), Mapping) else {}
    return {str(value or "") for value in evaluator.get("missing_evidence") or []}


def _resolve_active_context(text, contexts, provider_message_id="", *,
                            reply_to_message_id="", provider_timestamp="", entity_refs=()):
    exact_confirmations = [row for row in contexts
        if text == "CONFIRM " + str(row.get("operation_id") or "")]
    if len(exact_confirmations) == 1:
        return exact_confirmations[0], False, []
    if len(exact_confirmations) > 1:
        return None, exact_confirmations, []
    if reply_to_message_id:
        replies = [row for row in contexts if reply_to_message_id in {
            str(row.get("card_message_id") or ""),
            str(row.get("telegram_message_id") or ""),
        }]
        if len(replies) == 1:
            reply = replies[0]
            if str(reply.get("status") or "").startswith("waiting_for_context"):
                reply_entity = ENTITY_PATTERN.search(text)
                if not reply_entity:
                    return None, replies, []
                tag = reply_entity.group(1).casefold()
                target_ids = {str(binding.get("mission_id") or "")
                              for binding in reply.get("candidate_bindings") or []
                              if isinstance(binding, Mapping)
                              and str(binding.get("tag_number") or "").casefold() == tag}
                targets = [row for row in contexts
                           if str(row.get("mission_id") or "") in target_ids]
                if len(targets) != 1:
                    return None, replies, []
                claimed = str(reply.get("status") or "") == "waiting_for_context_consumption"
                if claimed and not (
                    str(reply.get("resolution_provider_message_id") or "") == provider_message_id
                    and str(reply.get("resolution_provider_timestamp") or "") == provider_timestamp):
                    return None, replies, []
                return {**targets[0], "_pending_clarification": reply,
                        "_pending_claimed": claimed}, False, []
            return reply, False, []
        if len(replies) > 1:
            return None, replies, []
    entity = ENTITY_PATTERN.search(text)
    semantic_tag = _semantic_tag(entity_refs)
    if entity or semantic_tag:
        tag = entity.group(1).casefold() if entity else semantic_tag
        consumed_contexts = {str(value or "") for row in contexts
                             for value in row.get("consumed_context_missions") or []}
        pending_matches = [row for row in contexts
            if str(row.get("status") or "") in {"waiting_for_context", "waiting_for_context_consumption"}
            and str(row.get("mission_id") or "") not in consumed_contexts
            and any(str(binding.get("tag_number") or "").casefold() == tag
                    for binding in row.get("candidate_bindings") or []
                    if isinstance(binding, Mapping))]
        if len(pending_matches) == 1:
            pending = pending_matches[0]
            target_ids = {str(binding.get("mission_id") or "")
                          for binding in pending.get("candidate_bindings") or []
                          if isinstance(binding, Mapping)
                          and str(binding.get("tag_number") or "").casefold() == tag}
            targets = [row for row in contexts if str(row.get("mission_id") or "") in target_ids]
            if len(targets) == 1:
                if str(pending.get("status") or "") == "waiting_for_context_consumption":
                    same_resolution = (
                        str(pending.get("resolution_provider_message_id") or "") == provider_message_id
                        and str(pending.get("resolution_provider_timestamp") or "") == provider_timestamp)
                    if not same_resolution:
                        return None, pending_matches, []
                return {**targets[0], "_pending_clarification": pending,
                        "_pending_claimed": str(pending.get("status") or "") == "waiting_for_context_consumption"}, False, []
        if len(pending_matches) > 1:
            return None, pending_matches, []
        matches = [row for row in contexts if _context_tag(row) == tag
                   and str(row.get("status") or "") in {"waiting_for_input", "preview_ready",
                                                          "waiting_for_confirmation", "preview_correction_pending"}]
        if len(matches) == 1:
            return matches[0], False, []
        prior = [row for row in matches
                 if str(row.get("provider_message_id") or "") != provider_message_id]
        echoes = [row for row in matches
                  if str(row.get("provider_message_id") or "") == provider_message_id]
        if len(prior) == 1 and echoes:
            return prior[0], False, [str(row.get("mission_id") or "") for row in echoes]
        return None, matches if len(matches) > 1 else False, []
    if UNRELATED_OPERATIONAL_PATTERN.search(text) or not FOLLOW_UP_PATTERN.search(text):
        return None, False, []
    candidates = [row for row in contexts
        if str(row.get("status") or "") in {"waiting_for_input", "preview_ready",
                                              "waiting_for_confirmation", "preview_correction_pending"}]
    if re.search(r"\b(?:removed|buried|disposed|cremated|body)\b", text, re.I):
        removal = [row for row in candidates
                   if "physical removal/disposal evidence" in _context_missing(row)]
        if len(removal) == 1:
            return removal[0], False, []
    if len(candidates) == 1:
        return candidates[0], False, []
    waiting = [row for row in candidates if str(row.get("status") or "") == "waiting_for_input"]
    if waiting:
        newest_time = max(str(row.get("provider_timestamp") or "") for row in waiting)
        newest = [row for row in waiting if str(row.get("provider_timestamp") or "") == newest_time]
        if len(newest) == 1 and _chronology_allows(newest[0], provider_message_id, provider_timestamp):
            return newest[0], False, []
    return None, candidates if len(candidates) > 1 else False, []


def _semantic_tag(entity_refs):
    for value in entity_refs or ():
        match = ENTITY_PATTERN.search(str(value))
        if match:
            return match.group(1).casefold()
    return ""


def _chronology_allows(active, provider_message_id, provider_timestamp):
    if (str(active.get("provider_message_id") or "") == provider_message_id
            and str(active.get("provider_timestamp") or "") == provider_timestamp):
        return True
    try:
        incoming = datetime.fromisoformat(provider_timestamp.replace("Z", "+00:00"))
        prior = datetime.fromisoformat(str(active.get("provider_timestamp") or "").replace("Z", "+00:00"))
        return incoming > prior
    except (TypeError, ValueError):
        return False


def _timestamp_strictly_after(candidate, prior):
    try:
        return datetime.fromisoformat(str(candidate).replace("Z", "+00:00")) > datetime.fromisoformat(
            str(prior).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
