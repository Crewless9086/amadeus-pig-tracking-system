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
BASE = '4d21d234a75ceba8956146eb2154c72492698376'
# Exact source pins are not approval. Applying the reconciliation still requires
# independent authenticated owner approval of the exact manifest and scope.
# Exact PR1386 source pins are bound; release authority remains independently bound.
CANDIDATE_PR = 1386
HEAD = '9f4d4470f23643153591cfee5ea9528b0b930aa4'
TREE = '7b838ed9d27c1f8af42b4d213cdd1fede98665a9'
# Complete candidate identity alone grants no release or farm-write authority.
# Synthetic qualification pins live only in tests; no later runtime delta is allowed.
APPROVED_RUNTIME_HEAD = '9f4d4470f23643153591cfee5ea9528b0b930aa4'
QUALIFICATION_TEST_PATHS = []
BRANCH = 'codex/manager-mortality-reconciliation-20261006'
PREDECESSOR_PR = 1385
PREDECESSOR_BASE = '103b431eaea709e6243e01dbe43f9bb65ed0e1ed'
PREDECESSOR_HEAD = 'a29ee4ecb57935d279fa843b917b5935f078c733'
PREDECESSOR_BRANCH = 'codex/manager-followthrough-reliability-20261006'
PATHS = ['.github/workflows/oom-sakkie-audit-rails.yml', 'docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md', 'docs/09-vault-brain/CHANGELOG.md', 'modules/oom_sakkie/general_manager_worker.py', 'modules/oom_sakkie/herdmaster_case_disposition.py', 'modules/oom_sakkie/manager_case_sources.py', 'modules/oom_sakkie/owner_attention_projection.py', 'tests/test_oom_sakkie_mortality_reconciliation.py', 'tests/test_oom_sakkie_mortality_reconciliation_postgres.py', 'tests/test_oom_sakkie_owner_attention_projection.py']
PREDECESSOR_PATHS = ['.github/workflows/oom-sakkie-audit-rails.yml', 'docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md', 'docs/09-vault-brain/CHANGELOG.md', 'modules/oom_sakkie/general_manager_worker.py', 'modules/oom_sakkie/manager_case_sources.py', 'modules/oom_sakkie/rootline_notification_disposition.py', 'tests/test_oom_sakkie_manager_case_sources.py', 'tests/test_oom_sakkie_rootline_notification_followthrough.py', 'tests/test_oom_sakkie_rootline_notification_followthrough_postgres.py']

WEB_SERVICE = "srv-d6sijjkhg0os73f7regg"
WEB_ROLLBACK = '4d21d234a75ceba8956146eb2154c72492698376'
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
REMOVED_EFFECTS = {'application_revision_rollback:web:103b431eaea709e6243e01dbe43f9bb65ed0e1ed'}
ADDED_EFFECTS = {'herdmaster_legacy_mortality_technical_pending_reconciliation', 'application_revision_rollback:web:4d21d234a75ceba8956146eb2154c72492698376'}
REMOVED_FORBIDDEN_EFFECTS = set()
ADDED_FORBIDDEN_EFFECTS = set()
REQUIRED_TESTS = {"Closed Render migration rail with disposable Postgres",
    "Playwright real-browser behavior gate", "Unit tests with disposable Postgres audit rails",
    "charlie-core", "mission-admission"}
REQUIRED_ACCEPTANCE = {
    'Reconcile retained HERDMASTER mortality and mortality-cluster advisories with exact legacy daily-evidence identity via the shared owning resolver. Current work and collector failures take precedence. A bounded read may return an internal typed nonmaterial receipt for unproved original assessment lineage; absence, unknown identity or incomplete evidence never proves welfare completion. Require the full durable row, current private owner, original refs, generation and material, live owned lease and concurrent-current-work fences after reads at admission and persistence. Preserve case, generation, digest, refs, summary and delivery history in waiting_reassessment with herdmaster_owning_reconciliation_pending and the five-minute cadence. Count reconciliation_pending only after its case event commits. The technical_dependency event must bind herdmaster.mortality_technical_dependency.v1, mortality_source_lineage_unproven, stable dependency_id, exact case/generation/digest/ref hash and owner binding, completion_proven:false and core_acknowledged:false. This receipt is not CORE intake, dispatch, execution or repair completion. Failed reads remain sanitized exceptions; refused persistence reports manager_reconciliation_persistence_unproven and counts an exception. Preserve truthful owner attention, ROOTLINE delivery proof and purpose siblings. Fresh current evidence re-enters owning reconciliation; replay and unchanged pending work cannot send, close welfare or manufacture lineage. Add no CORE consumer/activation, farm/provider write, message, replay trigger, schema, schedule, model, permission or security change. Require tests/test_oom_sakkie_mortality_reconciliation.py and tests/test_oom_sakkie_mortality_reconciliation_postgres.py in Prove legacy mortality technical reconciliation without farm completion, zero skips, covering malformed/crossed/stale refs, wrong owner, expired/foreign lease, post-read drift, event-persistence failure and concurrent current evidence.',
    'Close only the existing ROOTLINE current-plan delivery advisory from complete positive canonical observation and provider-confirmed delivery proof for the same current private recipient, SAST operating date and canonical plan material. Require lowercase 64-hex SHA-256 material, exact event/identity/provider-message refs, latest relevant delivery state and current recipient policy; missing, malformed, crossed, stale, uncertain or fingerprint-only evidence stays unresolved. Only this complete same-material notification family may accept fresh observation/event/result/generation metadata without resetting material digest, case generation or due time; preserve full latest audit refs. Incomplete evidence retains conservative material handling. Under the existing lock revalidate the retained case identity, generation, digest and refs, lease/delegation and concurrent-current-work fences. Complete once, retain original delivery history and refuse newer ambiguous/failed/pending state; replay is silent and changed material reopens normally. Preserve exact final localized retry-text binding and existing zero-send authority. This proves notification delivery only, never physical irrigation, welfare or hardware completion. This notification clause grants no mortality or welfare completion authority. Add no farm write, send, replay, retry, model call, schedule, configuration, schema or permission authority. Require tests/test_oom_sakkie_rootline_notification_followthrough.py and tests/test_oom_sakkie_rootline_notification_followthrough_postgres.py in Prove ROOTLINE notification follow-through without provider effects, zero skips, including malformed SHA/ref, recipient, lease and concurrent-current-work refusal. Require genuine loaded-revision natural same-case completion, no duplicate notice, preserved sibling/physical objectives and later quiet continuity before claiming an owner outcome.',
    'After releasing an incomplete initial reconciliation snapshot, take one fresh whole-cohort lock snapshot in canonical case-ID order only when all absent candidates are unique non-BEACON terminal findings. Preserve the original ordered fallback for insertion-capable gaps, every duplicate key, BEACON absences and a second-snapshot deletion that makes insertion possible; never acquire a lower follow-up lock from a retained terminal absence.',
    'Allow an exactly bound explicit clarification question to become its conversation protected preview only under fresh delivery ownership before edit journaling. Verify the exact edited provider message identity; all other unbound existing cards remain rejected. Prove the farrowing question, protected preview, genuine synthetic confirmation and one canonical litter journey in disposable PostgreSQL.',
    'Allow canonical retained preview persistence and the existing protected family delivery rail to deliver one bound confirmation card; preserve callback identity, deadlines, provider ambiguity and silent replay. A genuine authorized confirmation remains mandatory before the existing domain executor may record any farm fact; registration, release and presentation-window admission are not farm confirmation. Retained confirmation must bind the original protected card, claim and current source; operation text alone and caller-supplied confirmation flags are not authority.\n\nTelegram purpose adapter: one authenticated private owner may review evidence-grounded grouped suggestions, read reasons, change exact selections/purposes, inspect every exact old-to-new effect page and confirm the current bound preview. Use canonical names/tags, concise EN/AF text and human-readable purposes. Atomic exact-parent navigation edits the verified card and cannot retire a newer card. Revalidate current identities, weight/readiness evidence, commercial holds and case generation/membership inside the existing serializable batch writer; preserve atomic per-pig audit and idempotency. No inferred purpose, automatic approval, plain-yes farm write or engineering approval as farm confirmation. Lost commit/claim/result delivery recovers the same batch and truthful acknowledgement without another farm effect. A completed-card button opens a fresh read-only remaining-groups overview; it never reuses confirmation authority.',
    'Answer genuine later broad-brief, responsibilities and HERDMASTER-detail questions from current bounded canonical evidence; an unrelated pending farrowing question must not capture a new read enquiry or turn it into a farm-write confirmation.',
    'At orphan replacement require complete bounded source, claim, case, farm and provider history and the exact current private recipient. Cancelled, uncertain, attempted, confirmed, completed, competing or incomplete histories refuse replacement; stale generation, source supersession, materially changed identity or competing active claim also refuse. Replay, restart and concurrent preparers recover only the same immutable audited successor with zero new sends or generations. Within this inherited orphan-replacement flow, keep the US$1/day model cap, no additional model work, no manual farm write, and no hardware, configuration, schema or scheduler deployment.',
    'Before creating a protected preview claim, bind each animal to its exact current canonical identity and render its canonical name and tag where available. Distinguish unmarked piglets and different per-animal effects without borrowing a litter or sibling identity. Missing, ambiguous, duplicated or crossed source-to-animal identity refuses preparation before claim creation; display formatting cannot repair or authorize an invalid identity.',
    'Bound health context to its existing newest 100 owner/chat/source rows and join latest eligible family cards once per distinct mission. Deduplicate the latest all-status source chronology before active projection: terminal tombstones block older preview resurrection without becoming new actionable cases or discarding existing durable cases. Preserve owner isolation and bounded numeric stage durations; no new model work, deadline extension or scheduler deployment.',
    'Collect and refresh the exact retained farrowing family independently of broad herd collection through existing bounded canonical readers. A blocked broad collector must not erase independently complete review evidence. Preserve the total read budget, cycle deadline, send reserve, current-candidate precedence, source locks and sibling failure containment; missing or uncertain evidence remains an explicit gap.',
    'Commit the existing canonical mortality executor, source completion and protected complete_claim in one borrowed transaction; any applicable domain, welfare, source or claim failure rolls the transaction back. Validate the canonical completed winner and exact claim, card, source, operation and animal binding on replay; duplicate completed callbacks are silent and never re-execute the farm effect.',
    "Complete only the same existing purpose-review case from positive current canonical correction evidence, never collector omission or disappearance. Require complete immutable full-membership proof with original per-pig obligation epochs retained across partial successors. Prospective groups of 12 or more are supported only with full proof. Legacy uncapped 1-11 groups may adopt current-generation proof only; capped or unproven legacy groups remain unresolved. Every retained member must retain exact canonical litter, tag, Active and on-farm identity and have a latest pig.purpose_corrected event attributable to an executed owner-approved batch and decision with matching preview and event hashes after each original member's retained obligation epoch. Missing, partial, stale or contradictory obligations and unresolved eligible extras refuse closure. Only conclusively departed extra rows outside immutable obligations leave the unknown-purpose veto; retained members and ambiguous/conflicting lifecycle evidence never do. Use one read-only snapshot with four set-based reads, a six-second total deadline and bounds of 64 cases and 10000 source rows; timeout, failure or overflow refuses without partial success. Emit only the existing herdmaster_disposition terminal candidate with exact current generation and material digest; preserve lease, delegation and current-work-wins fences. Complete once including previously delivered cases; replay is silent and new legitimate unresolved material retains normal reopening/history. Owner-attention omission must remain unresolved unless positive completion is proved. This completion capability grants no farm write, owner deferral, new notice or retry, model, schema or schedule authority. Registration remains five release-metadata writes. Require genuine attributable approved correction, exact loaded-revision same-case completion and later natural quiet follow-up before claiming an owner outcome.",
    'Compose the concise localized farm brief from typed canonical brief facts, never from parsing opaque specialist prose. Keep full detailed rows and original questions available beneath the brief. Preserve exact canonical identity, quantities, dates, coverage counts, provenance and uncertainty; a missing fact must not become a clean status or an invented instruction. Limit family-facing detail without changing specialist records or hiding a distinct urgent owner decision.',
    'Context failure may deliver one truthful notice through the existing durable provider-bound rail under a separate identity; do not consume later request recovery, retry ambiguous sends, call paid inference or perform farm writes. A notice is not an answer.',
    'Continue a historical farrowing review only from a genuine fresh authenticated statement by the currently authorized owner in the bound private chat. Require the actual delivered review and an exact reply-to binding or unique current delivered context, with current source, case generation, canonical animal identity and claim history revalidated under the existing admission locks. Stale, revoked, cross-recipient, ambiguous, cancelled, superseded or changed context refuses preparation.',
    'Continue canonical collection for quiet cases and allow them spare dispatch capacity; do not claim a bounded quiet waiting time under sustained actionable demand. Prove large-backlog selection, same-case promotion after material owner-relevant evidence, disjoint concurrent claims, genuine later retained-card delivery and the protected canonical outcome separately. No additional model call, cadence change or manual scheduler trigger is authorized.',
    'Create the successor claim, immutable predecessor-keyed continuation audit and source append atomically under the existing source lock and mission active-claim invariant. Race, restart and replay recover the same requested successor; an old ancestor card cannot branch or create another generation. Scheduling may resume an already audited request but must never create a new confirmation generation except the single audited never-attempted legacy orphan replacement defined here; it must never automatically execute an unconfirmed farm receipt.',
    'Deliver the informational retained farrowing review only to the currently configured owner after existing private-principal, owner-role and allowlist authorization. Never select the first allowlisted recipient or infer ownership from the original claimant. Revalidate the current owner, exact source, claim, case generation and current canonical evidence immediately before existing delivery or edit admission; changed authority or evidence refuses provider action without a fallback recipient.',
    'Display the single-pig purpose preview from the canonical herdmaster_purpose_correction_v2 decisions/effects contract. Escape exact animal, purposes, reason/note; Pig ID is secondary. Require one complete matching decision/effect, current tag and purpose, Active/on-farm identity, matching digest/confirmation binding/actor, finite weights and nonfuture binding no older than 1800 seconds. Missing/legacy/malformed/multiple/mismatched/expired results leave Apply disabled; browser shape checks do not authenticate the server HMAC. Selection/purpose/note/reload/return-context changes invalidate intent, including change-away-and-back and late success/failure. Recheck intent and expiry before explicit owner confirmation; freeze that exact request before awaits with one invocation-owned submit lock through create/approve/execute; stale responses cannot unlock or duplicate it. Preserve the existing authenticated batch writer, canonical reread, idempotency and protected approval. Cancellation creates no batch. Report a save despite failed readback without retrying the write. Preserve adjacent auction evidence panels and safe order return. Require tests/pig_allocation_purpose_preview.spec.js via tests/purpose_preview_playwright.config.js in Run canonical single-pig purpose preview browser contract: zero skips, desktop/mobile visual evidence for the exact approved source. Retain all prior application/browser/four helper gates and outcome obligations. Synthetic previews/intercepted writes prove no farm execution or outcome; no decision is required or invented for engineering release.',
    'Exclude only order lines explicitly normalized to cancelled from current weighing identity comparison. Preserve the original line, pig ID, historical tag snapshot, parent order and source digest; retired history must not create a current identity task, physical departure or weighing instruction. Active, missing, unknown, conflicting or unsupported line status retains every current identity and lifecycle check; a terminal parent order alone does not retire its lines. Parent-state validation, separate sales, active allocations and outlet conflicts remain unchanged. Preserve the complete bounded read-only snapshot, source/case generation, current recipient and no-farm-write boundaries.',
    'Exercise an unexpired protected confirmation through real preview, claim and family delivery gates with explicit synthetic collection, refresh and preparation costs; the slower control must remain unattempted. Keep the 80-second cycle deadline and 30-second send reserve unchanged. Collector timeout before the global cutoff must contain only that owner while ready specialists progress; late results cannot send and a later cycle must reclaim independently. Hosted timing models are qualification, not measured live latency or owner acceptance.',
    'For a delivered expired-card continuation, only a genuine authenticated native callback on the latest verifiably delivered, expired, never-confirmed retained mortality card may request exactly one audited linked successor. The separate never-attempted orphan exception defined here cannot apply to a delivered card. Preserve the old claim, card, token, finite window and all renewal/correction/extension history unchanged. The expired click requests review only; the successor requires its own genuine confirmation before any farm effect. Retain the original facts, private principal, source, operation and canonical material without asking for already known facts.',
    'For the existing proven-zero-send ROOTLINE daily retry, bind strict retry authority to the exact final localized presentation text used by the existing family delivery path. Preserve the stored packet, material identity and current recipient. Changed text, missing zero-send proof, uncertain or delivered outcomes refuse retry; no manual retry, message or broader attempt authority is permitted. Do not alter protected confirmation lifecycles, claims, callbacks, source chronology, provider uncertainty or farm permissions.',
    'Guarded farm OpenAI requests share one durable atomic US$1 SAST-day cap, reserve before provider effects and retain reservation on unknown usage or outcome. No cap is claimed for ChatGPT/Codex credits, historical spend, other providers or unguarded external clients.',
    "Keep a protected operation stable across new canonical read timestamps while preserving chronology checks and all material evidence. An existing persisted retained preview may preserve its exact original operation only if fresh whole-preview content and global canonical generation still match; preserve its claim, token, mission and original source binding within each preview generation. Only that claim's single first-attempt presentation window may change preparation expiry. A delivered expired-card linked successor follows the exact native-callback continuation conditions below; the separately audited never-attempted orphan replacement is the sole preparation exception; no predecessor rebind, synthetic confirmation, manual rearm or broader renewal is authorized.",
    'Keep both owner-attention renderers pure over their supplied packets. Do not alter canonical evidence, material digests, stored answers, result hashes, task order or producer policy to improve wording. Preserve existing same-inbound replay, private-principal and provider bindings; presentation grants no farm instruction, protected claim, confirmation, model call, new notification, manual replay or retry. Previously delivered weighing and breeding answers remain historical evidence and must not be recomposed.',
    'Keep canonical reads bounded and read-only. Missing, malformed or unavailable evidence must remain an explicit gap, never a zero count or no-work assertion. Identify relevant animals, litters and pens from current evidence, disclose bounded-list remainders and distinguish recorded farm status from a verified physical count. Pen capacity is a records comparison; do not diagnose physical overcrowding or calculate maternity headcount excess from undefined capacity units.',
    'Keep presentation metadata outside material digests, notification keys, case identities and protected authority. Same-inbound replay must preserve its already stored answer and result digest without recomposition. Existing same-concern suppression remains silent; display changes alone must not create a notification, claim, paid model call or farm effect.',
    'Keep question history reads within existing deadlines without repeated full-history scans; preserve owner/chat isolation, partial ordering and cross-day answered-question retirement.',
    'Keep the preserved breeding-subject read and weighing-reconciliation flows read-only for farm state and within existing configured-owner and specialist authority. Those read flows must not create a claim, confirmation generation, role, farm permission, schema, scheduler deployment, manual message, replay, retry, model spend or hardware action. Preserve the parent mission, original source/farm/provider histories, US$1/day model cap and all ten other services. Require fresh genuine loaded-revision breeding follow-up and weighing delivery, exact canonical readback and later natural manager continuity before claiming an owner outcome.',
    'Label historical farrowing counts as unconfirmed original report information and state that no birth record has been created. Use plain localized language requesting genuine fresh owner input. The informational review contains no approval buttons, protected callback token or executable farm authority; it does not grant a role, create a new protected claim or manufacture an owner response. Any later birth record requires the existing fresh protected preview and genuine confirmation.',
    "Mark an overdue recorded exposure removal plan only against the supplied canonical packet's aware farm-date cutoff, never the wall clock. Missing, naive, invalid, future-start or conflicting dates remain explicit uncertainty. An open exposure record does not prove current physical presence, removal, mating or pregnancy and does not authorize physical work.\n\nPreserve the existing displayed task order and question priority. Ask a named current-status and actual-removal-date question only for the supported exposure-only worklist; require the animal name and observation date in a genuine reply. Do not replace a higher-priority condition question, infer a farm fact from a planned date or create new continuation authority.",
    'Name supplied breeding evidence gaps with bounded source wording and an explicit omitted count while retaining the full detailed worklist. Preserve canonical identities, facts, material digests, stored replay and protected authority. Prove the exact breeding presentation test in the existing conversational hosted stage with zero skips; earlier PR1372 replies remain historical evidence and do not prove this overdue-follow-up presentation outcome.',
    'No scheduler deployment, webhook cutover, n8n workflow publication, change or disablement, database migration, permission or configuration change, direct or terminal farm write, hardware command, manual cron trigger or manufactured acceptance.\n\nThe predecessor claim-kind migration is consumed history and must not be replayed, extended or reversed. Preserve its exact observed 18-kind or 19-kind target, including the presence or absence of herdmaster_record_litter_weaning; never implicitly enable weaning. Existing privileges, records, migration logs and other schema remain preserved. Register exactly five release-metadata writes through verified encrypted transport, complete protected merge and deploy only the existing web service. Roll back application to 4d21d234a75ceba8956146eb2154c72492698376 if needed, retaining additive schema and legitimate new claim/business history. No unencrypted transport, down-migration, unrelated migration, manual owner confirmation, scheduler/configuration change, hardware operation or release-operator farm write. Bind exact final candidate/tree/diff/helper/manifest and fresh mission preimages before release. Helper code is qualification-only and is never merged or deployed. Prior PR1385 registration and web deployment are consumed history; preserve the existing provider state without another workflow update or rollback.',
    'Normalize semantic container representation only through the existing persisted JSON encoding: tuples become their stored lists while identity, source status, facts, false values and zero counts remain exact. Unsupported facts must raise rather than be stringified. Preserve exact staged-source equality, predecessor comparison, terminal-state and cancellation fencing; JSON normalization grants no confirmation or provider authority.',
    'Ordinary completed mortality source chronology remains immutable on replay. Validate the exact original operation, principal, pig, lifecycle event, source digest and welfare result through current canonical readback; a missing or mismatched completed event must refuse without recreating a farm effect or appending a replacement source. Preserve existing first-completion persistence recovery from a still-preview source and the retained protected-callback-only boundary.',
    'Permit one audited replacement only when complete bounded history proves a legacy claim is expired, active and claim_created, with every delivery attempt, card, provider result and confirmation marker null and no earlier presentation, continuation, replacement, correction or renewal audit. The original private principal, original report, canonical pig and found_dead meaning must match while the complete current canonical preview material must differ. Changed material is not equivalent authority: never silently renew, reuse, rearm or confirm the stale claim.',
    'Permit the deployed retained-mortality runtime to start one finite 30-minute presentation window at the first admitted attempt only after complete durable history and fresh canonical facts, original private principal, source binding, operation, payload and digest match. Atomically record the immutable per-claim window audit with attempt ownership and expiry. Never restart the window after a real attempted, ambiguous or delivered effect or a prior window audit; a preparation-only expiry is not itself an attempt. Preserve original token and chronology, and do not clear archived markers or reset consumed correction or renewal history.',
    'Positive current canonical supersession evidence may silently suppress an obsolete farrowing review through a nonterminal disposition only. Preserve the same original case and every source, claim, family, farm and provider history; do not close the case or mark the birth complete. Missing, conflicting or unavailable supersession evidence stays unresolved. Prove exact configured-owner routing, pre-send revalidation, blocked broad collection, concurrent normal cycles, silent replay and changed-authority refusal in disposable PostgreSQL, then require genuine loaded-revision delivery and later natural-cycle continuity separately.',
    'Prepare condition_observation only from a genuine current authenticated owner report naming one exact current canonical animal and its finite nonboolean body-condition score. Preserve explicit observation date and date-only precision or a supplied aware instant; reject missing, future, invalid or conflicting observation dates before claim creation. Date-only normalization is a disclosed storage convention, not an invented physical observation time. Prior read context, a score alone, a pronoun or an old condition question cannot supply missing animal identity, observation facts or confirmation authority.\n\nRender the exact animal, score, observation date and precision in the existing protected preview. Require the currently authorized private owner and the exact bound current claim, preview digest, card and genuine confirmation before one canonical append. Cancelled, expired, revoked, cross-recipient, changed-identity or changed-preview claims refuse. Preserve original provider evidence, idempotency and atomic transaction boundaries; successful replay records no second observation.',
    'Prepare the family protected message before claiming a delivery attempt. Newly prepared retained mortality reports preserve the original report, principal, claim, token, operation and material and may stage without sending until a later natural cycle. Existing prepared reports render from the stored exact preview, then perform one authoritative fresh canonical rebuild under the source lock at admission; stored preview alone is never send authority. Preserve other protected-action expiry and delivery guards.',
    'Present weighing attention from the existing typed canonical packet with the current actionable answer first. Name individual weighing work only when complete current reconciliation is checked and the specialist already proves that exact animal due; conflicting evidence or unavailable reconciliation cannot become a weighing instruction. Keep the intentional prior reporting window and its coverage separate from current eligibility and due work. Label full-register comparisons as full-register records, preserve bounded exclusions and unresolved counts, and do not imply that those totals are the on-farm herd count.',
    'Presentation-only changes must not create or renew a protected claim, consume a confirmation, change material evidence or trigger another generation or provider attempt. Preserve original operation, claim, callback, expiry, recipient and provider bindings, durable delivery ownership, source material comparison, replay containment and uncertain-delivery refusal.',
    'Preserve bounded retained-preview limitations: missing litter/disposal facts and unproved live cold-path timing remain explicit. The shared source lock and latest all-status chronology fence retained admission and genuine confirmation against source cancellation and supersession; stale append predecessors are rejected. No global farm-writer fence is claimed: perform fresh final canonical validation and confirmation revalidation. Genuine confirmation, canonical operation/welfare readback and later independent same-case closure/replay remain required. Farrowing remains pending genuine current owner input and protected confirmation; historical previews, informational review, source, tests, release or a sent card are not business completion.',
    'Preserve exact retained confirmation buttons through the manager authorized sender, bound to the exact token for that preview generation; never rebind the expired predecessor and keep recipient revalidation and deadline options. Prove the outgoing Confirm/Change/Cancel callback payload and genuine deployed card separately.',
    'Preserve one fresh canonical rebuild, source cancellation/supersession serialization, original recipient reauthorization and unchanged 80-second cycle/30-second provider reserve at successor admission; revalidate material again at genuine confirmation. Reuse the existing one-attempt window audit/CAS and atomic domain/welfare/source/claim completion. Never renew an attempted window, accept an ambiguous predecessor or infer farm confirmation from registration, release or a continuation request.',
    'Preserve single-animal mortality meaning as source-bound animal/death/date/disposal facts across the semantic front door, manager-question partial replies, specialist preview and retained recovery; anchor relative dates to original provider time, reject missing sources and identity conflicts, retain uncertainty and invalidate corrected previews. No extra paid inference loop or new farm authority is granted.',
    'Preserve the existing weighing eligibility and schedule rules, sale/order and lifecycle reconciliation, pregnancy evidence and litter identity. Planned weaning never becomes completed weaning. A recorded completed litter must supersede an earlier near-farrowing observation for the same cycle; unknown or inconsistent later chronology remains explicit. Current nursing classification requires confirmed farrowing evidence, and proposed placements must not treat a planned weaning date as completed weaning. Qualify the exact breeding chronology and operating-loop tests alongside the canonical read journey tests. Scope genuine HERDMASTER owner questions and supported physical tasks before presentation limits; unrelated specialist failures and agent-owned technical work must not become owner obligations.',
    'Preserve uncertainty containment after acquiring an attempt, unbound existing-card rejection and genuine callback authority. Complete original source, claim, case and family chronology must prove eligibility; empty current markers are insufficient. A historical cleared false pre-send marker requires the exact immutable audited correction chain, including consumed renewal and any audited manual extension. Unknown or mixed history, actual provider ambiguity, cancellation, changed material and incomplete origin proof refuse existing-claim presentation admission. Changed material may enter only the separately audited orphan replacement, which creates a fresh independently confirmed preview. No private operator file or caller-controlled flag grants runtime authority.',
    'Prioritize potentially actionable owner work before known quiet dispatch paths using current canonical case fields; preserve specialist fairness within each class, active lease exclusion, expired delegated cleanup, five-claim capacity, deadlines, current-evidence refresh, protected confirmation and provider ambiguity. Do not delete quiet cases or mark them delivered or completed to free capacity.',
    'Project mortality completion to the SAME retained manager case only from exact completed source, the current protected claim in the fully validated continuation lineage and non-superseded current canonical operation and welfare readback; delivery alone, expired state, missing facts and silence never close a case.',
    'Prove exact stable-identity selection, advisory generation fencing, original-report reassessment, differing-material orphan replacement, first-preparation silence, concurrent rollback and zero-write replay in disposable PostgreSQL. Separately require the reviewed loaded revision, genuine normal-cycle card delivery, the successor protected callback, current-recipient and lineage validation, one canonical completion/readback and a later unattended same-case cycle. Local qualification and technical release never establish this owner outcome.',
    'Prove load/gate/journal/provider ordering, source cancellation and supersession during preparation, actual PostgreSQL concurrent preparers and lock-delay deferral, unchanged claim identity, one bound delivery and silent replay. Claim expiry changes only at first presentation-window admission and never restarts afterward. Fence stale finalizers with a fresh attempt identity. Preserve typed pre-attempt SQL deadline deferral only after explicit successful rollback and context exit; unknown errors or uncertain commit stay closed. Hosted tests are qualification, not owner acceptance.',
    'Prove native delivery, a quiet natural manager cycle, another expiry, a genuine newest-card request, its own genuine confirmation, one canonical operation/readback and closure of the same original manager case. Safe no-effect deadline rollback may resume next cycle; unknown failures remain refused. Quiet owner review must not become a false exception or claim a duplicate delivery. No terminal replay, manufactured observation or manual scheduler trigger proves this acceptance.',
    'Prove real loaded-revision retained preparation completes within the unchanged cycle deadline and delivers each exact protected claim once. Timing and hosted equivalence tests alone do not prove delivery; any manual extension of an expired unsent claim requires separately authenticated exact recovery approval and immutable audit.',
    'Prove tests/test_herdmaster_weighing_reconciliation.py in Run canonical HERDMASTER morning recipient-language gates and tests/test_herdmaster_weighing_reconciliation_postgres.py in Prove weighing reconciliation with isolated PostgreSQL. Prove exact breeding read context through Run canonical conversational follow-up gates, retaining all prior stages and tests with zero skips. Require all four full helper suites on the exact final helper revision before production binding; local focused checks and prior run receipts do not substitute for final hosted proof. Also require tests/test_herdmaster_purpose_work.py and tests/test_oom_sakkie_owner_attention_projection.py in the same morning stage; tests/test_herdmaster_purpose_weighing_postgres.py in the same weighing PostgreSQL stage; tests/test_oom_sakkie_manager_case_sources.py and tests/test_oom_sakkie_herdmaster_case_disposition_postgres.py in Run retained report identity and age recovery gates; and tests/test_oom_sakkie_farm_brief_concise.py in Prove family presentation and historical-review continuation. Require all four full helper suites on the exact final helper head with zero skips. Also require tests/test_oom_sakkie_purpose_decision.py in Prove weighing reconciliation with isolated PostgreSQL, preserving all existing selectors and zero-skip qualification. Prove current typed admission, unchanged case/material, current private owner and lease, durable exact-text retry fencing, one proven-zero-send recovery, ambiguous and delivered refusal, and silent later replay. Prove tests/test_oom_sakkie_purpose_refresh.py: one canonical purpose snapshot per valid claimed group; own refresh batch and shared 80s/30s cutoff. Reject late, failed, missing, held or changed evidence without cached fallback. Prove default dispatcher/store multi-cycle catch-up, mixed-collector isolation, fresh urgent priority and duplicate silence; no five-send guarantee or new authority.',
    'Prove tests/test_oom_sakkie_farm_brief_concise.py and tests/test_oom_sakkie_rootline_daily_presentation.py in the existing named hosted family presentation stage, alongside all previously required files and broader stages with zero skips. Prove the unchanged four full helper suites on the exact final helper revision. Separately require a fresh genuine configured-owner farm brief on the loaded revision, matching typed and provider receipts and later natural-cycle continuity. PR1369 acceptance is historical evidence; it does not establish this successor owner-visible outcome.',
    'Prove tests/test_oom_sakkie_herdmaster_breeding_exposure_runtime.py and tests/test_herdmaster_breeding_exposure_recovery.py in Run canonical conversational follow-up gates, tests/test_oom_sakkie_semantic_front_door.py in Run retained farrowing conversation gates, and tests/test_herdmaster_breeding_exposure_postgres.py with isolated PostgreSQL in Run HERDMASTER grouped breeding exposure transaction gates; retain all broader stages with zero skips. Require all four full helper suites on the exact final helper head before production binding. Separately require a genuine loaded-revision named dated observation, its own owner confirmation, exact canonical readback, silent replay and later natural reassessment before claiming this protected owner outcome; PR1373 read replies remain historical evidence.',
    'Prove tests/test_oom_sakkie_weighing_presentation.py and tests/test_oom_sakkie_breeding_plan_presentation.py in Run canonical conversational follow-up gates alongside all existing conversational, breeding, weighing and PostgreSQL coverage, with zero skips. Retain all broader stages and require the four full helper suites on the exact final helper head before production binding. Separately require fresh genuine owner weighing and breeding questions on the loaded revision, exact stored typed/result/provider bindings and later natural cycles before claiming an owner outcome; PR1371 deliveries do not establish this new presentation outcome.',
    'Prove the exact deployed six owner question journeys with current canonical readback and provider-bound responses; tests and hosted qualification alone are not owner acceptance. Check distinct domain answers, truthful failures, Afrikaans/English behavior and preserved general briefs. Do not fabricate a genuine owner test or mark full fleet autonomy from successful read questions.',
    'Prove the named hosted stage Prove family presentation and historical-review continuation with released family presentation and farrowing PostgreSQL tests plus family lifecycle, owner-task lifecycle, farrowing runtime, concise farm brief and ROOTLINE daily presentation coverage. Keep the broader audit stages and the four existing helper qualification suites. Separately require genuine loaded-revision family delivery, exact canonical readback and later natural-cycle continuity; local tests and a release cannot establish owner-visible acceptance.\n\nProve tests/test_oom_sakkie_purpose_completion.py in Prove weighing reconciliation with isolated PostgreSQL with zero skips, using the real approved batch writer and default manager store for completion, replay, partial/missing provenance, identity, epoch, lease and concurrent-current-work refusal. Also require tests/test_oom_sakkie_purpose_telegram.py, tests/test_oom_sakkie_purpose_telegram_postgres.py, tests/test_oom_sakkie_purpose_membership.py and tests/test_oom_sakkie_purpose_overview.py in the same isolated PostgreSQL qualification stage, preserving all prior selectors and zero skips.',
    'Prove the real PostgreSQL 314/317-candidate cohorts with 32 absent terminal findings use two whole-cohort lookup reads while preserving material events, generations, observation epochs, canonical identities and leases. Preserve concurrent insertion between snapshots, second-snapshot deletion rollback, post-snapshot insertion containment, reversed-cohort serialization and owning current-evidence refresh before delivery.',
    'Publish bounded current weighing assessment through the existing manager case and family brief. Preserve exact source and case identity, current recipient, generation and active-worker lease fences; only genuine source changes may alter material evidence. Observation time, row order, display changes and repeated natural cycles must not churn evidence, manufacture work or create another provider attempt. Retain truthful cohort totals with bounded detail; current eligibility, prior-window capture and actionable due work remain distinct.',
    'Read existing canonical health sources through one bounded consistent read-only snapshot; reject missing canonical configuration, incomplete reads and deadline exhaustion. Move the existing prepared mortality preview rebuild to final admission instead of adding another snapshot. Prove legacy unsent preview eligibility, same-card replay, genuine callback, current canonical readback and later natural manager cycles; other protected-action renewal rules remain unchanged.',
    "Read-only conversation answers must not create farm facts, close cases, create or renew protected claims, weaken current private-principal authorization, borrow another recipient's context or retry ambiguous delivery; existing protected actions retain their separate confirmation rails.",
    'Reassess an original unresolved retained mortality identity only from its existing original report text and original source time against current canonical identities through the existing deterministic specialist assessment. Use no new AI call, invented observation or owner replay. Preserve the original report and all source history, record attributable reassessment, reject contrary typed evidence and require a current protected preview and fresh genuine confirmation for any farm effect.',
    'Recognize owner-reported named mortality dates in either order and ordinal forms; resolve omitted year from the original evidence timestamp, preserve explicit year, reject invalid or conflicting dates, and retain chronology validation and genuine confirmation before any mortality write.',
    'Reconcile the existing HERDMASTER weighing concern from complete bounded current canonical lifecycle, weight, sale, allocation, outlet and parent-order evidence in one read-only snapshot. Keep the intentional prior weekly reporting window separate from current cohort eligibility, latest valid weights and current due evidence. Sales, reservations, an order promise, missing weights or an old reporting date never establish physical departure or authorize a new weighing task. Unsupported, duplicate, crossed, nonfinite, missing or conflicting evidence remains unresolved.',
    'Record condition_observation only through the existing grouped canonical pig_observation_events writer with recovery_hold_action=not_recorded and no supersession. A score of 3 is an observation, not recovery clearance: preserve an earlier explicit active hold and all prior observation history. Do not infer a hold, clearance, breeding readiness, mating, pregnancy, exposure, movement or pig-state change. Reject extra protected-effect fields rather than interpreting them as part of a condition-only report.',
    'Refresh only the exact claimed retained case identities through current canonical source, cancellation, resolution and completion checks; preserve the full canonical animal identity set for duplicate-tag rejection. Skip unrelated intake discovery during targeted retained refresh while preserving broad collection behavior.',
    'Refresh retained farrowing review only for the exact claimed original report, original private principal, stable canonical sow identity and one preserved expired never-attempted recovery claim. Require complete bounded source, claim, case and canonical history, current generation and evidence binding. Do not replace, renew, rearm or mutate the protected claim, report or farm facts; cancellation, competing claims, attempted delivery, confirmed outcomes, crossed identities and incomplete history refuse the review.',
    f'Release only the protected merge whose application tree equals exact PR{CANDIDATE_PR} head {HEAD} to existing web {WEB_SERVICE}, only after protected merge and required checks. Preserve all hosted selectors and four helper suites. Require completion and Telegram regressions in the existing isolated PostgreSQL qualification stage with zero skips; prove the conclusive-departure exception never waives retained members or ambiguous lifecycle. Qualify verified English/Afrikaans saved-purpose singular/plural wording. No manual case completion, owner confirmation, callback replay or provider workflow mutation. Genuine normal-cycle same-case completion and quiet later continuity remain required.',
    'Render the bounded breeding plan from exact canonical task and case fields without parsing specialist prose into new facts. Preserve task identity, displayed subject binding, chronology, recovery holds, evidence gaps and detailed worklist availability. Recorded exposure does not confirm mating or pregnancy; owner review is not a missing physical observation. Show a complete boar-and-date proposal only from its matching canonical case and current proposal fields; unsupported or incomplete evidence remains explicitly unresolved. Ask at most one grounded question for a uniquely displayed canonical subject; duplicate, unknown or ambiguous aliases cannot select a question, and condition questions retain the animal name and observation date requirement.',
    f'Require an independently authenticated attributable owner instruction bound by the coordinator to exact candidate {HEAD}, manifest and this exact legacy mortality technical-pending reconciliation and existing-web-only release contract scope. Preserve the actual standing instruction and its original context; do not fabricate a hash-specific owner answer, infer authority from source pins, extend a consumed exact manifest or authorize a later candidate. Registration approval alone does not grant provider mutation authority. This does not grant production transport authority or make engineering release approval farm confirmation. The same attributable instruction must also cover the previously scoped scheduled ready-purpose notice and its sole proven-zero-send retry; prior read-only projection authority alone is insufficient.',
    'Require the existing current Telegram allowlist and family-principal mortality-confirmation capability before claim creation and canonical preview persistence, at presentation admission and immediately before sending to the original private recipient, including scheduled completed delivery. Recipient revocation prevents delivery without changing the canonical completed farm fact; never redirect to another owner or change family permissions.',
    'Resolve an explicit animal by exact canonical Pig ID, tag or name in one bounded read-only repeatable-read snapshot; preserve Active, Sold and Dead lifecycle facts, contain ambiguous or missing identity, scope evidence before limits and report overflow rather than silently answering from an incomplete animal history.',
    'Resolve sow and litter by stable canonical sow and litter IDs, incident chronology and eligible active-litter status. A missing or changed display name cannot defeat an otherwise exact identity, and a name-only match cannot authorize a litter. Ambiguous identity, multiple eligible litters, conflicting or incomplete history and unavailable evidence refuse protected preparation without inventing farrowing, loss or litter facts.',
    'Retain only the exact bounded canonical subjects actually displayed in a successfully delivered read-only breeding plan. Bind subject IDs and displayed aliases to that stored plan, original provider input, configured private owner and current recipient; resolve a genuine follow-up through exact current canonical identity. Missing, ambiguous, expired, cross-recipient, undelivered or conflicting context refuses selection. A read answer or historical plan is not a new observation, farm instruction, protected preview or confirmation authority.',
    'Retire only the exact old HERDMASTER advisory case whose current canonical completion or lifecycle evidence proves that advisory obsolete. Bind the locked case identity, evidence digest and generation to the specialist-owned disposition, revalidate before commit and preserve its entire event history. Missing candidates, silence, similar animal labels, partial reads and delivery alone never authorize retirement; unrelated cases remain open.',
    'Return truthful localized English/Afrikaans callback alerts within Telegram limits. Failed acknowledgements may use one receipt-bound deduplicated informational family notice; preserve provider ambiguity and do not leak internal policy objects. Pending or ambiguous successor delivery must be reported as uncertain, without resending, claiming it was presented or saying the farm event was recorded; already-presented feedback requires exact provider/card binding.',
    f'Rollback is limited to web {WEB_SERVICE} revision {WEB_ROLLBACK}; this does not authorize another service, provider workflow or configuration change. Bind the exact current deployment/settings baseline and verify the released service identity before rollout or rollback. Preserve additive schema and genuine later business, claim and delivery history; uncertain deployment outcomes require readback rather than blind retry.',
    'Route inventory counts, pen capacity, weighing attention, litter/weaning attention, breeding plans and HERDMASTER owner dependencies through explicit typed read capabilities and the existing canonical services. Preserve the selected capability through the existing front door and gateway; do not substitute a generic farm brief or an unrelated pending question. Reuse existing breeding execution and scoped follow-up rails rather than create another worker, data owner or queue.',
    'Scheduled prioritization uses no paid model; coalesce routine briefing changes, preserve distinct urgent/owner-decision interrupts, and back off the same failed generation. Do not alter the existing scheduler or trigger a manual cycle.\n\nExplicit owner-confirmed future review dates use existing case events; newest request supersedes old dates and causes one natural due revisit. Consolidate only new unnotified or due groups; historical URL notices, partial decisions, unavailable siblings, immutable receipts and quiet unchanged cycles remain preserved. Urgent provider work precedes routine summaries under the unchanged 80-second cycle/30-second reserve. No new queue, schedule, AI polling, manual live trigger or per-case fallback. Optional semantic navigation uses the existing AI budget and cannot provide farm facts/confirmation. Require exact available membership, explicit current delivery state and verified dated deferrals before taking a quiet path ahead of history; only wholly delivered groups with no due request qualify. New, changed, unnotified or due work retains history verification. Count each bounded failure type and stage once; a completed worker cycle does not prove healthy overview continuity.',
    'Select retained mortality reports and short replies from existing typed specialist assessment and exact canonical animal identity; contrary assessment never falls back to legacy prose. Preserve latest-state, recipient, cancellation, supersession, protected claim, confirmation and replay guards; prove a genuine scheduled confirmation-card delivery and later canonical outcome separately.',
    'Separate bounded retained mortality and proven advisory family collection and refresh from the broad HERDMASTER collector. A broad timeout must not discard independently complete family evidence. Preserve exact canonical selectors, duplicate-tag and cross-principal containment, current-candidate precedence independent of collector order, sibling failure attribution, and the unchanged total retained-read budget and cycle/send deadlines.',
    'Separate retained-report refresh from broad herd collection; verify source and deadline containment, exact current canonical preview, genuine protected delivery/confirmation, atomic recording/readback, silent replay and a later independent manager cycle. Local or hosted simulations do not constitute owner acceptance.',
    'Share canonical purpose-review work between genuine weighing answers and the existing manager case, preserving day-14 eligibility, qualifying dated weights, cohort identity and current reconciliation. Missing historical coverage alone never establishes current weighing work. List clear weighing members beside held members with exact reasons; unknown, conflicting or unsupported evidence remains held or unavailable, never false no-work. Exclude conclusively sold/off-farm animals. Recorded weights advance the same case to decision only when the complete cohort has no missing or blocked member. Use one bounded read-only repeatable-read snapshot and shared remaining deadline; refuse overflow, query failure or inconsistent source. Detailed purpose reads remain opt-in for weighing. Observation time, day counters, display order and unrendered advice must not churn material evidence or create duplicate cases or attempts. This is an advisory application capability, not farm execution or release-operation authority. Preserve protected condition-observation intake, genuine observation and owner confirmation, hold preservation, all prior effects and the five metadata-write registration. Add no farm writer, claim, schedule, schema, model call, manual send or provider retry. Require a genuine loaded-revision weighing question, exact retained typed/provider binding, canonical cohort readback and later natural same-case reassessment; synthetic tests and prior releases do not prove this owner outcome.\n\nSeparate scheduled ready-purpose private-owner notice: the preceding no-provider-retry rule remains on the read-only weighing projection. Only this notice permits one existing opaque retry after durable zero-send proof bound to exact content, owner and generation; ambiguous history refuses. Revalidate unchanged case identity, material, lease and current source. No farm write, model, new schedule, schema or manual trigger. Prove same-case delivery and later natural reassessment.',
    'Share concise family message presentation through existing Oom Sakkie producers and delivery rails. Use short localized headings, readable bullets, restrained emoji and safe text escaping. Preserve exact actions, quantities, dates, dose, route, batch or lot, notes, lifecycle and uncertainty; never turn missing evidence into a fact or hide safety-relevant differences for visual brevity.',
    'Suppress an obsolete withdrawal advisory only for conclusively departed canonical animals. Missing, unknown or conflicting lifecycle evidence remains unresolved. Preserve current work and every existing source, claim, case, farm and provider history; later normal manager cycles must independently prove progress and protected delivery.',
    'The condition-observation effect describes the bounded application capability, not release-operation farm authority. Registration remains exactly five canonical release-metadata writes and does not create a live observation, protected claim or confirmation. Engineering approval, source pins, test fixtures, release, provider delivery or read-only answers never substitute for a genuine farm observation and its own protected owner confirmation. Preserve all existing read and presentation invariants, parent mission, holds and consumed approvals; this inherited condition-only intake adds no model call, migration, scheduler, service configuration or direct farm write authority.',
    'The existing scheduled worker may recover delivery of an exactly bound canonically completed retained-mortality result, including expired executing or exception-pending delivery leases, only after canonical operation, actor, animal and welfare readback and fresh recipient authorization. Keep effect_unresolved excluded; never automatically execute a pre-domain mortality receipt. Preserve bounded ambiguous same-card edit recovery and silent delivered replay without requesting another owner click.',
    'The first orphan replacement preparation sends nothing. A later normal manager cycle may present the exact audited successor through the existing protected delivery rail after current recipient authorization, complete lineage validation and fresh canonical rebuild. The successor requires its own genuine confirmation; replacement, scheduling, registration, release and the stale claim never grant farm-write authority. Preserve the original manager case, source identity and all histories, and use the existing atomic domain/welfare/source/claim completion on genuine confirmation.',
    'Preserve released canonical purpose-preview presentation and stale/duplicate-submit containment, preserving the existing protected batch writer. Preserve attributable approved-purpose completion of the existing fenced manager case and read-only canonical purpose-cohort work between weighing answers and existing manager cases, preserving current holds, bounded evidence and stable identity; preserve released named dated condition_observation intake through the existing protected breeding claim and canonical observation writer, requiring its own genuine confirmation and preserving explicit recovery holds, overdue-removal and evidence-gap presentation, task order, question priority, weighing and breeding owner-attention presentation, cancelled-order history containment, read-only breeding subject context, canonical weighing reconciliation, concise typed farm-brief presentation, exact presented-text binding for proven-zero-send ROOTLINE daily retry, retained farrowing review, identity, advisory disposition, retained mortality preparation and domain-scoped read questions, and admit no later candidate. Registration authorizes metadata reconciliation only, not an incident correction, manual expiry extension, predecessor claim rearm, parallel active claim, reused observation window or synthetic owner confirmation; consumed ordinary renewal and manual extension remain consumed. Existing delivered expired-card continuation and genuine confirmation restrictions remain; the already released audited never-attempted orphan replacement remains the only scheduler preparation exception.',
    'This successor adds no model call, confirmation bypass, direct farm mutation, broad mission closure, provider replay, scheduler deployment, unrelated configuration change or schema change. Preserve the already released stable-identity reassessment, exact proven advisory disposition and audited never-attempted legacy-claim replacement; preserve the released concise typed farm-brief presentation and exact presented-text binding for existing proven-zero-send ROOTLINE daily retry, preserving strict retry authority and all previously released historical-review and protected-preview behavior without changing farm-effect authority. Preserve the existing durable US$1 SAST-day OpenAI cap and all protected confirmation, mortality, delivery and current recipient controls. Any actual farm update still uses its existing separately authorized protected path. Preserve the previously released named Telegram capabilities and protected claim kinds within their existing boundaries; no migration exception is renewed and no release-operator farm authority is granted.',
    'Treat the genuine current reply as separately attributable new input through the existing protected farrowing preview path. Preserve the historical report, original and expired recovery claims, source history and unconfirmed historical counts unchanged; do not consume an old claim or interpret the old review as confirmation. The fresh statement may prepare a new protected preview only, with zero birth or other farm writes until its own genuine current confirmation.',
    'Unpriced audio/image/model requests fail closed with text guidance. Existing protected confirmations and canonical authorization remain unchanged; budget denial grants no alternative execution authority.',
    'Use bounded delivered context for current English and Afrikaans follow-ups, preserving owner, private chat, provider and subject binding; distinguish an explicit clarification question from a delivered summary and ask targeted Farewell ambiguity without inventing a farm outcome.',
    'Use one fresh bounded canonical health preview for early never-attempted orphan preparation. Reuse it only within the same preparation attempt and existing source/principal/claim/history locks; retain all no-attempt markers, complete material comparison, predecessor snapshot audit, atomic replacement and zero-send first preparation. Do not reuse an unbound preview, skip genuine-confirmation revalidation or revive a delivered, uncertain, cancelled or competing claim.',
    'Use retained_mortality_orphan_replacement.v1 for the immutable predecessor-keyed replacement audit. Under the existing source lock and active-claim invariant, atomically preserve the old claim, change only its status to changed, record its full old-claim audit plus source before/after evidence, create one fresh protected successor, and append retained_repreview.orphan_predecessor carrying the replacement event ID and predecessor claim hash. Retain both material digests without asserting equivalence; any failed guard or write rolls the complete transaction back.',
    'Validate complete bounded claim, source, family, case and operational chronology across successive expiries, with exact intermediate source edges and one linear lineage. A manager case may project only an already audited successor from that validated lineage while awaiting reconciliation; retain exact locked case identity, generation and evidence digest and reject arbitrary or root projection references. Same-timestamp event hashes are not causal order; require unique contiguous generation transitions and preserve unknown-history refusal.',
    'Verify exact loaded web revision and genuine subsequent provider delivery against canonical animal/case identities, read-query scope, language and durable audit; verify replay containment and later natural manager-cycle continuity. Do not substitute a terminal answer, replay historical Telegram messages, make the owner relay terminal actions or request already-pending physical facts again.\n\nRequire actual direct/gateway, canonical schema/claims/family/batch/default worker, concurrency, dated revisit, failure/replay and existing broader tests with zero skips; genuine Telegram choice/confirmation plus canonical/provider readback and later natural continuity remain mandatory for an owner outcome.',
    'Verify the loaded revision, budget metadata without prompt or secret disclosure, owner-visible text behavior, natural scheduled-cycle silence and next trigger. No terminal-generated farm observation or fabricated owner acceptance.',
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
        _require(isinstance(contract[key], list) and contract[key] and len(contract[key]) <= (102 if key == "operational_acceptance" else 100)
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
