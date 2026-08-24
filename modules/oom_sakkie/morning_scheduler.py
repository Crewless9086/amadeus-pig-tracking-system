"""Authenticated provider-clock entry points for the Oom Sakkie morning runtime."""
from __future__ import annotations

from datetime import datetime, timezone
import html
import os

from modules.oom_sakkie.daily_farm_manager import daily_farm_manager_store
from modules.oom_sakkie.morning_runtime import _configured_owner, run_morning_cycle


TOKEN_ENV = "OOM_SAKKIE_MORNING_SCHEDULER_TOKEN"
SYNTHETIC_PREFIX = "synthetic_acceptance:ROOTLINE-SCHEDULE-TEST:"


def run_provider_schedule(*, environ=None, now=None):
    """Run the genuine clock entry; daily Supabase claims arbitrate all wakes."""
    return run_morning_cycle(environ=environ, now=now)


def run_synthetic_acceptance(identity, *, environ=None, now=None, store=None,
                             rootline_loader=None, deliver=None):
    """Exercise current ROOTLINE planning with no farm/provider-control authority."""
    source = environ if environ is not None else os.environ
    identity = str(identity or "").strip()
    owner = _configured_owner(source)
    if not identity.startswith(SYNTHETIC_PREFIX) or not owner:
        return _safe("synthetic_acceptance_invalid", success=False)
    store = store or daily_farm_manager_store
    claim = store("claim_daily", identity, {
        "daily_identity": identity, "status": "synthetic_acceptance_claimed",
        "observed_at": (now or datetime.now(timezone.utc)).isoformat(),
        "contract_version": "oom_sakkie_rootline_schedule_test.v1",
        "synthetic_acceptance": True})
    if not isinstance(claim, dict) or claim.get("success") is not True:
        return _safe("synthetic_acceptance_claim_unproven", success=False)
    if claim.get("created") is False:
        return _safe("synthetic_acceptance_replay_suppressed")

    try:
        if rootline_loader is None:
            from modules.oom_sakkie.farm_manager_runtime import _load_rootline
            rootline_loader = lambda: _load_rootline(now or datetime.now(timezone.utc),
                str(source.get("OOM_SAKKIE_DAILY_MANAGER_LANGUAGE") or "en"))
        result = rootline_loader()
        items = tuple(getattr(result, "work_items", ()) or ())
        if items:
            plan = "\n".join(
                f"• <b>{html.escape(item.title)}</b> — {html.escape(item.next_action)}"
                for item in items[:3])
        else:
            plan = "ROOTLINE returned a bounded hold because no supported current plan was available."
        status = "synthetic_acceptance_rootline_plan"
    except Exception as exc:
        plan = ("ROOTLINE returned a bounded hold; current planning evidence could not be "
                f"assembled ({html.escape(exc.__class__.__name__)}).")
        status = "synthetic_acceptance_rootline_bounded_failure"

    payload = {"success": True, "status": status,
        "answer": "<b>ROOTLINE SCHEDULE TEST</b>\n\n" + plan +
                  "\n\nTEST only — no farm or hardware action was authorized or performed.",
        "hardware_commands": 0, "writes_farm_data": False,
        "protected_actions_performed": False}
    parsed = {"telegram_user_id": owner, "telegram_chat_id": owner,
        "provider_message_id": "scheduled:" + identity,
        "provider_timestamp": (now or datetime.now(timezone.utc)).isoformat(),
        "text": "ROOTLINE SCHEDULE TEST"}
    if deliver is None:
        from modules.oom_sakkie.telegram_gateway import deliver_family_result
        deliver = deliver_family_result
    delivery = deliver(parsed, payload, specialist="ROOTLINE",
                       mission_id=identity, card_mission_id=identity)
    confirmed = bool((delivery or {}).get("success") and
                     (delivery or {}).get("telegram_message_id"))
    return {**_safe(status, success=confirmed),
        "provider_delivery_confirmed": confirmed,
        "telegram_message_id": str((delivery or {}).get("telegram_message_id") or ""),
        "telegram_sends": int((delivery or {}).get("telegram_sends") or 0)}


def _safe(status, *, success=True):
    return {"success": success, "status": status, "telegram_sends": 0,
            "telegram_edits": 0, "hardware_commands": 0,
            "provider_control_calls": 0, "writes_farm_data": False,
            "protected_actions_performed": False}
