import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parents[1]
ART = ROOT / "artifacts"
inventory = json.loads((ART / "01_full_deterministic_mission_inventory.json").read_text(encoding="utf-8"))
dispositions = json.loads((ART / "02_evidence_backed_disposition_manifest.json").read_text(encoding="utf-8"))
preserved = json.loads((ART / "03_preserved_unfinished_value_manifest.json").read_text(encoding="utf-8"))
by_id = {r["mission_id"]: r for r in inventory["missions"]}
preserved_by_id = {r["mission_id"]: r for r in preserved["missions"]}
rewrite_ids = [r["mission_id"] for r in dispositions["missions"] if r["disposition"] == "rewrite_as_successor"]
decision_ids = [r["mission_id"] for r in dispositions["missions"] if r["disposition"] == "owner_decision_required"]
NOW = datetime.now(timezone.utc).isoformat()
MAIN = "70a4cf2b235e5ba441f9b5901efa45e699ad0c0b"

FAMILY_META = {
  "F01_OOM_SAKKIE_MANAGER_LIFECYCLE": {"priority":1,"label":"Oom Sakkie persistent manager lifecycle","proposal":"S01_OOM_DAILY_CONTROL_CLOSURE","delivered":["Authenticated generic family-message card lifecycle, natural follow-up editing, provider identity and first HERDMASTER factual-welfare adapter are live at current main 70a4cf2b; successor excludes rebuilding them."]},
  "F02_HERDMASTER_OPERATIONAL_ADAPTER": {"priority":2,"label":"HERDMASTER operational adapter and herd intelligence","proposal":"S02_HERDMASTER_OPERATIONAL_ADAPTER","delivered":["PR #373 owner-session guard, PR #390 control-plane incident repair, PR #397 auction implementation and current natural health/loss preview/factual writer are preserved as delivered evidence, not repeated objectives."]},
  "F03_ROOTLINE_OPERATIONAL_MANAGEMENT": {"priority":3,"label":"ROOTLINE operational management","proposal":"S03_ROOTLINE_OPERATIONAL_MANAGEMENT","delivered":["Deployed Level 1 Daily Brief and read-only Daily Advisor, including the single supervised C12345 safe-OFF proof, are baseline; they do not prove routine or autonomous control."]},
  "F04_SAM_LIVESTOCK_CONTINUITY": {"priority":4,"label":"SAM Livestock continuous narrow response","proposal":"S04_SAM_LIVESTOCK_CONTINUITY","delivered":["Current Stage 4 SAM routing, canonical reads and env-gated order-intake surfaces are baseline; successor does not recreate legacy Sheets/n8n behavior or broaden customer authority."]},
  "F05_BEACON_REPEATABLE_OPERATION": {"priority":5,"label":"BEACON repeatable organic operation and later paid boost","proposal":["S05_BEACON_ORGANIC_OPERATION","S06_BEACON_PAID_BOOST"],"delivered":["Existing gated media library, creative studio, publication binding/authorization and performance evidence surfaces are baseline; duplicate data-model/frontend/release objectives are removed."]},
  "F06_CORE_MINIMUM_RELIABILITY": {"priority":6,"label":"CHARLIE/CORE minimum enabling reliability","proposal":"S07_CORE_MINIMUM_RELIABILITY","delivered":["Adaptive tier scoring, minimum-agent packets, generation binding and the successful T0 canary are current truth; the legacy always-on executive programme is not revived."]},
}

def assign(row):
    s = f"{row.get('title','')} {row.get('raw_text','')}".lower()
    if "beacon" in s or "facebook" in s or "campaign" in s or "attribution" in s:
        return "F05_BEACON_REPEATABLE_OPERATION"
    if "sam" in s or "live stock" in s or "livestock" in s and "customer" in s or "environment timeout" in s or "baseline regression" in s:
        return "F04_SAM_LIVESTOCK_CONTINUITY"
    if "herdmaster" in s or "pig " in s or "pig-" in s or "farm profitability" in s or "auction" in s or "create order" in s:
        return "F02_HERDMASTER_OPERATIONAL_ADAPTER"
    if "telegram" in s or "outcome comm" in s or "executive attention" in s or "notification reliability" in s:
        return "F01_OOM_SAKKIE_MANAGER_LIFECYCLE"
    return "F06_CORE_MINIMUM_RELIABILITY"

grouped = defaultdict(list)
trace = []
for mid in rewrite_ids:
    row = by_id[mid]
    family = assign(row)
    grouped[family].append(mid)
    preserved_value = preserved_by_id[mid]
    trace.append({
      "predecessor_mission_id":mid,"predecessor_status":row["status"],"title":row.get("title"),
      "consolidated_family_id":family,"proposed_successor_ids":FAMILY_META[family]["proposal"] if isinstance(FAMILY_META[family]["proposal"],list) else [FAMILY_META[family]["proposal"]],
      "unique_unfinished_value_preserved":True,
      "preserved_value_reference":f"artifacts/03_preserved_unfinished_value_manifest.json#{mid}",
      "delivered_objective_removed": any(term in (row.get("owner_decision") or "").lower() for term in ("superseded","deployed tested pr","resolved its exact incident","completed repair")),
      "queue_effect":"none_during_reconciliation",
      "future_non_runnable_binding":"Required many-to-one supersession link in the later atomic queue-governance transaction."
    })

# ROOTLINE is a current-doctrine gap, not a rewritten legacy queue item.
families=[]
for fid, meta in sorted(FAMILY_META.items(), key=lambda x:x[1]["priority"]):
    mids=grouped.get(fid,[])
    titles=[by_id[mid].get("title") for mid in mids]
    families.append({
      "family_id":fid,"priority":meta["priority"],"label":meta["label"],"rewrite_predecessor_count":len(mids),
      "predecessor_mission_ids":mids,"deduplicated_objective_examples":titles[:12],
      "unique_value_source":"Full raw text, acceptance/review artifacts, tests, family dependencies and owner decisions remain in artifacts/01 and /03 and are linked by artifact/10.",
      "operational_boundary":"Ordinary execution belongs to Oom Sakkie and the named deployed specialist. CORE may build or repair only missing software capability.",
      "delivered_objectives_removed":meta["delivered"],
      "conflict_policy":"If later evidence conflicts, stop this family at owner_decision_required; do not infer completion or activate work.",
      "proposed_successor_ids":meta["proposal"] if isinstance(meta["proposal"],list) else [meta["proposal"]]
    })

T4_BASE=["source_mapper","technical_architect","builder","tester","qa_red_team","reviewer","publisher"]
def proposal(pid, order, title, family, depends, agents, outcome, acceptance, authority, stop, notes=""):
    return {"successor_id":pid,"state":"proposal_only_not_created","programme_order":order,"title":title,"family_id":family,
      "depends_on":depends,"adaptive_tier":"T4" if pid!="S07_CORE_MINIMUM_RELIABILITY" else "T3",
      "tier_reason":"Protected customer/provider, farm, hardware, publication or production consequence requires T4." if pid!="S07_CORE_MINIMUM_RELIABILITY" else "Cross-module CORE correction without business-operation authority requires T3.",
      "minimum_sufficient_agents":agents,
      "budget":{"wall_clock_minutes":1440 if pid!="S07_CORE_MINIMUM_RELIABILITY" else 960,"total_tokens":200000 if pid!="S07_CORE_MINIMUM_RELIABILITY" else 140000,"max_stage_attempts":3,"max_backflows":4},
      "measurable_business_outcome":outcome,"acceptance_outcomes":acceptance,"authority":authority,
      "stop_conditions":stop+["Any evidence conflict changes the family to owner_decision_required.","No merge, deploy, activation or production proof without its separate exact owner gate."],
      "predecessor_mission_ids":grouped.get(family,[]),"notes":notes}

program=[
 proposal("S01_OOM_DAILY_CONTROL_CLOSURE",1,"Close Oom Sakkie's persistent daily-control lifecycle gaps","F01_OOM_SAKKIE_MANAGER_LIFECYCLE",[],T4_BASE[:5]+["security_reviewer","business_reviewer"]+T4_BASE[5:],
  "One authenticated natural owner request is visibly acknowledged, delegated to the correct deployed specialist, followed through on one durable card, confirmed when protected action is needed, and truthfully completed or excepted without CORE becoming the operational manager.",
  ["Current-main generic family lifecycle and HERDMASTER factual-welfare adapter are treated as baseline, not rebuilt.","Authenticated private-owner intake produces one provider-confirmed visible acknowledgement bound to provider/chat/message identity.","Dispatch names the responsible specialist and never claims receipt/start without target-specific acknowledgement and fresh activity.","Natural follow-up edits the same card and preserves known context.","Exact confirmation binds operation, preview and evidence generation; supported exactly-once action writes once and direct replay writes zero rows.","Unsupported or compound effects return one truthful exception and perform zero partial writes.","Interrupted attempted delivery causes no blind retry; repeated provider update causes zero duplicate sends, edits or rows.","Completion/exception state remains readable after restart and unrelated ROOTLINE, SAM, BEACON and farm-state digests remain unchanged."],
  {"allowed":"Scoped repository implementation and tests for missing lifecycle/adapters after owner approval.","forbidden":["ordinary farm task execution by CORE","Telegram contact during build","production runtime acquisition","farm/customer mutation","merge/deploy/release"]},
  ["Provider identity or owner authentication is ambiguous.","A required specialist lacks a deployed adapter.","A proposed effect lacks one canonical exactly-once coordinator."]),
 proposal("S02_HERDMASTER_OPERATIONAL_ADAPTER",2,"Complete HERDMASTER governed operational adapter","F02_HERDMASTER_OPERATIONAL_ADAPTER",["S01_OOM_DAILY_CONTROL_CLOSURE"],T4_BASE[:5]+["product_reviewer","evidence_reviewer"]+T4_BASE[5:],
  "Oom Sakkie can delegate natural health/loss and herd-priority requests to HERDMASTER, which returns current evidence, one bounded recommendation/preview, and uses only owner-confirmed exactly-once canonical updates.",
  ["Natural health/loss intake separates observed fact, owner suspicion, veterinary attribution and inference.","Fresh canonical observations and separate management intents produce traceable breeding, retention, sale and welfare priorities.","Milestone reminders have positive/negative freshness tests and never silently mutate livestock.","Supported effects commit atomically once; mismatch, stale evidence or unsupported compound effect writes zero rows.","All unique lifecycle, retention/correction, migration, visual-evidence and audit requirements remain traceable to predecessors."],
  {"allowed":"Scoped HERDMASTER/Oom adapter code and tests.","forbidden":["diagnosis","unconfirmed livestock mutation","migration application","auction activation","ordinary herd management by CORE"]},
  ["Observation governance choices in artifact/11 remain undecided.","Canonical evidence is stale or incomplete."]),
 proposal("S03_ROOTLINE_OPERATIONAL_MANAGEMENT",3,"Advance ROOTLINE from daily advice to supervised management","F03_ROOTLINE_OPERATIONAL_MANAGEMENT",["S01_OOM_DAILY_CONTROL_CLOSURE"],T4_BASE[:5]+["evidence_reviewer"]+T4_BASE[5:],
  "Oom Sakkie receives a current ROOTLINE irrigation plan and can supervise an explicitly authorized execution; autonomous control remains a later commissioned, bounded state.",
  ["Daily plan uses fresh canonical weather, power, irrigation and policy evidence and distinguishes Needs Data/Hold.","Supervised command binds exact field/channel, plan, authority window and safe-OFF closure.","Replay performs zero additional hardware actions.","Loss of evidence, acknowledgement or connectivity fails safe closed.","Autonomous scheduling remains disabled until separately commissioned with bounded runtime and rollback proof."],
  {"allowed":"Scoped planning/supervised-control software after exact gates.","forbidden":["hardware use during build","uncommissioned autonomy","CORE operating irrigation","implicit IFTTT/n8n authority"]},
  ["Hardware identity or OFF proof is unavailable.","Owner policy or commissioning decision is missing."],"No rewrite predecessor existed; proposal is grounded in current ROOTLINE doctrine/source map and requested programme priority."),
 proposal("S04_SAM_LIVESTOCK_CONTINUITY",4,"Prove continuous narrow SAM Livestock response and owner attention","F04_SAM_LIVESTOCK_CONTINUITY",["S01_OOM_DAILY_CONTROL_CLOSURE","S02_HERDMASTER_OPERATIONAL_ADAPTER"],T4_BASE[:5]+["business_reviewer"]+T4_BASE[5:],
  "SAM sustains one narrow livestock customer journey using current inventory evidence, surfaces only genuine owner attention through Oom Sakkie, and never invents availability or authority.",
  ["One continuous conversation preserves context through clarification and topic changes.","Availability and animal facts carry current canonical provenance.","Customer delivery truth distinguishes accepted, provider-delivered/read, failed and ambiguous.","Owner-attention item is idempotent, buttonless until a genuine decision, and resolves on the original card.","No order, reservation, quote, customer send expansion or stock mutation beyond separately authorized rails."],
  {"allowed":"Scoped SAM/Oom attention software and tests.","forbidden":["unapproved customer sends","stock/order/payment authority","CORE handling ordinary sales"]},
  ["Provider delivery state is ambiguous.","Canonical livestock evidence is stale."]),
 proposal("S05_BEACON_ORGANIC_OPERATION",5,"Establish repeatable owner-gated BEACON organic operation","F05_BEACON_REPEATABLE_OPERATION",["S01_OOM_DAILY_CONTROL_CLOSURE"],T4_BASE[:5]+["business_reviewer"]+T4_BASE[5:],
  "BEACON repeatedly prepares, approves, publishes through existing gated rails, and measures organic content while Oom Sakkie coordinates owner attention.",
  ["Private intake, library acceptance, public-use approval and publication authorization remain separate.","Every publication binds approved asset/content/account and records provider identity/outcome.","Repeat and replay do not duplicate publication.","Performance evidence links publication to analytics without inventing sales attribution.","Organic weekly operation completes twice with no authority expansion."],
  {"allowed":"Scoped BEACON organic software/tests after owner approval.","forbidden":["publication during build","paid spend","unapproved public use","fabricated attribution"]},
  ["Rights/public-use approval is absent.","Provider publication identity is ambiguous."]),
 proposal("S06_BEACON_PAID_BOOST",6,"Add later bounded BEACON paid-boost capability","F05_BEACON_REPEATABLE_OPERATION",["S05_BEACON_ORGANIC_OPERATION"],T4_BASE[:5]+["business_reviewer"]+T4_BASE[5:],
  "A separately approved high-performing organic item can receive a strictly bounded paid boost with exact spend, audience, duration, stop and measurement controls.",
  ["Requires measured organic eligibility and explicit owner approval for asset, account, audience, budget and dates.","Hard spend ceiling and kill switch are deterministic.","No automatic rebudgeting, audience expansion or campaign creation.","Provider spend/outcome reconciliation is durable and ambiguous execution is not blindly retried."],
  {"allowed":"Design/build bounded paid-boost rail only after organic proof and exact owner approval.","forbidden":["spend during build","automatic budget changes","unapproved publication"]},
  ["Organic proof is insufficient.","Any spend/account/audience parameter lacks exact owner approval."]),
 proposal("S07_CORE_MINIMUM_RELIABILITY",7,"Apply only CORE corrections required by the programme","F06_CORE_MINIMUM_RELIABILITY",[],T4_BASE,
  "CORE safely creates and executes only owner-approved consolidated successors, with deterministic many-to-one predecessor retirement and no broad pickup.",
  ["Generalized many-to-one supersession binding excludes every linked predecessor from all runnable queries.","Atomic transaction cannot leave successor created while any predecessor remains runnable.","Queue filters derive from authoritative owner queue and preserve archive/family visibility.","Lease, artifact binding, notification and portfolio fixes are implemented only when reproduced against a programme mission.","Broad pickup remains disabled before, during and after queue governance."],
  {"allowed":"Scoped CORE queue/reliability code and tests after separate authorization.","forbidden":["broad pickup","mission approval","runtime activation","business-operation implementation","self-release"]},
  ["Many-to-one supersession cannot be proven atomic.","Any proposed correction is not reproduced by a consolidated successor."],"This is an enabling correction set, not an always-on executive programme revival. It runs only before the dependent mission that proves the need."),
]

trace_packet={"schema":"core_predecessor_successor_traceability_v1","generated_at":NOW,"rewrite_candidate_count":len(rewrite_ids),"mapped_count":len(trace),"unique_predecessor_count":len(set(x["predecessor_mission_id"] for x in trace)),"duplicate_mappings":len(trace)-len(set(x["predecessor_mission_id"] for x in trace)),"unmapped_predecessors":sorted(set(rewrite_ids)-{x["predecessor_mission_id"] for x in trace}),"mappings":trace,
 "atomic_retirement_procedure":{"state":"proposal_only","prerequisite":"Separately authorize and deploy a generalized many-to-one supersession ledger/query contract; current single-predecessor metadata is insufficient for consolidated successors.","steps":["Freeze owner-approved successor contract and exact predecessor set.","Acquire one database transaction and lock all predecessor rows in deterministic mission_id order.","Recheck every predecessor status/generation and broad-pickup-disabled invariant.","Insert exactly one successor in new/non-runnable state with current adaptive packet and immutable predecessor set.","Insert one append-only supersession link per predecessor, bound to successor and orchestration generation.","Verify authoritative runnable queries exclude every linked predecessor and the successor remains non-runnable pending separate approval.","Commit all links and successor atomically; rollback everything on any mismatch.","Append owner-review evidence; approval and pickup activation remain separate later owner actions."],"required_failure_mode":"Rollback leaves no successor and no changed predecessor/queue state."}}

(ART/"08_consolidated_mission_families.json").write_text(json.dumps({"schema":"core_consolidated_families_v1","generated_at":NOW,"input_rewrite_candidates":70,"family_count":len(families),"families":families},indent=2),encoding="utf-8")
(ART/"09_prioritized_successor_programme.json").write_text(json.dumps({"schema":"core_successor_programme_v1","generated_at":NOW,"production_revision":MAIN,"successor_count":len(program),"activation_state":"none_created_or_activated","programme":program},indent=2),encoding="utf-8")
(ART/"10_predecessor_successor_traceability.json").write_text(json.dumps(trace_packet,indent=2),encoding="utf-8")

decisions = """# Owner decisions required — consolidated second pass

No queue action was taken. Deferral preserves every predecessor row and its artifacts.

| Predecessor mission | Unresolved choice | Practical consequence | Recommended choice | Preserved if deferred |
|---|---|---|---|---|
| `CHARLIE-SCOPE-5148EF3E72992C91` | Who may capture observations; retention/deletion; correction authority; whether to apply its migration. | Without a governance decision, HERDMASTER cannot safely treat observations as durable operational evidence. | Oom Sakkie captures authenticated owner statements; retain append-only provenance; corrections append and supersede rather than delete; migration remains a separate exact owner gate after schema review. | Candidate `3a63246d…`, lifecycle design, protected migration note, tests and review evidence. |
| `CHARLIE-MISSION-BDC9DE4E2E6FF629` | Resume its UI/filter patch or replace it with current generalized queue governance. | Resuming can reintroduce legacy status-bucket assumptions and does not solve many-to-one retirement. | Defer the legacy patch; reproduce only its valid owner-queue visibility requirements inside `S07_CORE_MINIMUM_RELIABILITY`. | Frozen file scope, owner-queue count requirement, frontend regressions and artifact-binding failure evidence. |
| `CHARLIE-HERDMASTER-OBSERVATION-INTENT-INTEGRATION-20260721-R63C034E2` | Accept a new consolidated HERDMASTER contract or continue bounded legacy backflow after its correction budget was exhausted. | Legacy continuation risks repeating recovery slices while freshness, intent separation and milestone tests remain failed. | Choose the consolidated `S02_HERDMASTER_OPERATIONAL_ADAPTER`; carry all failed acceptance requirements forward and do not apply migrations/live canaries yet. | Freshness-aware reads, separate intent rail, traceable recommendation/reminder requirements, authority guards and all QA evidence. |
| `CHARLIE-SCOPE-DE10163AB1453469` | Build the legacy frontend now or wait for the canonical lifecycle/capture contract. | UI-first work would encode unresolved observation, advisory-intent and lifecycle semantics. | Defer frontend work until `S02` freezes the canonical read/capture contract; then include only the minimum operational view justified by that contract. | Separate Observation/Advisory Intent/Lifecycle layout, pig-ID mismatch tests, audit/idempotency requirements and desktop/mobile evidence requirement. |
"""
(ART/"11_owner_decisions_required.md").write_text(decisions,encoding="utf-8")

first=program[0]
packet=f"""# CHARLIE CORE fresh-start owner packet

Generated: {NOW}

## Consolidated result

The 70 rewrite candidates reduce to **7 proposed successor software missions** across six semantic families. None has been created, approved or activated. The authoritative queue remains 55 `new`, 27 `paused`, 3 `blocked`, one historical `pr_ready` T0 canary, and zero `approved`, `in_progress` or `release_approved` rows. Therefore broad pickup remains disabled in effect and no existing mission is pickup-runnable.

## First recommended mission only

`S01_OOM_DAILY_CONTROL_CLOSURE` — **Close Oom Sakkie's persistent daily-control lifecycle gaps**.

It is the fastest route to Oom Sakkie taking daily control because current production already contains the authenticated generic family-message card lifecycle and the first natural HERDMASTER welfare adapter. This mission does not rebuild those delivered capabilities. It closes only the remaining manager loop: visible intake, truthful specialist dispatch, natural follow-up, exact confirmation, durable completion and bounded exception handling. Ordinary farm operations remain with Oom Sakkie and deployed specialists; CORE only supplies missing software.

- Adaptive tier: **T4**, because authenticated Telegram/provider delivery and protected operational confirmation have high consequence.
- Minimum agent set: `{', '.join(first['minimum_sufficient_agents'])}`.
- Budget: 200,000 total tokens, 1,440 wall-clock minutes, three attempts per stage and four bounded backflows.
- Old missions replaced: {', '.join('`'+x+'`' for x in first['predecessor_mission_ids']) if first['predecessor_mission_ids'] else 'No directly assigned predecessor; current delivered baseline and consolidated lifecycle evidence apply.'}

### Exact acceptance outcomes

""" + "\n".join(f"- {x}" for x in first["acceptance_outcomes"]) + """

## Broad-pickup proof

`artifacts/05_missions_that_would_remain_runnable.json` records an empty runnable set. The production snapshot contains zero `approved`, `in_progress` and `release_approved` missions. This second pass issued no queue/runtime write and created no successor. `CHARLIE-REPLACEMENT-AF110E2A071BC18CCAA00DF2` remains historical `pr_ready` proof only and must never be released or rerun.

## Later atomic queue-governance procedure

Do not create successors until a separately authorized CORE governance correction implements and proves generalized many-to-one supersession. After owner approval, one database transaction must lock the exact predecessors, recheck status/generation and pickup-disabled truth, insert one successor as `new`/non-runnable, append one immutable successor-generation link per predecessor, prove every predecessor is excluded from every runnable query, and commit all-or-nothing. Any mismatch rolls back the successor and every link. Approval and pickup release remain separate later owner actions.

Smallest safe next action: owner reviews `S01` and the four decisions in artifact 11 only. No queue change is needed for review.
"""
(ART/"12_fresh_start_owner_packet.md").write_text(packet,encoding="utf-8")

assert len(rewrite_ids)==70 and len(trace)==70 and not trace_packet["unmapped_predecessors"] and trace_packet["duplicate_mappings"]==0
assert len(program)==7
print(json.dumps({"rewrite_candidates":len(rewrite_ids),"families":len(families),"successor_missions":len(program),"trace_mapped":len(trace),"owner_decisions":len(decision_ids)},indent=2))
