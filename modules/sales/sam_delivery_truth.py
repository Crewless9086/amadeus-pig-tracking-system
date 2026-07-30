"""Sanitized, append-only outbound delivery truth for SAM customer messages."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Mapping


DELIVERY_CONTRACT_VERSION = "sam_outbound_delivery_v1"
PREPARED = "prepared"
ATTEMPT_CLAIMED = "attempt_claimed"
CHATWOOT_ACCEPTED_UNVERIFIED = "chatwoot_accepted_unverified"
PROVIDER_DELIVERED = "provider_delivered"
PROVIDER_READ = "provider_read"
PROVIDER_FAILED = "provider_failed"
PROVIDER_OUTCOME_AMBIGUOUS = "provider_outcome_ambiguous"
CONFIRMED_STATES = {PROVIDER_DELIVERED, PROVIDER_READ}
NO_RETRY_STATES = {
    ATTEMPT_CLAIMED,
    CHATWOOT_ACCEPTED_UNVERIFIED,
    PROVIDER_DELIVERED,
    PROVIDER_READ,
    PROVIDER_FAILED,
    PROVIDER_OUTCOME_AMBIGUOUS,
}
DELIVERY_EVENT_SOURCES = {
    "sam_outbound_delivery_attempt_claim",
    "sam_outbound_delivery_transition",
}
DEFAULT_UNVERIFIED_OBSERVATION_SECONDS = 300
SUPPORTED_PROVIDER_STATUSES = {"sent", "delivered", "read", "failed"}


def build_delivery_attempt(inbound, decision, review, *, response_class="", attempt_generation=1, require_account_identity=False):
    inbound = inbound if isinstance(inbound, Mapping) else {}
    decision = decision if isinstance(decision, Mapping) else {}
    review = review if isinstance(review, Mapping) else {}
    conversation_id = _clean(inbound.get("conversation_id"), 120)
    account_id = _clean(inbound.get("account_id"), 120)
    contact_id = _clean(inbound.get("contact_id"), 120)
    inbox_id = _clean(inbound.get("inbox_id"), 120)
    inbound_message_id = _clean(inbound.get("message_id"), 120)
    review_id = _clean(
        review.get("review_event_id")
        or decision.get("review_event_id")
        or decision.get("conversation_review_id"),
        120,
    )
    owner_action_identity = _clean(review.get("owner_action_identity"), 120)
    reply = _clean_multiline(decision.get("suggested_reply_text"), 1800)
    reply_hash = hashlib.sha256(reply.encode("utf-8", errors="ignore")).hexdigest()
    response_class = _clean(
        response_class
        or (decision.get("autoreply_canary") or {}).get("response_class")
        or decision.get("response_class")
        or "routine_reply",
        80,
    )
    try:
        generation = max(1, int(attempt_generation))
    except (TypeError, ValueError):
        generation = 1
    required_pairs = [
        ("conversation_id", conversation_id),
        ("contact_id", contact_id),
        ("inbox_id", inbox_id),
        ("inbound_message_id", inbound_message_id),
        ("reply_hash", reply_hash),
        ("review_id", review_id),
        ("response_class", response_class),
    ]
    if require_account_identity:
        required_pairs.insert(0, ("account_id", account_id))
    required = [value for _, value in required_pairs]
    if not all(required):
        return {
            "success": False,
            "status": "delivery_attempt_identity_incomplete",
            "missing_fields": [name for name, value in required_pairs if not value],
        }
    identity_values = [
        conversation_id,
        contact_id,
        inbox_id,
        inbound_message_id,
        reply_hash,
        review_id,
        DELIVERY_CONTRACT_VERSION,
        response_class,
        str(generation),
        owner_action_identity,
    ]
    if require_account_identity:
        identity_values.insert(0, account_id)
    attempt_id = _stable_id("SAM-DELIVERY-ATTEMPT", identity_values)
    return {
        "success": True,
        "status": ATTEMPT_CLAIMED,
        "delivery_attempt_id": attempt_id,
        "delivery_contract_version": DELIVERY_CONTRACT_VERSION,
        "account_id": account_id,
        "conversation_id": conversation_id,
        "contact_id": contact_id,
        "inbox_id": inbox_id,
        "inbound_message_id": inbound_message_id,
        "review_id": review_id,
        "owner_action_identity": owner_action_identity,
        "reply_hash": reply_hash,
        "response_class": response_class,
        "attempt_generation": generation,
        "previous_delivery_state": PREPARED,
        "delivery_state": ATTEMPT_CLAIMED,
        "automatic_retry_prohibited": True,
        "customer_send_confirmed": False,
        "handled_autonomously": False,
        "contains_private_message_content": False,
        "contains_raw_provider_identity": False,
    }


def build_delivery_claim_event(attempt):
    attempt = _attempt(attempt)
    if not attempt.get("success"):
        return {}
    evidence = _evidence(attempt, ATTEMPT_CLAIMED)
    evidence["claim_timestamp"] = _utc_now()
    return _event(
        attempt["delivery_attempt_id"],
        "sam_outbound_delivery_attempt_claim",
        attempt["conversation_id"],
        attempt["inbound_message_id"],
        evidence,
    )


def classify_chatwoot_response(response):
    response = response if isinstance(response, Mapping) else {}
    status_code = response.get("status_code")
    body = response.get("body") if isinstance(response.get("body"), Mapping) else {}
    message_status = _clean(
        body.get("status")
        or body.get("delivery_status")
        or response.get("status")
        or response.get("delivery_status"),
        40,
    ).lower()
    outgoing_message_id = _clean(
        body.get("id") or body.get("message_id") or response.get("message_id"),
        120,
    )
    source_identity = (
        body.get("source_id")
        or (body.get("content_attributes") or {}).get("source_id")
        or response.get("source_id")
    )
    provider_identity_class = classify_provider_identity(source_identity)
    if not isinstance(status_code, int) or not 200 <= status_code < 300:
        state = PROVIDER_OUTCOME_AMBIGUOUS
        failure_class = "chatwoot_acceptance_unresolved"
    elif message_status in {"delivered"}:
        state = PROVIDER_DELIVERED
        failure_class = ""
    elif message_status in {"read"}:
        state = PROVIDER_READ
        failure_class = ""
    elif message_status in {"failed"}:
        state = PROVIDER_FAILED
        failure_class = "provider_reported_failed"
    elif message_status in {"sent"}:
        state = CHATWOOT_ACCEPTED_UNVERIFIED
        failure_class = ""
    else:
        state = PROVIDER_OUTCOME_AMBIGUOUS
        failure_class = "delivery_status_missing_or_malformed"
    if state != PROVIDER_OUTCOME_AMBIGUOUS and not outgoing_message_id:
        state = PROVIDER_OUTCOME_AMBIGUOUS
        failure_class = "chatwoot_outgoing_identity_missing"
    confirmed = state in CONFIRMED_STATES
    return {
        "delivery_state": state,
        "chatwoot_outgoing_message_id": outgoing_message_id,
        "chatwoot_response_status": message_status or "unresolved",
        "provider_identity_class": provider_identity_class,
        "automatic_retry_prohibited": True,
        "customer_send_confirmed": confirmed,
        "handled_autonomously": confirmed,
        "failure_class": failure_class,
        "status_code_class": "2xx" if isinstance(status_code, int) and 200 <= status_code < 300 else "unresolved",
        "contains_raw_provider_identity": False,
    }


def classify_dispatch_exception(exc):
    return {
        "delivery_state": PROVIDER_OUTCOME_AMBIGUOUS,
        "chatwoot_outgoing_message_id": "",
        "chatwoot_response_status": "unresolved",
        "provider_identity_class": "absent",
        "automatic_retry_prohibited": True,
        "customer_send_confirmed": False,
        "handled_autonomously": False,
        "failure_class": (
            "dispatch_timeout_or_transport_ambiguous"
            if isinstance(exc, (TimeoutError, ConnectionError))
            else "dispatch_outcome_ambiguous"
        ),
        "error_type": exc.__class__.__name__,
        "contains_raw_provider_identity": False,
    }


def classify_provider_identity(value):
    value = str(value or "").strip()
    lower = value.lower()
    if lower.startswith("wamid."):
        return "whatsapp_provider"
    if lower.startswith(("sam_live_stock:", "order_document:", "amadeus:")):
        return "application_supplied"
    return "other" if value else "absent"


def normalize_chatwoot_delivery_event(payload):
    """Normalize a Chatwoot message_updated envelope without retaining raw payload data."""
    payload = payload if isinstance(payload, Mapping) else {}
    nodes = [("payload", payload)]
    for key in ("message", "message_payload", "data"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            nodes.append((f"payload.{key}", value))
    messages = payload.get("messages")
    if isinstance(messages, list):
        nodes.extend(
            (f"payload.messages[{index}]", value)
            for index, value in enumerate(messages[:2])
            if isinstance(value, Mapping)
        )

    def candidates(keys, *, nested=()):
        found = []
        for path, node in nodes:
            for key in keys:
                value = _clean(node.get(key), 120)
                if value:
                    found.append((f"{path}.{key}", value))
            for container in nested:
                child = node.get(container)
                if isinstance(child, Mapping):
                    for key in keys:
                        value = _clean(child.get(key), 120)
                        if value:
                            found.append((f"{path}.{container}.{key}", value))
        return found

    event_values = candidates(("event", "event_name", "webhook_event"))
    event_type = (event_values[0][1] if event_values else "").lower()
    message_nodes = [
        (path, node) for path, node in nodes
        if path != "payload" or any(
            key in node for key in ("message_id", "message_type", "delivery_status", "message_status")
        )
    ]
    if not message_nodes and any(key in payload for key in ("id", "status", "source_id")):
        message_nodes = [("payload", payload)]

    status_values = []
    for path, node in message_nodes:
        for key in ("delivery_status", "message_status", "source_status", "status"):
            value = _clean(node.get(key), 40).lower()
            if value:
                status_values.append((f"{path}.{key}", value))
        for container in ("content_attributes", "additional_attributes"):
            child = node.get(container)
            if isinstance(child, Mapping):
                for key in ("delivery_status", "message_status", "source_status"):
                    value = _clean(child.get(key), 40).lower()
                    if value:
                        status_values.append((f"{path}.{container}.{key}", value))

    message_values = []
    for path, node in message_nodes:
        for key in ("message_id", "id"):
            value = _clean(node.get(key), 120)
            if value:
                message_values.append((f"{path}.{key}", value))
    conversation_values = candidates(
        ("conversation_id", "chatwoot_conversation_id"),
        nested=("conversation",),
    )
    for path, node in nodes:
        conversation = node.get("conversation")
        if isinstance(conversation, Mapping):
            value = _clean(conversation.get("id"), 120)
            if value:
                conversation_values.append((f"{path}.conversation.id", value))
    account_values = candidates(("account_id",), nested=("account",))
    inbox_values = candidates(("inbox_id",), nested=("inbox", "conversation"))
    for path, node in nodes:
        account = node.get("account")
        if isinstance(account, Mapping):
            value = _clean(account.get("id"), 120)
            if value:
                account_values.append((f"{path}.account.id", value))
        inbox = node.get("inbox")
        if isinstance(inbox, Mapping):
            value = _clean(inbox.get("id"), 120)
            if value:
                inbox_values.append((f"{path}.inbox.id", value))
        for parent in ("conversation",):
            child = node.get(parent)
            if isinstance(child, Mapping):
                inbox = child.get("inbox")
                if isinstance(inbox, Mapping):
                    value = _clean(inbox.get("id"), 120)
                    if value:
                        inbox_values.append((f"{path}.{parent}.inbox.id", value))
    type_values = candidates(("message_type",))
    provider_values = candidates(("source_id",), nested=("content_attributes",))
    timestamp_values = candidates(("event_timestamp", "updated_at", "created_at"))

    def resolve(found):
        values = {value for _, value in found}
        return (next(iter(values)) if len(values) == 1 else "", len(values) > 1)

    message_id, message_conflict = resolve(message_values)
    conversation_id, conversation_conflict = resolve(conversation_values)
    account_id, account_conflict = resolve(account_values)
    inbox_id, inbox_conflict = resolve(inbox_values)
    message_type, type_conflict = resolve(type_values)
    recognized_statuses = [(path, value) for path, value in status_values if value in SUPPORTED_PROVIDER_STATUSES]
    unknown_status = any(value not in SUPPORTED_PROVIDER_STATUSES for _, value in status_values)
    normalized_status, status_conflict = resolve(recognized_statuses)
    malformed = not normalized_status or unknown_status
    conflict = any((
        message_conflict, conversation_conflict, account_conflict, inbox_conflict,
        type_conflict, status_conflict,
    ))
    provider_classes = {classify_provider_identity(value) for _, value in provider_values}
    provider_class = next(iter(provider_classes)) if len(provider_classes) == 1 else (
        "conflicting" if provider_classes else "absent"
    )
    provider_conflict = len(provider_classes) > 1
    conflict = conflict or provider_conflict
    source_path = next(
        (path for path, value in recognized_statuses if value == normalized_status),
        "",
    )
    event_timestamp = timestamp_values[0][1] if timestamp_values else ""
    outgoing = str(message_type).lower() in {"1", "outgoing"}
    return {
        "event_type": event_type,
        "chatwoot_message_id": message_id,
        "conversation_id": conversation_id,
        "account_id": account_id,
        "inbox_id": inbox_id,
        "message_type": message_type,
        "outgoing": outgoing,
        "provider_identity_class": provider_class,
        "normalized_status": normalized_status or "unresolved",
        "status_source_path": source_path,
        "event_timestamp": event_timestamp,
        "conflict": conflict,
        "malformed": malformed,
        "source_count": len(status_values),
        "contains_raw_provider_identity": False,
        "contains_private_message_content": False,
    }


def build_delivery_transition_event(attempt, outcome):
    attempt = _attempt(attempt)
    outcome = outcome if isinstance(outcome, Mapping) else {}
    state = _clean(outcome.get("delivery_state"), 80)
    if not attempt.get("success") or state not in {
        CHATWOOT_ACCEPTED_UNVERIFIED,
        PROVIDER_DELIVERED,
        PROVIDER_READ,
        PROVIDER_FAILED,
        PROVIDER_OUTCOME_AMBIGUOUS,
    }:
        return {}
    outgoing_message_id = _clean(outcome.get("chatwoot_outgoing_message_id"), 120)
    evidence = _evidence(attempt, state)
    evidence.update({
        "chatwoot_outgoing_message_id": outgoing_message_id,
        "chatwoot_response_status": _clean(outcome.get("chatwoot_response_status"), 40),
        "provider_identity_class": _clean(outcome.get("provider_identity_class"), 40) or "absent",
        "terminal_or_reconciled_timestamp": _utc_now(),
        "customer_send_confirmed": state in CONFIRMED_STATES,
        "handled_autonomously": state in CONFIRMED_STATES,
        "failure_class": _clean(outcome.get("failure_class"), 100),
        "reconciliation_source": _clean(outcome.get("reconciliation_source"), 80),
        "status_source_path": _clean(outcome.get("status_source_path"), 160),
        "provider_event_type": _clean(outcome.get("provider_event_type"), 80),
        "provider_event_timestamp": _clean(outcome.get("provider_event_timestamp"), 80),
        "provider_event_conflict": bool(outcome.get("provider_event_conflict")),
        "provider_event_malformed": bool(outcome.get("provider_event_malformed")),
    })
    terminal = state in {PROVIDER_DELIVERED, PROVIDER_READ, PROVIDER_FAILED}
    event_id = _stable_id(
        "SAM-DELIVERY-TERMINAL" if terminal else "SAM-DELIVERY-TRANSITION",
        [attempt["delivery_attempt_id"], outgoing_message_id]
        if terminal else [attempt["delivery_attempt_id"], state, outgoing_message_id],
    )
    return _event(
        event_id,
        "sam_outbound_delivery_transition",
        attempt["conversation_id"],
        outgoing_message_id or attempt["inbound_message_id"],
        evidence,
    )


def reconcile_delivery_attempt(attempt, message_loader, transition_recorder=None):
    attempt = _attempt(attempt)
    if not attempt.get("success"):
        return {"success": False, "status": "delivery_attempt_invalid", "send_attempted": False}
    outgoing_message_id = _clean(attempt.get("chatwoot_outgoing_message_id"), 120)
    if not outgoing_message_id:
        return {
            "success": False,
            "status": "delivery_outgoing_identity_missing",
            "delivery_state": PROVIDER_OUTCOME_AMBIGUOUS,
            "send_attempted": False,
        }
    try:
        loaded = message_loader(attempt["conversation_id"], outgoing_message_id)
    except Exception as exc:
        loaded = {"status_code": None, "error_type": exc.__class__.__name__}
    if not isinstance(loaded, Mapping):
        loaded = {}
    body = loaded.get("body") if isinstance(loaded.get("body"), Mapping) else loaded
    observed_conversation = _clean(
        body.get("conversation_id")
        or (body.get("conversation") or {}).get("id"),
        120,
    )
    observed_message = _clean(body.get("id") or body.get("message_id"), 120)
    if (
        observed_conversation and observed_conversation != attempt["conversation_id"]
    ) or (observed_message and observed_message != outgoing_message_id):
        return {
            "success": False,
            "status": "delivery_reconciliation_identity_mismatch",
            "delivery_state": PROVIDER_OUTCOME_AMBIGUOUS,
            "send_attempted": False,
        }
    outcome = classify_chatwoot_response({
        "status_code": loaded.get("status_code", 200 if body else None),
        "body": body,
    })
    outcome["chatwoot_outgoing_message_id"] = outgoing_message_id
    event = build_delivery_transition_event(attempt, outcome)
    recorded = {"success": True, "created": False, "status": "transition_not_recorded"}
    if transition_recorder is not None:
        recorded = transition_recorder(event)
        if not isinstance(recorded, Mapping):
            recorded = {"success": False, "created": False, "status": "transition_record_invalid"}
    return {
        "success": True,
        "status": "delivery_reconciled",
        **outcome,
        "transition_event_id": event.get("review_event_id", ""),
        "transition_created": recorded.get("created") is True,
        "send_attempted": False,
        "automatic_retry_prohibited": True,
    }


def delivery_exception_required(state, *, age_seconds=0, observation_seconds=DEFAULT_UNVERIFIED_OBSERVATION_SECONDS):
    state = _clean(state, 80)
    if state in {PROVIDER_FAILED, PROVIDER_OUTCOME_AMBIGUOUS}:
        return True
    return state == CHATWOOT_ACCEPTED_UNVERIFIED and age_seconds >= max(1, int(observation_seconds))


def sanitized_attempt_chain(events, conversation_id, attempt_id=""):
    conversation_id = _clean(conversation_id, 120)
    attempt_id = _clean(attempt_id, 120)
    chain = []
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, Mapping):
            continue
        if _clean(event.get("chatwoot_conversation_id"), 120) != conversation_id:
            continue
        if event.get("event_source") not in DELIVERY_EVENT_SOURCES:
            continue
        evidence = event.get("review_json") if isinstance(event.get("review_json"), Mapping) else {}
        if attempt_id and _clean(evidence.get("delivery_attempt_id"), 120) != attempt_id:
            continue
        chain.append({
            "review_event_id": _clean(event.get("review_event_id"), 120),
            "event_source": _clean(event.get("event_source"), 80),
            "delivery_attempt_id": _clean(evidence.get("delivery_attempt_id"), 120),
            "delivery_state": _clean(evidence.get("delivery_state"), 80),
            "chatwoot_message_id": _clean(event.get("chatwoot_message_id"), 120),
            "customer_send_confirmed": evidence.get("customer_send_confirmed") is True,
            "handled_autonomously": evidence.get("handled_autonomously") is True,
            "automatic_retry_prohibited": evidence.get("automatic_retry_prohibited") is True,
        })
    return chain


def load_attempt_chain(database_url, conversation_id, attempt_id):
    conversation_id = _clean(conversation_id, 120)
    attempt_id = _clean(attempt_id, 120)
    if not database_url or not conversation_id or not attempt_id:
        return {"success": False, "status": "delivery_chain_identity_incomplete", "events": []}
    try:
        import psycopg
        with psycopg.connect(
            str(database_url).strip(),
            connect_timeout=1,
            options=(
                "-c default_transaction_read_only=on "
                "-c statement_timeout=750 "
                "-c lock_timeout=250"
            ),
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select review_event_id, chatwoot_conversation_id,
                           chatwoot_message_id, event_source, review_json,
                           created_at
                    from public.sam_live_stock_conversation_review_events
                    where chatwoot_conversation_id = %s
                      and event_source = any(%s)
                    order by created_at, review_event_id
                    """,
                    (conversation_id, sorted(DELIVERY_EVENT_SOURCES)),
                )
                columns = [column.name for column in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as exc:
        return {
            "success": False,
            "status": "delivery_chain_load_failed",
            "error_type": exc.__class__.__name__,
            "events": [],
        }
    chain = sanitized_attempt_chain(rows, conversation_id, attempt_id)
    latest = chain[-1] if chain else {}
    return {
        "success": bool(chain),
        "status": "delivery_chain_loaded" if chain else "delivery_chain_not_found",
        "conversation_id": conversation_id,
        "delivery_attempt_id": attempt_id,
        "events": chain,
        "latest_delivery_state": latest.get("delivery_state", ""),
        "customer_send_confirmed": latest.get("customer_send_confirmed") is True,
        "handled_autonomously": latest.get("handled_autonomously") is True,
        "automatic_retry_prohibited": bool(chain),
    }


def load_delivery_attempt_for_outgoing_message(database_url, conversation_id, outgoing_message_id):
    """Recover one exact attempt from append-only evidence; ambiguity fails closed."""
    conversation_id = _clean(conversation_id, 120)
    outgoing_message_id = _clean(outgoing_message_id, 120)
    if not database_url or not conversation_id or not outgoing_message_id:
        return {"success": False, "status": "delivery_lookup_identity_incomplete", "attempt": {}}
    try:
        import psycopg
        with psycopg.connect(str(database_url).strip(), connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select review_event_id, event_source, review_json
                    from public.sam_live_stock_conversation_review_events
                    where chatwoot_conversation_id = %s
                      and event_source = any(%s)
                    order by created_at, review_event_id
                    """,
                    (conversation_id, sorted(DELIVERY_EVENT_SOURCES)),
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "status": "delivery_lookup_failed",
            "error_type": exc.__class__.__name__,
            "attempt": {},
        }
    claims = {}
    matched_attempt_ids = set()
    for event_id, event_source, raw_review in rows:
        if isinstance(raw_review, str):
            try:
                raw_review = json.loads(raw_review)
            except (TypeError, ValueError):
                raw_review = {}
        evidence = raw_review if isinstance(raw_review, Mapping) else {}
        if not isinstance(evidence, Mapping):
            continue
        attempt_id = _clean(evidence.get("delivery_attempt_id"), 120)
        if event_source == "sam_outbound_delivery_attempt_claim" and attempt_id:
            claims[attempt_id] = dict(evidence)
        if (
            event_source == "sam_outbound_delivery_transition"
            and _clean(evidence.get("chatwoot_outgoing_message_id"), 120) == outgoing_message_id
            and attempt_id
        ):
            matched_attempt_ids.add(attempt_id)
    if len(matched_attempt_ids) != 1:
        return {
            "success": False,
            "status": "delivery_lookup_not_found" if not matched_attempt_ids else "delivery_lookup_ambiguous",
            "attempt": {},
        }
    attempt_id = next(iter(matched_attempt_ids))
    claim = claims.get(attempt_id)
    if not claim:
        return {"success": False, "status": "delivery_claim_not_found", "attempt": {}}
    attempt = {
        "success": True,
        "delivery_attempt_id": attempt_id,
        **{
            key: claim.get(key)
            for key in (
                "delivery_contract_version", "conversation_id", "contact_id",
                "inbox_id", "inbound_message_id", "review_id", "reply_hash",
                "response_class", "attempt_generation", "owner_action_identity",
            )
        },
        "chatwoot_outgoing_message_id": outgoing_message_id,
    }
    if _clean(attempt.get("conversation_id"), 120) != conversation_id:
        return {"success": False, "status": "delivery_lookup_conversation_mismatch", "attempt": {}}
    return {"success": True, "status": "delivery_attempt_loaded", "attempt": attempt}


def _attempt(value):
    value = dict(value) if isinstance(value, Mapping) else {}
    value["success"] = bool(value.get("success") and value.get("delivery_attempt_id"))
    return value


def _evidence(attempt, state):
    return {
        "delivery_attempt_id": attempt["delivery_attempt_id"],
        "delivery_contract_version": attempt["delivery_contract_version"],
        "account_id": attempt.get("account_id", ""),
        "conversation_id": attempt["conversation_id"],
        "contact_id": attempt["contact_id"],
        "inbox_id": attempt["inbox_id"],
        "inbound_message_id": attempt["inbound_message_id"],
        "review_id": attempt["review_id"],
        "owner_action_identity": attempt.get("owner_action_identity", ""),
        "reply_hash": attempt["reply_hash"],
        "response_class": attempt["response_class"],
        "attempt_generation": attempt["attempt_generation"],
        "delivery_state": state,
        "automatic_retry_prohibited": True,
        "customer_send_confirmed": state in CONFIRMED_STATES,
        "handled_autonomously": state in CONFIRMED_STATES,
        "contains_private_message_content": False,
        "contains_raw_provider_identity": False,
    }


def _event(event_id, source, conversation_id, message_id, evidence):
    return {
        "review_event_id": event_id,
        "chatwoot_conversation_id": conversation_id,
        "chatwoot_message_id": message_id,
        "customer_name": "",
        "channel": "chatwoot",
        "source_agent": "sam_outbound_delivery_truth",
        "event_source": source,
        "customer_message_excerpt": "",
        "sam_reply_excerpt": "",
        "score": 0,
        "confidence_target": 0,
        "safe_to_send": False,
        "owner_send_required": False,
        "no_reply_recommended": False,
        "escalation_required": False,
        "conversation_mode_recommendation": "AUTO",
        "recommended_action": "automatic_retry_prohibited",
        "review_json": evidence,
        "facts_json": {},
        "decision_json": {},
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_telegram": False,
        "creates_order": False,
        "reserves_stock": False,
        "changes_stock": False,
        "writes_farm_data": False,
    }


def _stable_id(prefix, values):
    raw = "|".join(str(value or "") for value in values)
    return prefix + "-" + hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:20].upper()


def _clean(value, limit):
    return str(value or "").strip()[:limit]


def _clean_multiline(value, limit):
    return "\n".join(line.rstrip() for line in str(value or "").strip().splitlines())[:limit]


def _utc_now():
    return datetime.now(timezone.utc).isoformat()
