"""Provider-chronology-driven autonomous SAM Livestock inbox operation."""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Mapping

from modules.sales.sam_live_stock_runtime import (
    extract_live_stock_facts,
    load_sam_general_context,
    parse_chatwoot_inbound,
    resolve_contextual_sales_route,
    resolve_sam_general_inbound_identity,
)
from modules.sales.sam_sales_router import classify_sam_sales_lane


class SamInboxOperationFailure(RuntimeError):
    """Safe phase evidence for a failed inbox cycle; contains no customer data."""

    def __init__(self, code, *, stage, effect_boundary):
        super().__init__(code)
        self.stage = stage
        self.effect_boundary = effect_boundary


def operate_livestock_inbox(
    *,
    environ=None,
    conversation_page_loader: Callable | None = None,
    history_loader: Callable,
    inbound_processor: Callable,
    claim_exists: Callable,
    claimed_inbound_loader: Callable | None = None,
    quarantined_conversation_loader: Callable | None = None,
    attention_queue_operator: Callable | None = None,
    attention_sam_state: Mapping | None = None,
    max_process_count: int | None = None,
    isolate_provider_read_failures: bool = False,
    now=None,
) -> dict:
    """Process every independently eligible current inbound exactly once."""
    source = environ if environ is not None else os.environ
    clock = now or datetime.now(timezone.utc)
    page_loader = conversation_page_loader or (
        lambda page: _conversation_page(page, source)
    )
    try:
        first = page_loader(1)
    except Exception as exc:
        raise SamInboxOperationFailure(
            "chatwoot_inventory_first_page_unavailable",
            stage="provider_inventory_read_before_claim",
            effect_boundary="not_crossed",
        ) from exc
    meta = (first.get("data") or {}).get("meta") or {}
    provider_total = int(meta.get("all_count") or 0)
    first_payload = (first.get("data") or {}).get("payload")
    if not isinstance(first_payload, list) or provider_total < len(first_payload):
        raise RuntimeError("chatwoot_inventory_page_invalid")
    rows = list(first_payload)
    page_count = max(1, math.ceil(provider_total / 25))

    def load_page(page):
        body = page_loader(page)
        data = body.get("data") if isinstance(body.get("data"), Mapping) else {}
        next_meta = data.get("meta") if isinstance(data.get("meta"), Mapping) else {}
        next_payload = data.get("payload")
        if (
            not isinstance(next_payload, list)
            or int(next_meta.get("all_count") or -1) != provider_total
        ):
            raise RuntimeError("chatwoot_inventory_changed")
        return page, list(next_payload)

    loaded = {}
    provider_read_failures = []
    if page_count > 1:
        with ThreadPoolExecutor(max_workers=min(24, page_count - 1)) as pool:
            futures = {
                pool.submit(load_page, page): page
                for page in range(2, page_count + 1)
            }
            for future in as_completed(futures):
                try:
                    page, payload = future.result()
                    loaded[page] = payload
                except Exception as exc:
                    if (
                        not isolate_provider_read_failures
                        or not _isolatable_provider_transport_failure(exc)
                    ):
                        raise
                    provider_read_failures.append({
                        "dependency": "chatwoot_inventory_page",
                        "page": futures[future],
                        "error_type": exc.__class__.__name__,
                    })
    for page in range(2, page_count + 1):
        if page in loaded:
            rows.extend(loaded[page])
    identities = [str(row.get("id") or "") for row in rows]
    if not all(identities) or len(set(identities)) != len(identities):
        raise RuntimeError("chatwoot_inventory_identity_conflict")
    if (
        len(identities) != provider_total
        and not provider_read_failures
    ):
        raise RuntimeError("chatwoot_inventory_incomplete")

    candidate_rows = []
    claim_cache = {}
    quarantined_conversations = set()
    candidate_keys = []
    for row in rows:
        latest = (
            row.get("last_non_activity_message")
            if isinstance(row.get("last_non_activity_message"), Mapping)
            else {}
        )
        inbound_id = (
            str(latest.get("id") or "")
            if latest.get("message_type") in (0, "incoming")
            else ""
        )
        if row.get("can_reply") is True and inbound_id:
            key = (str(row.get("id") or ""), inbound_id)
            candidate_keys.append(key)
    if claimed_inbound_loader and candidate_keys:
        claimed = {
            (str(conversation_id), str(inbound_id))
            for conversation_id, inbound_id
            in (claimed_inbound_loader(candidate_keys) or set())
        }
        claim_cache = {key: key in claimed for key in candidate_keys}
    else:
        claim_cache = {
            key: bool(claim_exists(*key)) for key in candidate_keys
        }
    if quarantined_conversation_loader and candidate_keys:
        quarantined_conversations = {
            str(conversation_id)
            for conversation_id in (
                quarantined_conversation_loader(
                    sorted({key[0] for key in candidate_keys})
                )
                or set()
            )
        }
    for row in rows:
        latest = (
            row.get("last_non_activity_message")
            if isinstance(row.get("last_non_activity_message"), Mapping)
            else {}
        )
        inbound_id = (
            str(latest.get("id") or "")
            if latest.get("message_type") in (0, "incoming")
            else ""
        )
        if row.get("can_reply") is True and inbound_id:
            key = (str(row.get("id") or ""), inbound_id)
            if (
                not claim_cache[key]
                and key[0] not in quarantined_conversations
            ):
                candidate_rows.append(row)

    history_cache = {}
    history_failures = {}
    if candidate_rows:
        with ThreadPoolExecutor(max_workers=min(16, len(candidate_rows))) as pool:
            futures = {
                pool.submit(
                    history_loader, str(row.get("id") or ""), source
                ): str(row.get("id") or "")
                for row in candidate_rows
            }
            for future in as_completed(futures):
                conversation_id = futures[future]
                try:
                    history_cache[conversation_id] = future.result()
                except Exception as exc:
                    if (
                        not isolate_provider_read_failures
                        or not _isolatable_provider_transport_failure(exc)
                    ):
                        raise
                    history_failures[conversation_id] = {
                        "dependency": "chatwoot_conversation_history",
                        "error_type": exc.__class__.__name__,
                    }
    for conversation_id, result in history_cache.items():
        history, status = result
        if (
            status != 200
            or not isinstance(history, Mapping)
            or history.get("success") is not True
            or not _history_is_complete(history)
        ):
            raise RuntimeError(
                "chatwoot_candidate_history_unavailable:"
                + conversation_id
            )

    def cached_claim_exists(conversation_id, inbound_id):
        key = (str(conversation_id), str(inbound_id))
        if key in claim_cache:
            return claim_cache[key]
        return claim_exists(*key)

    def cached_history_loader(conversation_id, _source):
        key = str(conversation_id)
        if key in history_cache:
            return history_cache[key]
        return history_loader(key, source)

    dispositions = []
    processed_count = 0
    operation_rows = sorted(rows, key=_autonomous_priority)
    for row in operation_rows:
        conversation_id = str(row.get("id") or "")
        if conversation_id in history_failures:
            latest = (
                row.get("last_non_activity_message")
                if isinstance(row.get("last_non_activity_message"), Mapping)
                else {}
            )
            dispositions.append({
                "account_id": str(row.get("account_id") or ""),
                "inbox_id": str(row.get("inbox_id") or ""),
                "contact_id": str(
                    ((row.get("meta") or {}).get("sender") or {}).get("id")
                    or ""
                ),
                "conversation_id": conversation_id,
                "inbound_message_id": str(latest.get("id") or ""),
                "queue_relevant": True,
                "eligible": False,
                "selected_for_processing": False,
                "disposition": "provider_chronology_unavailable",
                "final_route": "AUTO_SPECIALIST",
                "provider_state": "",
                "provider_confirmed": False,
                "owner_decision_required": False,
                "reply": "",
                "latest_inbound_at": int(latest.get("created_at") or 0),
                "coverage_exception": history_failures[conversation_id],
            })
            continue
        can_process = bool(
            max_process_count is None
            or processed_count < max(0, int(max_process_count))
        )
        disposition = _inspect_and_operate(
            row,
            source=source,
            history_loader=cached_history_loader,
            inbound_processor=inbound_processor,
            claim_exists=cached_claim_exists,
            effect_claim_exists=claim_exists,
            conversation_quarantined=(
                str(row.get("id") or "") in quarantined_conversations
            ),
            can_process=can_process,
            require_durable_result=max_process_count is not None,
            now=clock,
        )
        if disposition.get("selected_for_processing") is True:
            processed_count += 1
        if disposition["queue_relevant"]:
            dispositions.append(disposition)
    coverage_failures = [
        *provider_read_failures,
        *history_failures.values(),
    ]
    summary = build_sam_status_summary(
        dispositions,
        observed_at=clock,
        coverage_failures=coverage_failures,
        inventory_complete=not provider_read_failures,
    )
    attention = {}
    if attention_queue_operator is not False:
        operator = attention_queue_operator
        if operator is None:
            from modules.oom_sakkie.owner_attention_adapter import operate_owner_attention_queue
            operator = operate_owner_attention_queue
        try:
            sam_state = dict(attention_sam_state or {"state": "healthy"})
            if coverage_failures:
                sam_state.update({
                    "state": "degraded_partial_provider_coverage",
                    "affected_work_codes": [
                        code
                        for code, affected in (
                            (
                                "provider_inventory_page",
                                bool(provider_read_failures),
                            ),
                            (
                                "conversation_chronology",
                                bool(history_failures),
                            ),
                        )
                        if affected
                    ],
                    "coverage_exception_count": len(coverage_failures),
                    "manual_coverage_required": True,
                    "manual_coverage_reason_code": (
                        "provider_chronology_unavailable"
                    ),
                })
            attention = operator(
                dispositions,
                environ=source,
                now=clock,
                sam_state=sam_state,
            )
        except Exception:
            attention = {"success": False, "status": "owner_attention_queue_contained", "calls_telegram": False}
    return {
        "status": "sam_live_stock_inbox_operated",
        "inventory_count": len(rows),
        "provider_conversation_count": provider_total,
        "inventory_scope": (
            "partial_provider_inventory_isolated"
            if provider_read_failures
            else "full_provider_conversation_inventory"
        ),
        "provider_read_failures": provider_read_failures,
        "coverage_exception_count": (
            len(provider_read_failures) + len(history_failures)
        ),
        "dispositions": dispositions,
        "customers_answered": sum(
            item.get("provider_confirmed") is True for item in dispositions
        ),
        "quarantines": sum(
            item.get("provider_state") == "provider_outcome_ambiguous"
            for item in dispositions
        ),
        "owner_decisions": sum(
            item.get("owner_decision_required") is True
            for item in dispositions
        ),
        "lane_active": True,
        "lane_coverage_state": (
            "degraded_partial_provider_coverage"
            if coverage_failures
            else "complete"
        ),
        "automatic_retry_authorized": False,
        "protected_authority": False,
        "owner_status_summary": summary,
        "owner_attention_queue": attention,
    }


def _autonomous_priority(row):
    latest = (
        row.get("last_non_activity_message")
        if isinstance(row.get("last_non_activity_message"), Mapping)
        else {}
    )
    replyable_inbound = bool(
        row.get("can_reply") is True
        and latest.get("message_type") in (0, "incoming")
        and str(latest.get("id") or "")
    )
    return (
        0 if replyable_inbound else 1,
        int(latest.get("created_at") or 0) if replyable_inbound else 0,
        str(row.get("id") or ""),
        str(latest.get("id") or ""),
    )


def _inspect_and_operate(
    row,
    *,
    source,
    history_loader,
    inbound_processor,
    claim_exists,
    effect_claim_exists,
    conversation_quarantined,
    can_process,
    require_durable_result,
    now,
):
    conversation_id = str(row.get("id") or "")
    meta = row.get("meta") if isinstance(row.get("meta"), Mapping) else {}
    sender = meta.get("sender") if isinstance(meta.get("sender"), Mapping) else {}
    identity = {
        "account_id": str(row.get("account_id") or ""),
        "inbox_id": str(row.get("inbox_id") or ""),
        "contact_id": str(sender.get("id") or ""),
    }
    provider_latest = (
        row.get("last_non_activity_message")
        if isinstance(row.get("last_non_activity_message"), Mapping)
        else {}
    )
    provider_incoming = provider_latest.get("message_type") in (0, "incoming")
    provider_inbound_id = (
        str(provider_latest.get("id") or "") if provider_incoming else ""
    )
    if conversation_quarantined:
        return {
            **identity,
            "conversation_id": conversation_id,
            "inbound_message_id": provider_inbound_id,
            "queue_relevant": True,
            "eligible": False,
            "disposition": "delivery_quarantined_do_not_retry",
            "final_route": "AUTO_SPECIALIST",
            "provider_state": "provider_outcome_ambiguous",
            "provider_confirmed": False,
            "owner_decision_required": False,
            "reply": "",
            "latest_inbound_at": int(
                provider_latest.get("created_at") or 0
            ),
        }
    if (
        provider_latest
        and (
            row.get("can_reply") is not True
            or not provider_incoming
            or not provider_inbound_id
        )
    ):
        return {
            **identity,
            "conversation_id": conversation_id,
            "inbound_message_id": provider_inbound_id,
            "queue_relevant": False,
            "eligible": False,
            "disposition": (
                "closed_window_reengagement_required"
                if row.get("can_reply") is not True
                else "awaiting_customer"
            ),
            "final_route": "",
            "provider_state": "",
            "provider_confirmed": False,
            "owner_decision_required": False,
            "reply": "",
            "latest_inbound_at": int(
                provider_latest.get("created_at") or 0
            ),
        }
    if (
        provider_inbound_id
        and claim_exists(conversation_id, provider_inbound_id)
    ):
        return {
            **identity,
            "conversation_id": conversation_id,
            "inbound_message_id": provider_inbound_id,
            "queue_relevant": True,
            "eligible": False,
            "disposition": "already_claimed",
            "final_route": "AUTO_SPECIALIST",
            "provider_state": "",
            "provider_confirmed": False,
            "owner_decision_required": False,
            "reply": "",
            "latest_inbound_at": int(
                provider_latest.get("created_at") or 0
            ),
        }
    history, status = history_loader(conversation_id, source)
    messages = [
        item
        for item in (history.get("messages") or [])
        if isinstance(item, Mapping)
        and item.get("message_type") in (0, 1, "incoming", "outgoing")
        and not bool(item.get("private"))
    ]
    messages.sort(
        key=lambda item: (
            int(item.get("created_at") or 0),
            int(item.get("id") or 0),
        )
    )
    latest = messages[-1] if messages else {}
    latest_incoming = latest.get("message_type") in (0, "incoming")
    inbound_id = str(latest.get("id") or "") if latest_incoming else ""
    payload = {
        **latest,
        "event": "message_created",
        "account": {"id": row.get("account_id") or "147387"},
        "conversation": {
            "id": conversation_id,
            "inbox": {
                "id": row.get("inbox_id"),
                "channel_type": "Channel::Whatsapp",
            },
        },
        "sender": {"id": sender.get("id"), "name": sender.get("name")},
        "_sam_authoritative_history": history,
    }
    parsed = parse_chatwoot_inbound(payload) if latest_incoming else {}
    if parsed:
        parsed = resolve_sam_general_inbound_identity(
            parsed,
            payload,
            environ=source,
            conversation_identity_loader=lambda _cid, _env=None: {
                "success": True,
                "status": "provider_inventory_identity_verified",
                "account_id": str(row.get("account_id") or "147387"),
                "conversation_id": conversation_id,
                "contact_id": str(sender.get("id") or ""),
                "inbox_id": str(row.get("inbox_id") or ""),
            },
        )
    facts = extract_live_stock_facts(parsed.get("content"), parsed) if parsed else {}
    raw_route = classify_sam_sales_lane(parsed.get("content") or "") if parsed else {}
    context = (
        load_sam_general_context(
            parsed,
            conversation_history_loader=lambda *_args, **_kwargs: history,
            environ=source,
        )
        if parsed
        else {}
    )
    contextual = (
        resolve_contextual_sales_route(
            parsed, facts, context.get("prior_sales_context")
        )
        if parsed
        else {}
    )
    livestock = bool(
        raw_route.get("lane") == "live_stock_sales"
        and float(raw_route.get("confidence") or 0) >= 0.8
    ) or contextual.get("preserve_live_stock_lane") is True
    exact_claim = bool(
        inbound_id and claim_exists(conversation_id, inbound_id)
    )
    open_window = bool(row.get("can_reply") is True)
    eligible = bool(
        status == 200
        and _history_is_complete(history)
        and latest_incoming
        and inbound_id
        and livestock
        and open_window
        and not exact_claim
    )
    selected_for_processing = bool(eligible and can_process)
    if selected_for_processing:
        try:
            result = inbound_processor(payload)
        except Exception as exc:
            try:
                crossed = bool(
                    effect_claim_exists(conversation_id, inbound_id)
                )
                effect_boundary = "crossed" if crossed else "not_crossed"
            except Exception:
                effect_boundary = "indeterminate"
            raise SamInboxOperationFailure(
                "sam_selected_candidate_processing_failed",
                stage=(
                    "post_claim_processing"
                    if effect_boundary == "crossed"
                    else "preclaim_response_processing"
                    if effect_boundary == "not_crossed"
                    else "processing_boundary_indeterminate"
                ),
                effect_boundary=effect_boundary,
            ) from exc
    else:
        result = {}
    decision = result.get("sam_decision") if isinstance(result.get("sam_decision"), Mapping) else {}
    delivery = decision.get("routine_reply_delivery") if isinstance(decision.get("routine_reply_delivery"), Mapping) else {}
    outcome = delivery.get("delivery_outcome") if isinstance(delivery.get("delivery_outcome"), Mapping) else {}
    provider_state = str(outcome.get("delivery_state") or "")
    if selected_for_processing and require_durable_result:
        durable_result = bool(
            result.get("sent") is True
            or decision.get("reason") in {
                "routine_reply_confirmed_delivered",
                "routine_reply_delivery_ambiguous",
            }
            or provider_state in {
                "provider_delivered",
                "provider_read",
                "provider_outcome_ambiguous",
            }
            or (
                provider_state == "chatwoot_accepted_unverified"
                and isinstance(delivery.get("claim"), Mapping)
                and delivery["claim"].get("success") is True
                and delivery["claim"].get("created") is True
                and bool(
                    str(
                        delivery["claim"].get("delivery_attempt_id") or ""
                    ).strip()
                )
                and delivery.get("automatic_retry_prohibited") is True
            )
        )
        if (
            int(result.get("_operation_status_code") or 500) >= 400
            or result.get("processed") is not True
            or not durable_result
        ):
            raise RuntimeError(
                "sam_selected_candidate_without_durable_disposition:"
                + conversation_id
            )
    queue_relevant = bool(livestock or exact_claim)
    return {
        **identity,
        "conversation_id": conversation_id,
        "inbound_message_id": inbound_id,
        "queue_relevant": queue_relevant,
        "eligible": eligible,
        "selected_for_processing": selected_for_processing,
        "disposition": (
            "processed"
            if selected_for_processing
            else "deferred_to_next_autonomous_cycle"
            if eligible
            else "already_claimed"
            if exact_claim
            else "awaiting_customer"
            if livestock and not latest_incoming
            else "closed_window_reengagement_required"
            if livestock and not open_window
            else "not_livestock"
        ),
        "final_route": (
            "AUTO_SPECIALIST"
            if livestock
            else contextual.get("final_route") or raw_route.get("lane")
        ),
        "provider_state": provider_state,
        "provider_confirmed": provider_state in {
            "provider_delivered", "provider_read"
        },
        "owner_decision_required": bool(
            decision.get("protected_owner_exception_required")
            or decision.get("owner_gate_required")
        ),
        "owner_attention_decision": _owner_attention_decision(
            decision, latest, open_window=open_window
        ),
        "reply": decision.get("suggested_reply_text") or "",
        "latest_inbound_at": int(latest.get("created_at") or 0),
    }


def _owner_attention_decision(decision, latest, *, open_window):
    """Map only the existing canonical delivery-exception contract."""
    exception = decision.get("delivery_owner_exception") if isinstance(decision.get("delivery_owner_exception"), Mapping) else {}
    if (exception.get("eligible") is not True
            or exception.get("version") != "sam_delivery_owner_exception_v1"
            or not open_window):
        return None
    try:
        inbound_at = datetime.fromtimestamp(int(latest.get("created_at")), timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    return {
        "requested_authority": "delivery_commitment",
        "expires_at": (inbound_at + timedelta(hours=24)).isoformat(),
        "choices": [{
            "id": "decline",
            "label_code": "do_not_offer_delivery",
            "actionable": True,
            "outcome_code": "delivery_not_approved",
            "follow_up_trigger_code": "prepare_governed_reply",
        }],
        "source_contract": "sam_delivery_owner_exception_v1",
    }


def _history_is_complete(history):
    """Accept the real Chatwoot history shape only when chronology is auditable."""
    if not isinstance(history, Mapping) or history.get("success") is False:
        return False
    messages = history.get("messages")
    if not isinstance(messages, list) or not messages:
        return False
    public = [
        item for item in messages
        if isinstance(item, Mapping) and not bool(item.get("private"))
    ]
    if not public:
        return False
    try:
        return all(
            str(item.get("id") or "").strip()
            and int(item.get("created_at")) >= 0
            for item in public
        )
    except (TypeError, ValueError):
        return False


def build_sam_status_summary(
    dispositions,
    *,
    observed_at=None,
    coverage_failures=(),
    inventory_complete=True,
):
    """Build the compact owner-facing status used by the safe brief path."""
    rows = list(dispositions or [])
    eligible = [row for row in rows if row.get("eligible") is True]
    unavailable = [
        row for row in rows
        if row.get("disposition") == "provider_chronology_unavailable"
    ]
    awaiting_customer = [
        row for row in rows
        if row.get("disposition") == "awaiting_customer"
        or row.get("provider_confirmed") is True
    ]
    owner = [
        row for row in rows if row.get("owner_decision_required") is True
    ]
    quarantined = [
        row for row in rows
        if row.get("provider_state") == "provider_outcome_ambiguous"
        or row.get("disposition") == "already_claimed"
    ]
    closed = [
        row for row in rows
        if row.get("disposition")
        == "closed_window_reengagement_required"
    ]
    oldest = min(
        eligible,
        key=lambda row: int(row.get("latest_inbound_at") or 0),
        default={},
    )
    return {
        "lane_state": (
            "active"
            if not coverage_failures
            else "degraded_partial_provider_coverage"
        ),
        "customers_answered_today": sum(
            row.get("provider_confirmed") is True for row in rows
        ),
        "customers_awaiting_sam": sum(
            row.get("eligible") is True
            and row.get("provider_confirmed") is not True
            for row in rows
        ) + len(unavailable),
        "customers_awaiting_customer_reply": len(awaiting_customer),
        "owner_decisions": len(owner),
        "quarantines": len(quarantined),
        "closed_window_reengagement": len(closed),
        "oldest_eligible_unanswered_lead": (
            str(oldest.get("conversation_id") or "")
            if inventory_complete
            else ""
        ),
        "oldest_eligible_scope": (
            "full_provider_inventory"
            if inventory_complete
            else "unknown_partial_provider_inventory"
        ),
        "coverage_exceptions": _coverage_exception_summary(
            coverage_failures
        ),
        "last_successful_webhook_processing_time": (
            (observed_at or datetime.now(timezone.utc)).isoformat()
            if any(row.get("provider_confirmed") is True for row in rows)
            else ""
        ),
    }


def _coverage_exception_summary(failures):
    counts = {}
    for row in failures or ():
        dependency = str((row or {}).get("dependency") or "provider_read")
        counts[dependency] = counts.get(dependency, 0) + 1
    return [
        {"dependency": key, "count": counts[key]}
        for key in sorted(counts)
    ]


def _isolatable_provider_transport_failure(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return False
    return isinstance(exc, (TimeoutError, urllib.error.URLError))


def _conversation_page(page, environ):
    account = str(environ.get("CHATWOOT_ACCOUNT_ID") or "147387")
    inbox = str(environ.get("SAM_LIVE_STOCK_CHATWOOT_INBOX_ID") or "96568")
    query = urllib.parse.urlencode(
        {
            "inbox_id": inbox,
            "status": "all",
            "sort_by": "last_activity_at",
            "page": page,
        }
    )
    return _request(
        f"/api/v1/accounts/{account}/conversations?{query}", environ
    )


def _request(path, environ):
    base = str(environ.get("CHATWOOT_BASE_URL") or "").rstrip("/")
    token = str(
        environ.get("CHATWOOT_API_ACCESS_TOKEN")
        or environ.get("CHATWOOT_API_TOKEN")
        or ""
    )
    if not base.startswith("https://") or not token:
        raise RuntimeError("chatwoot_inventory_configuration_unavailable")
    request = urllib.request.Request(
        base + path,
        headers={"api_access_token": token, "Accept": "application/json"},
    )
    timeout = _bounded_timeout(
        environ.get("SAM_CHATWOOT_INVENTORY_READ_TIMEOUT_SECONDS"),
        default=5.0,
        minimum=1.0,
        maximum=10.0,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _bounded_timeout(value, *, default, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
