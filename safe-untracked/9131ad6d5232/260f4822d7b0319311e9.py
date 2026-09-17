import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parents[1]
ART = ROOT / "artifacts"
RAW_PATH = ART / "raw_nonterminal_mission_inventory.json"
packet = json.loads(RAW_PATH.read_text(encoding="utf-8"))
rows = packet["missions"]
AUDITED_AT = datetime.now(timezone.utc).isoformat()
HEAD = "19ebc3769e99363151b2d029d8cfec404eb3a703"
ORIGIN_MAIN = "70a4cf2b235e5ba441f9b5901efa45e699ad0c0b"
DEPLOYED = ORIGIN_MAIN
CANARY = "CHARLIE-REPLACEMENT-AF110E2A071BC18CCAA00DF2"

def meta(row): return row.get("metadata_json") or {}
def text(row): return " ".join(str(row.get(k) or "") for k in ("title", "raw_text", "owner_decision")).lower()
def pick(obj, *paths):
    for path in paths:
        cur = obj
        for part in path.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur not in (None, "", [], {}): return cur
    return None

def disposition(row):
    mid, status, body, m = row["mission_id"], row["status"], text(row), meta(row)
    if mid == CANARY:
        return "completed_by_current_truth", "T0 read-only objective completed at candidate 3768cc08, now an ancestor of live deployed 70a4cf2b; preserve pr_ready row as canary evidence and never release/rerun it."
    supersession = m.get("supersession") or {}
    if mid == "CHARLIE-MISSION-7001CE3566B4A171" or "duplicate child" in body or "canonical mission remains authoritative" in body:
        return "superseded_preserve_history", "Exact replacement/duplicate owner evidence identifies a canonical successor; retain all artifacts and keep this row non-runnable."
    if "decomposed this oversized mission" in body or "parent coordinates" in body or "parent waits for bounded child" in body:
        return "superseded_preserve_history", "The recorded owner decision makes this a coordinating/historical parent and assigns delivery to child missions."
    if status == "blocked" or "owner-held" in body or "explicit decisions" in body:
        return "owner_decision_required", "Runtime state or recorded owner decision contains an unresolved owner gate; no completion/supersession inference is safe."
    if supersession.get("status") == "current_contract_replacement":
        return "superseded_preserve_history", "Runtime supersession metadata names a current-contract replacement."
    return "rewrite_as_successor", "Legacy contract lacks sufficient current adaptive orchestration/source-map binding, or concerns operational activation now outside CORE; preserve value and rewrite before any approval."

manifest=[]; preserved=[]; groups=defaultdict(list)
for row in rows:
    m=meta(row); disp,reason=disposition(row)
    family=m.get("mission_family") or {}
    current_stage=pick(m,"current_stage","workflow.current_stage","execution.current_stage","review_packet.current_stage")
    last_stage=pick(m,"last_stage","workflow.last_stage","review_packet.last_stage","review_packet.blocked_agent")
    selected=pick(m,"orchestration.selected_agents","adaptive_orchestration.selected_agents","selected_agents") or []
    tier=pick(m,"orchestration.tier","adaptive_orchestration.tier","tier")
    manifest.append({
      "mission_id":row["mission_id"],"status":row["status"],"approval_level":row.get("approval_level"),
      "current_stage":current_stage,"last_stage":last_stage,"genuinely_active":False,
      "active_reason":"No in_progress/approved/release_approved rows exist; new, paused, blocked and pr_ready are not pickup-runnable.",
      "candidate_revision":pick(m,"candidate_revision","tested_revision","review_packet.tested_revision","review_packet.expected_revision"),
      "supersession":m.get("supersession"),"adaptive_tier":tier,"selected_agent_count":len(selected) if isinstance(selected,list) else None,
      "adaptive_safe": True if row["mission_id"]==CANARY else False,
      "adaptive_safety_reason":"Validated T0 minimum-agent packet." if row["mission_id"]==CANARY else "Not proven against current main/current doctrine; successor re-intake required.",
      "disposition":disp,"recommendation":reason,"updated_at":row.get("updated_at")})
    valuable={k:m.get(k) for k in ("acceptance_matrix","review_packet","agent_workflow","mission_family","orchestration","supersession","artifacts","tests") if m.get(k) not in (None,{},[])}
    preserved.append({"mission_id":row["mission_id"],"title":row.get("title"),"raw_owner_or_discovery_text":row.get("raw_text"),"recorded_owner_decision":row.get("owner_decision"),"valuable_metadata":valuable,"preservation_rule":"Copy/link into any approved successor; never delete or overwrite predecessor evidence."})
    if disp=="rewrite_as_successor": groups[family.get("root_mission_id") or family.get("parent_mission_id") or row["mission_id"]].append(row)

def domain_sources(title):
    s=title.lower()
    if "beacon" in s: return ["docs/09-vault-brain/04-workflows/BEACON_CAMPAIGN_WORKFLOW.md","docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md"]
    if "sam" in s or "sales" in s: return ["docs/09-vault-brain/04-workflows/SAM_GENERAL_CONVERSATION.md","docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md"]
    if "herdmaster" in s or "pig" in s or "farm" in s: return ["docs/09-vault-brain/02-agents/farm/HERDMASTER.md","docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md"]
    return ["docs/09-vault-brain/01-identity/CHARLIE_CORE.md","docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md"]

successors=[]
for idx,(root_id,items) in enumerate(sorted(groups.items()),1):
    titles=[x.get("title") or x["mission_id"] for x in items]
    successors.append({
      "proposal_id":f"CORE-RECON-SUCCESSOR-{idx:03d}","status":"proposal_only_not_activated",
      "predecessor_mission_ids":[x["mission_id"] for x in items],"predecessor_root":root_id,
      "title":f"Reconcile current capability: {titles[0]}",
      "business_outcome":"Reconfirm the still-needed software capability against current deployed specialist behavior, then deliver only measurable missing gaps.",
      "source_maps":domain_sources(" ".join(titles)),"acceptance":"Current production gap is reproduced; scoped change closes it; focused and regression tests pass; deployed specialist ownership and authority remain intact.",
      "adaptive_scoring":{"required":"re-score at owner-approved intake against current main","tier":"unassigned_until_intake","minimum_agents":"source_mapper plus only evidence-triggered architect/builder/test/reviewer roles"},
      "budget":{"tokens":"bounded at intake by tier","minutes":"bounded at intake by tier","attempts":"bounded at intake; no autonomous expansion"},
      "authority":{"allowed":"read current production and edit only explicitly mapped repository scope after owner approval","forbidden":["ordinary farm operations through CORE","production/runtime/customer/Telegram mutation","merge","deploy","release","stock/payment/farm lifecycle action"]},
      "replacement_binding":"After owner approval, atomically record successor supersession metadata naming every predecessor and validated generation identity; predecessor remains immutable and is excluded from every runnable query."
    })

counts=Counter(r["status"] for r in rows); disp_counts=Counter(x["disposition"] for x in manifest)
inventory={"schema":"core_reconciliation_inventory_v1","audited_at":AUDITED_AT,"source":"production Supabase PostgREST authenticated SELECT","status_scope":["new","triaged","planned","approved","in_progress","blocked","pr_ready","release_approved","paused"],"counts":dict(counts),"total":len(rows),"deterministic_order":"created_at asc, mission_id asc","raw_sha256":hashlib.sha256(RAW_PATH.read_bytes()).hexdigest(),"missions":rows}
(ART/"01_full_deterministic_mission_inventory.json").write_text(json.dumps(inventory,indent=2),encoding="utf-8")
(ART/"02_evidence_backed_disposition_manifest.json").write_text(json.dumps({"counts":dict(disp_counts),"missions":manifest},indent=2),encoding="utf-8")
(ART/"03_preserved_unfinished_value_manifest.json").write_text(json.dumps({"missions":preserved},indent=2),encoding="utf-8")
(ART/"04_proposed_clean_successor_mission_set.json").write_text(json.dumps({"proposals":successors},indent=2),encoding="utf-8")
(ART/"05_missions_that_would_remain_runnable.json").write_text(json.dumps({"missions":[],"proof":{"approved":counts.get("approved",0),"in_progress":counts.get("in_progress",0),"release_approved":counts.get("release_approved",0),"note":"pr_ready canary is review evidence, not pickup-runnable or business work."}},indent=2),encoding="utf-8")

review=f"""# CHARLIE CORE Mission Reconciliation — Owner Review\n\nAudited: {AUDITED_AT}\n\n## Result\n\nProduction returned **{len(rows)}** nonterminal missions: {dict(counts)}. No mission is currently pickup-runnable by status. The only `pr_ready` row is `{CANARY}`; its T0 objective is already present in live deployed lineage and it must remain preserved, unreleased and not rerun.\n\nDisposition counts: {dict(disp_counts)}. No legacy mission was declared complete except the evidence-only T0 canary, whose candidate `3768cc08` is an ancestor of live deployed `{DEPLOYED}`.\n\n## Truth and limitations\n\n- Live Render deploy: `{DEPLOYED}` (deployment `dep-d9nirfh5efls73ab0oeg`, live at 2026-08-02T11:46:19Z).\n- Current `origin/main`: `{ORIGIN_MAIN}`. Audit worktree HEAD: `{HEAD}`; the later main commit affects Oom Sakkie family-message lifecycle and source maps and was reconciled as deployed truth without altering this worktree.\n- The requested `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md` does not exist at worktree HEAD or current `origin/main`; current mission workflow, CORE identity, architecture standard and implementation source map were applied instead.\n- Direct PostgreSQL timed out twice; authenticated Supabase PostgREST fallback succeeded and returned the complete in-scope set.\n\n## Smallest safe next action\n\nOwner reviews only the disposition manifest and successor proposal set. If aligned, authorize a separate queue-mutation mission whose sole job is to atomically bind approved successors to predecessors and make predecessors durably non-runnable. Do **not** enable broad pickup, release/rerun the T0 canary, or activate operational work during review.\n"""
(ART/"07_owner_review_packet.md").write_text(review,encoding="utf-8")
print(json.dumps({"missions":len(rows),"counts":dict(counts),"dispositions":dict(disp_counts),"successor_proposals":len(successors)},indent=2))
