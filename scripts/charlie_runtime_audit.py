"""Read-only audit and explicit promotion manifest helper for CHARLIE CORE."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.runtime_integrity import cold_start_readiness, write_runtime_manifest
from modules.charlie.runner_control import RUNNER_DIR


def main():
    load_dotenv(REPO_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description="Audit or promote the exact CHARLIE CORE runtime revision.")
    parser.add_argument("action", choices=["audit", "promote"])
    parser.add_argument("--runtime-dir", default="")
    parser.add_argument("--allow-missing-manifest", action="store_true")
    parser.add_argument("--skip-github", action="store_true")
    args = parser.parse_args()
    runtime_dir = Path(args.runtime_dir).resolve() if args.runtime_dir else RUNNER_DIR
    if args.action == "promote":
        result = write_runtime_manifest(REPO_ROOT, runtime_dir=runtime_dir)
    else:
        result = cold_start_readiness(
            REPO_ROOT, runtime_dir=runtime_dir,
            require_manifest=not args.allow_missing_manifest,
            require_github=not args.skip_github,
        )
    print(json.dumps(result, indent=2))
    return 0 if result.get("success", result.get("ready", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
