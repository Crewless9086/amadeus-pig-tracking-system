import json
from pathlib import Path

root = Path(__file__).parents[1]
inv = json.loads((root / "artifacts/01_full_deterministic_mission_inventory.json").read_text(encoding="utf-8"))
disp = json.loads((root / "artifacts/02_evidence_backed_disposition_manifest.json").read_text(encoding="utf-8"))
by_id = {r["mission_id"]: r for r in inv["missions"]}

out = []
for d in disp["missions"]:
    if d["disposition"] not in {"rewrite_as_successor", "owner_decision_required"}:
        continue
    r = by_id[d["mission_id"]]
    m = r.get("metadata_json") or {}
    family = m.get("mission_family") or {}
    review = m.get("review_packet") or {}
    out.append({
        "mission_id": r["mission_id"], "disposition": d["disposition"], "status": r["status"],
        "title": r.get("title"), "raw_text": r.get("raw_text"), "owner_decision": r.get("owner_decision"),
        "root": family.get("root_mission_id"), "parent": family.get("parent_mission_id"),
        "relationship": family.get("relationship"), "finding_family": family.get("finding_family"),
        "dependency": family.get("dependency"), "approval_level": r.get("approval_level"),
        "acceptance_matrix": m.get("acceptance_matrix"), "active_blockers": review.get("active_blockers"),
        "blocked_reason": review.get("blocked_reason"), "recommended_next_action": review.get("recommended_next_action"),
        "protected_operations": review.get("protected_operations") or m.get("protected_operations"),
    })

path = root / "artifacts/second_pass_evidence_extract.json"
path.write_text(json.dumps(out, indent=2), encoding="utf-8")
for r in out:
    print("\t".join(str(r.get(k) or "") for k in ("disposition","mission_id","title","root","finding_family","owner_decision")))
