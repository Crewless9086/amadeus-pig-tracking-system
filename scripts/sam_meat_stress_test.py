import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.sales.sam_meat_stress import (
    format_stress_summary,
    run_sam_meat_stress_pack,
)


def main():
    parser = argparse.ArgumentParser(description="Run the Sam Meat local sales stress-test pack.")
    parser.add_argument("--json", action="store_true", help="Print full JSON results instead of the markdown summary.")
    parser.add_argument("--write-report", help="Write a markdown report to the given path.")
    parser.add_argument("--fail-on-known-gaps", action="store_true", help="Treat known improvement opportunities as failures.")
    args = parser.parse_args()

    summary = run_sam_meat_stress_pack()
    output = json.dumps(summary, indent=2, sort_keys=True) if args.json else format_stress_summary(summary)
    if args.write_report:
        path = Path(args.write_report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(format_stress_summary(summary), encoding="utf-8")
    print(output)
    if not summary["success"] or (args.fail_on_known_gaps and summary["known_gap_count"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
