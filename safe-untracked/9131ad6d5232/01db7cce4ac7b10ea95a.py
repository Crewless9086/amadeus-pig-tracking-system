"""Bounded read-only PostgREST fallback for the CORE mission reconciliation."""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv


OWNER_ROOT = Path(r"C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system")
load_dotenv(OWNER_ROOT / ".env", override=True)

base_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
api_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
if not base_url or not api_key:
    print(json.dumps({"success": False, "status": "supabase_rest_not_configured"}))
    raise SystemExit(2)

statuses = "new,triaged,planned,approved,in_progress,blocked,pr_ready,release_approved,paused"
params = urllib.parse.urlencode(
    {
        "select": "mission_id,status,source,raw_text,title,urgency,mission_type,approval_level,selected_next_step,owner_decision,codex_chat_write_status,metadata_json,created_at,updated_at",
        "status": f"in.({statuses})",
        "order": "created_at.asc,mission_id.asc",
        "limit": "5000",
    }
)
request = urllib.request.Request(
    f"{base_url}/rest/v1/charlie_missions?{params}",
    headers={"apikey": api_key, "Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    method="GET",
)
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        rows = json.load(response)
except urllib.error.HTTPError as exc:
    print(json.dumps({"success": False, "status": "supabase_rest_http_failed", "http_status": exc.code}))
    raise SystemExit(3)
except Exception as exc:
    print(json.dumps({"success": False, "status": "supabase_rest_read_failed", "error_type": type(exc).__name__}))
    raise SystemExit(4)

packet = {"success": True, "status": "ok", "count": len(rows), "missions": rows}
output_path = Path(__file__).parents[1] / "artifacts" / "raw_nonterminal_mission_inventory.json"
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
print(json.dumps({"success": True, "status": "ok", "count": len(rows), "output_path": str(output_path)}))
