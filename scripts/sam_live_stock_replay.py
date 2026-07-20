"""Deterministic historical replay runner for SAM Live Stock evaluation cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

from modules.sales.sam_live_stock_evaluation import aggregate_scorecard, graduation_by_reply_class, readiness_decision, score_replay_case
from modules.sales.sam_live_stock_runtime import handle_sam_live_stock_chatwoot_inbound
from modules.sales import sam_live_stock_runtime


def run_replay(cases, handler=handle_sam_live_stock_chatwoot_inbound):
    scores = []
    trace = []
    for case in cases:
        case = dict(case or {})
        payload = dict(case.get("payload") or {})
        intake = dict(case.get("intake_context") or {"success": False, "items": []})
        availability = list(case.get("availability_rows") or [])
        price_rule = dict(case.get("ledger_price_rule") or {})
        with patch.object(
            sam_live_stock_runtime,
            "resolve_live_stock_price_rule",
            return_value=price_rule or {"found": False, "source": "replay_fixture_price_missing"},
        ):
            result, status_code = handler(
                payload,
                environ=dict(case.get("environ") or {}),
                intake_context_loader=lambda _conversation_id, value=intake: value,
                conversation_history_loader=lambda *_args: {"success": True, "messages": list(case.get("history") or [])},
                availability_loader=lambda value=availability: value,
                availability_evidence=dict(case.get("herdmaster_evidence") or {}),
                owner_example_loader=lambda **_kwargs: ({"examples": []}, 200),
            )
        trace.append(_trace_entry(case, result, status_code))
        if status_code >= 400:
            scores.append({"case_id": case.get("case_id"), "handler_error": status_code})
            continue
        scores.append(score_replay_case(case, result))
    complete_conversations = len({str(case.get("conversation_group")) for case in cases if case.get("conversation_group")})
    scorecard = aggregate_scorecard(scores, complete_conversations=complete_conversations)
    graduation = graduation_by_reply_class([])
    return {
        "version": "sam_live_stock_historical_replay_v2",
        "scores": scores,
        "scorecard": scorecard,
        "readiness": readiness_decision(scorecard, graduation),
        "trace": trace,
        "owner_review_packet": _owner_review_packet(trace),
    }


def _trace_entry(case: Mapping[str, Any], result: Mapping[str, Any], status_code: int) -> dict[str, Any]:
    decision = result.get("sam_decision") if isinstance(result, Mapping) else {}
    decision = dict(decision or {})
    agent_evidence = dict(decision.get("agent_evidence") or {})
    ledger = dict(agent_evidence.get("ledger") or {})
    authority_keys = (
        "sends_customer_message", "calls_chatwoot", "calls_n8n", "creates_quote",
        "creates_order", "reserves_stock", "changes_stock", "writes_farm_data",
        "writes_order_intake", "writes_sales_transaction", "dispatch_enabled",
        "customer_public_output_enabled",
    )
    authority = {key: bool(decision.get(key) or result.get(key)) for key in authority_keys}
    return {
        "case_id": str(case.get("case_id") or ""),
        "conversation_group": str(case.get("conversation_group") or ""),
        "agent": decision.get("agent") or "sam_live_stock_backend",
        "handler_status": status_code,
        "intent_and_requirements": {
            "sales_lane": decision.get("sales_lane") or "unknown",
            "facts": dict(decision.get("facts") or {}),
            "missing_fields": list(decision.get("missing_fields") or []),
            "blockers": list(decision.get("blockers") or []),
        },
        "evidence_used": {
            "herdmaster": agent_evidence.get("herdmaster") or {},
            "ledger": ledger,
            "supplied_order_warning_review": list(case.get("order_warning_review") or []),
        },
        "confidence": {
            "lane": decision.get("lane_confidence"),
            "ledger": ledger.get("confidence"),
        },
        "response_proposal": decision.get("suggested_reply_text") or "",
        "quote_order_preparation": dict(decision.get("owner_action_packet") or {}),
        "next_action": decision.get("next_action") or "escalate",
        "authority_decision": {
            "read_only": True,
            "owner_review_required": bool(decision.get("owner_review_required", True)),
            "writes_or_sends_attempted": any(authority.values()),
            "flags": authority,
        },
    }


def _owner_review_packet(trace: list[dict[str, Any]]) -> dict[str, Any]:
    write_or_send_attempted = any(item["authority_decision"]["writes_or_sends_attempted"] for item in trace)
    return {
        "version": "sam_live_stock_owner_review_packet_v1",
        "conversation_count": len({item.get("conversation_group") for item in trace if item.get("conversation_group")}),
        "turn_count": len(trace),
        "customer_send_or_write_attempted": write_or_send_attempted,
        "owner_review_required": True,
        "owner_decision_needed": "Review the proposed reply and preparation boundary; no customer action is authorized by this replay.",
        "follow_up_recommendations": [item.get("next_action") for item in trace],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replay SAM Live Stock evaluation cases without customer sends.")
    parser.add_argument("cases", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError("Replay case file must contain a JSON list.")
    report = run_replay(cases)
    encoded = json.dumps(report, indent=2, ensure_ascii=True)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0 if report["readiness"]["ready_for_owner_review_pilot"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
