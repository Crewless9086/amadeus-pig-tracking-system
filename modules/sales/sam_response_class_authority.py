"""Persistent, fail-closed response-class authority controller."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from typing import Any, Callable, Iterable, Mapping

from services.database_service import DATABASE_URL_ENV
from modules.sales.sam_live_stock_evaluation import (
    EVALUATOR_VERSION,
    INITIAL_PREAUTHORIZED_CLASSES,
    evaluate_response_class_graduation,
)


TABLE = "sam_response_class_authority_events"
CONTROLLER_ENABLED_ENV = "SAM_RESPONSE_CLASS_AUTHORITY_CONTROLLER_ENABLED"
GLOBAL_KILL_SWITCH_ENV = "SAM_RESPONSE_CLASS_AUTHORITY_GLOBAL_ENABLED"
CLASS_SWITCH_PREFIX = "SAM_RESPONSE_CLASS_"
ALLOWED_DECISIONS = {
    "candidate", "canary_authorized", "promoted", "paused", "regressed", "retired",
}
OPERATING_STATES = {"promoted"}
OWNER_ONLY_DECISIONS = {"canary_authorized", "promoted", "retired"}
REGRESSION_SIGNALS = {
    "wrong_lane", "unsupported_claim", "duplicate_or_retry",
    "delivery_failure", "delivery_ambiguous", "owner_rejected",
}
LEARNING_CLASS_ALIASES = {
    "social_acknowledgement": "acknowledgement",
    "social_close": "simple_conversational_closure",
}

AUTHORITY_FLAGS = {
    "sends_customer_message": False,
    "calls_chatwoot": False,
    "calls_telegram": False,
    "creates_order": False,
    "creates_quote": False,
    "reserves_stock": False,
    "changes_stock": False,
    "writes_farm_data": False,
    "mutates_business_state": False,
}


def class_switch_env(response_class: str) -> str:
    return f"{CLASS_SWITCH_PREFIX}{_clean_class(response_class).upper()}_ENABLED"


def evidence_window_identity(response_class: str, evidence: Mapping[str, Any]) -> tuple[str, str]:
    canonical = {
        "response_class": _clean_class(response_class),
        "evaluator_version": EVALUATOR_VERSION,
        "evidence": _json_safe(dict(evidence or {})),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest().upper()
    return f"SAM-EVIDENCE-{digest[:24]}", digest


def build_authority_event(
    response_class: str,
    decision: str,
    evaluation: Mapping[str, Any],
    *,
    actor_type: str,
    actor_id: str,
    reason: str,
    prior_event: Mapping[str, Any] | None = None,
    authorized_envelope: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
    lifetime_days: int = 7,
) -> dict[str, Any]:
    now = _aware(now or datetime.now(timezone.utc))
    response_class = _clean_class(response_class)
    decision = str(decision or "").strip().lower()
    actor_type = str(actor_type or "").strip().lower()
    actor_id = str(actor_id or "").strip()[:120]
    reason = str(reason or "").strip()[:500]
    evaluation = dict(evaluation or {})
    evidence = dict(evaluation.get("evidence") or {})
    if response_class not in INITIAL_PREAUTHORIZED_CLASSES:
        raise ValueError("response_class_outside_initial_envelope")
    if decision not in ALLOWED_DECISIONS:
        raise ValueError("authority_decision_invalid")
    if actor_type not in {"owner", "server", "charlie"}:
        raise ValueError("authority_actor_invalid")
    if actor_type == "charlie" and decision != "paused":
        raise ValueError("charlie_may_only_pause")
    if decision in OWNER_ONLY_DECISIONS and actor_type != "owner":
        raise ValueError("owner_authority_required")
    if not actor_id or not reason:
        raise ValueError("actor_and_reason_required")
    envelope = _validated_envelope(response_class, authorized_envelope or {})
    if decision in {"canary_authorized", "promoted"} and not envelope:
        raise ValueError("authorized_envelope_required")
    window_id, window_hash = evidence_window_identity(response_class, evidence)
    source = environ if environ is not None else os.environ
    global_clear = _truthy(source.get(GLOBAL_KILL_SWITCH_ENV))
    class_clear = _truthy(source.get(class_switch_env(response_class)))
    prior_id = str((prior_event or {}).get("authority_event_id") or "")
    effective_at = now
    expires_at = now + timedelta(days=max(1, min(int(lifetime_days), 30)))
    canonical = {
        "response_class": response_class,
        "evidence_window_hash": window_hash,
        "evaluator_version": EVALUATOR_VERSION,
        "decision": decision,
        "prior_event_id": prior_id,
        "authorized_envelope": envelope,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "reason": reason,
        "effective_at": effective_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24].upper()
    return {
        "authority_event_id": f"SAM-AUTHORITY-{digest}",
        **canonical,
        "evidence_window_id": window_id,
        "evidence": _json_safe(evidence),
        "blockers": sorted(
            key for key, passed in (evaluation.get("gates") or {}).items()
            if passed is not True
        ),
        "global_kill_switch_clear": global_clear,
        "class_kill_switch_clear": class_clear,
        "created_at": now.isoformat(),
        "contains_customer_content": False,
        **AUTHORITY_FLAGS,
    }


def record_authority_event(event: Mapping[str, Any], *, database_url: str | None = None):
    event = dict(event or {})
    error = _validate_persisted_event(event)
    if error:
        return _result(error), 400
    database_url = _database_url(database_url)
    if not database_url:
        return _result("authority_database_unavailable"), 503
    try:
        import psycopg
        with psycopg.connect(
            database_url, connect_timeout=5,
            options="-c statement_timeout=8000 -c lock_timeout=2000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select authority_event_id, decision
                    from public.{TABLE}
                    where response_class=%s
                      and (
                        (nullif(%s, '') is not null and prior_event_id=nullif(%s, ''))
                        or (
                          nullif(%s, '') is null
                          and prior_event_id is null
                          and evidence_window_hash=%s
                        )
                      )
                    for share
                    """,
                    (
                        event["response_class"], event.get("prior_event_id", ""),
                        event.get("prior_event_id", ""), event.get("prior_event_id", ""),
                        event["evidence_window_hash"],
                    ),
                )
                existing = cursor.fetchall()
                conflict = next((row for row in existing if row[1] != event["decision"]), None)
                if conflict:
                    connection.rollback()
                    return _result(
                        "conflicting_authority_decision",
                        existing_event_id=conflict[0],
                    ), 409
                cursor.execute(
                    f"""
                    insert into public.{TABLE} (
                      authority_event_id, response_class, evidence_window_id,
                      evidence_window_hash, evaluator_version, decision,
                      prior_event_id, authorized_envelope_json, actor_type,
                      actor_id, reason, evidence_json, blockers_json,
                      global_kill_switch_clear, class_kill_switch_clear,
                      created_at, effective_at, expires_at,
                      contains_customer_content, sends_customer_message,
                      mutates_business_state
                    ) values (
                      %(authority_event_id)s, %(response_class)s,
                      %(evidence_window_id)s, %(evidence_window_hash)s,
                      %(evaluator_version)s, %(decision)s,
                      nullif(%(prior_event_id)s,''), %(authorized_envelope)s::jsonb,
                      %(actor_type)s, %(actor_id)s, %(reason)s,
                      %(evidence)s::jsonb, %(blockers)s::jsonb,
                      %(global_kill_switch_clear)s, %(class_kill_switch_clear)s,
                      %(created_at)s::timestamptz, %(effective_at)s::timestamptz,
                      %(expires_at)s::timestamptz, false, false, false
                    )
                    on conflict (authority_event_id) do nothing
                    returning authority_event_id
                    """,
                    {
                        **event,
                        "authorized_envelope": json.dumps(event.get("authorized_envelope") or {}),
                        "evidence": json.dumps(event.get("evidence") or {}),
                        "blockers": json.dumps(event.get("blockers") or []),
                    },
                )
                created = cursor.fetchone()
            connection.commit()
        return _result(
            "authority_event_recorded" if created else "authority_event_replay_withheld",
            created=bool(created),
            authority_event_id=event["authority_event_id"],
        ), 201 if created else 200
    except Exception as exc:
        return _result("authority_persistence_failed", error_type=exc.__class__.__name__), 503


def list_latest_authority_events(*, database_url: str | None = None):
    database_url = _database_url(database_url)
    if not database_url:
        return _result("authority_database_unavailable", events=[]), 503
    try:
        import psycopg
        with psycopg.connect(
            database_url, connect_timeout=5,
            options="-c default_transaction_read_only=on -c statement_timeout=8000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select distinct on (response_class)
                      authority_event_id, response_class, evidence_window_id,
                      evidence_window_hash, evaluator_version, decision,
                      prior_event_id, authorized_envelope_json, actor_type,
                      actor_id, reason, evidence_json, blockers_json,
                      global_kill_switch_clear, class_kill_switch_clear,
                      created_at, effective_at, expires_at
                    from public.{TABLE}
                    order by response_class, effective_at desc, created_at desc,
                             authority_event_id desc
                    limit 50
                    """
                )
                rows = cursor.fetchall()
        return _result("authority_events_loaded", events=[_event_row(row) for row in rows]), 200
    except Exception as exc:
        return _result(
            "authority_events_unavailable", events=[], error_type=exc.__class__.__name__
        ), 503


def evaluate_and_persist_candidates(
    evidence_events: Iterable[Mapping[str, Any]],
    *,
    actor_id: str = "sam_authority_evaluator",
    database_url: str | None = None,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
    recorder: Callable[..., tuple[dict[str, Any], int]] | None = None,
) -> dict[str, Any]:
    now = _aware(now or datetime.now(timezone.utc))
    evaluation = evaluate_response_class_graduation(evidence_events, now=now)
    latest_result, _ = list_latest_authority_events(database_url=database_url)
    latest = {
        row["response_class"]: row
        for row in latest_result.get("events", [])
        if isinstance(row, dict)
    }
    persisted = []
    failures = []
    write = recorder or record_authority_event
    for response_class in INITIAL_PREAUTHORIZED_CLASSES:
        row = evaluation["classes"][response_class]
        prior = latest.get(response_class) or {}
        decision = ""
        reason = ""
        if row["decision"] == "candidate" and prior.get("decision") not in {
            "candidate", "canary_authorized", "promoted",
        }:
            decision, reason = "candidate", "canonical_v2_thresholds_passed"
        elif row["decision"] == "regressed" and prior.get("decision") in {
            "candidate", "canary_authorized", "promoted",
        }:
            decision, reason = "regressed", "class_specific_failure_evidence"
        if not decision:
            continue
        event = build_authority_event(
            response_class, decision, row,
            actor_type="server", actor_id=actor_id, reason=reason,
            prior_event=prior, environ=environ, now=now,
        )
        result, status = write(event, database_url=database_url)
        (persisted if status < 400 else failures).append({
            "response_class": response_class,
            "status": result.get("status"),
            "authority_event_id": result.get("authority_event_id", ""),
        })
    return _result(
        "authority_evaluation_completed" if not failures else "authority_evaluation_partial",
        evaluation=evaluation,
        persisted=persisted,
        failures=failures,
        bounded_class_count=len(INITIAL_PREAUTHORIZED_CLASSES),
        runtime_authority_changed=False,
    )


def load_canonical_evidence(*, database_url: str | None = None, limit: int = 500):
    """Load bounded, exactly linked learning/delivery evidence without content."""
    database_url = _database_url(database_url)
    limit = max(1, min(int(limit), 500))
    if not database_url:
        return _result("authority_database_unavailable", events=[]), 503
    try:
        import psycopg
        with psycopg.connect(
            database_url, connect_timeout=5,
            options="-c default_transaction_read_only=on -c statement_timeout=8000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select learning_event_id, chatwoot_conversation_id,
                           captured_facts_json, created_at
                    from public.meat_sales_conversation_learning_events
                    where source_agent = 'sam_live_stock_backend'
                      and captured_facts_json->>'learning_kind' = 'owner_reply_capture'
                    order by created_at desc, learning_event_id desc
                    limit %s
                    """,
                    (limit,),
                )
                learning = cursor.fetchall()
                cursor.execute(
                    """
                    select review_event_id, chatwoot_conversation_id,
                           event_source, review_json, created_at
                    from public.current_actionable_sam_live_stock_review_events
                    where event_source in (
                        'sam_outbound_delivery_attempt_claim',
                        'sam_outbound_delivery_transition'
                    )
                    order by created_at desc
                    limit %s
                    """,
                    (limit * 4,),
                )
                delivery = cursor.fetchall()
    except Exception as exc:
        return _result(
            "authority_evidence_unavailable", events=[],
            error_type=exc.__class__.__name__,
        ), 503
    events = pair_canonical_evidence(
        [
            {
                "learning_event_id": event_id,
                "conversation_id": conversation_id,
                "captured_facts": facts,
                "created_at": created_at,
            }
            for event_id, conversation_id, facts, created_at in learning
        ],
        [
            {
                "review_event_id": event_id,
                "conversation_id": conversation_id,
                "event_source": event_source,
                "review_json": facts,
                "created_at": created_at,
            }
            for event_id, conversation_id, event_source, facts, created_at in delivery
        ],
    )
    return _result(
        "authority_evidence_loaded", events=events,
        bounded_limit=limit, delivery_row_limit=limit * 4,
    ), 200


def pair_canonical_evidence(
    learning_rows: Iterable[Mapping[str, Any]],
    delivery_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Pair exact conversation/review/class/durable-attempt evidence."""
    claims = set()
    terminal: dict[tuple[str, str, str, str], set[str]] = {}
    for raw_row in delivery_rows:
        row = dict(raw_row or {})
        facts = _mapping(row.get("review_json"))
        identity = (
            str(facts.get("delivery_attempt_id") or "").strip(),
            str(row.get("conversation_id") or facts.get("conversation_id") or "").strip(),
            str(facts.get("review_id") or facts.get("inbound_review_event_id") or "").strip(),
            _clean_class(facts.get("response_class")),
        )
        if not all(identity):
            continue
        source = str(row.get("event_source") or "").strip()
        if source == "sam_outbound_delivery_attempt_claim":
            claims.add(identity)
        elif source == "sam_outbound_delivery_transition":
            state = str(facts.get("delivery_state") or "").strip()
            if state in {
                "provider_delivered", "provider_read", "provider_failed",
                "provider_outcome_ambiguous",
            }:
                terminal.setdefault(identity, set()).add(state)
    events = []
    for raw_row in learning_rows:
        row = dict(raw_row or {})
        facts = _mapping(row.get("captured_facts"))
        response_class = _clean_class(
            facts.get("response_class") or facts.get("reply_class")
        )
        response_class = LEARNING_CLASS_ALIASES.get(response_class, response_class)
        if response_class not in RESPONSE_CLASS_POLICY_CLASSES:
            continue
        classification = str(facts.get("owner_reply_classification") or "")
        review_id = str(
            facts.get("review_event_id")
            or facts.get("inbound_review_event_id")
            or ""
        ).strip()
        conversation_id = str(
            row.get("conversation_id") or facts.get("conversation_id") or ""
        ).strip()
        matches = [
            states
            for identity, states in terminal.items()
            if identity in claims
            and identity[1:] == (conversation_id, review_id, response_class)
        ]
        states = matches[0] if len(matches) == 1 else set()
        created_at = row.get("created_at")
        events.append({
            "evidence_event_id": str(row.get("learning_event_id") or ""),
            "response_class": response_class,
            "observed_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or ""),
            "owner_approved": classification in {"approved_verbatim", "owner_edited"},
            "owner_rejected": classification in {"owner_replaced", "owner_reply_no_sam_draft"},
            "provider_confirmed": bool(states & {"provider_delivered", "provider_read"}),
            "delivery_failure": "provider_failed" in states,
            "delivery_ambiguous": "provider_outcome_ambiguous" in states,
            "wrong_lane": facts.get("wrong_lane") is True,
            "unsupported_claim": facts.get("unsupported_claim") is True,
            "duplicate_or_retry": facts.get("duplicate_or_retry") is True,
            "delivery_linkage_available": len(matches) == 1,
            "contains_customer_content": False,
        })
    return events


def run_bounded_authority_evaluation(
    *, database_url: str | None = None, now: datetime | None = None
):
    loaded, status = load_canonical_evidence(database_url=database_url)
    if status >= 400:
        return loaded, status
    result = evaluate_and_persist_candidates(
        loaded.get("events", []), database_url=database_url, now=now
    )
    return result, 200 if not result.get("failures") else 503


def append_authority_decision(
    response_class: str,
    decision: str,
    *,
    actor_type: str,
    actor_id: str,
    reason: str,
    authorized_envelope: Mapping[str, Any] | None = None,
    database_url: str | None = None,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
):
    loaded, status = list_latest_authority_events(database_url=database_url)
    if status >= 400:
        return loaded, status
    prior = next(
        (row for row in loaded.get("events", []) if row.get("response_class") == _clean_class(response_class)),
        {},
    )
    required_prior = {"canary_authorized": "candidate", "promoted": "canary_authorized"}
    if decision in required_prior and prior.get("decision") != required_prior[decision]:
        return _result("authority_prior_state_invalid"), 409
    if decision == "paused" and prior.get("decision") not in {"canary_authorized", "promoted"}:
        return _result("authority_prior_state_invalid"), 409
    evaluation = {
        "evidence": dict(prior.get("evidence") or {}),
        "gates": {key: True for key in (
            "sample_count", "owner_approval", "provider_delivery", "wrong_lane",
            "unsupported_claim", "duplicate_retry", "delivery_ambiguity",
            "failure_streak", "freshness", "bounded_window",
        )},
    }
    try:
        event = build_authority_event(
            response_class, decision, evaluation, actor_type=actor_type,
            actor_id=actor_id, reason=reason, prior_event=prior,
            authorized_envelope=authorized_envelope or prior.get("authorized_envelope") or {},
            environ=environ, now=now,
        )
    except (TypeError, ValueError) as exc:
        return _result(str(exc)), 400
    return record_authority_event(event, database_url=database_url)


def resolve_runtime_authority(
    response_class: str,
    *,
    current_message_class: str,
    delivery_rail_available: bool,
    latest_event: Mapping[str, Any] | None = None,
    event_loader: Callable[[], tuple[dict[str, Any], int]] | None = None,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    response_class = _clean_class(response_class)
    current_message_class = _clean_class(current_message_class)
    source = environ if environ is not None else os.environ
    now = _aware(now or datetime.now(timezone.utc))
    blockers = []
    if not _truthy(source.get(CONTROLLER_ENABLED_ENV)):
        blockers.append("controller_disabled")
    if response_class not in INITIAL_PREAUTHORIZED_CLASSES:
        blockers.append("class_outside_authorized_envelope")
    if current_message_class != response_class:
        blockers.append("current_message_class_mismatch")
    if not delivery_rail_available:
        blockers.append("durable_delivery_rail_unavailable")
    if not _truthy(source.get(GLOBAL_KILL_SWITCH_ENV)):
        blockers.append("global_kill_switch_not_clear")
    if not _truthy(source.get(class_switch_env(response_class))):
        blockers.append("class_kill_switch_not_clear")
    event = dict(latest_event or {})
    if not event and event_loader is not None:
        loaded, status = event_loader()
        if status < 400:
            event = next(
                (
                    row for row in loaded.get("events", [])
                    if row.get("response_class") == response_class
                ),
                {},
            )
    if not event:
        blockers.append("persistent_authority_unavailable")
    elif event.get("decision") not in OPERATING_STATES:
        blockers.append("persistent_state_not_promoted")
    else:
        expires_at = _parse_time(event.get("expires_at"))
        if expires_at is None or expires_at <= now:
            blockers.append("authority_expired")
        envelope = event.get("authorized_envelope")
        if not isinstance(envelope, dict) or response_class not in envelope.get("response_classes", []):
            blockers.append("persistent_envelope_mismatch")
    return _result(
        "runtime_authority_allowed" if not blockers else "runtime_authority_withheld",
        allowed=not blockers,
        response_class=response_class,
        blockers=blockers,
        authority_event_id=event.get("authority_event_id", ""),
        automatic_send_authorized=not blockers,
    )


def authority_visibility_report(
    evidence_events: Iterable[Mapping[str, Any]],
    *,
    latest_events: Iterable[Mapping[str, Any]] = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    evaluation = evaluate_response_class_graduation(evidence_events, now=now)
    latest = {
        row.get("response_class"): dict(row)
        for row in latest_events if isinstance(row, Mapping)
    }
    classes = {}
    for response_class in INITIAL_PREAUTHORIZED_CLASSES:
        row = evaluation["classes"][response_class]
        state = latest.get(response_class, {})
        blockers = [
            key for key, passed in row.get("gates", {}).items() if passed is not True
        ]
        classes[response_class] = {
            "evidence": row["evidence"],
            "qualification": row["decision"],
            "authority_state": state.get("decision", "unavailable"),
            "authority_event_id": state.get("authority_event_id", ""),
            "blockers": blockers,
            "next_step": (
                "owner_canary_authorization"
                if row["decision"] == "candidate"
                else f"collect_or_correct:{blockers[0]}"
                if blockers else "none"
            ),
        }
    return _result(
        "authority_visibility_ready",
        evaluator_version=EVALUATOR_VERSION,
        classes=classes,
        charlie={
            "read_sanitized_evidence": True,
            "may_append_pause": True,
            "may_promote": False,
            "may_send_customer_message": False,
            "may_mutate_business_state": False,
        },
        runtime_authority_changed=False,
    )


def _validated_envelope(response_class: str, envelope: Mapping[str, Any]) -> dict[str, Any]:
    envelope = dict(envelope or {})
    classes = sorted({_clean_class(value) for value in envelope.get("response_classes", [])})
    if not classes:
        return {}
    if any(value not in INITIAL_PREAUTHORIZED_CLASSES for value in classes):
        raise ValueError("envelope_contains_excluded_class")
    if response_class not in classes:
        raise ValueError("response_class_not_in_envelope")
    return {
        "version": str(envelope.get("version") or "sam_low_risk_envelope_v1"),
        "response_classes": classes,
        "claim_free_only": True,
        "consequential_actions": False,
    }


def _validate_persisted_event(event: Mapping[str, Any]) -> str:
    required = (
        "authority_event_id", "response_class", "evidence_window_id",
        "evidence_window_hash", "evaluator_version", "decision", "actor_type",
        "actor_id", "reason", "effective_at", "expires_at",
    )
    if any(not event.get(key) for key in required):
        return "authority_event_incomplete"
    if event.get("decision") not in ALLOWED_DECISIONS:
        return "authority_decision_invalid"
    if event.get("contains_customer_content") is not False:
        return "customer_content_prohibited"
    if event.get("sends_customer_message") or event.get("mutates_business_state"):
        return "authority_event_has_prohibited_effect"
    return ""


def _event_row(row) -> dict[str, Any]:
    keys = (
        "authority_event_id", "response_class", "evidence_window_id",
        "evidence_window_hash", "evaluator_version", "decision",
        "prior_event_id", "authorized_envelope", "actor_type", "actor_id",
        "reason", "evidence", "blockers", "global_kill_switch_clear",
        "class_kill_switch_clear", "created_at", "effective_at", "expires_at",
    )
    result = dict(zip(keys, row))
    for key in ("created_at", "effective_at", "expires_at"):
        if hasattr(result.get(key), "isoformat"):
            result[key] = result[key].isoformat()
    return result


def _json_safe(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return json.loads(encoded)


def _database_url(value):
    return str(value if value is not None else os.getenv(DATABASE_URL_ENV, "")).strip()


def _clean_class(value):
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")[:80]


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return _aware(parsed)
    except (TypeError, ValueError):
        return None


def _result(status: str, **extra):
    return {
        "success": not status.endswith(("failed", "unavailable")),
        "status": status,
        "append_only": True,
        "contains_customer_content": False,
        **AUTHORITY_FLAGS,
        **extra,
    }


RESPONSE_CLASS_POLICY_CLASSES = {
    "greeting", "acknowledgement", "thanks", "simple_conversational_closure",
    "simple_small_talk", "one_clarification",
    "referral_post_context_question", "verified_general_factual_answer",
    "livestock_informational_answer", "meat_informational_answer",
    "quote_order_payment_reservation_protected",
}


def _mapping(value):
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return dict(decoded) if isinstance(decoded, Mapping) else {}
        except (TypeError, ValueError):
            return {}
    return {}
