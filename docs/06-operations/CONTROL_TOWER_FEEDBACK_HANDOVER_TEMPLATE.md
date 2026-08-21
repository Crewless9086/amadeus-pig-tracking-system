# Control Tower Feedback And Continuation Template

Status: mandatory cross-system handover contract

Machine contract: `core_mission_outcome_handover_v1`. The complete human packet
below remains mandatory, but CORE accepts lifecycle evidence only from the
structured contract submitted to the canonical mission outcome-handover rail.
A short summary or claim that this template exists elsewhere is
`INVALID_HANDOVER`.

```json
{
  "contract_version": "core_mission_outcome_handover_v1",
  "handover_id": "stable append-only identity",
  "mission_id": "exact canonical mission identity",
  "reporting_actor_type": "terminal | control_tower | deployed_agent | external_verifier",
  "terminal_disposition": "stage-qualified disposition; never bare done/complete",
  "requested_lifecycle": "WORKING | REVIEW_HOLD | RELEASE_HOLD | EXTERNAL_HOLD | PROTECTED_BOUNDARY | BUSINESS_COMPLETE",
  "technical_milestones": ["source_ready", "tests_passed", "pr_open", "merged", "deployed", "health_passed"],
  "applicability": {
    "evidence_row": "required or {state:not_applicable,reason_code,reason,authority,audit_ref}"
  },
  "evidence": {
    "evidence_row": {"evidence_id": "canonical identity", "observed_at": "timezone-aware timestamp"}
  },
  "next_safe_stage": "exact automatic continuation stage",
  "hold": {"type": "EXTERNAL_HOLD or PROTECTED_BOUNDARY", "owner": "exact owner", "reason": "exact reason", "wake_condition": "observable condition", "automatic_continuation_trigger": "durable trigger"}
}
```

Required evidence rows are `operational_actor`, `genuine_trigger`,
`loaded_revision`, `canonical_readback`, `provider_result`,
`physical_or_customer_result`, `later_independent_cycle`, and
`safe_final_state`, `replay_and_concurrency_containment`,
`automatic_follow_up_or_unresolved_work_ownership`, and `owner_work_removal`.
Canonical readback and the safety, containment, follow-up/ownership rows cannot
be marked not applicable. Actor evidence must identify a non-terminal deployed
runtime. Trigger evidence must identify its provider and state
`created_by_terminal:false`. Revision evidence must carry the exact loaded
40-character SHA and `exact_match:true`. Canonical evidence must bind a receipt
to matching readback. Required provider and physical/customer evidence must
bind the originating result to the mission correlation. Safe-final-state
evidence must identify and verify the resulting safe state. Replay/concurrency
evidence must identify the enforcing control. Follow-up evidence must prove an
automatic next trigger or one exact blocker, owner and wake condition. The
later cycle must carry a durable
correlation ID and `terminal_independent:true`. Owner-work evidence must carry a
measurement ID and integer before/after manual-step counts with a strict
reduction. Every required `evidence_id` must already resolve to a mission-bound
canonical mission event whose producer identity, evidence row and immutable
payload digest match the submitted evidence;
caller-supplied labels alone are rejected. Only Control Tower, deployed-agent or independent-verifier evidence
may request `BUSINESS_COMPLETE`; a terminal never can.

Controlling references:

- `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md`
- `docs/09-vault-brain/00-governance/CONTROL_TOWER_ASSESSMENT_AND_DISPATCH_PROTOCOL.md`

The terminal must read both controlling files completely before returning this
packet. Control Tower must execute the protocol and append its separate Check
Receipt; merely receiving this template is not an assessment.

Use this template for CORE, OOM SAKKIE, ROOTLINE, HERDMASTER, SAM, BEACON,
CODEX UI and every future specialist. Do not omit sections because a terminal
performed only source work. Use `Unknown`, `none` or `not applicable` rather
than inferring evidence.

## Governance preflight

- Worktree, branch and HEAD:
- Upstream and ahead/behind current authoritative main:
- Mission Standard tracked blob, filesystem SHA-256, physical lines and read completely:
- Control Tower Protocol tracked blob, filesystem SHA-256, physical lines and read completely:
- Canonical Runtime Programme tracked blob, filesystem SHA-256, physical lines and read completely:
- Authoritative-main comparison:
- Worktree status and preservation classification:
- Feedback evidence observation time:

## Mission identity and owner outcome

- Existing mission ID:
- Owner-visible outcome:
- Explicit non-outcomes:
- Lifecycle state:
- Remaining acceptance journey:
- Strategic class: `OPERATING_SPINE` / `CURRENT_BLOCKER` / `EXPANSION`:
- Recovery-mode WIP slot: 1 / 2 / 3 / frozen / not applicable:
- Exact recurring owner action this mission removes:
- Current owner manual steps and target manual steps:
- Terminal-independent proof that closes the workload reduction:
- Why this is deployed-agent enablement rather than terminal substitution:

## Terminal state

- Visible development terminal: active / idle / released / stopped / Unknown
- Last instruction actually delivered:
- Delivery proof: prepared / delivered / acknowledged / started / progress observed
- Worktree, branch and current action:
- Last terminal-invoked production/test cycle:
- What stops when this terminal closes:
- Fresh progress evidence since the last feedback (commit/diff/artifact/heartbeat):
- Why any open process is active work rather than an idle shell:

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

## Agent execution ownership

- Operational actor (exact deployed agent/runtime):
- Genuine trigger and provider/canonical identity:
- Owner-facing or customer-facing channel:
- Terminal-permitted actions:
- Terminal-forbidden substitutions:
- Agent-origin proof:
- Terminal-created output present: no / classify exact test or recovery evidence
- What would have happened if the development terminal were closed:

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
- Standing authority ID, version, scope and limits:
- Current action inside standing authority: yes / no / Unknown
- Owner interactions requested in this complete journey:
- Irreducible reason for each owner interaction:
- Governed evidence source used instead of owner observation:
- Owner-burden systemic defect present: no / exact shared journey defect
- Owner workload delta achieved this turn: none / exact manual step removed
- New recurring owner labour introduced: none / exact temporary labour and removal trigger
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
- Serialized release lane owner, process/ledger proof and release trigger:
- Durable mission-register update proposed:

## Mandatory forward mission pipeline

- Intended complete specialist role:
- Capabilities already operationally proven through the deployed agent:
- Current outcome-bound mission:
- Next mission after the current mission:
- Later sequenced missions required for full scope:
- Exact dependencies/collision boundaries:
- Automatic promotion trigger:
- Latest owner observation or priority change:
- Register update evidence, or explicit reason persistence was unsafe:

The next-mission field is mandatory even when the current mission is active or
event-waiting. It records future sequencing; it is not permission to interrupt
active work. When the current development work releases, Control Tower promotes
the highest-value eligible non-colliding mission without waiting for Charl to
ask. Terminals build and prove capabilities; deployed agents operate them.

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

It must also say:

> Use durable standing authority for every equivalent routine cycle. Do not ask
> Charl to confirm a fact available from fresh canonical, provider or governed
> sensor evidence, and do not turn a missing trigger, worker, adapter or evidence
> collector into owner labour. Classify any avoidable or repeated approval as an
> owner-burden systemic defect and repair the reusable journey before requesting
> another owner action.

For any operational outcome it must additionally say:

> The deployed named agent is the operational actor. The terminal may implement,
> deploy and observe only; it must not generate the owner-facing result, send the
> provider message, confirm the action, perform the canonical business write or
> operate hardware on the agent's behalf. Classify terminal-created output only
> as terminal-invoked test evidence and require a fresh genuine trigger through
> the real owner/provider channel before Business completion.
