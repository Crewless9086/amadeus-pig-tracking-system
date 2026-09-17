"""Deterministic model budget guard for future CHARLIE model integrations.

This script records no provider calls and performs no model API activity. It is
only a local policy check that future Claude/Fable/GLM/OpenRouter layers must
pass before any model call is attempted.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_BUDGET_FILE = Path("loop/memory/budget.json")


@dataclass(frozen=True)
class BudgetDecision:
    ok: bool
    status: str
    reason: str = ""
    provider: str = ""
    stage: str = ""
    planned_usd: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "reason": self.reason,
            "provider": self.provider,
            "stage": self.stage,
            "planned_usd": self.planned_usd,
        }


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_budget(path: Path = DEFAULT_BUDGET_FILE) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Budget config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def check_budget(
    *,
    provider: str = "",
    stage: str = "",
    planned_usd: float = 0.0,
    spent_today_usd: float = 0.0,
    spent_mission_usd: float = 0.0,
    config: Mapping[str, Any] | None = None,
    path: Path = DEFAULT_BUDGET_FILE,
) -> BudgetDecision:
    try:
        budget = dict(config if config is not None else load_budget(path))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return BudgetDecision(ok=False, status="missing_budget_config", reason=str(exc), provider=provider, stage=stage)

    policy = dict(budget.get("policy") or {})
    caps = dict(budget.get("caps") or {})
    if not policy.get("live_model_api_calls_enabled", False):
        return BudgetDecision(ok=True, status="disabled", reason="live_model_api_calls_disabled", provider=provider, stage=stage)

    provider_key = provider.strip().lower()
    stage_key = stage.strip().lower()
    planned = max(0.0, float(planned_usd or 0.0))
    daily_limit = _as_float(caps.get("daily_limit_usd", caps.get("daily_external_model_usd")), 0.0)
    mission_limit = _as_float(caps.get("mission_limit_usd", caps.get("per_mission_external_model_usd")), 0.0)
    provider_limit = _as_float((caps.get("provider_limits") or {}).get(provider_key), daily_limit)
    stage_limit = _as_float((caps.get("stage_limits") or {}).get(stage_key), mission_limit)

    checks = [
        ("daily_limit_exceeded", daily_limit, spent_today_usd + planned),
        ("mission_limit_exceeded", mission_limit, spent_mission_usd + planned),
        ("provider_limit_exceeded", provider_limit, planned),
        ("stage_limit_exceeded", stage_limit, planned),
    ]
    for reason, limit, value in checks:
        if limit >= 0 and value > limit:
            return BudgetDecision(
                ok=False,
                status="blocked_budget",
                reason=reason,
                provider=provider_key,
                stage=stage_key,
                planned_usd=planned,
            )

    return BudgetDecision(ok=True, status="ok", provider=provider_key, stage=stage_key, planned_usd=planned)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a planned model spend against the CHARLIE budget gate.")
    parser.add_argument("--budget-file", type=Path, default=DEFAULT_BUDGET_FILE)
    parser.add_argument("--provider", default="")
    parser.add_argument("--stage", default="")
    parser.add_argument("--planned-usd", type=float, default=0.0)
    parser.add_argument("--spent-today-usd", type=float, default=0.0)
    parser.add_argument("--spent-mission-usd", type=float, default=0.0)
    args = parser.parse_args(argv)

    result = check_budget(
        provider=args.provider,
        stage=args.stage,
        planned_usd=args.planned_usd,
        spent_today_usd=args.spent_today_usd,
        spent_mission_usd=args.spent_mission_usd,
        path=args.budget_file,
    )
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

