# Control Tower Mission Register

Status: Active owner-facing dispatch authority

## 2026-08-19 - Queued Oom Sakkie shared owner-attention projection

Charl confirmed the cross-channel invariant: application, Telegram, future
voice and autonomous workers use the same canonical farm facts and the same
work-item identities, priority, ownership and lifecycle. Channels may render
different amounts of authorized detail, but they must not independently decide
what farm work exists.

This is the next phase of the existing Oom Sakkie continuous-manager and
HERDMASTER worklist lineage, not a dashboard-only mission and not a second
queue, database, scheduler or mission ledger. The current defect is that the
homepage assembles attention independently in browser code while the Brief uses
the manager pipeline. Prince can therefore appear in the Brief but not on the
homepage; Molly and Clovy can receive different classifications; status
reconciliation can be mislabeled as physical weighing; and a ROOTLINE refresh
failure can be shifted incorrectly to Charl.

Required outcome: one typed backend attention projection combining active
welfare lifecycles, HERDMASTER/breeding/litter work, ROOTLINE, sales and Orders.
Every item carries a stable ID, category, open/resolved/superseded state,
priority/watch classification, specialist owner, exact owner action, evidence
provenance/freshness and safe detail target. Homepage, Brief, Telegram and later
voice consume the same ordered identities. The homepage renders the shared top
three plus total hidden count and View all; channel-specific formatting and
permissions remain presentation concerns only.

Acceptance requires Prince parity and one identity across homepage and Brief;
resolution removes it from both; Molly/Clovy have the same classification or
evidence-based exclusion; `status_reconciliation` is distinct from
`weighing_due`; ROOTLINE automatic retries remain assigned to ROOTLINE/Oom
Sakkie until one precise physical observation is irreducible; specialist
timeouts cannot erase unrelated work; Telegram follows the concise semantic
emoji standard; and exact-revision authenticated desktop/mobile production
parity is proven. CODEX UI follows only after the shared backend contract is
established and requires Charl's visual approval.

Promotion is serialized behind current ROOTLINE and Orders/Sales work because
their manager adapters and presentation paths are collision-prone. The recently
completed Oom Sakkie timeout repair and autonomous five-minute manager cycles
are the operating base for this phase.

## 2026-08-19 - Owner-approved livestock quotation separation

Charl approved one shared livestock pricing, quotation and document system with
three explicitly different customer journeys:

1. `price_indication` - a current category-price guide in conversation, with no
   order, PDF by default, allocation, reservation or availability promise;
2. `budgetary_quotation` - a formal category-based quotation for funding,
   loan, company approval or budgeting, attached to the customer intake and
   containing no selected animals or stock commitment; and
3. `sales_quotation` with `quotation_basis = current_availability` - a current
   sales quotation that may contain supported animals or groups, while
   allocation proposal and reservation remain separate evidence states.

Customer request, quotation, allocation proposal and reservation must remain
distinct. The implementation must reuse the current requested-items editor,
effective-dated Supabase pricing, document renderer and outbound delivery rail;
it must not create a second quote engine. Issued prices are immutable snapshots,
expiry and supersession are explicit, conversion to an order refreshes current
price/availability, and no historical availability or reservation may be
carried forward as current truth.

The review also found that the compact authoritative Gold Standard no longer
contains the historically owner-approved direct-price examples retained in
commit `d78f1e02`. The implementation mission must restore only the unique
active behaviour - answer a supported direct price question before further
qualification, distinguish category price from availability, show quantity,
unit price, subtotal/total when known, and never imply reservation - without
restoring the removed 498-line historical document or creating duplicate
doctrine.

Immediate customer recovery: a one-page quotation for funding approval was
prepared locally for Wenettitus as
`FQ-2026-0819-WENETTITUS-01`, using read-only canonical Supabase prices R400 for
5-6 kg and R600 for 15-19 kg. It records 10 female and 10 male 5-6 kg piglets,
one female and one male approximately 15 kg, subtotal R9,200.00, VAT R1,380.00,
total R10,580.00 and validity through 22 August 2026. It explicitly creates no
order, allocation, reservation, availability promise or payment request. Charl
accepted the PDF for owner use; provider/customer send remains unconfirmed and
must not be inferred.

Continue the existing SALES/SAM/HERDMASTER quotation lineage after the current
customer recovery; do not create a parallel mission or document engine.
Doctrine reconciliation precedes implementation, followed by one intake-linked
quotation aggregate, quotation lines/price snapshots, SAM intent separation,
document/UI projection and exact Wenettitus-shaped acceptance. The current
stock-backed preview remains separately released for authenticated owner
acceptance and must not be misrepresented as the funding-quotation journey.

Release closure: PR #1118 merged normally as `05c3e2aa` after all three
exact-head CI lanes passed; Render deployed that exact revision and then the
documentation-only current-main superset `cc3011ed`. Migration
`202608190003_create_livestock_quotation_aggregate` is applied and read back in
production with both quotation tables, immutable snapshot triggers and zero
initial quotation/line rows. Authenticated production acceptance at
2026-08-19 08:25 UTC resolved the current effective Supabase price snapshots
(`PRICE-YOUNG_PIGLETS_5_TO_6_KG_ANY` at R400 and
`PRICE-WEANER_PIGLETS_15_TO_19_KG_ANY` at R600) and proved all three distinct
preview journeys against the Wenettitus-shaped four-line request. Each returned
subtotal R9,200.00, VAT R1,380.00 and total R10,580.00. Price indication and
budgetary quotation selected no animals and returned no allocation; the
current-availability sales quotation alone returned a HERDMASTER proposal.
All three reported zero quotation/order/order-line/reservation writes, and the
budgetary journey explicitly reported no allocation, animal selection,
availability promise, order or reservation. The existing PDF was not opened
for delivery or sent, and no customer/provider contact occurred.

Lifecycle: `BUSINESS_COMPLETE / DEPLOYED_QUOTATION_JOURNEYS_ACCEPTED /
CUSTOMER_DELIVERY_SEPARATELY_PROTECTED`. The development mission is closed;
later customer/provider delivery requires its own exact protected authority.
The next sales mission remains the registered deployed SAM salesperson outcome,
not another quotation engine or terminal-created customer response.

## 2026-08-19 - Overnight operating-outcome recovery

Owner priority: tomorrow's four-line livestock quote must be usable, while
ROOTLINE and the BEACON/SAM revenue loop continue toward genuine deployed-agent
outcomes. GENERAL's read-only finding is reconciled into the existing livestock
Orders/SAM/HERDMASTER journey; it is not a new OP-004, selector, order engine or
clearance workflow.

The controlling livestock distinction is now the immediate doctrine-repair
input for the existing journey: a recorded food-chain medicine withdrawal does
not by itself prohibit a live-animal quote or transfer. It blocks slaughter or
food-chain entry until the recorded date and must be disclosed compactly. An
actual recorded health, welfare, quarantine, movement or explicit sale hold
remains a blocker. Missing formal clearance fields must not be invented as
positive clearance and must not create a clearance regime the farm does not
operate. Sold, dead, off-farm, reserved, terminal and source-conflicted animals
remain genuine blockers. This is an owner operating rule, not a statutory or
veterinary claim.

Recovery WIP remains capped at three implementation tracks:

1. **Slot 1 - SALES / HERDMASTER livestock order completion
   (`RELEASED_OWNER_AUTH_REQUIRED`)**: continue the existing multi-line requested-items and
   OP-004 lineage in one fresh current-main worktree. Reconcile the contradictory
   livestock doctrine first, then simplify the existing live-transfer contract,
   matching, quote preview, Orders presentation and livestock document
   disclosure. Acceptance is the owner's exact four-line request represented
   once, with truthful recommendations/shortfalls and no premature reservation,
   purpose change, customer send or fabricated clearance.
2. **Slot 2 - ROOTLINE operational irrigation (`OPERATING_SPINE`)**: continue
   the existing ROOTLINE/Oom Sakkie spine from current main. The terminal may
   repair, review, integrate, deploy and observe; only deployed ROOTLINE may
   operate hardware, and only inside current canonical standing authority with
   fresh provider/safety evidence. B/C, fertiliser mixer, fertiliser injection
   and borehole remain separate commissioning/authority classes.
3. **Slot 3 - REVENUE BEACON/SAM closed loop (`OPERATING_SPINE`)**: continue the
   existing campaign/card lineage without touching Orders implementation.
   BEACON Meta content must use the sow's human name, tell a farm-life story,
   make no availability/sales/price/booking/urgency/contact call-to-action and
   use only exact public-use media or a precise missing-media exception. SAM
   activates only from genuine attributed inbound after protected publication.

The deployed Oom Sakkie manager and Brain Guard continue independently and do
not consume a development WIP slot. Manager timeout repair PRs #1100-#1103 are
contained in deployed revision `181543e7`. Natural cycles at 22:20 and 22:25
UTC completed after Brain Guard; the later cycle confirmed one material delivery
and suppressed fourteen duplicates. CORE remains frozen outside the three
overnight tracks until a slot releases or a proven cross-track incident requires
containment.

Owner subsequently authorized additional non-conflicting overnight work. A
fourth **read-only CORE recovery audit** is selected outside the three
implementation slots. It may inspect exact current source, registered CORE
worktrees, task/provider identity evidence, governed-stop state, queue/mission
truth, historical failed epochs and the next smallest reusable repair. It may
not edit source or governance, stage or activate CORE, mutate tasks/processes,
create/admit/dispatch missions, acquire the release lane or perform provider,
database, farm or customer writes. Its output is one evidence-backed
continuation packet ready for automatic promotion when an implementation slot
releases. Process existence and old activation waits remain non-evidence.

Charl then explicitly promoted this same `CMQ-20260813-05` Recovery Slot 1 lane
from read-only audit to exact-current validation and staging, while retaining a
separate protected activation gate. Authoritative main
`70baac05223608b1c2592b0512e5aa1037ea841b` passed 77/78 focused CORE
activation/staging tests with one platform skip and 251/257 proportional CORE
control tests with six platform skips in disposable image
`sha256:dad31c6f6a8da88f6146d6b0302d857df26e451c5891811c2a8b2ec277de1ab8`:
network disabled, read-only source/root, private PID boundary, all capabilities
dropped, unprivileged UID and tmpfs only. Signed validation receipt
`2d57556f77317915869378e164767bbc0a892dde76b63785f83a1a8e104988ec`
was preserved in the existing promotion ledger. The serialized staging rail
used historical `f096d36d` only as the exact rollback tuple and staged both
detached runtime trees plus manifest to `70baac05` under lane
`fd3583aa382e458f83ad7fc23b0b1cf0`. Readback proved no active release lane,
the scheduled task remained disabled, governed-stop digest remained
`8887c0c06d040b60fef580c0135761019fe7e416d594538cf86fcf18d1e594b1`,
and no activation or reconciliation lock exists. Lifecycle is
`OWNER_HOLD / EXACT_CURRENT_VALIDATED_AND_STAGED / ACTIVATION_NOT_AUTHORIZED`;
Business completion is false. Never reuse failed activation identity
`51412371da70e5ae6ba8a6f4fb1e7172` or any older epoch. The only promotion
trigger is fresh owner authority bound to exact revision, manifest, receipt,
stop digest, disabled task identity, observe-only mode and a new activation
identity/expiry; until then no task enablement, stop removal, worker start,
mission pickup or autonomy claim is permitted.

Later exact owner evidence supersedes that pre-activation hold for historical
state only: activation `4ee5c3545bb84873b8f65581736a3caf` is sealed and
non-replayable. Task Scheduler instance
`{E66790D2-FAD2-4A7D-98AC-540CEC3BC444}` reached its registered action and
exited `2147942401` (`0x80070001`) before supervisor or runner publication.
Containment restored governed stop and disabled that exact task. The retained
evidence cannot distinguish quoting, path, environment, launcher or early
Python failure because the inline `pythonw -c` boundary retained no secret-safe
stderr or startup phases. Current `CMQ-20260813-05` work is therefore
`WORKING / SOURCE_ONLY_STARTUP_EVIDENCE_REPAIR`; it may repair and review the
reusable pre-publication evidence boundary but may not stage, deploy, mutate or
run Task Scheduler, start CORE, or reuse any sealed epoch. Promotion after a
clean PR requires a new serialized validation/staging journey and a separately
authorized fresh activation identity.

Automatic promotion: each development lane continues through source, tests,
review, normal integration, deployment and genuine deployed-agent acceptance,
stopping only at a real protected, physical, external or serialized-release
boundary. Released clean worktrees must be closed promptly. Every lane must
return `CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md`; open processes and older
waits are not activity or dependency proof.

Slot 1 release evidence: PR #1107 merged on 19 August 2026 as main revision
`aea19d46aa4aee292b66e91fa8f590494deaae65`. Exact-head CI passed all three
required workflows; Brain Guard passed with zero findings; independent review
approved; authenticated and safe-local read-only desktop/390px preview evidence
proved the inherited `5_to_6_Kg` band (owner shorthand “56 kg” interpreted as
5–6 kg) plus the approximately 15 kg female/male lines, truthful availability,
shortfalls, animal facts, price and consolidated medicine disclosure with no
order/farm write. Production `/health` returned 200 and the deployed JavaScript
and CSS matched the exact main blobs byte-for-byte. `/orders/new` correctly
redirected to owner login. No production owner credential was present in the
terminal, so authenticated production acceptance remains the one bounded
owner-only action; no quote, reservation, purpose change or customer contact
was performed.

## 2026-08-18 - Slot 2 OOM SAKKIE morning-truth recovery

Fresh owner evidence showed materially unchanged ROOTLINE recommendations sent
repeatedly although no irrigation executed, a simultaneous manager brief saying
ROOTLINE refresh was unavailable, Monday weight coverage regressing from the
provider-confirmed 79/81 to 0/81, and an overlong machine-like farm plan. Charl
reports tags 123 and 151 were sold on Sunday, but Orders/Sales selection cannot
yet preserve that fact canonically. It remains owner-reported pending commercial
evidence, not a recorded sale or completed commercial fact.

Continue the existing shared OOM/ROOTLINE Slot 2 spine. Preserve weekend weights
in Monday's just-finished governed window; route uncovered tags to canonical
sale/order/status reconciliation without classifying them for reweighing; store
fresher unchanged ROOTLINE generations silently under the same date/material
plan identity; reserve Recommendation, Authorized, Started, Completed, Held and
Failed for exact lifecycle evidence; and render one short prioritized morning
plan. No weight rewrite, inferred sale, Telegram send or hardware actuation is
authorized. Source acceptance requires independent authority/replay review, one
serialized PR/merge/deploy, then one genuine scheduled concise result and a
later unchanged silent cycle.

## Purpose

This is the canonical planning and dispatch ledger for the visible development
terminals CORE, HERDMASTER, ROOTLINE, OOM SAKKIE, SAM, BEACON and CODEX UI. It grants no
customer-send, farm-write, provider-mutation, production-release or hardware
authority.

A visible terminal is a temporary development worker, not the deployed agent or
durable runtime. A prepared prompt is not running work, and terminal activity is
not proof that a deployed agent is operating.

Controlling authority remains the Agentic Operating Mission Standard, the
canonical Agentic Farm Runtime Programme at
`docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md`, and relevant specialist
doctrine and canonical-action contracts.

## Mandatory feedback transaction

Before answering every pasted terminal report or issuing another prompt,
Control Tower must:

1. verify authoritative lineage and controlling governance;
2. resolve the existing mission ID and avoid implicit duplicates;
3. append the evidence and decision to the feedback ledger;
4. update business status, dependency and owner-visible outcome;
5. update visible-terminal state separately from deployed-runtime state;
6. record delivery as `queued`, `prepared`, `delivered`, `acknowledged`,
   `started`, `progress_observed`, `released` or `contained`;
7. preserve and classify dirty or unique worktrees;
8. select exactly one next action: `SEND_NOTHING`, `ADDENDUM`, `CONTINUE`,
   `NEW_MISSION`, `WAIT_FOR_INPUT` or `CLOSE`;
9. only then return the assessment and continuation prompt to Charl.

Before displaying any prompt text, Control Tower must also emit exactly one
owner-facing dispatch banner:

- `DO NOT SEND — TERMINAL ACTIVE` when the exact terminal is already executing
  the correct mission. No sendable prompt text may follow.
- `SEND NOW — TERMINAL IDLE OR RELEASED` only when fresh evidence proves the
  terminal can accept the named mission now.
- `HOLD — VERIFY TERMINAL STATE` when current terminal state is Unknown or
  contradictory. No sendable prompt text may follow.

This presentation rule is mandatory even when an assessment request asks for a
continuation prompt. A queued addendum remains in this register until the next
safe terminal feedback boundary unless immediate delivery is genuinely needed
and explicitly classified. Control Tower must not rely on conversation memory
as the dispatch record.

Before assigning or reporting any autonomous specialist mission, Control Tower
must also apply the Agent Operational Reality Gate. Record web/API state,
background-worker state, autonomous trigger, heartbeat, last independent cycle,
next cycle, authority mode, last terminal-invoked cycle and terminal-independent
continuity separately. If these facts are absent, use `deployed-dormant`,
`invocation-only`, `event-waiting`, `scheduler-degraded`, `authority-disabled`
or `Unknown`; never record the agent as working merely because source is
deployed or a terminal is testing it.

After a contained execution has exposed a reusable defect and that repair is
deployed, seal the old execution identities as historical non-replayable
evidence. The next acceptance must use current canonical evidence and one fresh
execution identity. Do not keep a historical card, message, customer,
conversation, job, segment or canary as the active operating loop.

Every feedback transaction must additionally normalize the whole mission to one
shared lifecycle state: `WORKING`, `REVIEW_HOLD`, `RELEASE_HOLD`, `OWNER_HOLD`,
`EXTERNAL_HOLD`, `CONTAINED` or `BUSINESS_COMPLETE`. Technical milestones such as
source-ready, PR open, CI green, merged, deployed, canary-passed or terminal
released are recorded as evidence only. They never close the owner-visible
mission. Control Tower must return a terminal to `WORKING` when safe authorized
stages remain, and must preserve a genuine Hold with its exact unblock condition.

## Mandatory all-terminal dispatch sweep

After every owner message and every terminal report, Control Tower must inspect
the complete board, not only the terminal named in the latest message.

For each visible development terminal, Control Tower must determine with fresh
evidence whether it is `actively_working`, `idle_open`, `released`,
`blocked`, `waiting_for_real_event`, `waiting_for_owner` or `not_launched`.
An open Codex process is not sufficient proof of active work; Control Tower must
correlate the assigned mission, attached worktree, recent activity and latest
terminal acknowledgement or report.

Control Tower must then:

1. keep every actively working terminal on its existing mission unless a
   genuine addendum is required;
2. give each idle or released terminal the highest-priority eligible mission
   from its existing queue;
3. select a different eligible mission when the current outcome is truthfully
   waiting on a clock, owner decision, provider event or physical evidence;
4. explicitly release a terminal when no safe eligible work exists instead of
   pretending that it is working;
5. never assign two terminals to the same implementation files or serialized
   production lane;
6. prepare one self-contained prompt per newly eligible terminal and state
   whether Charl must paste it;
7. update prompt delivery and acknowledgement separately—prepared work is not
   delivered, and delivered work is not started;
8. repeat the sweep after any terminal completes, blocks or releases.

### Control Tower response closure gate

Control Tower may not close an owner response merely because the named mission
was assessed. Before responding, it must account for CORE, OOM SAKKIE,
ROOTLINE, HERDMASTER, SAM, BEACON and CODEX UI. Each `idle_open` or `released`
terminal must be classified as exactly one of:

1. `SEND NOW` — one eligible existing mission and paste-ready prompt are
   surfaced to Charl;
2. `DEPENDENCY IDLE` — the exact dependency and automatic eligibility trigger
   are recorded; or
3. `NO SAFE WORK` — the inspected queue contains no non-colliding authorized
   work.

An unexplained eligible idle terminal is a failed dispatch transaction and
must be corrected before the response closes. This gate does not authorize
invented work, overlapping files, simultaneous release-lane ownership or a
prompt to an already active terminal.

The owner should not have to ask which terminal is idle or remember its next
mission. Until automatic terminal delivery is proven, Control Tower remains
responsible for detecting the opportunity and presenting the exact prompts to
Charl immediately.

If this transaction cannot be persisted safely, Control Tower must explicitly
say the register was not updated. Conversation memory alone is not tracking.

Use `docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md` for every
new terminal feedback packet and every Control Tower continuation prompt.

## Mandatory forward mission pipeline

The control board and each specialist queue must be maintained as a forward
development pipeline toward the specialist's complete authoritative scope.
Each terminal entry must record:

1. intended complete specialist role and owner-visible result;
2. capabilities already operationally proven by the deployed agent;
3. current outcome-bound mission and terminal/worktree owner;
4. next highest-value eligible mission after the current mission;
5. later sequenced missions required to complete the documented role;
6. file, runtime, authority and serialized-lane collision boundaries;
7. exact dependency and automatic promotion trigger for every deferred mission;
8. latest owner observation or decision that changed priority; and
9. prompt delivery truth separately from selection and preparation.

After a terminal reports Business completion, releases its worktree or enters a
genuine clock/provider/owner/physical wait, Control Tower must immediately
promote another eligible non-colliding mission from this pipeline. If none is
registered, Control Tower must inspect the authoritative specialist scope,
business rules, roadmap and proven operating gaps, register the best bounded
outcome, and dispatch it without waiting for Charl to ask. It must not create
busywork, duplicate an active mission or make a development terminal perform
the deployed agent's recurring operational work.

Owner observations may reprioritize this pipeline at any time. Reprioritization
preserves active, completed, dirty and unique work unless a real collision
requires an explicit Hold. Conversation memory is context only and never
replaces this register.

## Current control board

Snapshot: 2026-08-13 SAST, reconciled through main `b7c0edcf`.

| Terminal | Terminal state | Existing mission and business/runtime truth | Next action |
|---|---|---|---|
| 2026-08-15 | BEACON `BMQ-20260813-04` awareness production proof | PR #942 merged as `3db13e5f`; exact Render deploy `dep-da02h2gu01pc73er4k8g` loaded it. Fresh authenticated delivery-disabled provider `202608150411` returned one useful text-only Facebook farm-awareness proposal; direct/concurrent replay retained mission `OOM-BEACON-REQUEST-6E696B196B656D9D243362AB`, packet `BEACON-AWARENESS-3EB89F3316C0D28A5BA4B94E` and one canonical row. Telegram/Meta/customer/spend/farm/media/hardware/n8n/Sheets effects were zero. | `BUSINESS_COMPLETE` for the bounded proposal outcome. BEACON remains request-driven/event-waiting, not autonomously scheduled. Public posting, media use, scheduling, boost/spend and customer commitment remain separate protected journeys; keep broader automation sequenced later. |
| 2026-08-15 | BEACON `BMQ-20260813-04` awareness adapter repair | The exact failed instruction `Prepare a non-availability farm-awareness campaign.` is retained as non-replay regression evidence. Diagnosis: Oom Sakkie's semantic result recorded the intent, but the adapter discarded it and always selected the demand-qualified builder. | Continue the same mission: preserve stable `live_stock_awareness` into the existing awareness builder, keep HERDMASTER capacity and SAM demand independent/Unknown-safe, use only current public-use/hash-proven media or text-only content, and prove one fresh deployed result with zero publication/spend. |
| CORE | `WORKING`: opaque creator deployed; governance integration precedes first canonical admission | PR #910 exact reviewed head `0811d775` merged/deployed as `9fb4c830`; Render and loaded application revision agree. Authenticated malformed, aliased, substituted and conflicting exact IDs fail before mission-store reads/writes. Supabase still contains zero CMQ-05 missions and zero Shadow events/comparisons. Owner-approved lifecycle/portfolio doctrine is tracked and green in PR #886 but is not yet authoritative `main`. | Integrate/reconcile governance PR #886 first. Then CORE must verify the new authoritative Standard in its own worktree, create/admit exactly one CMQ-05, prove exact idempotent readback and produce the no-write legacy/current-admission manifest. Do not begin Shadow scoring, bulk legacy mutation or runner restart. |
| HERDMASTER | Lifetime genetic-merit backend operational; UI journey queued | PR #905 merged/deployed as exact revision `1e6846d7`. Repeated authenticated herd/Tyson profile reads returned stable versioned packets, Limited confidence with missing context, explicit non-causation and nullable unsupported evidence; eight canonical table counts were unchanged. Backend slice is operational, but HMQ-04 lacks owner-facing page proof. HERDMASTER terminal is released-retain. | Keep HMQ-04 active but queued behind CODEX UI's already-promoted UIQ-02 reconciliation. After UIQ-02 releases, assign CODEX UI the separate analytics rendering mission using the proven packet without recalculating biology or converting nulls to zero. |
| ROOTLINE | Second genuine protected attempt failed at coordinator Supabase load | Fresh card `3590` was correctly digest/card/owner/job-bound and Charl pressed once. Callback authentication, claim transition and eligibility succeeded, then Gunicorn timed out loading active execution history from Supabase before coordinator ownership or any ON command. Claim is contained; final provider readback is online/all OFF, segment unconsumed and zero controls. | `CONTINUE RMQ-04 — NO MORE OWNER ACTION`: repair/bound the coordinator `load_active` Supabase path end to end, with degraded containment and worker survival. Do not press/reuse `3590`, request presence, send another card or actuate until deployed proof passes. |
| OOM SAKKIE | Contextual DB boundary repaired; genuine acceptance pending | PR #908 merged/deployed as `8a4fb58c`, adding bounded connection/query deadlines, cleanup and explicit degraded handling. One isolated contextual canary produced one manager receipt, one ROOTLINE observation receipt and one provider-confirmed labelled Telegram acknowledgement; direct/concurrent replays were silent, database-unavailable paths created no retention/downstream action and zero farm/hardware effects occurred. Historical `3587`/`3588` remain immutable. | `SEND NOTHING`: release development terminal. Keep OMQ-03 active for the next natural contextual reply; correlate provider receipt, exact durable facts, ROOTLINE consumption, one acknowledgement and replay. Keep OMQ-02 cross-reference for historical provider-ambiguous truth. |
| SAM | Development released; deployed acceptance pending | `SMQ-20260813-02`: bounded WhatsApp/WebWidget authority and first-event-card repair merged in PR #882 as `b36b2ca3` and is live within successor `6d7f3259`. Conversations `1533`/`2143` were untouched. Business completion needs the next genuine eligible inbound. | `SEND_NOTHING`: deployed SAM owns the next event. Use the development terminal only for read-only correlation or a reusable defect exposed by that event. |
| BEACON | Not launched | `BMQ-20260813-00`: provider/runtime and retained-worktree truth unreconciled; no posting authority inferred. | `NEW_MISSION` only when launched: read-only current-truth reconciliation. |
| CODEX UI | UIQ-02 reconciliation complete; isolated implementation cleared | Production already hides the exposure workspace on successful empty data, but read-role users can see an unusable protected UIT control. The bounded contract keeps facts visible and hides mutation controls unless complete active evidence plus owner-admin authority exist. Dirty target files in the original workspace are preserved earlier facelift/preview work; no active terminal owns them, and implementation is cleared only in the clean isolated UIQ-02 worktree. | Implement template/JS/tests presentation-only in `C:\tmp\uiq-20260813-02-protected-transition`, preserve original dirty files, backend/digest semantics and HMQ-04. Produce fresh local desktop/mobile/empty/read/admin/failure previews for owner approval; do not merge/deploy. |

## Mission queues

### CORE

- `CMQ-20260813-02A` — `parser_deployed_waiting_for_separate_authority`:
  PR #877 evidence and PR #885 opaque-ID repair are integrated; watchdog remains
  active and no additional proof window is authorized.
- `CMQ-20260813-03` — `deployed_waiting_for_genuine_acceptance`: PR #899 merged
  and deployed as `84601c83`. Loaded revision truth and combined validation prove
  exclusive ROOTLINE-irrigation and grouped-weight routing. Integration created
  no claim, message, confirmation, execution or farm write. Development is
  released; the mission remains bound to a later genuine end-to-end protected
  grouped-weight/movement journey.
- `CMQ-20260813-04` — queued reversible legacy-document retirement.
- `CMQ-20260813-05` — `creator_pr910_ready_then_portfolio_baseline`: Phase A
  Shadow is deployed/enabled but cannot persist until PR #910's private creator
  repair is integrated. After deployed proof, create exactly one CMQ-05 admitted to
  epoch `CORE-CURRENT-2026-08-14`, then produce the owner-approved no-write legacy
  Portfolio Baseline Manifest before normal Shadow scoring. Full plan:
  `CMQ_20260813_05_CURRENT_PORTFOLIO_BASELINE_PLAN.md`.
  Control Tower evaluation on the existing CORE queue/runner/register. No new
  CORE, hidden terminal windows, terminal spawning or prompt delivery. Record
  proposed terminal/mission/status/classification/collision/prompt/outcome and
  compare against ten subsequent human-Control-Tower decisions. Promotion to
  assisted dispatch requires a separate owner decision.

### HERDMASTER

- `HMQ-20260813-03` — `operationally_verified`: PR #884 is deployed; correct
  proposal/hold truth and zero-write repeated readback are proven.
- `HMQ-20260813-02` — `closed`: PR #889
  is deployed and the anonymous redirect, friendly login, successful return,
  authenticated page, JSON denial, malicious-next containment and zero farm
  mutation were all production-verified; NEXT_STEPS, source-map and changelog
  reconciliation shipped in the same merge. Development terminal released-retain.
- `HMQ-20260813-00` — integrated; waits for a natural exact-pig observation.
- `HMQ-20260813-04` — `backend_proven_ui_journey_queued`: reconcile
  retained PR #823 and both lifetime-merit worktrees against current production,
  then define one names-first, Unknown-safe, confidence/sample-size-aware,
  association-not-causation data/UX contract for herd and animal analytics.
  CODEX UI implementation waits for this contract; no farm writes.
- `HMQ-20260813-05` — waits for a genuine completed weight batch.
- `HMQ-20260813-06` — waits for physical exposure separation.

Detailed HERDMASTER evidence remains in
`docs/06-operations/HERDMASTER_OPEN_MISSION_REGISTER_20260812.md`.

### ROOTLINE

- `RMQ-20260813-02` — `gateway_blocked`: repair HTTP 403 and prove protected
  receipt before requesting fresh owner presence.
- `RMQ-20260813-04` — `failed_acceptance_coordinator_db_timeout`: prior physical B/C
  commissioning remains valid and must not be repeated merely to prove that the
  valves work. The remaining defect is the canonical automation journey: it
  must distinguish an intentional multi-segment irrigation job (required when
  total runtime exceeds the controller's 3,599-second native fail-stop) from an
  accidental replay/duplicate, persist segment and cumulative-runtime truth,
  and expose one digest-bound protected preview/confirmation lifecycle before
  B/C autonomy can be enabled. No further physical B test is authorized until
  that source/runtime contract is reviewed and deployed.
- `RMQ-20260813-03A` — queued isolated Injection CH1 control commissioning:
  safe physical isolation/dead-head check, exact channel identity, bounded ON/OFF,
  provider readback, native 120-second fail-stop, deterministic OFF and silent
  replay. This proves valve/control behavior only and must not claim fertilizer
  delivery; it does not require an eligible irrigation day.
- `RMQ-20260813-03B` — queued real Injection flow commissioning after Mixer and
  eligible irrigation: one active zone, verified ten-minute clean-water preflow,
  bounded dosing pulses/spacing, ten-minute flush, physical flow evidence and
  verified injector OFF.
- `RMQ-20260813-05` — queued water-credit lifecycle after B/C acceptance.
- `RMQ-20260813-06` — hardware-blocked Borehole 1 independent fail-OFF proof.

### OOM SAKKIE

- `OMQ-20260813-02` — `genuine_delivery_provider_ambiguous`: morning brief `3587`
  was physically received but canonical delivery outcome says zero sends/provider
  ambiguous; reconcile truth without resending it.
- `OMQ-20260813-03` — `repaired_waiting_for_genuine_contextual_acceptance`: PR
  #908 bounded the database path and synthetic canary/replay/degraded proof passed;
  historical reply `3588` remains unretained and unreplayed.
- `OMQ-20260813-04` — waits for next genuine specialist request.
- `OMQ-20260813-05` — queued browser/Telegram/voice canonical parity.
- `HERDMASTER-NATURAL-HEALTH-LOSS-1/OOM-INTAKE-SLICE-1` —
  `stage2_operational_readiness_waiting_genuine_acceptance`: PR #898 is live as
  `43b91712`; authenticated routing, canonical chronology/evidence and the real
  handler passed an isolated zero-delivery/zero-write gateway acceptance. The
  deployed runtime now owns the next genuine report. Pig 002 must not be
  replayed or written.

### SAM

- `SMQ-20260813-02` — `deployed_waiting_for_genuine_acceptance` using
  conversations `1533` and `2143` only as regression evidence; never replay
  them. The next eligible genuine inbound must produce one provider-confirmed
  useful reply or expose the next reusable defect.
- `SMQ-20260813-01` — queued retained-context Front Door routing.
- `SMQ-20260813-03` — waits for controlled pilot prerequisites.
- `SMQ-20260813-04` — queued Meat shared-context reconciliation.
- `SMQ-20260813-05` — `deployed_waiting_genuine_payment` protected sales/payment visibility:
  one Supabase-backed preview/digest-confirm rail replaces direct payment-state
  mutation, partial receipts retain actual amount, and Telegram remains
  review-only. PR #946 is deployed at merge `5a414e6c`; one authenticated
  genuine unpaid-sale preview returned no confirmation action and exact
  unchanged Supabase readback. A genuine evidence-backed payment confirmation
  remains outstanding and must not be manufactured.
- `SMQ-20260813-06` — blocked by CORE Phase 0 replacement proof.

### BEACON

- `BMQ-20260813-00` — queued read-only current-truth reconciliation.
- `BMQ-20260813-01` — blocked existing-publication closeout.
- `BMQ-20260813-02` — `source-active` private album intake recovery,
  cross-referenced to completed BMQ-20260813-04. The 15 August four-photo
  provider album is recoverable and immutable incident evidence; GateKeeper
  routed it correctly, but Render lacked the BEACON activation configuration
  and the shared gateway let generic owner context run before typed media.
  Repair, reviewed release, bounded recovery and fresh deployed proof remain.
- `BMQ-20260813-03` — `deployed-awaiting-owner` private Library/public-use separation.
  It reuses the completed eight-photo Bella album and one canonical append-only
  media decision rail. Exact merge/schema/Render and authenticated eight-photo
  contact-sheet readback are proven; a genuine owner button/readback remains;
  the terminal must not manufacture the decision. BMQ-20260813-05 follows.
- `BMQ-20260813-04` — `business-complete`; deployed Oom Sakkie returned one
  current text-only awareness proposal exactly once with zero publication,
  spend, customer, farm, hardware, n8n or Sheets effect. Retain its identities
  as regression evidence; current private-media work belongs to BMQ-20260813-02.
- `BMQ-20260813-05` — queued protected publication/performance loop.

### CODEX UI

- `UIQ-20260813-01` — `production_complete`: PR #894 plus fidelity correction
  PR #896 are one reviewed mission release, deployed at `c0065fb3` as
  `dep-d9uv650ae00c738qh2ng`. CODEX UI terminal is released.
- `UIQ-20260813-02` — `isolated_implementation_cleared`: implement the approved
  presentation-only role/actionability contract in the clean isolated worktree,
  leaving the original dirty facelift files untouched; fresh owner preview is
  required before integration.
- `UIQ-20260813-03` — `production_complete`: PR #901 merged/deployed as
  `c86adba1`; genuine desktop/mobile rows show canonical names first, with
  meaningful tag and Pig ID fallbacks, deterministic date-first sorting and
  zero farm-data writes. Worktree clean and released-retain.
- All new facelift work remains queued until the active UI mission is released;
  no two terminals may edit the same UI files concurrently.

## Feedback ledger

Append a row for every terminal report. Never rewrite history to make a later
result appear known earlier.

| Date | Terminal / mission | Evidence and decision | Closeout / next action |
|---|---|---|---|
| 2026-08-15 | Control Tower idle-terminal dispatch failure | After summarizing live agents and terminals, Control Tower identified eligible queued HERDMASTER and SAM work but did not proactively surface the dispatches until Charl asked why the terminals remained idle. The mandatory sweep existed, so this was an execution failure rather than missing doctrine. | Add and enforce the all-terminal response closure gate. Dispatch eligible disjoint HERDMASTER and SAM missions; keep OOM SAKKIE dependency-idle until HERDMASTER supplies corrected lifecycle/materiality truth. |
| 2026-08-15 | BEACON `BMQ-20260813-04` owner strategy decision | Charl selected the non-availability farm-awareness campaign. Current evidence has demand cap zero, so BEACON must not claim available inventory, select sale stock or publish an availability offer. The alternative wording `wait for buyer demand` meant no proactive campaign until a genuine quantified SAM/customer demand signal existed; because no acquisition or measurement action was specified, it was passive and insufficiently explained, and Charl did not select it. | Remove `OWNER_HOLD` and return the operational outcome to `WORKING`. The deployed Oom Sakkie/BEACON path should prepare one owner-reviewable farm-awareness proposal that makes no availability claim and performs no publication, spend, customer send, reservation or farm write. A development terminal is assigned only if the deployed runtime cannot perform that approved next step. |
| 2026-08-13 | CORE `CMQ-20260813-02A` | Reversible watchdog window rolled back; synthetic receipt/reply passed; mission pickup failed through ID truncation. | Released; repair parser before another window. |
| 2026-08-13 | CORE `CMQ-20260813-02A` parser repair | PR #877 evidence merged as `8f8ec3b2`; PR #885 opaque mission-ID and creation-precedence repair merged/deployed as `7c22cd5f`; no Telegram proof or provider mutation occurred. | Parser development released; live proof remains unauthorized. Promote CMQ-03 read-only reconciliation. |
| 2026-08-13 | CORE `CMQ-20260813-03` discovery | PR #888 documentation at exact head `5f5aa641` passed all checks and merged as `c5f4c68d`. Application and OOM converge on Supabase events but do not share one atomic group contract; Sheets fallback authority remains. | Clear only a new pure preview-contract module and isolated tests; prohibit executor/fallback cutover. |
| 2026-08-13 | CORE `CMQ-20260813-03` preview contract | PR #890 exact head `37c95264`, base `e154a397`, is live-GitHub mergeable/clean with all three checks green. The module is pure and unwired; it normalizes application, OOM and prepared browser-voice preview bytes, preserves Unknown, requires confirmation and fails closed on invalid identity/state. | Authorize normal merge only; no production usefulness or adapter/executor cutover is claimed or cleared. |
| 2026-08-13 | CORE `CMQ-20260813-03` preview integration | PR #890 merged normally as `a9ad1d1a`; reviewed blobs are byte-identical and exact-merge validation passed. No adapter, executor, route, UI, database, fallback or production state changed. | Release the integrated worktree. Clear one disjoint source-only application preview-adapter slice; preserve its executor and every other channel. |
| 2026-08-13 | CORE `CMQ-20260813-03` application adapter | PR #893 exact head `988f62ac` adds the application-only preview adapter, controller call and tests; all gates and independent reviews pass. It is based on `07e2dbc8`, while main advanced via disjoint UIQ #894 to `9300ca3f`. No deployment or farm/provider effect exists yet. | Reconcile the same PR onto current main; after renewed exact-head evidence, integrate through the serialized lane and prove one fresh authenticated zero-effect production preview. |
| 2026-08-13 | CORE `CMQ-20260813-03` application preview proof | PR #893 merged/deployed as `de4122ab`. Two identical authenticated movement-only previews used current opaque pig/pen identities, returned canonical contract v1 and the same digest, required confirmation and left batches, rows, weight events, location events and protected claims unchanged; no executor/provider call occurred. | Application preview adapter is operational. Continue one adapter at a time with source-only OOM typed preview wiring; no executor cutover or Business completion claim. |
| 2026-08-13 | CORE `CMQ-20260813-03` OOM typed adapter ready | PR #897 exact head `14a93d44` on current main changes only the OOM typed preview boundary, tests and documentation. All CI and independent reviews pass; protected claims/execution remain byte-identical and no runtime/provider/farm mutation occurred. | Authorize normal integration/deployment plus one authenticated synthetic zero-effect equivalence proof; do not execute, confirm, send or alter fallbacks. |
| 2026-08-13 | CORE `CMQ-20260813-03` OOM typed adapter deployed | PR #897 merged as `69059933` and is loaded in successor `43b91712`. CORE made no production call because the real OOM boundary necessarily creates a protected claim and Telegram preview, so Control Tower's requested zero-claim/zero-send proof was internally contradictory. | Do not add a preview-only public bypass. Audit canonical preview compatibility with the existing protected executor; later genuine acceptance should allow exactly one claim and preview while still performing zero farm writes before confirmation. |
| 2026-08-13 | CORE `CMQ-20260813-03` claim/executor compatibility | PR #899 exact head `01d1631b` is reviewed with green checks and fixes a real preview-versus-claim payload/digest split, but provides no Business outcome and remains unmerged. Authoritative main advanced to `693c11f7` through ROOTLINE PR #900, overlapping `protected_action_runtime.py` and its tests; live GitHub mergeability is not presently proven clean. | Keep CMQ-03 and the existing CORE terminal active. Reconcile PR #899 non-destructively onto current main, preserve the ROOTLINE irrigation callback consumer, renew cross-domain tests/reviews, then integrate/deploy through the serialized lane only if both action families coexist. Do not start CMQ-05 Shadow work until this terminal is released. |
| 2026-08-13 | CORE `CMQ-20260813-03` integration completion | PR #899 reconciled head `bf604d5e` merged/deployed as `84601c83`; authenticated loaded-runtime truth matches the merge. Combined tests and four reviews prove exclusive ROOTLINE irrigation versus grouped-weight dispatch. No protected claim, Telegram, confirmation, executor, provider action or farm write occurred. | Release the clean CMQ-03 development worktree; retain CMQ-03 for genuine acceptance only. The visible CORE terminal is now eligible and must be dispatched to owner-approved CMQ-05 Phase A Shadow Control Tower. |
| 2026-08-13 | CORE Programme | PR #878 proved canonical Programme location and merged pointer/source-map correction as `29f04528`. | Released; SAM may resume existing mission. |
| 2026-08-13 | CORE `CMQ-20260813-05` Shadow Control Tower authorization | Owner approved learning from the current Control Tower method to reduce manual delegation without losing quality. Phase A must use the existing visible CORE development terminal and existing durable CORE runner/queue; it must not create hidden terminal fleets or gain dispatch/release/production authority. | Build source-only shadow observation/evaluation, then compare ten real feedback transactions. Current Control Tower remains sole dispatch authority; later promotion requires explicit owner approval. |
| 2026-08-13 | CORE `CMQ-20260813-05` Phase A module | PR #903 exact head `6a2ae24b` on current main `8e1ff519` is open, mergeable and green with architecture, security and operations GO reviews. Its five-file source-only scope is disabled by default, stores observe-tier proposals/comparisons in the existing operational-event fabric and proves zero dispatch/process/mission/provider/farm/release authority. It exposes no route, scheduler or runner caller, so no real shadow comparison can occur yet. | Integrate the safe disabled module normally. Continue the same mission with one authenticated observation-only input in the existing durable CORE runner, separately reviewed and unmerged; preserve human Control Tower as sole authority and do not manufacture any of the ten comparisons. |
| 2026-08-14 | CORE `CMQ-20260813-05` private observation input | PR #903 is merged/deployed as `fe0e6d3a`, flag absent and zero Shadow events. PR #906 exact head `ff641523` on current `1e6846d7` is mergeable/green and wires a sealed authenticated internal action through existing CORE private policy/runtime/tools. It rejects cross-mission/feedback and replay conflicts, counts distinct durable pairs, and adds no public route, scheduler, process, agent, queue, schema or authority. | Integrate/deploy #906, enable only the reviewed observation flag and prove runtime zero authority. Begin counting with the first later genuine feedback whose proposal is durably recorded before the human decision; this report is ineligible retroactively. |
| 2026-08-14 | CORE `CMQ-20260813-05` first Shadow attempt | Phase A private input is deployed/enabled, but the first genuine SHADOW READY proposal failed closed before persistence: authenticated mission lookup returned 404 because CMQ-05 was never created in canonical Supabase mission truth. Proposal/event IDs are null, event count remains zero and all authority counters remain zero. | This is not a comparison and must not be bypassed. Use the existing owner-approved canonical mission-creation action to create/reconcile exactly one CMQ-05 record, prove idempotent exact readback, then retry the same still-undecided feedback proposal. |
| 2026-08-14 | CORE `CMQ-20260813-05` canonical creator defect | Read-only reconciliation proved exact CMQ-05/alias rows zero and Shadow events zero. The authenticated `create_mission` boundary drops explicit `mission_id` before calling `record_mission()`, despite the store supporting opaque IDs; invoking it would create/reuse a `CHARLIE-MISSION-*` identity. CORE stopped with all counters zero and no source/runtime mutation. | Continue CMQ-05 and cross-reference CMQ-02A. Repair/test the canonical private action's explicit-ID forwarding and fail-closed authorization; no direct database insert or mission creation until reviewed deployment. |
| 2026-08-14 | CORE `CMQ-20260813-05` portfolio-baseline expansion | Owner approved a clean current portfolio epoch rather than repairing the legacy queue mission by mission. Historical execution status/evidence must be preserved while current eligibility is separately classified; findings remain parent inbox/tasks unless Control Tower promotes an independent outcome. Current, terminal and historical boards must derive from one canonical record. | Keep the creator repair first. Then create/admit only CMQ-05, produce a no-write unresolved-legacy/current-admission manifest for owner approval, enforce epoch filtering across runner/recovery/release paths, admit approved current missions, establish terminal leases, and only then begin ten genuine Shadow comparisons. No legacy mutation is authorized yet. |
| 2026-08-14 | Cross-terminal full-outcome enforcement | Owner confirmed that terminals must carry approved missions through user-like deployed acceptance rather than stopping at source, PR, commit, CI or deployment. Necessary safety, review, release, owner and external-event stops remain valid but must be explicitly classified and resumable. | Apply the universal lifecycle/Hold taxonomy to all subsequent feedback and CORE portfolio records. Require the compact feedback block, reject ambiguous `complete` wording, continue safe authorized stages automatically and reserve `BUSINESS_COMPLETE` for fresh owner-visible, canonical/provider and applicable physical proof. |
| 2026-08-14 | CODEX UI `UIQ-20260813-02` visual approval | Owner reviewed the bounded admin/read/empty/incomplete/failure previews and approved progression, while noting the sample did not show the full live dataset. Control Tower inspected all six screenshots and exact four-file diff at `60057958`; no visual, accessibility, authority or data-presentation defect was found. Preview samples prove states, not complete production data. | Reclassify from `OWNER_HOLD` to `WORKING`. Reconcile against the updated 670-line Standard and current main, push/open reviewed PR, run required CI, integrate/deploy, then authenticate production and prove the full live exposure payload, names and grouping match the UI; admin-only controls, read-role suppression, empty/incomplete/failure behavior and zero unintended writes must be verified before `BUSINESS_COMPLETE`. |
| 2026-08-14 | CORE `CMQ-20260813-05` opaque creator PR ready | PR #910 exact head `0811d775` on base/current main `8a4fb58c` changes seven creator/store/test/source-map files. It preserves approved opaque IDs end to end, rejects malformed/multiple/alias/substituted/conflicting identities, gives exact-ID replay precedence, retains legacy generated IDs and proves exact-versus-legacy concurrency convergence. All required CI and architecture/security/operations reviews pass; zero canonical or Shadow rows were created. | Authorize normal integration/deployment and loaded fail-closed proof only. Do not create CMQ-05 in this step. After exact deployed evidence, issue the separate create/admit plus no-write Portfolio Baseline Manifest prompt. |
| 2026-08-14 | CORE `CMQ-20260813-05` opaque creator deployed | PR #910 exact reviewed head `0811d775` merged/deployed as `9fb4c830`; loaded revision truth matches, required CI/reviews are green and negative private-action probes fail before store access. Exact/alias CMQ-05 rows, Shadow events and comparisons remain zero; all authority counters remain zero. Normalized lifecycle state is `WORKING`, not complete. | Hold the first canonical write until owner-approved lifecycle/portfolio doctrine in PR #886 is reconciled into authoritative main. Then create/admit exactly one CMQ-05 and produce the no-write Portfolio Baseline Manifest; preserve zero Shadow scoring and zero legacy mutation. |
| 2026-08-14 | CORE `CMQ-20260813-05` governance-digest correction | CORE correctly failed closed because Control Tower supplied pre-merge working-tree SHA `385345...` as a required authoritative identity. Fresh authoritative worktree `598cb3d8` proves tracked blob `599beca2`, Windows filesystem SHA `3BD86DE1FB8397345D92AFB68B75985F1EE334478CBA5719EB8224C9833F32C5`, 670 lines; Runtime Programme remains blob `3b3b1279`, SHA `BDE098...1EBDF`, 189 lines. Zero canonical/Shadow/legacy/provider/farm mutations occurred. | Correct the Hold from `OWNER_HOLD` to `WORKING`; this was Control Tower metadata correction, not owner authority. Send an ADDENDUM to the same CORE terminal to continue exact CMQ-05 creation/admission and the no-write manifest without restarting the mission. |
| 2026-08-14 | CORE `CMQ-20260813-05` atomic admission boundary | CORE correctly stopped before creating a legacy-shaped exact-ID row: the deployed creator does not atomically persist epoch, classification, lifecycle or sole-human authority, and scheduling does not yet enforce epoch eligibility. Zero mission, Shadow, legacy, runner, provider or farm mutations occurred. The plan wording also blurred the owner-approved CMQ-05 bootstrap admission with later manifest-proposed admissions. | Keep lifecycle `WORKING`, not `OWNER_HOLD`. Correct the plan to allow only the already-approved atomic CMQ-05 bootstrap; implement/review/deploy the smallest canonical create-and-admit contract, create/read back exactly one CMQ-05 without scheduling activation, then produce the no-write manifest. Charl approval remains required before all other classifications/admissions. |
| 2026-08-14 | CORE `CMQ-20260813-05` legacy classification approval | Charl approved the complete 86-row legacy classification only: 49 recovery fragments, 19 test-evidence records, 11 superseded records and 7 historical records after explicitly correcting the order-stream row to historical. No current candidate admission was approved. UIQ-02 is excluded as BUSINESS_COMPLETE; RMQ-04 remains systemic WORKING with no retry before its full gate; HMQ-05 is EXTERNAL_HOLD for the next natural provider-confirmed brief. | Apply one sealed exact-baseline/exact-set atomic classification, preserve all historical status/evidence/timestamps, keep every legacy row non-runnable and replay no-op, and prove no additional admission, Shadow, dispatch, provider or farm effect. CMQ-05 remains WORKING and non-runnable. |
| 2026-08-13 | HERDMASTER `HMQ-20260813-03` | Candidate passed pre-advance gates; main advanced; no merge/deploy. | Preserve and reconcile non-destructively. |
| 2026-08-13 | HERDMASTER `HMQ-20260813-03` completion | PR #884 merged as `b7c0edcf` and production/browser readback proved Bonnie proposal wording, three exact recovery holds, five unchanged exposures/cycles and zero writes on repeated reads. | Development worktree clean released-retain; promote HMQ-02. |
| 2026-08-13 | HERDMASTER `HMQ-20260813-02` completion | PR #889 merged/deployed as `e154a397`. Production proved exact anonymous HTML login redirect and return, authenticated Breeding Attention rendering, retained API-style JSON denial, hostile-next containment and unchanged farm tables; NEXT_STEPS, source map and changelog were reconciled in the merge. | Mission closed; terminal released-retain. Reconcile HMQ-04 scope and file ownership before any new dispatch. |
| 2026-08-13 | HERDMASTER `HMQ-20260813-04` breeding intelligence handover | Live herd/detail analytics are read-only but table-led, name-secondary and limited to mating/litter association; missing weaned data may appear as zero and sample size, trends, family, health, growth, observations and financial evidence are not interpreted. Existing PR #823 has four unique commits but is 239 commits behind main; its two retained worktrees are clean. | Reconcile read-only and produce one authoritative data/UX contract before backend or CODEX UI implementation. Preserve Unknown, distinguish association from causation and create no competing ledger. |
| 2026-08-13 | HERDMASTER `HMQ-20260813-04` full-lifecycle contract | PR #902 exact head `f831288d` on current main `693c11f7` is open, mergeable and green. Three independent reviews approve the documentation-only evidence/UX contract; it defines available, derived, partial and prohibited evidence, nullable metrics, deterministic confidence and strict HERDMASTER/CODEX UI ownership. No source runtime, UI, configuration or farm data changed. | Integrate the contract normally. Continue the same HERDMASTER mission with one isolated read-only backend snapshot/composer implementation; no UI assignment, competing ledger, mutation or production-completion claim. |
| 2026-08-13 | HERDMASTER `HMQ-20260813-04` backend composer ready | PR #905 exact head `130741df` on base `fe0e6d3a` adds six backend/test files only: a single-connection repeatable-read evidence snapshot, versioned herd/named-animal composer and owner-protected JSON routes. Unknowns, denominators, correction lineage, names-first identity and non-causation are preserved; all CI and two independent reviews pass. Current main `406a6851` advanced only in ROOTLINE telemetry files. | Reconcile/integrate normally, deploy, and prove authenticated genuine herd/profile readback with `writes_performed:false` and unchanged canonical tables. Do not assign CODEX UI until this read contract is loaded and verified. |
| 2026-08-14 | HERDMASTER `HMQ-20260813-04` backend production proof | PR #905 reconciled head `e9a39ee1` merged/deployed exactly as `1e6846d7`. Twice-repeated authenticated herd and Tyson profile reads were semantically stable with `writes_performed:false`; genuine denominators, correction lineage, Limited confidence, explicit non-causation and nullable growth/finance limitations were present. Eight canonical table counts were unchanged. | Release HERDMASTER development worktree retained-clean. Keep HMQ-04 open for owner-facing pages; queue its CODEX UI slice behind existing UIQ-02 so one visible UI terminal never owns two active missions. |
| 2026-08-13 | ROOTLINE `RMQ-20260813-02` | PR #875/#876 live; provider safety eligible; card `3480` updated; zero controls. | Pending protected physical journey. |
| 2026-08-13 | ROOTLINE gateway incident | Telegram `3579` retained by n8n but relay received HTTP 403 before parsing/Supabase; presence expired; zero controls. | Repair end to end; no owner repetition. |
| 2026-08-13 | ROOTLINE `RMQ-20260813-04` water evidence | Readiness held because 11 August storage evidence was stale. Charl then sent fresh `Reservoir 4/4` and `Storage tanks 3/4`, but read-only trace found no new canonical Supabase receipt; Telegram showed zero pending/error backlog. | Treat as the same systemic intake incident. Recover durable provider receipt if possible; do not request another owner message. |
| 2026-08-13 | ROOTLINE shared Telegram intake repair | PR #887 merged as `e3c723aa`; dedicated gateway authentication and durable owner binding restored. Original reservoir/storage update recovered exactly once into Supabase with silent replay; zero controls. | Intake incident technically closed; B/C remains held on separate authority/lifecycle blockers. |
| 2026-08-13 | ROOTLINE `RMQ-20260813-04` acceptance correction | Control Tower rejected treating the next action as another generic Valve B commissioning test. Prior B/C physical commissioning is retained. Irrigation longer than the 3,599-second native fail-stop legitimately needs multiple intentional segments; this must be represented as one durable job with explicit segment identity, expected OFF/re-arm transitions and cumulative delivered runtime, while unrelated retries/replays remain no-ops. | ROOTLINE Terminal must first reconcile and repair the software contract read-only/source-first. Do not actuate B/C or ask Charl to travel until a reviewed deployed preview proves the intended job/segment boundary. |
| 2026-08-13 | ROOTLINE `RMQ-20260813-04` PR #891 review | Historical evidence proves B had two separate intentional legacy executions of 59.9833 minutes each and C one separate 59.9833-minute execution; history remains unchanged. PR #891 adds job/segment fields and pure tests, with all live CI gates green and zero controls, but default eligibility still reduces ordinary plans to one segment and calls projection with empty history, preventing demonstrated durable segment-2 continuation. | Keep the same mission and PR unmerged. Correct the requested-total and persisted-event boundary, add disposable-PostgreSQL concurrency/restart proof and independent exact-head safety review; no owner repetition or physical recommissioning. |
| 2026-08-13 | ROOTLINE `RMQ-20260813-04` PR #891 corrected | Exact head `6c81edd6` preserves the canonical 7,200-second target, derives two bounded segments, uses Supabase history, requires fresh OFF/fail-stop evidence between segments and proves atomic claim/replay behavior. All CI and independent reviews pass; zero controls. Main subsequently advanced via file-disjoint CORE PR #893 to `de4122ab`. | Reconcile once onto current main, then merge/deploy and perform non-actuating loaded-runtime proof. Present one protected B acceptance preview only after current safety/authority passes; do not recommission or actuate without fresh owner confirmation. |
| 2026-08-13 | ROOTLINE `RMQ-20260813-04` deployed readiness | PR #891 merged as `86e11bc` and deployed live. B is currently eligible for a stable two-segment job; Supabase history is empty for it, controller/all channels are OFF, native fail-stops are 3,599 seconds and autonomy remains disabled. No preview was sent because protected callbacks support grouped weights, breeding and mortality but no irrigation consumer. | Build one irrigation-specific protected confirmation consumer on the existing claim/runtime spine. Do not show a dead button or actuate before a fresh exact owner confirmation. |
| 2026-08-13 | ROOTLINE `RMQ-20260813-04` protected confirmation failure | PR #900 deployed the irrigation consumer and delivered exactly one digest-bound B/CH1 segment-1 preview as Telegram message `3586`. Charl then pressed `Bevestig` and observed nothing happen. The terminal report was produced before that press; callback receipt, claim transition, execution dispatch, provider control and physical state after the press are therefore unverified. | Treat as genuine failed acceptance in the same mission. Do not request another press or operate B. Retain and correlate update/callback identity, gateway/runtime logs, Supabase claim/job events and controller state; repair the first systemic boundary that failed, preserving replay safety. |
| 2026-08-14 | ROOTLINE `RMQ-20260813-04` callback repair | Trace correlated Telegram update `549158268`, card `3586`, n8n execution `64234` and the exact Supabase receipt. Authentication/binding/claim succeeded; volatile eWeLink readback digests caused false `protected_irrigation_eligibility_changed` containment before coordinator dispatch. PR #904 merged as `406a6851` and is deployed in `1e6846d7`; old claim is non-replayable, current controller safety passes and zero controls occurred. | Do not reuse the old card. Retain the mission until one fresh presence-bound preview and genuine confirmation produce provider-confirmed execution plus physical evidence. Ask for owner presence once, only after current eligibility is ready. |
| 2026-08-14 | ROOTLINE `RMQ-20260813-04` fresh readiness | Current B job/segment passes canonical water, dry weather, two-day debt and provider safety; B/all channels are OFF, fail-stop is 3,599 seconds, no current claim or execution exists and zero controls occurred. Old card `3586` remains contained. | Development terminal released/waiting. The sole blocker is explicit current physical presence; then issue one new short-lived preview and observe rather than manufacture the acceptance journey. |
| 2026-08-14 | ROOTLINE `RMQ-20260813-04` card-lifecycle repair | PR #907 reviewed head `7eb4297c` merged/deployed as `d527a560`; all checks pass. The change isolates each digest-bound preview, claim and completion under one Telegram card identity and contains active claims when delivery/card binding is unproven. Current controller readback is safe/OFF and zero controls occurred. The terminal report omitted required governance HEAD/blob/SHA/line/read evidence, and earlier owner presence expired during repair. | Do not claim the Standard was applied or request actuation yet. Require an addendum governance preflight and exact correction summary; then wait for a fresh current presence statement before one new card. |
| 2026-08-14 | ROOTLINE `RMQ-20260813-04` governance addendum | At `d527a560`, Standard blob `a2e17a43`/SHA `C250E625...AA56D`/603 and Programme blob `3b3b1279`/SHA `BDE098D5...1EBDF`/189 were tracked, blob-identical and completely read. Exact PR-907 binding/containment/replay behavior was documented; fresh provider readback showed controller online, B/all channels OFF, fail-stop 3,599 seconds, no execution/consumption and zero controls. | Governance blocker closed. Development terminal released; wait only for one new explicit current presence statement, then one new digest-scoped card and supervised physical proof. |
| 2026-08-14 | ROOTLINE `RMQ-20260813-04` card `3590` failed acceptance | Charl confirmed once on newly digest-scoped card `3590`. Authentication, exact binding, active-to-executing claim and eligible segment-1 decision succeeded; coordinator then blocked on Supabase `load_active` until Gunicorn killed the worker. It stopped before execution ownership, B ON, provider receipt, flow, consumption or runtime accounting. Claim was durably contained; 09:19 provider readback proved all OFF and zero controls. | Do not request another press or presence statement. Preserve `3590` and repair the coordinator/history database timeout with bounded failure and worker survival before any new physical attempt. The terminal handover must repeat full governance verification because this report omitted it. |
| 2026-08-13 | OOM SAKKIE/HERDMASTER Pig 002 intake | Genuine Pig 002 not-eating report was accepted upstream but rejected before parsing under the pre-#887 identity split; no reply, preview or write exists. Gateway is repaired, but the owner-approved natural health/loss workflow remains inactive. | Preserve report as failed-acceptance evidence; begin zero-I/O interpreter/preview slice without replay or farm write. |
| 2026-08-13 | OOM SAKKIE health/loss governance stop | OOM's clean retained worktree stopped before implementation because `HERDMASTER_NATURAL_HEALTH_AND_LOSS_INTAKE_WORKFLOW.md` is absent from authoritative main. Historical commit `d78f1e02` labels it owner-approved; Charl's current handover explicitly reaffirms the same existing mission and canonical workflow. Current main already contains the evaluator, tests, preview adapter, runtime and source handover, so copying the historical document unchanged would also be stale. | Reconcile the workflow documentation-only against current implementation and preserve its non-activation/protected-write boundaries; then repeat preflight and audit existing stage 1 without duplicate implementation. |
| 2026-08-13 | OOM SAKKIE `OOM-INTAKE-SLICE-1` source ready | Workflow PR #892 merged as `07e2dbc8`. Source-only PR #895 exact head `b293a279` has green CI and independent welfare/security passes; it preserves Pig 002 facts and Maya attribution with zero I/O. Current main advanced through disjoint UI PR #894 to `9300ca3f`; no runtime, provider or farm effect exists. | Reconcile the same PR onto current main and integrate only after repeated exact-head evidence; keep the outcome mission active for later genuine end-to-end proof. |
| 2026-08-13 | OOM SAKKIE `OOM-INTAKE-SLICE-1` Stage 1 integrated | PR #895 reconciled and merged normally as `6fd4d271`; 146 focused and 164 proportional tests, exact reviewed blobs and dual welfare/security reviews passed. No deployment/configuration/provider/farm effect was claimed. | Release Stage 1 worktree. Continue the same mission with Stage 2 authenticated routing, canonical evidence and deployed readiness; do not replay the historical Pig 002 update. |
| 2026-08-13 | OOM SAKKIE health/loss Stage 2 readiness | PR #898 merged/deployed as `43b91712`. Production found one exact current tag-002 match with canonical chronology; authenticated owner, gateway, Telegram webhook, Supabase and database configuration were present. An isolated synthetic request traversed the real handler and produced the welfare question while delivery was withheld, with zero farm/protected effects and zero synthetic lifecycle rows. | Development terminal released-retain. Send nothing and let the deployed runtime handle the next genuine report; retain the mission until provider delivery and later confirmed canonical readback succeed. |
| 2026-08-13 | OOM SAKKIE `OMQ-20260813-02` | No 13 August production morning trigger; PR #879 later integrated one Render-owned clock and synthetic non-actuating family. | Prove provider configuration and synthetic result; genuine clock proof still pending. |
| 2026-08-13 | ROOTLINE/OOM SAKKIE morning readiness | Provider verified exactly one enabled 06:45 SAST Render scheduler; a later duplicate was suspended. No genuine daily invocation, hardware action or authority change occurred. | Run one isolated non-actuating synthetic acceptance, then await genuine clock. |
| 2026-08-13 | ROOTLINE/OOM SAKKIE synthetic acceptance | Exactly one deployed-entry invocation, one separate Supabase claim and one provider-confirmed `ROOTLINE SCHEDULE TEST` send; eight direct/concurrent/post-restart replays were silent; genuine daily lifecycle unchanged; zero farm/hardware/provider-control effects. | Synthetic acceptance complete. Send nothing until post-07:00 genuine-event audit. |
| 2026-08-13 | OOM SAKKIE duplicate feedback | The same synthetic-acceptance evidence was submitted again with no newer event or changed evidence. | No status change, no duplicate mission, no repeat test and no new prompt. |
| 2026-08-14 | OOM SAKKIE `OMQ-20260813-03` genuine contextual failure | Morning brief `3587` was physically received. Charl's natural reply `3588` passed Telegram/GateKeeper, but relay `64316` received HTTP 500 after the Render worker blocked on Supabase/psycopg and timed out. No acknowledgement, durable three-fact retention or ROOTLINE continuation is proven; recurring reassess/schedule timeouts and OMQ-02 provider-ambiguous delivery are related evidence. Zero hardware commands occurred. | Continue OMQ-03 and cross-reference OMQ-02. Do not replay/resend the reply. Repair the bounded contextual load/degraded-database boundary, reconcile message-3587 delivery truth and prove exactly one non-actuating canary acknowledgement/retention/ROOTLINE supply. |
| 2026-08-14 | OOM SAKKIE `OMQ-20260813-03` bounded repair proof | PR #908 merged/deployed as `8a4fb58c`. One labelled synthetic contextual canary durably produced one manager receipt, one ROOTLINE observation receipt and one delivered family lifecycle, with three facts reaching ROOTLINE; direct/two concurrent replays were silent, database-unavailable tests degraded without retention/action and all farm/hardware/provider-control counters were zero. Historical `3587`/`3588` were untouched. | Development worktree released-retain. Send nothing and retain OMQ-03 for the next genuine contextual owner reply; synthetic proof is not Business completion. OMQ-02 remains cross-referenced for historical delivery-truth reconciliation. |
| 2026-08-14 | OOM SAKKIE `OMQ-20260813-03` no-event closeout | Terminal repeated complete governance verification at `8a4fb58c`; no genuine contextual reply arrived and no polling, message, replay, synthetic event or mutation occurred. Worktree is clean, merged and released-retain; development terminal is not the runtime. | No status change and no duplicate prompt/test. Keep terminal released and let the deployed runtime own the next natural reply; resume read-only correlation only when genuine evidence exists. |
| 2026-08-13 | SAM `SMQ-20260813-02` | Conversations `1533`/`2143` produced safe unsent replies and non-actionable cards; defect traced. | Continue bounded correction; no historical sends. |
| 2026-08-13 | SAM `SMQ-20260813-02` integration | PR #882 merged as `b36b2ca3`; successor `6d7f3259` is live. WhatsApp timestamp binding, WebWidget authority and safe first-event routing are corrected; historical conversations were untouched. | Development released; send nothing and observe next genuine inbound. |
| 2026-08-13 | CODEX UI `UIQ-20260813-01` | Dedicated UI terminal launched; preserved dirty `/matings` files exist in the original workspace; prompt prepared but not yet acknowledged. | Deliver one reconciliation/local-preview mission; no deployment yet. |
| 2026-08-13 | CODEX UI `UIQ-20260813-01` production completion | PR #894 merged as `9300ca3f`; production-fidelity correction PR #896 merged as deployed revision `c0065fb3`, deployment `dep-d9uv650ae00c738qh2ng`. Both PRs are retained as one mission release. | Mark UIQ-01 production-complete and release the UI terminal; do not assign another UI mission until explicit Control Tower promotion. |
| 2026-08-13 | CODEX UI `UIQ-20260813-03` expected-farrowing identity | Live `/verwagte-jongdatums` uses `sow_tag_number || sow_pig_id` and `boar_tag_number || boar_pig_id`, ignoring the already deployed owner-facing name fields. Current main read model supplies separate `sow_name` and `boar_name`; the target JS file is outside preserved dirty `/matings` work. | Assign the released CODEX UI terminal one isolated page-only correction and authenticated live proof. Do not reopen HERDMASTER backend missions or combine UIQ-02. |
| 2026-08-13 | CODEX UI `UIQ-20260813-03` production completion | PR #901 reviewed head `44e99b5d` merged/deployed as `c86adba1`. Authenticated 1440x1000 and 390x844 production proof showed nine genuine active expected-farrowing rows names-first with exact API/order agreement; three repeated reads left pigs 301, matings 20, exposures 5 and litters 25 unchanged. | Mark Business complete and release the clean isolated worktree. Promote queued UIQ-02 to read-only reconciliation only; keep HMQ-04 backend intelligence separate. |
| 2026-08-14 | CODEX UI `UIQ-20260813-02` reconciliation | Current `/matings` has no generic protected heading and hides the workspace on successful empty data. Five genuine active exposures are complete, but preserved production evidence shows read-role access beside an admin-only UIT action. Target files in the original workspace are dirty earlier facelift/preview work (`56397897` lineage plus uncommitted template state) and were preserved; the isolated UIQ-02 worktree is clean at deployed main. | Clear presentation-only implementation in the isolated UIQ-02 worktree. Preserve original dirty files and all backend authority. Require fresh local desktop/mobile previews for admin, read, empty, incomplete/loading/failure states and owner approval before merge/deploy. |

## New owner findings

| 2026-08-20 | CORE `CMQ-20260813-05` canonical validation-receipt repair | The preserved current-main worktree replaces the permissive hand-shaped v1 staging receipt with a canonical signed v2 producer/validator. Exact source, mandatory focused/proportional suite evidence and strict isolation properties are bound. Passed/rejected evidence shares one create-once state-root identity; staging claims a passed identity durably before mutation, so rejection, interruption and replay remain non-retryable. Focused and proportional source tests pass. No key provisioning, receipt issuance for runtime, staging, Task Scheduler, activation, deployment or business effect occurred. | Keep lifecycle `REVIEW_HOLD` after one exact-head PR is opened. Require independent architecture/security/release-integrity review, Brain Guard and exact-head CI; stop before merge, staging or activation. Resume only through a fresh serialized release decision. |

| 2026-08-16 | CONTROL TOWER `AUTONOMY_RECOVERY_MODE` | Charl reported that individually governed fixes and terminal feedback were accumulating while his daily relay, tracking and approval workload was not declining. The prior protocol enforced mission safety, freshness and all-terminal eligibility but did not cap global implementation WIP, measure owner labour or require each dispatch to advance terminal-independent deployed operation. Its all-terminal sweep could therefore bias Control Tower toward keeping eligible terminals busy. | Activate `AUTONOMY_RECOVERY_MODE` immediately. Maximum three implementation tracks: Slot 1 CORE durable mission delivery/supervision and safe runner ownership; Slot 2 shared OOM SAKKIE/ROOTLINE canonical actor, protected-action and reusable device-commissioning spine, including Anton parity; Slot 3 SAM narrow genuine customer-response operating proof. ROOTLINE deployed physical proof does not consume a separate slot, but any reusable ROOTLINE/OOM repair belongs to Slot 2 rather than opening a fourth track. Freeze BEACON, DOCUMENTS, HERDMASTER expansion and CODEX UI implementation at their preserved checkpoints; accept feedback for preservation/containment only unless it proves a direct blocker to Slots 1-3. Every dispatch must state the owner step removed and terminal-independent acceptance proof. Exit only after CORE removes prompt relay, OOM/ROOTLINE complete one non-owner-aliased protected journey using the reusable action/commissioning spine, one specialist completes a genuine deployed cycle and owner-relay burden is measurably lower. No new feature mission may displace these outcomes. |

| 2026-08-16 | CORE `CMQ-20260813-05` runner-control process-boundary containment and isolated validation | Two CORE Codex sessions exited while runner-control tests were invoked, so repeat in-terminal validation was prohibited. CORE preserved WIP `11566d27`, reconciled governance/current source, and committed signed exact-tree termination containment as `bae3bdaa`: signature/digest/member/generation/revision/mode/nonce/live-identity binding, current/ancestor/protected-process rejection and fail-closed Popen containment. Control Tower then ran validation in disposable Docker image `core-runner-validator:20260816`, network disabled, read-only source mount, tmpfs only and no host CORE/Codex/supervisor/relay visibility. Six focused tests passed. The full 56-test runner-control suite failed safely with two source/test regressions and three skips: missing `descendant_pids` in `test_exited_launcher_still_contains_and_verifies_captured_descendant`, and a decorator/signature arity mismatch in `test_governed_stop_handles_current_supervisor_before_runner_spawn`. No host or production process was targeted or mutated. | Keep mission `WORKING / VALIDATION_FAILED_SAFE`. Return the released CORE development terminal to the same clean branch for static correction only; it must not run runner/process-control tests inside Codex. Correct the two exact regressions without weakening signed-tree authority, checkpoint, and hand back to Control Tower. Control Tower reruns focused and full suites only in disposable isolation. No merge/deploy/runtime restart until all isolated tests pass, independent process-safety review approves exact head, current main is reconciled and a separate production release is authorized. The two terminal exits remain immutable systemic evidence; no owner repetition. |

| 2026-08-16 | OOM SAKKIE Anton `farm_manager` Telegram channel parity defect | GENERAL's read-only finding is partly contradicted by current main: `oom_sakkie_family_access_v1`, Anton's activated `farm_manager` binding, `family_runtime`, specialist adapters and `rootline_delegated_principal.v1` already exist. However, a real split-path defect remains. `telegram_direct.py` sends ordinary allowlisted text to `telegram_read_only` without binding the family principal, and its generic protected callback path rejects every non-owner before delegated-action evaluation. The authenticated gateway does resolve family policy and contains specialist/farm-manager routes, so a flat allowlist is not the sole authority model; ingress parity and callback delegation are the missing integration. The exact failed Anton exchange remains Unknown and must be traced before mutation. | Register one OOM SAKKIE integration mission, not a second actor registry: `OMQ-20260816-ANTON-FARM-MANAGER-CHANNEL`, intended worktree `C:\tmp\oom-anton-farm-manager-channel-20260816` from current main. First trace Anton's exact recent provider exchange read-only and produce a Charl/Anton capability matrix for direct and gateway paths. Then make every authenticated Telegram/voice ingress resolve the same existing canonical principal before routing; preserve Afrikaans, actor attribution, exact permissions, previews, idempotency and domain-owned action contracts. Never alias Anton to Charl or enable ambient writes/physical controls. Only explicitly delegated existing actions may reach protected callbacks; owner/development/secrets/roles/commissioning and unapproved hardware remain owner-only. Prove one non-actuating status/read path, one attributable observation preparation/confirmation, and one existing ROOTLINE delegated start/continue preview/callback locally; production physical acceptance waits for a fresh natural eligible Anton action. No new n8n/Sheets authority and no broad flag flip. OOM terminal is currently `SEND NOW`; stale morning-process existence is not active work. |

| 2026-08-16 | BEACON `BMQ-20260813-05` canonical text-only Facebook organic publication class | BEACON completed current governance reconciliation on clean head `46fe8475`, three commits ahead/zero behind main `4c12069d`, and correctly contained the disconnected adapter. Nineteen canonical publication tests passed; architecture/security/commercial reviews confirmed the existing organic binding is media-specific and requires at least one approved asset plus `owner_confirmed_subject`. The proven BMQ-04 proposal is text-only, and no reviewed text-only binding exists. No runtime/provider/owner-visible effect occurred. Waiting indefinitely for media would leave a legitimate organic Facebook capability missing and would not satisfy the owner-visible mission. | Control Tower authorizes source design of one distinct canonical text-only Facebook organic review/publication class inside BMQ-05; this grants no publication authority. Reuse the existing weekly decision, immutable binding, approval, execution-identity, provider-receipt and performance spine; require exact page/channel/caption/locale/evidence boundary/SAM routing/digest/expiry and `media=[]`, forbid media claims, spend, scheduling and customer commitments, and keep approval separate from provider execution according to the existing protected lifecycle. The active BEACON terminal receives an addendum now, must use the current handover template, obtain independent reviews, open a source-only PR and stop before merge/deploy/owner decision. Existing historical BEACON PRs are evidence-only and may not be revived as authority. |

| 2026-08-16 | HERDMASTER `HMQ-20260813-04` identity enrichment and CODEX UI release gate | PR #984 head `4cc8c07e` adds six ordered Tyson mating rows, separately labelled four-partner aggregates, canonical operational fields for all 37 offspring, deterministic Unknown/conflicting attribution and a stable semantic digest; focused/PostgreSQL tests, required CI and three independent reviews passed with zero farm writes. The technical contract is strong, but feedback verified superseded Standard blob `57a3839...`, omitted the mandatory Protocol/template and is no longer current: the branch is five commits ahead/four behind main `4c12069d`, with real overlap in its contract/backend/tests plus current governance. Meanwhile the existing CODEX UI worktree has fresh commit `b936a1e8` and preserved untracked `output/`; it is active work and must not be interrupted or duplicated. | Keep HMQ-04 `WORKING / SOURCE_RECONCILIATION_REQUIRED`; do not release UI from the stale PR head. Send the released HERDMASTER terminal to the same clean worktree to reconcile current main non-destructively, repeat current Standard/Protocol/Programme/template verification, resolve the overlapping backend/contract/tests, rerun exact-head evidence and update PR #984. Preserve CODEX UI's fresh branch/output and send it no prompt while active. Automatic UI promotion occurs only after HERDMASTER supplies a current exact packet digest/head and PR checks; then CODEX UI reconciles its existing work rather than starting another implementation. No merge, deploy, farm write or owner preview yet. |

| 2026-08-16 | SAM always-on Livestock `one_clarification` authority decision packet | SAM produced a bounded seven-day `sam_livestock_one_clarification_v1` proposal: only a neutral acknowledgement plus one deterministic missing-customer-fact question, with exact identity/chronology/evidence/authority binding, one provider attempt, durable claim, no retry on ambiguity, retained language/context and broad protected/commercial exclusions. Commercial-safety and security reviews found it correct after incorporated corrections. No dispatch, authority event, configuration, customer/provider call or production mutation occurred; deployed operation remains shadow-only. However, the terminal verified old main `3d0bd01d` and superseded Standard blob `57a3839...`, omitted the mandatory Protocol/template, and is now six commits behind current main `4c12069d`; therefore `OWNER_HOLD / EXACT_AUTHORITY_DECISION_READY` is premature. | Preserve the exact envelope as review evidence but return the same released SAM terminal to `C:\tmp\sam-always-on-inbox-loop` for current-lineage governance reconciliation and a refreshed no-write authority readback. Require the current 986-line Standard, Protocol, canonical Programme and feedback template; inspect intervening governance/ROOTLINE changes and open SAM PR collisions without touching retained worktrees. If the envelope and authority facts remain byte/semantically unchanged, return one current template packet and only then request Charl's Approve/Correct/Decline decision. Do not implement source, create authority, enable gates, deploy or send. Mission remains `WORKING / GOVERNANCE_RECONCILIATION_REQUIRED`; shadow loop remains authority-disabled. |

| 2026-08-16 | DOCUMENTS Mission 1 canonical catalogue source foundation | DOCUMENTS produced clean unique commit `107b4f0ff4a8a6c6e13ab5ba8707d63fb271b5c9` in `C:\tmp\documents-catalogue-20260816`, adding only the catalogue contract, focused tests and ownership map. Twenty-one tests passed and independent document/security reviews approved the bounded no-runtime foundation. No generator, route, persistence, delivery, scheduler, printer, provider or farm effect occurred. The branch is now one commit ahead and six behind current main `4c12069d`; its feedback verified the superseded Standard blob `57a3839...` and omitted the mandatory Control Tower protocol/template, so governance is stale even though the unique source is preserved. | Keep Mission 1 `WORKING / SOURCE_RECONCILIATION_REQUIRED`. Send the released DOCUMENTS terminal back to the same worktree to fetch and non-destructively reconcile current main, repeat the current Standard/Protocol/Programme/template preflight, rerun proportional tests/reviews, push the unique commit and open a bounded implementation PR. Do not begin Mission 2 until Mission 1 is integrated and current-lineage verified. Mission 2 remains the weekly-weight PDF/Telegram preparation journey with OOM SAKKIE integration and HERDMASTER data authority; no second generator, ledger, n8n/Sheets authority, direct print or production delivery. Charl must paste the prepared continuation once; no business decision or physical input is needed. |

| 2026-08-16 | BEACON `BMQ-20260813-05` protected publication/performance reconciliation | BEACON reported fresh progress in `C:\tmp\beacon-bmq-20260813-05-publication-performance-20260816`: one modified runtime adapter plus three unique untracked source/test/handover files, five focused tests passing and no provider/publication/spend/farm effect. Independent review correctly stopped a PR because the draft translation does not exactly match the canonical weekly-review/publication binding, the existing organic binding requires approved media plus `owner_confirmed_subject` and cannot silently authorize BMQ-04's text-only proposal, and media preview evidence lacks the required authenticated contact-sheet reconciliation. The worktree is four commits behind authoritative main and verified the superseded 976-line Standard, so its source evidence is preserved but its governance receipt is stale. | Keep the same mission `WORKING`, not `OWNER_HOLD`. Classify the terminal `ADDENDUM - ACTIVE TERMINAL`; preserve all dirty/unique bytes, reconcile non-destructively to current main, repeat the current 986-line Standard, Protocol, canonical Programme and feedback-template verification, then align the implementation to one canonical publication spine. Do not weaken media authority or smuggle text-only publication through the media binding: either use an already-authorized distinct text-only class or report the exact missing authority as a blocker. Media-bearing previews must bind authenticated contact-sheet inspection and exact approved-media evidence. No PR, deployment or owner decision until focused tests and exact preview reconciliation pass. Charl should paste the prepared addendum once; the target must return `CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md`. |

| 2026-08-16 | ROOTLINE Mixer commissioning readiness and B-parent containment | PRs #1008/#1012 repaired fertilizer-presence routing and visible-notice lifecycle; deployed ROOTLINE delivered one expired-presence notice bound to Telegram receipt 3667 with zero card/control/hardware effect. PR #1013 merged/deployed as `9f2970ba` and canonically cancelled B parent `ROOTLINE-IRRIGATION-JOB-E4700EC1D1F52AF72744C3F9F5`: 7,198 unverified seconds, zero runtime/water credit and fresh OFF evidence. C's verified first segment and 3,599-second remaining objective are preserved; current aggregation remains bounded-timeout fail-closed. Mixer `100204d497` CH2 is provider-online/OFF with 300-second native fail-OFF; Injection and Borehole MINI R4 remain disabled. Serialized lane released normally. | Mission remains `WORKING / OWNER_HOLD` for one fresh physical-presence statement followed by the deployed Oom Sakkie/ROOTLINE protected Mixer card, one bounded five-minute attempt, physical recirculation and pump-stop observations, provider-confirmed OFF and canonical commissioning evidence. Charl's current statement that he is ready to observe is fresh presence context, not permission for a development terminal to generate the card or operate hardware. Development worktree `C:\tmp\rootline-borehole-mini-r4-intake-20260816` is clean `RELEASED_RETAIN`; deployed runtime owns the next action. No repeat of contained B is permitted. |

| 2026-08-16 | Control Tower ordered-assessment protocol | Charl identified repeated Control Tower drift despite the complete Mission Standard and existing feedback template: open processes were treated as active work, stale waits survived cleared dependencies, mission promotion was missed and conversation memory substituted for a current all-terminal sweep. The rules existed but were distributed across a 976-line Standard without one mandatory execution receipt. | Add and enforce `CONTROL_TOWER_ASSESSMENT_AND_DISPATCH_PROTOCOL.md` as the mandatory operational companion, link it from the Standard and terminal feedback template, require a Control Tower Check Receipt, fresh process/runtime/dependency proof, durable register update and all-terminal sweep on every assessment. This changes governance procedure only; it grants no runtime, dispatch, provider, farm, hardware, n8n or Sheets authority. |

| 2026-08-16 | HERDMASTER `HMQ-20260813-04` current contract handoff after reconciliation | HERDMASTER reconciled to main `4c12069d` and pushed PR #984 head `bc7c1a4d`. The exact candidate has six individual Tyson mating rows, four separately labelled partner aggregates, 37/37 offspring operational projections and deterministic digest `a2915b915382a5b5ac53f3d01c5ef4c8c38f2d103c575678cc27a10ecdf273ed`; 50 focused tests, two disposable-PostgreSQL tests, all three CI lanes and three independent reviews passed with zero writes. Fresh Control Tower fetch now shows authoritative main `4d129488`: PR #984 is six commits ahead and six behind. The six incoming commits are ROOTLINE-only and byte-disjoint from HERDMASTER's five files, but exact-current-head CI and deployment proof do not yet exist. The CODEX UI worktree remains at `b936a1e8` with unique untracked `output/`; visible Codex processes do not prove that terminal is actively working. | Keep HMQ-04 `WORKING / SOURCE_RECONCILIATION_REQUIRED`, Business completion false. Send the released HERDMASTER terminal to the same clean worktree to merge current main non-destructively, repeat the current four-document preflight, prove the five HERDMASTER blobs/semantic packet remain unchanged, rerun proportional exact-head checks/reviews and update PR #984. Do not merge or deploy until the serialized release lane is freshly proven free and current-head checks pass. Preserve the existing CODEX UI branch/output and send it nothing until the exact backend merge and deployed revision are verified; then resume that same UI mission for reconciliation and owner preview. No farm write, owner preview, n8n/Sheets authority or duplicate analytics contract. |

| 2026-08-16 | BEACON `BMQ-20260813-05` text-only organic review source candidate | BEACON produced an uncommitted source-only `beacon_facebook_organic_text_only_review/v1` candidate on head `cdebba2f`: `media=[]` is mandatory; proposal/result, actor, page, caption, locale, audience, evidence, Unknowns, SAM routing, policy and expiry are digest-bound; spend, boost, scheduling, customer and farm authority remain zero. The existing media-bearing class is unchanged and 103 focused/canonical tests passed. No runtime, Supabase, provider, owner-visible, publication or physical effect occurred. Initial independent reviews blocked the draft; corrections were made afterward but fresh exact-head reviews have not approved them. A material journey gap remains: no completed Oom Sakkie protected-action adapter binds authenticated owner/private chat/card/packet digest/expiry/replay identity to Approve/Correct/Decline and the immutable weekly decision rail. Fresh Control Tower fetch shows current main `847d616e`; the candidate is four commits ahead/six behind. Incoming changes are ROOTLINE-only except that main lacks the branch-local BEACON handover file; the dirty six-file candidate is unique and must be preserved. | Keep BMQ-05 `WORKING / ACTIVE_UNCOMMITTED_CANDIDATE / SOURCE_RECONCILIATION_REQUIRED`; Business completion false. Send an addendum to the same BEACON terminal, because its packet contains fresh source/test progress, to checkpoint all current dirty bytes before reconciliation, then merge current main non-destructively. Complete the missing Oom Sakkie protected review adapter using the existing canonical protected-action and weekly-decision spine; do not create a competing ledger or publication path. Require exact authenticated-owner/private-chat/digest/expiry/replay binding, visible Approve/Correct/Decline, zero provider execution from review approval alone, focused replay/concurrency tests and fresh architecture/security/commercial reviews. Only after exact-head approval may it commit/push/open a source-only PR; stop before merge, deploy, owner preview or publication. Return the complete feedback template. No new n8n/Sheets authority. |

| 2026-08-16 | CORE `CMQ-20260813-05` isolated runner-control revalidation passed | CORE statically corrected the two safe-validation regressions in clean checkpoint `9da090fa`: exited/unverifiable startup handles cannot authorize descendant enumeration or PID termination, live captured descendants require exact identity revalidation immediately before containment, and the duplicated test decorator/signature mismatch was removed. Control Tower ran commit `9da090fa` in Docker image `core-runner-validator:20260816` (`sha256:dad31c6f...`) with network disabled, repository mounted read-only, read-only container root, tmpfs `/tmp`, bytecode writes disabled and a container PID namespace isolated from host CORE/Codex/supervisor/relay processes. The first shallow-mount invocation stopped during import with zero tests executed; corrected mount depth then produced 9/9 focused tests passing and the full 57-test suite passing with three platform-dependent skips. No host/production PID was visible or targeted and no provider, database, farm or runtime mutation occurred. Current main is `847d616e`; the branch is four ahead/eight behind, with incoming changes confined to ROOTLINE/Oom Sakkie files and outgoing changes confined to the three CORE runner-control files. | Promote mission to `WORKING / ISOLATED_VALIDATION_PASSED / SOURCE_RECONCILIATION_REQUIRED`; Business completion false. Send the released CORE development terminal back to the same clean worktree for non-destructive current-main reconciliation, exact-head static review and source-only PR preparation. It may run compile/diff checks but must not run runner/process-control tests inside Codex; Control Tower will repeat isolated tests if reconciliation changes any CORE blob. Require an independent process-safety/security review of the exact reconciled head. Stop before merge, deploy, runner start/stop, supervisor mutation or runtime-continuity claim. Historical terminal exits and the failed first isolated suite remain immutable evidence; no owner repetition. |

| 2026-08-16 | SAM always-on Livestock exact `one_clarification` source-envelope decision | SAM reconciled and reviewed `sam_livestock_one_clarification_v1` on head/deployed revision `4c12069d`: a neutral acknowledgement plus exactly one deterministic unanswered customer-fact question, retained language, seven-day maximum authority, candidate-to-canary-to-promoted transitions, complete identity/chronology/evidence digest binding, one durable claim before one provider attempt, no retry, delivered/read terminality, zero replay/restart/concurrency duplicates and broad protected/commercial exclusions. Commercial-safety and security reviews approved the packet for source preparation only. Canonical readback shows Level1 evaluation enabled but no response-class candidate/canary/promoted event and no controller/global/class gate; the independent Render shadow worker advances durable cycles but customer sending is disabled. Fresh Control Tower fetch shows main `847d616e`, eight commits beyond the SAM worktree; every intervening file is ROOTLINE/Oom Sakkie protected-Mixer-only and governance/SAM authority/runtime files are unchanged, so the decision semantics remain current even though the retained SAM worktree must fast-forward again before implementation. One diagnostic made an unnecessary read-only Chatwoot chronology retrieval; it had zero content output, mutation, replay or send and is retained as a process deviation, not acceptance evidence. | Set mission `WORKING / OWNER_HOLD / EXACT_AUTHORITY_DECISION_READY`; Business completion false. Do not prompt or restart SAM until Charl chooses: (1) approve the exact envelope for source/tests/PR only, (2) correct an exact field, or (3) decline and retain shadow-only operation. Approval creates no authority event, gate, deployment or customer-send permission. If approved, the same SAM terminal must first fast-forward to then-current main, repeat all four governing-document checks in its worktree, implement strict versioned envelope preservation/effective-time/predicate/proposal-claim-attempt-provider binding, prove existing schema compatibility with disposable PostgreSQL and return the complete handover template. Activation and genuine provider-confirmed acceptance remain later protected stages; final programme acceptance still requires five genuine customers. |

| 2026-08-16 | SAM `one_clarification` source implementation approval | Charl explicitly selected Option 1 after receiving the exact reviewed `sam_livestock_one_clarification_v1` decision packet. The approval is limited to source implementation, tests, independent review and one source-only PR. It does not create or promote an authority event, clear the controller/global/class gates, authorize a migration automatically, acquire the release lane, merge, deploy, enable dispatch, replay history or send any customer message. At approval time authoritative main remains `847d616e`; the retained SAM worktree is clean at `4c12069d`, zero ahead/eight behind, and the intervening changes are byte-disjoint ROOTLINE/Oom Sakkie protected-Mixer files. | Promote the same mission to `WORKING / SOURCE_IMPLEMENTATION_AUTHORIZED`. Send the existing SAM Livestock terminal one bounded continuation: fast-forward current main, repeat all four governing-document checks, implement the exact reviewed class/envelope and complete identity/evidence/claim/attempt/provider bindings, prove current-schema compatibility using focused and disposable-PostgreSQL tests, obtain fresh commercial-safety and security/data-integrity reviews, push and open one source-only PR, then stop. No authority mutation, deployment, gate change or provider/customer action. Return the complete feedback template. |

| 2026-08-16 | OOM SAKKIE `OMQ-20260816-ANTON-FARM-MANAGER-CHANNEL` ingress parity and delegated ROOTLINE boundary | Fresh provider chronology proves Anton's canonical `farm_manager` identity was already resolving. Message `3680` (`Wat kort my aandag?`) crossed authenticated Telegram/n8n/backend ingress but was classified `unsupported_family_capability` and returned provider-delivered generic denial `3681`; later weather message `3684` resolved the same principal and produced Afrikaans delivery `3685`, both with zero farm/hardware effects. The defect is classifier/direct-ingress parity, not missing access. A preserved dirty five-file candidate routes direct text through the existing canonical family principal/runtime, retains authorization/binding/language/provenance, isolates owner/SAM/BEACON handlers, gives one precise Afrikaans clarification and passed 219 tests plus security, HERDMASTER and Afrikaans reviews. Complete mission review correctly remains blocked: direct Telegram lacks an OOM-owned delegated-family ROOTLINE preview/callback contract. Current main is now `9c09a8ec`, nine commits ahead of candidate base `2da19d62`; incoming changes are the exact protected-action/ROOTLINE Mixer claims, runtime, gateway and migration surfaces on which the missing callback depends, while the dirty ordinary-text files themselves are preserved. | Keep mission `WORKING / ACTIVE_DIRTY_CANDIDATE / SOURCE_REVIEW_BLOCKED`; Business completion false. Send an addendum to the same OOM SAKKIE terminal: checkpoint all dirty bytes, reconcile current main non-destructively, retain the approved ordinary-text slice, then implement one source-only `oomfm:` delegated-family preview/callback boundary on the existing canonical claims table and `rootline_delegated_principal.v1`. Bind exact Anton private identity/role/auth/binding/evidence/path/zone/duration/job/provider chronology/preview digest/expiry; reconstruct actions only from persisted preview; fail closed for wrong identity/chat, Antoinette, forgery, expiry, changed evidence, ambiguity, replay and concurrency; never reuse owner callback semantics or grant commissioning/autonomy/excluded hardware. Require disposable-PostgreSQL proof and renewed ROOTLINE/security review. Commit/push/open one PR only after exact-head approval; stop before merge, deploy, send, farm write or hardware command. Return the full feedback template. |

| 2026-08-16 | ROOTLINE Mixer tenth owner-presence failure and reusable commissioning spine | Charl supplied fresh current physical presence at the fertilizer valves. Control Tower did not convert this chat into authenticated Telegram evidence and did not replay old cards. Canonical readback found one active `rootline_fertilizer_mixer_presence_refresh` claim with no card, confirmation or result; cards `3687` and `3689` remain completed/non-replayable. One authenticated deployed scheduler invocation returned `scheduled_reassessment_replayed_noop` for the current bucket, sent zero Telegram messages and made zero hardware/provider-control calls; follow-up readback showed the active claim still undelivered. The deployed lifecycle therefore cannot consume the fresh physical window and the same owner action has now failed repeatedly. GENERAL's architecture finding is accepted: provider/device control primitives, protected confirmation, commissioning stages and replay/audit must be reusable profiles rather than bespoke per-channel journeys. | Mark RMQ `WORKING / CONTAINED_SYSTEMIC_JOURNEY_DEFECT`; prohibit another Charl presence statement or Mixer attempt until non-actuating proof shows an active claim cannot become stranded before card delivery. Stop asking Charl to remain at the valve. Recovery Slot 2 becomes the shared OOM/ROOTLINE operating spine: first repair the active-claim delivery/recovery invariant and prove a presence button is delivered within one scheduler cycle with zero actuation; then define one typed device registry, provider-independent actuator adapter, generic commissioning state machine, protected confirmation/replay/audit contract and stage/status projection. Preserve existing Mixer evidence and B/C behavior. Split Injection into RMQ-03A isolated control proof and RMQ-03B real-flow acceptance. Ordinary relay devices using a proven provider/profile must require configuration plus supervised commissioning, not new control code. Pump/breaker risk profiles remain stricter. Fresh worktree evidence shows OOM SAKKIE reconciled current main at `632dd142` in the existing Anton/protected-action worktree while ROOTLINE's retained worktree is clean/released; because both defects share protected claim/runtime/gateway surfaces, the active OOM terminal owns Slot 2 implementation and ROOTLINE supplies mandatory device/safety review. No second ROOTLINE implementation worktree may start. |

| 2026-08-16 | DOCUMENTS `DMQ-20260816-01` catalogue checkpoint under Autonomy Recovery Mode | PR #1016 head `e228f74a` contains only the canonical document catalogue, ownership map and focused tests. Twenty-one local tests, compilation, diff checks, both independent reviews and all three exact-head CI lanes passed. It creates no route, PDF, Telegram delivery, scheduler, printer job, runtime authority or business effect. The retained worktree is clean and pushed. Fresh Control Tower comparison shows it is three commits ahead/thirty behind main `b5e13396`; incoming changes include the current 996-line Standard, 319-line Protocol, 216-line template, recovery-mode register and OOM/ROOTLINE protected-action work, while the three catalogue files remain isolated. The terminal's claim that PR monitoring is active work is rejected: no local process or deployed capability depends on it. | Classify DMQ-01 `WORKING / FROZEN_STRATEGIC_WIP / REVIEWED_PR_PRESERVED`; strategic class `EXPANSION`, no recovery WIP slot. Keep PR #1016 open and preserve worktree/branch/ignored artifacts without polling, reconciliation, merge or closure during Recovery Mode. Do not dispatch DOCUMENTS or start DMQ-02. Automatic promotion requires Recovery Mode exit plus a fresh collision/current-lineage audit; then reconcile PR #1016 normally and integrate before any adapter work. Current owner workload delta is zero because no operational document capability exists; no owner action is requested now. |

| 2026-08-16 | CORE `CMQ-20260813-05` runner-control source PR reconciled under Autonomy Recovery Mode | PR #1022 head `0b24532e` completed all three hosted CI lanes successfully after isolated validation and independent process-safety approval. Control Tower rejected its old CI wait as a current terminal dependency once the checks completed. Current main advanced to `9c014a7b`; commit inspection proved no intervening main commit touched the three CORE paths, so Control Tower merged main non-destructively into the preserved clean CORE branch and pushed exact head `799d1bc1`. The three isolated-tested blobs remain byte-identical (`2e3ddf78`, `32f1d52d`, `9c1399c1`). No local process-control test, runner command, process enumeration, supervisor/runtime mutation, deployment or owner-visible effect occurred. | Keep CMQ-05 `WORKING / SOURCE_RECONCILED / EXACT_HEAD_CI_IN_PROGRESS`; strategic class `OPERATING_SPINE`, Recovery Slot 1. GitHub-hosted CI may complete independently; the development terminal is released and must not be restarted merely to poll. If exact-head CI passes, Control Tower may integrate PR #1022 through the serialized release lane, but deployment and terminal-independent runner continuity remain separate acceptance stages. Before any later terminal action, CORE must repeat the current four-document governance preflight in its own worktree and return `CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md`. Never repeat process-control validation inside the CORE/Codex development tree. Owner workload delta remains zero and Charl should send nothing now. |

| 2026-08-16 | CORE `CMQ-20260813-05` runner-control source integrated | CORE repeated current four-document governance verification in its clean target worktree and returned the complete handover. PR #1022 exact head `799d1bc1` remained confined to the three CORE runner-control files, preserved all isolated-tested blobs, passed all three required exact-head CI lanes and was GitHub-mergeable. The only later main commits were Control Tower register updates and did not touch CORE source. Control Tower therefore used the serialized source release lane and merged PR #1022 as authoritative main `e31f80e5`. No deployment, runner/process command, process enumeration, supervisor mutation, runtime load or operational-continuity claim occurred. | Promote CMQ-05 to `WORKING / SOURCE_INTEGRATED / DEPLOYMENT_ASSESSMENT_REQUIRED`; strategic class `OPERATING_SPINE`, Recovery Slot 1, Business completion false. The cleared PR wait is retired. The next bounded stage is a separate deployment assessment against exact merge `e31f80e5`; before acting, the target CORE terminal must repeat current governance in its own worktree and return the complete feedback template. Do not run process-control validation inside Codex ancestry. Acceptance remains exact deployed revision and loaded source, exact owned-tree containment, durable worker identity, heartbeat, next independently triggered cycle and terminal-independent continuity. Charl should send no process command or repeat prior recovery actions. |

| 2026-08-16 | CORE `CMQ-20260813-05` deployment rail systemic blocker | Read-only deployment assessment identified the genuine local promotion rail `scripts/promote_charlie_runtime.ps1`, dedicated runtime/execution worktrees, runtime manifest and intended two-minute Windows watchdog task. Deployment was correctly refused: the rail would run runner-control tests beneath the vulnerable Codex ancestry, no isolated promotion executor exists, `supervisor.stop` and `governed_stop_active` remain present, and durable state contradicts itself across runtime HEAD `3768cc08`, execution HEAD `7cb7ddae`, manifest revision `d84ab1a4`, heartbeat source `9f2970ba` and desired merge `e31f80e5`. The last heartbeat is stale, supervisor is durably stopped, installed task state and lane ownership are Unknown, and no deterministic known-good rollback tuple is proven. Zero runtime, task, process, database, provider, farm or hardware mutation occurred. | Set CMQ-05 `WORKING / DEPLOYMENT_BLOCKED_SAFE / RELEASE_RAIL_REPAIR_REQUIRED`; retain Recovery Slot 1 and Business completion false. Preserve the governed stop and every contradictory state file as evidence. Dispatch one isolated source-only release-rail repair mission outside the CORE development process tree: design a reviewed promotion executor that accepts exact SourceRef, consumes the sealed isolated-validation receipt or runs validation in an independent boundary, stages runtime/execution/manifest agreement without enabling the watchdog, records durable lane ownership and an exact rollback tuple, and fails closed on any state contradiction. Do not deploy, clear the stop, register/enable the task, start/stop/enumerate processes or ask Charl to reproduce the exits. Only after source/CI/independent review may Control Tower separately authorize isolated promotion. |
| 2026-08-16 | BEACON `BMQ-20260813-05` protected text-only review PR preserved under Autonomy Recovery Mode | Clean PR #1024 head `f9c682a3` implements the source-only `beacon_facebook_organic_text_only_review/v1` contract with mandatory empty media, immutable evidence/policy/expiry binding, authenticated owner/private-chat/card callbacks, EN/AF/mixed Approve/Correct/Decline controls, existing weekly-decision authority, successor correction, replay/concurrency/restart containment and no competing ledger, n8n or Sheets authority. Its historical exact-head evidence is 225 proportional tests plus PostgreSQL coverage, three independent approvals and all three hosted CI lanes green. No source is runtime-loaded and no owner preview, Telegram mutation, Meta call, publication, schedule, spend, customer, farm or hardware effect exists. The terminal verified superseded governance (986/259/208 lines); current authoritative governance is 996/319/216 lines, and the clean branch is twelve ahead/twenty-two behind current main `ed64ebf3`. | Keep BMQ-05 `WORKING / FROZEN_STRATEGIC_WIP / REVIEWED_PR_PRESERVED`; strategic class `EXPANSION`, Business completion false, no Recovery Mode slot. Do not dispatch BEACON, reconcile, merge, deploy, preview or publish while the three operating-spine slots remain occupied. Preserve PR #1024, checkpoint `c5345b82`, clean head `f9c682a3`, handover and all historical worktrees. Automatic promotion requires Recovery Mode exit plus a fresh current-lineage collision audit; the BEACON terminal must then repeat all four current governing documents in its own worktree and return the complete handover template before any action. Owner workload delta is zero now; Charl should send nothing. |

| 2026-08-15 | Control Tower deployed-agent execution ownership correction | After SAM deployed the protected BKB settlement journey, Control Tower ambiguously instructed the SAM development terminal to "produce" the preview. The terminal generated a correct zero-write preview and token in feedback instead of the deployed Oom Sakkie/SAM runtime delivering Telegram buttons. No payment was written, but terminal test output was incorrectly advanced as the owner journey. | Extend the existing Agent Operational Reality and standing-authority lineage with a mandatory Agent Execution Ownership Gate. Every prompt and handover must name deployed actor, genuine trigger, owner channel, terminal-permitted role, forbidden substitutions and agent-origin proof. The BKB terminal preview remains contained test evidence; SMQ-20260813-05 stays WORKING until the deployed agent delivers and processes the genuine Telegram confirmation journey. |

| 2026-08-15 | Control Tower standing-authority and owner-burden correction | Owner reaffirmed that the system exists to remove routine work and that governed agents have standing permission to operate inside approved policies. ROOTLINE nevertheless encoded manual visible-rain confirmation and explicit owner review as mandatory dry-release evidence, proving that the Agent Operational Reality Gate did not prevent an autonomous trigger from remaining dependent on recurring owner labour. | Extend the existing Agent Operational Reality Gate lineage across the Mission Standard, Runtime Programme, handover, register, source map and changelog. Treat routine approvals, duplicate observations and terminal-manufactured evidence as systemic journey defects. Use RMQ-20260813-04 as the first runtime acceptance: fresh healthy local weather evidence must govern routine B/C rain release without per-cycle owner approval, while real rain, stale/conflicting evidence, controller safety and uncommissioned topology remain fail-closed. |

Before dispatch, record the mission ID, deployed owner, development terminal,
priority, dependency, dispatch truth, preserved acceptance outcome and whether
Charl should send anything now. A finding remains until owner-visible completion
or explicit containment.

## 2026-08-17 Continuous Agent Operations Reset

Mode: `AUTONOMY_RECOVERY_MODE / CONTINUOUS_OPERATION_ENFORCEMENT`.

Owner correction: the useful target is not a once-daily brief or a collection of
request-driven tools. Oom Sakkie must manage continuously, specialists must wake
from genuine events or durable schedules, and routine work must continue without
Charl activating terminals, relaying findings or discovering failures manually.

The previous stage labels are retained as historical engineering evidence but
do not establish current operational capability. No terminal may claim success
from source, tests, PR, merge, deployment, health, shadow output, one manual
invocation or one brief. Each active mission below owns the full loop through a
fresh genuine trigger, verified result, next trigger and terminal-close proof.

| Agent / development terminal | Current honest operating state | Complete outcome target | Continuous trigger and follow-up | Current acceptance blocker | Owner work removed |
|---|---|---|---|---|---|
| CORE / CORE | Release/staging rail integrated; `ebc661b5` was coherently staged under preserved governed stop, but authoritative main advanced to `f588c276` with the continuous-operation and Brain Guard reset before activation; no deployed worker exists | Durably receive, plan, dispatch, supervise and close bounded software missions, including detecting stalled agents, without Charl pasting prompts or monitoring terminals | Durable mission queue plus supervised runner; every mission retains worker, heartbeat, progress, closeout and next eligible mission | Revalidate and restage exact current authoritative main through the proven isolated rail, then separately govern activation, loaded-revision proof, exact-tree containment, heartbeat, next independent cycle and terminal-close continuity | Manual prompt relay, terminal checking, recovery and cross-terminal coordination |
| OOM SAKKIE / OOM SAKKIE | PR #1026 at `facb6a32` is source-tested, independently approved and CI-green for protected delivery and typed ROOTLINE device authority, but it was built on `ebc661b5`; no deployed manager loop is proven | Continuously ingest material farm/business/runtime events, investigate them, delegate typed specialist work, track it to closure and notify Charl or Anton only with a useful result, genuine exception or protected decision | Event subscriptions plus bounded reassessment scheduler and durable unresolved-work ledger; next trigger is evidence change or earliest due time, not tomorrow's brief | Reconcile PR #1026 non-destructively with current authoritative main and the Continuous Operations Acceptance Gate, rerun exact-head audit/CI/reviews, then make a serialized integration decision; deployment and genuine terminal-independent manager cycles remain absent | Discovering omissions, asking each specialist, repeating facts, chasing failures and waiting until the next morning |
| ROOTLINE / ROOTLINE | Request/invocation paths exist; current water-energy plan returned `no_current_water_energy_plan`; no current independent decision cycle proven | Continuously refresh water, weather, power, device and irrigation evidence; maintain a current plan; execute routine approved work inside standing authority; verify effects; retry/reassess; escalate one exact exception | Evidence-change events plus durable due-time scheduler; failures remain owned and reassessed automatically | Shared OOM/ROOTLINE claim delivery and reusable device commissioning spine remain incomplete; fresh plan worker/next cycle absent | Manually waking ROOTLINE, asking for irrigation status, repeating valve presence and monitoring retries |
| HERDMASTER / HERDMASTER | Canonical pig/litter/weight reads are useful; continuous husbandry worklist and follow-through not proven | Continuously maintain the herd work queue for weighing, litter care, treatments, welfare, breeding and sales eligibility; dispatch due work through Oom Sakkie and verify resulting canonical updates | Canonical event subscriptions plus due-date scheduler; every due item has next action, assignee, deadline and reassessment | Molly's due treatment was omitted from the manager output; weighing remained a count rather than an operated workflow; Pig 151 exclusion was silent rather than explained | Finding due animal work, checking lists/pages and diagnosing why an animal is unavailable |
| SAM / SAM Livestock | Autonomous shadow inbox cycling proven; customer dispatch disabled | Continuously handle every eligible genuine customer event with supported useful responses and follow-ups, escalating only protected commercial decisions | Provider webhook plus durable backlog/follow-up scheduler; unrelated work continues after one quarantine | Narrow source authority was approved but deployed response-class authority and five-customer proof remain absent | Reading the inbox, writing routine replies and remembering follow-ups |
| BEACON / BEACON | Proposal/publication source exists; no proactive deployed marketing loop or provider publication proof | Continuously reconcile sale-ready stock and current commercial priorities, prepare useful campaigns/media requests, obtain only protected approval, publish exactly once and measure the result | Sale-readiness/material-change events plus campaign cadence and performance reassessment | Frozen expansion classification is superseded where silence blocks the selected sell-ready-animal operating outcome; current terminal state and current-lineage collision must be verified before dispatch | Noticing animals need marketing, requesting campaigns and checking whether anything was posted or worked |
| DOCUMENTS / DOCUMENTS | Catalogue source only | Generate and deliver authorized documents from canonical requests through the correct channel and track delivery/printing outcome | Canonical document request events and due schedules | Frozen outside the three recovery tracks until it directly blocks an active operating outcome | Finding generators, preparing files and manually delivering/printing |
| CODEX UI / CODEX UI | Selected deployed pages useful; known silent eligibility presentation defect | Explain current operational state and blockers without becoming a competing business engine | Read-only projection of canonical agent state | Pig 151 is correctly blocked by withdrawal hold through 2026-09-08 but Orders silently omits it; fix is eligible only as the smallest current blocker in the herd/sales journey | Investigating hidden eligibility rules and guessing why an action is unavailable |
| GENERAL / GENERAL | Read-only diagnostic terminal only; not a deployed agent or implementation lane | Turn a short owner observation into one evidence-backed reusable end-to-end defect packet for Control Tower | Owner observation only; no autonomous trigger is claimed | Temporary manual relay remains until CORE ingests and supervises findings automatically | Technical reproduction, evidence collection, ownership discovery and scope design |

### Recovery WIP and sequencing

1. **Slot 1 — CORE operating spine:** stage and restore CORE safely, then prove
   durable mission receipt, supervision, closeout and a later independent cycle.
2. **Slot 2 — Continuous farm management spine:** the existing OOM SAKKIE
   recovery worktree owns Oom Sakkie event intake, manager-case lifecycle and
   shared ROOTLINE protected/reassessment boundaries. ROOTLINE and HERDMASTER
   review their typed domain contracts; they do not create competing manager
   loops.
3. **Slot 3 — Revenue operating spine:** SAM's genuine customer loop remains the
   implementation priority. BEACON's sale-ready-stock trigger and protected
   proposal/publication journey are part of this same revenue outcome and may
   be prepared only after fresh terminal/collision verification, without opening
   a fourth implementation track.

Frozen work remains preserved. A newly reported daily-operational defect is
folded into the relevant continuous loop; it must not become a disconnected
animal-, phrase-, card- or page-specific mission.

### Non-negotiable closeout test

For every agent, acceptance requires: exact deployed revision; durable trigger;
worker identity; fresh heartbeat; one genuine independent cycle; canonical and
provider/physical readback where applicable; durable unresolved-work ownership;
the next scheduled/event trigger; and a later cycle after the development
terminal closes. Missing evidence changes the state to `Unknown`, `dormant`,
`scheduler-degraded` or `authority-disabled`; it never becomes an owner task.

Charl should send no routine wake-up, status-check or repeated evidence message.
The only permissible owner interactions are a genuinely unavailable physical
fact, strategic choice, exception or protected authority expansion.

### CORE staging assessment — 2026-08-17

The staging epoch for `ebc661b58f6a0cbfeb50651f55bef4659966abd3`
successfully proved the new serialized, receipt-bound, zero-start rail while
preserving the governed stop. It did not activate CORE. Authoritative main then
advanced to `f588c27622555488553d74270dae07efe1925060`, which contains the
continuous-agent reset and fail-closed Brain Guard alignment enforcement.
Activation of the older staged revision is prohibited. Slot 1 remains WORKING /
`RESTAGE_CURRENT_MAIN_REQUIRED`; the next CORE target is exact current main, not
the historical staged commit. The successful staging receipt remains immutable
rail evidence and is not reused as validation authority for the new revision.

### OOM SAKKIE / ROOTLINE source assessment — 2026-08-17

PR #1026 at `facb6a32d5ec89023d7a5da0aaad8d3ef485de6f` passed its
proportional and disposable-PostgreSQL suites, all required hosted CI and three
independent source reviews. It remains source-only and has produced no deployed
manager, provider, canonical-production or physical outcome. Its base
`ebc661b58f6a0cbfeb50651f55bef4659966abd3` predates the continuous-agent and
Brain Guard reset now on authoritative main. The incoming current-main paths
have zero file overlap with PR #1026, so the existing released-retain worktree
is eligible for one non-destructive reconciliation and exact-current-head
review. Integration is prohibited until that refreshed evidence returns.

## Delivery limitation

Automatic prompt delivery to every visible terminal is not proven. Charl must
paste a prompt unless target-specific delivery and acknowledgement are evidenced.
The target is the durable CORE queue/runner. Until then, queued, delivered,
started and deployed-runtime-active remain distinct states.

## Vault Cutover Governance Hold — 2026-08-18

Mission: `VAULT-CUTOVER-20260818`, governance alignment programme.

Owner decision: **APPROVE VAULT CUTOVER BATCH 1 — inventory and classification
only; no moves, deletions, doctrine rewrites, or runtime changes.**

Batch 1 ran against authoritative baseline
`59c34f961c2c84bfa182b783987c806ac838fabe` in a clean isolated worktree. It
inventoried 513 tracked Markdown/MDX files: 172 inside `docs/09-vault-brain` and
341 outside. No byte-identical duplicate group exists. The risk is semantic
overlap, ambiguous lifecycle and competing authority. The durable file ledger
and proposed actions are recorded in `VAULT_MIGRATION_INVENTORY.md`; no proposed
action is execution authority.

Lifecycle: `WORKING / BATCH_1_CLASSIFICATION / GOVERNANCE_ALIGNMENT_HOLD`.

Control boundary: no new agent feature mission may treat unresolved legacy docs,
planning files, evidence logs or static agent assets as normative doctrine.
Existing production agents are not stopped by this documentation batch, but no
runtime change or new protected authority is granted. Batch 2 may begin only
after owner review of the Batch 1 conflict/action summary. Physical moves,
archive operations and deletions require their own approved manifest.

Next ordered work: governance routing; common agent contract; CORE/Oom Sakkie;
ROOTLINE/HERDMASTER; BEACON/SAM with Meta safety; CODEX UI with the mandatory
Facelift Standard; Documents/remaining specialists; data/workflow authority;
then an owner-approved archive/delete manifest.

### Vault Cutover Batch 2 - 2026-08-18

Owner approved Batch 2. Authority-routing design now establishes
`docs/09-vault-brain/` as the only normative agent-doctrine root, with only the
canonical Runtime Programme and Control Tower feedback template retained as
narrow controlling exceptions. Mission-state records and all technical,
planning, handover, evidence, static-asset and legacy documents are explicitly
non-doctrine unless later promoted through Vault governance.

Lifecycle: `WORKING / BATCH_2_AUTHORITY_DESIGN_COMPLETE /
ENFORCEMENT_AND_AGENT_AUDIT_PENDING`.

No files moved or deleted; no runtime, provider, production data or agent
authority changed. The next eligible batch is deterministic source enforcement
plus the ordered common/agent contradiction audit. Physical cutover remains
behind a separate owner-reviewed manifest.

### Vault Cutover Batch 3 - 2026-08-18

Owner approved deterministic enforcement and the principal-agent contradiction
audit. The existing Vault retrieval/Brain Guard path now loads canonical packs,
fails on missing or incomplete packs and rejects legacy/current-state/handover
material when claimed as doctrine. UI and BEACON/Meta policy overlays are
machine-selected. Documents remains deliberately blocked pending a canonical
agent/workflow pack.

Lifecycle: `WORKING / BATCH_3_SOURCE_ENFORCED /
PHYSICAL_MANIFEST_AND_DEPLOYED_ACCEPTANCE_PENDING`.

No document was moved or deleted and no production data/provider action was
performed. Next eligible work is the exact physical cutover manifest and
deployed Brain Guard acceptance, each behind its own reviewed boundary.

### Vault Cutover Batch 4 - 2026-08-18

Owner approved the exact physical-cutover manifest only. The resulting
machine-readable and human-reviewable manifests cover all 513 tracked source
Markdown/MDX files from baseline `66d4667d`, with current full digests,
all-tracked-text exact references, exact dispositions, destinations or
replacements, blockers and `physical_change_authorized: false`.

Lifecycle: `WORKING / BATCH_4_MANIFEST_COMPLETE /
PHYSICAL_EXECUTION_AND_DEPLOYED_ACCEPTANCE_PENDING`.

Disposition totals: 203 retained canonical/current/technical sources, 72
transitional sources retained behind exit tests, 15 existing archive files, 9
generated projections to reconcile, 18 future pointers, 117 extraction/archive
items, 73 runbook/history splits, 6 archive candidates and zero delete
candidates. No move, archive, deletion, pointer rewrite, runtime action,
provider action or production mutation occurred.

Automatic promotion requires owner approval of a bounded physical execution
batch. That later batch must regenerate against current main and close every
entry-specific blocker before changing the corresponding source.

### Vault Cutover Batch 5 - 2026-08-18

Owner approved the first bounded physical cleanup slice and expressly withheld
all deletion authority. The five top-level legacy governance files under
`docs/05-ai` were reconciled, preserved byte-for-byte through Git renames, and
archived under `docs/99-archive/vault-cutover/docs/05-ai/`. Active references
now resolve to canonical Vault packs or explicit archive evidence.

Lifecycle: `WORKING / BATCH_5_FIRST_SLICE_COMPLETE /
NEXT_PHYSICAL_SLICE_OWNER_APPROVAL_REQUIRED`.

No runtime, provider, production-data, agent authority or deployed behavior
changed. No deletion occurred. The agent-specific BEACON and SAM legacy files
remain in place. Automatic promotion requires a fresh owner approval for one
next coherent slice selected from the regenerated manifest; every deletion
continues to require a separate exact deletion approval.

### Vault Cutover Batch 6 - 2026-08-18

Owner authorized continuation as the next bounded no-deletion slice. The four
remaining agent-specific files under `docs/05-ai` were reconciled and archived
intact. Active BEACON and SAM authority now resolves only through focused Vault
packs; dated scope, storage and implementation plans remain archive evidence.

Lifecycle: `WORKING / BATCH_6_DOCS_05_AI_ARCHIVED /
NEXT_PHYSICAL_SLICE_OWNER_APPROVAL_REQUIRED`.

No deletion, runtime, provider, production-data or authority change occurred.
Automatic promotion requires a fresh bounded owner authorization using the
regenerated manifest.

### Vault Cutover Batch 7 - 2026-08-18

Owner authorized the next bounded no-deletion slice. Two superseded,
zero-reference external UI briefs were preserved intact under
`docs/99-archive/vault-cutover/external_sources/`. Current UI authority remains
the mandatory Facelift and UI Dashboard standards plus the owning-agent pack.

Lifecycle: `WORKING / BATCH_7_EXTERNAL_UI_BRIEFS_ARCHIVED /
NEXT_PHYSICAL_SLICE_OWNER_APPROVAL_REQUIRED`.

The external-source index and current telemetry/provider documentation remain
in place. No deletion, doctrine rewrite, runtime, provider, production-data or
authority change occurred. Automatic promotion requires a fresh bounded owner
authorization using the regenerated manifest.

### Vault Cutover Batch 8 - 2026-08-18

Owner authorized reconciliation and deletion where the strict test passed. The
four remaining external archive candidates were completely reviewed. None
passed the archive or deletion test: all retain current technical, provider,
secret-handling or meat-source value.

Lifecycle: `WORKING / BATCH_8_EXTERNAL_CANDIDATES_RESOLVED /
NEXT_PHYSICAL_SLICE_OWNER_APPROVAL_REQUIRED`.

The manifest now contains zero `ARCHIVE_CANDIDATE` entries. Vault doctrine
remains authoritative over the retained technical/source evidence. No move,
deletion, runtime, provider, production-data or authority change occurred.

### Vault Cutover Batch 9 - 2026-08-18

Owner approved the legacy navigation/process pointer slice. Seven files were
read completely, reference-audited and reduced to short compatibility pointers
after their durable rules were confirmed in focused Vault files.

Lifecycle: `WORKING / BATCH_9_LEGACY_POINTERS_COMPLETE /
NEXT_PHYSICAL_SLICE_OWNER_APPROVAL_REQUIRED`.

No path was deleted because CORE consumers and historical references still use
some of them. No runtime, provider, production-data or authority change
occurred. Automatic promotion requires a fresh bounded owner authorization
using the regenerated manifest.

### Vault Cutover Batch 10 - 2026-08-18

Owner approved the bounded root/status/navigation pointer slice. Five files
were read completely, reference-audited and reduced to short compatibility
pointers while retaining required local startup and agent-asset technical facts.

Lifecycle: `WORKING / BATCH_10_ROOT_STATUS_POINTERS_COMPLETE /
NEXT_PHYSICAL_SLICE_OWNER_APPROVAL_REQUIRED`.

No path was deleted because compatibility and technical consumers remain. No
runtime, provider, production-data or authority change occurred. Automatic
promotion requires a fresh bounded owner authorization using the regenerated
manifest.

### Vault Cutover Batch 11 - 2026-08-18

Owner approved the technical operating-contract slice. Three legacy files were
read completely and reference-audited; current procedures were consolidated
into existing focused Vault workflow/standard files before pointer conversion.

Lifecycle: `WORKING / BATCH_11_TECHNICAL_CONTRACTS_COMPLETE /
NEXT_PHYSICAL_SLICE_OWNER_APPROVAL_REQUIRED`.

No deletion, runtime, activation, deployment, provider, production-data or
authority change occurred. Automatic promotion requires a fresh bounded owner
authorization using the regenerated manifest.

### Vault Cutover Batch 12 - 2026-08-18

Owner approved the current-state and roadmap reconciliation slice. The two
large start-here projections were read completely and reference-audited, then
reduced to compatibility pointers after current mission truth was confirmed as
the responsibility of this durable register and fresh runtime evidence.

Lifecycle: `WORKING / BATCH_12_STATE_ROADMAP_POINTERS_COMPLETE /
NEXT_PHYSICAL_SLICE_OWNER_APPROVAL_REQUIRED`.

No unique doctrine was lost; dated content remains in Git history. No deletion,
runtime, activation, deployment, provider, production-data or authority change
occurred. `PRODUCT_VISION.md` is the final start-here projection awaiting a
separate complete reconciliation.

### Vault Cutover Batch 13 - 2026-08-18

Owner approved the final start-here projection reconciliation. The complete
legacy product vision was reviewed; its durable Oom Sakkie experience rules
were consolidated into focused identity and UI standards before the path was
reduced to a compatibility pointer.

Lifecycle: `WORKING / BATCH_13_START_HERE_PROJECTIONS_COMPLETE /
NEXT_MANIFEST_SLICE_OWNER_APPROVAL_REQUIRED`.

Duplicated agent bibles, authority rules, build phases, voice-provider notes,
asset proposals and open questions were not promoted as competing doctrine.
They remain in Git history. No deletion, runtime, activation, deployment,
provider, production-data or authority change occurred.

### Vault Cutover Batch 14 - 2026-08-18

Owner directed the programme to continue through complete repository alignment.
All 190 remaining physical-reconciliation entries were deterministically assigned
to Batches 15-27: 9 projections, 3 decision/index files, 12 Sheets-migration
files, 10 CORE mission files, 18 CORE operating files, 16 general operations
files, 22 HERDMASTER files, 30 Oom Sakkie files, 13 ROOTLINE files, 5 SAM/Revenue
files, 10 business-module files, 8 planning/inbox files and 34 Storyworks files.

Batch 28 is reserved for the 72 production-exit-tested transitional documents.
Batch 29 is reserved for deployed, scheduled Brain Guard acceptance.

Lifecycle: `WORKING / BATCH_14_EXECUTION_SCHEDULE_COMPLETE /
BATCHES_15_TO_29_REMAIN`.

No source document was moved, deleted or rewritten in this scheduling batch. No
runtime, provider, production-data, customer, farm or hardware action occurred.
Automatic promotion is Batch 15 generated-agent-projection reconciliation.

### Vault Cutover Batch 15 - 2026-08-18

Owner approved the generated-agent-projection slice. Nine handwritten static
agent notes were replaced in place by deterministic, digest-bound projections
from the exact Vault agent doctrine, per-agent JSON and central asset registry.
Beacon's inconsistent local `Posts` label was reconciled to `Marketing Lead`.

The generator and its fail-closed check are integrated into the standard Vault
alignment audit. Static cards cannot grant authority or claim runtime status.

Lifecycle: `WORKING / BATCH_15_GENERATED_PROJECTIONS_COMPLETE /
BATCHES_16_TO_29_REMAIN`.

No deletion, archive, runtime, activation, deployment, provider, production-data,
customer, farm or hardware change occurred. The remaining physical queue is 181
documents. Automatic promotion is Batch 16 decisions-and-migration-index reconciliation.

### Vault Cutover Batch 16 - 2026-08-18

Owner approved continuation into the decisions-and-migration-index slice. The
accepted source-of-truth decision and durable CHARLIE/CORE configuration rules
were reconciled into focused Vault governance, identity and deployment files.
The two dated ADR wrappers and completed migration index were then archived
intact; the physical-cutover manifest is the current migration ledger.

Lifecycle: `WORKING / BATCH_16_DECISIONS_INDEX_COMPLETE /
BATCHES_17_TO_29_REMAIN`.

No deletion, runtime, activation, deployment, provider, production-data,
customer, farm or hardware change occurred. The remaining physical queue is 178
documents. Automatic promotion is Batch 17 Sheets-migration reconciliation.

### Vault Cutover Batch 17 - 2026-08-18

Owner approved the 12-file Google Sheets migration reconciliation slice. The
current Supabase-first boundary, import lineage, duplicate/conflict handling,
shadow comparison, route cutover, rollback and fallback-retirement gates were
consolidated into focused Vault workflow, playbook and data contracts. All 12
dated GS-MIG sources were archived intact and removed from the active map.

Lifecycle: `WORKING / BATCH_17_SHEETS_MIGRATION_COMPLETE /
BATCHES_18_TO_29_REMAIN`.

No deletion, migration, import, Sheets/Supabase write, route cutover, fallback
retirement, deployment, provider, customer, farm or hardware action occurred.
The remaining physical queue is 166 documents. Automatic promotion is Batch 18
CORE mission-evidence reconciliation.

### Vault Cutover Batch 18 - 2026-08-18

Owner approved the ten-file CORE mission-evidence reconciliation slice. The
reusable portfolio-admission, execution-eligibility, current/historical
projection, Shadow observation, grouped preview, protected-claim, digest,
atomic-execution and replay rules were consolidated into focused Vault files.
All ten dated CMQ sources were archived intact and removed from active doctrine.

Lifecycle: `WORKING / BATCH_18_CORE_MISSION_EVIDENCE_COMPLETE /
BATCHES_19_TO_29_REMAIN`.

No deletion, mission admission, classification, dispatch, execution, runtime,
deployment, provider, customer, farm, database or hardware action occurred.
The remaining physical queue is 156 documents. Automatic promotion is Batch 19
sales-and-order mission-evidence reconciliation.

### Vault Cutover Batch 19 - 2026-08-18

Owner approved continuation. The manifest's exact Batch 19 family contained 18
CORE operating-spine, Build Relay, private-executive, runtime-recovery,
activation and dependency-retirement documents. Their reusable rules were
consolidated into focused CHARLIE/CORE identity, mission workflow and deployment
authority; all 18 dated sources were archived intact.

Lifecycle: `WORKING / BATCH_19_CORE_OPERATING_EVIDENCE_COMPLETE /
BATCHES_20_TO_29_REMAIN`.

No deletion, runtime, task, provider, mission, migration, deployment, customer,
farm, database or hardware action occurred. The remaining physical queue is 138
documents. Automatic promotion is Batch 20 agent mission-evidence
reconciliation.

### Vault Cutover Batch 20 - 2026-08-18

Owner approved continuation. The exact manifest family contained 16 general
operations sources. Their reusable testing, release, deployment, configuration,
recoverable bulk-operation, UI lifecycle, purpose-review and livestock
disclosure rules were consolidated into focused Vault authority; all 16 dated
or placeholder sources were archived intact.

Lifecycle: `WORKING / BATCH_20_GENERAL_OPERATIONS_COMPLETE /
BATCHES_21_TO_29_REMAIN`.

No deletion, runtime, mission, configuration, migration, deployment, provider,
customer, farm, database or hardware action occurred. The remaining physical
queue is 122 documents. Automatic promotion is Batch 21 HERDMASTER
reconciliation.

### Vault Cutover Batch 21 - 2026-08-18

Owner approved continuation. The exact manifest family contained 22
HERDMASTER operations plans and handovers. Their reusable breeding, exposure,
litter, weaning, health, loss, allocation, sales and lifecycle-analytics rules
were consolidated into focused Vault authority; all 22 sources were archived
intact.

Lifecycle: `WORKING / BATCH_21_HERDMASTER_COMPLETE /
BATCHES_22_TO_29_REMAIN`.

No animal, litter, mating, health, purpose, order, customer, farm, runtime,
provider or database action occurred. The remaining physical queue is 100
documents. Automatic promotion is Batch 22 OOM SAKKIE reconciliation.

### Vault Cutover Batch 22 - 2026-08-18

Owner approved continuation. The exact manifest family contained 30 OOM
SAKKIE missions, handovers, scorecards and runbooks. Their reusable manager,
dialogue, scheduling, family-access, specialist-dispatch, protected-action,
provider-chronology, delivery and browser rules were consolidated into focused
Vault authority; all 30 sources were archived intact.

Lifecycle: `WORKING / BATCH_22_OOM_SAKKIE_COMPLETE /
BATCHES_23_TO_29_REMAIN`.

No runtime, message, provider, customer, payment, animal, farm, database or
hardware action occurred. The remaining physical queue is 70 documents.
Automatic promotion is Batch 23 ROOTLINE reconciliation.

### Vault Cutover Batch 23 - 2026-08-18

Owner approved continuation. The exact manifest family contained thirteen
ROOTLINE plans, inventories, canaries, onboarding notes, contracts and
commissioning packets. Durable planning, device-class graduation, execution,
provider/physical verification and authority rules were consolidated into the
focused ROOTLINE agent, Control Architecture and Water And Energy Rules; all
thirteen sources were archived intact.

Lifecycle: `WORKING / BATCH_23_ROOTLINE_COMPLETE /
BATCHES_24_TO_29_REMAIN`.

No runtime, provider, message, database, farm, irrigation, fertiliser,
borehole or other hardware action occurred. The remaining physical queue is 57
documents. Automatic promotion is Batch 24 SAM/revenue reconciliation.

### Vault Cutover Batch 24 - 2026-08-18

Owner approved continuation. The exact manifest family contained five
SAM/revenue launch, inbox, completion, manager-summary and smoke documents.
Durable provider isolation, claim-boundary recovery, aggregate summary,
reply-class graduation and Meat tracking-only rules were consolidated into the
focused SAM agent, Livestock/Meat workflows and Meat rules; all five sources
were archived intact.

Lifecycle: `WORKING / BATCH_24_SAM_REVENUE_COMPLETE /
BATCHES_25_TO_29_REMAIN`.

No customer send, provider action, order, reservation, payment, stock, farm,
database or runtime action occurred. The remaining physical queue is 52
documents. Automatic promotion is Batch 25 business-module reconciliation.

### Vault Cutover Batch 25 - 2026-08-18

Owner approved continuation. The exact manifest family contained ten
farm-calendar and meat/pork/SAM business-module sources. Their durable calendar,
production, commercial, cutting, payment, campaign, knowledge and allocation
rules were consolidated into focused Vault authority; all ten sources were
archived intact.

Lifecycle: `WORKING / BATCH_25_BUSINESS_MODULES_COMPLETE /
BATCHES_26_TO_29_REMAIN`.

No customer send, public post, provider action, order, reservation, payment,
stock, farm, database or runtime action occurred. The remaining physical queue
is 42 documents. Automatic promotion is Batch 26 planning/inbox reconciliation.

### Vault Cutover Batch 26 - 2026-08-18

Owner approved continuation. Eight historical planning/inbox sources were
archived intact. The active `CODEX_CHAT.md` and `ToDoList.md` paths were reduced
to minimal non-doctrine technical scratchpads so current tooling remains
compatible without retaining stale missions or priorities.

Lifecycle: `WORKING / BATCH_26_PLANNING_INBOX_COMPLETE /
BATCHES_27_TO_29_REMAIN`.

No mission execution, runtime, customer, provider, farm, database or hardware
action occurred. The remaining physical queue is 34 Storyworks documents.
Automatic promotion is Batch 27 Storyworks reconciliation.

### Vault Cutover Batch 27 - 2026-08-18

Owner approved continuation. The complete 45-file Storyworks/Chronicle Vault
private validation package was archived intact, including 34 Markdown sources
and all supporting Petra evidence artefacts. Storyworks is explicitly separate
from BEACON, farm media and deployed agent operations; its historical research,
pilot status and provisional owner decisions cannot authorize current work.

Lifecycle: `WORKING / BATCH_27_STORYWORKS_COMPLETE /
BATCHES_28_TO_29_REMAIN`.

No account, media, narration, edit, upload, publication, spend, runtime,
provider, database, customer, farm or hardware action occurred. The historical
physical-reconciliation queue is empty. Automatic promotion is Batch 28
transitional-document exit-test reconciliation.

### Vault Cutover Batch 28 - 2026-08-18

Owner approved continuation. All 72 transitional documents received exact
retirement ownership: 32 Google Sheets documents are bound to
`GS-LEGACY-RETIREMENT-V1`; 40 n8n documents are bound to
`N8N-LEGACY-RETIREMENT-V1`. Fresh repository evidence proves current fallback,
administrator, workflow, webhook, script and customer-channel consumers, so
both exits remain `BLOCKED_CURRENT_RUNTIME_DEPENDENCY`. Retaining them is a
bounded technical exception, not doctrine or permission for new legacy logic.

Lifecycle: `WORKING / BATCH_28_TRANSITIONAL_EXITS_RECONCILED /
BATCH_29_FINAL_ACCEPTANCE_REMAINS`.

No workflow, Sheet, runtime, provider, database, customer, farm or hardware
action occurred. Automatic promotion is Batch 29 final repository audit,
deployed Brain Guard acceptance and cutover lock.

### Vault Cutover Batch 29 - 2026-08-18

Owner approved final continuation. PRs #1097 and #1098 merged the read-only,
revision-bound Brain Guard audit into the existing Oom Sakkie five-minute
manager schedule. Render cron `crn-d9us4d3ncjis73adehrg` and web service
`srv-d6sijjkhg0os73f7regg` loaded exact revision `5d27e4af`. Two independent
provider-origin cycles at 21:05 and 21:10 UTC each checked 118 files, found zero
alignment defects, recorded heartbeat and next-audit time, and produced stable
digest `a15295c1cb713ccbbe870460c1909426c9ea1713a06104cc37706ea198e6dd24`.

Lifecycle: `COMPLETE / VAULT_CUTOVER_29_OF_29 /
DEPLOYED_BRAIN_GUARD_CONTINUITY_PROVEN`.

The later manager case phase failed in both cycles. That pre-existing
operating-spine timeout remains a separate current defect; Brain Guard audit
success does not claim a completed manager business cycle. The 72 transitional
documents remain safely retained behind the two named Batch 28 exit tests.

### OOM SAKKIE manager-case timeout closeout - 2026-08-19

The reusable post-Brain-Guard manager-case timeout is repaired on authoritative
main by PR #1103 (`181543e7`, repair commit `57934592`). The correction runs the
bounded read-only candidate collectors concurrently while preserving declared
result order, and refreshes only the provider-owned HERDMASTER, ROOTLINE and
BEACON case families before delivery. Focused current-main verification passed
27 manager-case source/worker tests; all three PR checks passed.

Render cron `crn-d9us4d3ncjis73adehrg` and web service
`srv-d6sijjkhg0os73f7regg` loaded exact authoritative revision
`14129a23cd4c1750eb442c0b4372f884c4c8774c`. Provider-owned cycles
`OOM-MANAGER-CYCLE-20260819T081022876461Z-FBAAF1BE8EC547ABA7753827E324D118`
and
`OOM-MANAGER-CYCLE-20260819T081530523321Z-029BA419094A4843BC8D1A93210ABE2D`
completed independently on the five-minute schedule. Each passed scheduled
Brain Guard, reconciled thirteen current cases, recorded zero exceptions and
suppressed thirteen unchanged deliveries. No terminal invoked the cycle and no
manual Telegram, customer, Meta, farm, provider or hardware action was used.

Lifecycle: `BUSINESS_COMPLETE / MANAGER_CASE_TIMEOUT_REPAIRED /
CONSECUTIVE_PROVIDER_CYCLES_AND_TRUTHFUL_SILENCE_PROVEN`.

The timeout mission is closed. Current specialist cases remain owned by their
existing specialist missions and standing authority; this closeout does not
duplicate SALES quotation, CORE recovery, ROOTLINE device work or BEACON
event-waiting work. Automatic continuation remains the existing provider cron;
unchanged evidence stays silent and materially changed evidence re-enters the
same canonical manager-case lifecycle.

### OOM-ROOTLINE-FERTILIZER-CONFIG-20260809 readiness observer - 2026-08-20

Source-only PR #1138 adds one zero-control-call fertilizer-mixer readiness
collector to the existing provider-owned five-minute Oom Sakkie general-manager
worker and durable manager-case rail. It verifies the exact registry/account/
device/channel binding for `100204d497` channel 2, canonical current provider
freshness, OFF, enabled 300-second native fail-stop and absence of an active
auxiliary execution. Changing provider receipt clocks are observation evidence,
not new case generations; unchanged state is replay-silent. The readiness case
is attention-only and cannot send Telegram, call a provider control method,
create a claim, write farm data or operate hardware.

Lifecycle: `WORKING / SOURCE_PR_CI_GREEN / RELEASE_HOLD`.

The implementation avoids every file modified by active PR #1127. Focused
tests, Brain Guard and independent ROOTLINE/replay and security/provider reviews
passed at source head `5757a1a4`; hosted exact-head CI passed before this durable
register reconciliation and must repeat against the final PR head. The serialized
release owner is Control Tower/owner review. Automatic promotion requires PR
#1127 collision recheck, explicit merge/deployment authority, verified deployed
revision, one provider-origin canonical readiness result with current/next cycle,
and a later terminal-independent provider-origin cycle. No owner action, provider
readback, secret/configuration change, merge, deployment or hardware action was
performed by the development terminal.

### RMQ-20260813-04 B/C lifecycle truth repair - 2026-08-20

Owner-observed and GENERAL-inspected evidence reopened the existing operational
irrigation lineage: canonical history proves two early-20-August C segments,
while the shared Telegram daily presentation mapped `Completed` to `Hold` and
printed fixed false lifecycle fields. B had a fresh `Run now` recommendation but
did not advance into governed execution. The exact canonical B eligibility,
deferral/rejection and tank-gate result remain `Unknown` in this source worktree:
`DATABASE_URL` is absent, the deployed owner-status route correctly returned
403 without an owner session, and no in-app browser session was available. The
healthy deployed web service and historical manager cycles do not fill that gap.

Lifecycle: `REVIEW_HOLD / SOURCE_PR_1140_OPEN / RELEASE_HOLD /
CANONICAL_READBACK_REQUIRED`.

The current branch adds one read-only `rootline_zone_lifecycle.v1` projection
for `Recommended`, `Revalidating`, `Eligible`, `Authorized`, `Started`,
`Completed`, `Held` and `Failed`; the specialist result, persisted reassessment,
application owner-status projection and Telegram formatter consume that shared
shape. Completed history outranks later recommendation wording and can no longer
render as Hold. Each Hold exposes one supported reason or `Unknown` and assigns
the next action to ROOTLINE. Existing standing-water execution eligibility is
retained: absent/stale tank evidence does not independently block commissioned
B/C, while fresh adverse water, weather, controller, concurrency and shutdown
evidence still fail closed. Existing canonical job identity/history, atomic
claims, replay suppression and scheduler retry rails are reused; no database,
queue, scheduler, approval or Telegram lifecycle is added.

PR #1126 is governance collision evidence only because it modifies this
register and the Mission Standard; its current head must be reconciled before
final PR preparation without importing its lifecycle claims as runtime truth.
Source-only PR #1140 is the single review rail; a later serialized merge/deploy
decision remains outside this terminal's authority. Business completion still requires the
deployed ROOTLINE actor to produce a fresh B execution or one exact truthful
blocker, provider/canonical readback, physical proof and a later
terminal-independent cycle. This terminal is forbidden from operating B/C,
invoking the worker, controlling a provider or manufacturing acceptance.

## 2026-08-20 - DOCUMENTS DMQ-20260816-01 Green print continuation

The same `DMQ-20260816-01` mission resumed on branch
`feat/green-print-bridge-20260820` and PR #1150 from preserved clean head
`8ca84260`, one commit ahead of exact-current main `2548d99a`. PR #1009 remains
open and unmerged; its historical two-line registration is lineage evidence
only and is superseded by the current register record.

The source candidate now includes deterministic A4 weekly-sheet PDF revision
and SHA-256 binding, an exact existing-protected-claim payload, a private
crash-recovery adapter ledger with fenced lease, persisted pre-submission
attempt, reconciliation-before-retry, ambiguous Hold, 48-hour retry then
protected Continue/Cancel, restart recovery and temporary-PDF deletion, plus an
unapplied private Supabase canonical job/event migration with append-only audit
enforcement. Tests are synthetic and non-actuating. No print, Telegram send,
farm write, migration, deployment, credential, Home Assistant, CUPS, printer or
network action occurred.

Lifecycle remains `RELEASE_HOLD / ENABLING_SOURCE_ONLY`; strategic class
`CURRENT_BLOCKER`, recovery WIP slot 3. OWNER OUTCOME ACHIEVED is `NONE` and the
capability is not usable now. Automatic continuation remains the same mission
after normal review/merge and an explicitly authorized serialized migration and
deployment decision. Physical commissioning and one genuine authenticated Oom
Sakkie request require a later separately protected on-site window; only exact
canonical/provider/physical proof plus a later terminal-independent cycle can
close the mission.

Exact-current source evidence: 33 focused document/app tests pass, deterministic
Brain Guard reports zero findings, `git diff --check` passes, and Docker builds
and inspects the package as `linux/arm64` with the required Home Assistant and
OCI labels. Container inspection finds CUPS `cupsd`, `lp`, `lpstat` and
`lpadmin`, compiles the embedded Python, and validates the entrypoint shell.
Security/data-integrity review additionally binds the intake path and private-CA
path in source, rejects redirects and public DNS resolution, requires exact
CUPS provider identities, and reconciles persisted local attempts before new
intake. This remains synthetic terminal-invoked engineering evidence only.

#### 2026-08-21 installable-app continuation

The same branch was additively reconciled with authoritative main
`278f4b0b75be72a0a0e5f9af09e9b67699c1912a`, preserving the newly merged Oom
Sakkie owner-attention work. Official Home Assistant constraints support an
aarch64 protected app without privileged host access. `repository.yaml` and
`green_print_bridge/` now provide local CUPS, automatic worker polling, exact
canonical/protected envelope intake, verified private HTTPS PDF retrieval,
fixed queue/options, provider observation, `/data` recovery, tmpfs cleanup,
redacted health/logs, cold backup and rollback/uninstall guidance. Tests remain
synthetic and non-actuating.

Lifecycle remains `RELEASE_HOLD / ENABLING_SOURCE_ONLY`; strategic class
`CURRENT_BLOCKER`, recovery WIP slot 3. No app was installed or registered, no
secret/certificate/device fact was collected, and no canonical/provider/hardware
effect occurred. Automatic promotion trigger: reviewed PR merge, separately
authorized migration/deployment and private on-site commissioning. Business
completion still requires the deployed Oom Sakkie actor's fresh authenticated
natural request, one canonical job, provider-origin CUPS readback, exactly one
physically confirmed page, cleanup/follow-up and a later terminal-independent
cycle.

#### 2026-08-21 DMQ exact-head review correction

Independent review requested changes at `4b6734fbed58ef29b3301cabdbd89332f68e82c7`.
The same mission and branch now replace the installable worker's plain claimable
GET/local-only fence with canonical atomic claim leases and fenced idempotent
transitions; add protected Continue/Cancel and known-CUPS cancellation; pin
canonical HTTPS and private IPPS transport; bind queue/provider evidence; fail
closed on restore conflict, corrupt/partial ledger and low disk; and separate
process liveness from business Hold. Bounded initialization launches dedicated
non-root `greenprint` and `cupsd` identities with narrowed AppArmor access.

This is correction-stage source and synthetic test evidence only. No migration,
installation, deployment, credential, endpoint, Supabase, Telegram, CUPS,
printer or physical effect occurred. OWNER OUTCOME ACHIEVED remains `NONE`;
usability remains `NO`. Lifecycle becomes `REVIEW_HOLD / ENABLING_SOURCE_ONLY`
after push. The automatic next action is fresh independent exact-head review of
PR #1150. Only later separately authorized migration/deployment/commissioning,
a genuine natural request, exact canonical/provider evidence, one correct page,
cleanup/follow-up and a later terminal-independent cycle can close the mission.

## 2026-08-22 Control Tower current-main intake and dispatch reconciliation

### HERDMASTER-NATURAL-HEALTH-LOSS-1 / OOM-INTAKE-SLICE-1 defect

GENERAL's Pig 161 Brain Guard finding is consolidated into the existing natural
health/loss mission as `CURRENT_BLOCKER`; it is not a new mortality, welfare,
language, Telegram, queue, router, confirmation or database mission. Pig 161 is
sealed historical/provider evidence and must not be replayed or mutated.

The retained owner outcome is one natural death report, one concise preview in
the authenticated recipient's configured language, one protected confirmation,
atomic supported mortality plus attributable welfare-case effects, canonical
readback-controlled completion and only genuinely unresolved follow-up. Charl's
canonical notification language is English with English buttons. Anton's is
Afrikaans with Afrikaans buttons. Inbound language does not silently change the
stored output preference, and one message must never mix languages.

The reusable defects are: the current mortality preview exposes audit/technical
language; the inspected confirmed writer does not prove same-boundary creation,
append and death closure of the attributable welfare episode or reconciliation
of obsolete living-animal checks; and completion wording is not proven to follow
canonical readback. Unrelated welfare cases and distinct disposal, biosecurity
or mortality work remain open. No diagnosis, treatment, cause/time invention or
new authority is included.

Current-main terminal dispatch is directly proven. The isolated terminal session
`01a02903-1cd6-7f41-a7dd-34086a81351c` is active in
`.worktrees/herdmaster-health-loss-welfare-language-20260822`, branch
`fix/herdmaster-health-loss-welfare-language-20260822`, exact clean base
`a6b3112fe3a3008af763685e5b1ca31ab814963f`. Its first contained stop exposed a
stale Control Tower line-count instruction; Control Tower corrected it without
scope restart. The terminal acknowledged and resumed against the authoritative
1,127-line Standard blob `3002b94713e286c4eb2019419c438cc378c337fa`,
Protocol `8fbd0b9c9160164e31a17a2cbfa51ab88792a909`, Template
`1233aee625e45821a685614a33b1eb101c666ffd` and Programme
`fb44d7f86c47e605c283ed33c28ba2c4267d6edb`.

Lifecycle is `WORKING / SOURCE_AND_TEST_IMPLEMENTATION_ACTIVE`; this is **NO
BUSINESS OUTCOME**. No Pig 161 replay, provider message, production write,
schema/profile mutation, merge or deployment is authorized. Automatic
continuation is source audit, reusable repair, tests, Brain Guard, specialist
and security review, clean PR and complete handover. Later gates remain
independent review, serialized release, exact loaded revision, a fresh genuine
mortality event through the deployed Oom Sakkie/HERDMASTER actor, canonical and
provider readback, safe replay, automatic follow-up and a later
terminal-independent cycle. Owner action is none until one exact protected
release/profile/schema boundary is proven or the fully deployed actor is ready
to receive a genuinely new natural event.

### GREEN 0.3.2 reviewed source continuation

The existing Green commissioning outcome remains active under the owner's prior
bounded commissioning direction. PR #1164 exact head
`da0f67cf0eb53616582f37c054038b6f71b5fdd0` is a reviewed source candidate:
67 focused/wider tests passed and different-agent independent review passed
after repairs for DNS rebinding/TOCTOU, private certificate/SAN trust and
negative-test gaps. Hosted CI was queued at the observation time.

The candidate binds exact approved Render public-PKI HTTPS without redirects or
public IP pin, preserves the private-pinned profile, uses strict token/farm/Green
headers and fixed paths, and confines IPPS to a single private pin with SAN-only
TLS preflight, private CA policy, hostname-to-pin binding before CUPS and exact
AppArmor writes. No publish, install, configuration, identity, queue, document,
job, print or physical effect occurred. Lifecycle is `REVIEW_HOLD /
EXACT_HEAD_CI_PENDING`; **NO BUSINESS OUTCOME**. Green remains stopped with boot,
watchdog and auto-update off. Automatic promotion is exact-head CI pass followed
by Control Tower serialized release review; commissioning, a genuine physical
page, cleanup/follow-up and a later terminal-independent cycle remain separate
protected acceptance gates. Owner action is none now.

All five exact-head checks subsequently passed. Control Tower verified that the
publication job is not triggered by merge or push: it requires a separate manual
workflow dispatch with `publish=true`, exact expected source commit and a main-
branch identity check. PR #1164 was therefore merged normally at exact reviewed
head as main commit `429a91ffd3dd4f38faadeb9fb0f19f202ea87537` without package
publication. Green advances only to `INTEGRATED_SOURCE / PACKAGE_UNPUBLISHED /
RELEASE_HOLD`; **NO BUSINESS OUTCOME**. The next protected boundary is one exact
manual dispatch to build, publish, sign and attest the immutable 0.3.2 arm64
package from the exact main revision. No install, configuration, start, queue,
job or print is implied by that later package publication.

Owner authorization was subsequently received for that exact bounded package-
publication boundary. Control Tower dispatched the reviewed workflow exactly
once as GitHub Actions run `32568228754` from exact main
`429a91ffd3dd4f38faadeb9fb0f19f202ea87537`; both the verification job and the
publication job completed successfully. The immutable image is
`ghcr.io/crewless9086/amadeus-green-print-bridge:0.3.2` at digest
`sha256:92d034dd4a582b82f4ed09dd84434e47cf21f462f6e9a291d8a94a8227527369`.
The preserved release packet proves one `linux/arm64` OCI manifest, matching
source/version config labels, keyless Cosign verification, SPDX 2.3 SBOM,
provenance attestation and SBOM attestation; packet hashes matched the emitted
digest-bound receipt. Lifecycle advances to `IMMUTABLE_PACKAGE_PUBLISHED /
INSTALLATION_NOT_AUTHORIZED / COMMISSIONING_PENDING`; **NO BUSINESS OUTCOME**.
No installation, Home Assistant configuration, credential, start, CUPS/queue,
document, print, database, farm or provider effect was performed. Green remains
stopped and unavailable to the owner until a separately authorized installation
and commissioning boundary is completed and physically accepted.

The subsequent bounded 0.3.2 installation/zero-job commissioning window was
stopped before installation on a required precondition mismatch. Authenticated
Home Assistant readback showed installed version `0.3.1`, `Stopped`, with Start
on boot, Watchdog and Auto update OFF, while every required commissioning field
remained empty: canonical origin/endpoint, bearer credential, farm/Green/
printer/fixed-queue identities, registry version and printer URI. This matches
the earlier 0.3.1 containment record; the values described as "previously
approved" had been authorized for creation but were never actually created or
bound. Because this window expressly prohibited any new credential or identity
and required stop-on-mismatch, Control Tower did not click Update, install
0.3.2, save configuration or start Green. Zero documents, jobs and physical
prints were preserved. Lifecycle remains `IMMUTABLE_PACKAGE_PUBLISHED /
INSTALLATION_BLOCKED_BY_MISSING_BINDINGS / COMMISSIONING_PENDING`; **NO BUSINESS
OUTCOME**. The next owner boundary must authorize creation and protected storage
of exactly one least-privilege credential and the matching canonical identities,
then installation and zero-job commissioning against the already published
immutable digest.

The next owner-approved identity-registration/install window completed further
read-only preflight and then stopped before any write. Home Assistant identifies
the intended device as the HP OfficeJet Pro 8120 series. Direct private-LAN TLS
readback proved its self-signed certificate is current through 2030 and carries
the printer hostname as its sole SAN; local DNS resolves that hostname uniquely
to the same private address reported by Home Assistant. The 0.3.2 IPPS hostname-
pin contract is therefore coherent. However, its required trust anchor is not
present at the fixed Home Assistant path `/config/private-ca.crt`, and no existing
protected file-management channel is available: the installed-app inventory has
no file-management/terminal app and the established Home Assistant SSH ports are
closed. Installing another management app was outside the authorized boundary,
and weakening or bypassing TLS is prohibited. Control Tower therefore created no
credential or registry row, performed no Render/Supabase/Home Assistant write,
did not install 0.3.2, did not save options and did not start Green. Lifecycle is
`IMMUTABLE_PACKAGE_PUBLISHED / PRINTER_IDENTITY_VERIFIED /
TRUST_ANCHOR_PLACEMENT_BLOCKED / COMMISSIONING_PENDING`; **NO BUSINESS OUTCOME**.
The next bounded prerequisite is a protected method to place only the verified
printer certificate at the fixed trust path, after which the already-approved
identity, installation and zero-job commissioning sequence can be reauthorized
and completed.

Owner subsequently authorized installation of the official File editor and
confirmed immediate transmission of the verified public printer certificate to
the local authenticated Home Assistant instance. File editor 6.1.0 was installed
with Start on boot, Watchdog, Auto update and sidebar access OFF. The Chrome file-
chooser path remained unavailable even after its required extension permission
was enabled, so no upload occurred. A native File editor fallback created the
authorized `/config/private-ca.crt` name, but the editor retained modal focus:
the certificate text was interpreted as a filename and rejected with filename-
too-long before content save. This left only a zero-byte `private-ca.crt`; no
certificate content was written. Per stop-on-mismatch authority, Control Tower
did not retry, overwrite or delete it, and stopped File editor. Green remained
0.3.1 stopped and unchanged; zero queue, document, job and print effects
occurred. Lifecycle is `TRUST_FILE_EMPTY / FILE_EDITOR_STOPPED /
COMMISSIONING_PENDING`; **NO BUSINESS OUTCOME**. A fresh exact overwrite boundary
is required to replace only the empty file with the already verified public
certificate and prove readback before any Green identity or installation work.

Owner then authorized that exact bounded overwrite boundary. Control Tower
started only the installed official File editor, opened the existing zero-byte
`/config/private-ca.crt`, entered the already verified public HP certificate and
saved once. A fresh page reload independently read back the exact PEM bytes. The
readback certificate matched SHA-1 fingerprint
`D9A77D87534CF02CF992564E5863371870A4DCF6`, SAN `DNS:AmadeusKantoor`, the
self-signed HP subject/issuer identity and validity from 15 December 2025 through
14 December 2030. File editor was then stopped; the resulting control surface
showed Start available, Stop absent, and all four automatic controls unchecked:
Start on boot, Watchdog, Auto update and sidebar access. No Green installation,
start, credential, registry, queue, document, print, database, farm or provider
action occurred. Lifecycle advances to `TRUST_ANCHOR_PLACED_AND_VERIFIED /
FILE_EDITOR_STOPPED / GREEN_COMMISSIONING_PENDING`; **NO BUSINESS OUTCOME**.
The trust prerequisite is now cleared, but Green remains unavailable to the
owner until its separately governed identity registration, immutable 0.3.2
installation and zero-job commissioning are completed and later physically
accepted.

Owner subsequently directed Control Tower to continue all safe in-scope work
under standing authority without requesting a new approval at each reversible
step. Control Tower created one new least-privilege Green worker token directly
in the protected Render environment and one matching inactive canonical device
registry row. The identity set binds farm, Green, printer, fixed queue, registry
version and the exact production HTTPS origin; it is inactive pending health
proof. Home Assistant then updated the stopped app from 0.3.1 to 0.3.2, with
the UI confirming installed and latest version 0.3.2 and all automatic controls
remaining OFF. Configuration entry is not complete: focusing the protected
password field opened a Chrome password-manager/extension popup that blocks the
approved browser-control channel. The form was not saved and Green was not
started. Zero canonical jobs, CUPS jobs, documents or physical prints occurred.
Lifecycle is `GREEN_0.3.2_INSTALLED / CANONICAL_IDENTITY_INACTIVE /
CONFIGURATION_BLOCKED_BY_LOCAL_BROWSER_POPUP / COMMISSIONING_PENDING`;
**NO BUSINESS OUTCOME**. The only owner action is the physical dismissal of that
local Chrome popup; it is not a request for additional operating authority.

Fresh independent review rejected SAM Livestock PR #1163 exact head
`d578e8322097258be3b804b3857fb5cd1917ede5`: the production call path leaves
authoritative Meta page and attribution expectations empty, so payload-supplied
campaign identity and invalid or absent chronology can be promoted into retained
attributed context. All tests and hosted CI passed but did not cover this wiring
defect. Automatic customer sending remains OFF and no customer/provider effect
occurred. Control Tower retained the existing SAM five-customer mission and
dispatched a source-only repair terminal on the same PR lineage; **NO BUSINESS
OUTCOME**.

Fresh PR #1161 post-release audit proved Render healthy at loaded revision
`429a91ffd3dd4f38faadeb9fb0f19f202ea87537`, descending from the reviewed merge,
but found the genuine farrowing journey is not production-ready. No applied
migration admits `herdmaster_record_farrowing_litter` into the protected-action
constraint, and migration `202608220001` is absent from the closed production
migration allowlist. A genuine report would fail before confirmation. Control
Tower prohibited replay or owner testing and dispatched a bounded source-only
database-release repair for a new append-only action-kind migration, allowlist
coverage, tests, independent review and later serialized production readback.
The mission remains `DEPLOYED_CODE / DATABASE_AUTHORITY_BLOCKED /
GENUINE_EVENT_PROHIBITED`; **NO BUSINESS OUTCOME**.

The Chrome password-manager obstruction required a manual local paste attempt.
Home Assistant rejected that attempt because the popup had also discarded every
non-secret field. Its validation error echoed the attempted credential, so
Control Tower immediately rotated and invalidated it in Render and cleared the
local clipboard. A second credential appeared in Home Assistant's YAML validation
error while diagnosing the public-profile endpoint contract; Control Tower also
rotated and invalidated that value before proceeding. Neither exposed credential
can authenticate now. The third credential was transmitted only through the
authenticated local YAML options editor, saved with the complete matching
identity set, and read back without disclosure. The temporary transfer file was
then deleted and transient controller memory cleared; the current credential
remains only in the protected Render and Home Assistant stores.

The saved configuration exposed a source contract defect: Home Assistant's 0.3.2
schema treats `canonical_endpoint_ip` as required even though
`public_pki_exact_origin` correctly forbids an endpoint pin. An explicit empty
string satisfies both current layers and was saved; source still needs to make
that profile-specific contract unambiguous and regression-tested. Immediately
before start, canonical readback proved one matching inactive registry row and
zero print jobs/events. The bounded zero-job start then failed before worker or
CUPS activity with exact log `/bin/sh: can't open '/init': Permission denied`.
Home Assistant returned the app to stopped state with Start available, Stop
absent and all three automatic controls OFF. Post-failure canonical readback
again proved zero jobs and events; because failure precedes queue initialization,
no CUPS job or physical print effect occurred. The registry remains inactive and
uncommissioned. Lifecycle is `GREEN_0.3.2_CONFIGURED / STARTUP_PACKAGING_BLOCKED /
ZERO_EFFECT_CONTAINED / COMMISSIONING_PENDING`; **NO BUSINESS OUTCOME**. Control
Tower dispatched a source-only 0.3.3 startup/AppArmor and public-profile schema
repair on the existing Green lineage. Publication, update and the next zero-job
start remain later serialized stages; Green must not be started again on 0.3.2.

Subsequent Control Tower work retained that containment and advanced three
existing lanes without misclassifying technical state as owner completion.
SAM PR #1163 was repaired after two independent production-wiring failures,
then passed a different-agent exact-head review at
`c86c481383aecbae9a532a50e810e6fbf1b5b465`. Control Tower merged it as
`7806613ab666a92d769db3bb129ef6ae8871e30e`; Render reported that revision live,
and the later skills-only main revisions also contain it. Customer auto-send
remains OFF. No genuine five-customer provider cycle or later unattended cycle
has occurred, so SAM remains `SOURCE_DEPLOYED / OPERATIONAL_ACCEPTANCE_PENDING`;
**NO BUSINESS OUTCOME**. Obsolete patch-equivalent PR #1148 was closed to prevent
an independent duplicate merge. The separately owned BEACON nested provider-
readback defect remains logged without reprioritization.

HERDMASTER database-release PR #1167 repeatedly passed hosted CI while fresh
disposable-PostgreSQL review found fail-open schema, function, receipt, trigger,
ownership and privilege drift that the rail did not prove. Exact head
`465b2e3bad71232d36e2e2016a3aa69aba9aca01` closes earlier families but failed
another independent review: malformed historical schema could still receive an
applied receipt; receipt-anchor ownership/ACL/FK/trigger and protected-column/
role privileges were incomplete; legacy anchoring could certify corrupt
identity; a rejected run could retain bootstrap-trigger replacement; and
receipt hashing depended on session time zone. The head remains unmerged and
no production migration or farm event occurred. The same PR lineage is back in
bounded implementation with workspace-local artifacts. Lifecycle remains
`DATABASE_RELEASE_REPAIR / INDEPENDENT_REVIEW_FAIL / IMPLEMENTATION_ACTIVE`;
**NO BUSINESS OUTCOME**.

Green PR #1169 introduced a real arm64 custom-AppArmor startup gate rather than
relying on manifest inspection. That gate has progressively proved and repaired
the original `/init` denial, Alpine `su-exec` path, S6 runtime permissions,
public-profile blank-pin normalization, CRLF/umask packaging, initializer import,
least-privilege trust-store rules and workspace-local probe cleanup. It now
reaches a running healthy container and `event_waiting`, but exact hosted proof
shows CUPS is not yet running because the attempted fully unprivileged scheduler
bootstrap cannot perform CUPS' required startup ownership checks. The lane is
reconciling the minimal root-bootstrap/drop-privilege model without granting
broad `/etc/cups` mutation. Every publish job has remained skipped; Home
Assistant still has 0.3.2 stopped with automatic controls OFF, registry inactive,
and zero canonical jobs/events/physical prints. Lifecycle remains
`GREEN_0.3.3_SOURCE_REPAIR / REAL_ARM64_GATE_FAIL / COMMISSIONING_PENDING`;
**NO BUSINESS OUTCOME**.

Owner identified repeated permission popups and missing reusable Codex operating
procedures as avoidable supervision work. Control Tower implemented and
independently forward-tested three repository-scoped development-control skills:
`control-tower-operate`, `amadeus-implement` and
`amadeus-operational-acceptance`. PR #1170 merged as
`ce286fb7fc299bb7e044a24030bf0709060e2208`; fresh-session discovery, all three
official validators and realistic behavior tests passed. PR #1171 then added a
two-boundary autonomy contract and merged as
`5a91fd445eced361e715d141790116503eb15803`: canonical durable documents remain
at governed paths, mission-working evidence routes to ignored
`control-tower-artifacts/<mission-or-pr>/`, and disposable output routes to
ignored `.codex-runtime/missions/<mission-or-pr>/`. Multi-child forward-testing
proved workers received exact paths, wrote nowhere external and retained all
protected-action boundaries. This is a delivered owner-requested development-
control outcome that reduces routine approval interruptions; it is not an
Amadeus runtime capability and does not satisfy the still-open Green,
HERDMASTER or SAM operational outcomes.

### Strategic WIP and dispatch truth

Autonomy Recovery Mode remains in force. Two current-blocker tracks have fresh
activity: the existing Green transport/commissioning track and the consolidated
Oom Sakkie/HERDMASTER mortality-welfare-language repair. No third implementation
track is dispatched by this assessment. SAM PR #1163 and other eligible source
work are preserved without interruption; old health/loss, intake, mortality and
welfare worktrees remain historical/collision evidence only. The existing CORE
runner artifacts are stale and `supervisor.stop` is present, so no CORE pickup,
background work or release-lane ownership is claimed. The serialized production
release lane is free of a proven active mutation owner but is not acquired by
either source terminal.

## 2026-08-23 - Green read-only recovery continuation and HERDMASTER mortality review

This entry appends current evidence without changing mission priority or
creating a new lineage.

Green PR #1190 reached final independent PASS at exact head
`727944f349a3d1af2595fbc3e0f98eec7dbc85ff` and merged to authoritative main as
`301e65b7b339436b9a0a3270a62face26cb4eddd`. Post-merge CI runs
`32633003500`, `32633003487` and `32633003510` all succeeded. This is reviewed,
integrated technical state only; it is not installation, commissioning or an
owner outcome.

Read-only Green run `32633148563` subsequently passed the exact four-record
signature parser, immutable image/tag/index/manifest checks and attestation
inventory. It then failed without an actionable marker in the final
verification step before receipt or packet creation. All effect-bearing jobs
were skipped and no signing, attestation, image, tag, installation, document,
job or physical-print mutation occurred. Diagnosis continues automatically on
the existing Green 0.3.6 lineage. Lifecycle is
`EXACT_PARSER_AND_IMMUTABLE_INVENTORY_VERIFIED / FINAL_VERIFICATION_SILENT_FAIL /
NO_RECEIPT_OR_PACKET / READ_ONLY_DIAGNOSIS_ACTIVE`; **NO BUSINESS OUTCOME**.
OWNER ACTION: NONE.

HERDMASTER/Oom Sakkie PR #1191 initial exact head
`3114c7f63a06f247e2a204db4b08c9f186cffd8e` received an independent BLOCK.
The review identified four exact P1 requirements: the new PostgreSQL welfare
event inserts omit the mandatory positive `sequence_no`; the writer does not
discover, lock, append to and close the attributable existing open welfare case;
pen occupancy and availability completion is inferred rather than proved by
canonical projection readback; and the branch was behind authoritative current
main and therefore required reconciliation plus fresh exact-current gates.

The same review retained the correct bounded direction: Anton receives only
governed farm-manager mortality authority in addition to his existing farm and
irrigation envelope, without CORE, CHARLIE, permission-administration or
unrelated authority; authorization reuses shared capabilities rather than an
`is_owner` promotion; preview and confirmation remain bound to the same actor,
card and claim with replay/concurrency containment; and English/Afrikaans intake,
questions, previews, buttons, failures and completions follow the authenticated
recipient language. Distinct mortality, disposal and biosecurity work remains
excluded from living-welfare closure. No Pig 126, provider, production or
database effect occurred. Lifecycle is
`SOURCE_REVIEW_BLOCKED / SCHEMA_AND_ATTRIBUTABLE_CASE_REPAIR_REQUIRED /
EXACT_CURRENT_RECONCILIATION_REQUIRED`; **NO BUSINESS OUTCOME**. OWNER ACTION:
NONE.

## 2026-08-23 - Control Tower bounded-attempt and outcome-driving correction

Charl identified that repeated implement-review-dispatch-fail cycles were
consuming time without producing an owner outcome. Control Tower accepts this
as an operating-method defect. High commit, review, test or workflow counts do
not offset a missing physical or business result and must not be reported as
progress sufficient to continue the same approach indefinitely.

Effective immediately, an existing mission may make at most three contained
attempts against the same external acceptance boundary without achieving a
materially deeper acceptance state. After that threshold, Control Tower must
stop further dispatches on that design, preserve exact zero/effect evidence,
and perform a design-simplification review before another attempt. A new attempt
is permitted only when exact live sanitized inputs prove the prior failure,
the revised contract removes the demonstrated brittle assumption, an
independent reviewer passes the exact head, and the next run has attributable
stage diagnostics. Rewording, adding retries, expanding synthetic fixtures or
moving the same assertion does not reset the threshold.

Provider evidence comparisons must distinguish stable governed facts from
volatile transport/envelope representation. Stable semantic identity includes
the authorized record set, counts, predicate and subject identities, immutable
digests, source revisions, run/attempt identities, certificate/transparency-log
identity and required chronology. Byte equality may be required only for data
whose canonical serialization is itself an authoritative contract. Two or more
direct live read-only snapshots must expose and document any excluded volatile
fields; added, removed or materially changed governed evidence must still fail
closed.

Green crossed this threshold in read-only run `32633797982`. The run passed
signature identities, attestation identities/counts, immutable artifact checks
and canonical inventory, then failed exactly at
`attestation_pre_post_equality` because two provider snapshots were compared as
bytes. All effect-bearing jobs skipped and no registry, evidence, installation,
document, job or print effect occurred. No fourth Green dispatch is authorized
until repeated direct live snapshots identify the non-authoritative variance
and a reviewed stable semantic equality contract replaces the brittle byte
comparison. Lifecycle is `DESIGN_SIMPLIFICATION_REQUIRED /
LIVE_SNAPSHOT_DIFF_ACTIVE / FURTHER_DISPATCH_HELD`; **NO BUSINESS OUTCOME**.
OWNER ACTION: NONE.

Control Tower will keep Green as the serialized owner-outcome lane after this
contract repair and then proceed directly through installation, commissioning,
one controlled print and physical readback. Independent non-colliding Anton
health/loss source work may continue; BEACON and other release candidates remain
held rather than generating review activity that does not unblock the current
owner outcome.

## 2026-08-23 - Green 0.3.6 release closure and Home Assistant installation attempt

The bounded design simplification was completed and independently reviewed in
PR `#1193`. Exact head `458a03d228ff5e4dd130863f8e7ba579c3873e76`
replaced byte comparison of expiring provider URLs with fail-closed semantic
comparison of the stable signed evidence. It merged as
`3faf0ec00896662de99b794aeb4084da77b03edf`; all post-merge gates passed.
Read-only verification run `32634662022` succeeded and produced authoritative
packet artifact `9491984305`, archive digest
`sha256:03e90878a4a2111a4eecc4d003488a8fcc96d34accf9b872e4b0d2e0da02f075`.
Green 0.3.6 release evidence is therefore closed. This is technical release
completion, not an owner outcome.

At the owner's explicit action-time instruction to install Green 0.3.6, Control
Tower opened the existing Home Assistant Green app page. It showed installed
version `0.3.5`, available version `0.3.6`, and a stopped app. Control Tower
submitted the Home Assistant `Update` action exactly once. The UI entered
`Installing`; no duplicate update was submitted. The browser connection then
became unresponsive during readback. Three bounded read-only attachment/state
checks failed without producing authoritative post-installation state.

Lifecycle is `INSTALLATION_REQUESTED / POST_INSTALL_READBACK_BLOCKED`.
Installation is not claimed complete until Home Assistant visibly reports
current version `0.3.6`. Commissioning, start, zero-job health, controlled print
and physical readback remain outstanding. The next action is a single owner UI
refresh/readback to restore the blocked external boundary; it is not another
approval and must not trigger a second update.

Owner readback subsequently proved Home Assistant reports `Current version:
0.3.6`, so installation is complete. The same authoritative UI reports app
state `Error`; Green is therefore not commissioned and no owner outcome or
print is claimed. Control Tower attempted one fresh read-only browser attachment
to inspect the app controls/logs after the owner's refresh. The tab was listed
correctly but its DOM remained unresponsive, so no start action was repeated and
no configuration was changed. Lifecycle is now `INSTALLED_0.3.6 /
STARTUP_ERROR_DIAGNOSIS_BLOCKED_ON_LOG_READBACK`.

Owner-supplied provider log readback removed that uncertainty. The S6 launcher
continued after `/bin/sh: can't open '/init': Permission denied`, so that line is
not the decisive terminal marker and no broader `/init` authority is justified.
The exact terminal marker is `green_startup_failed stage=mount_validation
reason=ca_missing_or_empty`. Source reconciliation proved 0.3.6 moved the
certificate from the established app-owned `/config/private-ca.crt` contract to
`/homeassistant/private-ca.crt` and added a broader `homeassistant_config` map.

Control Tower created bounded current-main repair PR `#1194`, exact head
`7e641543`, for immutable candidate 0.3.7. It restores the sole read-only
`addon_config` map and exact `/config/private-ca.crt` access across initializer,
queue preflight, worker, AppArmor and real startup probe; removes the broader HA
config map; and updates the normal publication path while retaining historical
0.3.6 recovery evidence constants. Focused local verification is `115 passed`;
fresh independent review and hosted exact-head gates are pending. No install,
start, certificate, registry, document, print-job or physical effect occurred.

Green lifecycle is `INSTALLED_0.3.6_FAILED / PR1194_0.3.7_REPAIR_REVIEW_ACTIVE`.
Commissioning must separately prove the certificate exists inside Green's
private Supervisor `addon_config` mount; a File Editor path named `/config` is
not by itself proof of another app's private mount. **NO OWNER OUTCOME**.

Terminal sweep: PR `#1191` exact head
`5746f9adc57193f5fc7ede5e9bc19f239e39efdd` received a fresh independent PASS,
is clean/mergeable against exact main `3faf0ec00896662de99b794aeb4084da77b03edf`,
and all hosted gates pass. No live or Pig 126 effects occurred. PR `#1184`
remains migration-transport lineage requiring current-main reconciliation; PR
`#1182` remains BEACON/SAM lineage requiring current-main reconciliation. CORE
has no current release PR and requires current-main runtime/heartbeat readback.
No direct file collision exists among those three open release candidates;
release effects remain serialized behind Green. OWNER ACTION: NONE.

## 2026-08-23 - Green 0.3.7 no-mount trust repair and hosted runtime continuation

The initial PR `#1194` mount restoration was rejected after current Home
Assistant contract review proved `addon_config` is a separate app-private
location and cannot reuse the certificate previously saved in Home Assistant's
main `/config`. Control Tower simplified the design: Green now accepts the
commissioned printer certificate SHA-256 fingerprint, retrieves the certificate
only from the configured private literal IP endpoint, verifies exact fingerprint
and hostname identity, and installs only that verified public certificate inside
the container. No Home Assistant configuration mount or committed certificate
is required.

Hosted arm64/AppArmor runs successively exposed real startup boundaries rather
than owner outcomes: validation ordering, interpreter ordering, `/sbin/su-exec`
AppArmor execution, and then the long-lived unprivileged worker retaining the
root-private bootstrap CA path. Current exact PR head `7249ad39` points the
worker at the already verified root-owned mode-0644 installed certificate
`/etc/cups/ssl/site.crt` and performs an explicit `greenprint` readability check
before service execution. Focused verification is `116 passed`; diff check is
clean. Hosted run `32648715007`, job `97216884554`, has built the exact linux
arm64 image and is executing the real zero-job startup under package AppArmor.
It is still pending and is not claimed successful.

Green lifecycle is `INSTALLED_0.3.6_FAILED / PR1194_HEAD_7249ad39_HOSTED_ARM64_ACTIVE`.
No update, start, registry publication, document, print job or physical print
effect occurred in this continuation. **NO OWNER OUTCOME**. OWNER ACTION: NONE.

Terminal sweep remains: Herdmaster/Anton PR `#1191` is independently passed and
release-ready but requires migration reconciliation, deployment and Anton's new
provider-origin Pig 126 journey; BEACON/SAM PR `#1182` is independently passed
and release-ready with no META publication effect; CORE has no proved operating
cycle. Release effects remain serialized behind Green while non-colliding
read-only/source preparation is retained.

## 2026-08-23 - Owner-outcome audit and Green probe-loop correction

Control Tower confirms **NO BUSINESS OUTCOME** since the preceding handover.
Green remains installed as failed 0.3.6; PR `#1194` is not merged or published;
Herdmaster/Anton PR `#1191` and BEACON/SAM PR `#1182` remain open, mergeable and
fully green but are only Prepared; CORE has no proved live operating cycle.
Completed internal collaborators are not represented as visible terminals or
deployed agents. No active terminal delivery/acknowledgement/start evidence was
found outside Control Tower's direct Green work.

Green hosted run `32648966008` at exact head `630768d2` failed in the deliberate
negative `service_exec` test before the healthy journey. The test shadowed
`/opt/green/service.py`, but printer trust legitimately imports that same module,
so the artificial corruption caused an earlier `printer_trust` failure. This is
a test-probe defect, not evidence of another live production boundary. Current
head `fb600789` uses a bounded launcher shadow that permits only the certificate
readability preflight and fails only the service launch. Focused verification
remains `116 passed`; hosted arm64 run `32649186158`, job `97218017923`, is
active. **NO OWNER OUTCOME**. OWNER ACTION: NONE.

## 2026-08-23 - Operational spine promoted; Green held by owner priority

Charl explicitly changed the release order: Green is held until the other live
operational missions are producing genuine outcomes. This supersedes the prior
serialization of every release behind Green. PR `#1194` may retain its hosted
technical evidence, but Control Tower must not merge, publish, install or
commission another Green version while this hold remains.

The live system health endpoint concealed a material operating failure. Render
is loaded at exact main `3faf0ec00896662de99b794aeb4084da77b03edf` and the
schedulers continue firing, but today's ROOTLINE reassessments repeatedly
contain with `scheduled_reassessment_database_unavailable`, with zero Telegram
sends and zero hardware commands. The general manager cycle repeatedly claims
20 cases while confirming zero manager deliveries; BEACON reports a silent
publication cycle; no current daily farm-manager presentation or new irrigation
outcome was proven. This validates the owner's report that the deployed system
is effectively silent despite technical activity.

A bounded production-shaped component audit isolated two reusable source-read
defects. ROOTLINE's nested daily advisor consumed nearly its entire 18-second
deadline and the enclosing nine-reader group expired at 20 seconds. The daily
manager breeding snapshot also referenced
`current_canonical_litters.first_treatment_skipped_at`, a column not exposed in
production, and failed with SQLSTATE `42703`. No database, provider, farm or
hardware mutation occurred during diagnosis.

Current-main repair PR `#1195`, exact head
`d588622e5f82d0a365acb29df252f72140312b16`, gives the nested advisor an
immediate worker and a 25-second outer bound, and projects the optional litter
field through the row JSON shape so the absent field remains Unknown instead of
crashing the whole manager inventory. Focused verification is `84 passed`.
Against the live canonical data, the repaired ROOTLINE read returns a current
`Recommend` result and the breeding snapshot returns all 24 current litters.
Hosted exact-head gates, merge, deployment, live scheduler readback, provider
delivery and later unattended continuity remain required. This is a P0 repair
within the existing operational missions, not a new product mission and not yet
an owner outcome. OWNER ACTION: NONE.

## 2026-08-23 - Operational spine released; BEACON and Anton advanced

PR `#1195` passed all four exact-head hosted gates, merged as
`97d12e2c9f95eacf1c64b2e26d442625fc09eea7`, and was proven live on Render
before the next release. BEACON/SAM PR `#1182` was then refreshed onto that
main, passed all four hosted gates, merged as
`86fe618ac21a0c8f93d248fd8ac0f62fe94c77a9`, and was proven live. This removes
the contradictory public-livestock solicitation bypass that caused the owner to
decline card 3714. The declined card remains cancelled and is not replayed.

Herdmaster/Anton PR `#1191` was refreshed again onto the BEACON merge, passed
all four hosted gates including the disposable-Postgres mortality/welfare
transaction gate, and merged as
`6102ebab37d6fc9f64f29f91663267217be50f94`. Its Render deployment is active.
No Pig 126 record, old Telegram event, Facebook post, customer message,
irrigation hardware or Green state was mutated by these release steps.

Remaining acceptance boundaries are explicit. ROOTLINE must complete a natural
post-deployment scheduled reassessment without the prior database-unavailable
containment and later repeat unattended. BEACON must generate a new compliant
owner card from the deployed policy and may publish only after the protected
owner decision; SAM must then prove attributable customer intake. Anton must
send a new Afrikaans Telegram report for Pig 126 and press his own `Bevestig`
button; canonical and provider readback must prove the result. Green remains
held by owner priority. A read-only CORE probe exposed a separate historical
normalized audit write ending in `UndefinedColumn`; this finding is recorded
without reprioritizing it ahead of the active acceptance lanes. **NO BUSINESS
OUTCOME** at this checkpoint. OWNER ACTION: NONE.

## 2026-08-23 - Live operating proof and BEACON scheduler correction

The released operational-spine repair produced a genuine natural ROOTLINE
cycle. At 16:15 UTC the unattended reassessment completed successfully, sent
three Telegram lifecycle messages and issued one governed hardware command.
Canonical readback records zone `C12345` as `STARTED` at
`2026-08-23T16:17:30.151059Z` for a planned 60 minutes under event
`ROOTLINE-HISTORY-47ADA6606BF59A4E8672B033`; Telegram delivery message `3901`
is provider-confirmed. This is a real operational effect, but water flow and
safe completed shutdown are not yet proven. Control Tower retains the mission
through its due completion/readback and a later unattended cycle.

The natural general-manager cycle also delivered one BEACON case through
Telegram, but the message truthfully stated that no current proposal existed.
Production-shaped readback isolated the reason: the automatic scheduler still
called the retired livestock-enquiry solicitation builder, while the active
META policy correctly prohibits public livestock acquisition solicitation.
The existing compliant farm-awareness builder was present but unused.

Bounded repair PR `#1196` now routes scheduled BEACON work to a protected,
text-only farm-awareness card. It makes no stock, availability, price or sales
claim and contains no acquisition call-to-action. Genuine independently
initiated replies remain campaign-attributable and route privately to SAM.
Generic media is not inferred to have exact event/subject authority. Focused
verification is `104 passed`; all four hosted gates passed; the PR merged as
`7777ee05b37b8ca6d3227bf112433d481066dbcb`; and Render proved that exact
revision live with a healthy endpoint. Production-shaped canonical/config
readback builds status `beacon_livestock_awareness_ready` with a protected
campaign package.

This is released technical and operational preparation, not a marketing or
sales outcome. Acceptance still requires a natural deployed manager cycle to
deliver the new exact owner card, the protected owner decision, META provider
publication/readback and later genuine attributable inbound to SAM. Anton's
new Pig 126 provider journey also remains a human acceptance action and has not
been simulated or replayed. Green PR `#1194` remains held under the owner's
changed priority. OWNER ACTION: NONE.

The next unattended manager cycle advanced BEACON to generation `92` and
provider-confirmed Telegram card `3714`. Charl approved that newly bound exact
card once. The protected publication consumer then executed and META confirmed
post `920598737794159_122149046469122163` at
`2026-08-23T16:41:42Z`; provider readback returned the identical post ID.
Canonical attribution resolves successfully as
`BEACON-CAMPAIGN-084B84F604CFAC6E983CB7EC`, packet
`BEACON-AWARENESS-7B42DB6C7732388D6D8DD46A`, through protected consumer
`BEACON-PUB-CONSUMER-8FC40D17BD899A9E39F394D9`. The post is text-only,
zero-spend farm awareness and makes no stock, price, availability or sales
claim. This is a genuine provider-confirmed BEACON publication effect. A
logged-out Chrome read of the initially derived Facebook URL displayed `This
content isn't available at the moment`. A subsequent direct read-only META
Graph read returned `is_published=true`, the exact post ID, matching message
digest and provider permalink
`https://www.facebook.com/122144340309122163/posts/122149046469122163`.
That provider permalink also remains unavailable to the logged-out browser,
so BEACON publication is proven while anonymous audience visibility remains
Unknown (login or Page visibility restrictions may apply). It also does not
prove a SAM lead or sale; those require later genuine attributable customer
inbound.

Control Tower briefly opened PR `#1197` after initially interpreting the
educational phrase `Follow the farm journey` as prohibited by the final
validator. Canonical publication proof corrected that inference: the active
policy and final validator both permit this bounded educational wording, and
META accepted it. PR `#1197` was closed unmerged to avoid an unnecessary
minor-fix release loop. ROOTLINE's second unattended post-repair cycle was
claimed at `2026-08-23T16:45:24Z` and remains under readback. OWNER ACTION:
NONE.

ROOTLINE's second unattended post-repair cycle completed at
`2026-08-23T16:46:33Z` with status
`scheduled_rootline_plan_and_execution_completed`, two Telegram sends and zero
hardware commands. This proves automatic continuity and no duplicate start
while the active C12345 segment is still running. Final operational acceptance
still requires the due shutdown/completion and safe-state readback. The sole
current human acceptance action is Anton's own new Afrikaans Pig 126 report and
his own `Bevestig`; no terminal replay or proxy confirmation is permitted.

Charl subsequently inspected the Amadeus Facebook Page in his authenticated
owner session and confirmed that post
`920598737794159_122149046469122163` is visible on the Page. This resolves the
anonymous-browser visibility Unknown and proves the owner-visible BEACON
publication outcome. The owner also reported that the post has no image and is
visually poor. That is a genuine quality defect, not a publication failure:
the deployed scheduler deliberately selected text-only output because no media
asset with exact public-use and subject/event authority was available. Preserve
the successful automated publication and campaign attribution. The bounded
follow-on is to let BEACON select exact approved public-use media automatically;
do not restore livestock solicitation, invent media authority, create a parallel
publication workflow or claim a SAM lead before genuine attributable inbound.
OWNER ACTION: NONE.

Charl corrected two ROOTLINE statements: B Camp was already physically proven,
and irrigation timing belongs to ROOTLINE's adaptive decision rather than a
fixed daylight-only window. Current canonical/source reconciliation confirms
both corrections. The immutable commissioned controller baseline records
B/channel 1 as `ROOTLINE-COMMISSION-D248A120ECE1961DB81B6C2E`, and canonical
irrigation history proves verified B completions with safe shutdown on 12, 15
and 19 August 2026. The active business rule already says summer may favour
evening/night execution and clock time is adaptive. The command-inert daily
advisor alone retained stale `not_canary_proven` and daylight-gate wording.

Current-blocker PR `#1198`, exact head `85e29385`, reconciles that advisory
projection with the commissioned baseline and adaptive timing rule. Focused
verification is `82 passed`; hosted exact-head gates are pending. This source
repair performs no hardware action and does not expand authority. ROOTLINE's
genuine current outcome remains the deployed C12345 execution
`ROOTLINE-EXECUTION-2A699BC07BD93EF40914AA69`, started at 18:17 SAST for one
bounded segment. Its native fail-stop becomes due at approximately 19:17 SAST;
the deployed scheduler, not a terminal, must record authoritative OFF/shutdown
and then create the next fresh typed decision. B must not be watered merely to
repeat proof or satisfy a display expectation; it runs when current canonical
need ranks it eligible inside standing authority. OWNER ACTION: NONE.

At 19:09 SAST Anton performed the requested genuine post-deployment Pig 126
acceptance from his own Telegram account with: `Vark 126 is dood, ons het hom
verwyder en begrawe.` The deployed Oom Sakkie agent again routed him through
the reduced observation-only family path and replied that HERDMASTER retained
the attributable observation once but Charl still had to confirm mortality or
lifecycle change. This is a fresh genuine failure, not acceptance. Readback at
17:14 UTC confirms Pig 126 remains `Active`, on farm and in `PEN-012`, with no
new mortality claim. The event is sealed as incident evidence; Anton must not
repeat it until the reusable path is repaired and redeployed.

Charl's authority correction is explicit: Anton and Charl receive the same Oom
Sakkie farm-management messages and approval capabilities across all deployed
farm specialists managed through Oom Sakkie, rendered in each recipient's
configured language. Anton may manage and confirm governed farm and irrigation
work. CORE, CHARLIE, owner-private/non-farm business authority, permission
administration, payments and publication outside the farm-manager envelope do
not transfer. Existing actor binding, audit, replay, concurrency, canonical
safety and device-specific safeguards remain. This is an addendum to
`HERDMASTER-NATURAL-HEALTH-LOSS-1 / OOM-INTAKE-SLICE-1`, not a new workflow or
mission. The same mission is `CONTAINED / SYSTEMIC_ROLE_ROUTING_REPAIR_ACTIVE`;
no further owner attempt is allowed until exact-current implementation, review,
merge, deployment and non-actuating production readiness prove the old
farm-manager observation-only branch is unreachable. OWNER ACTION: NONE.

PR `#1198` passed all four exact-head hosted gates, merged as
`efd8d302022b8e526fdc8f6a560d8838e758366a`, and Render proved that exact
revision live. The deployed 19:16 SAST ROOTLINE reassessment then persisted a
fresh typed decision for both zones: B12345 `Run` for 60 minutes and C12345
`Run` for 60 minutes, each with adaptive window
`now_after_fresh_execution_revalidation`. It scheduled the next reassessment
for `2026-08-23T19:45:32+02:00`. C's current segment remains the active
sequential execution; B is eligible after C shutdown/readback and fresh safety
revalidation. This proves that B is neither uncommissioned nor daylight-blocked,
but it is not yet proof that tonight's B physical run started or completed.
The deployed ROOTLINE worker owns that outcome. OWNER ACTION: NONE.

## 2026-08-23 19:09 SAST - Anton provider failure and superseding parity authority

Under existing mission `HERDMASTER-NATURAL-HEALTH-LOSS-1` and bounded lineage
`OOM-INTAKE-SLICE-1`, Anton sent the genuine provider-origin message exactly as
follows: `Vark 126 is dood, ons het hom verwyder en begrawe.` Oom Sakkie returned
the legacy reply requiring Charl to confirm the mortality/lifecycle change.
This is a provider-confirmed acceptance failure, not completion. Canonical
readback proves Pig 126 remains untouched: `Active`, on farm, in `PEN-012`, with
no new mortality claim or lifecycle effect. Anton must not repeat the report
while the systemic authority path is under repair.

Charl's latest authority decision supersedes narrower wording in the preceding
entry without deleting its incident history. Anton and Charl have parity across
all governed Oom Sakkie specialist access, messages and approval journeys,
localized by recipient (`Anton = af`; `Charl = en`). Only CORE and CHARLIE are
excluded from that parity. This decision does not weaken same-actor/private-chat
binding, exact protected confirmation, attributable audit, replay and
concurrency containment, canonical readback, or physical and device-specific
safety gates. It creates no new mission, agent, workflow, confirmation rail or
authority store and does not reprioritize the register.

Exact-current source inspection identifies a systemic implementation blocker.
`modules/oom_sakkie/family_access.py` still classifies broad protected
capabilities as owner-only and routes only enumerated farm-manager permissions;
the protected-action manager allowlists and gateway projections retain the same
broader owner-only assumptions across SAM, BEACON and other Oom Sakkie
specialists. Repair must reconcile those shared authority paths with the parity
decision while preserving action-specific governance and every existing safety
boundary. Do not add specialist-specific bypasses or infer that one successful
HERDMASTER path proves parity elsewhere.

Mission state remains `CONTAINED / SYSTEMIC_ROLE_ROUTING_REPAIR_REQUIRED`.
Completion still requires exact-current implementation, regression families for
both actors and both languages across governed specialist journeys, independent
review, merge, exact deployed-revision proof and genuine provider acceptance
without proxying or replaying Pig 126. **NO OWNER OUTCOME.** OWNER ACTION: NONE.

## 2026-08-23 - Oom Sakkie daily-brief retirement and projection findings

The following findings remain inside the existing Oom Sakkie, ROOTLINE and
daily-manager mission lineage. They create no new mission and do not change
priority.

ROOTLINE's 2026-08-23 owner message exposed backend tokens and audit language,
including `Completed`, `now_after_fresh_execution_revalidation`,
`59.983333... canonical` and lifecycle boilerplate, while asking the owner to
interpret too much implementation detail. This is an owner-projection defect,
not a failure of the underlying recorded irrigation lifecycle. The target is a
short human result: B and C completed safely and are off; state the next check
time; ask at most one optional tank-level question using `LOW`, `OK` or `FULL`.
Internal tokens, floating-point duration residue and lifecycle boilerplate must
remain in audit evidence rather than the owner message.

Prince (`PIG-2026-E057`) is being presented with a stale welfare question.
Canonical lifecycle rows from 15 and 17 August remain `waiting_for_input`, but
the attributable owner reply event
`OOM-MANAGER-QUESTION-7FD2CD4F06621C770BEA6D68` on 20 August records that
Prince is improving and eating. No active lifecycle closure event exists, so
silence or the reply alone must not be represented as canonical closure.
Source inspection shows `_load_answered_questions` filters answers by
`daily_identity`; later daily briefs therefore ignore the attributable earlier
answer and ask again. Repair the existing answer-to-lifecycle reconciliation
and retirement path; do not manually mutate or silently close Prince's case.

Tristan sale `SALE-A1EE5E3DBC3110D1` is canonical `sale_status=Completed` and
`payment_status=Not_Applicable` because it is a charity disposition, last
updated on 20 August. `build_sale_watch_result` retires only `Completed` sales
whose payment is `Paid` or `Settled`, so the daily brief falsely resurrects a
payment review that cannot apply. The existing sale-watch retirement rule must
recognize attributable completed non-payment dispositions without weakening
normal payment controls.

These are three bounded daily-brief retirement/projection defects: concise
ROOTLINE owner rendering, durable prior-answer reconciliation, and completed
charity-sale retirement. No irrigation command, welfare closure, sale/payment
change, provider action or canonical mutation is authorized or claimed here.
**NO OWNER OUTCOME.** OWNER ACTION: NONE.

## 2026-08-23 - ROOTLINE current execution continuity and truthful projection blocker

This finding remains inside the existing ROOTLINE mission and directly blocks
its current owner outcome. C execution
`ROOTLINE-EXECUTION-2A699BC07BD93EF40914AA69` started channel 2 at
18:17:30 SAST with native deadline 19:17:29. At 19:48 the canonical execution
store still reported it `Active`; no current attributable `Completed` event or
verified-off closure was present.

The daily presentation nevertheless described C as `Completed` by projecting a
historical 59.9833-minute completion. That projection is stale and untruthful
for the current execution. Historical completion evidence must not substitute
for the active execution's own identity-bound OFF and closure readback.

The scheduled reassessment POST occurred at 19:45:28, four seconds before the
recorded `next_reassessment_at` of 19:45:32. It produced no new reassessment or
closure, and the next cron opportunity is later. This is timing/continuity
evidence, not proof that the active segment stopped safely.

B must not start while C lacks current verified-off closure. ROOTLINE must let
the deployed scheduler reconcile the exact C execution, record attributable OFF
and terminal state, refresh the typed decision, and only then consider B under
fresh safety revalidation. No terminal command, irrigation mutation, synthetic
closure or manual history correction is authorized. Mission state is
`CONTINUITY_BLOCKED / CURRENT_C_OFF_CLOSURE_REQUIRED / PROJECTION_REPAIR_REQUIRED`.
**NO OWNER OUTCOME.** OWNER ACTION: NONE.
