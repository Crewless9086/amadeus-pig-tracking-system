"""Evidence-based workforce overview for CHARLIE and connected agents."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_REGISTRY_PATH = REPO_ROOT / "static" / "assets" / "agents" / "agent_registry.json"
TRUST_LEDGER_PATH = REPO_ROOT / "loop" / "memory" / "trust.tsv"


WORKFORCE_DEFINITIONS = (
    {"id": "charlie", "name": "CHARLIE", "team": "Owner Command", "role": "Charl's private digital executive, conversational interface and cross-system commander.", "stage": "planned"},
    {"id": "charlie-core", "name": "CORE", "team": "Execution", "role": "Owner-gated agentic mission engine for building, repairing, testing and upgrading systems.", "stage": "live_supervised"},
    {"id": "codex-builder", "name": "Codex Builder", "team": "Build", "role": "Primary repository builder under CHARLIE mission contracts.", "stage": "live_supervised"},
    {"id": "review-qa", "name": "Review & QA", "team": "Build", "role": "Deterministic tests, reviewer and red-team quality gates.", "stage": "live_supervised", "registry_id": "gatekeeper"},
    {"id": "sam-live-stock", "name": "SAM Live Stock", "team": "Sales", "role": "Owner-reviewed live-stock conversations, sales preparation and learning.", "stage": "evidence_gathering", "registry_id": "sam"},
    {"id": "sam-meat", "name": "SAM Meat Sales", "team": "Sales", "role": "Meat lead intake and future owner-reviewed sales workflow.", "stage": "built_not_live", "registry_id": "butcher"},
    {"id": "oom-sakkie", "name": "Oom Sakkie", "team": "Farm Command", "role": "Farm managers' conversational AI with oversight of farm operations and farm agents.", "stage": "live_supervised", "registry_id": "oom-sakkie"},
    {"id": "herdmaster", "name": "Herdmaster", "team": "Farm", "role": "Pig, litter, breeding, weaning and health intelligence.", "stage": "planned", "registry_id": "herdmaster"},
    {"id": "fred", "name": "FRED", "team": "Private Transfers", "role": "Planned client-facing transport enquiry and booking agent for Amadeus Private Transfers.", "stage": "planned"},
    {"id": "ledger", "name": "Ledger", "team": "Business", "role": "Sales, money, opportunities and business-readiness intelligence.", "stage": "planned", "registry_id": "ledger"},
    {"id": "beacon", "name": "Beacon", "team": "Business", "role": "Owner-reviewed public content and demand generation.", "stage": "planned", "registry_id": "beacon"},
)


CONNECTIONS = (
    ("owner", "charlie", "owns"),
    ("charlie", "charlie-core", "commands"),
    ("charlie", "oom-sakkie", "delegates farm command"),
    ("charlie", "fred", "commands business"),
    ("charlie", "ledger", "coordinates"),
    ("charlie", "beacon", "coordinates"),
    ("charlie-core", "codex-builder", "dispatches"),
    ("charlie-core", "review-qa", "gates"),
    ("oom-sakkie", "sam-live-stock", "coordinates"),
    ("oom-sakkie", "sam-meat", "coordinates"),
    ("oom-sakkie", "herdmaster", "routes"),
    ("sam-live-stock", "supabase", "reads facts"),
    ("sam-live-stock", "chatwoot", "receives"),
    ("sam-live-stock", "telegram", "owner review"),
)


SYSTEM_NODES = (
    {"id": "owner", "name": "Charl", "kind": "owner"},
    {"id": "supabase", "name": "Supabase", "kind": "system"},
    {"id": "chatwoot", "name": "Chatwoot", "kind": "system"},
    {"id": "telegram", "name": "Telegram", "kind": "system"},
)


def build_agent_workforce_packet(
    *,
    mission_summary: Mapping[str, Any] | None = None,
    runner: Mapping[str, Any] | None = None,
    sam_learning: Mapping[str, Any] | None = None,
    registry: Mapping[str, Any] | None = None,
    trust_entries: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    mission_summary = dict(mission_summary or {})
    runner = dict(runner or {})
    sam_learning = dict(sam_learning or {})
    registry = dict(registry or load_agent_registry())
    trust_entries = dict(trust_entries or load_trust_ledger())
    registry_by_id = {str(item.get("agent_id")): item for item in registry.get("agents", []) if isinstance(item, Mapping)}
    counts = mission_summary.get("counts") if isinstance(mission_summary.get("counts"), Mapping) else {}
    scorecard = sam_learning.get("scorecard") if isinstance(sam_learning.get("scorecard"), Mapping) else {}

    agents = []
    for definition in WORKFORCE_DEFINITIONS:
        item = dict(definition)
        visual = registry_by_id.get(str(item.pop("registry_id", "")), {})
        item.update({
            "portrait": _available_portrait(visual.get("portrait_panel") or visual.get("portrait_main") or ""),
            "authority_boundary": visual.get("authority_boundary") or _default_boundary(item["id"]),
            "evidence": {"measured": False, "progress_percent": None, "label": "Not measured"},
            "metrics": [],
            "blockers": [],
            "owner_action": "No action required",
        })
        if item["id"] == "charlie-core":
            item.update(_charlie_evidence(counts, runner, trust_entries))
        elif item["id"] == "codex-builder":
            item.update(_trust_evidence("mission_loop_foundation", trust_entries, "Mission-loop trust evidence"))
        elif item["id"] == "review-qa":
            item.update(_trust_evidence("mission_loop_foundation", trust_entries, "Shared mission verification evidence"))
        elif item["id"] == "sam-live-stock":
            item.update(_sam_evidence(scorecard, sam_learning))
        agents.append(item)

    measured = [agent for agent in agents if agent["evidence"]["measured"]]
    candidates = [agent for agent in agents if agent.get("candidate_count", 0) > 0]
    blocked = [agent for agent in agents if agent.get("blockers")]
    return {
        "success": True,
        "status": "agent_workforce_ready",
        "version": "charlie_agent_workforce_v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "summary": {
            "agents_total": len(agents),
            "measured_agents": len(measured),
            "graduation_candidates": sum(agent.get("candidate_count", 0) for agent in candidates),
            "attention_needed": len(blocked),
            "active_missions": int(counts.get("in_progress") or 0),
            "review_ready_missions": int(counts.get("pr_ready") or 0),
        },
        "agents": agents,
        "map": {
            "nodes": [*SYSTEM_NODES, *({"id": agent["id"], "name": agent["name"], "kind": "agent", "team": agent["team"]} for agent in agents)],
            "connections": [{"from": source, "to": target, "label": label} for source, target, label in CONNECTIONS],
        },
        "graduation_rule": "Evidence may create an owner-review candidate. No threshold changes authority automatically.",
        "authority": {
            "auto_graduation": False,
            "owner_activation_required": True,
            "customer_send_changed": False,
            "stock_or_order_authority_changed": False,
        },
    }


def load_agent_registry(path: Path = AGENT_REGISTRY_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"agents": []}
    except (OSError, ValueError):
        return {"agents": []}


def load_trust_ledger(path: Path = TRUST_LEDGER_PATH) -> dict[str, dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = csv.DictReader(handle, delimiter="\t")
            return {str(row.get("skill")): dict(row) for row in rows if row.get("skill")}
    except OSError:
        return {}


def _sam_evidence(scorecard: Mapping[str, Any], sam_learning: Mapping[str, Any]) -> dict[str, Any]:
    turns = int(scorecard.get("captured_owner_replies") or 0)
    conversations = int(scorecard.get("conversation_count") or 0)
    turn_target = max(1, int(scorecard.get("production_sample_target") or 100))
    conversation_target = max(1, int(scorecard.get("complete_conversation_target") or 20))
    evidence_progress = round(min(turns / turn_target, 1) * 70 + min(conversations / conversation_target, 1) * 30)
    classes = ((scorecard.get("graduation") or {}).get("classes") or {}) if isinstance(scorecard.get("graduation"), Mapping) else {}
    candidates = [name for name, row in classes.items() if isinstance(row, Mapping) and row.get("narrow_auto_send_candidate")]
    metrics = [
        _metric("Owner replies", turns, turn_target, "count"),
        _metric("Conversations", conversations, conversation_target, "count"),
        _metric("Unchanged", float(scorecard.get("unchanged_rate") or 0), 0.8, "rate"),
        _metric("Accepted / minor", float(scorecard.get("accepted_or_minor_edit_rate") or 0), 0.95, "rate"),
    ]
    blockers = []
    if turns < turn_target:
        blockers.append(f"{turn_target - turns} more reviewed replies needed for the evidence floor")
    if conversations < conversation_target:
        blockers.append(f"{conversation_target - conversations} more complete conversations needed")
    if not sam_learning.get("success", True):
        blockers.append("Learning scorecard source is unavailable")
    return {
        "stage": "graduation_candidate" if candidates else "evidence_gathering",
        "evidence": {"measured": True, "progress_percent": evidence_progress, "label": "Production evidence"},
        "metrics": metrics,
        "reply_classes": [
            {
                "name": name,
                "events": int(row.get("events") or 0),
                "unchanged_rate": float(row.get("unchanged_rate") or 0),
                "safe_streak": int(row.get("consecutive_safe_accepted") or 0),
                "candidate": bool(row.get("narrow_auto_send_candidate")),
            }
            for name, row in sorted(classes.items()) if isinstance(row, Mapping)
        ],
        "candidate_count": len(candidates),
        "blockers": blockers,
        "owner_action": "Review graduation evidence" if candidates else "Continue owner-reviewed conversations",
        "source_status": sam_learning.get("status") or "scorecard_unknown",
    }


def _charlie_evidence(counts: Mapping[str, Any], runner: Mapping[str, Any], trust_entries: Mapping[str, Any]) -> dict[str, Any]:
    completed = int(counts.get("done") or 0) + int(counts.get("deployed") or 0)
    blocked_count = int(counts.get("blocked") or 0)
    terminal = completed + blocked_count
    outcome_rate = 0.0 if not terminal else completed / terminal
    active = int(counts.get("in_progress") or 0)
    evidence = _trust_evidence("mission_loop_foundation", trust_entries, "Mission outcomes")
    evidence["metrics"] = [
        _metric("Completed", completed, None, "count"),
        _metric("Blocked", blocked_count, 0, "count"),
        _metric("Outcome rate", outcome_rate, 0.95, "rate"),
        _metric("Active", active, None, "count"),
    ]
    evidence["runner_state"] = runner.get("status") or "unknown"
    evidence["owner_action"] = "Review blocked missions" if blocked_count else "No action required"
    if blocked_count:
        evidence["blockers"] = [f"{blocked_count} mission{'s' if blocked_count != 1 else ''} blocked"]
    return evidence


def _trust_evidence(skill: str, trust_entries: Mapping[str, Any], label: str) -> dict[str, Any]:
    row = trust_entries.get(skill) if isinstance(trust_entries.get(skill), Mapping) else {}
    runs = int(row.get("runs") or 0)
    passes = int(row.get("passes") or 0)
    rate = 0.0 if not runs else passes / runs
    return {
        "evidence": {"measured": runs > 0, "progress_percent": round(rate * 100) if runs else None, "label": label if runs else "Not measured"},
        "trust_tier": row.get("tier") or "watch",
        "metrics": [_metric("Verified runs", runs, 20, "count"), _metric("Pass rate", rate, 0.95, "rate")],
        "blockers": [] if runs else ["Trust ledger has no verified runs for this capability"],
        "owner_action": "Continue supervised missions" if runs < 20 else "Review trust tier",
    }


def _metric(label: str, value: Any, target: Any, kind: str) -> dict[str, Any]:
    return {"label": label, "value": value, "target": target, "kind": kind}


def _default_boundary(agent_id: str) -> str:
    return {
        "charlie": "Private to Charl. Future execution must use approved tools, audit trails and owner authority rules.",
        "charlie-core": "Coordinates missions and evidence. Owner approval remains required for red-zone actions.",
        "codex-builder": "May edit approved repository scope and run tests. Cannot approve its own work.",
        "review-qa": "May verify and block. Cannot deploy or override owner decisions.",
        "fred": "Planned client-facing transport booking agent only; no production booking, pricing, payment or dispatch authority exists yet.",
    }.get(agent_id, "No production authority is granted until an approved workflow defines it.")


def _available_portrait(value: Any) -> str:
    path = str(value or "").strip()
    if not path.startswith("/assets/agents/"):
        return ""
    relative = path.removeprefix("/assets/")
    return path if (REPO_ROOT / "static" / "assets" / relative).is_file() else ""
