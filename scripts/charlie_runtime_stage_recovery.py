"""Read or recover an interrupted CORE source-staging lane without starting CORE."""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.runtime_staging import (
    RuntimeStagingError,
    read_staging_state,
    recover_runtime_staging,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["readback", "recover"])
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--lane-id")
    parser.add_argument("--rollback-sha256")
    args = parser.parse_args()
    try:
        if args.action == "readback":
            result = read_staging_state(args.state_root)
        else:
            result = recover_runtime_staging(
                state_root=args.state_root, lane_id=args.lane_id,
                rollback_sha256=args.rollback_sha256,
            )
    except RuntimeStagingError as exc:
        result = {"success": False, "status": exc.status, **exc.evidence}
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
