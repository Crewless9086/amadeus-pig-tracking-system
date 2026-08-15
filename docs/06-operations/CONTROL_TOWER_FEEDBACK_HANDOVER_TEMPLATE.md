# Control Tower Feedback And Continuation Template

Status: mandatory cross-system handover contract

Use this template for CORE, OOM SAKKIE, ROOTLINE, HERDMASTER, SAM, BEACON,
CODEX UI and every future specialist. Do not omit sections because a terminal
performed only source work. Use `Unknown`, `none` or `not applicable` rather
than inferring evidence.

## Governance preflight

- Worktree, branch and HEAD:
- Mission Standard tracked blob, filesystem SHA-256, physical lines and read completely:
- Canonical Runtime Programme tracked blob, filesystem SHA-256, physical lines and read completely:
- Authoritative-main comparison:
- Worktree status and preservation classification:

## Mission identity and owner outcome

- Existing mission ID:
- Owner-visible outcome:
- Explicit non-outcomes:
- Lifecycle state:
- Remaining acceptance journey:

## Terminal state

- Visible development terminal: active / idle / released / stopped / Unknown
- Last instruction actually delivered:
- Delivery proof: prepared / delivered / acknowledged / started / progress observed
- Worktree, branch and current action:
- Last terminal-invoked production/test cycle:
- What stops when this terminal closes:

## Deployed agent operational reality

- Exact deployed revision:
- Web/API runtime and health:
- Background worker identity:
- Autonomous trigger type and provider identity:
- Trigger enabled:
- Fresh heartbeat:
- Supervisor/restart state:
- Last independently triggered cycle and correlation ID:
- Last canonical result:
- Next scheduled cycle or exact triggering condition:
- Production authority mode:
- Proof the terminal did not create or keep alive the independent cycle:
- Honest classification: autonomous / event-waiting / invocation-only /
  deployed-dormant / scheduler-degraded / authority-disabled / Unknown

HTTP health, deployed source, CI, a route, a terminal-created card, a manual
script or a synthetic canary cannot by itself establish autonomous operation.

## Evidence classification

- Documented facts:
- Runtime-loaded facts:
- Supabase/canonical facts:
- Provider-verified facts:
- Physical or customer-visible facts:
- Unknown or contradictory facts:

## Fresh execution epoch

- Historical contained identities sealed and non-replayable:
- Reusable defect repaired:
- Fresh current-world evidence source:
- New canonical execution identity:
- Why this is not a replay or reconstruction of an old attempt:
- Terminal-independent subsequent-cycle proof:

## Effects and authority

- Database/farm/customer/provider/hardware changes:
- n8n or Google Sheets authority added: no / explain violation
- Protected authority used:
- Replay and concurrency result:

## Closeout and next action

- Owner-facing dispatch banner: `DO NOT SEND — TERMINAL ACTIVE` /
  `SEND NOW — TERMINAL IDLE OR RELEASED` / `HOLD — VERIFY TERMINAL STATE`
- Business result, or `NO BUSINESS OUTCOME`:
- Exact blocker and owner:
- Safe work remaining:
- Terminal/worktree closeout:
- Control Tower classification: SEND_NOTHING / ADDENDUM / CONTINUE /
  NEW_MISSION / WAIT_FOR_INPUT / CLOSE
- Exact next terminal:
- Expected owner-visible result:

## Mandatory all-terminal closure gate

Before Control Tower may end its response, list CORE, OOM SAKKIE, ROOTLINE,
HERDMASTER, SAM, BEACON and CODEX UI with a fresh terminal state. Every
`idle` or `released` terminal must have exactly one of:

- `SEND NOW` with its highest-priority eligible existing mission;
- `DEPENDENCY IDLE` with the exact mission/event/authority dependency and the
  trigger that makes it eligible; or
- `NO SAFE WORK` with the inspected queue evidence.

Silently leaving an eligible terminal idle is a failed Control Tower
transaction. Completing the named terminal assessment does not waive this
gate. Prepared prompts must still be distinguished from delivered and started
work, and no active terminal may be interrupted merely to maximize utilization.

## Mandatory owner-facing prompt rule

The dispatch banner controls whether Charl receives prompt text:

- `DO NOT SEND — TERMINAL ACTIVE`: give no sendable continuation prompt. Name
  the existing mission and retain any new fact for reconciliation at the next
  safe feedback boundary. Do not invite Charl to interrupt or resend.
- `SEND NOW — TERMINAL IDLE OR RELEASED`: provide one self-contained prompt,
  the exact terminal and worktree, and state plainly that Charl should paste it
  now unless direct delivery is proven.
- `HOLD — VERIFY TERMINAL STATE`: give no sendable prompt until fresh evidence
  resolves whether the terminal is active, idle, released or stopped.

An assessment format that requests an exact continuation prompt does not
override this rule. When the correct terminal is already active, the exact
continuation field must contain only `DO NOT SEND — TERMINAL ACTIVE` plus the
current mission identity; it must not include prompt-shaped text that Charl
could reasonably paste. Conversation memory is context, never the durable
dispatch ledger or authority.

## Mandatory continuation-prompt clause

Every continuation prompt for an intended autonomous agent must say:

> Do not stop at source, tests, PR, merge, deployment, health, a manually
> invoked canary or containment. Prove the deployed agent's autonomous trigger,
> worker identity, heartbeat, durable independent cycle, next cycle and
> terminal-independent continuity. Retire contained historical attempts as
> immutable evidence and use a fresh current execution identity after repair.
> Keep one canonical action spine, Supabase truth and no new n8n or Google
> Sheets business authority.
