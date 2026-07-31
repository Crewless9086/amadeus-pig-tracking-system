"""Small adapter from current SAM evidence to the existing owner Telegram/card rail."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping

from modules.oom_sakkie.owner_attention_queue import (
    build_owner_attention_queue,
    build_resolved_card_edit,
    consume_decision_card,
    reassess_decision_card,
)
from modules.oom_sakkie.specialist_owner_decisions import (
    render_beacon_card,
    specialist_choice,
    specialist_decision_current,
    validate_specialist_binding,
)
from modules.sales.sam_live_stock_launch_control import (
    _deliver_sam_live_stock_owner_card,
    _telegram_edit_message,
    build_sam_live_stock_owner_card_event,
    build_sam_live_stock_review_event,
    record_sam_live_stock_review_event,
)
from modules.sales.sam_live_stock_runtime import load_chatwoot_conversation_history
from services.database_service import DATABASE_URL_ENV


ENABLED_ENV = "OOM_SAKKIE_OWNER_ATTENTION_QUEUE_ENABLED"
OWNER_USER_ID_ENV = "OOM_SAKKIE_OWNER_ATTENTION_OWNER_USER_ID"
SUMMARY_IDENTITY = "OOMAQ-SALES-STATUS"
EVENT_SOURCE = "oom_sakkie_owner_attention_queue"
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


def project_sam_dispositions(dispositions: Iterable[Mapping[str, Any]], *, observed_at: datetime) -> list[dict[str, Any]]:
    """Project current SAM results without customer content or invented decisions."""
    now = _aware(observed_at)
    results = []
    for row in dispositions or ():
        if not isinstance(row, Mapping) or row.get("queue_relevant") is not True:
            continue
        identity = {key: _opaque(row.get(key)) for key in ("account_id", "inbox_id", "contact_id", "conversation_id", "inbound_message_id")}
        if not all(_IDENTITY.fullmatch(value) for value in identity.values()):
            continue
        status = _status(row)
        decision = row.get("owner_attention_decision") if isinstance(row.get("owner_attention_decision"), Mapping) else None
        if status == "owner_decision" and decision is None:
            status = "qualification_progress"
        latest_at = _timestamp(row.get("latest_inbound_at"))
        sequence = _sequence(identity["inbound_message_id"])
        if latest_at is None or sequence is None or latest_at > now:
            continue
        evidence = {"identity": identity, "status": status, "disposition": _opaque(row.get("disposition")),
                    "provider_state": _opaque(row.get("provider_state")), "owner_decision_required": row.get("owner_decision_required") is True}
        item = {"status": status, "account_id": identity["account_id"], "inbox_id": identity["inbox_id"],
                "contact_id": identity["contact_id"], "conversation_id": identity["conversation_id"],
                "latest_inbound_id": identity["inbound_message_id"], "observed_at": now.isoformat(),
                "latest_inbound_at": latest_at.isoformat(), "chronology_sequence": sequence}
        if decision is not None:
            allowed = {"requested_authority", "expires_at", "choices", "source_contract"}
            reserved = set(decision) - allowed
            if reserved or decision.get("source_contract") != "sam_delivery_owner_exception_v1":
                item["status"] = "qualification_progress"
            else:
                item.update({key: decision[key] for key in ("requested_authority", "expires_at", "choices")})
                item["evidence_packet_hash"] = _digest(evidence | {"decision": {key: decision.get(key) for key in sorted(allowed)}})
        results.append(item)
    return results


def operate_owner_attention_queue(dispositions: Iterable[Mapping[str, Any]], *, sam_state: Mapping[str, Any] | None = None,
                                  environ=None, now: datetime | None = None, active_card_loader=None,
                                  evidence_recorder=None, telegram_sender=None, telegram_editor=None,
                                  incident_loader=None, decision_loader=None) -> dict[str, Any]:
    """Create/edit only the consolidated summary and warranted cards/alerts."""
    source = environ if environ is not None else os.environ
    clock = _aware(now or datetime.now(timezone.utc))
    if not _truthy(source.get(ENABLED_ENV)):
        return _result("owner_attention_queue_disabled")
    snapshot = clock - timedelta(microseconds=1)
    observations = project_sam_dispositions(dispositions, observed_at=snapshot)
    start = snapshot.replace(hour=0, minute=0, second=0, microsecond=0)
    queue = build_owner_attention_queue(observations, period_start=start.isoformat(), period_end=clock.isoformat(),
                                        now=clock, sam_state=sam_state or {"state": "healthy"})
    deliveries = []
    deliveries.append(_deliver(queue["summary"], kind="summary", identity=SUMMARY_IDENTITY, source=source,
                               active_card_loader=active_card_loader, evidence_recorder=evidence_recorder,
                               telegram_sender=telegram_sender, telegram_editor=telegram_editor))
    for card in queue["decision_cards"]:
        deliveries.append(_deliver(card, kind="decision", identity=f"OOMAQ-{card['decision_id']}", source=source,
                                   active_card_loader=active_card_loader, evidence_recorder=evidence_recorder,
                                   telegram_sender=telegram_sender, telegram_editor=telegram_editor))
    current_decision_ids = {card["decision_id"] for card in queue["decision_cards"]}
    decision_expiries = _expire_prior_decisions(current_decision_ids, clock=clock, source=source,
        decision_loader=decision_loader, evidence_recorder=evidence_recorder, telegram_editor=telegram_editor)
    for alert in queue["system_alerts"]:
        deliveries.append(_deliver(alert, kind="system_alert", identity=f"OOMAQ-ALERT-{alert['alert_id'][:32]}", source=source,
                                   active_card_loader=active_card_loader, evidence_recorder=evidence_recorder,
                                   telegram_sender=telegram_sender, telegram_editor=telegram_editor))
    current_alert_ids = {alert["alert_id"] for alert in queue["system_alerts"]}
    incident_resolutions = _resolve_prior_incidents(current_alert_ids, source=source,
        incident_loader=incident_loader, evidence_recorder=evidence_recorder, telegram_editor=telegram_editor)
    return {"success": all(item.get("success") for item in deliveries + decision_expiries + incident_resolutions), "status": "owner_attention_queue_operated",
            "queue": queue, "deliveries": deliveries, "decision_expiries": decision_expiries,
            "incident_resolutions": incident_resolutions,
            "individual_ordinary_notifications": 0,
            "calls_telegram": any(item.get("calls_telegram") for item in deliveries + decision_expiries + incident_resolutions),
            "sends_customer_message": False, "writes_farm_data": False}


def operate_specialist_owner_decision(binding: Mapping[str, Any], *, environ=None, now: datetime | None = None,
                                      chronology_loader=None, specialist_card_loader=None, active_card_loader=None,
                                      evidence_recorder=None, telegram_sender=None, telegram_editor=None) -> dict[str, Any]:
    """Deliver one closed specialist-owned decision through the existing card rail."""
    source = environ if environ is not None else os.environ
    if not _truthy(source.get(ENABLED_ENV)):
        return _result("owner_attention_queue_disabled")
    try:
        valid = validate_specialist_binding(binding)
        if valid["specialist_identity"] != "BEACON":
            return _result("specialist_owner_decision_unsupported")
        loader = specialist_card_loader or _load_attention_card
        prior = loader(valid["decision_token"], source.get(DATABASE_URL_ENV))
        current = (chronology_loader or _current_specialist_chronology)(valid, source)
        if not specialist_decision_current(valid, current, now=now or datetime.now(timezone.utc)):
            card = prior.get("card") if prior.get("success") and isinstance(prior.get("card"), Mapping) else {}
            if card.get("telegram_message_id"):
                return _expire_specialist_card(card, valid, source=source, now=now,
                    evidence_recorder=evidence_recorder, telegram_editor=telegram_editor)
            return _result("specialist_owner_decision_stale")
        if prior.get("success") and (prior.get("card") or {}).get("telegram_message_id"):
            return {**_result("specialist_owner_decision_duplicate_withheld", True),
                    "decision_identity": valid["deterministic_identity"], "duplicate_cards_created": 0}
        text, markup = render_beacon_card(binding)
        item = {"decision_id": valid["decision_token"], "external_decision_identity": valid["deterministic_identity"],
                "specialist_binding": valid, "card_digest": valid["binding_digest"],
                "expires_at": valid["expires_at"], "choices": valid["allowed_owner_choices"]}
        identity = "OOMAQ-" + valid["deterministic_identity"]
        event = build_sam_live_stock_review_event({"conversation_id": identity}, {}, {},
            {"score": 0, "safe_to_send": False, "recommended_action": "specialist_owner_decision"}, event_source=EVENT_SOURCE)
        event["review_event_id"] = "OOMAQ-SPECIALIST-" + _digest(item)[:24]
        event["chatwoot_conversation_id"] = identity
        owner_id = _opaque(source.get(OWNER_USER_ID_ENV))
        if not owner_id:
            return _result("owner_attention_bound_owner_required")
        context = {"kind": "decision", "item": item,
                   "expected_owner_identity_hash": _digest({"telegram_owner_id": owner_id})}
        recorder = evidence_recorder or record_sam_live_stock_review_event

        def bound_recorder(evidence):
            evidence = dict(evidence)
            review = dict(evidence.get("review_json") or {})
            review["owner_attention"] = context
            evidence["review_json"] = review
            evidence["customer_message_excerpt"] = evidence["sam_reply_excerpt"] = ""
            return recorder(evidence)

        delivered, status = _deliver_sam_live_stock_owner_card(event, {"text": text, "reply_markup": markup}, source,
            telegram_sender, telegram_editor, active_card_loader, bound_recorder, "oom_sakkie_specialist_decision_created")
        return {**delivered, "http_status": status, "decision_identity": valid["deterministic_identity"],
                "duplicate_cards_created": 0, "sends_customer_message": False, "writes_farm_data": False,
                "publishes": False}
    except ValueError:
        return _result("specialist_owner_decision_invalid")
    except Exception:
        return _result("specialist_owner_decision_contained")


def repair_specialist_owner_attention_resolution(card, receipt, *, environ=None,
                                                 evidence_loader=None, evidence_recorder=None, telegram_editor=None):
    """Idempotently repair only a specialist card's post-receipt presentation."""
    source = environ if environ is not None else os.environ
    try:
        binding = validate_specialist_binding(card["specialist_binding"])
        if card.get("decision_id") != binding["decision_token"] or card.get("card_digest") != binding["binding_digest"]:
            return _result("specialist_owner_resolution_receipt_invalid")
        loaded = (evidence_loader or _load_attention_card)(binding["decision_token"], source.get(DATABASE_URL_ENV))
        if not loaded.get("success") or not isinstance(loaded.get("card"), Mapping) or not isinstance(loaded.get("receipt"), Mapping):
            return _result("specialist_owner_resolution_evidence_unavailable")
        trusted_card, trusted_receipt = loaded["card"], loaded["receipt"]
        if any(str(card.get(key) or "") != str(trusted_card.get(key) or "") for key in
               ("decision_id", "card_digest", "telegram_chat_id", "telegram_message_id")):
            return _result("specialist_owner_resolution_card_mismatch")
        required_receipt = ("status", "receipt_id", "decision_id", "deterministic_identity", "card_digest",
                            "choice_id", "replay_key", "actor_identity_hash")
        if any(str(receipt.get(key) or "") != str(trusted_receipt.get(key) or "") for key in required_receipt):
            return _result("specialist_owner_resolution_receipt_mismatch")
        replay_key = _digest({"card_digest": binding["binding_digest"], "choice": receipt.get("choice_id"),
                              "actor_identity_hash": receipt.get("actor_identity_hash")})
        if (receipt.get("status") != "consumed" or receipt.get("decision_id") != binding["decision_token"]
                or receipt.get("card_digest") != binding["binding_digest"]
                or receipt.get("deterministic_identity") != binding["deterministic_identity"]
                or receipt.get("replay_key") != replay_key
                or receipt.get("receipt_id") != "OOMAQ-RECEIPT-" + replay_key[:24]
                or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("actor_identity_hash") or ""))):
            return _result("specialist_owner_resolution_receipt_invalid")
        authority = specialist_choice(binding, receipt["choice_id"])
        (telegram_editor or _telegram_edit_message)(_token(source), trusted_card["telegram_chat_id"], trusted_card["telegram_message_id"],
            "Oom Sakkie — Decision recorded\n\n"
            f"Outcome: {authority['outcome_code'].replace('_', ' ')}\n"
            f"Next follow-up: {authority['next_action_owner']}", {"inline_keyboard": []})
        recorder = evidence_recorder or record_sam_live_stock_review_event
        recorded, status = recorder(_specialist_resolution_event(trusted_card, receipt, "resolved"))
        return {**_result("specialist_owner_resolution_repaired", status < 400 and recorded.get("success") is True),
                "calls_telegram": True, "follow_up_owner": authority["next_action_owner"], "publishes": False}
    except Exception:
        return _result("specialist_owner_resolution_repair_contained")


def process_owner_attention_callback(payload: Mapping[str, Any], *, environ=None, evidence_loader=None,
                                     current_binding_loader=None, evidence_recorder=None, telegram_editor=None,
                                     now: datetime | None = None) -> tuple[dict[str, Any], int]:
    try:
        return _process_owner_attention_callback(payload, environ=environ, evidence_loader=evidence_loader,
            current_binding_loader=current_binding_loader, evidence_recorder=evidence_recorder,
            telegram_editor=telegram_editor, now=now)
    except ValueError:
        return _result("owner_attention_callback_evidence_invalid"), 409
    except Exception:
        return _result("owner_attention_callback_contained"), 503


def repair_owner_attention_resolution(card, receipt, *, expected_owner_identity_hash, environ=None,
                                      evidence_recorder=None, telegram_editor=None):
    """Idempotently repair only the Telegram presentation of a consumed card."""
    source = environ if environ is not None else os.environ
    try:
        edit = build_resolved_card_edit(card, receipt, expected_card_digest=card["card_digest"],
            expected_owner_identity_hash=expected_owner_identity_hash, expected_replay_key=receipt["replay_key"])
        outcome = edit["edit_intent"]
        (telegram_editor or _telegram_edit_message)(_token(source), card["telegram_chat_id"], card["telegram_message_id"],
            _resolved_text(outcome), {"inline_keyboard": []})
        recorder = evidence_recorder or record_sam_live_stock_review_event
        recorded, status = recorder(_resolution_event(card, receipt, "resolved"))
        return {"success": status < 400 and recorded.get("success") is True, "status": "owner_attention_resolution_repaired",
                "calls_telegram": True, "sends_customer_message": False}
    except Exception:
        return _result("owner_attention_resolution_repair_contained")


def _process_owner_attention_callback(payload: Mapping[str, Any], *, environ=None, evidence_loader=None,
                                      current_binding_loader=None, evidence_recorder=None, telegram_editor=None,
                                      now: datetime | None = None) -> tuple[dict[str, Any], int]:
    """Consume one authenticated owner choice through the existing evidence rail."""
    source = environ if environ is not None else os.environ
    callback = str(payload.get("callback_data") or "")
    parts = callback.split(":")
    if len(parts) != 3 or parts[0] != "sam_live_owner_decision":
        return _result("owner_attention_callback_invalid"), 400
    decision_id, choice = parts[1], parts[2]
    loader = evidence_loader or _load_attention_card
    loaded = loader(decision_id, source.get(DATABASE_URL_ENV))
    if not loaded.get("success"):
        return {**_result(loaded.get("status") or "owner_attention_card_unavailable"), "evidence": loaded}, 409
    card = loaded["card"]
    if (str(payload.get("telegram_message_id") or "") != str(card.get("telegram_message_id") or "")
            or str(payload.get("telegram_chat_id") or "") != str(card.get("telegram_chat_id") or "")):
        return _result("owner_attention_telegram_identity_mismatch"), 409
    actor_id = _opaque(payload.get("telegram_user_id"))
    owner_ids = {_opaque(value) for value in str(source.get("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS") or "").split(",") if _opaque(value)}
    expected_owner_id = _opaque(source.get(OWNER_USER_ID_ENV))
    if not actor_id or actor_id not in owner_ids or actor_id != expected_owner_id:
        return _result("owner_attention_owner_identity_denied"), 403
    actor_hash = _digest({"telegram_owner_id": actor_id})
    if loaded.get("expected_owner_identity_hash") != actor_hash:
        return _result("owner_attention_card_owner_binding_mismatch"), 409
    if isinstance(card.get("specialist_binding"), Mapping):
        return _process_specialist_owner_callback(card, choice, actor_hash, loaded, source=source,
            current_binding_loader=current_binding_loader, evidence_recorder=evidence_recorder,
            telegram_editor=telegram_editor, now=now)
    binding_loader = current_binding_loader or (lambda binding: _current_binding(binding, source))
    try:
        current = binding_loader(card["binding"])
    except Exception:
        return _result("owner_attention_authoritative_chronology_unavailable"), 503
    receipt = loaded.get("receipt") if isinstance(loaded.get("receipt"), Mapping) else None
    prepared = consume_decision_card(card, choice=choice, actor_identity_hash=actor_hash,
        expected_owner_identity_hash=actor_hash, expected_card_digest=card["card_digest"], current_binding=current,
        existing_consumption_receipt=receipt, now=now or datetime.now(timezone.utc))
    if prepared["status"] == "decision_replay_noop":
        return {**_result("owner_attention_callback_replay_noop", True), "decision": prepared}, 200
    if prepared["status"] != "decision_consumption_intent_prepared":
        edit = prepared.get("edit_intent")
        if edit:
            (telegram_editor or _telegram_edit_message)(_token(source), card["telegram_chat_id"], edit["telegram_message_id"],
                                                        _expired_text(edit), {"inline_keyboard": []})
        return {**_result(prepared["status"]), "decision": prepared, "calls_telegram": bool(edit)}, 409
    intent = prepared["atomic_consumption_intent"]
    receipt = {"status": "consumed", "receipt_id": "OOMAQ-RECEIPT-" + intent["replay_key"][:24],
               "decision_id": decision_id, "card_digest": card["card_digest"], "choice_id": choice,
               "replay_key": intent["replay_key"], "actor_identity_hash": actor_hash}
    recorder = evidence_recorder or record_sam_live_stock_review_event
    recorded, record_status = recorder(_receipt_event(card, receipt))
    if record_status >= 400 or not recorded.get("success"):
        return {**_result("owner_attention_consumption_record_failed"), "evidence": recorded}, 503
    if recorded.get("created") is False:
        return {**_result("owner_attention_callback_replay_noop", True), "writes_performed": 0, "calls_telegram": False}, 200
    edit = build_resolved_card_edit(card, receipt, expected_card_digest=card["card_digest"],
                                    expected_owner_identity_hash=actor_hash, expected_replay_key=intent["replay_key"])
    outcome = edit["edit_intent"]
    try:
        (telegram_editor or _telegram_edit_message)(_token(source), card["telegram_chat_id"], outcome["telegram_message_id"],
                                                    _resolved_text(outcome), {"inline_keyboard": []})
    except Exception:
        recorder(_resolution_event(card, receipt, "resolution_edit_failed"))
        return {**_result("owner_attention_resolution_edit_failed"), "receipt_id": receipt["receipt_id"],
                "repair_required": True}, 503
    recorder(_resolution_event(card, receipt, "resolved"))
    return {**_result("owner_attention_decision_consumed", True), "decision": edit, "calls_telegram": True,
            "sends_customer_message": False, "follow_up_owner": outcome["next_follow_up_owner"]}, 200


def _process_specialist_owner_callback(card, choice, actor_hash, loaded, *, source, current_binding_loader,
                                       evidence_recorder, telegram_editor, now):
    binding = validate_specialist_binding(card["specialist_binding"])
    if card.get("decision_id") != binding["decision_token"] or card.get("card_digest") != binding["binding_digest"]:
        return _result("specialist_owner_decision_binding_mismatch"), 409
    receipt = loaded.get("receipt") if isinstance(loaded.get("receipt"), Mapping) else None
    replay_key = _digest({"card_digest": binding["binding_digest"], "choice": choice, "actor_identity_hash": actor_hash})
    if receipt is not None:
        if (receipt.get("decision_id") != binding["decision_token"] or receipt.get("replay_key") != replay_key
                or receipt.get("choice_id") != choice or receipt.get("actor_identity_hash") != actor_hash):
            return _result("specialist_owner_decision_receipt_mismatch"), 409
        return {**_result("owner_attention_callback_replay_noop", True), "writes_performed": 0,
                "calls_telegram": False}, 200
    loader = current_binding_loader or (lambda value: _current_specialist_chronology(value, source))
    try:
        current = loader(binding)
    except Exception:
        return _result("owner_attention_authoritative_chronology_unavailable"), 503
    if not specialist_decision_current(binding, current, now=now or datetime.now(timezone.utc)):
        result = _expire_specialist_card(card, binding, source=source, now=now,
            evidence_recorder=evidence_recorder, telegram_editor=telegram_editor)
        return result, int(result.pop("http_status"))
    try:
        callback_authority = specialist_choice(binding, choice)
    except ValueError:
        return _result("owner_attention_callback_evidence_invalid"), 409
    receipt = {"status": "consumed", "receipt_id": "OOMAQ-RECEIPT-" + replay_key[:24],
               "decision_id": binding["decision_token"], "deterministic_identity": binding["deterministic_identity"],
               "card_digest": binding["binding_digest"], "choice_id": choice,
               "replay_key": replay_key, "actor_identity_hash": actor_hash}
    recorder = evidence_recorder or record_sam_live_stock_review_event
    recorded, status = recorder(_specialist_receipt_event(card, receipt, callback_authority))
    if status >= 400 or not recorded.get("success"):
        return _result("owner_attention_consumption_record_failed"), 503
    if recorded.get("created") is False:
        return {**_result("owner_attention_callback_replay_noop", True), "writes_performed": 0,
                "calls_telegram": False}, 200
    try:
        (telegram_editor or _telegram_edit_message)(_token(source), card["telegram_chat_id"], card["telegram_message_id"],
            "Oom Sakkie — Decision recorded\n\n"
            f"Outcome: {callback_authority['outcome_code'].replace('_', ' ')}\n"
            f"Next follow-up: {callback_authority['next_action_owner']}", {"inline_keyboard": []})
    except Exception:
        recorder(_specialist_resolution_event(card, receipt, "resolution_edit_failed"))
        return {**_result("owner_attention_resolution_edit_failed"), "receipt_id": receipt["receipt_id"],
                "repair_required": True}, 503
    recorder(_specialist_resolution_event(card, receipt, "resolved"))
    return {**_result("owner_attention_decision_consumed", True), "calls_telegram": True,
            "follow_up_owner": callback_authority["next_action_owner"],
            "specialist_outcome_callback": callback_authority, "publishes": False}, 200


def _expire_specialist_card(card, binding, *, source, now, evidence_recorder, telegram_editor):
    reason = ("expired" if _aware(now or datetime.now(timezone.utc)) >= datetime.fromisoformat(binding["expires_at"])
              else "chronology_or_evidence_changed")
    try:
        (telegram_editor or _telegram_edit_message)(_token(source), card["telegram_chat_id"], card["telegram_message_id"],
            "Oom Sakkie — Decision expired\n\nSpecialist evidence or chronology changed. No action was applied.",
            {"inline_keyboard": []})
    except Exception:
        return {**_result("specialist_owner_decision_expiry_edit_failed"), "http_status": 503}
    recorder = evidence_recorder or record_sam_live_stock_review_event
    recorded, record_status = recorder(_specialist_expiry_event(card, binding, reason))
    if record_status >= 400 or not recorded.get("success"):
        return {**_result("specialist_owner_decision_expiry_persistence_failed"), "calls_telegram": True,
                "repair_required": True, "http_status": 503}
    return {**_result("decision_expired"), "calls_telegram": True, "http_status": 409}


def _deliver(item, *, kind, identity, source, active_card_loader, evidence_recorder, telegram_sender, telegram_editor):
    event = build_sam_live_stock_review_event({"conversation_id": identity}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "owner_attention_queue"}, event_source=EVENT_SOURCE)
    event["review_event_id"] = "OOMAQ-EVENT-" + _digest({"identity": identity, "item": item})[:24]
    event["chatwoot_conversation_id"] = identity
    event["customer_message_excerpt"] = event["sam_reply_excerpt"] = ""
    text, markup = _presentation(item, kind)
    owner_id = _opaque(source.get(OWNER_USER_ID_ENV)) if kind == "decision" else ""
    if kind == "decision" and not owner_id:
        return {**_result("owner_attention_bound_owner_required"), "http_status": 503, "kind": kind}
    context = {"kind": kind, "item": item,
               "expected_owner_identity_hash": _digest({"telegram_owner_id": owner_id}) if owner_id else ""}
    recorder = evidence_recorder or record_sam_live_stock_review_event

    def bound_recorder(evidence):
        evidence = dict(evidence)
        review = dict(evidence.get("review_json") or {})
        review["owner_attention"] = context
        evidence["review_json"] = review
        evidence["customer_message_excerpt"] = evidence["sam_reply_excerpt"] = ""
        return recorder(evidence)

    result, status = _deliver_sam_live_stock_owner_card(event, {"text": text, "reply_markup": markup}, source,
        telegram_sender, telegram_editor, active_card_loader, bound_recorder, "oom_sakkie_owner_attention_created")
    return {**result, "http_status": status, "kind": kind}


def _presentation(item, kind):
    if kind == "summary":
        counts = item["counts"]
        text = ("Oom Sakkie — Sales status\n\n"
                f"New enquiries: {counts['new_enquiries']}\n"
                f"Automatically answered: {counts['automatically_answered_customers']}\n"
                f"Qualification in progress: {counts['qualification_progress']}\n"
                f"Awaiting customers: {counts['awaiting_customers']}\n"
                f"Owner decisions: {counts['genuine_owner_decisions']}\n"
                f"Systemic failures: {counts['systemic_failures']}\n\n"
                "SAM owns ordinary follow-up. Only protected exceptions need owner action.")
        return text, {"inline_keyboard": []}
    if kind == "system_alert":
        return ("Oom Sakkie — SAM system attention\n\nAffected: " + ", ".join(item["affected_work"]) +
                "\n" + item["manual_coverage_guidance"], {"inline_keyboard": []})
    buttons = [[{"text": choice["label_code"].replace("_", " ").title(),
                 "callback_data": f"sam_live_owner_decision:{item['decision_id']}:{choice['id']}"}] for choice in item["choices"]]
    return ("Oom Sakkie — Protected owner decision\n\n"
            f"Authority: {item['requested_authority'].replace('_', ' ')}\n"
            "This decision is bound to the current customer chronology and expires automatically.",
            {"inline_keyboard": buttons})


def _load_attention_card(decision_id, database_url=None):
    database_url = str(database_url or "").strip()
    if not database_url:
        return {"success": False, "status": "owner_attention_database_unavailable"}
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=5) as connection, connection.cursor() as cursor:
            cursor.execute("""select review_json from public.sam_live_stock_conversation_review_events
                where review_json->'owner_attention'->'item'->>'decision_id'=%s
                order by created_at desc, review_event_id desc limit 1""", (decision_id,))
            row = cursor.fetchone()
            if not row:
                return {"success": False, "status": "owner_attention_card_not_found"}
            review = row[0] if isinstance(row[0], Mapping) else json.loads(row[0])
            card = dict(review["owner_attention"]["item"])
            owner_card = review.get("owner_card") if isinstance(review.get("owner_card"), Mapping) else {}
            card["telegram_message_id"] = str(owner_card.get("telegram_message_id") or "")
            card["telegram_chat_id"] = str(owner_card.get("telegram_chat_id") or "")
            cursor.execute("""select review_json from public.sam_live_stock_conversation_review_events
                where event_source=%s and review_json->'owner_attention_receipt'->>'decision_id'=%s
                order by created_at desc limit 1""", (EVENT_SOURCE, decision_id))
            receipt_row = cursor.fetchone()
            receipt_review = receipt_row[0] if receipt_row and isinstance(receipt_row[0], Mapping) else json.loads(receipt_row[0]) if receipt_row else {}
            return {"success": True, "status": "owner_attention_card_loaded", "card": card,
                    "expected_owner_identity_hash": review["owner_attention"].get("expected_owner_identity_hash"),
                    "receipt": receipt_review.get("owner_attention_receipt")}
    except Exception:
        return {"success": False, "status": "owner_attention_card_load_failed"}


def _receipt_event(card, receipt):
    event = build_sam_live_stock_review_event({"conversation_id": "OOMAQ-" + card["decision_id"]}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "owner_attention_decision_consumed"}, event_source=EVENT_SOURCE)
    event["review_event_id"] = receipt["receipt_id"]
    event["review_json"] = {"owner_attention_receipt": receipt}
    event["customer_message_excerpt"] = event["sam_reply_excerpt"] = ""
    return event


def _resolution_event(card, receipt, state):
    event = _receipt_event(card, receipt)
    event["review_event_id"] = "OOMAQ-RESOLUTION-" + _digest({"receipt": receipt["receipt_id"], "state": state})[:24]
    event["recommended_action"] = state
    event["review_json"] = {"owner_attention_resolution": {"decision_id": card["decision_id"],
        "receipt_id": receipt["receipt_id"], "state": state, "telegram_chat_id": card["telegram_chat_id"],
        "telegram_message_id": card["telegram_message_id"]}}
    return event


def _specialist_receipt_event(card, receipt, callback_authority):
    event = build_sam_live_stock_review_event({"conversation_id": "OOMAQ-" + receipt["deterministic_identity"]}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "specialist_owner_decision_consumed"},
        event_source=EVENT_SOURCE)
    event["review_event_id"] = receipt["receipt_id"]
    event["review_json"] = {"owner_attention_receipt": receipt,
                            "specialist_outcome_callback": callback_authority}
    event["customer_message_excerpt"] = event["sam_reply_excerpt"] = ""
    return event


def _specialist_resolution_event(card, receipt, state):
    event = _specialist_receipt_event(card, receipt, {})
    event["review_event_id"] = "OOMAQ-SPECIALIST-RESOLUTION-" + _digest(
        {"receipt": receipt["receipt_id"], "state": state})[:20]
    event["recommended_action"] = state
    event["review_json"] = {"owner_attention_resolution": {
        "decision_id": card["decision_id"], "deterministic_identity": receipt["deterministic_identity"],
        "receipt_id": receipt["receipt_id"], "state": state,
        "telegram_chat_id": card["telegram_chat_id"], "telegram_message_id": card["telegram_message_id"]}}
    return event


def _specialist_expiry_event(card, binding, reason):
    base = build_sam_live_stock_review_event({"conversation_id": "OOMAQ-" + binding["deterministic_identity"]}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "specialist_owner_decision_expired"},
        event_source=EVENT_SOURCE)
    base["review_event_id"] = "OOMAQ-SPECIALIST-EXPIRY-" + _digest(
        {"identity": binding["deterministic_identity"], "digest": binding["binding_digest"], "reason": reason})[:20]
    event = build_sam_live_stock_owner_card_event(base, {
        "conversation_id": "OOMAQ-" + binding["deterministic_identity"],
        "telegram_chat_id": card["telegram_chat_id"], "telegram_message_id": card["telegram_message_id"]},
        "expired", reason)
    event["review_event_id"] = base["review_event_id"]
    event["review_json"]["owner_attention"] = {"kind": "decision", "item": dict(card),
        "expected_owner_identity_hash": ""}
    event["customer_message_excerpt"] = event["sam_reply_excerpt"] = ""
    return event


def _expire_prior_decisions(current_ids, *, clock, source, decision_loader, evidence_recorder, telegram_editor):
    loader = decision_loader or _load_active_decisions
    recorder = evidence_recorder or record_sam_live_stock_review_event
    results = []
    for card in loader(source.get(DATABASE_URL_ENV)):
        if isinstance(card.get("specialist_binding"), Mapping):
            continue
        if card.get("decision_id") in current_ids:
            continue
        reason = "expired" if clock >= datetime.fromisoformat(card["expires_at"].replace("Z", "+00:00")) else "chronology_or_evidence_superseded"
        try:
            (telegram_editor or _telegram_edit_message)(_token(source), card["telegram_chat_id"], card["telegram_message_id"],
                "Oom Sakkie — Decision no longer current\n\nSAM owns reassessment. No action was applied.", {"inline_keyboard": []})
            event = build_sam_live_stock_review_event({"conversation_id": "OOMAQ-" + card["decision_id"]}, {}, {},
                {"score": 0, "safe_to_send": False, "recommended_action": "owner_attention_decision_expired"}, event_source=EVENT_SOURCE)
            event["review_event_id"] = "OOMAQ-DECISION-EXPIRED-" + _digest({"decision": card["decision_id"], "reason": reason})[:24]
            event["review_json"] = {"owner_attention": {"kind": "decision", "item": {"decision_id": card["decision_id"]}},
                "owner_card": {"conversation_id": "OOMAQ-" + card["decision_id"], "telegram_chat_id": card["telegram_chat_id"],
                    "telegram_message_id": card["telegram_message_id"], "state": "expired", "action": reason}}
            event["customer_message_excerpt"] = event["sam_reply_excerpt"] = ""
            recorded, status = recorder(event)
            results.append({"success": status < 400 and recorded.get("success") is True, "status": "decision_expired_in_place",
                            "reason": reason, "calls_telegram": True, "decision_id": card["decision_id"]})
        except Exception:
            results.append({"success": False, "status": "decision_expiry_contained", "calls_telegram": False,
                            "decision_id": card.get("decision_id")})
    return results


def _load_active_decisions(database_url=None):
    return _load_active_owner_attention_cards(database_url, "decision", "decision_id")


def _resolve_prior_incidents(current_ids, *, source, incident_loader, evidence_recorder, telegram_editor):
    loader = incident_loader or _load_active_incidents
    incidents = loader(source.get(DATABASE_URL_ENV))
    recorder = evidence_recorder or record_sam_live_stock_review_event
    results = []
    for incident in incidents:
        if incident.get("alert_id") in current_ids:
            continue
        try:
            transition = "superseded" if current_ids else "resolved"
            text = ("Oom Sakkie — SAM system alert updated\n\nA newer system alert is current."
                    if transition == "superseded" else
                    "Oom Sakkie — SAM system recovered\n\nNo manual coverage alert is current.")
            (telegram_editor or _telegram_edit_message)(_token(source), incident["telegram_chat_id"],
                incident["telegram_message_id"], text,
                {"inline_keyboard": []})
            event = build_sam_live_stock_review_event({"conversation_id": incident["identity"]}, {}, {},
                {"score": 0, "safe_to_send": False, "recommended_action": "system_alert_resolved"}, event_source=EVENT_SOURCE)
            event["review_event_id"] = "OOMAQ-ALERT-RESOLVED-" + _digest({"incident": incident, "transition": transition})[:24]
            event["review_json"] = {"owner_attention": {"kind": "system_alert", "item": {"alert_id": incident["alert_id"]}},
                "owner_card": {"conversation_id": incident["identity"], "telegram_chat_id": incident["telegram_chat_id"],
                    "telegram_message_id": incident["telegram_message_id"], "state": transition, "action": "system_" + transition}}
            event["customer_message_excerpt"] = event["sam_reply_excerpt"] = ""
            recorded, status = recorder(event)
            results.append({"success": status < 400 and recorded.get("success") is True, "status": "system_alert_" + transition,
                            "calls_telegram": True, "alert_id": incident["alert_id"]})
        except Exception:
            results.append({"success": False, "status": "system_alert_resolution_contained", "calls_telegram": False,
                            "alert_id": incident.get("alert_id")})
    return results


def _load_active_incidents(database_url=None):
    rows = _load_active_owner_attention_cards(database_url, "system_alert", "alert_id")
    return [{"alert_id": row["alert_id"], "identity": row["identity"], "telegram_chat_id": row["telegram_chat_id"],
             "telegram_message_id": row["telegram_message_id"]} for row in rows]


def _load_active_owner_attention_cards(database_url, kind, id_key):
    if id_key not in {"decision_id", "alert_id"} or kind not in {"decision", "system_alert"}:
        return []
    if not str(database_url or "").strip():
        return []
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=5) as connection, connection.cursor() as cursor:
            cursor.execute(f"""select distinct on (review_json->'owner_attention'->'item'->>'{id_key}')
                review_json from public.sam_live_stock_conversation_review_events
                where review_json->'owner_attention'->>'kind'=%s
                order by review_json->'owner_attention'->'item'->>'{id_key}', created_at desc, review_event_id desc""", (kind,))
            rows = cursor.fetchall()
        incidents = []
        for row in rows:
            review = row[0] if isinstance(row[0], Mapping) else json.loads(row[0])
            owner_card = review.get("owner_card") if isinstance(review.get("owner_card"), Mapping) else {}
            if owner_card.get("state") not in {"active", "with_owner"}:
                continue
            item = review["owner_attention"]["item"]
            incidents.append({id_key: item[id_key], "identity": owner_card["conversation_id"],
                "telegram_chat_id": owner_card["telegram_chat_id"], "telegram_message_id": owner_card["telegram_message_id"]})
            if kind == "decision":
                incidents[-1]["expires_at"] = item["expires_at"]
                if isinstance(item.get("specialist_binding"), Mapping):
                    incidents[-1]["specialist_binding"] = item["specialist_binding"]
        return incidents
    except Exception:
        return []


def _current_binding(binding, source):
    current = dict(binding)
    history = load_chatwoot_conversation_history(binding["conversation_id"], environ=source, limit=100)
    if history.get("success") is not True:
        raise RuntimeError("owner_attention_authoritative_chronology_unavailable")
    inbound = [row for row in history.get("messages", []) if row.get("private") is not True and row.get("message_type") in (0, "incoming")]
    if not inbound:
        raise RuntimeError("owner_attention_authoritative_inbound_unavailable")
    inbound.sort(key=lambda row: (int(row.get("created_at") or 0), int(row.get("id") or 0)))
    current["latest_inbound_id"] = str(inbound[-1]["id"])
    return current


def _current_specialist_chronology(binding, source):
    valid = validate_specialist_binding(binding)
    if valid["specialist_identity"] != "BEACON" or valid["decision_type"] != "organic_publication_decision":
        raise RuntimeError("unsupported specialist chronology")
    database_url = str(source.get(DATABASE_URL_ENV) or "").strip()
    if not database_url:
        raise RuntimeError("specialist chronology database unavailable")
    evidence = valid["evidence_binding"]
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=5) as connection, connection.cursor() as cursor:
            cursor.execute("""select b.binary_asset_id from public.beacon_media_binaries b
                join public.beacon_media_source_links l using(binary_asset_id)
                where b.content_sha256=%s and l.beacon_asset_id=%s limit 1""",
                (evidence["asset_sha256"], evidence["asset_identity"]))
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("specialist asset unavailable")
            binary_id = row[0]
            cursor.execute("""select library_event_id,event_type from public.beacon_media_library_events
                where binary_asset_id=%s order by recorded_at desc,library_event_id desc""", (binary_id,))
            events = cursor.fetchall()
            event_map = {event_id: event_type for event_id, event_type in events}
            if (event_map.get(evidence["library_accept_event_id"]) != "library_accepted"
                    or event_map.get(evidence["public_use_event_id"]) != "public_use_approved"):
                raise RuntimeError("specialist approval evidence changed")
            if events[0][0] != evidence["public_use_event_id"]:
                latest = events[0][0]
            else:
                latest = evidence["public_use_event_id"]
            cursor.execute("""select count(*) from public.beacon_organic_publication_authorization_events
                where binding_id=%s""", (valid["deterministic_identity"],))
            authorizations = int(cursor.fetchone()[0])
            cursor.execute("""select coalesce(campaign_usage_count,0) from public.beacon_media_assets
                where asset_id=%s""", (evidence["asset_identity"],))
            use_row = cursor.fetchone()
            uses = int(use_row[0]) if use_row else 0
        return {"latest_library_event_id": latest, "publication_authorization_count": authorizations,
                "prior_campaign_use_count": uses}
    except Exception as exc:
        raise RuntimeError("specialist authoritative chronology unavailable") from exc


def _status(row):
    if row.get("owner_decision_required") is True:
        return "owner_decision"
    if row.get("provider_confirmed") is True:
        return "automatically_answered"
    if row.get("disposition") == "awaiting_customer":
        return "awaiting_customer"
    if row.get("selected_for_processing") is True:
        return "qualification_progress"
    return "new_enquiry"


def _timestamp(value):
    try:
        return datetime.fromtimestamp(int(value), timezone.utc) if not isinstance(value, datetime) else _aware(value)
    except (TypeError, ValueError, OSError):
        return None


def _sequence(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _opaque(value):
    return str(value or "").strip()[:120]


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _aware(value):
    if value.tzinfo is None:
        raise ValueError("timezone-aware datetime required")
    return value.astimezone(timezone.utc)


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _token(source):
    return str(source.get("SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN") or source.get("OOM_SAKKIE_TELEGRAM_BOT_TOKEN") or "")


def _chat_id(source):
    return str(source.get("SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID") or "")


def _expired_text(edit):
    return "Oom Sakkie — Decision expired\n\nSAM owns reassessment. No action was applied."


def _resolved_text(edit):
    return ("Oom Sakkie — Decision recorded\n\n"
            f"Outcome: {edit['outcome_code'].replace('_', ' ')}\n"
            f"Next follow-up: {edit['next_follow_up_owner']}")


def _result(status, success=False):
    return {"success": success, "status": status, "calls_telegram": False, "sends_customer_message": False,
            "writes_farm_data": False, "creates_order": False, "reserves_stock": False}
