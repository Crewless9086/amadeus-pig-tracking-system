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

The owner should not have to ask which terminal is idle or remember its next
mission. Until automatic terminal delivery is proven, Control Tower remains
responsible for detecting the opportunity and presenting the exact prompts to
Charl immediately.

If this transaction cannot be persisted safely, Control Tower must explicitly
say the register was not updated. Conversation memory alone is not tracking.

## Current control board

Snapshot: 2026-08-13 SAST, reconciled through main `b7c0edcf`.

| Terminal | Terminal state | Existing mission and business/runtime truth | Next action |
|---|---|---|---|
| CORE | Discovery integrated; source-only slice prepared | `CMQ-20260813-03` read-only reconciliation merged in PR #888 as `c5f4c68d`. It proves canonical Supabase convergence but separate application/OOM preview and execution contracts; no runtime/provider facts or duplicate production writes were claimed. | `CONTINUE`: implement only a new side-effect-free shared preview contract plus isolated adapter-conformance tests. Existing executors, routes, UI, migrations and legacy fallbacks remain untouched. |
| HERDMASTER | HMQ-02 and HMQ-03 production-verified; terminal released | `HMQ-20260813-02` is live through PR #889 merge `e154a397`: anonymous HTML redirects to the friendly owner login and returns after authentication, while anonymous JSON remains a 403; hostile return targets fail safe and farm counts remain unchanged. `HMQ-20260813-03` remains operationally verified. | `CONTINUE — SEND NOTHING`: development terminal is released-retain. Do not manufacture another HERDMASTER task; promote the next queued mission only after its exact scope and active file ownership are reconciled. |
| ROOTLINE | Shared Telegram intake repaired; B/C remains held | PR #887 merge `e3c723aa` restored the dedicated authenticated gateway header and durable owner binding. The original `Reservoir 4/4`, `Storage tanks 3/4` observation was recovered once into Supabase and replay was silent. B/C remains held because autonomy and protected B/C confirmation lifecycle are not deployed. | `SEND_NOTHING` on the intake incident. Retain RMQ-04 pending reviewed B/C confirmation lifecycle; no owner repetition or control. |
| OOM SAKKIE | Health/loss intake slice prepared; morning clock remains deployed-owned | `HERDMASTER-NATURAL-HEALTH-LOSS-1`: Pig 002 genuine report failed before PR #887 and remains unrecorded/unanswered; authentication is now repaired but the natural health/loss capability is still inactive. `OMQ-20260813-02` remains separately waiting for the genuine clock. | `NEW_MISSION`: implement only delivery stage 1 zero-I/O natural event interpreter and complete-effect preview contract with Pig 002/Maya fixtures. No replay, message, route activation or farm write. |
| SAM | Development released; deployed acceptance pending | `SMQ-20260813-02`: bounded WhatsApp/WebWidget authority and first-event-card repair merged in PR #882 as `b36b2ca3` and is live within successor `6d7f3259`. Conversations `1533`/`2143` were untouched. Business completion needs the next genuine eligible inbound. | `SEND_NOTHING`: deployed SAM owns the next event. Use the development terminal only for read-only correlation or a reusable defect exposed by that event. |
| BEACON | Not launched | `BMQ-20260813-00`: provider/runtime and retained-worktree truth unreconciled; no posting authority inferred. | `NEW_MISSION` only when launched: read-only current-truth reconciliation. |
| CODEX UI | Launched and ready; prompt prepared | `UIQ-20260813-01`: reconcile the preserved dirty `/matings` facelift and corrected deployed read contract before continuing UI work. The original shared workspace contains uncommitted UI files and must not be reset, stashed, deleted or overwritten. | `CONTINUE`: inspect and classify the existing diff, reconcile it with current main and the approved dashboard/facelift standards, then produce a local owner-review preview. No deployment without Charl's fresh visual approval. |

## Mission queues

### CORE

- `CMQ-20260813-02A` — `parser_deployed_waiting_for_separate_authority`:
  PR #877 evidence and PR #885 opaque-ID repair are integrated; watchdog remains
  active and no additional proof window is authorized.
- `CMQ-20260813-03` — `discovery_integrated_source_slice_cleared`: PR #888 is
  merged; next work is limited to a new side-effect-free preview contract and
  isolated conformance tests with no executor, route, UI or fallback cutover.
- `CMQ-20260813-04` — queued reversible legacy-document retirement.

### HERDMASTER

- `HMQ-20260813-03` — `operationally_verified`: PR #884 is deployed; correct
  proposal/hold truth and zero-write repeated readback are proven.
- `HMQ-20260813-02` — `closed`: PR #889
  is deployed and the anonymous redirect, friendly login, successful return,
  authenticated page, JSON denial, malicious-next containment and zero farm
  mutation were all production-verified; NEXT_STEPS, source-map and changelog
  reconciliation shipped in the same merge. Development terminal released-retain.
- `HMQ-20260813-00` — integrated; waits for a natural exact-pig observation.
- `HMQ-20260813-04` — queued attributable lifecycle/genetic merit.
- `HMQ-20260813-05` — waits for a genuine completed weight batch.
- `HMQ-20260813-06` — waits for physical exposure separation.

Detailed HERDMASTER evidence remains in
`docs/06-operations/HERDMASTER_OPEN_MISSION_REGISTER_20260812.md`.

### ROOTLINE

- `RMQ-20260813-02` — `gateway_blocked`: repair HTTP 403 and prove protected
  receipt before requesting fresh owner presence.
- `RMQ-20260813-04` — `active_software_acceptance_blocked`: prior physical B/C
  commissioning remains valid and must not be repeated merely to prove that the
  valves work. The remaining defect is the canonical automation journey: it
  must distinguish an intentional multi-segment irrigation job (required when
  total runtime exceeds the controller's 3,599-second native fail-stop) from an
  accidental replay/duplicate, persist segment and cumulative-runtime truth,
  and expose one digest-bound protected preview/confirmation lifecycle before
  B/C autonomy can be enabled. No further physical B test is authorized until
  that source/runtime contract is reviewed and deployed.
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
- `HERDMASTER-NATURAL-HEALTH-LOSS-1/OOM-INTAKE-SLICE-1` —
  `prompt_prepared_zero_io`: natural illness/injury/death/loss interpreter and
  complete-effect preview contract only; Pig 002 is immutable failed-acceptance
  evidence and must not be replayed or written.

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
| 2026-08-13 | CORE `CMQ-20260813-02A` parser repair | PR #877 evidence merged as `8f8ec3b2`; PR #885 opaque mission-ID and creation-precedence repair merged/deployed as `7c22cd5f`; no Telegram proof or provider mutation occurred. | Parser development released; live proof remains unauthorized. Promote CMQ-03 read-only reconciliation. |
| 2026-08-13 | CORE `CMQ-20260813-03` discovery | PR #888 documentation at exact head `5f5aa641` passed all checks and merged as `c5f4c68d`. Application and OOM converge on Supabase events but do not share one atomic group contract; Sheets fallback authority remains. | Clear only a new pure preview-contract module and isolated tests; prohibit executor/fallback cutover. |
| 2026-08-13 | CORE Programme | PR #878 proved canonical Programme location and merged pointer/source-map correction as `29f04528`. | Released; SAM may resume existing mission. |
| 2026-08-13 | HERDMASTER `HMQ-20260813-03` | Candidate passed pre-advance gates; main advanced; no merge/deploy. | Preserve and reconcile non-destructively. |
| 2026-08-13 | HERDMASTER `HMQ-20260813-03` completion | PR #884 merged as `b7c0edcf` and production/browser readback proved Bonnie proposal wording, three exact recovery holds, five unchanged exposures/cycles and zero writes on repeated reads. | Development worktree clean released-retain; promote HMQ-02. |
| 2026-08-13 | HERDMASTER `HMQ-20260813-02` completion | PR #889 merged/deployed as `e154a397`. Production proved exact anonymous HTML login redirect and return, authenticated Breeding Attention rendering, retained API-style JSON denial, hostile-next containment and unchanged farm tables; NEXT_STEPS, source map and changelog were reconciled in the merge. | Mission closed; terminal released-retain. Reconcile HMQ-04 scope and file ownership before any new dispatch. |
| 2026-08-13 | ROOTLINE `RMQ-20260813-02` | PR #875/#876 live; provider safety eligible; card `3480` updated; zero controls. | Pending protected physical journey. |
| 2026-08-13 | ROOTLINE gateway incident | Telegram `3579` retained by n8n but relay received HTTP 403 before parsing/Supabase; presence expired; zero controls. | Repair end to end; no owner repetition. |
| 2026-08-13 | ROOTLINE `RMQ-20260813-04` water evidence | Readiness held because 11 August storage evidence was stale. Charl then sent fresh `Reservoir 4/4` and `Storage tanks 3/4`, but read-only trace found no new canonical Supabase receipt; Telegram showed zero pending/error backlog. | Treat as the same systemic intake incident. Recover durable provider receipt if possible; do not request another owner message. |
| 2026-08-13 | ROOTLINE shared Telegram intake repair | PR #887 merged as `e3c723aa`; dedicated gateway authentication and durable owner binding restored. Original reservoir/storage update recovered exactly once into Supabase with silent replay; zero controls. | Intake incident technically closed; B/C remains held on separate authority/lifecycle blockers. |
| 2026-08-13 | ROOTLINE `RMQ-20260813-04` acceptance correction | Control Tower rejected treating the next action as another generic Valve B commissioning test. Prior B/C physical commissioning is retained. Irrigation longer than the 3,599-second native fail-stop legitimately needs multiple intentional segments; this must be represented as one durable job with explicit segment identity, expected OFF/re-arm transitions and cumulative delivered runtime, while unrelated retries/replays remain no-ops. | ROOTLINE Terminal must first reconcile and repair the software contract read-only/source-first. Do not actuate B/C or ask Charl to travel until a reviewed deployed preview proves the intended job/segment boundary. |
| 2026-08-13 | OOM SAKKIE/HERDMASTER Pig 002 intake | Genuine Pig 002 not-eating report was accepted upstream but rejected before parsing under the pre-#887 identity split; no reply, preview or write exists. Gateway is repaired, but the owner-approved natural health/loss workflow remains inactive. | Preserve report as failed-acceptance evidence; begin zero-I/O interpreter/preview slice without replay or farm write. |
| 2026-08-13 | OOM SAKKIE `OMQ-20260813-02` | No 13 August production morning trigger; PR #879 later integrated one Render-owned clock and synthetic non-actuating family. | Prove provider configuration and synthetic result; genuine clock proof still pending. |
| 2026-08-13 | ROOTLINE/OOM SAKKIE morning readiness | Provider verified exactly one enabled 06:45 SAST Render scheduler; a later duplicate was suspended. No genuine daily invocation, hardware action or authority change occurred. | Run one isolated non-actuating synthetic acceptance, then await genuine clock. |
| 2026-08-13 | ROOTLINE/OOM SAKKIE synthetic acceptance | Exactly one deployed-entry invocation, one separate Supabase claim and one provider-confirmed `ROOTLINE SCHEDULE TEST` send; eight direct/concurrent/post-restart replays were silent; genuine daily lifecycle unchanged; zero farm/hardware/provider-control effects. | Synthetic acceptance complete. Send nothing until post-07:00 genuine-event audit. |
| 2026-08-13 | OOM SAKKIE duplicate feedback | The same synthetic-acceptance evidence was submitted again with no newer event or changed evidence. | No status change, no duplicate mission, no repeat test and no new prompt. |
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
