"""Read-only Chatwoot history recovery for SAM Live Stock learning evidence."""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from modules.sales.conversation_learning import AUTHORITY_FLAGS, record_sales_conversation_learning_event
from services.database_service import DATABASE_URL_ENV


CHATWOOT_BASE_URL_ENV = "CHATWOOT_BASE_URL"
CHATWOOT_ACCOUNT_ID_ENV = "CHATWOOT_ACCOUNT_ID"
CHATWOOT_TOKEN_ENV = "CHATWOOT_API_ACCESS_TOKEN"
CHATWOOT_TOKEN_FALLBACK_ENV = "CHATWOOT_API_TOKEN"


def recover_chatwoot_learning(*, days=14, max_pages=50, workers=8, dry_run=True, environ=None, now=None, opener=None, recorder=None, existing_key_loader=None):
    """Inventory or append historical owner-reply examples without sending anything."""
    source = os.environ if environ is None else environ
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=max(1, min(int(days), 90)))
    opener = opener or urllib_request.urlopen
    recorder = recorder or record_sales_conversation_learning_event
    conversations = _list_conversations(source, since, max_pages=max_pages, opener=opener)
    candidates = []
    skipped = {"no_messages_in_window": 0, "no_owner_reply": 0, "generated_outgoing": 0}
    histories = {}
    worker_count = max(1, min(int(workers), 12))
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {
            pool.submit(_list_messages, source, str(conversation.get("id") or "").strip(), since, opener=opener): conversation
            for conversation in conversations if str(conversation.get("id") or "").strip()
        }
        for future in as_completed(futures):
            conversation = futures[future]
            histories[str(conversation.get("id") or "").strip()] = future.result()
    for conversation in conversations:
        conversation_id = str(conversation.get("id") or "").strip()
        if not conversation_id:
            continue
        messages = histories.get(conversation_id, [])
        pairs, pair_skips = _owner_reply_pairs(conversation_id, messages, since)
        for key, value in pair_skips.items():
            skipped[key] = skipped.get(key, 0) + value
        if not messages:
            skipped["no_messages_in_window"] += 1
        candidates.extend(_learning_event(conversation, pair) for pair in pairs)

    existing_key_loader = existing_key_loader or _existing_owner_reply_keys
    existing_keys = existing_key_loader(source.get(DATABASE_URL_ENV))
    already_captured = [item for item in candidates if _event_reply_key(item) in existing_keys]
    candidates = [item for item in candidates if _event_reply_key(item) not in existing_keys]
    created = 0
    duplicates = 0
    failures = []
    if not dry_run:
        for event in candidates:
            result, status = recorder(event)
            if status >= 400:
                failures.append({"learning_event_id": event["learning_event_id"], "status": result.get("status")})
            elif result.get("created_count"):
                created += 1
            else:
                duplicates += 1
    return {
        "success": not failures,
        "status": "chatwoot_history_learning_preview_ready" if dry_run else "chatwoot_history_learning_import_complete",
        "window": {"since": since.isoformat(), "until": now.isoformat(), "days": int(days)},
        "conversation_count": len(conversations),
        "candidate_count": len(candidates),
        "already_captured_count": len(already_captured),
        "created_count": created,
        "duplicate_count": duplicates,
        "failure_count": len(failures),
        "failures": failures[:20],
        "skipped": skipped,
        "dry_run": bool(dry_run),
        "sample": [_public_candidate(item) for item in candidates[:10]],
        "authority": dict(AUTHORITY_FLAGS),
    }


def _list_conversations(source, since, *, max_pages, opener):
    rows = []
    for page in range(1, max(1, min(int(max_pages), 100)) + 1):
        payload = _get_json(source, "/conversations", {"status": "all", "assignee_type": "all", "page": page}, opener)
        data = payload.get("data") if isinstance(payload, dict) else {}
        page_rows = data.get("payload") if isinstance(data, dict) else []
        page_rows = [item for item in (page_rows or []) if isinstance(item, dict)]
        if not page_rows:
            break
        rows.extend(item for item in page_rows if _conversation_activity(item) >= since)
        if all(_conversation_activity(item) < since for item in page_rows):
            break
    return rows


def _list_messages(source, conversation_id, since, *, opener):
    rows = []
    before = None
    for _ in range(100):
        query = {"before": before} if before else {}
        payload = _get_json(source, f"/conversations/{urllib_parse.quote(conversation_id)}/messages", query, opener)
        page_rows = payload.get("payload") if isinstance(payload, dict) else []
        page_rows = [item for item in (page_rows or []) if isinstance(item, dict)]
        if not page_rows:
            break
        rows.extend(page_rows)
        oldest = min(page_rows, key=lambda item: _timestamp(item.get("created_at")))
        if _timestamp(oldest.get("created_at")) < since or len(page_rows) < 20:
            break
        next_before = oldest.get("id")
        if not next_before or str(next_before) == str(before):
            break
        before = next_before
    unique = {str(item.get("id")): item for item in rows if item.get("id") is not None}
    return sorted(
        [item for item in unique.values() if _timestamp(item.get("created_at")) >= since],
        key=lambda item: (_timestamp(item.get("created_at")), str(item.get("id"))),
    )


def _owner_reply_pairs(conversation_id, messages, since):
    pending_inbound = []
    pairs = []
    skipped = {"no_owner_reply": 0, "generated_outgoing": 0}
    for message in messages:
        if message.get("private") is True or not str(message.get("content") or "").strip():
            continue
        message_type = int(message.get("message_type") or 0)
        if message_type == 0:
            pending_inbound.append(message)
            continue
        if message_type != 1:
            continue
        if _generated_outgoing(message):
            skipped["generated_outgoing"] += 1
            continue
        if not pending_inbound:
            continue
        pairs.append({
            "conversation_id": conversation_id,
            "incoming": list(pending_inbound),
            "outgoing": message,
        })
        pending_inbound = []
    if pending_inbound:
        skipped["no_owner_reply"] += 1
    return pairs, skipped


def _learning_event(conversation, pair):
    outgoing = pair["outgoing"]
    incoming = pair["incoming"]
    conversation_id = pair["conversation_id"]
    customer_text = "\n".join(str(item.get("content") or "").strip() for item in incoming).strip()
    owner_reply = str(outgoing.get("content") or "").strip()
    outgoing_id = str(outgoing.get("id") or "")
    digest = hashlib.sha256(f"{conversation_id}|{outgoing_id}|{owner_reply}".encode("utf-8")).hexdigest()[:24]
    channel = _channel(conversation)
    return {
        "learning_event_id": f"SAM-HISTORY-{digest.upper()}",
        "lead_id": f"SAM-LIVE-CONV-{conversation_id}",
        "chatwoot_conversation_id": conversation_id,
        "channel": channel,
        "source_agent": "sam_live_stock_backend",
        "event_source": "chatwoot_historical_owner_reply",
        "event_type": "owner_review_note",
        "customer_message_excerpt": customer_text,
        "sam_reply_excerpt": "",
        "customer_wanted": {},
        "captured_facts": {
            "learning_kind": "owner_reply_historical_example",
            "owner_reply_excerpt": owner_reply,
            "owner_reply_classification": "owner_reply_no_sam_draft",
            "chatwoot_conversation_id": conversation_id,
            "incoming_message_ids": [str(item.get("id") or "") for item in incoming],
            "owner_reply_message_id": outgoing_id,
            "owner_reply_created_at": _timestamp(outgoing.get("created_at")).isoformat(),
            "reply_class": "historical_unclassified",
        },
        "missing_facts": [],
        "objections": [],
        "confusion_signals": [],
        "sam_misses": [],
        "conversion_signal": "unknown",
        "improvement_suggestion": "Use this real owner reply as private historical style and sales-conversation evidence.",
        "campaign_source": "chatwoot_historical_recovery",
        "recorded_by": "sam_live_stock_history_import",
        **AUTHORITY_FLAGS,
    }


def _get_json(source, path, query, opener):
    base = str(source.get(CHATWOOT_BASE_URL_ENV) or "https://app.chatwoot.com").strip().rstrip("/")
    account = str(source.get(CHATWOOT_ACCOUNT_ID_ENV) or "").strip()
    token = str(source.get(CHATWOOT_TOKEN_ENV) or source.get(CHATWOOT_TOKEN_FALLBACK_ENV) or "").strip()
    if not account or not token:
        raise RuntimeError("Chatwoot history import is not configured")
    suffix = f"?{urllib_parse.urlencode(query)}" if query else ""
    request = urllib_request.Request(
        f"{base}/api/v1/accounts/{urllib_parse.quote(account)}{path}{suffix}",
        headers={"api_access_token": token, "Accept": "application/json"},
        method="GET",
    )
    try:
        with opener(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8", errors="replace") or "{}")
    except urllib_error.HTTPError as exc:
        raise RuntimeError(f"Chatwoot history read failed with HTTP {exc.code}") from exc


def _conversation_activity(conversation):
    return _timestamp(conversation.get("last_activity_at") or conversation.get("updated_at") or conversation.get("created_at"))


def _timestamp(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    return (parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed).astimezone(timezone.utc)


def _generated_outgoing(message):
    attrs = message.get("content_attributes") if isinstance(message.get("content_attributes"), dict) else {}
    source = str(attrs.get("amadeus_source") or message.get("source_id") or "").lower()
    return attrs.get("sam_live_stock_generated") is True or source.startswith(("sam_live_stock:", "order_document:"))


def _channel(conversation):
    meta = conversation.get("meta") if isinstance(conversation.get("meta"), dict) else {}
    channel = str(meta.get("channel") or conversation.get("channel") or "chatwoot").strip().lower()
    return channel[:80] or "chatwoot"


def _public_candidate(event):
    captured = event.get("captured_facts") or {}
    return {
        "learning_event_id": event["learning_event_id"],
        "conversation_id": event["chatwoot_conversation_id"],
        "channel": event["channel"],
        "incoming_message_count": len(captured.get("incoming_message_ids") or []),
        "owner_reply_message_id": captured.get("owner_reply_message_id"),
        "owner_reply_created_at": captured.get("owner_reply_created_at"),
    }


def _existing_owner_reply_keys(database_url):
    if not str(database_url or "").strip():
        return set()
    import psycopg
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select chatwoot_conversation_id, captured_facts_json->>'owner_reply_excerpt'
                from public.meat_sales_conversation_learning_events
                where source_agent = 'sam_live_stock_backend'
                  and coalesce(captured_facts_json->>'owner_reply_excerpt', '') <> ''
                """
            )
            return {
                _reply_key(conversation_id, reply)
                for conversation_id, reply in cursor.fetchall()
                if conversation_id and reply
            }


def _event_reply_key(event):
    captured = event.get("captured_facts") if isinstance(event.get("captured_facts"), dict) else {}
    return _reply_key(event.get("chatwoot_conversation_id"), captured.get("owner_reply_excerpt"))


def _reply_key(conversation_id, reply):
    normalized = " ".join(str(reply or "").lower().split())
    return f"{str(conversation_id or '').strip()}|{normalized}"
