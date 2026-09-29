"""Pure durable-history checks for retained mortality presentation.

No manual executor, private plan or caller approval is imported. A recognized
legacy audit is historical evidence; only fresh canonical admission can send.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

from modules.oom_sakkie.herdmaster_source_transaction import require as _require, digest as _digest

BOUND = 128
CASE_HISTORY_BOUND = 4096
RENEWAL_CONSUMED = "retained_claim_renewal_already_consumed"
RENEWAL = "retained_protected_preview_expiry_renewed"
CORRECTION = "protected_presend_timeout_classification_corrected"
EXTENSION = "protected_unsent_confirmation_expiry_extended"
WINDOW = "retained_mortality_presentation_window_started"
TTL_SECONDS = 1800
EMPTY_MARKERS = ("preview_card_message_id", "delivery_attempt_id", "delivery_attempted_at",
    "provider_accepted_at", "delivery_confirmed_at", "delivery_ambiguous_at", "delivery_result",
    "confirmation_provider_message_id", "confirmation_provider_timestamp", "result_payload", "completed_at")


def _sha(value): return hashlib.sha256(str(value).encode()).hexdigest()


def _time(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    _require(result.tzinfo is not None, "history_timestamp_unproven")
    return result.astimezone(timezone.utc)


def _one(rows, name):
    _require(isinstance(rows, list) and len(rows) == 1, name + "_not_unique")
    return rows[0]


def _validate_family_history(family, source_history, claim, card_mission_id):
    """Only complete, source-bound clarification deliveries predating this claim.

    These are historical questions, never permission for a confirmation send.
    Unknown fields (including null protected bindings) and incomplete attempts
    fail closed. The exact detailed rows remain part of the approved preimage.
    """
    _require(isinstance(family, list) and len(family) <= BOUND, "family_history_bound")
    base = {"event_id", "state", "mission_id", "card_mission_id", "owner_user_id", "chat_id",
        "provider_message_id", "provider_timestamp", "inbound_text_sha256", "specialist_identity",
        "task_state", "text_sha256", "semantic_domain", "semantic_intent", "semantic_continuation",
        "read_query", "clarification_question"}
    groups, event_ids = {}, set()
    for item in family:
        _require(isinstance(item, dict) and set(item) == {"review_event_id", "created_at", "record"},
                 "family_record_shape_unproven")
        r = item["record"]
        _require(isinstance(r, dict) and r.get("state") in {"delivery_attempted", "delivered"},
                 "family_effect_unproven")
        extra = {"telegram_message_id", "delivery_provider_timestamp"} if r["state"] == "delivered" else set()
        _require(set(r) == base | extra, "family_protected_or_unknown_fields")
        _require(isinstance(r["event_id"], str) and bool(r["event_id"])
            and r["event_id"] == item["review_event_id"] and r["event_id"] not in event_ids,
            "family_event_identity_unproven")
        _require(r["event_id"] == r["card_mission_id"] + (
            "-DELIVERY-ATTEMPT" if r["state"] == "delivery_attempted" else "-DELIVERED"),
            "family_event_identity_unproven")
        event_ids.add(r["event_id"])
        _require(r["owner_user_id"] == claim["owner_user_id"] and r["chat_id"] == claim["private_chat_id"]
            and r["mission_id"] == r["card_mission_id"] == source_history[0]["record"]["mission_id"]
            and r["card_mission_id"] not in {claim["mission_id"], card_mission_id}
            and r["specialist_identity"] == "HERDMASTER" and r["task_state"] == "waiting_for_input"
            and r["semantic_domain"] == "herd_health" and r["semantic_intent"] == "mortality_report"
            and r["semantic_continuation"] is False and r["read_query"] == {}, "family_identity_unproven")
        matches = [s for s in source_history if s["record"].get("status") == "waiting_for_input"
            and s["record"].get("provider_message_id") == r["provider_message_id"]]
        source_item = _one(matches, "family_clarification_source")
        source = source_item["record"]
        preview = source.get("preview") or {}
        _require(source.get("owner_user_id") == r["owner_user_id"] and source.get("chat_id") == r["chat_id"]
            and source.get("mission_id") == r["mission_id"] and source.get("event_phase") == "preview_generated"
            and not source.get("operation_id") and preview.get("status") == "event_date_required"
            and preview.get("success") is False and type(preview.get("question_count")) is int
            and preview["question_count"] == 1 and not preview.get("confirmation_ready")
            and not preview.get("confirmation_binding") and not preview.get("confirmation_required")
            and all(preview.get(k) is False for k in ("consumes_confirmation", "protected_actions_performed",
                "writes_farm_data", "routes_messages", "sends_telegram"))
            and preview.get("zero_io") is True
            and (preview.get("evaluator") or {}).get("identity") == claim["preview_payload"]["identity"],
            "family_clarification_source_unproven")
        question = preview.get("owner_text")
        _require(isinstance(question, str) and bool(question.strip()) and len(question) <= 240
            and question == source.get("owner_text") == r["clarification_question"]
            and _sha(question) == r["text_sha256"]
            and _sha(" ".join(str(source.get("owner_text_verbatim") or "").split())) == r["inbound_text_sha256"],
            "family_clarification_text_unproven")
        _require(_time(r["provider_timestamp"]) == _time(source["provider_timestamp"])
            <= _time(source_item["created_at"]) <= _time(item["created_at"]) < _time(claim["created_at"]),
            "family_clarification_chronology_unproven")
        groups.setdefault((r["card_mission_id"], r["provider_message_id"], r["text_sha256"]), []).append(item)
    for group in groups.values():
        _require(len(group) == 2 and {r["record"]["state"] for r in group} == {"delivery_attempted", "delivered"},
                 "family_clarification_delivery_incomplete")
        attempted = next(r for r in group if r["record"]["state"] == "delivery_attempted")
        delivered = next(r for r in group if r["record"]["state"] == "delivered")
        stable = base - {"event_id", "state"}
        _require(all(attempted["record"][k] == delivered["record"][k] for k in stable)
            and isinstance(delivered["record"]["telegram_message_id"], str)
            and bool(delivered["record"]["telegram_message_id"].strip())
            and _time(attempted["created_at"]) <= _time(delivered["record"]["delivery_provider_timestamp"])
            <= _time(delivered["created_at"]), "family_clarification_delivery_unproven")


def _is_consumed_renewal_guard(event, claim):
    """Production guard returns before preview persistence or provider delivery."""
    p = event["event_payload"]
    required = {"case_id", "cycle_id", "event_type", "failure_kind", "generation", "occurred_at",
        "outcome_status", "provider_ambiguity_contained"}
    timings = p.get("processing_timings_ms")
    telemetry_valid = (p.get("deadline_phase", "") == "" and ("processing_timings_ms" not in p or
        (isinstance(timings, dict) and set(timings) == {"dispatch_wait", "refresh_and_delivery"}
         and all(type(v) is int and 0 <= v <= 3_600_000 for v in timings.values()))))
    return (required <= set(p) <= required | {"deadline_phase", "processing_timings_ms"} and telemetry_valid
        and event["event_type"] == p["event_type"] == "exception"
        and p["failure_kind"] == p["outcome_status"] == RENEWAL_CONSUMED
        and p["provider_ambiguity_contained"] is False
        and p["case_id"] == event["case_id"] and p["generation"] == event["generation"]
        and isinstance(p["cycle_id"], str) and bool(p["cycle_id"].strip())
        and _time(p["occurred_at"]) == _time(event["occurred_at"]) >= _time(claim["expires_at"]))


def _hex(value, length=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None


def validate_audit_chain(claim, case, source, audits, *, observed_at):
    """Validate durable causes, including the archived pre-send false attempt.

    Source pins and authority references describe completed historical changes;
    they do not authorize this presentation. All current effects are checked
    separately and the complete material preview is rebuilt at admission.
    """
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_report_binding
    claim_hash = _sha(claim["callback_token"])
    _require(len(audits) <= BOUND, "claim_audit_history_overflow")
    _require(len({a["event_id"] for a in audits}) == len(audits), "claim_audit_duplicate")
    by_type = {}
    for row in audits:
        _require(_time(row["occurred_at"]) <= observed_at, "claim_audit_future")
        kind = row["event_type"]
        _require(kind in {RENEWAL, CORRECTION, EXTENSION}, "claim_window_or_unknown_audit_exists")
        _require(kind not in by_type, "claim_audit_conflict")
        _require(row["aggregate_type"] == "protected_action_claim" and row["aggregate_id"] == claim_hash,
            "claim_audit_aggregate_mismatch")
        by_type[kind] = row
    _require(EXTENSION not in by_type or CORRECTION in by_type, "extension_correction_missing")
    _require(CORRECTION not in by_type or RENEWAL in by_type, "correction_renewal_missing")
    expected_expiry = None
    corrected = by_type.get(CORRECTION)
    for kind in (RENEWAL, CORRECTION, EXTENSION):
        if kind not in by_type:
            continue
        row = by_type[kind]
        payload = row["payload_json"]
        occurred = _time(row["occurred_at"])
        _require(payload.get("claim_hash") == claim_hash and payload.get("preview_digest") == claim["preview_digest"]
            and payload.get("one_time_only") is True and type(payload.get("provider_attempts")) is int
            and payload["provider_attempts"] == 0 and type(payload.get("farm_writes")) is int
            and payload["farm_writes"] == 0, "historical_audit_binding_invalid")
        new_expiry = _time(payload["new_expires_at"])
        start = new_expiry - timedelta(seconds=TTL_SECONDS)
        # The ordinary renewal reads its audit clock before the later UPDATE
        # clock. Its archived attempt must follow that actual renewal start.
        _require((occurred <= start <= observed_at) if kind == RENEWAL else start == occurred,
            "historical_audit_ttl_invalid")
        if kind == RENEWAL:
            old_expiry = _time(payload["old_expires_at"])
            _require(row["event_id"] == "OOM-RETAINED-RENEWAL-" + claim_hash[:32].upper()
                and row["idempotency_key"] == "retained-preview-renewal:" + claim_hash + ":" + old_expiry.isoformat()
                and payload.get("contract_version") == "retained_preview_renewal_v1"
                and payload.get("mission_id") == claim["mission_id"]
                and payload.get("evidence_generation") == claim["evidence_generation"]
                and payload.get("source_binding") == retained_report_binding([source])
                and payload.get("old_status") in {"active", "expired"}
                and payload.get("old_delivery_state") in {None, "claim_created", "expired"}
                and payload.get("new_status") == "active" and payload.get("new_delivery_state") == "claim_created"
                and _time(claim["created_at"]) <= old_expiry <= occurred, "renewal_history_unproven")
        else:
            _require(payload.get("case_id") == case["case_id"] and payload.get("generation") == case["generation"]
                and payload.get("evidence_digest") == case["evidence_digest"]
                and _hex(payload.get("plan_sha256")) and _hex(payload.get("preimage_sha256"))
                and all(_hex(payload.get(key), 40) for key in ("prevention_revision", "prevention_tree", "deployed_revision"))
                and isinstance(payload.get("authority_reference"), str) and payload["authority_reference"].strip()
                and payload.get("scheduler_triggers") == 0 and row["authority_tier"] == "owner_approved"
                and row["source_record_id"] == case["case_id"]
                and row["provenance_json"] == {"source_ref": "sha256:" + payload["preimage_sha256"]},
                "legacy_audit_provenance_unproven")
            if kind == CORRECTION:
                archived = payload.get("archived_claim_markers") or {}
                required = {"delivery_attempt_id", "delivery_attempted_at", "delivery_ambiguous_at", "delivery_result",
                    "expires_at", "status", "delivery_state"}
                old_result = {"success": False, "status": "family_message_cycle_deadline_deferred",
                    "telegram_message_id": None, "telegram_sends": 0, "telegram_edits": 0}
                renewal = by_type[RENEWAL]
                renewal_projection = {key: renewal[key] for key in
                    ("event_id", "event_type", "idempotency_key", "payload_json", "occurred_at")}
                _require(row["event_id"] == "OOM-PRESEND-CORRECTION-" + claim_hash[:32].upper()
                    and row["idempotency_key"] == "oom-presend-timeout-correction:" + claim_hash
                    and row["source_system"] == "manual_presend_timeout_correction"
                    and payload.get("contract_version") == "oom_presend_timeout_correction.v1"
                    and isinstance(payload.get("original_renewal"), dict)
                    and set(payload["original_renewal"]) == set(renewal_projection)
                    and all(payload["original_renewal"][key] == renewal_projection[key]
                        for key in renewal_projection if key != "occurred_at")
                    and _time(payload["original_renewal"]["occurred_at"]) == _time(renewal["occurred_at"])
                    and set(archived) == required and archived["status"] in {"active", "expired"}
                    and archived["delivery_state"] == "delivery_ambiguous"
                    and archived["delivery_result"] == old_result
                    and archived["delivery_result"]["success"] is False
                    and type(archived["delivery_result"]["telegram_sends"]) is int
                    and type(archived["delivery_result"]["telegram_edits"]) is int
                    and archived["delivery_attempt_id"] == _sha("oom_protected_delivery.v1|" +
                        claim["callback_token"] + "|" + claim["preview_digest"])
                    and _time(renewal["payload_json"]["new_expires_at"]) - timedelta(seconds=TTL_SECONDS)
                    <= _time(archived["delivery_attempted_at"])
                    <= _time(archived["delivery_ambiguous_at"]) <= expected_expiry < occurred
                    and _time(archived["expires_at"]) == expected_expiry,
                    "legacy_presend_correction_unproven")
            else:
                _require(row["event_id"] == "OOM-UNSENT-EXTENSION-" + claim_hash[:32].upper()
                    and row["idempotency_key"] == "oom-unsent-confirmation-extension:" + claim_hash
                    and row["source_system"] == "manual_unsent_confirmation_extension"
                    and row["causation_id"] == corrected["event_id"]
                    and payload.get("contract_version") == "oom_unsent_confirmation_extension.v1"
                    and payload.get("original_correction_event_id") == corrected["event_id"]
                    and payload.get("original_correction_plan_sha256") == corrected["payload_json"]["plan_sha256"]
                    and payload.get("owner_user_id") == claim["owner_user_id"]
                    and payload.get("original_renewal_consumed") is True
                    and payload.get("metadata_writes") == 2 and payload.get("ttl_seconds") == TTL_SECONDS
                    and _time(payload["old_expires_at"]) == expected_expiry < occurred,
                    "legacy_extension_chain_unproven")
        expected_expiry = new_expiry
    if expected_expiry is not None:
        _require(_time(claim["expires_at"]) == expected_expiry, "claim_expiry_chain_changed")
    return corrected, by_type


def validate_case_history(events, claim, case, audits, cycle, *, observed_at):
    corrected, by_type = audits
    _require(0 < len(events) <= CASE_HISTORY_BOUND, "case_history_overflow_or_missing")
    _require(len({event["event_id"] for event in events}) == len(events), "case_history_duplicate")
    _require(sum(event["event_type"] == "created" for event in events) == 1, "case_creation_history_unproven")
    correction_count = containment_count = 0
    for event in events:
        payload = event["event_payload"]
        _require(event["case_id"] == case["case_id"] and event["generation"] == case["generation"]
            and payload.get("case_id") == case["case_id"] and payload.get("generation") == case["generation"]
            and payload.get("event_type") == event["event_type"]
            and _time(payload["occurred_at"]) == _time(event["occurred_at"]), "case_history_binding_changed")
        _require(_time(event["occurred_at"]) <= observed_at, "case_history_future")
        # The archived false ambiguity marker is the one recognized exception;
        # a send/card/confirmation marker is never overridden by that label.
        _require(not any(payload.get(key) for key in ("delivery_confirmed", "provider_confirmed",
            "confirmed_generation_preserved", "provider_card_message_id", "delivery_attempt_id",
            "telegram_sends", "telegram_edits", "writes_farm_data")), "case_effect_history_exists")
        outcome = payload.get("outcome_status", "")
        if corrected and event["event_id"] == corrected["event_id"] + "-REASSESS":
            _require(event["event_type"] == "reassessment_scheduled"
                and payload.get("correction_audit_event_id") == corrected["event_id"]
                and payload.get("plan_sha256") == corrected["payload_json"]["plan_sha256"]
                and not payload.get("provider_ambiguity_contained")
                and payload.get("failure_kind", "") == ""
                and outcome == "proven_presend_timeout_classification_corrected"
                and _time(event["occurred_at"]) == _time(corrected["occurred_at"]), "case_correction_history_invalid")
            correction_count += 1
            continue
        if corrected and event["event_type"] == "contained":
            archived = corrected["payload_json"]["archived_claim_markers"]
            _require(outcome == "protected_delivery_ambiguous" and payload.get("provider_ambiguity_contained") is True
                and payload.get("failure_kind", "") in {"", outcome}
                and payload.get("cycle_id") == corrected["causation_id"] == (cycle or {}).get("cycle_id")
                and _hex((cycle or {}).get("source_revision"), 40)
                and _time(cycle["started_at"]) <= _time(archived["delivery_attempted_at"])
                <= _time(event["occurred_at"]) < _time(corrected["occurred_at"]), "legacy_containment_cycle_unproven")
            containment_count += 1
            continue
        _require(not any(payload.get(key) for key in ("provider_ambiguity_contained", "delivery_confirmed",
            "provider_confirmed", "confirmed_generation_preserved", "provider_card_message_id", "delivery_attempt_id",
            "telegram_sends", "telegram_edits", "writes_farm_data")), "case_effect_history_exists")
        if outcome == "retained_mortality_presend_statement_deferred":
            _require(_is_presend_statement_guard(event), "presend_statement_guard_unproven")
            continue
        if outcome == RENEWAL_CONSUMED:
            event_time = _time(event["occurred_at"])
            previous = [a for a in by_type.values() if _time(a["occurred_at"]) <= event_time]
            _require(bool(previous), "renewal_guard_without_history")
            effective = max(previous, key=lambda a: _time(a["occurred_at"]))["payload_json"]["new_expires_at"]
            _require(_is_consumed_renewal_guard(event, {**claim, "expires_at": effective}), "renewal_guard_unproven")
            continue
        if outcome == "retained_claim_current_preview_mismatch":
            # Historical clock-hash mismatch returned before persistence/delivery.
            # Its label alone is insufficient: an exact correction plus complete
            # source/family/claim evidence and fresh material are required outside.
            _require(corrected is not None and event["event_type"] == "exception"
                and _time(event["occurred_at"]) < _time(corrected["occurred_at"])
                and payload.get("failure_kind") in {"", outcome}, "legacy_preview_guard_unproven")
            continue
        allowed = {"", "manager_cycle_deadline_deferred", "family_message_cycle_deadline_deferred",
            "retained_mortality_prepared_not_presented"}
        _require(event["event_type"] in {"created", "claimed", "delegated", "heartbeat", "exception",
            "delivery_suppressed", "reassessment_scheduled"} and outcome in allowed
            and payload.get("failure_kind", "") in {"", outcome}
            and (event["event_type"] != "exception" or outcome in allowed - {"", "retained_mortality_prepared_not_presented"})
            and (event["event_type"] != "delivery_suppressed" or bool(outcome)), "unsafe_case_history")
    _require((correction_count, containment_count) == ((1, 1) if corrected else (0, 0)),
        "legacy_correction_case_history_missing")


def _is_presend_statement_guard(event):
    """Known body SQL timeout; wrapper emits this only after explicit successful rollback."""
    p = event["event_payload"]
    required = {"case_id", "cycle_id", "event_type", "failure_kind", "generation", "occurred_at",
        "outcome_status", "provider_ambiguity_contained"}
    timings = p.get("processing_timings_ms")
    telemetry_valid = (p.get("deadline_phase", "") == "" and ("processing_timings_ms" not in p or
        (isinstance(timings, dict) and set(timings) == {"dispatch_wait", "refresh_and_delivery"}
         and all(type(v) is int and 0 <= v <= 3_600_000 for v in timings.values()))))
    return (required <= set(p) <= required | {"deadline_phase", "processing_timings_ms"} and telemetry_valid
        and event["event_type"] == p["event_type"] == "exception"
        and p["failure_kind"] == p["outcome_status"] == "retained_mortality_presend_statement_deferred"
        and p["provider_ambiguity_contained"] is False
        and p["case_id"] == event["case_id"] and p["generation"] == event["generation"]
        and isinstance(p["cycle_id"], str) and bool(p["cycle_id"].strip())
        and _time(p["occurred_at"]) == _time(event["occurred_at"]))
