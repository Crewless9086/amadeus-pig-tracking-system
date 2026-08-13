# Control Tower Mission Register

Status: Active owner-facing dispatch authority

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

If this transaction cannot be persisted safely, Control Tower must explicitly
say the register was not updated. Conversation memory alone is not tracking.

## Current control board

Snapshot: 2026-08-13 SAST, reconciled through main `b7c0edcf`.

| Terminal | Terminal state | Existing mission and business/runtime truth | Next action |
|---|---|---|---|
| CORE | Released between prompts | `CMQ-20260813-02A`: watchdog proof rolled back; watchdog active; mission-ID truncation blocks another proof. PR #877 evidence remains to integrate. PR #878 corrected Programme discovery. | `CONTINUE`: integrate evidence and repair opaque mission-ID handling. No new watchdog window without separate authority. |
| HERDMASTER | Preserved candidate | `HMQ-20260813-03`: Breeding Attention correction is neither merged nor deployed. Candidate remains at `C:\tmp\herdmaster-breeding-eligibility-truth-20260813`; deployed HERDMASTER unchanged. | `CONTINUE`: reconcile non-destructively against current main, rerun gates and review. |
| ROOTLINE | Synthetic scheduler acceptance complete; Mixer gateway incident remains separate | `RMQ-20260813-04`: one deployed synthetic invocation used the real ROOTLINE planning path, one separate Supabase claim and one Telegram TEST send; eight direct/concurrent/post-restart replays were silent with zero farm/hardware/provider-control effects. `RMQ-20260813-02` Mixer still requires gateway repair before fresh owner presence. | `SEND_NOTHING` for morning work; deployed ROOTLINE supplies tomorrow's genuine decision. Continue Mixer gateway repair only as its separate incident. |
| OOM SAKKIE | Synthetic path proven; genuine morning clock event pending | `OMQ-20260813-02`: provider-verified Render scheduler is enabled for 06:45 SAST; synthetic end-to-end delivery and durable replay passed. Business completion still requires the natural 14 August provider-clock outcome. | `SEND_NOTHING`: after 07:00 SAST on 14 August, the OOM SAKKIE development terminal performs read-only genuine-event verification. |
| SAM | Development released; deployed acceptance pending | `SMQ-20260813-02`: bounded WhatsApp/WebWidget authority and first-event-card repair merged in PR #882 as `b36b2ca3` and is live within successor `6d7f3259`. Conversations `1533`/`2143` were untouched. Business completion needs the next genuine eligible inbound. | `SEND_NOTHING`: deployed SAM owns the next event. Use the development terminal only for read-only correlation or a reusable defect exposed by that event. |
| BEACON | Not launched | `BMQ-20260813-00`: provider/runtime and retained-worktree truth unreconciled; no posting authority inferred. | `NEW_MISSION` only when launched: read-only current-truth reconciliation. |
| CODEX UI | Launched and ready; prompt prepared | `UIQ-20260813-01`: reconcile the preserved dirty `/matings` facelift and corrected deployed read contract before continuing UI work. The original shared workspace contains uncommitted UI files and must not be reset, stashed, deleted or overwritten. | `CONTINUE`: inspect and classify the existing diff, reconcile it with current main and the approved dashboard/facelift standards, then produce a local owner-review preview. No deployment without Charl's fresh visual approval. |

## Mission queues

### CORE

- `CMQ-20260813-02A` — `systemic_defect_repair_required`: integrate PR #877
  and repair full mission-ID parsing before another authorized proof.
- `CMQ-20260813-03` — queued grouped weights/movements canonical cutover.
- `CMQ-20260813-04` — queued reversible legacy-document retirement.

### HERDMASTER

- `HMQ-20260813-03` — `preserved_requires_reconciliation`: low-BCS holds,
  supersession truth and plan-only wording without farm writes.
- `HMQ-20260813-02` — queued protected-page owner-login redirect.
- `HMQ-20260813-00` — integrated; waits for a natural exact-pig observation.
- `HMQ-20260813-04` — queued attributable lifecycle/genetic merit.
- `HMQ-20260813-05` — waits for a genuine completed weight batch.
- `HMQ-20260813-06` — waits for physical exposure separation.

Detailed HERDMASTER evidence remains in
`docs/06-operations/HERDMASTER_OPEN_MISSION_REGISTER_20260812.md`.

### ROOTLINE

- `RMQ-20260813-02` — `gateway_blocked`: repair HTTP 403 and prove protected
  receipt before requesting fresh owner presence.
- `RMQ-20260813-04` — `ready_waiting_for_genuine_clock_event`: one enabled
  provider scheduler is proven; the 14 August result must still correlate
  ROOTLINE decision, durable claim, Telegram outcome and silent replay.
- `RMQ-20260813-03` — queued Injection commissioning after Mixer and preflow.
- `RMQ-20260813-05` — queued water-credit lifecycle after B/C acceptance.
- `RMQ-20260813-06` — hardware-blocked Borehole 1 independent fail-OFF proof.

### OOM SAKKIE

- `OMQ-20260813-02` — `ready_waiting_for_genuine_clock_event`: post-07:00
  read-only proof must correlate the Render invocation, one date-stable claim,
  one Telegram plan/hold or recorded failure, and zero replay sends.
- `OMQ-20260813-03` — waits for next genuine contextual reply.
- `OMQ-20260813-04` — waits for next genuine specialist request.
- `OMQ-20260813-05` — queued browser/Telegram/voice canonical parity.

### SAM

- `SMQ-20260813-02` — `deployed_waiting_for_genuine_acceptance` using
  conversations `1533` and `2143` only as regression evidence; never replay
  them. The next eligible genuine inbound must produce one provider-confirmed
  useful reply or expose the next reusable defect.
- `SMQ-20260813-01` — queued retained-context Front Door routing.
- `SMQ-20260813-03` — waits for controlled pilot prerequisites.
- `SMQ-20260813-04` — queued Meat shared-context reconciliation.
- `SMQ-20260813-05` — queued protected sales/payment visibility.
- `SMQ-20260813-06` — blocked by CORE Phase 0 replacement proof.

### BEACON

- `BMQ-20260813-00` — queued read-only current-truth reconciliation.
- `BMQ-20260813-01` — blocked existing-publication closeout.
- `BMQ-20260813-02` — owner direction only for private media intake.
- `BMQ-20260813-03` — queued library/public-use separation.
- `BMQ-20260813-04` — queued evidence-backed proposal.
- `BMQ-20260813-05` — queued protected publication/performance loop.

### CODEX UI

- `UIQ-20260813-01` — `prompt_prepared`: preserve and reconcile the dirty
  `/matings` facelift, authoritative names and IN/UIT/farrowing-window contract.
- `UIQ-20260813-02` — queued conditional hiding/simplification of `Beskermde
  Oorgang` when there is no actionable protected transition.
- All new facelift work remains queued until the active UI mission is released;
  no two terminals may edit the same UI files concurrently.

## Feedback ledger

Append a row for every terminal report. Never rewrite history to make a later
result appear known earlier.

| Date | Terminal / mission | Evidence and decision | Closeout / next action |
|---|---|---|---|
| 2026-08-13 | CORE `CMQ-20260813-02A` | Reversible watchdog window rolled back; synthetic receipt/reply passed; mission pickup failed through ID truncation. | Released; repair parser before another window. |
| 2026-08-13 | CORE Programme | PR #878 proved canonical Programme location and merged pointer/source-map correction as `29f04528`. | Released; SAM may resume existing mission. |
| 2026-08-13 | HERDMASTER `HMQ-20260813-03` | Candidate passed pre-advance gates; main advanced; no merge/deploy. | Preserve and reconcile non-destructively. |
| 2026-08-13 | ROOTLINE `RMQ-20260813-02` | PR #875/#876 live; provider safety eligible; card `3480` updated; zero controls. | Pending protected physical journey. |
| 2026-08-13 | ROOTLINE gateway incident | Telegram `3579` retained by n8n but relay received HTTP 403 before parsing/Supabase; presence expired; zero controls. | Repair end to end; no owner repetition. |
| 2026-08-13 | OOM SAKKIE `OMQ-20260813-02` | No 13 August production morning trigger; PR #879 later integrated one Render-owned clock and synthetic non-actuating family. | Prove provider configuration and synthetic result; genuine clock proof still pending. |
| 2026-08-13 | ROOTLINE/OOM SAKKIE morning readiness | Provider verified exactly one enabled 06:45 SAST Render scheduler; a later duplicate was suspended. No genuine daily invocation, hardware action or authority change occurred. | Run one isolated non-actuating synthetic acceptance, then await genuine clock. |
| 2026-08-13 | ROOTLINE/OOM SAKKIE synthetic acceptance | Exactly one deployed-entry invocation, one separate Supabase claim and one provider-confirmed `ROOTLINE SCHEDULE TEST` send; eight direct/concurrent/post-restart replays were silent; genuine daily lifecycle unchanged; zero farm/hardware/provider-control effects. | Synthetic acceptance complete. Send nothing until post-07:00 genuine-event audit. |
| 2026-08-13 | SAM `SMQ-20260813-02` | Conversations `1533`/`2143` produced safe unsent replies and non-actionable cards; defect traced. | Continue bounded correction; no historical sends. |
| 2026-08-13 | SAM `SMQ-20260813-02` integration | PR #882 merged as `b36b2ca3`; successor `6d7f3259` is live. WhatsApp timestamp binding, WebWidget authority and safe first-event routing are corrected; historical conversations were untouched. | Development released; send nothing and observe next genuine inbound. |
| 2026-08-13 | CODEX UI `UIQ-20260813-01` | Dedicated UI terminal launched; preserved dirty `/matings` files exist in the original workspace; prompt prepared but not yet acknowledged. | Deliver one reconciliation/local-preview mission; no deployment yet. |

## New owner findings

Before dispatch, record the mission ID, deployed owner, development terminal,
priority, dependency, dispatch truth, preserved acceptance outcome and whether
Charl should send anything now. A finding remains until owner-visible completion
or explicit containment.

## Delivery limitation

Automatic prompt delivery to every visible terminal is not proven. Charl must
paste a prompt unless target-specific delivery and acknowledgement are evidenced.
The target is the durable CORE queue/runner. Until then, queued, delivered,
started and deployed-runtime-active remain distinct states.
