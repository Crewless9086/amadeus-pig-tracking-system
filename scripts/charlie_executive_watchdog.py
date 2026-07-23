"""Always-on CHARLIE executive watchdog, independent from CORE execution.

One invocation performs a bounded supervision tick. Windows Task Scheduler runs
it every minute and after reboot, so executive observation and owner briefing do
not disappear when the heavier CORE builder is stopped or unhealthy.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.domain_observer_readers import observer_readers
from modules.charlie.executive_runtime import run_executive_cycle
from modules.charlie.executive_store import queue_outbox
from modules.charlie.runner_control import runner_status, start_runner
from modules.sales.riversdale_auction import queue_due_owner_prompts
from scripts.charlie_mission_pickup import _deliver_executive_outbox, _run_domain_observers


def _load_environment():
    candidates = [REPO_ROOT / ".env", REPO_ROOT.parent.parent / ".env"]
    for path in candidates:
        if path.exists():
            load_dotenv(path, override=False)
            return str(path)
    return ""


def _idle_recommendations(goals=None, readers=None):
    readers = readers or observer_readers()
    recommendations = []
    for key in ("sam_lead_health", "ledger_cash_exceptions", "herdmaster_readiness", "beacon_opportunities"):
        reader = readers.get(key)
        if not callable(reader):
            continue
        try:
            evidence = reader()
        except Exception:
            continue
        for item in evidence.get("recommendations") or []:
            summary = str(item.get("summary") or "").strip()
            if summary and summary not in recommendations:
                recommendations.append(summary)
    if not recommendations:
        active = [str(item.get("title") or "").strip() for item in (goals or []) if item.get("status") == "active"]
        if active:
            recommendations.append(f"Select the next measurable mission for the active goal: {active[0]}.")
    return recommendations[:3]


def _observer_recommendations(observers):
    recommendations = []
    for run in (observers or {}).get("runs") or []:
        for item in run.get("recommendations") or []:
            summary = str(item.get("summary") or "").strip()
            if summary and summary not in recommendations:
                recommendations.append(summary)
    return recommendations[:3]


def _queue_idle_brief(cycle, recommendations, *, now=None):
    counts = cycle.get("status_counts") if isinstance(cycle.get("status_counts"), dict) else {}
    runnable = int((cycle.get("queue_health") or {}).get("runnable_count") or 0)
    working = runnable + int(counts.get("in_progress") or 0) + int(counts.get("release_approved") or 0)
    if working or int(counts.get("new") or 0) or int(counts.get("pr_ready") or 0):
        return {"success": True, "status": "portfolio_not_idle"}
    now = now or datetime.now(ZoneInfo("Africa/Johannesburg"))
    lines = ["CHARLIE executive update", "There is no runnable approved mission right now."]
    blocked = int(counts.get("blocked") or 0)
    if blocked:
        lines.append(f"I am tracking {blocked} blocked mission(s) through recovery or exact owner escalation.")
    if recommendations:
        lines.append("My next recommendations:")
        lines.extend(f"{index}. {value}" for index, value in enumerate(recommendations, start=1))
        lines.append("Reply with the recommendation number or say yes to #1 and I will turn it into the next governed mission.")
    else:
        lines.append("I found no evidence-backed recommendation yet; I will keep observing rather than invent work.")
    payload = {
        "private_text": "\n".join(lines),
        "block_class": "portfolio_idle",
        "recommendations": recommendations,
    }
    return queue_outbox(
        "EXECUTIVE_PORTFOLIO_IDLE", payload,
        idempotency_key=f"executive-idle:{now.date().isoformat()}",
    )[0]


def supervision_tick(*, now=None, readers=None, runner_reader=runner_status, runner_starter=start_runner):
    now = now or datetime.now(ZoneInfo("Africa/Johannesburg"))
    state = runner_reader()
    executive, executive_status = run_executive_cycle(
        runner={"active_mission_id": state.get("active_mission_id") or ""},
    )
    if executive_status >= 400:
        return {"success": False, "status": "executive_cycle_failed", "executive": executive}
    cycle = executive.get("cycle") if isinstance(executive.get("cycle"), dict) else {}
    observers = _run_domain_observers()
    recommendations = _observer_recommendations(observers)
    if not recommendations:
        recommendations = _idle_recommendations(goals=[
            {"title": "the active executive goal", "status": "active"}
        ], readers={})
    idle_brief = _queue_idle_brief(cycle, recommendations, now=now)
    auction_prompts = queue_due_owner_prompts(queue_outbox, today=now.date())

    runner_start = {"status": "not_required"}
    queue_progress = any(
        item.get("action") == "ensure_queue_progress"
        for item in cycle.get("commands") or []
    )
    if queue_progress and not state.get("active"):
        runner_start, _ = runner_starter(status_override=state)
    delivery = _deliver_executive_outbox()
    return {
        "success": True,
        "status": "charlie_executive_supervision_complete",
        "executive": executive,
        "observers": observers,
        "idle_brief": idle_brief,
        "auction_prompts": auction_prompts,
        "runner_start": runner_start,
        "delivery": delivery,
    }


def main():
    _load_environment()
    parser = argparse.ArgumentParser(description="Run one independent CHARLIE executive supervision tick.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = supervision_tick()
    print(json.dumps(result, default=str) if args.json else result.get("status"))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
