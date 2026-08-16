"""Durable deployed presentation worker for completed private BEACON albums."""
from __future__ import annotations

import os
import threading

from modules.beacon.media_intake import latest_pending_private_album_review
from modules.oom_sakkie.beacon_media_review_runtime import present_private_media_review
from modules.oom_sakkie.protected_action_claims import bind_claim_card

POLL_SECONDS = 60
ENABLED_ENV = "BEACON_TELEGRAM_MEDIA_INTAKE_ENABLED"
OWNER_ENV = "OOM_SAKKIE_DAILY_MANAGER_OWNER_USER_ID"
_START_LOCK = threading.Lock()
_STARTED = False


def run_private_media_review_cycle(*, environ=None, album_loader=None,
                                   presenter=None, deliver=None, binder=None,
                                   lifecycle_loader=None):
    """Present the latest completed pending album through the canonical card."""
    source = environ if environ is not None else os.environ
    owner = _configured_owner(source)
    if not _truthy(source.get(ENABLED_ENV)):
        return _safe("private_media_review_worker_disabled")
    if not owner:
        return _safe("private_media_review_worker_owner_binding_unavailable", success=False)

    album_loader = album_loader or latest_pending_private_album_review
    packet, status = album_loader(owner_user_id=owner, private_chat_id=owner)
    if status == 404:
        return _safe("private_media_review_worker_no_completed_album")
    if status >= 400 or packet.get("success") is not True:
        return _safe("private_media_review_worker_evidence_unavailable", success=False)
    if packet.get("library_state") != "pending_or_mixed":
        return _safe("private_media_review_worker_no_pending_library_decision")
    group_id = str(packet.get("intake_group_id") or "")
    completed_at = str(packet.get("album_completed_at") or "")
    if not group_id or not completed_at:
        return _safe("private_media_review_worker_trigger_identity_unavailable", success=False)

    if lifecycle_loader is None:
        from modules.oom_sakkie.family_message_lifecycle import load_family_lifecycle
        lifecycle_loader = load_family_lifecycle
    events=list(lifecycle_loader(group_id) or [])
    completed=next((row for row in reversed(events)
        if row.get("state") in {"delivered","updated"}
        and str(row.get("task_state") or "")=="completed"
        and str(row.get("mission_id") or "")==group_id),None)
    latest=next((row for row in reversed(events)
        if row.get("state") in {"delivered","updated"}),None)
    message_id=str((completed or {}).get("telegram_message_id") or "")
    exact_completed=(completed is not None
        and str(completed.get("card_mission_id") or "")==group_id
        and str(completed.get("specialist_identity") or "")=="BEACON_MEDIA"
        and str(completed.get("owner_user_id") or "")==owner
        and str(completed.get("chat_id") or "")==owner and bool(message_id))
    exact_latest=(latest is not None
        and str(latest.get("mission_id") or "") in {group_id,group_id+":LIBRARY"}
        and str(latest.get("card_mission_id") or "")==group_id
        and str(latest.get("specialist_identity") or "")=="BEACON_MEDIA"
        and str(latest.get("owner_user_id") or "")==owner
        and str(latest.get("chat_id") or "")==owner
        and str(latest.get("telegram_message_id") or "")==message_id)
    exact_card=exact_completed and exact_latest
    if not exact_card:
        return _safe("private_media_review_worker_completed_card_unproven", success=False)

    parsed = {
        "telegram_user_id": owner,
        "telegram_chat_id": owner,
        "provider_message_id": "canonical:album-completed:" + group_id,
        "provider_timestamp": completed_at,
        "text": "Completed private album requires Library review",
        "semantic": {"language": str(source.get("OOM_SAKKIE_DAILY_MANAGER_LANGUAGE") or "en")},
    }
    presenter = presenter or present_private_media_review
    result, result_status = presenter(parsed, album_loader=lambda **_: (packet, 200))
    if result_status >= 400 or result.get("success") is not True:
        return {**_safe("private_media_review_worker_claim_contained", success=False),
                "result_status": result.get("status")}
    result = {**result, "card_mission_id": group_id,
              "owner_visible_completion_policy": "verified_edit_or_new_message"}

    if deliver is None:
        from modules.oom_sakkie.telegram_gateway import deliver_family_result
        deliver = deliver_family_result
    delivery = deliver(parsed, result, specialist="BEACON_MEDIA",
                       mission_id=result["mission_id"], card_mission_id=group_id)
    delivered_message_id = str((delivery or {}).get("telegram_message_id") or "")
    provider_confirmed = bool((delivery or {}).get("provider_delivery_confirmed") is True
        or ((delivery or {}).get("success") is True and delivered_message_id))
    if provider_confirmed and delivered_message_id:
        binder = binder or bind_claim_card
        if not binder(result.get("callback_token"), delivered_message_id):
            return {**_safe("private_media_review_worker_card_binding_pending", success=False),
                    "telegram_message_id": delivered_message_id}
    if (delivery or {}).get("success") is not True or not delivered_message_id:
        return {**_safe("private_media_review_worker_delivery_unconfirmed", success=False),
                "delivery_status": (delivery or {}).get("status") or "unknown",
                "provider_delivery_confirmed":provider_confirmed,
                "telegram_message_id":delivered_message_id}
    return {**_safe("private_media_review_presented"),
            "intake_group_id": group_id, "album_digest": packet.get("album_digest"),
            "provider_trigger_id": parsed["provider_message_id"],
            "telegram_message_id": delivered_message_id,
            "telegram_sends": int(delivery.get("telegram_sends") or 0),
            "telegram_edits": int(delivery.get("telegram_edits") or 0),
            "provider_delivery_confirmed": True}


def start_private_media_review_worker(*, environ=None, runner=None):
    """Start one daemon per process; durable claims arbitrate scaled workers."""
    global _STARTED
    source = environ if environ is not None else os.environ
    if not _truthy(source.get(ENABLED_ENV)):
        return False
    with _START_LOCK:
        if _STARTED:
            return False
        _STARTED = True
        threading.Thread(target=runner or _runtime_loop, kwargs={"environ": source},
                         name="beacon-private-media-review-worker", daemon=True).start()
        return True


def _runtime_loop(*, environ):
    import time
    while True:
        try:
            run_private_media_review_cycle(environ=environ)
        except Exception:
            pass
        time.sleep(POLL_SECONDS)


def _configured_owner(source):
    explicit = str(source.get(OWNER_ENV) or "").strip()
    allowed = {item.strip() for item in str(
        source.get("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS") or "").split(",") if item.strip()}
    if explicit:
        return explicit if explicit in allowed else ""
    return next(iter(allowed)) if len(allowed) == 1 else ""


def _safe(status, *, success=True):
    return {"success": success, "status": status, "telegram_sends": 0,
            "telegram_edits": 0, "publishes": False, "schedules": False,
            "customer_sends": False, "spends_money": False,
            "writes_farm_data": False, "hardware_commands": 0,
            "meta_calls": 0, "n8n_mutations": 0,
            "google_sheets_mutations": 0}


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
