"""Dry-run-only model routing policy for future CHARLIE support modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from scripts import model_budget_guard, trust_log


@dataclass(frozen=True)
class RoutingDecision:
    task_type: str
    risk_level: str
    recommended_model: str
    reason: str
    budget_class: str
    owner_approval_required: bool
    live_call_allowed: bool
    blocked_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


RED_TASKS = {"destructive_migration", "customer_send", "payment", "reservation", "public_post", "lifecycle_write"}
SOL_TASKS = {"security_review", "migration_review", "p0_failure_analysis", "architecture_review"}
LUNA_TASKS = {"docs_summary", "log_compression", "mission_triage", "status_classification"}


def recommend_route(
    task_type: str,
    *,
    risk_level: str = "medium",
    skill: str = "mission_model_routing",
    planned_usd: float = 0.0,
    budget_config: Mapping[str, Any] | None = None,
    trust_entries: Mapping[str, trust_log.TrustEntry] | None = None,
) -> RoutingDecision:
    task = task_type.strip().lower()
    risk = risk_level.strip().lower()
    if task in RED_TASKS:
        return RoutingDecision(task, risk, "none", "Red-zone action requires owner authority.", "blocked", True, False, "red_zone")
    model = "gpt-5.6-luna" if task in LUNA_TASKS else "gpt-5.6-sol" if task in SOL_TASKS or risk == "high" else "gpt-5.6-terra"
    budget_class = "low" if model.endswith("luna") else "high" if model.endswith("sol") else "standard"
    entries = dict(trust_entries or {})
    entry = entries.get(skill)
    tier = entry.tier if entry else "watch"
    budget = model_budget_guard.check_budget(provider="openai", stage=task, planned_usd=planned_usd, config=budget_config)
    blocked = "model_routing_dry_run_only"
    if not budget.ok:
        blocked = budget.status
    elif tier == "watch":
        blocked = "trust_tier_watch"
    return RoutingDecision(
        task,
        risk,
        model,
        "Deterministic recommendation only; Codex remains the primary builder.",
        budget_class,
        risk == "high" or model.endswith("sol"),
        False,
        blocked,
    )
