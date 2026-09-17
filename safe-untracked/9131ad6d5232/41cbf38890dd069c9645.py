import json
from collections import Counter
from pathlib import Path

root = Path(__file__).parents[1]
rows = json.loads((root / "artifacts/raw_nonterminal_mission_inventory.json").read_text(encoding="utf-8"))["missions"]

def pick(meta, *paths):
    for path in paths:
        cur = meta
        for part in path.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur not in (None, "", [], {}):
            return cur
    return None

summary = []
for row in rows:
    meta = row.get("metadata_json") or {}
    summary.append({
        "mission_id": row["mission_id"], "status": row["status"], "title": row.get("title"),
        "approval_level": row.get("approval_level"), "owner_decision": row.get("owner_decision"),
        "current_stage": pick(meta, "current_stage", "workflow.current_stage", "execution.current_stage", "review_packet.current_stage"),
        "last_stage": pick(meta, "last_stage", "workflow.last_stage", "review_packet.last_stage", "review_packet.blocked_agent"),
        "pr": pick(meta, "pull_request.number", "pull_request.url", "pr.number", "pr.url", "review_packet.pull_request"),
        "candidate_revision": pick(meta, "candidate_revision", "tested_revision", "review_packet.tested_revision", "review_packet.expected_revision"),
        "supersession": meta.get("supersession"), "family": meta.get("mission_family"),
        "selected_agents": pick(meta, "orchestration.selected_agents", "adaptive_orchestration.selected_agents", "selected_agents"),
        "tier": pick(meta, "orchestration.tier", "adaptive_orchestration.tier", "tier"),
        "updated_at": row.get("updated_at"),
    })
(root / "artifacts/compact_nonterminal_inventory.json").write_text(json.dumps({"counts": Counter(x["status"] for x in summary), "missions": summary}, indent=2), encoding="utf-8")
print(json.dumps({"counts": Counter(x["status"] for x in summary), "missions": summary}, indent=2))
