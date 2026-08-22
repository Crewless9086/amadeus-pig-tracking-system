#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

try:
    value = json.loads(Path("/data/green-runtime/health.json").read_text(encoding="utf-8"))
    heartbeat = datetime.fromisoformat(value["heartbeat_at"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    # A durable business Hold is live. Restarts must not erase or churn it.
    scheduler = subprocess.run(
        ["/usr/bin/lpstat", "-r"], capture_output=True, text=True, timeout=5,
    )
    healthy = (
        value.get("liveness") == "alive"
        and age < 180
        and scheduler.returncode == 0
        and scheduler.stdout.strip() == "scheduler is running"
    )
except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, json.JSONDecodeError):
    healthy = False
sys.exit(0 if healthy else 1)
