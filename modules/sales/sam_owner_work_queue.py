"""Canonical, no-send SAM owner work queue.

The queue persists chronology evidence, not customer message content.  It is
deliberately independent from Telegram delivery and customer-send authority.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import time
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from typing import Any, Callable, Iterable, Mapping

from services.database_service import DATABASE_URL_ENV
from modules.sales.sam_owner_reply_window import (
    evaluate_reply_window,
    prepare_window_alert,
)


WORK_TABLE = "sam_owner_work_item_events"
REPORT_TABLE = "sam_owner_backlog_report_events"
ALERT_TABLE = "sam_owner_window_alert_events"
MAX_CONVERSATIONS = 100
MAX_MESSAGES_PER_CONVERSATION = 100
MAX_MESSAGE_PAGES = 5
MESSAGE_PAGE_SIZE = 20
MESSAGE_REQUEST_TIMEOUT_SECONDS = 8
OWNER_INVENTORY_REQUEST_TIMEOUT_SECONDS = 8
MAX_INVENTORY_PAGES = 100
MAX_INVENTORY_ROWS = 2500
INVENTORY_TOTAL_DEADLINE_SECONDS = 360
MAX_RECONCILIATION_BATCH = 25
SUPPORTED_OWNERSHIP_MODES = {"HUMAN", "AUTO_GENERAL", "AUTO_SPECIALIST"}
AGENT_OWNERSHIP_MODES = {"AUTO_GENERAL", "AUTO_SPECIALIST"}
OWNER_ATTENTION_POLICY_REASONS = {
    "explicit_human_request", "protected_policy", "specialist_policy",
    "delivery_exception_policy",
}
PROTECTED_MARKERS = {
    "payment", "order", "reservation", "complaint", "delivery_failure",
    "welfare", "safety", "protected_action",
}
SPECIALIST_MARKERS = {
    "sam_meat", "meat_sales", "livestock_specialist", "herdmaster",
    "pricing_review", "specialist_review",
}
AUTHORITY_FLAGS = {
    "sends_customer_message": False,
    "changes_conversation_ownership": False,
    "calls_telegram": False,
    "creates_order": False,
    "creates_quote": False,
    "reserves_stock": False,
    "changes_stock": False,
    "writes_farm_data": False,
    "mutates_business_state": False,
}


class OwnerWorkEvidenceError(ValueError):
    pass


def build_owner_work_observation(
    conversation: Mapping[str, Any],
    *,
    review: Mapping[str, Any] | None = None,
    observed_at: datetime | None = None,
    reconciliation_actor_id: str,
) -> dict[str, Any]:
    """Build one canonical observation from authoritative conversation evidence."""
    conversation = _mapping(conversation, "conversation")
    observed_at = _aware(observed_at or datetime.now(timezone.utc))
    reconciliation_actor_id = _clean(reconciliation_actor_id, 200)
    if not reconciliation_actor_id:
        raise OwnerWorkEvidenceError("server_derived_owner_principal_required")
    identity = _conversation_identity(conversation)
    raw_messages = conversation.get("messages")
    if not isinstance(raw_messages, list):
        raise OwnerWorkEvidenceError("messages_unavailable")
    if len(raw_messages) > MAX_MESSAGES_PER_CONVERSATION:
        raise OwnerWorkEvidenceError("message_bound_exceeded")

    messages = [_message(row, identity) for row in raw_messages]
    messages = [row for row in messages if row is not None]
    messages.sort(key=lambda row: (row["created_at"], _numeric_sort(row["message_id"])))
    public = [row for row in messages if row["public"]]
    inbound = [row for row in public if row["direction"] == "incoming"]
    outgoing = [row for row in public if row["direction"] == "outgoing"]
    latest_inbound = inbound[-1] if inbound else None
    latest_outgoing = outgoing[-1] if outgoing else None
    last_answer_index = max(
        (index for index, row in enumerate(public) if row["direction"] == "outgoing"),
        default=-1,
    )
    unanswered = [
        row for index, row in enumerate(public)
        if index > last_answer_index and row["direction"] == "incoming"
    ]

    review = dict(review or {})
    review_identity = _clean(review.get("chatwoot_conversation_id"))
    if review_identity and review_identity != identity["conversation_id"]:
        raise OwnerWorkEvidenceError("review_conversation_mismatch")
    latest_reviewed_inbound = _clean(review.get("chatwoot_message_id"))
    if latest_reviewed_inbound and latest_reviewed_inbound not in {
        row["message_id"] for row in inbound
    }:
        raise OwnerWorkEvidenceError("reviewed_inbound_missing")

    markers = _authoritative_markers(conversation, review)
    protected = sorted(markers & PROTECTED_MARKERS)
    specialist = sorted(markers & SPECIALIST_MARKERS)
    ownership = _ownership_evidence(conversation)
    ownership_mode = ownership["normalized_mode"]
    attrs = conversation.get("custom_attributes")
    attrs = attrs if isinstance(attrs, Mapping) else {}
    suspicious_evidence = attrs.get("sam_security_suspicious_link")
    suspicious_evidence = suspicious_evidence if isinstance(suspicious_evidence, bool) else None
    window = evaluate_reply_window(
        raw_messages,
        conversation_identity={
            **identity,
            "channel": conversation.get("channel"),
            "channel_type": conversation.get("channel_type"),
            "inbox": conversation.get("inbox"),
        },
        suspicious_link_evidence=suspicious_evidence,
        now=observed_at,
    )
    withheld = []
    classification = "WAITING_FOR_OWNER_REPLY"
    lane = "GENERAL"
    actionable = bool(unanswered)
    missed_classification = (
        "multiple_unanswered_inbounds" if len(unanswered) > 1
        else "single_unanswered_inbound" if unanswered
        else "handled_by_later_public_owner_reply"
    )
    ownership_exception = ownership["decision_required"]
    if ownership_exception:
        withheld.append(ownership["reason"])
        classification = "OWNERSHIP_DECISION_REQUIRED"
        missed_classification = "ownership_decision_required"
        actionable = bool(unanswered)
    elif ownership_mode != "HUMAN":
        withheld.append("human_ownership_not_authoritative")
        classification = "IDENTITY_OR_EVIDENCE_UNAVAILABLE"
        actionable = False
    if not inbound:
        withheld.append("no_public_inbound")
        classification = "IDENTITY_OR_EVIDENCE_UNAVAILABLE"
        actionable = False
    elif not unanswered:
        classification = "CUSTOMER_ALREADY_HANDLED"
        actionable = False
    if protected and not ownership_exception:
        classification = "PROTECTED_ACTION_REQUIRED"
        lane = "PROTECTED"
        withheld.append("protected_work_requires_owner")
        actionable = True
        missed_classification = "protected_owner_work"
    elif specialist and not ownership_exception:
        classification = "SPECIALIST_REVIEW_REQUIRED"
        lane = "SPECIALIST"
        withheld.append("specialist_work_separated")
        actionable = True
        missed_classification = "specialist_owner_work"
    if actionable and not review:
        withheld.append("current_review_unavailable")
    if latest_reviewed_inbound and latest_inbound:
        if latest_reviewed_inbound != latest_inbound["message_id"]:
            withheld.append("review_stale_for_latest_inbound")
    if window["window_state"] == "unavailable" and not ownership_exception:
        classification = "IDENTITY_OR_EVIDENCE_UNAVAILABLE"
        actionable = False
        withheld.append(window["reason"])
    elif window["window_state"] == "unavailable":
        withheld.append(window["reason"])
    elif window["window_state"] == "expired" and not ownership_exception:
        classification = "CUSTOMER_REPLY_PROHIBITED"
        actionable = False
        withheld.extend(["provider_reply_window_expired", "customer_reply_prohibited"])
    elif window["window_state"] == "expired":
        withheld.extend(["provider_reply_window_expired", "customer_reply_prohibited"])
    elif window["reply_authority_state"] == "customer_reply_prohibited" and not ownership_exception:
        classification = "CUSTOMER_REPLY_PROHIBITED"
        actionable = False
        withheld.extend([window["reason"], "customer_reply_prohibited"])
    elif window["reply_authority_state"] == "customer_reply_prohibited":
        withheld.extend([window["reason"], "customer_reply_prohibited"])
    if ownership_exception:
        window = {
            **window,
            "provider_reply_authority_state": window["reply_authority_state"],
            "reply_authority_state": "ownership_decision_required",
            "ordinary_reply_allowed": False,
            "send_reply_action_visible": False,
            "template_required": False,
        }

    chronology = [
        {
            "message_id": row["message_id"],
            "direction": row["direction"],
            "created_at": row["created_at"],
        }
        for row in public
    ]
    chronology_hash = _digest({
        **identity,
        "chronology": chronology,
        "ownership_mode": ownership_mode,
        "ownership_evidence_state": ownership["state"],
        "ownership_decision_required": ownership_exception,
    })
    work_item_id = f"SAM-OWNER-WORK-{_digest(identity)[:24]}"
    event_type = "actionable" if actionable else "withheld"
    observation_hash = _digest({
        'work_item_id': work_item_id,
        'chronology_hash': chronology_hash,
        'classification': classification,
        'lane': lane,
        'actionable': actionable,
        'withheld': sorted(withheld),
        'review_event_id': _clean(review.get("review_event_id")),
        'reviewed_inbound_message_id': latest_reviewed_inbound,
        'window_evidence_hash': window["window_evidence_hash"],
    })
    event_id = f"SAM-OWNER-WORK-EVENT-{observation_hash[:24]}"
    observation = {
        "work_event_id": event_id,
        "work_item_id": work_item_id,
        **identity,
        "ownership_mode": ownership_mode,
        "ownership_evidence_state": ownership["state"],
        "ownership_decision_required": ownership_exception,
        "latest_message_id": public[-1]["message_id"] if public else "",
        "latest_message_at": public[-1]["created_at"] if public else None,
        "latest_inbound_message_id": latest_inbound["message_id"] if latest_inbound else "",
        "latest_outgoing_message_id": latest_outgoing["message_id"] if latest_outgoing else "",
        "chronology_hash": chronology_hash,
        "observation_hash": observation_hash,
        "unanswered_inbound_bundle": [
            {"sequence": index + 1, **row}
            for index, row in enumerate(unanswered)
        ],
        "unanswered_count": len(unanswered),
        "classification": classification,
        "missed_message_classification": missed_classification,
        "lane": lane,
        "actionable": actionable,
        "withheld_reasons": sorted(set(withheld)),
        "review_event_id": _clean(review.get("review_event_id")),
        "reviewed_inbound_message_id": latest_reviewed_inbound,
        "protected_markers": protected,
        "specialist_markers": specialist,
        "event_type": event_type,
        "source": "bounded_owner_attention_reconciliation_v1",
        "reconciliation_actor_id": reconciliation_actor_id,
        "reply_window": window,
        "window_state": window["window_state"],
        "reply_authority_state": window["reply_authority_state"],
        "window_reason": window["reason"],
        "provider_identity_class": window["provider_identity_class"],
        "window_evidence_hash": window["window_evidence_hash"],
        "expires_at_utc": window["expires_at_utc"],
        "expires_at_johannesburg": window["expires_at_johannesburg"],
        "remaining_seconds": window["remaining_seconds"],
        "warning_threshold_hours": window["warning_threshold_hours"],
        "urgent_threshold_hours": window["urgent_threshold_hours"],
        "alert_band": window["alert_band"],
        "ordinary_reply_allowed": window["ordinary_reply_allowed"],
        "send_reply_action_visible": window["send_reply_action_visible"],
        "template_required": window["template_required"],
        "observed_at": observed_at.isoformat(),
        "contains_customer_content": False,
        **AUTHORITY_FLAGS,
    }
    observation["prepared_window_alert"] = prepare_window_alert(
        work_item_id, observation_hash, window, prepared_at=observed_at
    )
    return observation


def record_owner_work_observation(
    observation: Mapping[str, Any], *, database_url: str | None = None
) -> tuple[dict[str, Any], int]:
    observation = dict(observation or {})
    error = _validate_observation(observation)
    if error:
        return _result(error), 400
    database_url = _database_url(database_url)
    if not database_url:
        return _result("owner_work_database_unavailable"), 503
    try:
        import psycopg
        with psycopg.connect(
            database_url, connect_timeout=5,
            options="-c statement_timeout=8000 -c lock_timeout=2000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select work_event_id
                    from public.{WORK_TABLE}
                    where work_item_id=%s
                    order by observed_at desc, created_at desc, work_event_id desc
                    limit 1
                    """,
                    (observation["work_item_id"],),
                )
                prior = cursor.fetchone()
                cursor.execute(
                    f"""
                    insert into public.{WORK_TABLE} (
                      work_event_id, work_item_id, account_id, conversation_id,
                      contact_id, inbox_id, ownership_mode, latest_message_id,
                      latest_message_at, latest_inbound_message_id,
                      latest_outgoing_message_id, chronology_hash,
                      observation_hash,
                      unanswered_inbound_bundle_json, unanswered_count,
                      classification, missed_message_classification, lane,
                      actionable, withheld_reasons_json, review_event_id,
                      reviewed_inbound_message_id, protected_markers_json,
                      specialist_markers_json, event_type, source,
                      reconciliation_actor_id,
                      window_state, reply_authority_state, window_reason,
                      provider_identity_class, window_evidence_hash,
                      expires_at_utc, expires_at_johannesburg,
                      remaining_seconds, warning_threshold_hours,
                      urgent_threshold_hours, alert_band,
                      ordinary_reply_allowed, send_reply_action_visible,
                      template_required,
                      prior_event_id, observed_at, contains_customer_content,
                      sends_customer_message, changes_conversation_ownership,
                      calls_telegram, mutates_business_state
                    ) values (
                      %(work_event_id)s, %(work_item_id)s, %(account_id)s,
                      %(conversation_id)s, %(contact_id)s, %(inbox_id)s,
                      %(ownership_mode)s, %(latest_message_id)s,
                      %(latest_message_at)s::timestamptz,
                      %(latest_inbound_message_id)s,
                      %(latest_outgoing_message_id)s, %(chronology_hash)s,
                      %(observation_hash)s,
                      %(unanswered_inbound_bundle)s::jsonb, %(unanswered_count)s,
                      %(classification)s, %(missed_message_classification)s,
                      %(lane)s, %(actionable)s, %(withheld_reasons)s::jsonb,
                      %(review_event_id)s, %(reviewed_inbound_message_id)s,
                      %(protected_markers)s::jsonb,
                      %(specialist_markers)s::jsonb, %(event_type)s, %(source)s,
                      %(reconciliation_actor_id)s,
                      %(window_state)s, %(reply_authority_state)s,
                      %(window_reason)s, %(provider_identity_class)s,
                      %(window_evidence_hash)s, %(expires_at_utc)s::timestamptz,
                      %(expires_at_johannesburg)s::timestamptz,
                      %(remaining_seconds)s, %(warning_threshold_hours)s,
                      %(urgent_threshold_hours)s, %(alert_band)s,
                      %(ordinary_reply_allowed)s, %(send_reply_action_visible)s,
                      %(template_required)s,
                      %(prior_event_id)s, %(observed_at)s::timestamptz,
                      false, false, false, false, false
                    )
                    on conflict (work_event_id) do nothing
                    returning work_event_id
                    """,
                    {
                        **observation,
                        "latest_message_at": observation.get("latest_message_at"),
                        "unanswered_inbound_bundle": json.dumps(
                            observation["unanswered_inbound_bundle"],
                            sort_keys=True, separators=(",", ":"),
                        ),
                        "withheld_reasons": json.dumps(observation["withheld_reasons"]),
                        "protected_markers": json.dumps(observation["protected_markers"]),
                        "specialist_markers": json.dumps(observation["specialist_markers"]),
                        "prior_event_id": prior[0] if prior else None,
                    },
                )
                created = cursor.fetchone()
                alert_created = None
                alert = observation.get("prepared_window_alert")
                if created and isinstance(alert, Mapping):
                    cursor.execute(
                        f"""
                        insert into public.{ALERT_TABLE} (
                          alert_event_id,alert_deduplication_hash,work_item_id,
                          observation_hash,conversation_id,contact_id,inbox_id,
                          window_contract_version,window_state,
                          reply_authority_state,alert_band,expires_at_utc,reason,
                          prepared_at,delivery_enabled,delivered,
                          contains_customer_content,sends_customer_message,
                          changes_conversation_ownership,calls_telegram,
                          uses_template,mutates_business_state
                        ) values (
                          %(alert_event_id)s,%(alert_deduplication_hash)s,
                          %(work_item_id)s,%(observation_hash)s,
                          %(conversation_id)s,%(contact_id)s,%(inbox_id)s,
                          %(window_contract_version)s,%(window_state)s,
                          %(reply_authority_state)s,%(alert_band)s,
                          %(expires_at_utc)s::timestamptz,%(reason)s,
                          %(prepared_at)s::timestamptz,false,false,false,
                          false,false,false,false,false
                        )
                        on conflict (alert_event_id) do nothing
                        returning alert_event_id
                        """,
                        alert,
                    )
                    alert_created = cursor.fetchone()
            connection.commit()
        return _result(
            "owner_work_observation_recorded" if created else "owner_work_observation_replay_withheld",
            created=bool(created), work_event_id=observation["work_event_id"],
            work_item_id=observation["work_item_id"],
            alert_prepared=bool(alert_created),
            alert_event_id=(
                observation.get("prepared_window_alert", {}).get("alert_event_id")
                if isinstance(observation.get("prepared_window_alert"), Mapping)
                else None
            ),
        ), 201 if created else 200
    except Exception as exc:
        return _result(
            "owner_work_observation_persistence_failed",
            error_type=exc.__class__.__name__,
        ), 503


def reconcile_human_backlog(
    conversations: Iterable[Mapping[str, Any]],
    *,
    review_by_conversation: Mapping[str, Mapping[str, Any]] | None = None,
    recorder: Callable[[Mapping[str, Any]], tuple[dict[str, Any], int]] | None = None,
    observed_at: datetime | None = None,
    reconciliation_actor_id: str,
) -> tuple[dict[str, Any], int]:
    """Bounded injected reconciliation; callers own authoritative reads."""
    rows = list(conversations or [])
    if len(rows) > MAX_CONVERSATIONS:
        return _result("owner_work_conversation_bound_exceeded"), 400
    review_by_conversation = dict(review_by_conversation or {})
    recorder = recorder or record_owner_work_observation
    observations = []
    failures = []
    created = 0
    for index, conversation in enumerate(rows):
        conversation_id = _clean(
            conversation.get("id") if isinstance(conversation, Mapping) else ""
        )
        try:
            observation = build_owner_work_observation(
                conversation,
                review=review_by_conversation.get(conversation_id),
                observed_at=observed_at,
                reconciliation_actor_id=reconciliation_actor_id,
            )
            result, status = recorder(observation)
            if status >= 400:
                failures.append({
                    "conversation_id": conversation_id,
                    "reason": result.get("status", "persistence_failed"),
                })
                continue
            created += int(result.get("created") is True)
            observations.append(observation)
        except OwnerWorkEvidenceError as exc:
            failures.append({
                "conversation_id": conversation_id,
                "reason": str(exc),
                "item_index": index,
            })
    counts = _classification_counts(observations)
    status = "owner_work_reconciliation_completed" if not failures else "owner_work_reconciliation_withheld"
    return _result(
        status, observations=observations, failures=failures,
        observed_count=len(observations), created_count=created,
        counts=counts, evidence_complete=not failures,
    ), 200 if not failures else 409


def load_latest_owner_work_event(
    conversation_id: str, *, database_url: str | None = None
) -> tuple[dict[str, Any], int]:
    conversation_id = _clean(conversation_id)
    database_url = _database_url(database_url)
    if not conversation_id or not database_url:
        return _result("owner_work_prior_state_unavailable", found=False), 503
    try:
        import psycopg
        with psycopg.connect(
            database_url, connect_timeout=3,
            options="-c statement_timeout=3000 -c lock_timeout=1000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select account_id, conversation_id, contact_id, inbox_id,
                           ownership_mode, unanswered_inbound_bundle_json,
                           review_event_id
                    from public.{WORK_TABLE}
                    where conversation_id=%s
                    order by observed_at desc, created_at desc, work_event_id desc
                    limit 1
                    """,
                    (conversation_id,),
                )
                row = cursor.fetchone()
    except Exception as exc:
        return _result(
            "owner_work_prior_state_unavailable",
            found=False,
            error_type=exc.__class__.__name__,
        ), 503
    if not row:
        return _result("owner_work_prior_state_not_found", found=False), 200
    return _result(
        "owner_work_prior_state_loaded",
        found=True,
        state={
            "account_id": _clean(row[0]),
            "conversation_id": _clean(row[1]),
            "contact_id": _clean(row[2]),
            "inbox_id": _clean(row[3]),
            "ownership_mode": _clean(row[4]),
            "unanswered_inbound_bundle": _json_value(row[5], []),
            "review_event_id": _clean(row[6]),
        },
    ), 200


def observe_owner_work_message_event(
    inbound: Mapping[str, Any],
    review: Mapping[str, Any],
    raw_payload: Mapping[str, Any],
    *,
    direction: str = "incoming",
    reconciliation_actor_id: str,
    recorder: Callable[[Mapping[str, Any]], tuple[dict[str, Any], int]] | None = None,
    state_loader: Callable[[str], tuple[dict[str, Any], int]] | None = None,
) -> tuple[dict[str, Any], int]:
    """Merge one webhook message into sanitized canonical work state."""
    inbound = inbound if isinstance(inbound, Mapping) else {}
    review = review if isinstance(review, Mapping) else {}
    raw_payload = raw_payload if isinstance(raw_payload, Mapping) else {}
    identity = {
        key: _clean(inbound.get(key))
        for key in ("account_id", "conversation_id", "contact_id", "inbox_id")
    }
    provenance = inbound.get("identity_provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    conflicts = provenance.get("conflicts")
    conflicts = conflicts if isinstance(conflicts, Mapping) else {}
    conversation = raw_payload.get("conversation")
    conversation = conversation if isinstance(conversation, Mapping) else {}
    direction = _clean(direction).lower()
    if (
        any(not value for value in identity.values())
        or any(value is True for value in conflicts.values())
        or _clean(conversation.get("status")).lower() != "open"
        or not _clean(inbound.get("message_id"))
        or not _clean(inbound.get("last_inbound_at"))
        or direction not in {"incoming", "outgoing"}
    ):
        return _result(
            "owner_work_webhook_observation_evidence_incomplete",
            evidence_complete=False,
        ), 409
    prior_result, prior_status = (state_loader or load_latest_owner_work_event)(
        identity["conversation_id"]
    )
    if prior_status >= 400:
        return _result(
            "owner_work_webhook_prior_state_unavailable",
            evidence_complete=False,
        ), 503
    prior = prior_result.get("state")
    prior = prior if prior_result.get("found") is True and isinstance(prior, Mapping) else {}
    if direction == "outgoing" and not prior:
        return _result(
            "owner_work_outgoing_prior_state_required",
            evidence_complete=False,
        ), 409
    if prior and any(
        _clean(prior.get(key)) != identity[key]
        for key in ("account_id", "conversation_id", "contact_id", "inbox_id")
    ):
        return _result(
            "owner_work_webhook_prior_identity_conflict",
            evidence_complete=False,
        ), 409
    prior_bundle = prior.get("unanswered_inbound_bundle") if prior else []
    if not isinstance(prior_bundle, list) or not all(
        isinstance(row, Mapping) for row in prior_bundle
    ):
        return _result(
            "owner_work_webhook_prior_state_malformed",
            evidence_complete=False,
        ), 409
    messages = [
        {
            "id": row.get("message_id"),
            "message_type": 0,
            "created_at": row.get("created_at"),
            "private": False,
            "conversation_id": identity["conversation_id"],
        }
        for row in prior_bundle
    ]
    messages.append({
        "id": inbound["message_id"],
        "message_type": 0 if direction == "incoming" else 1,
        "created_at": inbound["last_inbound_at"],
        "private": False,
        "conversation_id": identity["conversation_id"],
    })
    ownership_mode = _clean(prior.get("ownership_mode")) if prior else ""
    custom_attributes = (
        {"conversation_mode": ownership_mode}
        if ownership_mode in SUPPORTED_OWNERSHIP_MODES
        else inbound.get("conversation_custom_attributes")
    )
    try:
        observation = build_owner_work_observation(
            {
                "account_id": identity["account_id"],
                "id": identity["conversation_id"],
                "contact_id": identity["contact_id"],
                "inbox_id": identity["inbox_id"],
                "status": "open",
                "channel": inbound.get("channel"),
                "custom_attributes": custom_attributes,
                "labels": conversation.get("labels") or [],
                "messages": messages,
            },
            review=review,
            reconciliation_actor_id=reconciliation_actor_id,
        )
    except OwnerWorkEvidenceError as exc:
        return _result(
            "owner_work_webhook_observation_evidence_incomplete",
            failure_reason=str(exc)[:120],
            evidence_complete=False,
        ), 409
    try:
        persisted, status_code = (recorder or record_owner_work_observation)(
            observation
        )
    except Exception as exc:
        return _result(
            "owner_work_webhook_observation_persistence_failed",
            error_type=exc.__class__.__name__,
            evidence_complete=False,
        ), 503
    return _result(
        persisted.get("status", "owner_work_webhook_observation_persistence_failed"),
        created=persisted.get("created") is True,
        created_count=int(persisted.get("created") is True),
        work_item_id=observation.get("work_item_id"),
        work_event_id=observation.get("work_event_id"),
        evidence_complete=persisted.get("success") is True,
    ), status_code


def reconcile_live_human_conversation(
    conversation_id: str,
    *,
    reconciliation_actor_id: str,
    environ: Mapping[str, str] | None = None,
    message_reader: Callable[[str, Mapping[str, str]], tuple[dict[str, Any], int]] | None = None,
) -> tuple[dict[str, Any], int]:
    """Run one bounded authoritative owner-attention read and evidence append."""
    from modules.sales.sam_live_stock_launch_control import (
        load_latest_sam_live_stock_review_events_for_conversations,
    )

    source = environ if environ is not None else os.environ
    conversation_id = _clean(conversation_id)
    if not conversation_id:
        return _result("owner_work_conversation_id_required"), 400
    if not _clean(reconciliation_actor_id, 200):
        return _result("server_derived_owner_principal_required"), 403
    try:
        conversations = load_bounded_owner_attention_conversations(
            conversation_id, source
        )
    except Exception as exc:
        return _result(
            "owner_work_chatwoot_read_failed", error_type=exc.__class__.__name__
        ), 503
    if not isinstance(conversations, list) or len(conversations) > MAX_CONVERSATIONS:
        return _result("owner_work_conversation_evidence_incomplete"), 503
    exact = [
        row for row in conversations
        if isinstance(row, Mapping) and _clean(row.get("id")) == conversation_id
    ]
    if len(exact) != 1:
        return _result(
            "owner_work_exact_conversation_unavailable",
            exact_match_count=len(exact),
        ), 409
    hydrated = []
    reader = message_reader or load_bounded_conversation_messages
    for row in exact:
        if not isinstance(row, Mapping):
            return _result("owner_work_conversation_evidence_incomplete"), 503
        conversation_id = _clean(row.get("id"))
        history, history_status = reader(conversation_id, source)
        if history_status >= 400 or history.get("evidence_complete") is not True:
            return _result(
                "owner_work_chronology_evidence_unavailable",
                failed_conversation_id=conversation_id,
                failure_reason=history.get("status"),
            ), 503
        hydrated.append({**row, "messages": history["messages"]})
    ids = [_clean(row.get("id")) for row in hydrated]
    reviews, review_status = load_latest_sam_live_stock_review_events_for_conversations(ids)
    if review_status >= 400 or not reviews.get("success"):
        return _result("owner_work_review_evidence_unavailable"), 503
    return reconcile_human_backlog(
        hydrated,
        review_by_conversation=reviews.get("events_by_conversation_id") or {},
        reconciliation_actor_id=reconciliation_actor_id,
    )


def load_bounded_owner_attention_conversations(
    conversation_id: str,
    environ: Mapping[str, str],
    *,
    opener: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """Read one exact open owner-attention conversation without broad scanning."""
    source = environ if environ is not None else os.environ
    base_url = _clean(
        source.get("CHATWOOT_BASE_URL") or "https://app.chatwoot.com", 240
    ).rstrip("/")
    account_id = _clean(source.get("CHATWOOT_ACCOUNT_ID") or "147387")
    inbox_id = _clean(source.get("SAM_LIVE_STOCK_CHATWOOT_INBOX_ID"))
    token = _clean(
        source.get("CHATWOOT_API_ACCESS_TOKEN") or source.get("CHATWOOT_API_TOKEN"),
        500,
    )
    conversation_id = _clean(conversation_id)
    if not base_url or not account_id or not inbox_id or not token or not conversation_id:
        raise OwnerWorkEvidenceError("owner_attention_inventory_not_configured")
    if not inbox_id.isdigit():
        raise OwnerWorkEvidenceError("owner_attention_inventory_inbox_invalid")
    opener = opener or urllib_request.urlopen
    request = urllib_request.Request(
        f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}",
        headers={"api_access_token": token, "Accept": "application/json"},
        method="GET",
    )
    try:
        with opener(
            request, timeout=OWNER_INVENTORY_REQUEST_TIMEOUT_SECONDS
        ) as response:
            if int(response.status) != 200:
                raise OwnerWorkEvidenceError(
                    "owner_attention_inventory_http_unavailable"
                )
            row = json.loads(response.read().decode("utf-8"))
    except OwnerWorkEvidenceError:
        raise
    except (
        urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError,
        ValueError, json.JSONDecodeError,
    ) as exc:
        raise OwnerWorkEvidenceError(
            f"owner_attention_inventory_read_failed:{exc.__class__.__name__}"
        ) from exc
    if not isinstance(row, Mapping):
        raise OwnerWorkEvidenceError("owner_attention_inventory_envelope_malformed")
    if (
        _clean(row.get("id")) != conversation_id
        or _clean(row.get("inbox_id")) != inbox_id
    ):
        raise OwnerWorkEvidenceError("owner_attention_inventory_identity_mismatch")
    if _clean(row.get("status")).lower() != "open":
        raise OwnerWorkEvidenceError("owner_attention_inventory_status_mismatch")
    ownership = _ownership_evidence(row)
    if (
        ownership["normalized_mode"] == "HUMAN"
        or ownership["decision_required"]
        or _explicit_owner_attention_policy(row)
    ):
        return [dict(row)]
    return []


def load_bounded_configured_inbox_inventory(
    environ: Mapping[str, str],
    *,
    opener: Callable[..., Any] | None = None,
    monotonic: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Read the complete configured open inbox or fail without a partial all-clear."""
    source = environ if environ is not None else os.environ
    base_url = _clean(
        source.get("CHATWOOT_BASE_URL") or "https://app.chatwoot.com", 240
    ).rstrip("/")
    account_id = _clean(source.get("CHATWOOT_ACCOUNT_ID") or "147387")
    inbox_id = _clean(source.get("SAM_LIVE_STOCK_CHATWOOT_INBOX_ID"))
    token = _clean(
        source.get("CHATWOOT_API_ACCESS_TOKEN") or source.get("CHATWOOT_API_TOKEN"),
        500,
    )
    if not base_url or not account_id or not inbox_id or not token:
        raise OwnerWorkEvidenceError("owner_inventory_not_configured")
    if not account_id.isdigit() or not inbox_id.isdigit():
        raise OwnerWorkEvidenceError("owner_inventory_identity_invalid")
    opener = opener or urllib_request.urlopen
    monotonic = monotonic or time.monotonic
    started_at = monotonic()
    rows_by_id: dict[str, dict[str, Any]] = {}
    expected_count: int | None = None
    for page_number in range(1, MAX_INVENTORY_PAGES + 1):
        if monotonic() - started_at >= INVENTORY_TOTAL_DEADLINE_SECONDS:
            raise OwnerWorkEvidenceError("owner_inventory_total_deadline_exceeded")
        query = urllib_parse.urlencode({
            "inbox_id": inbox_id,
            "status": "open",
            "page": page_number,
        })
        request = urllib_request.Request(
            f"{base_url}/api/v1/accounts/{account_id}/conversations?{query}",
            headers={"api_access_token": token, "Accept": "application/json"},
            method="GET",
        )
        try:
            with opener(
                request, timeout=OWNER_INVENTORY_REQUEST_TIMEOUT_SECONDS
            ) as response:
                if int(response.status) != 200:
                    raise OwnerWorkEvidenceError("owner_inventory_http_unavailable")
                envelope = json.loads(response.read().decode("utf-8"))
        except OwnerWorkEvidenceError:
            raise
        except (
            urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError,
            ValueError, json.JSONDecodeError,
        ) as exc:
            raise OwnerWorkEvidenceError(
                f"owner_inventory_read_failed:{exc.__class__.__name__}"
            ) from exc
        page, page_count = _conversation_inventory_page(envelope)
        if page is None or page_count is None:
            raise OwnerWorkEvidenceError("owner_inventory_envelope_malformed")
        if expected_count is None:
            expected_count = page_count
            if expected_count > MAX_INVENTORY_ROWS:
                raise OwnerWorkEvidenceError("owner_inventory_row_bound_exceeded")
        elif page_count != expected_count:
            raise OwnerWorkEvidenceError("owner_inventory_count_changed")
        for row in page:
            conversation_id = _clean(row.get("id"))
            row_account = _conversation_account_id(row)
            if (
                not conversation_id
                or not conversation_id.isdigit()
                or _clean(row.get("inbox_id")) != inbox_id
                or (row_account and row_account != account_id)
                or _clean(row.get("status")).lower() != "open"
                or conversation_id in rows_by_id
            ):
                raise OwnerWorkEvidenceError("owner_inventory_identity_conflict")
            rows_by_id[conversation_id] = dict(row)
        if len(rows_by_id) > MAX_INVENTORY_ROWS:
            raise OwnerWorkEvidenceError("owner_inventory_row_bound_exceeded")
        if len(rows_by_id) == expected_count:
            return _result(
                "owner_inventory_complete",
                conversations=list(rows_by_id.values()),
                account_id=account_id,
                inbox_id=inbox_id,
                expected_count=expected_count,
                observed_count=len(rows_by_id),
                pages_read=page_number,
                evidence_complete=True,
            )
        if not page:
            raise OwnerWorkEvidenceError("owner_inventory_pagination_incomplete")
    raise OwnerWorkEvidenceError("owner_inventory_pagination_incomplete")


def reconcile_configured_owner_inventory_batch(
    *,
    reconciliation_actor_id: str,
    cursor_token: str = "",
    limit: int = MAX_RECONCILIATION_BATCH,
    environ: Mapping[str, str] | None = None,
    inventory_reader: Callable[[Mapping[str, str]], Mapping[str, Any]] | None = None,
    conversation_reconciler: Callable[..., tuple[dict[str, Any], int]] | None = None,
) -> tuple[dict[str, Any], int]:
    """Repair one deterministic batch after proving complete inbox coverage."""
    source = environ if environ is not None else os.environ
    actor = _clean(reconciliation_actor_id, 200)
    if not actor:
        return _result("server_derived_owner_principal_required"), 403
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return _result("owner_inventory_batch_limit_invalid"), 400
    if limit < 1 or limit > MAX_RECONCILIATION_BATCH:
        return _result("owner_inventory_batch_limit_invalid"), 400
    cursor_secret = _clean(
        source.get("OWNER_SESSION_SECRET") or source.get("SECRET_KEY"), 500
    )
    if not cursor_secret:
        return _result("owner_inventory_cursor_signing_unavailable"), 503
    try:
        inventory = (inventory_reader or load_bounded_configured_inbox_inventory)(
            source
        )
    except Exception as exc:
        return _result(
            "owner_inventory_reconciliation_coverage_unavailable",
            failure_reason=str(exc)[:160],
            evidence_complete=False,
        ), 503
    rows = inventory.get("conversations")
    if inventory.get("evidence_complete") is not True or not isinstance(rows, list):
        return _result(
            "owner_inventory_reconciliation_coverage_incomplete",
            evidence_complete=False,
        ), 503
    eligible = []
    for row in rows:
        if not isinstance(row, Mapping):
            return _result(
                "owner_inventory_reconciliation_row_malformed",
                evidence_complete=False,
            ), 503
        ownership = _ownership_evidence(row)
        if (
            ownership["normalized_mode"] == "HUMAN"
            or ownership["decision_required"]
            or _explicit_owner_attention_policy(row)
        ):
            eligible.append(dict(row))
    eligible.sort(key=lambda row: int(_clean(row.get("id"))))
    inventory_hash = hashlib.sha256(
        json.dumps(
            [
                {
                    "conversation_id": _clean(row.get("id")),
                    "ownership": _ownership_evidence(row),
                }
                for row in eligible
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    start_index = 0
    if cursor_token:
        cursor = _decode_inventory_cursor(cursor_token, cursor_secret)
        if (
            cursor is None
            or cursor.get("inventory_hash") != inventory_hash
            or not isinstance(cursor.get("next_index"), int)
            or isinstance(cursor.get("next_index"), bool)
            or cursor["next_index"] < 0
            or cursor["next_index"] >= len(eligible)
        ):
            return _result("owner_inventory_batch_cursor_invalid"), 409
        start_index = cursor["next_index"]
    selected = eligible[start_index:start_index + limit]
    reconciler = conversation_reconciler or reconcile_live_human_conversation
    results = []
    failures = []
    for row in selected:
        conversation_id = _clean(row.get("id"))
        result, status_code = reconciler(
            conversation_id,
            reconciliation_actor_id=actor,
            environ=source,
        )
        item = {
            "conversation_id": conversation_id,
            "status": result.get("status"),
            "status_code": status_code,
            "created_count": int(result.get("created_count") or 0),
        }
        results.append(item)
        if status_code >= 400 or result.get("evidence_complete") is not True:
            failures.append(item)
    if failures:
        first_failure_id = _clean(failures[0].get("conversation_id"))
        first_failure_offset = next(
            index for index, row in enumerate(selected)
            if _clean(row.get("id")) == first_failure_id
        )
        next_index = start_index + first_failure_offset
    else:
        next_index = start_index + len(selected)
    remaining = len(eligible) - next_index
    complete = not failures and next_index == len(eligible)
    next_cursor = (
        ""
        if complete
        else _encode_inventory_cursor(
            {
                "version": 1,
                "inventory_hash": inventory_hash,
                "next_index": next_index,
            },
            cursor_secret,
        )
    )
    return _result(
        (
            "owner_inventory_reconciliation_completed"
            if complete
            else "owner_inventory_reconciliation_incomplete"
        ),
        inventory_expected_count=inventory.get("expected_count"),
        inventory_observed_count=inventory.get("observed_count"),
        eligible_count=len(eligible),
        reconciled_count=len(results) - len(failures),
        failures=failures,
        results=results,
        next_cursor=next_cursor,
        remaining_count=remaining,
        evidence_complete=complete,
    ), 200 if complete else 409


def load_bounded_conversation_messages(
    conversation_id: str,
    environ: Mapping[str, str],
    *,
    opener: Callable[..., Any] | None = None,
) -> tuple[dict[str, Any], int]:
    """Read a complete bounded Chatwoot conversation-message chronology."""
    source = environ if environ is not None else os.environ
    base_url = _clean(source.get("CHATWOOT_BASE_URL") or "https://app.chatwoot.com", 240).rstrip("/")
    account_id = _clean(source.get("CHATWOOT_ACCOUNT_ID") or "147387")
    token = _clean(
        source.get("CHATWOOT_API_ACCESS_TOKEN") or source.get("CHATWOOT_API_TOKEN"), 500
    )
    conversation_id = _clean(conversation_id)
    if not base_url or not account_id or not token or not conversation_id:
        return _result("owner_work_chronology_reader_not_configured"), 503
    opener = opener or urllib_request.urlopen
    rows: list[dict[str, Any]] = []
    after = 0
    try:
        for page_number in range(1, MAX_MESSAGE_PAGES + 1):
            query = urllib_parse.urlencode({"after": after})
            request = urllib_request.Request(
                f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages?{query}",
                headers={"api_access_token": token, "Accept": "application/json"},
                method="GET",
            )
            with opener(request, timeout=MESSAGE_REQUEST_TIMEOUT_SECONDS) as response:
                if int(response.status) != 200:
                    return _result("owner_work_chronology_http_unavailable"), 503
                envelope = json.loads(response.read().decode("utf-8"))
            page = _message_list_rows(envelope)
            if page is None:
                return _result("owner_work_chronology_envelope_malformed"), 503
            rows.extend(page)
            if len(rows) > MAX_MESSAGES_PER_CONVERSATION:
                return _result("owner_work_chronology_row_bound_exceeded"), 503
            if not page or len(page) < MESSAGE_PAGE_SIZE:
                return _result(
                    "owner_work_chronology_loaded", messages=rows,
                    pages_read=page_number, rows_read=len(rows),
                    evidence_complete=True,
                ), 200
            ids = []
            for row in page:
                raw_id = row.get("id") or row.get("message_id")
                if isinstance(raw_id, bool) or not str(raw_id or "").isdigit():
                    return _result("owner_work_chronology_cursor_invalid"), 503
                ids.append(int(raw_id))
            cursor = max(ids)
            if cursor <= after:
                return _result("owner_work_chronology_pagination_stalled"), 503
            after = cursor
        return _result(
            "owner_work_chronology_pagination_incomplete",
            pages_read=MAX_MESSAGE_PAGES, rows_read=len(rows),
            evidence_complete=False,
        ), 503
    except (
        urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError,
        ValueError, json.JSONDecodeError,
    ) as exc:
        return _result(
            "owner_work_chronology_read_failed", error_type=exc.__class__.__name__
        ), 503


def _message_list_rows(envelope: Any) -> list[dict[str, Any]] | None:
    if isinstance(envelope, list):
        rows = envelope
    elif isinstance(envelope, Mapping):
        rows = next(
            (
                envelope.get(key) for key in ("payload", "messages", "data")
                if isinstance(envelope.get(key), list)
            ),
            None,
        )
    else:
        rows = None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return None
    return rows


def list_owner_work_items(
    *, database_url: str | None = None, include_withheld: bool = True, limit: int = 100
) -> tuple[dict[str, Any], int]:
    database_url = _database_url(database_url)
    if not database_url:
        return _result("owner_work_database_unavailable", items=[]), 503
    limit = max(1, min(int(limit or 100), MAX_CONVERSATIONS))
    try:
        import psycopg
        with psycopg.connect(
            database_url, connect_timeout=5,
            options="-c default_transaction_read_only=on -c statement_timeout=8000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    with latest as (
                      select distinct on (work_item_id)
                        work_event_id, work_item_id, account_id, conversation_id,
                        contact_id, inbox_id, ownership_mode,
                        latest_message_id, latest_message_at,
                        latest_inbound_message_id, latest_outgoing_message_id,
                        chronology_hash, unanswered_inbound_bundle_json,
                        observation_hash, unanswered_count, classification,
                        missed_message_classification, lane, actionable,
                        withheld_reasons_json, review_event_id,
                        reviewed_inbound_message_id, event_type,
                        window_state,reply_authority_state,window_reason,
                        provider_identity_class,window_evidence_hash,
                        expires_at_utc,expires_at_johannesburg,
                        remaining_seconds,warning_threshold_hours,
                        urgent_threshold_hours,alert_band,
                        ordinary_reply_allowed,send_reply_action_visible,
                        template_required,observed_at, created_at
                      from public.{WORK_TABLE}
                      order by work_item_id, observed_at desc, created_at desc,
                               work_event_id desc
                    )
                    select
                      work_event_id, work_item_id, account_id, conversation_id,
                      contact_id, inbox_id, ownership_mode,
                      latest_message_id, latest_message_at,
                      latest_inbound_message_id, latest_outgoing_message_id,
                      chronology_hash, unanswered_inbound_bundle_json,
                      observation_hash, unanswered_count, classification,
                      missed_message_classification, lane, actionable,
                      withheld_reasons_json, review_event_id,
                      reviewed_inbound_message_id, event_type,
                      window_state,reply_authority_state,window_reason,
                      provider_identity_class,window_evidence_hash,
                      expires_at_utc,expires_at_johannesburg,
                      remaining_seconds,warning_threshold_hours,
                      urgent_threshold_hours,alert_band,
                      ordinary_reply_allowed,send_reply_action_visible,
                      template_required,observed_at
                    from latest
                    where (%s or actionable=true)
                    order by
                      case when actionable then 0 else 1 end,
                      expires_at_utc asc nulls last,
                      observed_at desc, created_at desc, work_event_id desc
                    limit %s
                    """,
                    (bool(include_withheld), limit),
                )
                columns = [column.name for column in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        items = [_json_safe(row) for row in rows]
        return _result(
            "owner_work_items_loaded", items=items,
            counts=_classification_counts(items), evidence_complete=True,
        ), 200
    except Exception as exc:
        return _result(
            "owner_work_items_unavailable", items=[],
            error_type=exc.__class__.__name__, evidence_complete=False,
        ), 503


def build_charlie_backlog_report(
    items: Iterable[Mapping[str, Any]], *, report_date: str | None = None
) -> dict[str, Any]:
    safe_items = [dict(row) for row in items or []]
    counts = _classification_counts(safe_items)
    reasons: dict[str, int] = {}
    window_states: dict[str, int] = {}
    alert_bands: dict[str, int] = {}
    for row in safe_items:
        for reason in row.get("withheld_reasons") or row.get("withheld_reasons_json") or []:
            reason = _clean(reason)
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
        window_state = _clean(row.get("window_state")) or "unavailable"
        window_states[window_state] = window_states.get(window_state, 0) + 1
        alert_band = _clean(row.get("alert_band")) or "none"
        alert_bands[alert_band] = alert_bands.get(alert_band, 0) + 1
    report_date = report_date or datetime.now(timezone.utc).date().isoformat()
    snapshot_hash = _digest([
        {
            "work_item_id": row.get("work_item_id"),
            "chronology_hash": row.get("chronology_hash"),
            "classification": row.get("classification"),
            "actionable": bool(row.get("actionable")),
        }
        for row in safe_items
    ])
    return {
        "report_id": f"SAM-OWNER-BACKLOG-{report_date}-{snapshot_hash[:16]}",
        "report_date": report_date,
        "snapshot_hash": snapshot_hash,
        "total_current_items": len(safe_items),
        "actionable_count": sum(bool(row.get("actionable")) for row in safe_items),
        "ownership_decision_required_count": sum(
            row.get("classification") == "OWNERSHIP_DECISION_REQUIRED"
            for row in safe_items
        ),
        "classification_counts": counts,
        "withheld_reason_counts": dict(sorted(reasons.items())),
        "window_state_counts": dict(sorted(window_states.items())),
        "alert_band_counts": dict(sorted(alert_bands.items())),
        "nearest_expiry_utc": next(
            (
                row.get("expires_at_utc") for row in sorted(
                    safe_items,
                    key=lambda item: item.get("expires_at_utc") or "9999",
                )
                if row.get("actionable") and row.get("expires_at_utc")
            ),
            None,
        ),
        "alerts_delivery_enabled": False,
        "contains_customer_content": False,
        **AUTHORITY_FLAGS,
    }


def record_charlie_backlog_report(
    report: Mapping[str, Any], *, database_url: str | None = None
) -> tuple[dict[str, Any], int]:
    report = dict(report or {})
    if (
        not _clean(report.get("report_id"))
        or not _clean(report.get("report_date"))
        or not _clean(report.get("snapshot_hash"))
        or report.get("contains_customer_content") is not False
        or any(report.get(key) is not False for key in AUTHORITY_FLAGS)
    ):
        return _result("owner_backlog_report_invalid"), 400
    database_url = _database_url(database_url)
    if not database_url:
        return _result("owner_work_database_unavailable"), 503
    try:
        import psycopg
        with psycopg.connect(
            database_url, connect_timeout=5,
            options="-c statement_timeout=8000 -c lock_timeout=2000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    insert into public.{REPORT_TABLE} (
                      report_id, report_date, snapshot_hash,
                      total_current_items, actionable_count,
                      classification_counts_json, withheld_reason_counts_json,
                      contains_customer_content, sends_customer_message,
                      mutates_business_state
                    ) values (
                      %(report_id)s, %(report_date)s::date, %(snapshot_hash)s,
                      %(total_current_items)s, %(actionable_count)s,
                      %(classification_counts)s::jsonb,
                      %(withheld_reason_counts)s::jsonb, false, false, false
                    )
                    on conflict (report_id) do nothing
                    returning report_id
                    """,
                    {
                        **report,
                        "classification_counts": json.dumps(
                            report.get("classification_counts") or {}, sort_keys=True
                        ),
                        "withheld_reason_counts": json.dumps(
                            report.get("withheld_reason_counts") or {}, sort_keys=True
                        ),
                    },
                )
                created = cursor.fetchone()
            connection.commit()
        return _result(
            "owner_backlog_report_recorded" if created else "owner_backlog_report_replay_withheld",
            created=bool(created), report_id=report["report_id"],
        ), 201 if created else 200
    except Exception as exc:
        return _result(
            "owner_backlog_report_persistence_failed",
            error_type=exc.__class__.__name__,
        ), 503


def run_daily_backlog_report(
    *, database_url: str | None = None, report_date: str | None = None
) -> tuple[dict[str, Any], int]:
    loaded, status = list_owner_work_items(
        database_url=database_url, include_withheld=True, limit=MAX_CONVERSATIONS
    )
    if status >= 400:
        return loaded, status
    report = build_charlie_backlog_report(loaded.get("items") or [], report_date=report_date)
    persisted, persisted_status = record_charlie_backlog_report(
        report, database_url=database_url
    )
    return _result(
        persisted.get("status", "owner_backlog_report_persistence_failed"),
        report=report, created=bool(persisted.get("created")),
    ), persisted_status


def _conversation_inventory_page(
    envelope: Any,
) -> tuple[list[dict[str, Any]] | None, int | None]:
    if not isinstance(envelope, Mapping):
        return None, None
    data = envelope.get("data")
    data = data if isinstance(data, Mapping) else envelope
    rows = data.get("payload")
    meta = data.get("meta")
    if (
        not isinstance(rows, list)
        or not all(isinstance(row, dict) for row in rows)
        or not isinstance(meta, Mapping)
    ):
        return None, None
    raw_count = meta.get("all_count")
    if isinstance(raw_count, bool) or not str(raw_count or "").isdigit():
        return None, None
    return rows, int(raw_count)


def _conversation_account_id(conversation: Mapping[str, Any]) -> str:
    meta = conversation.get("meta")
    meta = meta if isinstance(meta, Mapping) else {}
    return _clean(conversation.get("account_id") or meta.get("account_id"))


def _encode_inventory_cursor(payload: Mapping[str, Any], secret: str) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(
            dict(payload), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(
        secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{encoded}.{signature}"


def _decode_inventory_cursor(token: Any, secret: str) -> dict[str, Any] | None:
    value = _clean(token, 1200)
    if not value or "." not in value:
        return None
    encoded, supplied_signature = value.rsplit(".", 1)
    expected_signature = hmac.new(
        secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return None
    try:
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
        )
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _json_value(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value) if isinstance(value, str) else fallback
    except json.JSONDecodeError:
        return fallback
    return parsed


def _conversation_identity(conversation: Mapping[str, Any]) -> dict[str, str]:
    meta = conversation.get("meta") if isinstance(conversation.get("meta"), Mapping) else {}
    sender = meta.get("sender") if isinstance(meta.get("sender"), Mapping) else {}
    contact = conversation.get("contact") if isinstance(conversation.get("contact"), Mapping) else {}
    inbox = conversation.get("inbox") if isinstance(conversation.get("inbox"), Mapping) else {}
    values = {
        "account_id": _clean(conversation.get("account_id") or meta.get("account_id")),
        "conversation_id": _clean(conversation.get("id") or conversation.get("conversation_id")),
        "contact_id": _clean(
            conversation.get("contact_id") or contact.get("id") or sender.get("id")
        ),
        "inbox_id": _clean(conversation.get("inbox_id") or inbox.get("id")),
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise OwnerWorkEvidenceError(f"identity_missing:{','.join(missing)}")
    return values


def _message(row: Any, identity: Mapping[str, str]) -> dict[str, Any] | None:
    if not isinstance(row, Mapping):
        raise OwnerWorkEvidenceError("message_shape_invalid")
    message_type = row.get("message_type")
    if message_type in {2, "2", "activity"}:
        return None
    direction = _clean(row.get("direction")).lower()
    if not direction:
        direction = {"0": "incoming", "1": "outgoing"}.get(str(message_type), "")
    if direction not in {"incoming", "outgoing"}:
        raise OwnerWorkEvidenceError("message_direction_unknown")
    private = row.get("private")
    if private not in {None, True, False}:
        raise OwnerWorkEvidenceError("message_private_state_invalid")
    message_id = _clean(row.get("id") or row.get("message_id"))
    created_at = _canonical_timestamp(row.get("created_at"))
    if not message_id or not created_at:
        raise OwnerWorkEvidenceError("message_identity_or_timestamp_missing")
    conversation_id = _clean(
        row.get("conversation_id")
        or (row.get("conversation") or {}).get("id")
        if isinstance(row.get("conversation"), Mapping)
        else row.get("conversation_id")
    )
    if conversation_id and conversation_id != identity["conversation_id"]:
        raise OwnerWorkEvidenceError("message_conversation_mismatch")
    return {
        "message_id": message_id,
        "direction": direction,
        "created_at": created_at,
        "public": private is not True,
    }


def _authoritative_markers(
    conversation: Mapping[str, Any], review: Mapping[str, Any]
) -> set[str]:
    attrs = conversation.get("custom_attributes")
    attrs = attrs if isinstance(attrs, Mapping) else {}
    labels = conversation.get("labels")
    labels = labels if isinstance(labels, list) else []
    markers = {_clean(value).lower() for value in labels if _clean(value)}
    for key in ("sales_lane", "specialist_lane", "protected_reason", "human_reason"):
        value = _clean(attrs.get(key)).lower()
        if value:
            markers.add(value)
    decision = review.get("decision_json")
    decision = decision if isinstance(decision, Mapping) else {}
    for key in ("lane", "escalation_reason", "protected_reason"):
        value = _clean(decision.get(key)).lower()
        if value:
            markers.add(value)
    return markers


def _ownership_evidence(conversation: Mapping[str, Any]) -> dict[str, Any]:
    attrs = conversation.get("custom_attributes")
    if attrs is not None and not isinstance(attrs, Mapping):
        return {
            "normalized_mode": "UNAVAILABLE",
            "state": "malformed",
            "decision_required": True,
            "reason": "conversation_ownership_malformed",
        }
    attrs = attrs if isinstance(attrs, Mapping) else {}
    raw = attrs.get("conversation_mode")
    if raw is None:
        raw = conversation.get("conversation_mode")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {
            "normalized_mode": "UNAVAILABLE",
            "state": "missing",
            "decision_required": True,
            "reason": "conversation_ownership_missing",
        }
    if not isinstance(raw, str):
        return {
            "normalized_mode": "UNAVAILABLE",
            "state": "malformed",
            "decision_required": True,
            "reason": "conversation_ownership_malformed",
        }
    mode = raw.strip().upper()
    if mode == "AUTO":
        mode = "AUTO_GENERAL"
    if mode not in SUPPORTED_OWNERSHIP_MODES:
        return {
            "normalized_mode": "UNAVAILABLE",
            "state": "unsupported",
            "decision_required": True,
            "reason": "conversation_ownership_unsupported",
        }
    return {
        "normalized_mode": mode,
        "state": "valid",
        "decision_required": False,
        "reason": "",
    }


def _ownership_mode(conversation: Mapping[str, Any]) -> str:
    return _ownership_evidence(conversation)["normalized_mode"]


def _explicit_owner_attention_policy(conversation: Mapping[str, Any]) -> bool:
    packet = conversation.get("owner_attention_policy")
    if not isinstance(packet, Mapping):
        return False
    return (
        packet.get("required") is True
        and packet.get("server_derived") is True
        and _clean(packet.get("reason")).lower() in OWNER_ATTENTION_POLICY_REASONS
    )


def _validate_observation(event: Mapping[str, Any]) -> str:
    required = (
        "work_event_id", "work_item_id", "account_id", "conversation_id",
        "contact_id", "inbox_id", "chronology_hash", "classification",
        "observed_at",
        "reconciliation_actor_id",
        "window_state", "reply_authority_state", "window_reason",
        "provider_identity_class", "window_evidence_hash", "alert_band",
    )
    if any(not _clean(event.get(key)) for key in required):
        return "owner_work_observation_incomplete"
    if event.get("contains_customer_content") is not False:
        return "customer_content_forbidden"
    if any(event.get(key) is not False for key in AUTHORITY_FLAGS):
        return "owner_work_authority_forbidden"
    if event.get("ordinary_reply_allowed") is True and event.get("window_state") not in {
        "open", "approaching_expiry",
    }:
        return "ordinary_reply_authority_window_invalid"
    if event.get("send_reply_action_visible") is True and event.get("ordinary_reply_allowed") is not True:
        return "send_reply_visibility_authority_invalid"
    if event.get("classification") == "OWNERSHIP_DECISION_REQUIRED" and (
        event.get("ownership_mode") != "UNAVAILABLE"
        or event.get("ordinary_reply_allowed") is not False
        or event.get("send_reply_action_visible") is not False
        or event.get("reply_authority_state") != "ownership_decision_required"
        or event.get("template_required") is not False
    ):
        return "ownership_exception_authority_invalid"
    alert = event.get("prepared_window_alert")
    if alert is not None:
        if not isinstance(alert, Mapping):
            return "window_alert_shape_invalid"
        if (
            alert.get("work_item_id") != event.get("work_item_id")
            or alert.get("observation_hash") != event.get("observation_hash")
            or alert.get("conversation_id") != event.get("conversation_id")
            or alert.get("contact_id") != event.get("contact_id")
            or alert.get("inbox_id") != event.get("inbox_id")
        ):
            return "window_alert_identity_mismatch"
        if any(alert.get(key) is not False for key in (
            "delivery_enabled", "delivered", "contains_customer_content",
            "sends_customer_message", "changes_conversation_ownership",
            "calls_telegram", "uses_template", "mutates_business_state",
        )):
            return "window_alert_authority_forbidden"
    try:
        json.dumps(_json_safe(event), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return "owner_work_observation_not_json_safe"
    return ""


def _classification_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = _clean(row.get("classification")) or "IDENTITY_OR_EVIDENCE_UNAVAILABLE"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _result(status: str, **extra: Any) -> dict[str, Any]:
    failure_markers = (
        "failed", "unavailable", "incomplete", "invalid", "forbidden",
        "missing", "exceeded", "malformed", "stalled", "not_configured",
    )
    return {
        "success": not any(marker in status for marker in failure_markers),
        "status": status, **extra, **AUTHORITY_FLAGS,
    }


def _database_url(value: str | None) -> str:
    return str(value if value is not None else os.getenv(DATABASE_URL_ENV, "") or "").strip()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OwnerWorkEvidenceError(f"{name}_shape_invalid")
    return value


def _clean(value: Any, limit: int = 160) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise OwnerWorkEvidenceError("timestamp_invalid")
    if value.tzinfo is None or value.utcoffset() is None:
        raise OwnerWorkEvidenceError("timestamp_timezone_missing")
    return value.astimezone(timezone.utc)


def _canonical_timestamp(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise OwnerWorkEvidenceError("timestamp_invalid") from exc
    return _aware(value).isoformat() if isinstance(value, datetime) else ""


def _numeric_sort(value: Any) -> tuple[int, str]:
    text = _clean(value)
    return (int(text), text) if text.isdigit() else (0, text)


def _digest(value: Any) -> str:
    encoded = json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest().upper()


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported_json_value:{type(value).__name__}")
