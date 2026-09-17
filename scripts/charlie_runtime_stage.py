"""Plan or stage CORE runtime source without starting or scheduling CORE."""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.runtime_staging import RuntimeStagingError, plan_runtime_staging, stage_runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["plan", "stage"])
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--execution-root", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--expected-runtime-head", required=True)
    parser.add_argument("--expected-execution-head", required=True)
    parser.add_argument("--expected-manifest-commit", required=True)
    parser.add_argument("--expected-task-sha256", required=True)
    args = parser.parse_args()
    try:
        plan = plan_runtime_staging(
            source_ref=args.source_ref, runtime_root=Path(args.runtime_root),
            execution_root=Path(args.execution_root), state_root=Path(args.state_root),
            receipt_path=Path(args.receipt), receipt_sha256=args.receipt_sha256,
            expected_runtime_head=args.expected_runtime_head,
            expected_execution_head=args.expected_execution_head,
            expected_manifest_commit=args.expected_manifest_commit,
            expected_task_sha256=args.expected_task_sha256,
        )
        result = plan if args.action == "plan" else stage_runtime(plan)
    except RuntimeStagingError as exc:
        result = {"success": False, "status": exc.status, **exc.evidence}
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
