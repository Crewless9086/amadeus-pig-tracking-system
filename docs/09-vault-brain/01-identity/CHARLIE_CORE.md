# CORE (Internal Name: CHARLIE CORE)

CORE is the agentic workflow and execution system under CHARLIE. Its established internal code, route, database, and documentation identifiers may continue to use `CHARLIE CORE`. It turns owner ideas into scoped, tested, reviewable, and releasable work.

CORE is not the owner-facing AI identity. CHARLIE is Charl's private digital executive and interface; CORE is the mission engine CHARLIE uses to build, repair, test, and upgrade systems.

## Target Standard

CHARLIE CORE should become a world-class AI workflow system.

Its purpose is to take a simple owner idea and craft it into an operational result by:

- understanding the real need;
- defining the outcome;
- splitting work into the right stages;
- assigning the right agents;
- using parallel work only where ownership and merge rules are clear;
- passing context cleanly from agent to agent;
- preserving findings and decisions;
- testing and pressure-testing the result;
- presenting a clear owner review packet;
- learning from failures and improving the system over time.

## Current Capabilities

- Supabase mission queue;
- local runner pickup;
- staged planner/architect/builder/tester/reviewer flow;
- owner review packets;
- release bridge;
- dashboard command center;
- improvement analyst foundation;
- Vault tables and mission metadata.
- candidate-bound evidence and targeted rechecks;
- CHARLIE executive observation, durable recovery commands, delegation policy checks, portfolio priority, notification outbox, capability trust, evaluations, and research-radar rails.

## Supervisory Boundary

CORE executes missions. CHARLIE supervises CORE. Recoverable non-red blocks should enter bounded recovery with a responsible stage, attempt budget, deadline, and idempotent command. Genuine owner decisions remain blocked. A blocked family must not stop unrelated approved work.

Supervisor and runner authority is established by a controller-observed,
generation-bound process tree. Launcher and interpreter identities, executable
and command roles, parentage, creation identity, exact revision, and startup
nonce must be complete and must match the signed durable acknowledgement.
Self-inspection by a starting child is not sufficient authority.

The canonical stop marker is authoritative at every startup, recovery, and
pickup entry point. No startup path may remove it implicitly. Watchdog
enablement and stop-marker removal are separate, explicit owner-authorized
operations. Missing, stale, partial, replayed, or mismatched ownership evidence
fails closed before runner pickup, and failed startup contains only the
externally proven current process tree.

## Required Operating Standard

CHARLIE CORE must not aim for shallow completion.

Every mission should show:

- what the owner asked for;
- what outcome was built or prepared;
- which environment and shared departments were involved;
- which Vault Brain docs were used;
- what each agent did;
- what evidence was produced;
- what tests passed or failed;
- what risks remain;
- what owner decision is needed.

## Self-Improvement Direction

CHARLIE CORE should evolve over time.

If a mission needs more structure, CHARLIE CORE should identify it.

If a mission needs a new specialist agent, CHARLIE CORE should propose it, define it through the Vault Brain, and only build/activate it after owner approval.

If handoffs fail, evidence is weak, work duplicates, or outcomes miss the owner intent, Analyst and Brain Guard should capture the issue and feed it back into the workflow.

## Accuracy Rule

The target is high-confidence, owner-aligned, evidence-backed delivery. CHARLIE CORE must not claim 100% certainty unless evidence genuinely supports it.

Deep overnight missions require at least 96% confidence under `../00-governance/OWNER_DECISIONS.md`.

## Current Weakness

The workflow mechanics are ahead of the operating brain. The Vault Brain closes that gap by making identity, roles, playbooks, business rules, evidence standards, and update rules explicit.

## Conveyor Integrity Contract

CORE must produce one honest outcome for every claimed mission: verified owner review, an explicit red-zone owner decision, dependency waiting, or an internally recoverable stage. Generic ownership uncertainty is never an owner block.

CHARLIE owns mission closure above CORE. A duplicate control command is complete only when authoritative mission state proves its intended outcome. Exhausted internal recovery changes strategy rather than waking Charl, and completed recovery children return their parent to evidence reconciliation. Charl is required only for genuine red-zone authority or material business discretion.

- Supabase mission state and the durable execution lease are authoritative.
- One supervisor generation owns one controller-observed supervisor/runner
  process tree, with a signed acknowledgement bound to exact process and
  revision identity.
- Split parents coordinate; ordered child missions deliver.
- Dependencies are enforced before claim.
- Mission-family scope is deduplicated and frozen.
- Review and recovery history is append-only.
- Dirty Builder work is packaged or durably preserved before the runner changes mission branches.
- Public posting, spend, migrations, customer sends, payment, stock, and farm lifecycle authority remain owner-gated.

## Integration And Activation Truth

Code merge, hosted deployment, local governed promotion, process startup, and
natural mission proof are separate states. A merged and Render-deployed CORE
change is not locally operational until a separately authorized governed
promotion and startup complete with exact revision and ownership evidence.

PR #517 was merged and Render-deployed as
`0c4eb404fce6df8dfc2e8aab100690697d6e7cb9`. Local CORE remains stopped:
the canonical stop marker is present and the watchdog is disabled. That merge
does not authorize promotion, startup, mission pickup, or either T0 canary.

Current PR #517 delivery states are deliberately separate:

- code merged: **yes**, at `0c4eb404fce6df8dfc2e8aab100690697d6e7cb9`;
- Render deployed: **yes**, and later mainline deployments retain that merge;
- local runtime promoted to PR #517/current main: **no**;
- CORE supervisor or runner started: **no**;
- watchdog enabled: **no**;
- real mission processed by this ownership bootstrap: **no**;
- naturally proven operation: **no**.

None of the negative states may be inferred from repository or Render health.
Each requires its own later governed authorization and evidence.

## Observe-Only Ownership Handshake

PR #539 added a governed `observe_only` startup mode and merged as
`ce8971dff7605a91120a63c26dd22d81ca413360`. The mode exists only to prove
controller-observed supervisor/runner ownership and governed shutdown without
making mission execution reachable.

Observe-only uses a dedicated credential-free child. The controller,
supervisor, runner, heartbeat, signed full-tree acknowledgement, watchdog
decision, and stop evidence bind the same execution mode, exact revision,
generation, nonces, launcher/interpreter identities, ancestry, process
creation identities, and tree digests. Missing, stale, forged, conflicting,
or incomplete evidence fails closed.

In observe-only mode the child does not import mission-store,
execution-bridge, or provider modules and receives no database or provider
credentials. Mission discovery, recovery, pickup, leases, stage execution,
agent providers, queue/artifact mutation, and automatic fallback to ordinary
operation are unreachable. Watchdog recovery remains disabled.

Availability is not activation. At the current documentation cut:

- observe-only code merged: **yes**;
- exact current hosted revision: **yes**, current main
  `1c47e53d5121d2fae5e49019f88872838b80d47c`;
- local runtime/execution/manifest promoted to current main: **no**, all remain
  `98cfe04e4ea23a4ddc43525671bb56de0a49670d`;
- observe-only handshake executed: **no**;
- ordinary CORE operation enabled: **no**;
- naturally proven mission operation: **no**.

The canonical stop marker remains present and the watchdog remains disabled.
A later handshake requires a new exact-revision owner authorization and must
end with zero CORE processes, the marker restored, and watchdog disabled.
