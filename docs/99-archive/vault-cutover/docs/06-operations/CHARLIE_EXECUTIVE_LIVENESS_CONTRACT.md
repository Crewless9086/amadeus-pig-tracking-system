# CHARLIE Executive Liveness Contract

Status: active architecture contract.

## Purpose

CHARLIE owns portfolio momentum above CORE. CORE executes bounded missions; it does not decide that a process heartbeat is equivalent to useful progress. Supabase `charlie_missions` remains mission truth and the primary checkout `.charlie_runner` control files remain local runtime truth.

## Non-Negotiable Invariants

1. A recovery mission may not depend on the blocked parent it exists to repair.
2. Dependency filtering happens before queue limits. A blocked first row may never hide runnable work.
3. CHARLIE reasons over four separate counts: approved, runnable, dependency-blocked, and active.
4. Safe independent work continues when another mission family is blocked.
5. `approved > 0`, `runnable = 0`, and no active mission is a queue-deadlock incident, not an idle queue.
6. The watchdog measures process health and portfolio progress. It must never label a deadlocked queue healthy.
7. Every Git worktree publishes heartbeat and supervisor state to one canonical control directory.
8. Recoverable engineering failures are CHARLIE decisions within delegated policy. Charl is contacted only for red-zone authority or genuine business discretion.
9. Final delegated approval requires current PR state, green deterministic checks, complete acceptance evidence, and policy/trust authority. CHARLIE may not approve its own unverified work.
10. Executive incidents use Charl's private CHARLIE channel. CORE stage chatter is not the owner interface.
11. Windows watchdog, supervisor, and process probes run without visible console windows.
12. ANALYST validates a conveyor repair against the original failure signature after deployment.

## Executive Loop

Each cycle observes durable mission state, classifies dependencies, adjudicates recoverable blocks, verifies delegated reviews, maintains a runnable runway, and records an incident when progress is impossible. Idempotency keys prevent repeated commands and repeated Telegram noise.

## Authority

CHARLIE may approve safe new engineering work and verified final reviews only through active delegation policy and promoted trust. Customer sends, public posts, payments, reservations, stock/lifecycle writes, destructive migrations, credential access, and unresolved business choices remain Charl decisions.

## Proof Standard

The repair is complete only when tests reproduce the former blocked-first-row failure, prove a recovery child runs while its parent is blocked, prove the watchdog reports queue deadlock, prove runtime state resolves to the primary checkout, and show a live approved mission moving to `in_progress` after restart.
