#!/usr/bin/env python3
"""Standalone CHARLIE native runner. It intentionally has no merge/deploy mode."""

from __future__ import annotations

import argparse
import json
import signal
import threading
from pathlib import Path

from modules.charlie.native_runner.service import NativeRunnerService


def parser():
    value = argparse.ArgumentParser(description="Plugin-independent CHARLIE native runner")
    mode = value.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--watch", action="store_true")
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    value.add_argument("--poll-seconds", type=int, default=15)
    value.add_argument("--profile-home", required=True)
    value.add_argument("--repository-root", required=True)
    value.add_argument("--worktree-root", required=True)
    value.add_argument("--config-file")
    value.add_argument("--configuration-source", choices=("profile", "environment"), default="profile")
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    status_path = Path(args.worktree_root) / ".runner-status.json"
    if args.status:
        print(status_path.read_text(encoding="utf-8") if status_path.exists() else json.dumps({"state": "NOT_STARTED"}))
        return 0
    service = NativeRunnerService(profile_home=args.profile_home,
        repository_root=args.repository_root, worktree_root=args.worktree_root,
        status_path=status_path, config_path=args.config_file,
        configuration_source=args.configuration_source)
    if args.watch:
        stopping = threading.Event()
        def stop(_signum, _frame):
            stopping.set()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        return service.watch(args.poll_seconds, stop_event=stopping)
    result = service.once(dry_run=args.dry_run)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
