"""CLI for the serialized provider-origin CORE activation rail."""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.runtime_activation import (
    ActivationError,
    WindowsExactTaskController,
    plan_activation,
    prepare_activation,
    read_activation_runtime_evidence,
    recover_activation,
    verify_or_recover_activation,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Govern provider-origin observe-only CORE activation.")
    parser.add_argument("action", choices=("dry-run", "prepare", "verify", "recover"))
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--runtime-root")
    parser.add_argument("--execution-root")
    parser.add_argument("--authority")
    parser.add_argument("--authority-sha256")
    parser.add_argument("--activation-id")
    args = parser.parse_args(argv)
    controller = WindowsExactTaskController()
    try:
        if args.action in {"dry-run", "prepare"}:
            if not all((args.runtime_root, args.execution_root, args.authority, args.authority_sha256)):
                parser.error("dry-run/prepare require runtime, execution, authority and authority digest")
            plan = plan_activation(
                authority_path=args.authority,
                authority_sha256=args.authority_sha256,
                state_root=args.state_root,
                runtime_root=args.runtime_root,
                execution_root=args.execution_root,
            )
            result = plan if args.action == "dry-run" else prepare_activation(
                plan, task_controller=controller
            )
        elif args.action == "verify":
            state_root = Path(args.state_root)
            result = verify_or_recover_activation(
                state_root=state_root,
                verification_reader=lambda packet: read_activation_runtime_evidence(
                    packet, state_root=state_root
                ),
                task_controller=controller,
            )
        else:
            if not args.activation_id:
                parser.error("recover requires --activation-id")
            result = recover_activation(
                state_root=args.state_root,
                task_controller=controller,
                activation_id=args.activation_id,
            )
    except ActivationError as exc:
        result = {"success": False, "status": exc.status, **exc.evidence}
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
