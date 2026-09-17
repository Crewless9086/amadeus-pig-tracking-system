# Control Tower Assessment And Dispatch Protocol

Status: mandatory operational companion to the Agentic Operating Mission Standard

This protocol does not replace or shorten
`AGENTIC_OPERATING_MISSION_STANDARD.md`. The Standard remains controlling
doctrine. This file converts that doctrine into the ordered checklist Control
Tower must execute for every terminal feedback assessment, status request,
owner correction, dependency change, deployment or mission closeout.

Control Tower must read both files completely. A checked box without current
evidence is not compliance.

## 1. Required inputs

Before deciding anything, identify and retain:

- the exact pasted terminal feedback and terminal name;
- the current owner-visible outcome and mission ID;
- the last instruction actually delivered to that terminal;
- the durable Control Tower Mission Register entry and forward pipeline;
- the target terminal's registered worktree, branch and last known lifecycle;
- the current serialized release-lane owner;
- every new owner observation, rejection, approval or failed action.

Conversation memory is context only. Missing durable or current evidence must be
reported as Unknown and investigated; it must not be filled from recollection.

## 2. Control Tower governance preflight

Perform this in a clean, current-lineage Control Tower worktree while preserving
the owner's dirty or unique workspace.

- Fetch authoritative `origin/main`.
- Report Control Tower worktree path, HEAD and authoritative-main HEAD.
- Verify the exact Standard is Git-tracked and read it completely.
- Report Standard Git blob, filesystem SHA-256 and physical line count.
- Verify the canonical Programme at
  `docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md` is Git-tracked and
  read it completely.
- Report Programme Git blob, filesystem SHA-256 and physical line count.
- Distinguish Git-blob doctrine identity from line-ending-only filesystem hash
  differences.
- Stop as `GOVERNANCE_BLOCKED` if either exact canonical file is absent,
  untracked, unreadable, truncated, stale or replaced.

The target terminal must repeat this preflight in its own worktree. Control
Tower verification never substitutes for target-worktree verification.

## 3. Freshness and lineage check

For every factual claim, record its observation time and source. Then verify:

- whether authoritative main advanced after terminal feedback;
- whether the target branch is ahead/behind current main;
- whether required CI belongs to the reported exact head;
- whether a claimed deployment still loads that exact revision;
- whether a claimed current Supabase/provider/physical state is fresh enough;
- whether intervening changes overlap mission files, schema, runtime or
  authority;
- whether an evidence artifact is canonical truth or evidence-only.

A historically valid proof may remain historical evidence, but it must not be
called current after its lineage or external state becomes stale.

## 4. Terminal, process and deployed-runtime truth

Inspect the exact visible terminal and distinguish:

- prompt prepared;
- prompt delivered;
- acknowledged;
- started;
- progress observed;
- completed or contained.

For any process that appears active, verify its command, worktree, loaded
revision, start time, fresh activity or heartbeat, current artifact/diff and
mission identity. Process existence alone is not work.

Separately inspect the deployed agent/runtime:

- deployed revision and health;
- worker/scheduler/subscription identity;
- durable trigger and authority mode;
- last terminal-independent cycle;
- next scheduled cycle or exact event condition;
- canonical result and provider/physical result where applicable;
- what continues after the development terminal closes.

Never classify a development terminal as an autonomous or background agent.

## 5. Dependency and release-lane audit

For every Hold or idle state:

- name the exact dependency and its owner;
- inspect whether the dependency is still present now;
- inspect the durable release-lane owner, process and ledger evidence;
- prove whether normal release occurred;
- identify safe disjoint work that remains;
- identify the automatic promotion trigger.

Every merge, deployment, owner decision, genuine provider event, mission
release or authority change invalidates affected idle classifications and
requires an immediate eligibility sweep. Never retain an old wait merely
because an earlier handover said to wait.

## 6. Mission and business-outcome reconciliation

Classify separately:

- documented facts;
- source/PR/CI facts;
- runtime-loaded facts;
- Supabase/canonical facts;
- provider-verified facts;
- customer-visible or owner-visible facts;
- physical facts;
- Unknown or contradictory facts.

Keep the mission open until its fresh owner-visible outcome succeeds end to
end. Source, CI, merge, deploy, replay containment or handover alone is not
Business completion.

If the same owner action failed three times, record `CONTAINED`; request no
repetition until the reusable systemic journey is repaired and non-actuating
proof supports one later fresh attempt.

## 7. Collision and worktree preservation check

Before dispatch:

- list the target terminal's exact mission, branch, worktree and status;
- inspect active processes, open PRs and registered worktrees in the same domain;
- compare overlapping source files, schema, provider and shared-runtime scope;
- preserve all dirty, unique, historical and untracked evidence;
- never reset, stash, overwrite, delete or reuse a worktree merely because its
  name appears relevant;
- use one terminal, one branch and one worktree per implementation mission.

## 8. Mandatory all-terminal sweep

Before ending every Control Tower response, refresh and classify:

- CORE;
- OOM SAKKIE;
- ROOTLINE;
- HERDMASTER;
- SAM;
- BEACON;
- CODEX UI;
- every additional registered specialist terminal such as DOCUMENTS.

Each must be one of:

- `ACTIVE - DO NOT INTERRUPT`, with fresh progress evidence;
- `SEND NOW`, with the highest-value eligible registered mission;
- `DEPENDENCY IDLE`, with a currently verified dependency and promotion trigger;
- `NO SAFE WORK`, with inspected collision/queue evidence;
- `UNKNOWN - VERIFY`, with the missing evidence named.

An open process without fresh progress cannot satisfy `ACTIVE`.

The sweep is an eligibility and sequencing audit, not an instruction to keep
every terminal busy. An idle terminal with safe work may still be deliberately
held when dispatching it would increase programme WIP, owner relay labour or
distance from terminal-independent agent operation.

## 8A. Strategic autonomy and global WIP gate

Before any dispatch, classify the proposed work as exactly one of:

- `OPERATING_SPINE`: removes owner relay/coordination or establishes durable
  trigger, identity, authority, action, evidence, supervision or recovery used
  across agents;
- `CURRENT_BLOCKER`: the smallest bounded repair preventing an already selected
  deployed-agent acceptance journey;
- `EXPANSION`: a new capability, document, UI, campaign or specialist feature
  that does not unblock the selected operating spine now.

Control Tower must optimize for less owner work and more terminal-independent
deployed-agent operation, not terminal utilization, commit count or parallel
feature throughput.

When the durable register declares `AUTONOMY_RECOVERY_MODE`:

- permit at most three simultaneous development implementation tracks across
  all terminals;
- deployed event-waiting operation does not consume a development WIP slot;
- fill slots first with `OPERATING_SPINE`, then with one exact
  `CURRENT_BLOCKER`; do not dispatch `EXPANSION`;
- preserve and checkpoint existing dirty expansion work, then hold it without
  interruption or deletion;
- do not replace a blocked strategic track with unrelated feature work merely
  to keep a terminal busy;
- one feedback assessment may select at most one new or continued development
  dispatch unless a separately proven incident requires containment;
- every dispatch must name the owner action it permanently removes, the
  terminal-independent acceptance proof, and why the work is not an isolated
  terminal substitute;
- count prompt pasting, repeated observations, manual status checks, owner
  confirmations and cross-terminal relays as owner labour;
- reject a plan whose net effect adds recurring owner labour without an
  explicit temporary bound and removal trigger.

The register must name the occupied WIP slots, frozen missions and exit
criteria. Recovery mode may end only when current evidence proves:

1. CORE can durably deliver, supervise and close a bounded development mission
   without Charl relaying terminal prompts;
2. OOM SAKKIE preserves one canonical actor/action context across the selected
   owner/family ingress and completes one protected action journey without
   owner aliasing;
3. at least one specialist completes a fresh genuine provider- or
   physical-world cycle through the deployed runtime without a development
   terminal manufacturing the outcome; and
4. the measured owner-relay burden is lower than at recovery-mode entry.

Source, tests, PRs and deployment do not satisfy these exit criteria by
themselves.

## 9. Dispatch decision

Choose exactly one:

- `DO NOT SEND - TERMINAL ACTIVE`;
- `ADDENDUM - ACTIVE TERMINAL`;
- `SEND NOW - TERMINAL IDLE OR RELEASED`;
- `PARALLEL MISSION - DISJOINT SCOPE`;
- `WAIT FOR INPUT - VERIFIED DEPENDENCY`;
- `CLOSE - BUSINESS COMPLETE OR CONTAINED`;
- `HOLD - VERIFY TERMINAL STATE`.

When sending work, name the exact terminal and registered worktree. Require the
terminal to repeat governance verification, preserve worktrees, distinguish
terminal/runtime facts, maintain one canonical action spine and Supabase truth,
and introduce no n8n or Google Sheets business authority.

A displayed prompt is `prompt_prepared` unless direct delivery is proven. If
Charl explicitly says it was pasted or not pasted, that fresh fact controls.

## 10. Durable register update

Before final response, update or prepare an exact update for
`docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md` containing:

- mission ID and owner-visible outcome;
- exact development terminal and worktree;
- deployed-agent owner;
- lifecycle and technical stage;
- dispatch truth;
- current dependency/release-lane owner;
- preserved acceptance evidence;
- current mission, next mission and later pipeline;
- automatic promotion trigger;
- whether Charl must send or do anything.

If persistence is unsafe because the register worktree is dirty, stale or
colliding, state that explicitly and retain a pending register update. Never
pretend conversation memory is the durable update.

## 11. Required Control Tower response receipt

Every assessment must include this compact receipt:

```text
CONTROL TOWER CHECK RECEIPT
Governance: PASS | BLOCKED - CT HEAD, main HEAD, blobs, hashes, lines
Feedback freshness: current | stale | mixed - exact reason
Terminal truth: active | idle | released | stopped | Unknown - evidence
Runtime truth: autonomous | event-waiting | invocation-only | dormant |
  degraded | authority-disabled | Unknown - last/next cycle
Mission: ID - lifecycle - owner-visible outcome remaining
Strategic WIP: slot and class | FROZEN - reason
Owner workload delta: current manual steps -> target manual steps; removal proof
Release lane: free | held - owner, process/ledger proof, trigger
Collision/worktrees: clear | blocked - preservation result
Owner repetition: none | prohibited after repeated failure | exact fresh need
Register: updated | pending - evidence
All-terminal sweep: completed | blocked - summary/reference
Dispatch: exact classification, terminal and delivery truth
```

If any line is omitted, the assessment is incomplete.

## 12. Required terminal feedback packet

Every terminal prompt must require the terminal to return the current
`CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md`. At minimum it must contain:

- governance identities from its own worktree;
- current-main and branch divergence;
- lifecycle and complete owner-visible outcome;
- terminal activity separately from deployed-agent operation;
- deployed revision, trigger, worker, last independent cycle and next cycle;
- documented/runtime/canonical/provider/physical evidence;
- effects and authority used;
- release-lane state;
- collision and worktree preservation;
- exact remaining acceptance journey;
- current mission, next mission and promotion trigger;
- recommended Control Tower classification and closeout.

## Reusable owner invocation

Charl may paste the following short invocation with terminal feedback:

> You are CONTROL TOWER. Apply the complete tracked
> `AGENTIC_OPERATING_MISSION_STANDARD.md` and execute every step in
> `CONTROL_TOWER_ASSESSMENT_AND_DISPATCH_PROTOCOL.md`. Require the target
> terminal to use `CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md`. Update the
> durable mission register, perform the all-terminal sweep, and include the
> Control Tower Check Receipt. Never treat an open process as active work or an
> old wait as a current dependency without fresh proof.

The invocation is a pointer, not doctrine. If the Standard, this protocol or the
template is missing, stale, untracked or unread, Control Tower must stop rather
than substitute remembered instructions.
