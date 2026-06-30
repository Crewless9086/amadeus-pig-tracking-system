import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.execution_bridge import complete_no_release_mission, prepare_release_execution


def main():
    load_dotenv(REPO_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description="Prepare or complete a local CHARLIE release-approved mission.")
    parser.add_argument("--mission-id", default="", help="Specific CHARLIE mission id. Defaults to the newest release_approved mission.")
    parser.add_argument("--complete-no-release", action="store_true", help="Mark a release_approved mission done when no merge/deploy is required.")
    args = parser.parse_args()

    if args.complete_no_release:
        result, status_code = complete_no_release_mission(mission_id=args.mission_id)
    else:
        result, status_code = prepare_release_execution(mission_id=args.mission_id)
        result["dry_run_note"] = "Add --complete-no-release only when owner final approval is enough and no merge/deploy is required."
    print(json.dumps(result, indent=2))
    return 0 if status_code < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
