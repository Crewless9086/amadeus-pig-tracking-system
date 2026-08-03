"""Safe final owner front door after all context and specialist routes."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping


def build_owner_clarification(parsed: Mapping[str, Any]) -> dict[str, Any]:
    owner = str(parsed.get("telegram_user_id") or "")
    chat = str(parsed.get("telegram_chat_id") or "")
    provider = str(parsed.get("provider_message_id") or "")
    identity = hashlib.sha256(
        f"{owner}|{chat}|{provider}|owner-front-door-v1".encode()
    ).hexdigest()
    mission = "OOM-OWNER-CONTEXT-" + identity[:24].upper()
    return {
        "handled": True,
        "success": True,
        "status": "owner_context_clarification_required",
        "answer": (
            "<b>OOM SAKKIE - ONE DETAIL NEEDED</b>\n\n"
            "Which current farm item is this about: "
            "an animal or tag, water/irrigation, a customer or sale, or marketing?"
        ),
        "tool_used": "owner_context_front_door",
        "mission_id": mission,
        "card_mission_id": mission,
        "question_count": 1,
        "needs_clarification": True,
        "writes_farm_data": False,
        "writes_lifecycle": False,
        "sends_customers": False,
        "publishes": False,
        "hardware_commands": False,
        "protected_actions_performed": False,
        "trace_store": {"stored": False, "status": "family_lifecycle_owns_durable_trace"},
    }
