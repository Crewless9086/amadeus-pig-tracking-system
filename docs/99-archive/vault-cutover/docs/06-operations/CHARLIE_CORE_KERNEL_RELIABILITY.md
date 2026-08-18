# CHARLIE CORE Kernel Reliability

## Purpose

This repair hardens the shared workflow kernel. It does not patch individual missions or weaken owner authority.

## Failure Contract

1. Git marker access failures become durable `repository_infrastructure` results with the exact path, error type, and recovery action.
2. Three identical child exits stop the supervisor, including exits that occur before the child writes a recognized status.
3. An infrastructure hold sends the exact signature, affected path when known, and required recovery through the existing owner notification path.
4. The watchdog reports `supervisor_child_crash_restarting` separately from healthy startup.
5. A typed marker-access failure may recreate only the dedicated `.charlie_runner` worktree. Ambiguous or non-empty Git operations are never deleted automatically.
6. All runner Git preflight and worktree repair operations share one canonical repository-operation lock.

## Mission Continuity

7. Release and review packets are merged with existing evidence on release failure. Earlier PR, test, and review evidence is retained.
8. A recovered final artifact for the wrong durable stage is quarantined once. It cannot stop supervisor startup or be consumed repeatedly.
9. Acceptance-recovery children use a five-stage workflow: Source Mapper, Builder, Tester, Evidence Reviewer, Reviewer.
10. A child is not created when path-bearing acceptance criteria are outside its declared allowed-file scope.

## Visibility And Learning

11. CORE exposes supervisor restarts, identical failure count, latest failure, attempts, stage runtime, and changed-file evidence. The dashboard strip shows restart and latest-failure truth.
12. A successful automated conveyor repair immediately runs an ANALYST lifecycle refresh. Improvement proposals then move through deployed validation using later mission outcomes rather than remaining advisory forever.

## Executive Closure

- Every frozen acceptance matrix includes a CHARLIE-owned closure contract.
- An existing idempotency key is not treated as success until the desired Supabase mission state is present.
- An exhausted identical repair changes strategy through Planner/Architect or bounded child decomposition.
- Terminal bounded children automatically return their paused parent to Evidence Reviewer.
- Creating an unapplied additive migration is internal engineering work. Applying it to production remains an explicit Charl decision.
- The Windows supervisor uses an operating-system named mutex as well as the durable lock file, and runner children start without a visible console window.

## Contract-Aware Recovery

- A recovery hint cannot jump past an earlier incomplete durable workflow stage. Artifact ingestion and execution therefore agree on the stage that owns the next result.
- An ordinary owner send-back remains a deliberate direct stage resume and does not replay accepted upstream work.
- A Builder refusal caused by `builder_allowed=false` is owned by Architect. CORE routes to Architect once instead of retrying an unauthorized Builder.
- Every queued internal stage recovery triggers an asynchronous ANALYST cycle. Repeated routing defects therefore become measured proposals and deployed-repair validation evidence.

## Safety

- The repository repair is limited to a dedicated `.charlie_runner` worktree and its configured base branch.
- Non-empty Git operations stop for inspection.
- No customer send, payment, reservation, stock, lifecycle, migration, merge authority, or owner gate is changed.
- Deterministic tests remain the final completion gate.
