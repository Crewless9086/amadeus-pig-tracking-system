import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.runner_control import cleanup_runner_environment, runner_status, start_runner, stop_runner


def main():
    load_dotenv(REPO_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description="Control the local CHARLIE mission pickup runner.")
    parser.add_argument("action", choices=["status", "start", "stop", "cleanup"])
    args = parser.parse_args()

    if args.action == "start":
        result, status_code = start_runner()
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
