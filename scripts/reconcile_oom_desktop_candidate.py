"""Exact OMQ conversation-followup maintainer reconciliation; no public apply endpoint.

Caller authentication is a trusted maintainer boundary, never inferred from files.
Preparation is DB-free. Apply performs canonical metadata reconciliation only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION = "oom_desktop_candidate_reconciliation_v1"
MISSION_ID = "OMQ-20260813-03-MORNING-CONTAINMENT"
PARENT_ID = "OMQ-20260813-03"
BASE = '3a8f06266552196dadebfce270bf5c4f977a29d5'
# Exact source pins are not approval. Applying the reconciliation still requires
# independent authenticated owner approval of the exact manifest and scope.
CANDIDATE_PR = 1364
HEAD = 'e8af6a1d18bc76b2617f6de3a8133c8a559b5cb4'
TREE = '84b1b3b67fcbb8e13834fb3890192f6bb8381bba'
# The complete runtime candidate is reviewed; no later qualification delta is allowed.
APPROVED_RUNTIME_HEAD = HEAD
QUALIFICATION_TEST_PATHS = []
BRANCH = 'codex/herdmaster-question-routing-20260929'
PREDECESSOR_PR = 1363
PREDECESSOR_BASE = '5c3e6dc7211bb8285acbec3987974241cc2e152f'
PREDECESSOR_HEAD = 'd20bc93a24c156f7e6bb19d0cf496811d407a48d'
PREDECESSOR_BRANCH = 'codex/oom-expired-confirmation-continuation-20260929'
PATHS = [
    '.github/workflows/oom-sakkie-audit-rails.yml',
    'docs/09-vault-brain/02-agents/farm/HERDMASTER.md',
    'docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md',
    'docs/09-vault-brain/CHANGELOG.md',
    'modules/agents/herdmaster.py',
    'modules/oom_sakkie/farm_manager_loop.py',
    'modules/oom_sakkie/farm_manager_runtime.py',
    'modules/oom_sakkie/herd_read_queries.py',
    'modules/oom_sakkie/herdmaster_request_runtime.py',
    'modules/oom_sakkie/semantic_front_door.py',
    'modules/oom_sakkie/service.py',
    'modules/oom_sakkie/telegram_gateway.py',
    'modules/oom_sakkie/tools.py',
    'modules/pig_weights/herdmaster_breeding_attention_service.py',
    'modules/pig_weights/herdmaster_breeding_operating_loop.py',
    'modules/pig_weights/herdmaster_breeding_policy.py',
    'modules/pig_weights/herdmaster_daily_manager_evidence.py',
    'static/assets/agents/herdmaster/agent.md',
    'tests/test_herdmaster_breeding_chronology.py',
    'tests/test_herdmaster_breeding_operating_loop.py',
    'tests/test_oom_sakkie_conversation_followup.py',
    'tests/test_oom_sakkie_herd_read_queries.py',
]
PREDECESSOR_PATHS = [
    '.github/workflows/oom-sakkie-audit-rails.yml',
    'docs/09-vault-brain/04-workflows/HERDMASTER_NATURAL_HEALTH_AND_LOSS_INTAKE_WORKFLOW.md',
    'docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md',
    'docs/09-vault-brain/CHANGELOG.md',
    'modules/oom_sakkie/family_message_lifecycle.py',
    'modules/oom_sakkie/herdmaster_burst_recovery.py',
    'modules/oom_sakkie/herdmaster_retained_recovery_runtime.py',
    'modules/oom_sakkie/manager_case_sources.py',
    'modules/oom_sakkie/protected_action_runtime.py',
    'modules/oom_sakkie/retained_mortality_confirmation.py',
    'modules/oom_sakkie/retained_mortality_continuation.py',
    'modules/oom_sakkie/retained_mortality_presentation.py',
    'modules/oom_sakkie/telegram_direct.py',
    'tests/test_oom_sakkie_retained_confirmation_feedback.py',
    'tests/test_oom_sakkie_retained_mortality_continuation_postgres.py',
    'tests/test_oom_sakkie_retained_mortality_presentation_postgres.py',
]
WEB_SERVICE = "srv-d6sijjkhg0os73f7regg"
WEB_ROLLBACK = BASE
# These identify retired predecessor effects, not successor authority.
SCHEDULER_SERVICE = "crn-d9us4d3ncjis73adehrg"
SCHEDULER_ROLLBACK = "f9c003855cc335be6b652f313bfb0e3c02fb1f2a"
HELPERS = ("modules/charlie/mission_store.py", "modules/charlie/mission_control.py",
           "scripts/render_oom_desktop_registration_sql.py")
MAINTAINER_PATHS = {"scripts/reconcile_oom_desktop_candidate.py",
    "tests/test_oom_desktop_candidate_reconciliation.py",
    ".github/workflows/oom-desktop-rebind-qualification.yml",
    "scripts/correct_oom_presend_timeout.py", "tests/test_oom_presend_timeout_correction.py",
    "scripts/extend_oom_unsent_confirmation.py", "tests/test_oom_unsent_confirmation_extension.py",
    "scripts/render_oom_desktop_registration_sql.py", "tests/test_oom_desktop_registration_sql.py"}
DECISION = "reconcile_exact_oom_conversation_followup_candidate"
TASK_ID = "01a0b9d5-5c55-7e30-a5fc-aea27c93ffd6"
REMOVED_EFFECTS = {'application_revision_rollback:web:5c3e6dc7211bb8285acbec3987974241cc2e152f'}
ADDED_EFFECTS = {'herdmaster_canonical_domain_scoped_read_answers', 'application_revision_rollback:web:3a8f06266552196dadebfce270bf5c4f977a29d5'}
REMOVED_FORBIDDEN_EFFECTS = set()
ADDED_FORBIDDEN_EFFECTS = set()
REQUIRED_TESTS = {"Closed Render migration rail with disposable Postgres",
    "Playwright real-browser behavior gate", "Unit tests with disposable Postgres audit rails",
    "charlie-core", "mission-admission"}
REQUIRED_ACCEPTANCE = {
    "Route inventory counts, pen capacity, weighing attention, litter/weaning attention, breeding plans and HERDMASTER owner dependencies through explicit typed read capabilities and the existing canonical services. Preserve the selected capability through the existing front door and gateway; do not substitute a generic farm brief or an unrelated pending question. Reuse existing breeding execution and scoped follow-up rails rather than create another worker, data owner or queue.",
    "Keep canonical reads bounded and read-only. Missing, malformed or unavailable evidence must remain an explicit gap, never a zero count or no-work assertion. Identify relevant animals, litters and pens from current evidence, disclose bounded-list remainders and distinguish recorded farm status from a verified physical count. Pen capacity is a records comparison; do not diagnose physical overcrowding or calculate maternity headcount excess from undefined capacity units.",
    "Preserve the existing weighing eligibility and schedule rules, sale/order and lifecycle reconciliation, pregnancy evidence and litter identity. Planned weaning never becomes completed weaning. A recorded completed litter must supersede an earlier near-farrowing observation for the same cycle; unknown or inconsistent later chronology remains explicit. Current nursing classification requires confirmed farrowing evidence, and proposed placements must not treat a planned weaning date as completed weaning. Qualify the exact breeding chronology and operating-loop tests alongside the canonical read journey tests. Scope genuine HERDMASTER owner questions and supported physical tasks before presentation limits; unrelated specialist failures and agent-owned technical work must not become owner obligations.",
    "This read-routing repair adds no model call, confirmation bypass, farm mutation, mission closure, provider replay, scheduler deployment, configuration change or schema change. Preserve the existing durable US$1 SAST-day OpenAI cap and all protected confirmation, mortality, delivery and current recipient controls. Any actual farm update still uses its existing separately authorized protected path.",
    "Prove the exact deployed six owner question journeys with current canonical readback and provider-bound responses; tests and hosted qualification alone are not owner acceptance. Check distinct domain answers, truthful failures, Afrikaans/English behavior and preserved general briefs. Do not fabricate a genuine owner test or mark full fleet autonomy from successful read questions.",
    "After releasing an incomplete initial reconciliation snapshot, take one fresh whole-cohort lock snapshot in canonical case-ID order only when all absent candidates are unique non-BEACON terminal findings. Preserve the original ordered fallback for insertion-capable gaps, every duplicate key, BEACON absences and a second-snapshot deletion that makes insertion possible; never acquire a lower follow-up lock from a retained terminal absence.",
    "Prove the real PostgreSQL 314/317-candidate cohorts with 32 absent terminal findings use two whole-cohort lookup reads while preserving material events, generations, observation epochs, canonical identities and leases. Preserve concurrent insertion between snapshots, second-snapshot deletion rollback, post-snapshot insertion containment, reversed-cohort serialization and owning current-evidence refresh before delivery.",
    "Exercise an unexpired protected confirmation through real preview, claim and family delivery gates with explicit synthetic collection, refresh and preparation costs; the slower control must remain unattempted. Keep the 80-second cycle deadline and 30-second send reserve unchanged. Collector timeout before the global cutoff must contain only that owner while ready specialists progress; late results cannot send and a later cycle must reclaim independently. Hosted timing models are qualification, not measured live latency or owner acceptance.",
    "This exact candidate repairs domain-scoped HERDMASTER read questions through the existing typed semantic front door, specialist tools and canonical services; no later candidate is admitted. Registration authorizes metadata reconciliation only, not an incident correction, manual expiry extension, predecessor claim rearm, parallel active claim, reused observation window or synthetic owner confirmation; consumed ordinary renewal and manual extension remain consumed. Existing protected mortality continuation and genuine confirmation restrictions are preserved unchanged.",
    "Refresh only the exact claimed retained case identities through current canonical source, cancellation, resolution and completion checks; preserve the full canonical animal identity set for duplicate-tag rejection. Skip unrelated intake discovery during targeted retained refresh while preserving broad collection behavior.",
    "Bound health context to its existing newest 100 owner/chat/source rows and join latest eligible family cards once per distinct mission. Deduplicate the latest all-status source chronology before active projection: terminal tombstones block older preview resurrection without becoming new actionable cases or discarding existing durable cases. Preserve owner isolation and bounded numeric stage durations; no new model work, deadline extension or scheduler deployment.",
    "Prove real loaded-revision retained preparation completes within the unchanged cycle deadline and delivers each exact protected claim once. Timing and hosted equivalence tests alone do not prove delivery; any manual extension of an expired unsent claim requires separately authenticated exact recovery approval and immutable audit.",
    "Allow an exactly bound explicit clarification question to become its conversation protected preview only under fresh delivery ownership before edit journaling. Verify the exact edited provider message identity; all other unbound existing cards remain rejected. Prove the farrowing question, protected preview, genuine synthetic confirmation and one canonical litter journey in disposable PostgreSQL.",
    "Preserve exact retained confirmation buttons through the manager authorized sender, bound to the exact token for that preview generation; never rebind the expired predecessor and keep recipient revalidation and deadline options. Prove the outgoing Confirm/Change/Cancel callback payload and genuine deployed card separately.",
    "Prepare the family protected message before claiming a delivery attempt. Newly prepared retained mortality reports preserve the original report, principal, claim, token, operation and material and may stage without sending until a later natural cycle. Existing prepared reports render from the stored exact preview, then perform one authoritative fresh canonical rebuild under the source lock at admission; stored preview alone is never send authority. Preserve other protected-action expiry and delivery guards.",
    "Prove load/gate/journal/provider ordering, source cancellation and supersession during preparation, actual PostgreSQL concurrent preparers and lock-delay deferral, unchanged claim identity, one bound delivery and silent replay. Claim expiry changes only at first presentation-window admission and never restarts afterward. Fence stale finalizers with a fresh attempt identity. Preserve typed pre-attempt SQL deadline deferral only after explicit successful rollback and context exit; unknown errors or uncertain commit stay closed. Hosted tests are qualification, not owner acceptance.",
    "Preserve uncertainty containment after acquiring an attempt, unbound existing-card rejection and genuine callback authority. Complete original source, claim, case and family chronology must prove eligibility; empty current markers are insufficient. A historical cleared false pre-send marker requires the exact immutable audited correction chain, including consumed renewal and any audited manual extension. Unknown or mixed history, actual provider ambiguity, cancellation, changed material and incomplete origin proof refuse admission. No private operator file or caller-controlled flag grants runtime authority.",
    "Prioritize potentially actionable owner work before known quiet dispatch paths using current canonical case fields; preserve specialist fairness within each class, active lease exclusion, expired delegated cleanup, five-claim capacity, deadlines, current-evidence refresh, protected confirmation and provider ambiguity. Do not delete quiet cases or mark them delivered or completed to free capacity.",
    "Continue canonical collection for quiet cases and allow them spare dispatch capacity; do not claim a bounded quiet waiting time under sustained actionable demand. Prove large-backlog selection, same-case promotion after material owner-relevant evidence, disjoint concurrent claims, genuine later retained-card delivery and the protected canonical outcome separately. No additional model call, cadence change or manual scheduler trigger is authorized.",
    "Keep a protected operation stable across new canonical read timestamps while preserving chronology checks and all material evidence. An existing persisted retained preview may preserve its exact original operation only if fresh whole-preview content and global canonical generation still match; preserve its claim, token, mission and original source binding within each preview generation. Only that claim's single first-attempt presentation window may change preparation expiry. A separately requested linked successor follows the exact continuation conditions below; no predecessor rebind, synthetic confirmation, manual rearm or broader renewal is authorized.",
    "Read existing canonical health sources through one bounded consistent read-only snapshot; reject missing canonical configuration, incomplete reads and deadline exhaustion. Move the existing prepared mortality preview rebuild to final admission instead of adding another snapshot. Prove legacy unsent preview eligibility, same-card replay, genuine callback, current canonical readback and later natural manager cycles; other protected-action renewal rules remain unchanged.",
    "Preserve single-animal mortality meaning as source-bound animal/death/date/disposal facts across the semantic front door, manager-question partial replies, specialist preview and retained recovery; anchor relative dates to original provider time, reject missing sources and identity conflicts, retain uncertainty and invalidate corrected previews. No extra paid inference loop or new farm authority is granted.",
    "Separate retained-report refresh from broad herd collection; verify source and deadline containment, exact current canonical preview, genuine protected delivery/confirmation, atomic recording/readback, silent replay and a later independent manager cycle. Local or hosted simulations do not constitute owner acceptance.",
    "Select retained mortality reports and short replies from existing typed specialist assessment and exact canonical animal identity; contrary assessment never falls back to legacy prose. Preserve latest-state, recipient, cancellation, supersession, protected claim, confirmation and replay guards; prove a genuine scheduled confirmation-card delivery and later canonical outcome separately.",
    "Recognize owner-reported named mortality dates in either order and ordinal forms; resolve omitted year from the original evidence timestamp, preserve explicit year, reject invalid or conflicting dates, and retain chronology validation and genuine confirmation before any mortality write.",
    "Keep question history reads within existing deadlines without repeated full-history scans; preserve owner/chat isolation, partial ordering and cross-day answered-question retirement.",
    "Context failure may deliver one truthful notice through the existing durable provider-bound rail under a separate identity; do not consume later request recovery, retry ambiguous sends, call paid inference or perform farm writes. A notice is not an answer.",
    "Guarded farm OpenAI requests share one durable atomic US$1 SAST-day cap, reserve before provider effects and retain reservation on unknown usage or outcome. No cap is claimed for ChatGPT/Codex credits, historical spend, other providers or unguarded external clients.",
    "Scheduled prioritization uses no paid model; coalesce routine briefing changes, preserve distinct urgent/owner-decision interrupts, and back off the same failed generation. Do not alter the existing scheduler or trigger a manual cycle.",
    "Unpriced audio/image/model requests fail closed with text guidance. Existing protected confirmations and canonical authorization remain unchanged; budget denial grants no alternative execution authority.",
    "Verify the loaded revision, budget metadata without prompt or secret disclosure, owner-visible text behavior, natural scheduled-cycle silence and next trigger. No terminal-generated farm observation or fabricated owner acceptance.",
    f"Release only the protected merge whose application tree equals exact PR{CANDIDATE_PR} head {HEAD} to existing web {WEB_SERVICE}, only after protected merge and required checks.",
    f"Require an independently authenticated attributable owner instruction bound by the coordinator to exact candidate {HEAD}, manifest and this web-only HERDMASTER read-question routing repair scope. Preserve the actual standing instruction and its original context; do not fabricate a hash-specific owner answer, infer authority from source pins, extend a consumed exact manifest or authorize a later candidate. This does not grant production transport authority.",
    f"Rollback is limited to web {WEB_SERVICE} revision {WEB_ROLLBACK}; this does not authorize another service or configuration change.",
    "Permit the deployed retained-mortality runtime to start one finite 30-minute presentation window at the first admitted attempt only after complete durable history and fresh canonical facts, original private principal, source binding, operation, payload and digest match. Atomically record the immutable per-claim window audit with attempt ownership and expiry. Never restart the window after a real attempted, ambiguous or delivered effect or a prior window audit; a preparation-only expiry is not itself an attempt. Preserve original token and chronology, and do not clear archived markers or reset consumed correction or renewal history.",
    "Require the existing current Telegram allowlist and family-principal mortality-confirmation capability before claim creation and canonical preview persistence, at presentation admission and immediately before sending to the original private recipient, including scheduled completed delivery. Recipient revocation prevents delivery without changing the canonical completed farm fact; never redirect to another owner or change family permissions.",
    "Allow canonical retained preview persistence and the existing protected family delivery rail to deliver one bound confirmation card; preserve callback identity, deadlines, provider ambiguity and silent replay. A genuine authorized confirmation remains mandatory before the existing domain executor may record any farm fact; registration, release and presentation-window admission are not farm confirmation. Retained confirmation must bind the original protected card, claim and current source; operation text alone and caller-supplied confirmation flags are not authority.",
    "Commit the existing canonical mortality executor, source completion and protected complete_claim in one borrowed transaction; any applicable domain, welfare, source or claim failure rolls the transaction back. Validate the canonical completed winner and exact claim, card, source, operation and animal binding on replay; duplicate completed callbacks are silent and never re-execute the farm effect.",
    "The existing scheduled worker may recover delivery of an exactly bound canonically completed retained-mortality result, including expired executing or exception-pending delivery leases, only after canonical operation, actor, animal and welfare readback and fresh recipient authorization. Keep effect_unresolved excluded; never automatically execute a pre-domain mortality receipt. Preserve bounded ambiguous same-card edit recovery and silent delivered replay without requesting another owner click.",
    "Ordinary completed mortality source chronology remains immutable on replay. Validate the exact original operation, principal, pig, lifecycle event, source digest and welfare result through current canonical readback; a missing or mismatched completed event must refuse without recreating a farm effect or appending a replacement source. Preserve existing first-completion persistence recovery from a still-preview source and the retained protected-callback-only boundary.",
    "Normalize semantic container representation only through the existing persisted JSON encoding: tuples become their stored lists while identity, source status, facts, false values and zero counts remain exact. Unsupported facts must raise rather than be stringified. Preserve exact staged-source equality, predecessor comparison, terminal-state and cancellation fencing; JSON normalization grants no confirmation or provider authority.",
    "Project mortality completion to the SAME retained manager case only from exact completed source, the current protected claim in the fully validated continuation lineage and non-superseded current canonical operation and welfare readback; delivery alone, expired state, missing facts and silence never close a case.",
    "No scheduler deployment, webhook cutover, n8n workflow disablement, database migration, permission or configuration change, direct or terminal farm write, hardware command, manual cron trigger or manufactured acceptance.",
    "Answer genuine later broad-brief, responsibilities and HERDMASTER-detail questions from current bounded canonical evidence; an unrelated pending farrowing question must not capture a new read enquiry or turn it into a farm-write confirmation.",
    "Resolve an explicit animal by exact canonical Pig ID, tag or name in one bounded read-only repeatable-read snapshot; preserve Active, Sold and Dead lifecycle facts, contain ambiguous or missing identity, scope evidence before limits and report overflow rather than silently answering from an incomplete animal history.",
    "Use bounded delivered context for current English and Afrikaans follow-ups, preserving owner, private chat, provider and subject binding; distinguish an explicit clarification question from a delivered summary and ask targeted Farewell ambiguity without inventing a farm outcome.",
    "Read-only conversation answers must not create farm facts, close cases, create or renew protected claims, weaken current private-principal authorization, borrow another recipient's context or retry ambiguous delivery; existing protected actions retain their separate confirmation rails.",
    "Verify exact loaded web revision and genuine subsequent provider delivery against canonical animal/case identities, read-query scope, language and durable audit; verify replay containment and later natural manager-cycle continuity. Do not substitute a terminal answer, replay historical Telegram messages, make the owner relay terminal actions or request already-pending physical facts again.",
    "Preserve bounded retained-preview limitations: missing litter/disposal facts and unproved live cold-path timing remain explicit. The shared source lock and latest all-status chronology fence retained admission and genuine confirmation against source cancellation and supersession; stale append predecessors are rejected. No global farm-writer fence is claimed: perform fresh final canonical validation and confirmation revalidation. Genuine confirmation, canonical operation/welfare readback and later independent same-case closure/replay remain required. Farrowing remains preview-only; source, tests, release or a sent card are not business completion.",
    "Only a genuine authenticated native callback on the latest verifiably delivered, expired, never-confirmed retained mortality card may request exactly one audited linked successor. Preserve the old claim, card, token, finite window and all renewal/correction/extension history unchanged. The expired click requests review only; the successor requires its own genuine confirmation before any farm effect. Retain the original facts, private principal, source, operation and canonical material without asking for already known facts.",
    "Create the successor claim, immutable predecessor-keyed continuation audit and source append atomically under the existing source lock and mission active-claim invariant. Race, restart and replay recover the same requested successor; an old ancestor card cannot branch or create another generation. Scheduling may resume an already audited request but must never create a new confirmation generation or automatically execute an unconfirmed farm receipt.",
    "Validate complete bounded claim, source, family, case and operational chronology across successive expiries, with exact intermediate source edges and one linear lineage. A manager case may project only an already audited successor from that validated lineage while awaiting reconciliation; retain exact locked case identity, generation and evidence digest and reject arbitrary or root projection references. Same-timestamp event hashes are not causal order; require unique contiguous generation transitions and preserve unknown-history refusal.",
    "Preserve one fresh canonical rebuild, source cancellation/supersession serialization, original recipient reauthorization and unchanged 80-second cycle/30-second provider reserve at successor admission; revalidate material again at genuine confirmation. Reuse the existing one-attempt window audit/CAS and atomic domain/welfare/source/claim completion. Never renew an attempted window, accept an ambiguous predecessor or infer farm confirmation from registration, release or a continuation request.",
    "Prove native delivery, a quiet natural manager cycle, another expiry, a genuine newest-card request, its own genuine confirmation, one canonical operation/readback and closure of the same original manager case. Safe no-effect deadline rollback may resume next cycle; unknown failures remain refused. Quiet owner review must not become a false exception or claim a duplicate delivery. No terminal replay, manufactured observation or manual scheduler trigger proves this acceptance.",
    "Return truthful localized English/Afrikaans callback alerts within Telegram limits. Failed acknowledgements may use one receipt-bound deduplicated informational family notice; preserve provider ambiguity and do not leak internal policy objects. Pending or ambiguous successor delivery must be reported as uncertain, without resending, claiming it was presented or saying the farm event was recorded; already-presented feedback requires exact provider/card binding.",
}


class ReconciliationError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def _require(condition, reason):
    if not condition:
        raise ReconciliationError(reason)


def _fields(value, keys, reason):
    _require(isinstance(value, dict) and set(value) == set(keys), reason)
    return value


def _sha(value, size=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % size, value) is not None


def _require_candidate_pins():
    _require(type(CANDIDATE_PR) is int and CANDIDATE_PR > 0
             and _sha(HEAD, 40) and _sha(TREE, 40) and _sha(APPROVED_RUNTIME_HEAD, 40)
             and HEAD == APPROVED_RUNTIME_HEAD and QUALIFICATION_TEST_PATHS == []
             and isinstance(PATHS, list) and bool(PATHS)
             and all(isinstance(path, str) and path and not path.startswith(("/", "\\"))
                     and ":" not in path and "\\" not in path and ".." not in path.split("/")
                     for path in PATHS)
             and PATHS == sorted(set(PATHS)), "candidate_pins_pending")


def _time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(parsed.tzinfo is not None, "timezone_required")
    return parsed


def _load(raw, expected, label):
    _require(isinstance(raw, bytes) and len(raw) <= 2_000_000 and _sha(expected)
             and digest(raw) == expected, label + "_digest_mismatch")
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ReconciliationError("nonfinite_json")))


def prepare_reconciliation(manifest_bytes, approval_bytes, *, expected_manifest_sha256,
                           expected_approval_sha256, now=None):
    """Validate a pinned proposal; supplied approval bytes are not authentication."""
    _require_candidate_pins()
    now = now or _now()
    m = _fields(_load(manifest_bytes, expected_manifest_sha256, "manifest"), {
        "version", "mission_id", "parent_mission_id", "candidate", "generation", "desktop",
        "expected_child_record", "expected_child_sha256", "expected_parent_record", "expected_parent_sha256",
        "expected_correction", "contract", "implementation", "idempotency_key", "expires_at"}, "manifest_fields")
    a = _fields(_load(approval_bytes, expected_approval_sha256, "approval"), {
        "version", "decision", "approval_id", "manifest_sha256", "owner_principal", "desktop_task_id",
        "source", "evidence_ref", "instruction_text", "issued_at", "expires_at"}, "approval_fields")
    _require(m["version"] == a["version"] == VERSION and m["mission_id"] == MISSION_ID
             and m["parent_mission_id"] == PARENT_ID and a["decision"] == DECISION
             and a["manifest_sha256"] == expected_manifest_sha256, "scope_or_approval_mismatch")
    for key in ("approval_id", "owner_principal", "evidence_ref", "instruction_text"):
        _require(isinstance(a[key], str) and a[key].strip() == a[key] and 1 <= len(a[key]) <= 2000,
                 "approval_identity_missing")
    _require(len(a["owner_principal"]) <= 180 and len(a["evidence_ref"]) <= 500, "approval_identity_too_long")
    issued, expires = _time(a["issued_at"]), _time(a["expires_at"])
    _require(issued <= now < expires and expires == _time(m["expires_at"])
             and 0 < (expires - issued).total_seconds() <= 86400, "approval_not_current")
    source = _fields(a["source"], {"kind", "task_id", "request_text", "answer_text",
        "transcript_sha256", "observed_at", "source_message_id"}, "approval_source_fields")
    _require(source["kind"] == "current_conversation_transcript" and source["task_id"] == TASK_ID
             and source["source_message_id"] is None
             and all(isinstance(source[k], str) and source[k].strip() for k in ("request_text", "answer_text"))
             and digest(canonical({k: source[k] for k in ("task_id", "request_text", "answer_text")})) == source["transcript_sha256"]
             and _time(source["observed_at"]) <= issued, "approval_source_invalid")
    d = _fields(m["desktop"], {"task_id", "principal", "transport"}, "desktop_fields")
    _require(re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", str(d["task_id"]))
             and d["task_id"] == TASK_ID and d["transport"] == "codex_desktop" and d["principal"] == "codex_desktop:" + d["task_id"]
             and a["desktop_task_id"] == d["task_id"], "desktop_identity_invalid")
    for key in ("generation", "idempotency_key"):
        _require(isinstance(m[key], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,159}", m[key]), key + "_invalid")
    c = _fields(m["candidate"], {"pr_number", "branch", "base_sha", "head_sha", "tree_sha", "diff_sha256", "changed_files"}, "candidate_fields")
    _require(type(c["pr_number"]) is int and c["pr_number"] == CANDIDATE_PR and c["branch"] == BRANCH
             and c["base_sha"] == BASE and c["head_sha"] == HEAD and c["tree_sha"] == TREE
             and _sha(c["diff_sha256"]) and c["changed_files"] == PATHS, "candidate_identity_changed")
    implementation = _fields(m["implementation"], {"base_revision", "adapter_sha256", "helper_files"}, "implementation_fields")
    _require(implementation["base_revision"] == BASE and _sha(implementation["adapter_sha256"])
             and set(implementation["helper_files"]) == set(HELPERS)
             and all(_sha(x) for x in implementation["helper_files"].values()), "implementation_pins_invalid")
    for name, mission in (("child", MISSION_ID), ("parent", PARENT_ID)):
        row = m["expected_" + name + "_record"]
        _require(isinstance(row, dict) and row.get("mission_id") == mission and row.get("status") == "in_progress"
                 and isinstance(row.get("metadata_json"), dict)
                 and _sha(m["expected_" + name + "_sha256"])
                 and digest(canonical(row)) == m["expected_" + name + "_sha256"], "expected_" + name + "_record_invalid")
    metadata = m["expected_child_record"]["metadata_json"]
    family, packet, prior_contract, admission = [metadata.get(key) or {} for key in (
        "mission_family", "review_packet", "mission_admission_contract", "mission_admission")]
    _require(all(isinstance(x, dict) for x in (family, packet, prior_contract, admission))
             and family.get("root_mission_id") == PARENT_ID and family.get("generation")
             and family.get("parent_mission_id", PARENT_ID) == PARENT_ID
             and packet.get("pr_number") == PREDECESSOR_PR and admission.get("status") == "valid"
             and packet.get("candidate_revision") == PREDECESSOR_HEAD
             and packet.get("branch_name") == prior_contract.get("branch") == PREDECESSOR_BRANCH
             and prior_contract.get("base_sha") == PREDECESSOR_BASE
             and prior_contract.get("allowed_files") == PREDECESSOR_PATHS
             and admission.get("mission_id") == MISSION_ID
             and admission.get("root_mission_id") == family["root_mission_id"]
             and admission.get("generation") == prior_contract.get("generation") == family["generation"]
             and admission.get("head_sha") == packet.get("candidate_revision")
             and admission.get("base_sha") == prior_contract.get("base_sha")
             and isinstance(admission.get("signed_receipt"), dict)
             and m["generation"] != family["generation"], "predecessor_binding_invalid")
    _require(not metadata.get("execution_lease")
             and not any((metadata.get(key) or {}).get("status") == "valid"
                         for key in ("dispatch_authorization", "hermes_native_execution")), "active_execution_conflict")
    correction = _fields(m["expected_correction"], {"event_id", "metadata", "recorded_by"}, "correction_fields")
    _require(correction["metadata"].get("event_id") == correction["event_id"]
             and correction["metadata"].get("mission_id") == MISSION_ID
             and correction["metadata"].get("event_type") == "owner_correction_recorded"
             and correction["metadata"].get("recorded_by") == correction["recorded_by"], "predecessor_correction_invalid")
    contract = _fields(m["contract"], {"generation", "branch", "base_sha", "allowed_files", "forbidden_files",
        "allowed_effects", "forbidden_effects", "required_tests", "operational_acceptance"}, "contract_fields")
    _require(contract["generation"] == m["generation"] and contract["branch"] == BRANCH
             and contract["base_sha"] == BASE and contract["allowed_files"] == PATHS, "contract_identity_changed")
    for key in ("allowed_files", "forbidden_files", "allowed_effects", "forbidden_effects", "required_tests", "operational_acceptance"):
        _require(isinstance(contract[key], list) and contract[key] and len(contract[key]) <= 100
                 and all(isinstance(v, str) and 0 < len(v) <= 2000 for v in contract[key])
                 and len(set(contract[key])) == len(contract[key]), "contract_lists_invalid")
    _require(not set(contract["allowed_effects"]) & set(contract["forbidden_effects"]), "effect_scope_conflict")
    _require(REMOVED_EFFECTS <= set(prior_contract.get("allowed_effects") or [])
             and REMOVED_FORBIDDEN_EFFECTS <= set(prior_contract.get("forbidden_effects") or [])
             and set(contract["allowed_effects"]) == (set(prior_contract["allowed_effects"]) - REMOVED_EFFECTS) | ADDED_EFFECTS
             and set(contract["forbidden_effects"]) == (set(prior_contract["forbidden_effects"]) - REMOVED_FORBIDDEN_EFFECTS) | ADDED_FORBIDDEN_EFFECTS
             and set(contract["forbidden_files"]) == set(prior_contract.get("forbidden_files") or [])
             and REQUIRED_TESTS | set(prior_contract.get("required_tests") or []) <= set(contract["required_tests"])
             and REQUIRED_ACCEPTANCE == set(contract["operational_acceptance"]), "approved_scope_delta_changed")
    return {"manifest": m, "approval": a, "manifest_sha256": expected_manifest_sha256,
            "approval_sha256": expected_approval_sha256,
            "event_id": "OOM-DESKTOP-REBIND-" + expected_manifest_sha256.upper()}


def verify_source_and_candidate(plan):
    """Read only trusted implementation files and inert candidate Git objects."""
    _require_candidate_pins()
    m = plan["manifest"]
    def git(*args):
        return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=ROOT)
    _require(git("rev-parse", "origin/main").decode().strip() == BASE, "protected_main_changed")
    _require(set(git("diff", "--name-only", BASE, "--").decode().splitlines()) <= MAINTAINER_PATHS,
             "trusted_checkout_changed")
    _require(set(git("ls-files", "--others", "--exclude-standard").decode().splitlines()) <= MAINTAINER_PATHS,
             "untracked_trusted_dependency")
    _require(digest(Path(__file__).read_bytes()) == m["implementation"]["adapter_sha256"], "adapter_source_changed")
    for path, expected in m["implementation"]["helper_files"].items():
        _require(digest((ROOT / path).read_bytes()) == expected, "helper_source_changed")
    _require(git("merge-base", APPROVED_RUNTIME_HEAD, HEAD).decode().strip() == APPROVED_RUNTIME_HEAD,
             "approved_runtime_ancestry_changed")
    qualification_paths = sorted(git("diff", "--name-only", APPROVED_RUNTIME_HEAD, HEAD, "--").decode().splitlines())
    _require(qualification_paths == QUALIFICATION_TEST_PATHS, "qualification_only_test_paths_changed")
    c = m["candidate"]
    _require(git("rev-parse", HEAD + "^{tree}").decode().strip() == c["tree_sha"], "candidate_tree_changed")
    paths = sorted(git("diff", "--name-only", BASE, HEAD, "--").decode().splitlines())
    _require(paths == PATHS, "candidate_paths_changed")
    patch = git("diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index", BASE, HEAD, "--")
    from modules.charlie.mission_admission import canonical_candidate_diff
    _require(canonical_candidate_diff(paths, patch) == c["diff_sha256"], "candidate_diff_changed")


class _BorrowedConnection:
    """Existing helper contexts cannot commit/close the transaction they borrow."""
    def __init__(self, connection):
        self.connection = connection
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def cursor(self):
        return self.connection.cursor()


def _read_record(cursor, mission_id, *, lock=False):
    cursor.execute("select to_jsonb(m) from public.charlie_missions m where mission_id=%s" +
                   (" for update" if lock else ""), (mission_id,))
    row = cursor.fetchone()
    _require(row and isinstance(row[0], dict), "mission_record_unavailable")
    return row[0]


def _event(cursor, event_id):
    cursor.execute("select metadata_json,recorded_by,event_type from public.charlie_mission_events "
                   "where mission_id=%s and event_id=%s", (MISSION_ID, event_id))
    return cursor.fetchone()


def _latest_correction(cursor):
    cursor.execute("select event_id,metadata_json,recorded_by from public.charlie_mission_events "
                   "where mission_id=%s and event_type='owner_correction_recorded' "
                   "order by created_at desc,event_id desc limit 1", (MISSION_ID,))
    return cursor.fetchone()


def _same_scalar_record(left, right):
    return {k: v for k, v in left.items() if k not in {"metadata_json", "updated_at"}} == {
        k: v for k, v in right.items() if k not in {"metadata_json", "updated_at"}}


def _bindings(plan):
    m = plan["manifest"]
    family = dict(m["expected_child_record"]["metadata_json"]["mission_family"])
    family["generation"] = m["generation"]
    c = m["candidate"]
    return {"review_packet": {"pr_number": CANDIDATE_PR, "branch_name": BRANCH, "candidate_revision": HEAD,
                "candidate_tree": c["tree_sha"], "candidate_diff_sha256": c["diff_sha256"], "changed_files": PATHS},
            "mission_admission_contract": m["contract"], "mission_family": family,
            "external_supervisor": m["desktop"],
            "desktop_candidate_reconciliation": {"version": VERSION, "event_id": plan["event_id"],
                "manifest_sha256": plan["manifest_sha256"], "approval_sha256": plan["approval_sha256"]}}


def reconcile_candidate(manifest_bytes, approval_bytes, *, expected_manifest_sha256,
                        expected_approval_sha256, authenticated_owner_principal="",
                        authenticated_desktop_principal="", dry_run=True,
                        database_url=None, connect_factory=None):
    plan = prepare_reconciliation(manifest_bytes, approval_bytes,
        expected_manifest_sha256=expected_manifest_sha256, expected_approval_sha256=expected_approval_sha256)
    if dry_run:
        return {"status": "prepared", "writes": 0, **plan}
    m, a = plan["manifest"], plan["approval"]
    _require(authenticated_owner_principal == a["owner_principal"]
             and authenticated_desktop_principal == m["desktop"]["principal"], "independent_authentication_required")
    _require((isinstance(database_url, str) and database_url.strip()) or callable(connect_factory),
             "explicit_database_connection_required")
    verify_source_and_candidate(plan)
    from modules.charlie import mission_store as store
    from modules.charlie.mission_control import (apply_event_to_projection, validate_mission_control_event,
        build_mission_control_event, canonical_event_equal)
    _require(validate_mission_control_event(m["expected_correction"]["metadata"])[0], "predecessor_correction_invalid")
    proposed = _bindings(plan)
    with store._connect(database_url or "", connect_factory) as connection:
        _require(not getattr(connection, "autocommit", False), "transaction_required")
        with connection.cursor() as cursor:
            cursor.execute("set local lock_timeout='3s'")
            cursor.execute("set local statement_timeout='10s'")
            records = {mid: _read_record(cursor, mid, lock=True) for mid in sorted((MISSION_ID, PARENT_ID))}
            _require(_now() < _time(m["expires_at"]), "approval_expired_under_lock")
            _require(records[PARENT_ID] == m["expected_parent_record"], "parent_state_changed")
            before = records[MISSION_ID]
            recorded = _event(cursor, plan["event_id"])
            if recorded:
                history = recorded[0]
                _require(recorded[1:] == (a["owner_principal"], "workflow_updated")
                         and history.get("manifest_sha256") == plan["manifest_sha256"]
                         and history.get("approval_sha256") == plan["approval_sha256"]
                         and history.get("previous_record") == m["expected_child_record"]
                         and history.get("parent_record") == m["expected_parent_record"]
                         and history.get("manifest") == m and history.get("approval") == a,
                         "replay_history_conflict")
                metadata = before["metadata_json"]
                _require(_same_scalar_record(before, m["expected_child_record"])
                         and all(metadata.get(k) == v for k, v in proposed.items()), "replay_binding_conflict")
                correction = _latest_correction(cursor)
                _require(correction and correction[0] == history["correction"]["event_id"]
                         and correction[1] == history["correction"] and correction[2] == a["owner_principal"],
                         "replay_correction_conflict")
                current = metadata.get("mission_admission") or {}
                _require(current == history["invalidated_admission"] or (
                    all(current.get(k) == v for k, v in {"mission_id": MISSION_ID,
                        "root_mission_id": proposed["mission_family"]["root_mission_id"], "generation": m["generation"],
                        "base_sha": BASE, "head_sha": HEAD}.items()) and isinstance(current.get("signed_receipt"), dict)),
                    "replay_admission_conflict")
                return {"status": "exact_replay", "mission_id": MISSION_ID, "writes": 0}
            _require(before == m["expected_child_record"] and digest(canonical(before)) == m["expected_child_sha256"],
                     "predecessor_state_changed")
            correction = _latest_correction(cursor)
            expected = m["expected_correction"]
            _require(correction == (expected["event_id"], expected["metadata"], expected["recorded_by"]),
                     "predecessor_correction_changed")
            payload = {"event_type": "owner_correction_recorded", "summary": a["instruction_text"],
                "corrects_event_id": expected["event_id"], "idempotency_key": m["idempotency_key"] + ":owner",
                "current_worker": m["desktop"]["principal"],
                "evidence_refs": [a["evidence_ref"], "sha256:" + plan["manifest_sha256"], "sha256:" + plan["approval_sha256"]]}
            result, status = store.invalidate_mission_admission_for_owner_correction(MISSION_ID, m["generation"],
                owner_authentication={"authenticated": True, "principal_type": "owner_admin", "principal_id": a["owner_principal"]},
                correction_payload=payload, connect_factory=lambda _: _BorrowedConnection(connection))
            _require(status < 400 and result.get("status") == "mission_admission_invalidated", "owner_invalidation_failed")
            intermediate = _read_record(cursor, MISSION_ID)
            invalidated = result["admission"]
            _require(_same_scalar_record(before, intermediate)
                     and intermediate["metadata_json"] == {**before["metadata_json"], "mission_admission": invalidated},
                     "invalidation_readback_mismatch")
            correction = _latest_correction(cursor)
            _require(correction and correction[0] == result["correction_event_id"]
                     and correction[2] == a["owner_principal"]
                     and canonical_event_equal(correction[1], build_mission_control_event(
                         MISSION_ID, payload, recorded_by=a["owner_principal"])), "correction_readback_mismatch")
            updated = {**intermediate["metadata_json"], **proposed}
            updated["mission_control_projection"] = apply_event_to_projection(
                {**before, "metadata": updated}, correction[1])
            history = {"version": VERSION, "manifest": m, "approval": a,
                "manifest_sha256": plan["manifest_sha256"], "approval_sha256": plan["approval_sha256"],
                "previous_record": before, "parent_record": records[PARENT_ID], "correction": correction[1],
                "invalidated_admission": invalidated, "bindings": proposed}
            cursor.execute("update public.charlie_missions m set metadata_json=%s::jsonb,updated_at=now() "
                           "where mission_id=%s and to_jsonb(m)=%s::jsonb returning mission_id",
                           (canonical(updated).decode(), MISSION_ID, canonical(intermediate).decode()))
            _require(cursor.fetchone() == (MISSION_ID,), "conditional_binding_lost")
            cursor.execute("insert into public.charlie_mission_events "
                "(event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at) "
                "values(%s,%s,'workflow_updated',%s,%s,%s::jsonb,now())",
                (plan["event_id"], MISSION_ID, f"Owner-approved exact Desktop PR{CANDIDATE_PR} candidate reconciliation.",
                 a["owner_principal"], canonical(history).decode()))
            after = _read_record(cursor, MISSION_ID)
            _require(_same_scalar_record(before, after) and after["metadata_json"] == updated
                     and _read_record(cursor, PARENT_ID) == records[PARENT_ID]
                     and _event(cursor, plan["event_id"]) == (history, a["owner_principal"], "workflow_updated")
                     and _latest_correction(cursor) == correction, "final_readback_mismatch")
    return {"status": "candidate_reconciled", "mission_id": MISSION_ID, "pr_number": CANDIDATE_PR,
            "head_sha": HEAD, "writes": 5, "admission_issued": False, "release_performed": False}


def main():
    parser = argparse.ArgumentParser(description="Prepare only; never applies a canonical mutation.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--approval", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--approval-sha256", required=True)
    args = parser.parse_args()
    plan = prepare_reconciliation(Path(args.manifest).read_bytes(), Path(args.approval).read_bytes(),
        expected_manifest_sha256=args.manifest_sha256, expected_approval_sha256=args.approval_sha256)
    verify_source_and_candidate(plan)
    print(json.dumps({"status": "prepared", "writes": 0, "mission_id": MISSION_ID,
                      "manifest_sha256": plan["manifest_sha256"]}))


if __name__ == "__main__":
    main()
