#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

try:
    value = json.loads(Path("/data/health.json").read_text(encoding="utf-8"))
    heartbeat = datetime.fromisoformat(value["heartbeat_at"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    healthy = value.get("status") in {"starting", "event_waiting", "working"} and age < 180
except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
    healthy = False
sys.exit(0 if healthy else 1)
