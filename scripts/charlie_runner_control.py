import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.runner_control import (
    EXECUTION_MODE_OBSERVE_ONLY,
    EXECUTION_MODE_ORDINARY,
    cleanup_runner_environment,
    runner_status,
    start_runner,
    stop_runner,
)


def _load_runner_dotenv():
    candidates = [REPO_ROOT / ".env"]
    if REPO_ROOT.parent.name == ".worktrees":
        candidates.append(REPO_ROOT.parent.parent / ".env")
    for path in candidates:
        if path.exists():
            load_dotenv(path, override=False)
            return str(path)
    return ""


def main():
    _load_runner_dotenv()
    parser = argparse.ArgumentParser(description="Control the local CHARLIE mission pickup runner.")
    parser.add_argument("action", choices=["status", "start", "stop", "cleanup"])
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()

    if args.action == "start":
        result, status_code = start_runner(
            execution_mode=(
                EXECUTION_MODE_OBSERVE_ONLY
                if args.observe_only
                else EXECUTION_MODE_ORDINARY
            )
        )
    elif args.observe_only:
        result, status_code = {
            "success": False,
            "status": "observe_only_valid_only_for_start",
        }, 400
    elif args.action == "stop":
        result, status_code = stop_runner()
    elif args.action == "cleanup":
        result, status_code = cleanup_runner_environment()
    else:
        result, status_code = runner_status(), 200
    print(json.dumps(result, indent=2))
    return 0 if status_code < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
