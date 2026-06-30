import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.execution_bridge import (
    DEFAULT_TIMEOUT_SECONDS,
    complete_codex_execution_from_artifact,
    prepare_codex_execution,
    run_codex_execution_bridge,
)


def main():
    load_dotenv(REPO_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description="Prepare or run a local Codex execution for an in-progress CHARLIE mission.")
    parser.add_argument("--mission-id", default="", help="Specific CHARLIE mission id. Defaults to the newest in_progress mission.")
    parser.add_argument("--status", default="in_progress", help="Mission status to pick when --mission-id is omitted.")
    parser.add_argument("--execute-codex", action="store_true", help="Actually run codex exec locally. Without this, only prepares the prompt.")
    parser.add_argument("--recover-final-artifact", action="store_true", help="Move an in-progress mission to owner review from an existing final artifact.")
    parser.add_argument("--final-path", default="", help="Optional explicit .final.md artifact path for recovery.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args()

    if args.recover_final_artifact:
        result, status_code = complete_codex_execution_from_artifact(
            mission_id=args.mission_id,
            final_path=args.final_path or None,
        )
    elif args.execute_codex:
        result, status_code = run_codex_execution_bridge(
            mission_id=args.mission_id,
            status=args.status,
            execute_codex=True,
            timeout_seconds=args.timeout_seconds,
        )
    else:
        result, status_code = prepare_codex_execution(
            mission_id=args.mission_id,
            status=args.status,
        )
        result["dry_run_note"] = "Add --execute-codex to run codex exec and move the mission toward owner review."
    print(json.dumps(result, indent=2))
    return 0 if status_code < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
