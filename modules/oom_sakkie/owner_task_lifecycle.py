"""Owner-request lifecycle on the existing Oom Sakkie Telegram rail.

This adapter distinguishes deployed-agent work from development-terminal work.
It creates no router, bot, specialist service, or physical authority.
"""

from __future__ import annotations

import hashlib
import html
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from modules.oom_sakkie.specialist_dispatch_ack import reconcile_specialist_dispatch


TASK_STATES = frozenset({
    "received", "assigned", "working", "waiting_for_input", "completed",
    "failed", "contained",
})
EVENT_SOURCE = "oom_sakkie_owner_task_lifecycle"
ROOTLINE_RECOVERY_REQUEST = "OOM-ROOTLINE-SMARTLIFE-CAPABILITY-REQUEST-20260801"
ROOTLINE_RESULT_ARTIFACT = "ROOTLINE-BC-AUTONOMOUS-CONTROL-CLOSURE-20260801"
ROOTLINE_RESULT_SHA256 = "0747ffe0dbf3cdaeb0badd6de3b2df43174b855616bdac3881585fae00bf1a50"
ROOTLINE_MEDIA_GROUP = "14284829442614404"
ROOTLINE_REQUEST_DELIVERED_EVENT = ROOTLINE_RECOVERY_REQUEST + "-DELIVERED"
ROOTLINE_PROVIDER_ITEMS = {
    "3157": "AQADHQ5rGyoncFN-",
    "3158": "AQADGQ5rGyoncFN-",
    "3159": "AQADHg5rGyoncFN-",
    "3160": "AQADGg5rGyoncFN-",
    "3161": "AQADGw5rGyoncFN-",
    "3162": "AQADHA5rGyoncFN-",
}
ROOTLINE_MEDIA_SHA256 = frozenset({
    "d620f5ff0ffe9aba21edbb80add05dc2a3d97633507d0153e81ee26d20bdca76",
    "9a0bdc5c3c1917084878aa9435cd84651daa7879aa8da1a9d542ac170a9af089",
    "87ca237d66d0d7288c7f239d240d6cd94275d464361c3c1fc244a4494a868cd5",
    "84aa0c0486ccd6a25c6e16c088da02e20df0ad297fcae76c481ac735646832f",
    "28c2e189b9dfcdcf6722b9e741e1b78c0bc83b8dcc8bfd57abc4c6a06f078063",
    "2b66d3c8c036c8923cfb44e962b8bcfec1a5e3e22e6eb1609e756435e4cf54c0",
})


def owner_task_input(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Normalize owner text/photo/video input without trusting client identity."""
    payload = payload if isinstance(payload, Mapping) else {}
    message = payload.get("message")
    if not isinstance(message, Mapping):
        return None
    sender = message.get("from") if isinstance(message.get("from"), Mapping) else {}
    chat = message.get("chat") if isinstance(message.get("chat"), Mapping) else {}
    photos = message.get("photo") if isinstance(message.get("photo"), list) else []
    video = message.get("video") if isinstance(message.get("video"), Mapping) else None
    text = str(message.get("text") or message.get("caption") or "").strip()
    if photos:
        candidates = [row for row in photos if isinstance(row, Mapping) and row.get("file_id")]
        media = max(candidates, key=lambda row: int(row.get("file_size") or 0), default={})
        kind = "photo"
    elif video:
        media, kind = video, "video"
    elif text:
        media, kind = {}, "text"
    else:
        return None
    stamp = message.get("date")
    if not isinstance(stamp, (int, float)):
        return None
    return {
        "update_id": str(payload.get("update_id") or ""),
        "message_id": str(message.get("message_id") or ""),
        "owner_user_id": str(sender.get("id") or ""),
        "chat_id": str(chat.get("id") or ""),
        "chat_type": str(chat.get("type") or ""),
        "provider_message_at": datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
        "media_group_id": str(message.get("media_group_id") or "")[:160],
        "item_kind": kind,
        "text": text[:2000],
        "file_id": str(media.get("file_id") or "")[:300],
        "file_unique_id": str(media.get("file_unique_id") or "")[:300],
        "declared_file_size": int(media.get("file_size") or 0),
        "declared_mime_type": str(media.get("mime_type") or ("image/jpeg" if kind == "photo" else ""))[:120],
    }


def task_identity(request_id: str, envelope: Mapping[str, Any]) -> str:
    response = envelope.get("media_group_id") or envelope.get("message_id")
    raw = "|".join((request_id, str(envelope.get("owner_user_id")), str(envelope.get("chat_id")), str(response)))
    return "OOM-TASK-" + hashlib.sha256(raw.encode()).hexdigest()[:24].upper()


def handle_owner_task_input(
    payload: Mapping[str, Any], *, environ=None, now=None,
    request_loader: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
    event_loader: Callable[[str], list[Mapping[str, Any]]] | None = None,
    event_recorder: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    media_reader: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
    telegram_sender: Callable[[str, str, str], Mapping[str, Any]] | None = None,
    specialist_dispatcher: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    dispatch_reconciler: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    delivery_reconciler: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], int]:
    """Bind one update to an active request and advance one durable task."""
    source = environ if environ is not None else os.environ
    envelope = owner_task_input(payload)
    if envelope is None:
        return {"handled": False, "status": "owner_task_input_not_applicable"}, 200
    allowed = {part.strip() for part in str(source.get("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS") or "").split(",") if part.strip()}
    if envelope["chat_type"] != "private" or envelope["owner_user_id"] not in allowed or envelope["chat_id"] not in allowed:
        return {"handled": False, "status": "owner_task_owner_binding_unmatched"}, 200
    request = dict((request_loader or _load_active_request)(envelope) or {})
    if not request:
        return {"handled": False, "status": "owner_task_active_request_not_found"}, 200
    if request.get("owner_user_id") != envelope["owner_user_id"] or request.get("chat_id") != envelope["chat_id"]:
        return {"handled": True, "success": False, "status": "owner_task_request_identity_mismatch"}, 409
    expected_provider_items = dict(request.get("expected_provider_items") or {})
    if expected_provider_items and expected_provider_items.get(envelope["message_id"]) != envelope.get("file_unique_id"):
        return {"handled": True, "success": False, "status": "owner_task_provider_media_identity_mismatch"}, 409
    request_at = _time(request.get("request_delivered_at"))
    received_at = _time(envelope["provider_message_at"])
    if not request_at or not received_at or received_at < request_at:
        return {"handled": True, "success": False, "status": "owner_task_response_predates_request"}, 409
    task_id = task_identity(str(request["request_id"]), envelope)
    load = event_loader or _load_task_events
    record = event_recorder or _record_task_event
    existing = [dict(row) for row in load(task_id)]
    received_probe = _event(task_id, request, "received", envelope)
    already_received = any(row.get("event_id") == received_probe["event_id"] for row in existing)
    if envelope["item_kind"] == "video" and already_received:
        return {"handled": True, "success": False, "status": "owner_task_video_intake_contained",
                "task_id": task_id, "media_writes": 0}, 415
    media = {}
    if envelope["item_kind"] == "video" and not already_received:
        contained = _event(task_id, request, "contained", envelope, event_id=received_probe["event_id"],
            detail={"reason": "owner_task_video_intake_not_supported", "media_writes": 0})
        record(contained)
        return {"handled": True, "success": False, "status": "owner_task_video_intake_contained",
                "task_id": task_id, "media_writes": 0}, 415
    if envelope["item_kind"] == "photo" and not already_received:
        media = dict((media_reader or _store_owner_media)(envelope, task_id))
        if not media.get("content_sha256") or media.get("readback_verified") is not True:
            return {"handled": True, "success": False, "status": "owner_task_media_verification_failed", "task_id": task_id}, 409
    if not already_received:
        received_event = _event(task_id, request, "received", envelope, media=media)
        record(received_event)
    # Reload after the atomic item claim so concurrent final album arrivals can
    # each observe the complete authoritative aggregate on retry.
    existing = [dict(row) for row in load(task_id)]
    items = _received_items(existing)
    expected = int(request.get("expected_item_count") or 1)
    complete_input = len(items) == expected
    if not complete_input:
        return {"handled": True, "success": True, "status": "owner_task_album_receiving", "task_id": task_id,
                "received_items": len(items), "expected_items": expected, "acknowledgements": 0}, 202

    ack_sent, ack_ready = _deliver_once(task_id, request, envelope, existing, record,
        telegram_sender or _send_owner_html, delivery_reconciler,
        purpose="acknowledgement", state="received",
        text=_ack_text(len(items), _item_types(items)),
        detail={"acknowledgement": True, "item_count": len(items), "item_types": _item_types(items)})
    if not ack_ready:
        return {"handled": True, "success": False, "status": "owner_task_acknowledgement_delivery_unresolved",
                "task_id": task_id, "provider_reconciliation_required": True,
                "acknowledgements": 0, "results": 0, "dispatches": 0}, 202

    hashes = sorted(str(item.get("media", {}).get("content_sha256") or "").lower() for item in items if item.get("media"))
    provider_items = {str(item.get("provider_message_id")): str(item.get("file_unique_id")) for item in items}
    prepared_input_exact = (
        len(items) == expected
        and hashes == sorted(str(value).lower() for value in request.get("expected_media_sha256") or ())
        and (not expected_provider_items or provider_items == expected_provider_items)
    )
    if request.get("prepared_result_sha256") and prepared_input_exact:
        return _complete_prepared_result(task_id, request, envelope, existing, record,
            telegram_sender, delivery_reconciler, ack_sent)

    record(_event(task_id, request, "assigned", envelope, detail={"specialist": request["specialist_identity"]}))
    if specialist_dispatcher is None:
        alerts, alert_ready = _deliver_once(task_id, request, envelope, existing, record,
            telegram_sender or _send_owner_html, delivery_reconciler,
            purpose="no-adapter", state="contained",
            text=_no_adapter_exception_text(request["specialist_identity"]),
            detail={"reason": "deployed_specialist_adapter_unavailable", "development_terminal_required": True})
        if not alert_ready:
            return {"handled": True, "success": False, "status": "owner_task_exception_delivery_unresolved",
                    "task_id": task_id, "provider_reconciliation_required": True,
                    "automatic_execution_claimed": False}, 202
        return {"handled": True, "success": True, "status": "owner_task_contained_no_deployed_specialist_adapter",
                "task_id": task_id, "acknowledgements": ack_sent, "systemic_exceptions": alerts,
                "development_terminal_required": True, "automatic_execution_claimed": False}, 202

    dispatch, dispatch_sent, dispatch_ready = _dispatch_once(
        task_id, request, envelope, items, existing, record, specialist_dispatcher, dispatch_reconciler)
    if not dispatch_ready:
        return {"handled": True, "success": False, "status": "owner_task_dispatch_delivery_unresolved",
                "task_id": task_id, "acknowledgements": ack_sent, "results": 0,
                "dispatches": 0, "provider_reconciliation_required": True}, 202
    dispatch_events = list(dispatch.get("events") or [])
    if not _dispatch_matches_request(request, dispatch_events):
        record(_event(task_id, request, "contained", envelope, event_id=task_id + "-DISPATCH-MISMATCH",
            detail={"reason": "specialist_dispatch_binding_mismatch"}))
        return {"handled": True, "success": False, "status": "owner_task_dispatch_binding_mismatch",
                "task_id": task_id, "automatic_execution_claimed": False}, 409
    snapshot = reconcile_specialist_dispatch(dispatch_events, now=now or datetime.now(timezone.utc))
    state = "completed" if snapshot.completed else "working" if snapshot.execution_started else "waiting_for_input"
    state_record = record(_event(task_id, request, state, envelope, detail={"dispatch_snapshot": snapshot.to_dict()}))
    results = 0
    owner_result_html = str(dispatch.get("owner_result_html") or "")
    expected_result_sha = str((request.get("dispatch_binding") or {}).get("owner_result_sha256") or "").lower()
    if state == "completed" and hashlib.sha256(owner_result_html.encode("utf-8")).hexdigest() != expected_result_sha:
        record(_event(task_id, request, "contained", envelope, event_id=task_id + "-RESULT-BYTES-MISMATCH",
            detail={"reason": "owner_result_bytes_not_bound_to_artifact"}))
        return {"handled": True, "success": False, "status": "owner_task_result_bytes_mismatch",
                "task_id": task_id, "results": 0}, 409
    if state == "completed" and owner_result_html:
        results, ready = _deliver_once(task_id, request, envelope, existing, record,
            telegram_sender or _send_owner_html, delivery_reconciler,
            purpose="completion", state="completed", text=owner_result_html,
            detail={"dispatch_snapshot": snapshot.to_dict()})
        if not ready:
            return {"handled": True, "success": False, "status": "owner_task_completion_delivery_unresolved",
                    "task_id": task_id, "provider_reconciliation_required": True}, 202
    return {"handled": True, "success": True, "status": "owner_task_dispatched", "task_id": task_id,
            "task_state": state, "dispatch_state": snapshot.state, "acknowledgements": ack_sent,
            "results": results, "dispatches": dispatch_sent}, 200 if state == "completed" else 202


def monitor_owner_task_dispatch(task, dispatch_events, *, now, event_recorder, telegram_sender,
                                lifecycle_events=(), delivery_reconciler=None):
    """Turn a missed deployed-agent acknowledgement/start into one alert."""
    snapshot = reconcile_specialist_dispatch(dispatch_events, now=now)
    if snapshot.state != "ack_timeout" or snapshot.alert is None:
        return {"success": True, "status": "owner_task_dispatch_current", "dispatch_state": snapshot.state,
                "systemic_exceptions": 0}
    alert = snapshot.alert.to_dict() if hasattr(snapshot.alert, "to_dict") else snapshot.to_dict()["alert"]
    task_id = str(task["task_id"])
    envelope = dict(task["envelope"])
    request = dict(task["request"])
    reason = str(alert.get("reason") or "")
    sent, ready = _deliver_once(task_id, request, envelope, list(lifecycle_events), event_recorder,
        telegram_sender, delivery_reconciler, purpose="dispatch-timeout", state="contained",
        text=_dispatch_timeout_text(request["specialist_identity"], reason),
        detail={"dispatch_alert": alert, "development_terminal_required": True})
    return {"success": ready,
            "status": "owner_task_dispatch_timeout_contained" if ready else "owner_task_dispatch_timeout_delivery_unresolved",
            "dispatch_state": snapshot.state, "systemic_exceptions": sent,
            "provider_reconciliation_required": not ready,
            "automatic_execution_claimed": False}


def _complete_prepared_result(task_id, request, envelope, existing, record, sender,
                              delivery_reconciler, acknowledgements):
    record(_event(task_id, request, "assigned", envelope, detail={
        "specialist": request["specialist_identity"], "result_source": "prepared_specialist_result"}))
    record(_event(task_id, request, "working", envelope, detail={
        "working_agent_identity": "oom-sakkie-agent",
        "work_type": "prepared_specialist_result_reconciliation",
        "specialist_agent_dispatched": False, "development_terminal_started": False}))
    results, ready = _deliver_once(task_id, request, envelope, existing, record,
        sender or _send_owner_html, delivery_reconciler, purpose="completion", state="working",
        text=_rootline_completion_text(), detail={
            "outcome_artifact_id": request["prepared_result_id"],
            "outcome_artifact_sha256": request["prepared_result_sha256"],
            "specialist_agent_dispatched": False, "hardware_actions": 0})
    if not ready:
        return {"handled": True, "success": False, "status": "owner_task_completion_delivery_unresolved",
                "task_id": task_id, "provider_reconciliation_required": True,
                "specialist_agent_dispatched": False, "hardware_actions": 0}, 202
    record(_event(task_id, request, "completed", envelope, event_id=task_id + "-COMPLETED",
        detail={"outcome_artifact_id": request["prepared_result_id"],
                "outcome_artifact_sha256": request["prepared_result_sha256"],
                "specialist_agent_dispatched": False, "result_delivered": True, "hardware_actions": 0}))
    return {"handled": True, "success": True, "status": "owner_task_completed_from_prepared_specialist_result",
            "task_id": task_id, "task_state": "completed", "acknowledgements": acknowledgements,
            "results": results, "specialist_agent_dispatched": False, "development_terminal_started": False,
            "hardware_actions": 0}, 200


def _load_active_request(envelope):
    import psycopg
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute("""select created_at, review_json->'owner_task_request'
                    from public.sam_live_stock_conversation_review_events
                    where review_json ? 'owner_task_request'
                    order by created_at desc limit 20""")
                generic_rows = cursor.fetchall()
                row = None
                if envelope.get("media_group_id") == ROOTLINE_MEDIA_GROUP:
                    cursor.execute("""select created_at, review_json->'rootline_device_evidence_request'
                        from public.sam_live_stock_conversation_review_events
                        where review_event_id=%s and chatwoot_conversation_id=%s""",
                        (ROOTLINE_REQUEST_DELIVERED_EVENT, ROOTLINE_RECOVERY_REQUEST))
                    row = cursor.fetchone()
    except (KeyError, psycopg.Error):
        return None
    received_at = _time(envelope.get("provider_message_at"))
    active = []
    for created_at, packet in generic_rows:
        if not isinstance(packet, Mapping):
            continue
        candidate = dict(packet)
        if not all(str(candidate.get(key) or "") for key in
                   ("request_id", "specialist_identity", "request_delivered_at",
                    "owner_user_id", "chat_id")):
            continue
        expires = _time(candidate.get("expires_at"))
        delivered = _time(candidate.get("request_delivered_at"))
        if (candidate.get("state") == "waiting_for_input"
                and str(candidate.get("owner_user_id") or "") == envelope.get("owner_user_id")
                and str(candidate.get("chat_id") or "") == envelope.get("chat_id")
                and delivered and received_at and received_at >= delivered
                and (expires is None or received_at <= expires)
                and envelope.get("item_kind") in set(candidate.get("allowed_item_kinds") or ())):
            active.append(candidate)
    if len(active) == 1:
        return active[0]
    if len(active) > 1 or envelope.get("media_group_id") != ROOTLINE_MEDIA_GROUP:
        return None
    # The first recovery request predates the generic owner_task_request
    # contract. It remains eligible only with its exact durable delivery row.
    if not row or not isinstance(row[1], Mapping):
        return None
    evidence = dict(row[1])
    if evidence.get("state") != "delivered" or str(evidence.get("telegram_message_id") or "") != "3156":
        return None
    owner = str(os.environ.get("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID")
                or os.environ.get("SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID") or "").strip()
    chat = str(os.environ.get("OOM_SAKKIE_TELEGRAM_OWNER_CHAT_ID")
               or os.environ.get("SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID") or "").strip()
    if not owner or not chat:
        return None
    delivered_at = row[0].astimezone(timezone.utc).isoformat() if getattr(row[0], "tzinfo", None) else str(row[0])
    return {
        "request_id": ROOTLINE_RECOVERY_REQUEST,
        "request_message_id": "3156",
        "request_delivered_at": delivered_at,
        "owner_user_id": owner,
        "chat_id": chat,
        "specialist_identity": "ROOTLINE",
        "decision_type": "controller_capability_evidence",
        "expected_item_count": 6,
        "expected_provider_items": dict(ROOTLINE_PROVIDER_ITEMS),
        "expected_media_sha256": tuple(sorted(ROOTLINE_MEDIA_SHA256)),
        "prepared_result_id": ROOTLINE_RESULT_ARTIFACT,
        "prepared_result_sha256": ROOTLINE_RESULT_SHA256,
    }


def _load_task_events(task_id):
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'owner_task' from public.sam_live_stock_conversation_review_events
                where review_json->'owner_task'->>'task_id'=%s order by created_at,review_event_id""", (task_id,))
            return [row[0] for row in cursor.fetchall()]


def _dispatch_matches_request(request, events):
    binding = request.get("dispatch_binding")
    if not isinstance(binding, Mapping) or not events:
        return False
    required = ("mission_id", "target_worker_id", "release_digest",
                "outcome_artifact_id", "outcome_artifact_sha256", "owner_result_sha256")
    if any(not str(binding.get(key) or "") for key in required):
        return False
    for event in events:
        if any(str(event.get(key) or "") != str(binding[key])
               for key in ("mission_id", "target_worker_id", "release_digest")):
            return False
    completions = [event for event in events if event.get("state") == "completed"]
    return all(
        str(event.get("outcome_artifact_id") or "") == str(binding["outcome_artifact_id"])
        and str(event.get("outcome_artifact_sha256") or "").lower()
            == str(binding["outcome_artifact_sha256"]).lower()
        and event.get("outcome_status") == "completed"
        for event in completions
    )


def _dispatch_once(task_id, request, envelope, items, existing, record, dispatcher, reconciler):
    """Dispatch once, or reconcile an accepted call before any bounded retry."""
    attempted_id = task_id + "-DISPATCH-ATTEMPT"
    delivered_id = task_id + "-DISPATCH-DELIVERED"
    delivered = next((row for row in existing if row.get("event_id") == delivered_id), None)
    if delivered:
        packet = dict(delivered.get("detail", {}).get("dispatch_packet") or {})
        if reconciler is not None:
            proof = dict(reconciler({"task_id": task_id,
                "dispatch_binding": dict(request.get("dispatch_binding") or {})}) or {})
            refreshed = dict(proof.get("dispatch_packet") or {})
            if str(proof.get("status") or "") in {"delivered", "progress_observed", "completed"} and refreshed:
                packet = refreshed
        return packet, 0, bool(packet)
    attempted = any(row.get("event_id") == attempted_id for row in existing)
    if not attempted:
        claimed = record(_event(task_id, request, "assigned", envelope, event_id=attempted_id,
            detail={"dispatch_state": "attempted", "dispatch_binding": dict(request.get("dispatch_binding") or {})}))
        attempted = claimed.get("created") is False
    packet = None
    if attempted:
        if reconciler is None:
            return {}, 0, False
        proof = dict(reconciler({"task_id": task_id,
            "dispatch_binding": dict(request.get("dispatch_binding") or {})}) or {})
        proof_state = str(proof.get("status") or "ambiguous")
        if proof_state == "delivered":
            packet = dict(proof.get("dispatch_packet") or {})
            receipt = str(proof.get("delivery_receipt_id") or packet.get("delivery_receipt_id") or "")
            if not receipt or not packet:
                return {}, 0, False
            record(_event(task_id, request, "assigned", envelope, event_id=delivered_id,
                detail={"dispatch_state": "delivered", "delivery_reconciled": True,
                        "delivery_receipt_id": receipt, "dispatch_packet": packet}))
            return packet, 0, True
        if proof_state != "conclusively_absent":
            return {}, 0, False
    try:
        packet = dict(dispatcher({"task_id": task_id, "request": request, "items": items}) or {})
    except Exception:
        return {}, 0, False
    receipt = str(packet.get("delivery_receipt_id") or "")
    if not receipt:
        return {}, 0, False
    record(_event(task_id, request, "assigned", envelope, event_id=delivered_id,
        detail={"dispatch_state": "delivered", "delivery_receipt_id": receipt,
                "dispatch_packet": packet}))
    return packet, 1, True


def _record_task_event(event):
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    base = build_sam_live_stock_review_event({"conversation_id": event["task_id"]}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "owner_task_lifecycle"}, event_source=EVENT_SOURCE)
    base["review_event_id"] = event["event_id"]
    base["chatwoot_conversation_id"] = event["task_id"]
    base["review_json"] = {"owner_task": event}
    result, status = record_sam_live_stock_review_event(base)
    if status >= 400 or not result.get("success"):
        raise RuntimeError("owner_task_event_persistence_failed")
    return result


def _store_owner_media(envelope, task_id):
    from modules.beacon.media_intake import (
        MAX_IMAGE_BYTES, SupabasePrivateStorage, _download_telegram_file, _validate_streamed_image,
    )
    temp_path = None
    try:
        source = dict(os.environ)
        canonical_token = str(source.get("SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN") or "").strip()
        if not canonical_token:
            raise RuntimeError("owner_task_canonical_bot_token_not_configured")
        # Request 3156 and GateKeeper's owner trigger use the existing SAM/Oom
        # owner bot. Force the media helper onto that same bot identity even if
        # the disabled direct route has a different legacy token configured.
        source["OOM_SAKKIE_TELEGRAM_BOT_TOKEN"] = canonical_token
        temp_path, download = _download_telegram_file(envelope, source)
        validated = _validate_streamed_image(temp_path, envelope["declared_mime_type"], download)
        suffix = ".jpg" if validated["observed_mime_type"] == "image/jpeg" else ".png"
        path = f"owner-tasks/{task_id}/{envelope['message_id']}-{validated['content_sha256']}{suffix}"
        body = Path(temp_path).read_bytes()
        storage = SupabasePrivateStorage(source)
        uploaded = storage.put(path, body, validated["observed_mime_type"])
        if uploaded.get("success") is not True:
            raise RuntimeError("owner_task_private_upload_failed")
        readback = storage.get(path, MAX_IMAGE_BYTES)
        readback_sha = hashlib.sha256(readback).hexdigest()
        return {**validated, "storage_path": path, "readback_sha256": readback_sha,
                "readback_verified": readback_sha == validated["content_sha256"]}
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


def _event(task_id, request, state, envelope, *, event_id="", media=None, detail=None):
    if state not in TASK_STATES:
        raise ValueError("owner_task_state_invalid")
    source_id = envelope.get("file_unique_id") or envelope.get("message_id")
    eid = event_id or "OOM-TASK-EVENT-" + hashlib.sha256(
        f"{task_id}|{state}|{source_id}".encode()).hexdigest()[:24].upper()
    return {"event_id": eid, "task_id": task_id, "request_id": request["request_id"], "state": state,
        "specialist_identity": request["specialist_identity"], "owner_user_id": envelope["owner_user_id"],
        "chat_id": envelope["chat_id"], "provider_message_id": envelope["message_id"],
        "provider_message_at": envelope["provider_message_at"], "media_group_id": envelope.get("media_group_id") or "",
        "item_kind": envelope["item_kind"], "file_unique_id": envelope.get("file_unique_id") or "",
        "media": dict(media or {}), "detail": dict(detail or {})}


def _received_items(events):
    rows = [row for row in events if row.get("state") == "received" and not row.get("detail", {}).get("acknowledgement")]
    unique = {}
    for row in rows:
        unique[(row.get("provider_message_id"), row.get("file_unique_id"), row.get("item_kind"))] = row
    return list(unique.values())


def _deliver_once(task_id, request, envelope, existing, record, sender, reconciler,
                  *, purpose, state, text, detail):
    """Claim, reconcile, and confirm one Telegram delivery without blind retry."""
    token = hashlib.sha256(f"{task_id}|{purpose}".encode()).hexdigest()[:20].upper()
    attempt_id = f"OOM-TASK-DELIVERY-{token}-ATTEMPT"
    delivered_id = f"OOM-TASK-DELIVERY-{token}-DELIVERED"
    delivered = next((row for row in existing if row.get("event_id") == delivered_id), None)
    if delivered:
        provider_id = str(delivered.get("detail", {}).get("telegram_message_id") or "")
        return 0, bool(provider_id)
    attempted = any(row.get("event_id") == attempt_id for row in existing)
    if not attempted:
        claimed = record(_event(task_id, request, state, envelope, event_id=attempt_id,
            detail={**detail, "delivery_purpose": purpose, "delivery_state": "attempted",
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}))
        attempted = claimed.get("created") is False
    if attempted:
        if reconciler is None:
            return 0, False
        proof = dict(reconciler({"task_id": task_id, "purpose": purpose,
            "owner_user_id": envelope["owner_user_id"], "chat_id": envelope["chat_id"],
            "attempt_event_id": attempt_id, "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}) or {})
        proof_state = str(proof.get("status") or "ambiguous")
        if proof_state == "delivered" and str(proof.get("telegram_message_id") or ""):
            record(_event(task_id, request, state, envelope, event_id=delivered_id,
                detail={**detail, "delivery_purpose": purpose, "delivery_reconciled": True,
                        "telegram_message_id": str(proof["telegram_message_id"])}))
            return 0, True
        if proof_state != "conclusively_absent":
            return 0, False
    result = dict(sender(envelope["chat_id"], text, purpose) or {})
    provider_id = str(result.get("telegram_message_id") or "")
    if result.get("success") is not True or not provider_id:
        return 0, False
    record(_event(task_id, request, state, envelope, event_id=delivered_id,
        detail={**detail, "delivery_purpose": purpose, "delivery_state": "delivered",
                "telegram_message_id": provider_id}))
    return 1, True


def _item_types(items):
    counts = {}
    for item in items:
        kind = str(item.get("item_kind") or "item")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _ack_text(count, types):
    label = ", ".join(f"{value} {key}{'' if value == 1 else 's'}" for key, value in sorted(types.items()))
    return f"📥 <b>EVIDENCE RECEIVED</b>\n\nI received <b>{count}</b> items ({html.escape(label)}). I’m checking them against your exact request now."


def _no_adapter_exception_text(specialist):
    return (f"⚠️ <b>{html.escape(str(specialist))} FOLLOW-UP WAITING</b>\n\n"
            "Your evidence is safely retained, but no deployed specialist-agent adapter can accept this task yet. "
            "Development-terminal work is required; I will not claim automatic execution.")


def _dispatch_timeout_text(specialist, reason):
    status = ("the deployed specialist agent did not acknowledge this exact task"
              if reason == "delivery_acknowledgement_missing"
              else "the deployed specialist agent acknowledged the task but no fresh task-specific start was observed")
    return (f"⚠️ <b>{html.escape(str(specialist))} FOLLOW-UP WAITING</b>\n\n"
            f"Your evidence is safely retained, but {status}. "
            "Development-terminal investigation is required; I will not claim automatic execution.")


def _rootline_completion_text():
    return ("✅ <b>CONTROLLER CHECK COMPLETE</b>\n\n"
            "The controller supports independent native auto-OFF for each channel, with a maximum of <b>60 minutes</b>.\n\n"
            "Future unattended irrigation may use separately authorized runs of at most 60 minutes after commissioning. "
            "One uninterrupted 120-minute run requires an independent interval safety relay.\n\n"
            "No controller setting or hardware state was changed.")


def _send_owner_html(chat_id, text, purpose):
    from modules.oom_sakkie.telegram_direct import send_owner_telegram_reply
    result, _ = send_owner_telegram_reply(chat_id, text, parse_mode="HTML")
    return result


def _time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
