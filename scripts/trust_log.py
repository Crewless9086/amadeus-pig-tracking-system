"""File-based CHARLIE mission-loop trust ledger utility."""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_TRUST_FILE = Path("loop/memory/trust.tsv")
FIELDS = [
    "skill",
    "runs",
    "passes",
    "failures",
    "tier",
    "last_result",
    "last_tested_at",
    "last_failure_reason",
]


@dataclass
class TrustEntry:
    skill: str
    runs: int = 0
    passes: int = 0
    failures: int = 0
    tier: str = "watch"
    last_result: str = "never"
    last_tested_at: str = ""
    last_failure_reason: str = "none"

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "TrustEntry":
        return cls(
            skill=row.get("skill", "").strip(),
            runs=int(row.get("runs") or 0),
            passes=int(row.get("passes") or 0),
            failures=int(row.get("failures") or 0),
            tier=row.get("tier") or "watch",
            last_result=row.get("last_result") or "never",
            last_tested_at=row.get("last_tested_at") or "",
            last_failure_reason=row.get("last_failure_reason") or "none",
        )

    def as_row(self) -> dict[str, str]:
        return {
            "skill": self.skill,
            "runs": str(self.runs),
            "passes": str(self.passes),
            "failures": str(self.failures),
            "tier": self.tier,
            "last_result": self.last_result,
            "last_tested_at": self.last_tested_at,
            "last_failure_reason": self.last_failure_reason,
        }


def compute_tier(runs: int, passes: int, failures: int, *, red_zone_violation: bool = False) -> str:
    if red_zone_violation:
        return "watch"
    if runs <= 0:
        return "watch"
    pass_rate = passes / runs
    if pass_rate < 0.90:
        return "watch"
    if runs < 10:
        return "watch"
    if runs < 20:
        return "queue"
    if pass_rate >= 0.95:
        return "auto"
    return "queue"


def load_entries(path: Path = DEFAULT_TRUST_FILE) -> dict[str, TrustEntry]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return {
            row["skill"]: TrustEntry.from_row(row)
            for row in reader
            if row.get("skill")
        }


def save_entries(entries: dict[str, TrustEntry], path: Path = DEFAULT_TRUST_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for skill in sorted(entries):
            writer.writerow(entries[skill].as_row())


def log_result(
    skill: str,
    result: str,
    *,
    reason: str = "",
    red_zone_violation: bool = False,
    path: Path = DEFAULT_TRUST_FILE,
    tested_at: str | None = None,
) -> TrustEntry:
    normalized = result.strip().lower()
    if normalized not in {"pass", "fail"}:
        raise ValueError("result must be 'pass' or 'fail'")
    if not skill or not skill.strip():
        raise ValueError("skill is required")

    entries = load_entries(path)
    entry = entries.get(skill) or TrustEntry(skill=skill)
    entry.runs += 1
    if normalized == "pass":
        entry.passes += 1
        entry.last_failure_reason = "none"
    else:
        entry.failures += 1
        entry.last_failure_reason = reason.strip() or "unspecified_failure"
    if red_zone_violation:
        entry.last_failure_reason = reason.strip() or "red_zone_violation"
    entry.last_result = "red_zone_violation" if red_zone_violation else normalized
    entry.last_tested_at = tested_at or _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    entry.tier = compute_tier(entry.runs, entry.passes, entry.failures, red_zone_violation=red_zone_violation)
    entries[skill] = entry
    save_entries(entries, path)
    return entry


def render_summary(path: Path = DEFAULT_TRUST_FILE) -> str:
    entries = load_entries(path)
    if not entries:
        return "No trust ledger entries."
    lines = ["skill | tier | runs | pass_rate | last_result | last_failure_reason"]
    for skill in sorted(entries):
        entry = entries[skill]
        pass_rate = 0.0 if entry.runs == 0 else entry.passes / entry.runs
        lines.append(
            f"{entry.skill} | {entry.tier} | {entry.runs} | {pass_rate:.0%} | "
            f"{entry.last_result} | {entry.last_failure_reason}"
        )
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update or render the CHARLIE trust ledger.")
    parser.add_argument("--file", type=Path, default=DEFAULT_TRUST_FILE)
    parser.add_argument("--skill", default="")
    parser.add_argument("--result", choices=["pass", "fail"])
    parser.add_argument("--reason", default="")
    parser.add_argument("--red-zone", action="store_true")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.render or not args.result:
        print(render_summary(args.file))
        return 0
    entry = log_result(
        args.skill,
        args.result,
        reason=args.reason,
        red_zone_violation=args.red_zone,
        path=args.file,
    )
    print(f"{entry.skill}: tier={entry.tier} runs={entry.runs} last={entry.last_result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

