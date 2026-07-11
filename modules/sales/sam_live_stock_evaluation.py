"""Replay scoring and evidence-based authority graduation for SAM Live Stock."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping


REQUIRED_PRODUCTION_TURNS = 100
REQUIRED_COMPLETE_CONVERSATIONS = 20
REQUIRED_CONSECUTIVE_ACCEPTED = 20


def score_replay_case(case: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    decision = result.get("sam_decision") if isinstance(result.get("sam_decision"), Mapping) else result
    decision = dict(decision or {})
    facts = dict(decision.get("facts") or {})
    review = dict(decision.get("conversation_review") or {})
    reply = str(decision.get("suggested_reply_text") or "")
    expected_action = str(case.get("expected_next_action") or "")
    expected_language = str(case.get("expected_language") or "")
    expected_facts = dict(case.get("expected_facts") or {})
    fact_errors = {
        key: {"expected": expected, "actual": facts.get(key)}
        for key, expected in expected_facts.items()
        if facts.get(key) != expected
    }
    action = str(decision.get("internal_next_action") or (decision.get("conversation_plan") or {}).get("next_action") or "")
    language = str(facts.get("customer_language") or "")
    return {
        "case_id": str(case.get("case_id") or ""),
        "reply_class": str(case.get("reply_class") or facts.get("message_intent") or "unclear"),
        "facts_correct": not fact_errors,
        "fact_errors": fact_errors,
        "next_action_correct": not expected_action or action == expected_action,
        "language_correct": not expected_language or language == expected_language,
        "relevant_answer": bool(reply) or action == "no_reply_needed",
        "human_voice": not any(token in reply.lower() for token in ("sam live", "decision packet", "owner_review_send_candidate", "current sam live price estimate:")),
        "unsafe": bool(review.get("blocked_reasons")),
        "invented_commitment": any(token in reply.lower() for token in ("reserved for you", "payment confirmed", "definitely available")),
        "reply_source": decision.get("reply_source") or "",
        "reply": reply,
    }


def aggregate_scorecard(scores: Iterable[Mapping[str, Any]], *, complete_conversations: int = 0) -> dict[str, Any]:
    rows = [dict(row) for row in scores]
    total = len(rows)
    rate = lambda key: 0.0 if not total else round(sum(bool(row.get(key)) for row in rows) / total, 4)
    return {
        "version": "sam_live_stock_scorecard_v1",
        "evaluated_turns": total,
        "complete_conversations": int(complete_conversations or 0),
        "stock_and_fact_accuracy": rate("facts_correct"),
        "next_action_accuracy": rate("next_action_correct"),
        "language_accuracy": rate("language_correct"),
        "relevant_answer_rate": rate("relevant_answer"),
        "human_voice_rate": rate("human_voice"),
        "unsafe_count": sum(bool(row.get("unsafe")) for row in rows),
        "invented_commitment_count": sum(bool(row.get("invented_commitment")) for row in rows),
        "production_evidence_complete": total >= REQUIRED_PRODUCTION_TURNS and complete_conversations >= REQUIRED_COMPLETE_CONVERSATIONS,
    }


def graduation_by_reply_class(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        row = dict(event or {})
        grouped[str(row.get("reply_class") or "unclear")].append(row)
    classes = {}
    for reply_class, rows in grouped.items():
        consecutive = 0
        for row in reversed(rows):
            accepted = row.get("owner_reply_classification") in {"approved_verbatim", "owner_edited"}
            safe = not row.get("unsafe") and not row.get("fact_error")
            if accepted and safe:
                consecutive += 1
            else:
                break
        unchanged = sum(row.get("owner_reply_classification") == "approved_verbatim" for row in rows)
        classes[reply_class] = {
            "events": len(rows),
            "consecutive_safe_accepted": consecutive,
            "unchanged_rate": 0.0 if not rows else round(unchanged / len(rows), 4),
            "narrow_auto_send_candidate": consecutive >= REQUIRED_CONSECUTIVE_ACCEPTED and unchanged / len(rows) >= 0.8,
            "auto_send_enabled": False,
        }
    return {"version": "sam_live_stock_graduation_v1", "classes": classes, "owner_activation_required": True}


def readiness_decision(scorecard: Mapping[str, Any], graduation: Mapping[str, Any]) -> dict[str, Any]:
    scorecard = dict(scorecard or {})
    gates = {
        "production_evidence": bool(scorecard.get("production_evidence_complete")),
        "facts": float(scorecard.get("stock_and_fact_accuracy") or 0) == 1.0,
        "next_action": float(scorecard.get("next_action_accuracy") or 0) >= 0.95,
        "language": float(scorecard.get("language_accuracy") or 0) >= 0.95,
        "relevance": float(scorecard.get("relevant_answer_rate") or 0) >= 0.95,
        "human_voice": float(scorecard.get("human_voice_rate") or 0) >= 0.90,
        "no_unsafe": int(scorecard.get("unsafe_count") or 0) == 0,
        "no_invented_commitment": int(scorecard.get("invented_commitment_count") or 0) == 0,
    }
    return {
        "version": "sam_live_stock_readiness_decision_v1",
        "gates": gates,
        "ready_for_owner_review_pilot": all(value for key, value in gates.items() if key != "production_evidence"),
        "ready_for_narrow_auto_send_owner_decision": all(gates.values()) and any(
            item.get("narrow_auto_send_candidate") for item in (graduation.get("classes") or {}).values()
        ),
        "auto_send_enabled": False,
        "confidence_ceiling": 0.98 if all(gates.values()) else 0.95,
    }


def owner_learning_scorecard(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    conversations = set()
    for event in events:
        event = dict(event or {})
        if event.get("source_agent") != "sam_live_stock_backend":
            continue
        captured = event.get("captured_facts") if isinstance(event.get("captured_facts"), Mapping) else {}
        if captured.get("learning_kind") != "owner_reply_capture":
            continue
        classification = str(captured.get("owner_reply_classification") or "")
        rows.append({
            "reply_class": captured.get("reply_class") or "unclear",
            "owner_reply_classification": classification,
            "unsafe": bool(captured.get("unsafe")),
            "fact_error": bool(captured.get("fact_error")),
        })
        if event.get("chatwoot_conversation_id"):
            conversations.add(str(event.get("chatwoot_conversation_id")))
    total = len(rows)
    unchanged = sum(row["owner_reply_classification"] == "approved_verbatim" for row in rows)
    minor_or_better = sum(row["owner_reply_classification"] in {"approved_verbatim", "owner_edited"} for row in rows)
    graduation = graduation_by_reply_class(rows)
    return {
        "version": "sam_live_stock_owner_learning_scorecard_v1",
        "captured_owner_replies": total,
        "conversation_count": len(conversations),
        "unchanged_rate": 0.0 if not total else round(unchanged / total, 4),
        "accepted_or_minor_edit_rate": 0.0 if not total else round(minor_or_better / total, 4),
        "graduation": graduation,
        "production_sample_target": REQUIRED_PRODUCTION_TURNS,
        "complete_conversation_target": REQUIRED_COMPLETE_CONVERSATIONS,
        "auto_send_enabled": False,
    }
