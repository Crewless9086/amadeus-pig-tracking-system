"""Safe final owner front door after all context and specialist routes."""

from __future__ import annotations

import hashlib
import html
from typing import Any, Mapping


def build_owner_clarification(parsed: Mapping[str, Any]) -> dict[str, Any]:
    owner = str(parsed.get("telegram_user_id") or "")
    chat = str(parsed.get("telegram_chat_id") or "")
    provider = str(parsed.get("provider_message_id") or "")
    identity = hashlib.sha256(
        f"{owner}|{chat}|{provider}|owner-front-door-v1".encode()
    ).hexdigest()
    mission = "OOM-OWNER-CONTEXT-" + identity[:24].upper()
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), Mapping) else {}
    question = str(semantic.get("clarification_question") or "").strip()
    af = str(semantic.get("language") or parsed.get("output_language") or "en").startswith("af")
    if not question:
        question = ("Oor watter huidige plaasitem gaan dit: 'n dier of tag, water, verkope of bemarking?" if af else
                    "Which current farm item is this about: an animal or tag, water/irrigation, a customer or sale, or marketing?")
    return {
        "handled": True,
        "success": True,
        "status": "owner_context_clarification_required",
        "answer": ("<b>OOM SAKKIE — EEN BESONDERHEID NODIG</b>" if af else
                   "<b>OOM SAKKIE - ONE DETAIL NEEDED</b>") + "\n\n" + html.escape(question),
        "clarification_question": question,
        "tool_used": "owner_context_front_door",
        "mission_id": mission,
        "card_mission_id": mission,
        "question_count": 1, "read_only": True, "writes_performed": False,
        "recipient_render_contract": "canonical_read_answer_v1",
        "recipient_language": str(semantic.get("language") or "en"),
        "needs_clarification": True,
        "writes_farm_data": False,
        "writes_lifecycle": False,
        "sends_customers": False,
        "publishes": False,
        "hardware_commands": False,
        "protected_actions_performed": False,
        "trace_store": {"stored": False, "status": "family_lifecycle_owns_durable_trace"},
    }
