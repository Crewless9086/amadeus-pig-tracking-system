"""Plan or stage CORE runtime source without starting or scheduling CORE."""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.runtime_staging import RuntimeStagingError, plan_runtime_staging, stage_runtime, plan_runtime_initialization, initialize_runtime_stopped, stage_initialized_runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["plan", "stage", "plan-initialize", "initialize-stopped", "stage-initialized"])
    parser.add_argument("--source-ref", required=False)
    parser.add_argument("--runtime-root", required=False)
    parser.add_argument("--execution-root", required=False)
    parser.add_argument("--state-root", required=False)
    parser.add_argument("--receipt", required=False)
    parser.add_argument("--receipt-sha256", required=False)
    parser.add_argument("--expected-runtime-head", required=False)
    parser.add_argument("--expected-execution-head", required=False)
    parser.add_argument("--expected-manifest-commit", required=False)
    parser.add_argument("--expected-task-sha256", required=False)
    parser.add_argument("--canonical-root")
    parser.add_argument("--assigned-root")
    parser.add_argument("--mission-id")
    parser.add_argument("--interpreter")
    args = parser.parse_args()
    try:
        if args.action in {"plan-initialize", "initialize-stopped"}:
            required = ("canonical_root", "assigned_root", "state_root", "source_ref", "mission_id", "interpreter", "expected_task_sha256")
        elif args.action == "stage-initialized":
            required = ("state_root", "receipt", "receipt_sha256", "expected_task_sha256")
        else:
            required = ("source_ref", "runtime_root", "execution_root", "state_root", "receipt", "receipt_sha256",
                        "expected_runtime_head", "expected_execution_head", "expected_manifest_commit", "expected_task_sha256")
        if any(not getattr(args, name) for name in required):
            parser.error("all exact identity arguments for the selected action are required")
        if args.action in {"plan-initialize", "initialize-stopped"}:
            plan = plan_runtime_initialization(**{name: getattr(args, name) for name in required})
            result = plan if args.action == "plan-initialize" else initialize_runtime_stopped(plan)
        elif args.action == "stage-initialized":
            result = stage_initialized_runtime(state_root=args.state_root, receipt_path=args.receipt,
                receipt_sha256=args.receipt_sha256, expected_task_sha256=args.expected_task_sha256)
        else:
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
