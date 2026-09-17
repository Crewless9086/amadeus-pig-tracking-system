"""Run the proposal-only Agentic Business OS observer cycle."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.charlie.domain_observers import OBSERVERS, run_observer_cycle
from modules.charlie.domain_observer_readers import observer_readers
from modules.charlie.domain_observer_store import observer_last_runs, record_observer_run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-domain", action="append", default=[])
    parser.add_argument("--live-reads", action="store_true")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()

    def unavailable(domain):
        return {
            "source_refs": [],
            "freshness": "unknown",
            "facts": [],
            "gaps": [f"{domain}_reader_not_configured"],
            "recommendations": [],
        }

    readers = observer_readers() if args.live_reads else {spec["domain"]: unavailable for spec in OBSERVERS.values()}
    last_runs = None
    recorder = None
    if args.persist:
        loaded, loaded_status = observer_last_runs()
        if loaded_status >= 400:
            print(json.dumps(loaded, indent=2))
            return 1
        last_runs = loaded.get("last_runs") or {}
        recorder = lambda run: record_observer_run(run)[0]
    result = run_observer_cycle(readers, last_runs=last_runs, event_domains=args.event_domain, recorder=recorder)
    result["mode"] = "live_reads" if args.live_reads else "dry_run_no_live_reads"
    result["persistence_enabled"] = bool(args.persist)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") in {"observer_cycle_complete", "observer_cycle_not_due"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
