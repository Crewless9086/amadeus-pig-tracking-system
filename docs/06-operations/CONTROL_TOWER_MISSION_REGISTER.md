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

## 2026-08-22 19:13 SAST - Green release, HERDMASTER database rail and BEACON generation reconciliation

This append-only reconciliation uses authoritative current main
`2722faee539c6789ee59778f914a80c141b897e5`. It records material transitions in
the already selected Green, HERDMASTER/Oom Sakkie and BEACON/SAM missions. It
does not create, reprioritize or broaden a mission, and it grants no deployment,
database, provider, customer, farm, printer or hardware authority.

### Green 0.3.3 immutable package and commissioning boundary

Green startup/AppArmor repair PR #1169 passed its exact-head hosted gates and
different-agent review, then merged as
`704d94b39036d5999afb707ab26ee9d1338e647b`. The reviewed publication workflow
built and published version 0.3.3 once from that exact source revision as
`ghcr.io/crewless9086/amadeus-green-print-bridge@sha256:12005dcb883abd7e4dad893b82491fc2b661cf1a4daa9617d1e466cb0531a389`.
The first post-publication verification stopped safely when Sigstore's TUF
trusted-root service reset its connection. The immutable tag and digest were
not rebuilt or replaced.

Verify-only recovery PR #1173 merged as current main
`2722faee539c6789ee59778f914a80c141b897e5`. Manual workflow-dispatch run
`32586142132` then completed successfully with `publish=false`. Its recovery job
bound current main to source revision `704d94b39036d5999afb707ab26ee9d1338e647b`,
version 0.3.3 and the exact existing digest; read back the tag at the same
digest; proved a single `linux/arm64` image; verified the keyless Cosign
signature and digest-bound SLSA provenance and SPDX 2.3 SBOM attestations; and
preserved six non-secret packet files as artifact `9479090859`, archive SHA-256
`e01e8f7372125b3f20d50bf4bf3b1fd1688aceae9963ce2a6ba6e03436fe6d3e`.
The receipt identities are Cosign verification
`021ad1a1ed632db2ebad5f0d3d7ed025abb75a12a71d9b78e63e434147fb8b32`,
provenance verification
`403bce9fadf5e1b30210d448a5bf9127cf66aaa1293958a62146e57c498148ea`
and SBOM-attestation verification
`f24e0aa4a3d3c65cf51e0750a30e7de85161040febe998da8dcd1f5d2d5de38d`.

This is verified immutable release evidence, not an owner outcome. Fresh Home
Assistant evidence supplied to Control Tower still shows installed Green 0.3.2
stopped, its saved exact configuration and identities preserved, version 0.3.3
available, and zero canonical jobs, CUPS jobs, documents or physical prints.
Start on boot, Watchdog and Auto update remain OFF. Lifecycle is
`OWNER_HOLD / IMMUTABLE_0.3.3_VERIFIED / INSTALLATION_AND_ZERO_JOB_COMMISSIONING_PENDING`;
**NO BUSINESS OUTCOME**. The one action-time boundary is approval to click the
exact 0.3.3 update and, only after saved configuration and empty-queue readback,
perform one start/health/heartbeat/zero-effect/stop cycle. Stop on any version,
digest, identity, configuration, queue or effect mismatch. No document, print
job or physical print is part of this commissioning window.

Automatic continuation trigger: exact owner approval of that bounded update
and zero-job cycle. Control Tower then owns the browser operation, verification,
safe stop and register readback without another routine approval. A later
genuine Oom Sakkie print request, exactly one physical page, follow-up and a
terminal-independent later cycle remain distinct acceptance gates and are not
claimed here.

### HERDMASTER/Oom Sakkie PR #1167 database-release repair

The existing farrowing database-authority lineage remains one
`CURRENT_BLOCKER`; no parallel migration system or mission exists. Independent
disposable-PostgreSQL reviews repeatedly rejected earlier CI-green heads for
fail-open schema, receipt, ownership, ACL, privilege, trigger, rewrite-rule,
time-zone and governed-view integrity gaps. Those failures remain preserved as
evidence and are not overwritten by the latest technical pass.

Exact current head `ad343583569bd6e37eec68372904ef22bed57e95` is clean and
mergeable against current main, with all four hosted exact-head gates passing.
Its bounded repair advances the deterministic catalog manifest to include the
complete governed `pg_rewrite` inventory including `_RETURN`, normalized rule
and view definitions, relation kind/options and `relhasrules`; the production-
shaped same-column `WHERE false` governed-view replacement and prior
`INSERT DO INSTEAD NOTHING` attack now reject before any receipt or migration
mutation in disposable PostgreSQL. This exact head remains under a fresh
different-agent independent review. Lifecycle is
`REVIEW_HOLD / DATABASE_RELEASE_REPAIR_EXACT_HEAD_CI_GREEN / PRODUCTION_UNCHANGED`;
**NO BUSINESS OUTCOME**. No merge, deployment, production database access,
migration, protected claim, farrowing record or farm/provider effect occurred.

Automatic continuation trigger: independent exact-head PASS. Control Tower may
then serialize current-main reconciliation and the already governed release
decision; production migration execution and canonical readback remain a
separate protected release stage. Any review finding returns to the same PR
lineage without owner intervention or another database rail.

### BEACON PR #1174 generation stability and SAM dependency

BEACON/SAM operational acceptance remains the existing revenue outcome: the
deployed BEACON actor must produce one stable current owner decision, protected
publication must occur exactly once only under its authority, and genuine
attributed customer inbound must then reach deployed SAM. No terminal may
manufacture the post, customer message or SAM acceptance.

Production observation exposed manager-generation churn: unchanged scheduled
collection and immediate refresh could replace the candidate and defer owner
delivery. PR #1174 is the single bounded repair lineage. Independent review of
head `643e9b4728229ccf3cc3f2f454336e3b47ded0a1` correctly failed release because
the replacement generation identity omitted the non-secret target Facebook Page
identity and explicit policy identity/version. That could leave an old claim
unusable without producing the required successor after a genuine Page or
policy change. No post, customer message, approval, spend or provider mutation
occurred.

The same lane repaired that finding at exact current head
`962a61578a6b2191254b3ed8177caf45f4478a81`. GitHub currently reports PR #1174
clean and all three hosted exact-head checks passing. The head is not merged or
deployed and still requires different-agent exact-head rereview of unchanged
refresh, unrelated SAM audit changes, Page/policy successor generation,
stale-claim retirement, replay/concurrency and executor revalidation. Lifecycle
is `REVIEW_HOLD / LATEST_REPAIR_CI_GREEN / INDEPENDENT_REREVIEW_PENDING`;
**NO BUSINESS OUTCOME**.

Automatic continuation trigger: independent exact-head PASS, followed by the
serialized merge/deploy decision, exact loaded-revision proof and one deployed
scheduled actor cycle. Only after a current provider-confirmed owner card exists
may the already governed publication journey advance; SAM remains
`DEPENDENCY_IDLE / GENUINE_ATTRIBUTED_INBOUND_PENDING`, with customer auto-send
OFF and no five-customer or later unattended acceptance claimed.

### Fresh collision, worktree and release sweep

- PR #1167 modifies only the migration workflow, production migration runner,
  farrowing action-kind migration and its database-rail tests. PR #1174 modifies
  only BEACON request/manager source and BEACON/manager tests. Their source files
  do not overlap each other or this register-only branch.
- Green PRs #1169 and #1173 are merged. Their retained worktrees contain only
  ignored test output; their unique commits are preserved in main and they do
  not own the release lane.
- The prior Control Tower register branch head `a60aa85063384aa1debbf197f8cc43d75ffbcfa0`
  is clean, merged through PR #1172 and an ancestor of current main. This fresh
  register branch is the only writer to this register in the current
  reconciliation.
- Numerous historical worktrees and old open PRs remain preserved as collision
  or archive evidence. They are not fresh terminal activity and receive no new
  priority or release authority from this sweep.
- Process enumeration found Codex, Node, PowerShell and Python processes, but
  process existence did not establish terminal mission activity. Active claims
  below rely only on exact current PR/worktree activity and supplied current
  terminal feedback.
- No production release-lane mutation owner is active. Green waits at a bounded
  owner action-time hardware/configuration boundary; PR #1167 and PR #1174 are
  source-review holds and do not own production.

### Mandatory all-terminal closure sweep

| Visible terminal | Current classification | Fresh evidence, dependency and promotion trigger |
|---|---|---|
| CORE | `UNKNOWN - VERIFY` | Local runner/runtime worktrees and processes exist, but no fresh target-bound mission heartbeat or current execution proof was established. Do not infer pickup or autonomy; reassess on a fresh CORE handover or canonical worker heartbeat. |
| OOM SAKKIE | `ACTIVE - DO NOT INTERRUPT` | Existing PR #1167 current-blocker lineage is at exact head `ad343583` under independent review. Continue the same mission; no duplicate prompt or migration rail. |
| ROOTLINE | `DEPENDENCY IDLE` | No fresh non-colliding current terminal activity was proved. Strategic WIP remains occupied by Green, #1167 and #1174; reassess immediately when one current track releases or a proven ROOTLINE production incident unblocks an existing outcome. |
| HERDMASTER | `ACTIVE - DO NOT INTERRUPT` | PR #1167 is the current farrowing database-release blocker and exact-head independent review gate. Its deployed farm outcome remains absent; resume automatically on review result. |
| SAM | `DEPENDENCY IDLE` | Source is deployed with auto-send OFF; genuine acceptance depends on a deployed BEACON publication producing attributed customer inbound. Promote immediately after provider-confirmed BEACON publication and genuine inbound. |
| BEACON | `ACTIVE - DO NOT INTERRUPT` | PR #1174 latest repair head `962a615` is clean and CI-green after the preserved Page/policy review FAIL; independent rereview is the next gate. |
| CODEX UI | `NO SAFE WORK` | The current WIP slots and overlapping historical UI work remain preserved. No current owner-outcome blocker requires a new UI mission before the three selected tracks release. |
| DOCUMENTS / Green | `DEPENDENCY IDLE` | Source/package release is verified and the terminal is released; commissioning waits only for the exact action-time owner approval recorded above. No development prompt is eligible. |

### Control Tower Check Receipt and handover

```text
CONTROL TOWER CHECK RECEIPT
Governance: PASS - CT HEAD/main 2722faee539c6789ee59778f914a80c141b897e5;
  Standard blob 3002b94713e286c4eb2019419c438cc378c337fa,
  SHA-256 44e34c69145b83d2cd5b6a5322a6c2c124789fa647e19f19b3e39a7293a5202b,
  1127 lines; Protocol blob 8fbd0b9c9160164e31a17a2cbfa51ab88792a909,
  SHA-256 d4eb4b54a660ce39dfc92cb0fa253b0f2e3d7314462984702602d0f4b66a7e0a,
  319 lines; Programme blob fb44d7f86c47e605c283ed33c28ba2c4267d6edb,
  SHA-256 721281eeacc33ae11877ce610fe7a76ba06de6b75db4573f64933073fd358309,
  278 lines; Template blob 1233aee625e45821a685614a33b1eb101c666ffd,
  SHA-256 6d81bdfd41770f30e7e2e9acea584e747e007fe3ab155d3427fb17599a26111f,
  266 lines. All are tracked and read completely in this worktree.
Feedback freshness: mixed - GitHub/CI/worktree evidence refreshed at 2026-08-22
  19:13 SAST; Home Assistant state is the latest supplied authenticated Control
  Tower readback and must be revalidated immediately before update.
Terminal truth: #1167 and #1174 active review lineages; Green development
  released; other processes are not activity proof.
Runtime truth: Green stopped/uncommissioned; BEACON/SAM operational outcome
  pending; HERDMASTER production database unchanged; no autonomy inferred.
Mission: DMQ-20260816-01 Green - OWNER_HOLD - zero-job commissioning remains;
  #1167 - REVIEW_HOLD - production-safe database release remains;
  BMQ-20260813-05 - REVIEW_HOLD - stable card/publication/customer loop remains.
Strategic WIP: Green CURRENT_BLOCKER; #1167 CURRENT_BLOCKER; #1174 OPERATING_SPINE.
Owner workload delta: Green manual install/status/queue supervision -> one
  action-time approval, then Control Tower update/verify/stop; full removal still unproven.
Release lane: free - no current production mutation owner.
Collision/worktrees: clear for this documentation PR; dirty/ignored and
  historical worktrees preserved, not deleted or reused.
Owner repetition: none; one fresh 0.3.3 action-time approval is the exact need.
Register: updated in a clean exact-current documentation branch.
All-terminal sweep: completed in the table above.
Dispatch: WAIT FOR INPUT for Green commissioning; CONTINUE - SEND NOTHING for
  active #1167 and #1174 review lineages.
```

Decision: `WAIT` for Green installation while source-review lanes continue.

Why: the immutable Green package is now fully verified, but the installed device
remains on stopped 0.3.2 and the owner-visible zero-job commissioning outcome has
not occurred.

Send to exact terminal: `CONTINUE - SEND NOTHING` for the already-running PR
#1167 independent review and PR #1174 repair/rereview lineages. No development
prompt should be relayed. On Green approval, Control Tower resumes the same
commissioning mission directly; it must not ask Charl to operate the browser.

Expected business result: Green installs the exact verified 0.3.3 package,
proves healthy zero-job heartbeat and empty canonical/CUPS state, then returns
stopped with every automatic control OFF and no document or physical print.

ACTION REQUIRED NOW: Approve the exact Home Assistant Green 0.3.3 update and one
zero-job start/verify/stop cycle; Control Tower will revalidate the digest,
saved identities, configuration and empty queues immediately before acting and
will stop on any mismatch.

### 2026-08-22 child `SAFETY_BLOCKED` incident and Control Tower recovery correction

After PR #1167 exact head
`ad343583569bd6e37eec68372904ef22bed57e95` passed its exact-current hosted
gates, child `/root/oom_1167_review_ad34` was assigned the already authorized
bounded defensive review. Exact wall-clock time is `Unknown`; the attributable
date and sequence are 2026-08-22 SAST after those gates. The non-secret exact
scope was: review only PR #1167's repository migration runner and the
workspace-local disposable PostgreSQL service; verify governed-catalog
completeness and fail-closed zero-mutation behavior under schema drift; perform
no secret retrieval, external scanning, production access, provider action or
unrelated-system access.

The child response was withheld by a safety safeguard. Only that child attempt
is classified `SAFETY_BLOCKED`. PR #1167's owner outcome, priority, current
head, evidence, authority and independent-review requirement remain unchanged;
the mission is not Business-complete, globally blocked, reprioritized or
authorized for merge, deployment or production migration. No secret, credential,
database connection, external target or exploit payload was recorded in this
incident entry. No production, provider, customer, farm or external-system
effect occurred.

Control Tower corrected the reusable development procedure on the existing
repository-scoped `control-tower-operate` skill lineage. PR #1176 exact head
`dcd026fbca83ba36dcfb7da3495e37ca04bb40da`, reconciled onto authoritative
current main `7dbdf172c86e96aaec2bf78006cf4a79f50cab31`, adds the same narrowly bounded
`SAFETY_BLOCKED` recovery rule: preserve mission authority and safety boundaries,
record only non-secret workspace-local evidence, do not resend the same prompt,
remove unrelated sensitive concepts, and resume through a fresh named Amadeus
repository/disposable-test task. It explicitly prohibits secret retrieval or
disclosure, authentication bypass, sandbox circumvention, unrestricted scanning,
unrelated-system access and unauthorized production or external mutation.

Independent governance rereview at that exact head is `PASS`. The only
candidate change relative to current main remains the reviewed 21-line skill
addition. It verified that
the correction preserves mission scope and protected authority, narrows and
resumes only owner-authorized defensive repository work, retains safeguards,
and creates no Amadeus runtime agent, queue, scheduler, database, provider
adapter, product workflow or authority plane. Skill Creator validation, Vault
alignment, `git diff --check` and all three hosted exact-head gates passed;
GitHub reports the PR clean. The complete non-secret review handover is preserved
workspace-locally at
`control-tower-artifacts/PR-1176/review-dcd026fb/PR1176_DCD026FB_INDEPENDENT_GOVERNANCE_REVIEW_20260822.md`.

Lifecycle is `WORKING / CHILD_ATTEMPT_SAFETY_BLOCKED / RECOVERY_RULE_REVIEWED`;
**NO BUSINESS OUTCOME**. PR #1176 was subsequently merged as authoritative main
`8c517580bb03fd2036cfe359c403ebb55c43d5cf`; this is a governed development
procedure correction, not an Amadeus owner outcome. This correction
does not consume a new strategic WIP slot and does not change the Green,
HERDMASTER/Oom Sakkie, BEACON or SAM sequence recorded above. Automatic
continuation is a fresh narrowed PR #1167 defensive review attempt under the
same existing authority under the now-merged reviewed recovery rule;
independent lanes continue without interruption. Owner action for this incident
is none; the separate Green action-time boundary recorded above remains the only
current owner blocker.

### 2026-08-22 post-snapshot authoritative-main reconciliation

Authoritative `origin/main` advanced from `2722faee539c6789ee59778f914a80c141b897e5`
to `7dbdf172c86e96aaec2bf78006cf4a79f50cab31` through the reviewed PR #1174
BEACON generation-stability merge. This supersedes the earlier open-PR snapshot
without rewriting its preserved review history. Repository repair is merged;
exact loaded production revision, a genuine public BEACON post, and customer
inbound to SAM remain `Unknown` here. Therefore this is technical progress and
**NO OWNER OUTCOME**: no post, customer message, provider effect, farm effect or
database effect was performed or proved by this reconciliation.

PR #1175 is reconciled onto that exact current main. PR #1176 exact head
`dcd026fbca83ba36dcfb7da3495e37ca04bb40da` contains the unchanged reviewed
recovery rule plus the already reviewed PR #1174 main lineage. No mission was
reprioritized, duplicated, completed or granted new authority. Green remains
the current owner-action blocker; PR #1167 continues its existing repair/review
lifecycle; BEACON still requires deployment and genuine post-to-SAM acceptance
before any owner outcome claim.

Authoritative main then advanced once more to
`8c517580bb03fd2036cfe359c403ebb55c43d5cf` through the reviewed PR #1176 merge.
PR #1175 is reconciled onto that exact current main. The child incident and its
non-secret scope remain durably recorded; the recovery correction is now active
development procedure. No deployment, provider, database, farm, customer or
physical effect follows from that merge, and no mission priority changed.

### 2026-08-22 Green 0.3.3 contained-start superseding current state

This entry supersedes only the earlier Home Assistant current-state snapshot;
it preserves the publication and preflight history above. The exact immutable
Green 0.3.3 package was installed on the authenticated Home Assistant Green.
Pre-start canonical readback proved zero eligible work, claims, events and jobs.
One bounded zero-job start was attempted. The service returned to stopped before
commissioning completed; it was not retried. Start on boot, Watchdog and Auto
update remain OFF. No known document submission, CUPS/canonical job or physical
print effect occurred. These are contained technical events, not an owner
outcome, and they do not prove Green operational acceptance.

High-confidence diagnosis is preserved workspace-locally at
`control-tower-artifacts/GREEN-0.3.3/diagnosis/GREEN_033_STARTUP_FAILURE_DIAGNOSIS_20260822.md`.
The 0.3.3 initializer appears to require ambient DNS resolution of the
certificate hostname before it establishes the already commissioned pinned-IP
hostname binding; the hosted arm64/AppArmor probe pre-seeded that resolution and
therefore did not exercise the production shape. This is a source/evidence
diagnosis, not canonical proof of the exact runtime failure. Lower-probability
fail-fast initializer causes remain bounded Unknowns until the replacement
package proves the Home Assistant journey.

Green 0.3.3 remains contained and must not be restarted. A 0.3.4 repair on the
same Green lineage is active: preserve the registered endpoint, certificate,
credential and fixed queue; verify TLS/SAN against the pinned private IP before
installing the local binding; add sanitized stage/reason evidence and a
production-shaped no-preseeded-DNS arm64/AppArmor regression. Publication,
installation and another zero-job commissioning attempt remain later governed
stages. The technical repair is the current blocker, so owner action is none.

#### Superseding terminal sweep, handover and Check Receipt

| Lane | Current state | Next controlled transition |
|---|---|---|
| Green | `ACTIVE - 0.3.4 SAME-LINEAGE REPAIR`; 0.3.3 installed but stopped and contained; zero known job/document/print effect | Implement, independently review and pass exact-current production-shaped gates before any new immutable publication decision. |
| Oom Sakkie / PR #1167 | `ACTIVE - REPAIR/REVIEW`; open exact head `01d3890d33f1341bcce5f9551ded858de4fd1833`; no production database effect | Complete exact-head hosted gates and fresh narrowed independent defensive review under the merged recovery rule. |
| Control Tower / PR #1175 | `ACTIVE - GOVERNANCE RECEIPT`; append-only current-state reconciliation | Pass exact-head gates and independent review; do not merge from this lane. |
| BEACON / SAM | `ACCEPTANCE PENDING`; source repair merged, but no genuine public post or customer inbound outcome is proved here | Deploy exact reviewed revision and prove genuine post-to-SAM provider/customer acceptance through its existing lane. |
| HERDMASTER / remaining queued lanes | `PRESERVED / NOT REPRIORITIZED`; no new collision or owner outcome established by this entry | Continue only under their recorded priority when a strategic slot releases or they unblock an existing outcome. |

Terminal sweep result: no duplicate Green system, credential, registry, queue,
certificate or mission was created. The stopped 0.3.3 package is contained; the
0.3.4 change is the only active Green repair lineage. No terminal may call the
installation or failed start commissioning, activation or owner acceptance.

Control Tower Check Receipt: authoritative main
`8c517580bb03fd2036cfe359c403ebb55c43d5cf`; Green diagnostic evidence read in
full; GitHub open-PR and worktree collisions swept; prior authority and history
preserved; new facts appended without reprioritization; external/Home Assistant
access not performed by this register update; exact-current local and hosted
gates required before handover. Decision: `CONTINUE AUTOMATICALLY / NO OWNER
OUTCOME YET`.

OWNER ACTION: NONE

## 2026-08-23 HERDMASTER / Anton fresh deployed failure

At 19:09 SAST Anton sent `Vark 126 is dood, ons het hom verwyder en
begrawe.` Production, loaded at exact revision
`7777ee05b37b8ca6d3227bf112433d481066dbcb`, returned the legacy
observation-only response requiring Charl's separate confirmation. Canonical
read-only evidence still showed Pig 126 Active, on farm and in PEN-012, with no
mortality claim. Pig 126 and the old provider event remain sealed from terminal
mutation or replay.

This is new evidence in existing mission
`HERDMASTER-NATURAL-HEALTH-LOSS-1 / OOM-INTAKE-SLICE-1`, not a new mission. The
semantic front door omitted Afrikaans `vark` identity and standalone `dood`, and
the gateway diverted every non-owner through a reduced family lane before the
shared Oom Sakkie specialist pipeline. Older capability policy also retained
owner-only assumptions beyond mortality.

The bounded repair gives FARM_MANAGER the same governed Oom Sakkie specialist
messages and actor-bound approval journeys as OWNER, localized to the recipient,
through explicit capabilities and action kinds. CORE and CHARLIE remain
structurally unreachable; permission administration and unsafe hardware
exceptions remain excluded. Replay, audit, canonical revalidation,
confirmation and physical safety controls remain mandatory.

Lifecycle: `WORKING / SOURCE_AND_TEST_IMPLEMENTATION_ACTIVE`; **NO BUSINESS
OUTCOME**. Do not request another Anton test until exact-current tests, Brain
Guard, independent review, merge, exact loaded revision and non-actuating
production readiness prove the legacy farm-manager branch is unreachable. Only
a new provider-origin report and Anton's own confirmation may then establish
acceptance.

OWNER ACTION: NONE

## 2026-08-24 - HMQ stale heat-gating intake consolidation

GENERAL's stale heat-gating finding is consolidated into existing mission
`HMQ-20260813-05`, with `HMQ-20260813-00` supplying the already-integrated
individual-observation contract. No mission, document, store, queue or priority
was created. Prince's P0 incident remains first; this finding retains the
existing combined weighing-to-management-and-breeding lane position. Current
state is `BLOCK / IMPLEMENTATION_MISALIGNMENT`, with **NO OWNER OUTCOME**.

Controlling invariant: absence of attributable heat evidence may never create
or retain work at any point in the closed loop. Heat is not a prerequisite for
weighing recovery, management recommendation, boar recommendation, protected
placement, the governed 17-day exposure, removal, or later reproductive-outcome
follow-up. If Charl or Anton voluntarily supplies an exact-pig heat observation,
it may be retained once as append-only canonical history under HMQ-00; it must
not become an inferred fact, repeated question, work-retention gate or blocker.

Scope is the existing HMQ-05 weighing-to-breeding closed loop: recover a genuine
completed weight batch; optionally capture selective body-condition scores in
the existing Bulk Weight Entry; produce concise management and boar
recommendations; prepare protected, actor-bound placement; verify the governed
17-day exposure; remove safely; and follow the later attributable reproductive
outcome. HMQ-00's shared fact-intake/history path is reused for volunteered
observations. The repair must retire stale heat-dependent questions or work when
no evidence exists, preserve missing facts as Unknown, and carry source,
provider, canonical and physical acceptance evidence through every protected
transition.

The required owner contract is one upload with distinct canonical effects: each
entered weight becomes a weight event, each changed location becomes a location
event, and each entered BCS becomes a separate observation event consumed by the
existing Herdmaster management lifecycle. Blank BCS means no observation and
must create no event, question or retained work. A BCS-only row is actionable
without requiring a weight or location change. BCS must not be hidden in weight
notes. Corrections and supersessions remain append-only and attributable; they
must never overwrite observation history silently.

Non-scope includes a new intake system, mission, schema, store, page, queue or
scheduler; asking the family to inspect heat; inferring negative heat from
silence; unprotected breeding or mating action; terminal-proxy confirmation;
manual provider traffic; and database, animal or physical mutation during this
intake. Breeding remains in scope as an outcome journey, but placement, exposure
and removal remain protected physical actions and cannot be claimed from source
or provider text alone.

Evidence remains separated. **Source evidence:** authoritative main
`ce906bd1713be942c58beec4c1e85de545d3e80b` contains the current HMQ product
surface, while legacy PR `#603` remains open at head
`895e5052fcdaad782dce37beff9aaa6d08d8149b` on stale base
`4774420f7db56740be13c0667a5469aa8f389627`; its two-file prototype independently
models `weight` and optional `heat_observation`, so it is collision evidence to
reconcile, not authority to revive or merge. **Provider evidence:** no new
attributable weighing, heat, placement, exposure or removal message was
inspected. **Canonical evidence:** no production row was written or changed,
the required database migration, RLS and trigger truth for separate weight,
location and observation events is Unknown and therefore an implementation gate,
and a genuine completed HMQ-05 batch plus downstream lifecycle readback remain
pending. **Physical evidence:** no weighing, BCS, heat observation, placement,
exposure, removal or reproductive outcome was performed or inferred; absence of
heat evidence is not evidence that an animal is or is not in heat.

The measurable owner outcome remains one genuine closed loop: Charl or Anton
uploads the batch once; receives separate exact-once weight, location and
selective BCS canonical events plus concise language-localized Herdmaster
management and boar guidance without being asked for absent heat; performs only
the protected, confirmed placement/removal steps; and later receives
canonical/provider proof of exposure and reproductive outcome with replay-safe
automatic follow-up. Blank BCS produces zero observation effect, BCS-only input
is accepted, and a corrected BCS supersedes append-only history. Any volunteered
heat fact remains visible as history but never creates a field, question, task,
reminder, blocker or retained work.
After Prince P0 release, the next automatic step is a current-main collision
review and the smallest repair to the existing shared observation, weight and
breeding projection, followed by exact regression tests, reviewed release,
genuine acceptance at every real-world gate and a later stable cycle. PR `#603`
must not be merged or used as a parallel implementation. **OWNER ACTION: NONE.**

Control Tower Check Receipt: this append-only intake classification records the
invariant, full existing closed-loop scope, evidence boundaries, stale PR
collision and acceptance contract without a technical-progress or owner-outcome
claim. No provider, canonical, farm, animal, deployment or physical effect
occurred.

### Heat-gating source repair prepared on exact current main

On authoritative main `a074ed18831f0695560ac8b9a310978aaffaaea6`, the
remaining stale heat dependency was localized to owner questions, grouped
management observations, one legacy heat-only task projection and its delay
wording. The core classifiers already declared `heat_observation_required=false`
and retained volunteered heat facts through the existing canonical observation
rail. The bounded repair removes absent heat from questions and grouped required
checks, retires a legacy heat-only task instead of projecting it, and replaces
the not-pregnant fallback with a neutral reproductive-status review. Exact
volunteered or ambiguous heat statements remain attributable history and may be
clarified; silence creates no inferred fact or work.

Selective Bulk Weight Entry BCS capture remains the next serial addendum in the
same mission. It is deliberately excluded from this first PR because it crosses
the weight upload, UI and canonical write boundary and requires separate
append-only observation/supersession proof. This split does not change priority
or create another mission. Lifecycle remains `WORKING / SOURCE_REPAIR_ACTIVE`;
**NO BUSINESS OUTCOME** and **OWNER ACTION: NONE**. No provider, canonical,
animal, farm or physical effect occurred.

### Selective BCS source repair prepared on exact current main

The serial HMQ-05 addendum reuses Bulk Weight Entry and HMQ-00's canonical
`pig_observation_events` writer. A row is actionable when it contains only a
valid BCS; blank BCS has zero observation effect. Each selected pig receives a
separate append-only body-condition observation keyed by draft plus pig, with
replay withheld and the latest effective BCS explicitly superseded on a
correction. No heat input or derived heat work is introduced. The draft remains
recoverable when either the BCS or weight/location rail fails. No schema, page,
store, queue or scheduler is added. Lifecycle remains `WORKING /
SOURCE_REPAIR_ACTIVE`; **NO BUSINESS OUTCOME** and **OWNER ACTION: NONE** until
reviewed release and genuine canonical/provider acceptance.

Independent review found that a response-loss retry could recalculate a newer
supersession predecessor and conflict with its already committed event, and
that a later pig failure hid earlier committed rows. The repaired batch first
reads the exact draft-plus-pig idempotency event and reuses its original
predecessor before invoking the canonical writer. A partial response now lists
all committed/replayed events, the exact failed pig and status, and requires the
draft to remain retained. Production-shaped PostgreSQL tests cover
retry-after-commit, concurrent replay and a genuine multi-pig partial.
The same-day observation timestamp is bound to the authenticated server's
current SAST date at local day-start rather than a fixed noon, so a pre-noon
upload cannot manufacture future evidence and concurrent retries remain byte
stable. A committed retry reuses its exact stored timestamp. Past dates remain deterministic local noon and the canonical writer
continues to reject any future date.

## 2026-08-24 - Prince generic Telegram completion acceptance failure

This owner finding is consolidated into existing mission
`HERDMASTER-NATURAL-HEALTH-LOSS-1`; no mission, document, store, page or priority
was created. A provider completion that says only that a HERDMASTER observation
was recorded, or exposes only a backend pig ID, is not an owner outcome. The
completion must name the canonical human pig identity, state the exact confirmed
facts, report the welfare state and next action bound to the exact protected
operation and attributable welfare case, and render every part in the
recipient's language. Backend-only identifiers may remain audit evidence but
may not replace the human identity.

Current state is `BLOCK / OWNER_ACCEPTANCE_FAILURE`. Independent review of PR
`#1232` at head `281057cf30a17dad693fd77e5290d91303f4aeeb` blocks the candidate:
the query selects the latest welfare state for the pig rather than binding the
state to the exact welfare case attributable to the confirmed operation. A
later or unrelated case could therefore produce a plausible but false state or
next action. The implementation must fail closed unless identity, confirmed
facts, operation, claim, exact welfare case, case state and next action all bind
to one canonical chain at immediate pre-delivery readback.

Evidence remains separated. **Source evidence:** exact current main
`db72542499cd76ab7ebb06c777c0a1877f6e2f58` and the blocked PR `#1232` diff/checks.
**Provider evidence:** the generic completion card is genuine delivered text but
does not prove its omitted identity/facts/case state. **Canonical evidence:**
the existing mission remains active; no farm or welfare row was changed by this
intake. **Physical evidence:** Prince's real welfare state cannot be inferred
from generic provider wording or source code and remains governed by the exact
attributable canonical case and family observations.

The measurable owner outcome is one recipient-localized completion that tells
Charl or Anton which canonical pig was observed, exactly what was confirmed,
whether the exact operation-bound welfare case is open, monitoring, escalated or
closed, and the truthful next action; replay produces no duplicate edit/message
or state effect. Source repair, tests, merge or deployment alone are not this
outcome. Priority is unchanged because this finding directly unblocks the
existing health/loss mission. **OWNER ACTION: NONE.** No repeat observation,
confirmation or provider action is requested while the technical binding repair
remains blocked.

Control Tower Check Receipt: one existing mission lineage receives one
append-only acceptance failure. PR `#1232` remains unmerged. This register
intake performed no provider, welfare, farm, animal or physical mutation.
## 2026-08-24 - ROOTLINE unchanged-plan owner-noise intake and exact diagnosis

This is an outcome-unblocking addendum to existing `RMQ-20260813-04`, not a
new mission, notification rail, store, queue or scheduler. Owner evidence says
the same standalone `ROOTLINE TODAY'S WATER PLAN` continued approximately every
fifteen to thirty minutes: B remained ready after the final safety check, C
remained ready with the internal revalidation reason, no owner action was
needed, and only the next-check clock moved. The required owner outcome is one
plan inside the daily Brief; standalone plan delivery only after a material
owner-visible B/C plan or owner-question change; immediate start, stop and
verified-completion messages preserved; a concise close summary; and silent
unchanged reassessments. `OWNER ACTION: NONE`.

Read-only production evidence on exact deployed/current-main revision
`a2f2c7c90f8226654ffdb7fdd766bad676cf6c97` proves provider messages `3982`,
`3983` and `3985` were each delivered with a different material digest although
their persisted B/C owner projections were semantically unchanged. The shared
digest included hidden borehole, fertilizer and overall specialist state that
the standalone B/C presentation does not render. This is a projection/deduplication
defect, not a scheduler, provider or irrigation-control failure.

Lifecycle: `WORKING / IMPLEMENTATION_PR_1234 / REVIEW_AND_DEPLOY_PENDING / NO
BUSINESS OUTCOME`. PR #1234 exact source commit `7923625d` restricts the existing
notification material identity to rendered B/C semantics while retaining owner
question and stable reassessment material. Fifty-two focused owner-response,
daily-presentation and automatic-scheduler tests pass; no Telegram message,
provider control, database farm write or irrigation command was issued by the
terminal. The existing canonical Mission Control row received idempotent event
`CORE-MISSION-CONTROL-C5514E2F5DB7985EA6E79182`; exact replay was a no-op,
status remains `paused / event_waiting`, and owner action remains `NONE`.

First missing acceptance gate: independent exact-head PASS and hosted CI,
serialized merge/deployment, then a natural provider-origin material-change
delivery followed by a later unchanged natural reassessment with zero standalone
plan delivery. Immediate lifecycle notifications must remain unaffected. This
directly unblocks the existing owner outcome but does not otherwise reprioritize
the durable mission order.

### Post-deployment digest-cutover acceptance failure and compatibility repair

PR #1234 independently passed, merged as
`6040d34a36030101cd65218c50d728505d4b8b48`, and loaded exactly on Render.
The first natural post-deployment cycle recorded observation at
`2026-08-24T11:46:51.913854Z`, then delivered provider message `3986` at
`11:47:03.557070Z`. Its B/C owner semantics remained unchanged, but the newly
corrected semantic digest could not equal the predecessor's legacy digest, so
the version cutover emitted one false duplicate. Zero hardware/farm mutation
occurred and the separate execution-lifecycle notification rail was untouched.

Lifecycle remains `WORKING / POSTDEPLOY_ACCEPTANCE_FAIL / SAME_LINEAGE_COMPATIBILITY_REPAIR`;
**NO BUSINESS OUTCOME** and `OWNER ACTION: NONE`. The bounded continuation must
bind the prior delivered and pending packet to the exact recipient, operating
date and predecessor identity; compare stable rendered semantics only for the
declared volatile canonical reassessment clock; and fail open to one legitimate
delivery when predecessor evidence is absent, ambiguous or mismatched. Genuine
zone/lifecycle/verified-completion/owner-question changes and fixed meaningful
deadlines must still produce exactly one successor. Completion still requires
reviewed deployment, a natural materially changed plan when one genuinely
occurs, and a later natural unchanged zero-send cycle.

### First compatibility deployment failed and existing fertilizer delay evidence

PR #1235 independently passed and merged as
`5c3ba98af02a8220adaf715d5b002988deb1d4c1`; Render loaded that exact revision.
The first natural due cycle then recorded observation
`OOM-ROOTLINE-OBS-DAE1CCE12878150024CB5914-RECORD_OBSERVATION` at
`2026-08-24T12:17:01.610604Z` with the same visible B/C semantics as message
`3986`, but claimed pending notification
`OOM-ROOTLINE-REASSESS-245167D18F25A1595F1F9EFE` and delivered provider message
`3987` at `12:17:13.522650Z`. Only the next-check time moved from 14:16 to 14:46
SAST. Raw append-only packet readback proves exact predecessor owner/chat/date,
identity, provider receipt and pending-answer enrichment; suppression failed
because production's `durable_backend_schedule` trigger was excluded from the
hard-coded volatile-trigger allowlist. This remains a notification-only
acceptance failure with zero irrigation, fertilizer, borehole or farm effect.

The same-lineage repair on exact current main replaces that brittle trigger
allowlist with a versioned owner-plan semantic fingerprint stored in the
existing pending/delivery packet. It normalizes only the visible next-check
line and retains exact recipient, date, provider receipt and predecessor
binding. Existing historical packet text supplies the transition fingerprint;
missing or ambiguous predecessor evidence still permits the first legitimate
plan, and a visible zone, lifecycle, verified-completion or owner-question
change still produces one successor. Lifecycle notices remain separate.

Owner evidence also states that no fertilizer has been used for three weeks and
that further delay is unacceptable. This is consolidated into the existing
`RMQ-20260813-02` Mixer and `RMQ-20260813-03A/03B` Injection lineage; it creates
no new mission and does not change priority. Source and canonical readiness are
not physical commissioning: Mixer CH2 is read-only observed and bounded for a
future supervised five-minute proof, while Injection CH1 remains dependent on
commissioned Mixer plus genuine active B/C preflow, pulse, flush and exact OFF
evidence. The current absence of a dedicated canonical Mission Control row for
these register-retained identities remains a visibility gap; no substitute row
or direct database mutation was made here.

Lifecycle: `WORKING / POSTDEPLOY_ACCEPTANCE_FAIL / SEMANTIC_REPAIR_ACTIVE`.
Measurable outcomes remain two natural unchanged cycles with zero standalone
plan delivery, then one technically ready supervised Mixer proof and later
separate Injection acceptance. **OWNER ACTION: NONE** until the notification
repair is reviewed/deployed and the exact commissioning rail reports readiness;
do not ask the owner to wait at equipment or repeat a presence statement.

### BMQ-20260813-05 semantic adoption configuration recovery prepared

The deployed semantic interpreter remains fail-closed unless all three existing
Render keys are present: `OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED`,
`OOM_SAKKIE_LLM_ROUTER_MODEL`, and secret `OPENAI_API_KEY`. The first approved
legacy asset exhausted its bounded attempts while that runtime was not fully
configured and is durably in terminal `exception`; merely adding configuration
cannot make the existing eligibility predicate select it again. The bounded
same-mission repair permits exactly one append-only reset only after the runtime
is configured and only for the exact approved binary/hash whose terminal cause
is `interpretation_unavailable`. The binary ID and SHA-256 must equal the
explicit `BEACON_SEMANTIC_RECOVERY_BINARY_ASSET_ID` and
`BEACON_SEMANTIC_RECOVERY_ASSET_SHA256` bindings. A global advisory lock and
durable `bmq05-first-approved-asset-v1` ledger receipt prevent another asset
from consuming a reset across later calls or configuration changes. Authority
changes, foreign failures, tagged assets, digest mismatch and a second reset fail closed. The retry interprets
authenticated owner context only; it performs no filename inference,
publication, spend, customer send or provider mutation. Lifecycle remains
`WORKING / CONFIG_REQUIRED / SOURCE_REPAIR_ACTIVE`; **NO BUSINESS OUTCOME**.

#### Supervised Mixer physical commissioning evidence in progress

On `2026-08-24` the owner first reported `CH2 OFF, pump stopped`; exact source
wall-clock time was not supplied and remains Unknown. This is attributable
physical preflight evidence for existing `RMQ-20260813-02`, not commissioning
completion. At `2026-08-24T16:15:11+02:00` Control Tower received the owner's
next physical observation: `CH2 ON, pump running, tank recirculating` for
`Controller (1) Right` / device `100204d497` / CH2 `Kunsmis Meng`. The owner is
now observing the existing 300-second native auto-OFF window. No Injection CH1
or Borehole action is authorized or reported. Completion remains blocked on
physical pump/recirculation stop at native timeout plus exact provider OFF and
canonical execution/commissioning readback. **OWNER ACTION: observe only and
report immediately when CH2, pump and recirculation stop; do not toggle another
control or retry ON.**

The owner subsequently reported `CH2 auto-OFF, pump stopped, recirculation
stopped.` This is attributable physical mapping and native 300-second fail-stop
proof, not a ROOTLINE outcome. The next deployed manager readback at
`2026-08-24T14:20:22.769628Z` reached generation 8 with readiness digest
`3da21131194f782aaefe4b393a8405f99958f7f2a739330a57bdc8c74eaf985b`,
unknowns `[]`, and zero canonical auxiliary execution events. Under the
readiness collector contract this proves fresh authoritative provider binding,
CH2 current OFF, native auto-OFF exactly 300 seconds, no conflicting active
auxiliary execution and zero provider control calls. It also proves the manual
run did not become canonical commissioning.

The exact existing governed continuation is one fresh owner Telegram presence
statement bound to Mixer CH2, followed by the ROOTLINE protected preview and
one actor-bound `Confirm` approval. The runtime must then own one exactly-once
ON, native timeout/recovery, provider OFF, physical stopped-flow evidence,
canonical completion and zero-ON replay. No manual repeat, Injection CH1 or
Borehole action is part of this acceptance.

### 2026-08-24 - Mission Control latency outcome and ROOTLINE current hold

Existing `CMQ-20260813-05` achieved one bounded owner-visible outcome without
closing the broader operating-spine mission. PR #1236 merged as exact main
`c210c5295c37d0ca6424173207387ba24621d113`; Render loaded that exact revision.
Two separate authenticated owner-page loads then displayed all six current
canonical Control Tower missions with their counts, details, next steps and
owner-action state inside the existing Mission Control page, with no timeout.
This retires the page-critical query-latency acceptance gate only. CMQ remains
`WORKING`: runner continuity, automatic governed mission progression and the
broader operating-spine acceptance are not claimed complete. No mission, row,
store, page, priority, provider or farm state was created or changed by this
register receipt.

ROOTLINE PR #1237 exact head
`4444861d6be5f6af33f98e869b05e05369aff537` independently passed against its
then-current base with 69 focused local tests, 32 independent focused tests,
clean diff and all four hosted gates. It adds a production-shaped pre-upgrade
message `3986` predecessor and proves the clock-only `3987` successor is silent,
while fixed deadlines, changed B/C semantics, lifecycle/completion and owner
questions remain material. Main subsequently advanced to the disjoint CMQ
merge above, so #1237 is being reconciled and re-gated before any integration;
no stale-base merge or deployment is authorized.

The owner's fresh Mixer presence statement did not reach the deployed direct
Telegram webhook: Render request evidence through
`2026-08-24T14:42:47.051211Z` contains no corresponding POST, and canonical
readback at `2026-08-24T14:40:05.648244Z` contains no new Mixer claim or card.
The remaining `active` presence claim was created on 16 August, expired on 17
August and has no preview-card binding. It is historical stale state, but it
cannot have intercepted a new request that never reached Amadeus. Exact blocker
is upstream Telegram/n8n relay ingestion; root cause below that boundary is
still Unknown. Zero new claim, card, execution, provider call or hardware/farm
effect occurred. `OWNER ACTION: NONE`: do not resend the message, press an old
button or operate CH1, CH2 or Borehole until exact dedupe-safe relay recovery is
proved and one fresh protected Mixer preview is visible.

#### ROOTLINE message 4000 post-deploy silence failure

The first natural reassessment after exact live revision
`42d8708335e89b8a1977dd69d4c45e2d314c03bf` did not meet the unchanged-plan
silence gate. Observation
`OOM-ROOTLINE-OBS-CE14204919D0E97A5B5C1BDD-RECORD_OBSERVATION` at
`2026-08-24T15:46:54.825893Z` produced result
`ROOTLINE-RESULT-20260824-A700309E8F09AE5E`; pending notification
`OOM-ROOTLINE-REASSESS-A0AE5380D99026A01B83AD12` was then provider-confirmed
as Telegram message `4000` at `2026-08-24T15:47:06.599047Z`. Its visible B/C
plan, question and owner action were unchanged from delivered message `3997`;
only the approximate next-check clock moved from `17:46` to `18:16`. This is a
notification acceptance failure, not an irrigation, fertilizer, borehole or
farm effect and not an owner outcome.

Exact readback identified two same-lineage predicates: the pre-v3 message
`3997` packet had no semantic fingerprint, and the one-way legacy transition
excluded current trigger `refresh_missing_or_stale_evidence`; the v3 packet for
message `4000` also retained its moving `at` value inside the otherwise stable
reassessment fingerprint. The bounded correction normalizes only that `at`
value for this exact trigger and admits the trigger to the exact-bound one-way
legacy transition. Trigger, reason, conditions, recipient, operating date,
provider receipt, predecessor identity, fixed deadlines, visible B/C state,
lifecycle, verified completion and owner questions remain material and
fail-closed. No new mission, notification rail, store, queue, scheduler or
priority is created. Lifecycle remains
`WORKING / POSTDEPLOY_ACCEPTANCE_FAIL / CLOCK_FINGERPRINT_REPAIR_ACTIVE`;
acceptance still requires reviewed deployment followed by two natural
unchanged cycles with zero standalone plan messages and one later genuine
material change producing exactly one successor. **OWNER ACTION: NONE.**

#### Mixer message 4001 misrouting and ROOTLINE message 4003 continuation

At `2026-08-24T16:13:21Z` the owner sent the exact governed Mixer readiness
phrase as Telegram message `4001`. The direct webhook reached exact live
revision `829b161f7f396b7e8b013e9aa98a6b953e1fc18e` but returned HTTP `409` and
incorrectly projected existing manager-question mission
`OOM-FAMILY-396CC42918431530CA7C373E` with task state
`manager_question_rootline_observation_ambiguous`. The unrelated clarification
`Which is full: the reservoir or the storage tanks?` was provider-confirmed as
message `4002` at `2026-08-24T16:13:40.976546Z`. No fresh Mixer claim or card
was created; the only active row remains the expired, unbound 16 August claim.
There was no confirmation, execution, provider-control call, irrigation,
fertilizer, borehole or farm effect. The exact source defect is precedence:
the broad manager-question continuation runs before the already exact-matched
Mixer specialist path. The repair moves only that exact phrase ahead of the
manager question while preserving actor, chat, chronology, specialist mission,
card, digest, pending-context, replay and zero-authority checks. All non-exact
manager replies retain their existing path. **OWNER ACTION: NONE; do not resend
or press message 4002.**

The first natural reassessment after revision `829b161f...` was claimed at
`2026-08-24T16:16:12.988067Z`, retained unchanged visible B/C decisions,
reasons and owner question, but delivered another standalone plan as message
`4003`. Its internal structured scheduler reason shortened from
`Refresh forecast, tanks.` to `Refresh tanks.`; that token does not appear in
the delivered owner plan. This is continued failure of the same notification
mission, not a new mission or priority change. The semantic fingerprint is
therefore versioned to bind the rendered owner-visible plan only: visible B/C
decision/reason, lifecycle or verified completion, fixed-deadline wording and
owner-question changes remain material, while hidden trigger/reason/clock churn
cannot manufacture an identical standalone plan. Lifecycle remains
`WORKING / POSTDEPLOY_ACCEPTANCE_FAIL / OWNER_VISIBLE_FINGERPRINT_REPAIR_ACTIVE`.

#### Mixer message 4005 protected-preview failure after revision 857c6125

At `2026-08-24T17:27:55Z` the owner's confirmed exact governed Mixer phrase
arrived as provider message `4005`; the n8n webhook completed HTTP `200` at
`17:28:34Z` on exact live revision
`857c612560a861a5f7dea5400c9b625109aa377c`. The specialist readback was safe
and current (`all_outputs_off=true`, Mixer CH2 native auto-off `300s`), but the
gateway persisted `contextual_followup_claimed` against stale parent Telegram
message `3480` and delivered plain readiness message `4006` instead of creating
the protected Mixer claim/card. The expired 16 August presence claim remained
and was not atomically retired. This is a further acceptance BLOCK in existing
`RMQ-20260813-02`, not a new mission or priority change. There were zero
provider-control calls, hardware commands or farm writes and no confirmation
or actuation. The bounded repair makes the exact commissioning phrase enter
the protected claim/card delivery boundary immediately after specialist
acceptance, before any generic contextual projection, while retaining actor,
chat, age, mission, digest, concurrency, replay and confirmation safeguards.
Lifecycle is `WORKING / PROTECTED_PREVIEW_ACCEPTANCE_FAIL / REPAIR_ACTIVE`.
**OWNER ACTION: NONE; do not resend or confirm until a reviewed repair is live.**

#### Mixer message 4007 cross-action stale-claim handoff failure

After reviewed PR #1242 merged and exact revision
`642af37cf77fec6bdb81d1bd1b5f322080a7bef3` was live, fresh manager readback
again proved all outputs OFF and Mixer CH2 native auto-off `300s`. The owner's
one exact post-deploy phrase arrived as message `4007` at
`2026-08-24T17:43:01Z`; webhook HTTP `200` completed at `17:43:41Z`. The direct
protected boundary was reached, but the old active-status, expired, unbound
`rootline_fertilizer_mixer_presence_refresh` row is a different action kind
from `rootline_fertilizer_mixer_commissioning`. The generic claim rail correctly
refused to retire that foreign-action row, so no commissioning claim/card was
created; the gateway then misleadingly retained the earlier plain readiness
answer and delivered message `4008`. This is the same `RMQ-20260813-02`
acceptance blocker, not a new mission or priority change. The repair adds one
explicit atomic handoff: only the exact expired, unbound presence predecessor
for the same mission, actor, chat and canonical payload digest may retire before
the commissioning insert. Live, bound, malformed, mismatched and unrelated
claims remain blockers. Claim failure produces an explicit contained/no-start
answer and can never reuse plain readiness. There were zero provider-control
calls, hardware commands or farm writes. Lifecycle is
`WORKING / CROSS_ACTION_STALE_CLAIM_BLOCK / HANDOFF_REPAIR_ACTIVE`.
**OWNER ACTION: NONE; do not resend or confirm during repair.**

### BMQ-20260813-05 protected-delivery ambiguity follow-up containment — 2026-08-24

- Consolidated OMQ-20260813-03 natural-cycle finding into this existing BEACON sale/media lineage without changing mission priority.
- Production readback proved one immutable BEACON manager generation was reclaimed every five minutes after an exact protected card update became provider-ambiguous. The protected lifecycle correctly forbade a duplicate provider call, but the manager case retained an already-due reassessment timestamp and therefore recorded an exception forever.
- The bounded repair keeps the generation visibly contained and unconfirmed, preserves every protected publication and actor/card/digest boundary, and makes explicit do-not-retry provider ambiguity terminal for that immutable generation. Unchanged cycles cannot reclaim it; genuinely changed canonical evidence still creates a successor generation normally.
- No provider, publication, spend, customer, farm, hardware or production-data effect was performed. Business completion remains false until deployed natural cycles prove the reclaim loop stopped and later reconciliation remains safe.

## 2026-08-24 - ROOTLINE provider-readback commissioning authority addendum

Charl explicitly authorized the existing `RMQ-20260813-02`,
`RMQ-20260813-03` and `RMQ-20260813-06` lineages to use fresh authoritative
application/provider ON then OFF readback as sufficient operational start/stop
proof for the governed Fertilizer mixer, Fertilizer injector and Borehole
controller. Routine owner physical presence/observation is removed; Charl and
Anton report exceptions later. No new mission or priority change results.
Existing boundaries remain: Mixer is exact CH2 with a 300-second fail-stop;
Injector requires exactly one active irrigation zone, at least ten minutes
pre-flow, at most 120 seconds ON and at least ten minutes flush; Borehole cannot
be commanded until exact binding and bounded fail-OFF are proven. Every path
still requires idempotency, replay/concurrency containment, canonical lifecycle
and final verified OFF. A command receipt alone proves no outcome.

The same decision authorized exactly one retry of failed GateKeeper execution
`66525`. Retry `66544` succeeded through the GateKeeper call node, but produced
no fresh canonical Mixer commissioning claim/card on immediate readback and no
pre-confirm hardware/provider-control effect. A second retry is prohibited;
downstream transport diagnosis continues in the existing RMQ-02 lineage.
**NO BUSINESS OUTCOME. OWNER ACTION: NONE.**

Read-only diagnosis proved the live GateKeeper ordinary-message node calls
backend relay `TlKy9kUgJJE0msU4` with `waitForSubWorkflow=false`. On retry,
n8n marked that fire-and-forget call successful and returned unchanged input,
while creating no child execution or durable relay receipt. The relay exposes
only `Execute Workflow Trigger`, so no bounded public child-invocation API exists.
The existing GateKeeper tracked definition is reconciled to the live 2.0B relay
identity and now requires `waitForSubWorkflow=true`; the deployment contract
forces the same receipt-bearing setting when reconciling live workflow state.
Parent success can therefore no longer precede child completion/failure. The
stored message may be recovered exactly once only after reviewed provider
deployment/readback; no direct backend POST, manufactured card or pre-confirm
actuation is permitted.

## 2026-08-24 - GREEN farm-house printer risk acceptance addendum

Charl accepts the confidentiality and local-network risk of practical
farm-house printer operation by the farm team and removes private PKI,
TLS/IPPS and certificate setup as blockers in the existing DMQ/GREEN lineage.
No new mission or priority results. Minimum operational integrity remains:
one fixed approved printer and queue, exact canonical job identity and digest,
bounded retry, no duplicate/replay, and truthful printed-or-failed
canonical/provider readback. No public arbitrary-print endpoint or
caller-selected printer, queue, URL or payload is authorized. Existing jobs,
documents and historical evidence are unchanged. **NO BUSINESS OUTCOME. OWNER
ACTION: NONE** until reviewed source is integrated and one genuine exact job is
read back without duplicate output.

Current `green_print_bridge/DOCS.md` and app source still mandate
`private_ipps`, private CA and TLS validation, and open PR #1194 further
hardens that superseded policy. PR #1194 must not merge; this owner decision is
not operative until a bounded reviewed source correction removes those gates
while preserving the minimum job-integrity contract above.

For `RMQ-20260813-06`, the owner will provide exact Borehole connector/binding
details tomorrow. This is the existing external trigger; ask no further
question tonight and do not command Borehole before exact binding plus bounded
fail-OFF are proven.

## 2026-08-24 - HMQ heat-reminder projection correction

Post-deployment read-only acceptance of existing mission `HMQ-20260813-05`
against exact live revision `2fdecec1444725d07e0b362dc95caaa3c6e99ea6`
proved that the heat-only task and question gates were removed, but the current
operating-loop projection still prepared 13 due `Return-to-heat observation
window` reminders inside a 38-item reminder plan. No reminder was delivered
(`delivery_operational=false`, `sent_count=0`), no canonical or physical effect
occurred, and volunteered `standing_heat` facts remained append-only observation
history. This is the same mission and priority: current and future reminder
projection/delivery must exclude the legacy heat window while the historical
milestone remains available for audit. Source repair is active; **NO BUSINESS
OUTCOME** and **OWNER ACTION: NONE** until deployed readback proves zero heat
questions, tasks and reminders on a later natural cycle.

## 2026-08-25 - DMQ-20260816-01 GREEN 0.3.8 device commissioning receipt

The existing GREEN/DOCUMENTS mission advanced through release and real-device
commissioning without creating another mission, document, queue or print
workflow. PR #1250 merged as exact revision
`844d3a10944e07a5341602ea18b337fca16b0dbd`; PR #1194 was closed as
superseded. Guarded workflow run `32810759240` published the one-time
`linux/arm64` 0.3.8 package and verified its Cosign signature, provenance,
SPDX SBOM, OCI source/version/platform bindings and tag equality at immutable
index digest
`sha256:587e0a21237d5706d42122161a5ec71ae75be54f4cf5db283ee26e5d922ee9bd`.

Charl installed the released package through Home Assistant. Control Tower
corrected the existing saved transport fields to the reviewed bounded profile:
`local_ipp_fixed` and the exact fixed queue endpoint
`ipp://192.168.0.118:631/printers/weekly-a4`. After a stability wait, Home
Assistant reported `Current version 0.3.8` and `Running`. This proves the bridge
is installed and active on the intended device. It does not prove a document
printed: no canonical print job or CUPS submission was created during
commissioning, and no physical page or later continuity readback exists yet.
Lifecycle is `WORKING / BRIDGE_ACTIVE / GENUINE_PRINT_ACCEPTANCE_WAITING`.

The smallest existing governed acceptance path remains the shared DOCUMENTS
weekly-sheet rail already bound to this mission. A genuine private Oom Sakkie
request with semantic intent `weekly_weighing_sheet_print` builds the canonical
`farm.weekly_weight_sheet.v1` revision from current active pigs and creates one
actor-bound `documents_green_print` protected preview. Nothing prints until the
same actor confirms. Confirmation atomically creates the one digest-bound job;
the installed Green worker then claims it, retrieves the exact canonical PDF,
submits only to the fixed `weekly-a4` queue and records CUPS/canonical outcome.
The separate protected physical-page follow-up records printed/incorrect/
uncertain truth and never auto-reprints. Do not manufacture a request, document,
confirmation or job merely for commissioning. **OWNER ACTION: NONE:** the next
automatic action is for Green to remain in its zero-job polling/heartbeat cycle
until a genuine farm need produces the existing protected weekly-sheet request;
Control Tower then follows that single journey through confirmation, provider/
canonical readback and a later terminal-independent continuity cycle.

## 2026-08-25 - DMQ-20260816-01 standing print authority addendum

Charl's authenticated private request to print an allowlisted farm document is
the authority for one bounded GREEN job on the commissioned fixed local queue.
This supersedes the commissioning receipt's preview/Confirm wording: that loop
is a systemic owner-burden defect and must not remain in the natural request
path. Oom Sakkie must create the exact immutable revision, persist a
deterministic digest-bound standing-authority receipt, create/recover the one
canonical job idempotently, follow provider and canonical truth through
completion, and ask Charl only about a genuine exception or physical page
result. One A4 monochrome copy, registry-bound printer and queue, bounded
retry/reconciliation and no automatic reprint remain invariant.

This remains the existing `DMQ-20260816-01` mission and the existing GREEN job,
worker, queue and physical-follow-up rail. The document catalogue is the sole
extension inventory: current governed PDF generators may gain small immutable
revision adapters one at a time, but may not create a second print API, worker,
queue, ledger or confirmation system. Loading sheet, removal/transport, health
declaration and quote are catalogued extension candidates; their direct-print
authority remains fail-closed until each adapter and its evidence binding are
implemented and tested. No job was synthesized or sent by this source change.
**NO BUSINESS OUTCOME. OWNER ACTION: NONE** until integration/deployment and a
later genuine request prove canonical/provider/physical readback.

## 2026-08-25 - PR1251 ROOTLINE standing-authority evidence reconciliation

This append-only entry restores evidence accidentally removed while reconciling
the GREEN standing-print branch. It belongs to the existing ROOTLINE missions
and changes neither priority nor current authority. At the time of the event,
Charl had removed routine commissioning confirmations and human-presence
requirements for already governed ROOTLINE connectors. Fresh authenticated
requests and eligible plans could execute only when exact device, current need,
provider safety, deterministic claim, replay/concurrency and native fail-stop
contracts passed; authoritative application/provider ON then OFF readback was
sufficient operational proof.

Fresh Telegram message `4023` entered GateKeeper execution `66616` at
`2026-08-25T04:49:34Z`; child relay execution `66617` completed before the
parent at `04:50:15Z`, proving the reviewed `waitForSubWorkflow=true` receipt
repair. The backend returned `commissioning_specific_hold` because its first
controller read was incomplete. It created no claim, card or execution and made
no hardware/provider-control call. The automatic collector passed at
`04:50:10.625293Z` with readiness digest
`3da21131194f782aaefe4b393a8405f99958f7f2a739330a57bdc8c74eaf985b`,
unknowns `[]`, exact CH2 OFF, the then-current 300-second fail-stop, no active
execution and zero control calls. This proved a bounded fresh-read timing race,
not an unsafe device state.

Independent review of PR #1251 also proved that its first direct-command head
reached the standing-authority executor without the durable acceptance receipt
required by production and would stop at
`commissioning_acceptance_receipt_unproven`, with zero device effect. The merged
repair records one deterministic, idempotent `contextual_followup_completed`
receipt on the existing ROOTLINE operational-intake rail before execution and
validates mission, owner/chat, provider message/time, text digest, task kind,
zero-effect authority and response contract. Persistence failure remains
fail-closed. Later Mixer commissioning/native-limit and Borehole connector
decisions remain authoritative over the historical readiness envelope recorded
here; this reconciliation does not roll them back. **OWNER ACTION: NONE.**

## 2026-08-25 - Anton mortality GateKeeper dependency failure

Fresh Telegram message `4028` entered the existing HERDMASTER/Oom Sakkie
lineage at `2026-08-25T07:03:14Z`, but GateKeeper execution `66636` stopped at
the pre-routing Google Sheets `Get User Info` authorization lookup with HTTP
503. The live node had no retry. The backend therefore received no message and
created no semantic result, claim, delivery, observation, welfare or lifecycle
effect. This is an ingress/auth dependency failure, not a safe semantic hold or
canonical writer failure. The old provider update must not be replayed.

The bounded repair performs one initial authorization read and at most four
retries, two seconds apart, only for HTTP 429, HTTP 5xx and transport failures.
HTTP 401/403 and all other deterministic 4xx failures stop after the first read.
The maximum envelope is five reads and approximately eight seconds of retry
wait. Exhaustion remains fail-closed, and only one successful authorization
result may reach the backend route, so retries cannot duplicate a backend
message or farm effect. **NO BUSINESS OUTCOME. OWNER ACTION: NONE** until the
reviewed workflow is deployed and a later genuine provider interaction proves
the full actor-bound mortality journey and terminal-independent continuity.

## 2026-08-25 - RMQ-20260813-06 Borehole 1 exact connector and standing authority

Charl supplied the existing Borehole 1 connector binding: eWeLink device
`1002851416`, display `Boorgat 1 Krag Toevoer`, SONOFF MINI R4 sole output
(logical channel 1), exact IFTTT events `borehole_1_on` / `borehole_1_off`,
power-restoration OFF and native four-hour auto-OFF. The supplied Maker key and
URLs are secret and are intentionally absent from this register, repository,
PR and evidence. They may be consumed only through the existing protected
`ROOTLINE_IFTTT_MAKER_KEY` configuration rail.

Owner standing authority removes routine presence and preview/confirmation.
Fresh provider/app OFF -> ON -> OFF is sufficient operational proof for this
governed power connector. The approximately 1.2 kW inverter load is supporting
evidence only, never a gate or stop. The internal tank-full cutoff may stop the
pump while the plug remains energized, so plug ON never proves pumped volume or
storage gain. ROOTLINE may schedule repeat bounded overnight segments from
canonical water need, power and no-rain evidence, but each segment requires an
exclusive deterministic claim, exactly one ON attempt, native/primary deadline,
bounded OFF recovery, authoritative final OFF and restart recovery. No live
configuration or actuation occurred. **NO BUSINESS OUTCOME. OWNER ACTION: NONE**
until reviewed source is deployed and the protected secret/configuration and
canonical standing-active baseline are proven loaded.
## 2026-08-25 - DMQ-20260816-01 held print-request recovery repair

GREEN now retains an authenticated private weekly-print request in the existing
protected-action table before attempting job authorization. The receipt binds
owner, private chat, provider message, exact request-text SHA-256, preview
digest, document revision and fixed device registry. A transient commissioning
precondition rolls back the job but leaves that receipt `active` for the
authenticated morning scheduler to reassess. Recovery never replays Telegram;
it advances the same receipt through `executing` to `completed`, and completed
replay resolves the same deterministic job. One A4 monochrome copy, fixed
`weekly-a4`, and no automatic reprint remain invariant.

The historical genuine request is Telegram message `4031`, update `549158359`,
text SHA-256 `cd2252a44d92a29cc7ae94a0885a3a7d3ed0f527276f696f124871f9c45ddb4c`,
and n8n executions `66641`/`66642`. It may be adopted only after this reviewed
revision deploys, after readback proves the activated canonical registry and
zero prior jobs/claims/events for that request. Adoption must use those exact
provider facts, record an audit receipt, and then allow the scheduler rail to
continue it; it must not synthesize or replay a Telegram update. No adoption or
print job was performed by this source change.

## 2026-08-25 - HERDMASTER continuous-husbandry Molly first-treatment parity intake

The new Molly Telegram finding is consolidated into the existing
`HERDMASTER / HERDMASTER` continuous-husbandry operating loop recorded in the
Continuous Agent Operations Reset; it is not a new HMQ mission, litter mission,
Telegram queue, farrowing workflow or treatment database. That existing loop
already names Molly's omitted due treatment as an acceptance blocker and owns
continuous litter, treatment, medical and welfare work through the canonical
HERDMASTER queue and Oom Sakkie follow-through.

Current owner-visible parity is not proven. Canonically due-and-ready Molly
litter first-treatment work may appear in the shared Owner Attention projection,
but the genuine Telegram manager journey must carry the same current task and
must follow it through the existing protected litter-treatment action to exact
canonical readback, reassessment and retirement. Unknown, partial, already
completed or durably skipped evidence must remain non-actionable. No product,
dose, treatment fact or completion may be inferred, and a Telegram message or
button alone is not a farm outcome. The owner must not be asked to rediscover,
relay or repeatedly chase due work that HERDMASTER and Oom Sakkie already own.

The current implementation owner is the isolated source worktree
`C:/tmp/herdmaster-litter-treatment-telegram-parity-20260825`, branch
`fix/herdmaster-litter-treatment-telegram-parity-20260825`, created from exact
main `78b724fa487a9ceadfc4a52512e260bb89ea71e0`. Farrowing database authority,
natural health/loss, welfare, weighing, breeding and historical litter PRs are
collision evidence only; they do not authorize a second treatment writer or a
Molly-specific bypass. Priority is unchanged. **NO BUSINESS OUTCOME. OWNER
ACTION: NONE.** Automatic continuation is the same-lineage source repair,
independent review, exact deployment, then one fresh genuine Telegram cycle
proving names-first parity, one protected exact treatment journey when truly
due, canonical completion/readback, replay containment and a later stable cycle
without repeated work.

## 2026-08-25 - HMQ-20260813-05 automatic completed-batch consumption source repair

The accepted selective-BCS batch exposed the existing closed-loop defect: its
canonical weight and observation events were complete, but no deployed
automatic cycle had projected the material exact-pig findings into stable
HERDMASTER manager cases. Read-only manual analysis was not an owner outcome.

The bounded repair reuses the existing five-minute general-manager worker and
`oom_manager_cases` lifecycle. It reads only completed canonical batches,
binds every finding to the exact pig plus batch and weight/observation event,
selects only the deterministic latest qualifying event per pig/case across the
bounded completed-batch window, and uses stable pig-scoped dedupe identities.
A material BCS or descriptive
weight change retains a seven-day HERDMASTER reassessment; a newer exact
in-range/non-material event completes that same case. Replay and concurrent
cycles cannot create another case or terminal event. Heat is neither requested
nor inferred. No batch, observation, farm record, provider, scheduler, schema,
queue or store was mutated or added by source preparation.

Source readiness remains distinct from acceptance. Completion requires reviewed
merge/deployment, a natural five-minute worker cycle consuming the already
completed batch without replaying it, exact case/event readback, and a later
terminal-independent cycle proving idempotency and continued ownership.
**NO BUSINESS OUTCOME. OWNER ACTION: NONE.**

## 2026-08-25 - OMQ-20260813-03 Morning Farm Plan outcome projection defect

Live Telegram card `4033` (observed `08:16:19Z`, presented `08:16:51Z`) repeated
the same unresolved work seen on cards `4027` and `4029`: terminal Pig 126
mortality appeared as a generic follow-up, ROOTLINE called B/C ready while its
canonical reason said current deficit was insufficient, and weekly weighing
dumped `0/75` plus 75 reconciliation tags. With no genuine question, the same
message then said no action was required and exposed a 15-minute backend poll.
This is consolidated into existing `OMQ-20260813-03`; no new mission, store or
priority was created.

The bounded source repair preserves the shared Daily Farm Manager and canonical
specialist rails. It distinguishes exact owner-required work from Oom Sakkie's
automatic reconciliation, removes raw polling and long reconciliation commands
from owner output, preserves exact mortality lifecycle closure binding, and contains exact ROOTLINE
Eligible-versus-insufficient-deficit conflicts as automatic safe checking.
Source completion is not acceptance. Completion still requires merge/deploy,
a later natural concise Brief, unchanged-cycle silence and proof that specialist
work advances or reports a bounded exception without duplicate effects.
**OWNER ACTION: NONE.**

### First natural post-deploy acceptance — FAIL

The first owner-supplied natural Morning Plan after exact deployed revision
`f4c26fdc205f06dd0e20f3a2f0a1a5409348b6ef` read: `TODAY'S FARM PLAN`;
`OOM SAKKIE IS CHECKING AUTOMATICALLY`; mortality follow-up
`PIG-2026-3EE5`; irrigation B and C `Checking safely`; weighing `0/75` with
75 tags needing status reconciliation; and `No action required`. This proves a
shorter provider-visible presentation, but the owner found it not useful or
end-to-end. It does not prove specialist dispatch, canonical advancement,
closure, or a useful bounded exception for any listed work. The existing
`OMQ-20260813-03` acceptance therefore remains **FAIL / NO BUSINESS OUTCOME**;
priority is unchanged and **OWNER ACTION: NONE**.

## 2026-08-25 - ROOTLINE standing-device activation and silent reassessment repair

This finding is consolidated into existing ROOTLINE `RMQ-20260813-03A`,
`RMQ-20260813-06` and Oom/ROOTLINE operating-spine lineage; it is not a new
mission, scheduler, device store or notification rail. Owner-confirmed device
baselines are Mixer CH2 / `100204d497` / 1,800-second native auto-OFF,
Injector CH1 / the same controller / 120-second native auto-OFF, and Borehole 1
/ `1002851416` / four-hour native auto-OFF. Standing authority removes routine
presence and confirmation, but every real ON still requires an exact current
need-driven task, canonical `standing_active` device record, enabled production
flag, provider safety, deterministic claim and bounded final OFF/readback.

Fresh owner evidence also proves an existing-mission Telegram defect: periodic
no-action water-plan cards exposed `now_after_fresh_execution_revalidation`,
`durable parent objective` and readiness wording while asking for nothing.
The bounded repair preserves durable observations and automatic reassessment
silently. Only a hardware start, verified completion/stop, failure, or one exact
owner decision may notify; internal reason/window tokens never render. Source
and tests are not an owner outcome. Completion requires reviewed merge,
deployment, loaded revision, a genuine need-driven device execution with exact
provider/canonical readback, and a later terminal-independent silent/no-duplicate
cycle. **DURABLY LOGGED only after commit. OWNER ACTION: NONE.**

Independent review blocked the first source head because the Injector task was
not promoted by the planner, Mixer eligibility expanded every task to the full
native limit, and scheduler-composition recovery coverage was incomplete. The
same mission repair now promotes Injector only from exact active-zone,
pre-flow, flush-window, batch and current-need evidence; binds Mixer execution
to the task's remaining daily `planned_seconds` (including split sessions); and
tests Injector start plus Mixer/Borehole active recovery to final OFF with no
ON retry. This remains source/review evidence only. **NO BUSINESS OUTCOME.
OWNER ACTION: NONE.**

B/C start readback is retained as immutable pre-flow evidence; immediately
before Injector planning the scheduler refreshes the exact canonical active
zone's provider output and promotes only an authoritative fresh ON bound to the
same execution. A stale start receipt cannot masquerade as current flow.
No readback grants authority for a different zone or execution.

The subsequent exact-head rereview found that injected tests had bypassed the
production evidence loader. The default canonical loader now reads the existing
append-only ROOTLINE execution and authenticated operational-intake rails for
completed fertilizer executions, current-week batch observations, fresh
explicit fertilizer need, one exact active irrigation execution and fresh
Borehole interlocks. Missing, stale, malformed or database-unavailable fields
remain absent and therefore command-inert. End-to-end default-loader tests now
cross loader, planner and scheduler for both eligible and ineligible outcomes;
they do not manufacture production evidence. **NO BUSINESS OUTCOME. OWNER
ACTION: NONE.**

## 2026-08-25 - HMQ-20260813-05 selective Bulk BCS natural acceptance

Read-only production evidence proves genuine canonical capture in the existing
`HMQ-20260813-05` lane, supported by `HMQ-20260813-00`. Batch
`df4c6197-4b2c-4253-b120-b07ad69305f4` was created at
`09:59:29.645Z` and completed at `10:03:00.828Z`: 79 rows were visible and
actionable, 79 weights and 7 moves succeeded, and the batch recorded 79 success,
zero failed and zero duplicates. Draft
`BULK-DRAFT-1787650403572-8e45ea` produced five separate canonical
`pig_observation_events`, each bound to the bulk-BCS draft-plus-pig idempotency
and append-only supersession contract:

- Bonnie / `PIG-2026-5376`: BCS `3.5`, event
  `HERD-OBS-5F9A52DC43BA509393A2A6A189231CDC`;
- Teena / `PIG-2026-74FF`: BCS `2`, event
  `HERD-OBS-22388C055CF15234B27AAEB757726210`;
- Waki / `PIG-2026-7531`: BCS `2`, event
  `HERD-OBS-C59CE145C1F257D5B996BBFD69D77A10`;
- Ms Piggy / `PIG-2026-92F3`: BCS `3.5`, event
  `HERD-OBS-E0CED0A5325E5D1F8D30854BE55ACDBD`; and
- Zigay / `PIG-2026-EEAC`: BCS `3`, event
  `HERD-OBS-BB5068789C07574EBBF0B571C5144CF3`.

A manually invoked read-only heat-free management projection consumed these
observations with `writes_performed=false` and produced zero heat-required
tasks. It created or updated zero manager cases bound to the five exact pigs.
That is diagnostic projection evidence only: an automatic deployed cycle, its
next follow-up and later independent continuity proof remain unproven.

This is a genuine canonical selective-BCS acceptance outcome, not a replay or
manual correction. The owner nevertheless saw no BCS in Draft Preview Upload
progress, so owner-visible presentation remains **FAIL / PRESENTATION DEFECT**;
it does not negate the proven canonical capture. No new mission or priority was
created, no production write/replay was performed by Control Tower, and
**OWNER ACTION: NONE**. The accepted batch must not be resubmitted.

## 2026-08-25 - Existing HERDMASTER natural-litter journey Linda intake

The owner's 2026-08-22 Telegram report — `Morning, Linda gave birth to 9
piglets. 8 alive, 1 mummified, Date 2026-08-22` — is consolidated into the
existing PR `#1161` / PR `#1167` natural-litter acceptance lineage. No new
mission or priority was created. Retained provider evidence proves the genuine
report at `07:20Z` followed by an incorrect clarification at `07:21Z`; exact
historical provider message IDs were not retained and remain Unknown. The
message must not be replayed or requested again while the production authority
gate remains unresolved.

Fresh read-only canonical evidence identifies Linda as `PIG-2026-5AA8`, Active
and on farm. Her only canonical litter is historical `LIT-2026-MNB9`, dated
2026-01-30 and Weaned; there is no 2026-08-22 litter, mating row, Linda-bound
manager case, farrowing protected claim or preview card. The missing litter is
therefore a genuine end-to-end acceptance failure, not a UI-only visibility
defect.

Current source contains the reviewed semantic `record_farrowing_litter` route,
dedicated `herdmaster_record_farrowing_litter` protected claim/runtime and
exactly-once canonical writer; the focused current-source family passes. PR
`#1161` merged as `a6b3112fe3a3008af763685e5b1ca31ab814963f` and DB release
PR `#1167` merged as `61a8d196736a2153e87e12b910445967a9ba6ed6`.
Production readback nevertheless shows migration
`202608220001_extend_litter_supersession_for_fact_corrections` applied but not
`202608220002_allow_herdmaster_farrowing_protected_claims`; the loaded Render
revision could not be reached from this read-only terminal and remains Unknown.
The route is source/test-ready but not proven production-ready. Next automatic
work is to reconcile and apply the already governed missing migration through
the protected migration rail, verify exact loaded revision and duplicate-safe
readback, then request one fresh owner report only when the deployed path is
ready. **NO BUSINESS OUTCOME. OWNER ACTION: NONE; DO NOT RESEND YET.**

Fresh terminal-independent acceptance on 2026-08-25 supersedes that readiness
state. A new genuine Telegram report created protected claim mission
`OOM-HERD-LITTER-E71867CF692725B072D0D50C`; provider-confirmed preview `4048`
was authorised and completed at `19:20:10.620365Z`. Canonical readback proves
Linda (`PIG-2026-5AA8`) now has active litter
`LIT-OOM-D7F1943733BEDCE0` dated 2026-08-22 with 9 total, 8 born alive, 0
stillborn and 1 mummified. HERDMASTER follow-up case
`OOM-MANAGER-HERD-LITTER-D7F1943733BEDCE0A1C82B0C` is open for the next litter
care cycle at `2026-09-01T19:20:05.623678Z`. The canonical farrowing and
automatic follow-up owner outcome is **PROVEN**; it must not be replayed.

The same genuine journey exposed a presentation defect: preview and completion
led with internal ID `PIG-2026-5AA8` rather than Linda. This is a bounded
addendum in the same lineage, without priority change. Shared rendering must
lead with the escaped canonical animal name, show the ID only as secondary
context, fall back to ID when no name exists, and preserve English/Afrikaans
channel output without changing canonical truth. **OWNER ACTION: NONE.**

## 2026-08-25 - HMQ-20260813-05 automatic batch-to-management owner outcome

The existing `HMQ-20260813-05` lineage has advanced from source-ready to a
genuine deployed-agent outcome for completed-batch consumption. PR `#1270`
passed independent review and merged as exact revision
`8465103df799acd7b6225c8c98440ccb4cfa05b5`; Render loaded that revision.

The terminal-independent Oom Sakkie general-manager cycle
`OOM-MANAGER-CYCLE-20260825T121524106342Z-E5A83E83364E4A2D90C67A6F924FEE71`
consumed genuine accepted batch `df4c6197-4b2c-4253-b120-b07ad69305f4` at
`2026-08-25T12:15:24.106342Z`. It created exactly seven stable HERDMASTER
cases, each generation 1 with exactly one append-only `created` event:

- Teena BCS 2: `OOM-CASE-D2D021AD952D54D4EBB16689`;
- Waki BCS 2: `OOM-CASE-06F41E4EF440CC20585E312C`;
- tag 138 weight -20.0%: `OOM-CASE-FF00ED3DB3A385AE091C08EF`;
- tag 139 weight -10.6%: `OOM-CASE-C9695FF2BE2A3A3C1BF4A52E`;
- tag 111 weight -10.3%: `OOM-CASE-C1A2AB12E9C1A2D664B32A4B`;
- tag 2 weight +15.6%: `OOM-CASE-BDE56DBB892229C103AC8541`; and
- Ms Piggy weight -22.6%: `OOM-CASE-1FB5B5C3B6F7C36E412265F5`.

Later terminal-independent cycles from `2026-08-25T12:20:28.858735Z` through
`2026-08-25T13:40:23.087785Z` created zero cases. The seven exact batch cases
remain generation 1 with unchanged evidence digests and unchanged update time
`2026-08-25T12:15:24.106342Z`, proving replay containment and no multi-batch
generation churn. The three in-range BCS observations correctly created no open
case. No heat evidence, question, task, reminder, confidence penalty or blocker
was introduced.

**OWNER OUTCOME PROVEN** is deliberately bounded to automatic completed-batch
consumption, durable material-case ownership and later terminal-independent
idempotency. The seven material cases remain open with reassessment dates around
`2026-09-01`; their later animal outcomes are not claimed. The next automatic
action is HERDMASTER reassessment from fresh canonical condition, appetite,
movement, welfare, weight and lifecycle evidence. **OWNER ACTION: NONE.**

### CONTROL TOWER CHECK RECEIPT

- Governance: PASS - Control Tower current-main worktree
  `C:/tmp/linda-migration-diagnosis`, HEAD/main `8465103d`; Standard blob
  `3002b94713e286c4eb2019419c438cc378c337fa` (1127 physical lines), Protocol
  blob `8fbd0b9c9160164e31a17a2cbfa51ab88792a909` (319), Programme blob
  `fb44d7f86c47e605c283ed33c28ba2c4267d6edb` (278); all tracked and read
  completely.
- Feedback freshness: current - production cycles and canonical readback were
  observed after the exact deployment.
- Terminal truth: released - PR `#1270` is merged; no terminal is sustaining
  the runtime cycle.
- Runtime truth: autonomous - scheduled worker
  `oom-sakkie-general-manager-v1`, trigger
  `oom-sakkie-morning-scheduler:general-manager`, exact loaded revision,
  repeated five-minute cycles and next-cycle timestamps are canonical.
- Mission: `HMQ-20260813-05` - bounded owner outcome proven; seven material
  animal follow-ups remain open.
- Strategic WIP: existing operating-spine outcome-depth activation; no new
  mission or priority.
- Owner workload delta: manual post-upload inspection and case creation -> zero
  post-upload case-creation steps; natural worker and later cycles prove removal.
- Release lane: released after exact deploy and readback.
- Collision/worktrees: clear for this documentation-only receipt; historical
  weighing, observation and review worktrees preserved.
- Owner repetition: none; accepted batch must not be resubmitted.
- Register: updated in this existing mission lineage.
- All-terminal sweep: delegated to the root Control Tower because this
  specialist receipt does not hold current state for unrelated terminals.
- Dispatch: `CONTINUE - SEND NOTHING`; deployed HERDMASTER/Oom Sakkie worker
  owns reassessment automatically.

## 2026-08-25 - OMQ-20260813-03 owner-useless mortality current-case card

**INTAKE RECEIPT — DURABLY LOGGED, NOT YET AN OUTCOME**

- Finding: Telegram delivered `OOM SAKKIE — HERDMASTER CURRENT CASE` for
  `PIG-2026-3EE5` using internal terms (`canonical`, `attributable`), an ISO
  reassessment timestamp and the vague instruction `Review this individual
  once`, without stating a farm question or offering a usable decision.
- Classification: existing-mission defect, consolidated into
  `OMQ-20260813-03` and the existing HERDMASTER continuous-husbandry /
  mortality-follow-up lineage. No new mission, queue, page or workflow.
- Exact owner outcome: Oom Sakkie remains silent while HERDMASTER can continue
  automatically. If one farm fact is genuinely missing, Telegram identifies
  the pig in owner-recognizable terms and asks exactly that question; a simple
  bounded choice uses buttons. Internal state codes, database language and raw
  timestamps are never owner output.
- Duplicate/collision result: this extends the existing Morning Farm Plan and
  owner-attention projection defect; it does not change mission priority.
- Canonical location: this register section plus the existing general-manager
  case delivery and HERDMASTER daily-manager adapter. Canonical animal and
  welfare lifecycles remain authoritative.
- Current status: implementation under review. Cases with no owner question are
  suppressed; owner-visible follow-up text no longer exposes canonical jargon
  or raw reassessment timestamps. Existing automatic reassessment is retained.
- Priority position: unchanged within active `OMQ-20260813-03`; the finding
  unblocks the already-prioritized useful-manager outcome.
- Next automatic action: reviewed release, exact loaded-revision proof, then a
  natural cycle proving the no-question card remains silent and any genuine
  question is concise and actionable.
- Owner action: none. Do not ask Charl to interpret or close the current backend
  card and do not manufacture a reply to it.

### 2026-08-25 no-question queue rotation addendum

**DURABLY LOGGED — NOT YET AN OWNER OUTCOME.** Natural exact-production cycles
after the no-question suppression deployment exposed a blocking defect: the
suppression result did not advance `next_reassessment_at`, so the same first 20
already-due cases could be reclaimed every five minutes and starve later work.
This remains within `OMQ-20260813-03`; priority is unchanged. The bounded repair
returns a fresh five-minute cadence through the existing finish-claim path and
adds a 21-case/two-cycle rotation regression. PR `#1275` also touches this
register but not the runtime/test files; both receipts must survive integration.
Source completion is not the owner outcome. Natural fair rotation, silence for
no-question work, later genuine-question delivery and terminal-independent
repetition remain required. **OWNER ACTION: NONE.**

Natural acceptance at exact revision `e983221e` narrowed the defect further:
the first cycle's 20 suppressed cases comprised 19 older non-farm suppressions
and one duplicate suppression, which also retained overdue timestamps. The
canonical follow-up therefore enforces cadence advancement in `_finish_claim`
for every successful unconfirmed outcome lacking an explicit future schedule,
while preserving explicit future schedules and existing confirmed/failed
behavior. Mixed-status fair rotation remains under review; no owner outcome is
claimed. **OWNER ACTION: NONE.**

Natural production acceptance then proved the queue repair: the
`15:25:14.264025Z` and `15:30:32.913131Z` cycles processed disjoint sets of 19
successful suppression-event cases, advanced every one to a future cadence and
confirmed zero provider deliveries. Fair silent rotation is therefore
**OWNER OUTCOME PROVEN**. A separate existing-lineage defect remains for
`PIG-2026-3EE5`: refresh-unavailable on an already confirmed immutable
generation is correctly prevented from downgrading or resending, but the
monotonic guard left its lease/timestamp overdue. The bounded addendum releases
that technical lease and schedules the next cadence while preserving confirmed
truth. It does not close the mortality case or manufacture farm evidence.
**OWNER ACTION: NONE.**

Natural post-`1aa4974d` acceptance exposed a separate global-loop blocker in
the same lineage. Cycle
`OOM-MANAGER-CYCLE-20260825T195518955722Z-2D05EA6CB69E4226B65044D88C45CFE1`
finished Prince, then claimed ROOTLINE mixer case
`OOM-CASE-C0C589F1A0970494C2BB730F` and failed with `ValueError`; bounded
read-only reproduction established `rootline_mixer_registry_binding_invalid`.
That single specialist refresh prevented later due work, including
`PIG-2026-3EE5`, from being finished. This is a blocking defect/addendum in
existing `OMQ-20260813-03`, not a new mission, and priority is unchanged except
that it directly unblocks the existing acceptance. The bounded repair contains
per-case specialist refresh/delivery domain exceptions into an attributable
exception event, stable `waiting_reassessment`, future cadence and lease
release, then continues the queue. Manager-case persistence and systemic
invariants remain cycle-fatal. No provider delivery, closure or farm evidence
is synthesized. PR `#1154` is a shared-runtime collision and must remain
separate; it must rebase and preserve current terminal/provider, cadence and
monotonic-delivery invariants. Independent review blocked initial head
`177a9075` because its try-boundary included canonical `_refresh_claim` store
work. The corrected boundary catches only the specialist invocation; canonical
normalization, locking and persistence failures remain cycle-fatal.
**DURABLY LOGGED - NOT YET AN OWNER OUTCOME. OWNER ACTION: NONE.**

## 2026-08-25 - DMQ-20260816-01 GREEN 0.3.10 migration-rail defect

Governed Render run `32860700895` succeeded at exact source but the closed
allowlist ended before existing migration `202608250001`; the GREEN lease/device
fence was therefore not applied. This is an addendum to existing mission
`DMQ-20260816-01`, not a new mission or print request. The bounded source repair
adds that unchanged migration to the existing closed rail with exact
predecessor/target function and ACL readback, catalog inventory and disposable
PostgreSQL apply/replay/drift/rollback proof. It does not run the migration or
touch production. Existing job `GREEN-WWS-WWS-20260825.r1.a79d4a6effa6`
remains the sole pre-attempt job; it must not be recreated or replayed.
**DURABLY LOGGED - NOT YET AN OUTCOME. OWNER ACTION: NONE.**

### 2026-08-25 normal governed migration dispatch addendum

GitHub rejected blank legacy-adoption inputs before creating a normal governed
migration run. This is an existing `DMQ-20260816-01` rail defect, not authority
to reuse a legacy packet. Those inputs are optional at dispatch while runtime
validation still permits exactly zero or two strictly valid values. No migration
or print recovery occurred. **DURABLY LOGGED - NOT YET AN OUTCOME. OWNER ACTION: NONE.**

## 2026-08-25 - ROOTLINE connector activation evidence reconciliation

Fresh zero-control provider readback is consolidated into existing Mixer
`RMQ-20260813-02`, Injector `RMQ-20260813-03A/03B` and Borehole
`RMQ-20260813-06`; priority is unchanged. Fertilizer controller `100204d497`
CH2 was online/OFF but retained a
300-second native auto-OFF rather than the intended 1,800 seconds. CH1 was
online/OFF with a 120-second native auto-OFF and power-restoration OFF, but no
canonical supervised Injector execution event exists. The current plan remains
`Await batch` / `Await eligible irrigation`, zero fertilizer executions are
recorded and both fertilizer flags remain disabled. A standing-authority
migration or flag activation would therefore manufacture missing evidence.

Borehole `1002851416` CH1 separately reported ON while native auto-OFF,
power-restoration and conflicting-path evidence were incomplete. No current
evidence attributes that ON state to a ROOTLINE flag, scheduler claim or
command. It is evidence only, not a ROOTLINE execution or owner outcome.

The existing governed journey must first obtain corrected CH2 provider readback
and canonical Injector supervised evidence, then bind exact evidence through a
reviewed append-only authority migration before any five-flag configuration.
No database, Render, provider or hardware mutation occurred. **DURABLY LOGGED
— NOT YET AN OWNER OUTCOME. ACTION REQUIRED NOW: Set Mixer CH2 native auto-OFF
to 30 minutes (1,800 seconds).** Do not repeat a Telegram message or presence
statement, and do not perform any Injector or Borehole action now. ROOTLINE owns
fresh readback, commissioning reconciliation and every later automatic next
step.

### 2026-08-25 lost-local-ledger pre-attempt adoption defect

After migration `202608250001` was governed and read back, GREEN 0.3.10 could
not discover the sole canonical job
`GREEN-WWS-WWS-20260825.r1.a79d4a6effa6`: its canonical lease was expired and
pre-attempt, while a fresh local SQLite ledger had no retained row from which
to request lease recovery. This is an existing `DMQ-20260816-01` defect and an
addendum to the retained-local-ledger recovery lineage; it does not change
priority and creates no mission, job, replay, queue or workflow.

The bounded repair lets the existing canonical claim function prefer exactly
one expired `claimed` row only while its immutable device binding is active,
authorization and retry deadline remain current, and attempt, CUPS and provider
identities are all absent. It renews that same row under a locked transaction,
records a `lease_recovered` adoption event, and returns it to the ordinary GREEN
worker so the existing local ledger and submission path continue normally.
Post-attempt, expired-authority, inactive-binding and live-lease rows remain
ineligible. Source, tests, PR, migration and worker execution are not an owner
outcome; physical page proof remains separate. **DURABLY LOGGED - NOT YET AN OUTCOME.
OWNER ACTION: NONE.**

## 2026-08-25 - RMQ-20260813-02 Mixer 1,800-second provider correction readback

At `2026-08-25T20:48:04Z`, fresh zero-control provider evidence verified
fertilizer controller `100204d497` online with CH2 OFF, native auto-OFF enabled
at exactly 1,800 seconds and power-restoration state OFF. CH1 remained OFF at
its unchanged 120-second native auto-OFF with power-restoration OFF. The read
used three provider reads and zero provider control calls.

This resolves the Mixer configuration mismatch in existing `RMQ-20260813-02`;
it does not prove a fresh Mixer execution or owner outcome. The current plan
still reports `Await batch`, Mixer and Injector flags remain disabled and zero
fertilizer execution events exist. Injector `RMQ-20260813-03A/03B` continues
through the existing automatic supervised-evidence lane. ROOTLINE owns fresh
need/pre-flow evidence, bounded execution, provider ON/OFF readback and canonical
reconciliation without another Telegram message, presence statement or owner
action. The append-only authority migration and five-flag activation remain
blocked until the full exact evidence contract is satisfied. **DURABLY LOGGED —
NOT YET AN OWNER OUTCOME. OWNER ACTION: NONE.**

### 2026-08-25 post-adoption immutable-envelope repair

Production readback proved the lost-ledger migration adopted the sole existing
job twice under valid authority and its exact active device binding, but GREEN
never requested the PDF or created an attempt. The worker's local ledger hashed
the complete canonical claim row, including rotating lease owner, token and
expiry. A valid recovered lease therefore appeared to be an identity conflict
before local persistence. This is an existing `DMQ-20260816-01` defect; priority
is unchanged. The bounded 0.3.11 repair compares only an explicit immutable
job envelope, refreshes the stored canonical row and lease when that identity
is equal, rejects every immutable drift, and emits only a credential-free hold
reason. It creates no job, authorization, replay, recovery call or print.
Source completion is not the owner outcome. **DURABLY LOGGED - NOT YET AN
OUTCOME. OWNER ACTION: NONE.**

### 2026-08-25 GREEN 0.3.11 publication-rail binding correction

The reviewed 0.3.11 worker repair merged, but publication preflight found the
existing immutable-image workflow still bound its normal publish/recover lane
to version 0.3.10. Dispatch was stopped before any package effect. This is a
release-rail defect within existing `DMQ-20260816-01`, not a new mission and not
authority to overwrite the immutable 0.3.10 tag. The bounded successor binds
normal publication, SBOM and release-packet names to 0.3.11 while preserving
the separately quarantined historical 0.3.10 partial-publication recovery
contract unchanged. No image, installation, recovery or print occurred.
**DURABLY LOGGED - NOT YET AN OUTCOME. OWNER ACTION: NONE.**

## 2026-08-25 - OMQ-20260813-03 changed-evidence refresh-unavailable cadence

Natural exact-production cycles after `7edd0404` contained the ROOTLINE mixer
exception and completed, but exposed one separate queue-health defect. Prince
case `OOM-CASE-0F6334544590218757B7A013` generation 24 has current evidence
different from its historical confirmed delivery and no current specialist
candidate. `manager_delivery_refresh_unavailable` truthfully sent and closed
nothing and released the lease, but retained overdue reassessment
`2026-08-24T09:05:22Z`, reclaiming one of 20 slots every cycle. This is an
addendum to existing `OMQ-20260813-03` / HERDMASTER continuity, not a new
mission or priority change. The bounded repair preserves evidence, unresolved
question and confirmed history while keeping exception state, scheduling a
future cadence and allowing later cases to rotate. A later successful refresh
still follows normal genuine-question delivery. Source/tests are not an owner
outcome; natural post-deploy cadence and queue continuation remain required.
**DURABLY LOGGED - NOT YET AN OWNER OUTCOME. OWNER ACTION: NONE.**
