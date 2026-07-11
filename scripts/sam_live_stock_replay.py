"""Deterministic historical replay runner for SAM Live Stock evaluation cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from modules.sales.sam_live_stock_evaluation import aggregate_scorecard, graduation_by_reply_class, readiness_decision, score_replay_case
from modules.sales.sam_live_stock_runtime import handle_sam_live_stock_chatwoot_inbound


def run_replay(cases, handler=handle_sam_live_stock_chatwoot_inbound):
    scores = []
    for case in cases:
        case = dict(case or {})
        payload = dict(case.get("payload") or {})
        intake = dict(case.get("intake_context") or {"success": False, "items": []})
        availability = list(case.get("availability_rows") or [])
        result, status_code = handler(
            payload,
            environ=dict(case.get("environ") or {}),
            intake_context_loader=lambda _conversation_id, value=intake: value,
            conversation_history_loader=lambda *_args: {"success": True, "messages": list(case.get("history") or [])},
            availability_loader=lambda value=availability: value,
            owner_example_loader=lambda **_kwargs: ({"examples": []}, 200),
        )
        if status_code >= 400:
            scores.append({"case_id": case.get("case_id"), "handler_error": status_code})
            continue
        scores.append(score_replay_case(case, result))
    complete_conversations = len({str(case.get("conversation_group")) for case in cases if case.get("conversation_group")})
    scorecard = aggregate_scorecard(scores, complete_conversations=complete_conversations)
    graduation = graduation_by_reply_class([])
    return {
        "version": "sam_live_stock_historical_replay_v1",
        "scores": scores,
        "scorecard": scorecard,
        "readiness": readiness_decision(scorecard, graduation),
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
