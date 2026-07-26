"""Canonical, no-send SAM owner work queue.

The queue persists chronology evidence, not customer message content.  It is
deliberately independent from Telegram delivery and customer-send authority.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
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
    ownership_mode = _ownership_mode(conversation)
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
    if ownership_mode != "HUMAN":
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
    if protected:
        classification = "PROTECTED_ACTION_REQUIRED"
        lane = "PROTECTED"
        withheld.append("protected_work_requires_owner")
        actionable = True
        missed_classification = "protected_owner_work"
    elif specialist:
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
    if window["window_state"] == "unavailable":
        classification = "IDENTITY_OR_EVIDENCE_UNAVAILABLE"
        actionable = False
        withheld.append(window["reason"])
    elif window["window_state"] == "expired":
        classification = "CUSTOMER_REPLY_PROHIBITED"
        actionable = False
        withheld.extend(["provider_reply_window_expired", "customer_reply_prohibited"])
    elif window["reply_authority_state"] == "customer_reply_prohibited":
        classification = "CUSTOMER_REPLY_PROHIBITED"
        actionable = False
        withheld.extend([window["reason"], "customer_reply_prohibited"])

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
        "source": "bounded_human_backlog_reconciliation_v1",
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


def reconcile_live_human_conversation(
    conversation_id: str,
    *,
    reconciliation_actor_id: str,
    environ: Mapping[str, str] | None = None,
    message_reader: Callable[[str, Mapping[str, str]], tuple[dict[str, Any], int]] | None = None,
) -> tuple[dict[str, Any], int]:
    """Run one bounded authoritative HUMAN inventory read and evidence append."""
    from modules.sales.sam_live_stock_launch_control import (
        _chatwoot_read_conversations,
        load_latest_sam_live_stock_review_events_for_conversations,
    )

    source = environ if environ is not None else os.environ
    conversation_id = _clean(conversation_id)
    if not conversation_id:
        return _result("owner_work_conversation_id_required"), 400
    if not _clean(reconciliation_actor_id, 200):
        return _result("server_derived_owner_principal_required"), 403
    try:
        conversations = _chatwoot_read_conversations(source)
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
                        contact_id, inbox_id, latest_message_id, latest_message_at,
                        chronology_hash, unanswered_inbound_bundle_json,
                        observation_hash, unanswered_count, classification,
                        missed_message_classification, lane, actionable,
                        withheld_reasons_json, review_event_id, event_type,
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
                      contact_id, inbox_id, latest_message_id, latest_message_at,
                      chronology_hash, unanswered_inbound_bundle_json,
                      observation_hash, unanswered_count, classification,
                      missed_message_classification, lane, actionable,
                      withheld_reasons_json, review_event_id, event_type,
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


def _ownership_mode(conversation: Mapping[str, Any]) -> str:
    attrs = conversation.get("custom_attributes")
    attrs = attrs if isinstance(attrs, Mapping) else {}
    return _clean(attrs.get("conversation_mode") or conversation.get("conversation_mode")).upper()


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
