"""Owner notification for canonical v2 response-class authority candidates."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Callable, Mapping

from modules.sales.conversation_learning import AUTHORITY_FLAGS


GRADUATION_NOTIFICATION_ENABLED_ENV = "SAM_LIVE_STOCK_GRADUATION_NOTIFICATION_ENABLED"
TELEGRAM_BOT_TOKEN_ENV = "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN"
TELEGRAM_BOT_TOKEN_FALLBACK_ENV = "OOM_SAKKIE_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID"


def notify_new_graduation_candidates(
    *,
    scorecard_loader: Callable[[], tuple[dict[str, Any], int]],
    event_recorder: Callable[[dict[str, Any]], tuple[dict[str, Any], int]],
    telegram_sender: Callable[[str, str, str, dict[str, Any] | None], Any],
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    source = environ if environ is not None else os.environ
    if not _truthy(source.get(GRADUATION_NOTIFICATION_ENABLED_ENV, "1")):
        return _result("graduation_notification_disabled", attempted=False)
    token = str(source.get(TELEGRAM_BOT_TOKEN_ENV) or source.get(TELEGRAM_BOT_TOKEN_FALLBACK_ENV) or "").strip()
    chat_id = str(source.get(TELEGRAM_CHAT_ID_ENV) or "").strip()
    if not token or not chat_id:
        return _result("graduation_notification_not_configured", attempted=False)

    loaded, status_code = scorecard_loader()
    if status_code >= 400 or not loaded.get("success"):
        return _result("graduation_scorecard_unavailable", attempted=True, scorecard_status_code=status_code)
    scorecard = loaded.get("scorecard") if isinstance(loaded.get("scorecard"), Mapping) else {}
    graduation = (
        scorecard.get("graduation")
        if isinstance(scorecard.get("graduation"), Mapping)
        else scorecard
    )
    if graduation.get("version") != "sam_response_class_graduation_v2":
        return _result("canonical_v2_scorecard_required", attempted=True)
    classes = graduation.get("classes") or {}
    notified = []
    for reply_class, evidence in sorted(classes.items()):
        if not isinstance(evidence, Mapping) or evidence.get("decision") != "candidate":
            continue
        event = _notification_event(str(reply_class), evidence)
        recorded, record_status = event_recorder(event)
        if record_status >= 400 or not recorded.get("success") or not int(recorded.get("created_count") or 0):
            continue
        telegram_sender(token, chat_id, _notification_text(str(reply_class), evidence), _notification_keyboard(str(reply_class)))
        notified.append(str(reply_class))
    return _result(
        "graduation_candidates_notified" if notified else "no_new_graduation_candidates",
        attempted=True,
        notified_reply_classes=notified,
        notification_count=len(notified),
    )


def _notification_event(reply_class: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    metrics = dict(evidence.get("evidence") or {})
    digest = hashlib.sha256(
        json.dumps(
            {
                "version": "sam_response_class_graduation_v2",
                "reply_class": reply_class,
                "evidence": metrics,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:20].upper()
    return {
        "learning_event_id": f"SAM-LIVE-GRADUATION-{digest}",
        "lead_id": f"SAM-LIVE-GRADUATION-{reply_class}"[:120],
        "channel": "owner_telegram",
        "source_agent": "sam_live_stock_backend",
        "event_source": "response_class_authority_v2",
        "event_type": "owner_review_note",
        "captured_facts": {
            "learning_kind": "graduation_notification",
            "reply_class": reply_class,
            "evaluator_version": "sam_response_class_graduation_v2",
            "evidence_window_hash": digest,
            "sample_count": int(metrics.get("sample_count") or 0),
            "owner_approval_rate": metrics.get("owner_approval_rate"),
            "provider_delivered_read_rate": metrics.get("provider_delivered_read_rate"),
            "owner_activation_required": True,
            "runtime_authority_changed": False,
        },
        "improvement_suggestion": f"Owner review requested for SAM Live Stock reply class {reply_class}.",
        "recorded_by": "sam_live_stock_graduation_notifier",
        **AUTHORITY_FLAGS,
    }


def _notification_text(reply_class: str, evidence: Mapping[str, Any]) -> str:
    metrics = dict(evidence.get("evidence") or {})
    approval = round(float(metrics.get("owner_approval_rate") or 0) * 100)
    delivered = round(float(metrics.get("provider_delivered_read_rate") or 0) * 100)
    return (
        "SAM Graduation Candidate\n\n"
        f"Reply class: {reply_class.replace('_', ' ').title()}\n"
        f"Reviewed replies: {int(metrics.get('sample_count') or 0)}\n"
        f"Owner approved: {approval}%\n"
        f"Provider confirmed: {delivered}%\n\n"
        "SAM remains owner-reviewed. No authority changed automatically."
    )


def _notification_keyboard(reply_class: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [[{
            "text": "Review Evidence",
            "url": "https://amadeus-pig-tracking-system.onrender.com/charlie-agents",
        }]]
    }


def _result(status: str, *, attempted: bool, **extra: Any) -> dict[str, Any]:
    return {
        "success": True,
        "status": status,
        "attempted": attempted,
        "auto_send_enabled": False,
        "owner_activation_required": True,
        "sends_customer_message": False,
        "changes_stock": False,
        "creates_order": False,
        **extra,
    }


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
