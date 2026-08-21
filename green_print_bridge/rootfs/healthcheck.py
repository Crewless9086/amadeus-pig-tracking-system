#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

try:
    value = json.loads(Path("/data/health.json").read_text(encoding="utf-8"))
    heartbeat = datetime.fromisoformat(value["heartbeat_at"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    # A durable business Hold is live. Restarts must not erase or churn it.
    healthy = value.get("liveness") == "alive" and age < 180
except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
    healthy = False
sys.exit(0 if healthy else 1)
