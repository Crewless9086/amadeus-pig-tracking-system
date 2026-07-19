"""Names-only Phase 2 workspace and revision audit."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.charlie.concurrency_control import revision_truth, workspace_inventory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--render-commit", default="")
    args = parser.parse_args()
    inventory = workspace_inventory(args.repo_root)
    truth = revision_truth(args.repo_root, render_deployed_commit=args.render_commit)
    safe_workspaces = [{key: item.get(key) for key in ("path", "role", "branch", "commit", "is_current", "dirty_files")} for item in inventory.get("workspaces", [])]
    print(json.dumps({"version": "core_concurrency_audit_v1", "workspace": {**inventory, "workspaces": safe_workspaces}, "revision_truth": truth}, indent=2))
    return 0 if inventory.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
