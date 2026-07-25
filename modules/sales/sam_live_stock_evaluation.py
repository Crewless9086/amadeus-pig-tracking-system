"""Replay scoring and evidence-based authority graduation for SAM Live Stock."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable, Mapping


REQUIRED_PRODUCTION_TURNS = 100
REQUIRED_COMPLETE_CONVERSATIONS = 20
REQUIRED_CONSECUTIVE_ACCEPTED = 20

RESPONSE_CLASS_POLICY = {
    "greeting": {"minimum_samples": 25, "low_risk": True},
    "acknowledgement": {"minimum_samples": 25, "low_risk": True},
    "thanks": {"minimum_samples": 25, "low_risk": True},
    "simple_small_talk": {"minimum_samples": 30, "low_risk": True},
    "one_clarification": {"minimum_samples": 30, "low_risk": True},
    "referral_post_context_question": {"minimum_samples": 40, "low_risk": False},
    "verified_general_factual_answer": {"minimum_samples": 50, "low_risk": False},
    "livestock_informational_answer": {"minimum_samples": 75, "low_risk": False},
    "meat_informational_answer": {"minimum_samples": 75, "low_risk": False},
    "quote_order_payment_reservation_protected": {
        "minimum_samples": 0,
        "low_risk": False,
        "self_graduation_prohibited": True,
    },
}


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


def evaluate_response_class_graduation(
    events: Iterable[Mapping[str, Any]], *, now: datetime | None = None
) -> dict[str, Any]:
    """Evaluate independent classes; this function never grants runtime authority."""
    now = now or datetime.now(timezone.utc)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        row = dict(event or {})
        reply_class = str(row.get("response_class") or row.get("reply_class") or "unknown")
        grouped[reply_class].append(row)
    results = {}
    for reply_class, policy in RESPONSE_CLASS_POLICY.items():
        rows = sorted(grouped.get(reply_class, []), key=lambda row: str(row.get("observed_at") or ""))
        total = len(rows)
        rate = lambda key: None if not total else round(
            sum(bool(row.get(key)) for row in rows) / total, 4
        )
        approvals = rate("owner_approved")
        delivered = rate("provider_confirmed")
        wrong_lane = rate("wrong_lane")
        unsupported = rate("unsupported_claim")
        duplicate = rate("duplicate_or_retry")
        escalation = rate("escalation_correct")
        intervention = rate("owner_intervention_required")
        ambiguous = rate("delivery_ambiguous")
        truth_verified = rate("truth_source_verified")
        class_canary_proven = rate("class_canary_proven")
        recent_failure_streak = 0
        for row in reversed(rows):
            if any(
                bool(row.get(key))
                for key in ("wrong_lane", "unsupported_claim", "duplicate_or_retry", "delivery_ambiguous")
            ):
                recent_failure_streak += 1
            else:
                break
        timestamps = [_parse_observed_at(row.get("observed_at")) for row in rows]
        timestamps = [value for value in timestamps if value is not None]
        freshest_days = None
        window_days = None
        if timestamps:
            freshest_days = max(0, (now - max(timestamps)).days)
            window_days = max(0, (max(timestamps) - min(timestamps)).days)
        evidence = {
            "sample_count": total,
            "owner_approval_rate": approvals,
            "provider_delivered_read_rate": delivered,
            "wrong_lane_rate": wrong_lane,
            "unsupported_claim_rate": unsupported,
            "duplicate_retry_rate": duplicate,
            "escalation_correctness_rate": escalation,
            "owner_intervention_rate": intervention,
            "delivery_ambiguity_rate": ambiguous,
            "verified_truth_rate": truth_verified,
            "class_canary_proven_rate": class_canary_proven,
            "recent_failure_streak": recent_failure_streak,
            "evidence_window_days": window_days,
            "freshest_evidence_days": freshest_days,
        }
        gates = {
            "sample_count": total >= policy["minimum_samples"],
            "owner_approval": approvals is not None
            and approvals >= (0.95 if policy.get("low_risk") else 0.975),
            "provider_delivery": delivered is not None and delivered >= 0.98,
            "wrong_lane": wrong_lane is not None and wrong_lane == 0.0,
            "unsupported_claim": unsupported is not None and unsupported == 0.0,
            "duplicate_retry": duplicate is not None and duplicate == 0.0,
            "escalation_correctness": escalation is not None and escalation >= 0.95,
            "owner_intervention": intervention is not None
            and intervention <= (0.05 if policy.get("low_risk") else 0.10),
            "delivery_ambiguity": ambiguous is not None and ambiguous <= 0.02,
            "failure_streak": recent_failure_streak == 0,
            "freshness": freshest_days is not None and freshest_days <= 7,
            "bounded_window": window_days is not None and window_days <= 30,
            "verified_truth": (
                truth_verified == 1.0
                if reply_class
                in {
                    "verified_general_factual_answer",
                    "livestock_informational_answer",
                    "meat_informational_answer",
                }
                else True
            ),
            "specialist_canary": (
                class_canary_proven == 1.0
                if reply_class
                in {"livestock_informational_answer", "meat_informational_answer"}
                else True
            ),
            "pre_authorized_low_risk": bool(policy.get("low_risk")),
            "self_graduation_allowed": not policy.get("self_graduation_prohibited", False),
        }
        candidate = all(gates.values())
        decision = (
            "promotion_candidate"
            if candidate
            else "regressed"
            if recent_failure_streak > 0
            else "withheld"
        )
        results[reply_class] = {
            "evidence": evidence,
            "gates": gates,
            "decision": decision,
            "runtime_enabled": False,
            "owner_activation_required": True,
            "class_kill_switch": f"SAM_RESPONSE_CLASS_{reply_class.upper()}_ENABLED",
        }
    return {
        "version": "sam_response_class_graduation_v2",
        "classes": results,
        "global_kill_switch": "SAM_RESPONSE_CLASS_GRADUATION_ENABLED",
        "runtime_authority_changed": False,
        "consequential_self_authorization": False,
    }


def build_response_class_graduation_event(
    reply_class: str, decision: Mapping[str, Any], *, observed_at: str
) -> dict[str, Any]:
    """Build sanitized append-only decision evidence for an existing recorder."""
    reply_class = str(reply_class or "unknown")
    decision = dict(decision or {})
    canonical = {
        "version": "sam_response_class_graduation_event_v1",
        "response_class": reply_class,
        "decision": str(decision.get("decision") or "withheld"),
        "evidence": dict(decision.get("evidence") or {}),
        "gates": dict(decision.get("gates") or {}),
        "observed_at": str(observed_at or ""),
        "runtime_enabled": False,
        "owner_activation_required": True,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24].upper()
    return {
        "graduation_event_id": f"SAM-GRADUATION-{digest}",
        **canonical,
        "append_only": True,
        "contains_customer_content": False,
        "contains_private_provider_identity": False,
    }


def build_charlie_sam_oversight_packet(
    graduation: Mapping[str, Any],
    *,
    human_backlog: Mapping[str, Any],
    delivery_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose sanitized read authority while withholding enable/send authority."""
    graduation = dict(graduation or {})
    return {
        "version": "charlie_sam_oversight_v1",
        "human_backlog": dict(human_backlog or {}),
        "delivery": dict(delivery_metrics or {}),
        "graduated_classes": [
            key
            for key, value in (graduation.get("classes") or {}).items()
            if value.get("runtime_enabled") is True
        ],
        "promotion_candidates": [
            key
            for key, value in (graduation.get("classes") or {}).items()
            if value.get("decision") == "promotion_candidate"
        ],
        "paused_or_regressed_classes": [
            key
            for key, value in (graduation.get("classes") or {}).items()
            if value.get("decision") in {"paused", "regressed"}
        ],
        "read_sanitized_evidence": True,
        "may_raise_alerts": True,
        "may_pause_pre_authorized_class": True,
        "may_propose_promotion": True,
        "may_enable_consequential_authority": False,
        "may_send_customer_message": False,
        "may_mutate_business_state": False,
    }


def _parse_observed_at(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


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
    historical_examples = 0
    historical_conversations = set()
    for event in events:
        event = dict(event or {})
        if event.get("source_agent") != "sam_live_stock_backend":
            continue
        captured = event.get("captured_facts") if isinstance(event.get("captured_facts"), Mapping) else {}
        if captured.get("learning_kind") == "owner_reply_historical_example":
            historical_examples += 1
            if event.get("chatwoot_conversation_id"):
                historical_conversations.add(str(event.get("chatwoot_conversation_id")))
            continue
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
        "historical_owner_reply_examples": historical_examples,
        "historical_conversation_count": len(historical_conversations),
        "total_learning_examples": total + historical_examples,
        "unchanged_rate": 0.0 if not total else round(unchanged / total, 4),
        "accepted_or_minor_edit_rate": 0.0 if not total else round(minor_or_better / total, 4),
        "graduation": graduation,
        "production_sample_target": REQUIRED_PRODUCTION_TURNS,
        "complete_conversation_target": REQUIRED_COMPLETE_CONVERSATIONS,
        "auto_send_enabled": False,
    }
