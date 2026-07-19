"""Run the proposal-only Agentic Business OS observer cycle."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.charlie.domain_observers import OBSERVERS, run_observer_cycle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-domain", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()

    def unavailable(domain):
        return {
            "source_refs": [],
            "freshness": "unknown",
            "facts": [],
            "gaps": [f"{domain}_reader_not_configured"],
            "recommendations": [],
        }

    readers = {spec["domain"]: unavailable for spec in OBSERVERS.values()}
    result = run_observer_cycle(readers, event_domains=args.event_domain)
    result["mode"] = "dry_run_no_persistence"
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") in {"observer_cycle_complete", "observer_cycle_not_due"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
