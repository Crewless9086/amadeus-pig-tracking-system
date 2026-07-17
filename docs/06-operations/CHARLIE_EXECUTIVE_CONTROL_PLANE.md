# CHARLIE Executive Control Plane

Status: approved implementation contract.

## Purpose

CHARLIE is Charl's private executive control layer. CORE remains the mission execution engine. Supabase remains authoritative for runtime state, while the Vault Brain remains owner-reviewed doctrine.

The control plane must keep productive work moving, resolve recoverable exceptions, apply only explicitly delegated authority, and interrupt Charl only for genuine owner decisions or red-zone actions.

## Operating Model

1. Observe current mission, runner, queue, recovery, business, and policy state.
2. Reduce observations into deterministic commands with idempotency keys.
3. Execute only commands allowed by a current delegation policy and tool permission.
4. Record every command, decision, result, and notification in append-only audit rails.
5. Verify outcomes through deterministic gates and candidate-bound evidence.
6. Escalate ambiguous, irreversible, legal, financial, public, customer, credential, reservation, and lifecycle actions to Charl.

## Authority

- `auto`: reversible internal mechanics with deterministic verification.
- `charlie_delegated`: bounded authority explicitly delegated by Charl, with expiry, scope, budget, rollback, and audit requirements.
- `charl_human`: red-zone, strategic ambiguity, exhausted recovery, or authority not delegated.

Prompt text and model confidence never grant authority. Policies are deny-by-default and stored in Supabase.

## Durable Kernel

Every control-plane action is represented by a command with an idempotency key. Recovery cases have a responsible stage, retry budget, next attempt time, deadline, and terminal disposition. Notifications use an outbox so process crashes cannot silently lose them.

CORE may not leave a recoverable failure sitting in an owner-blocked state. It must schedule recovery, preserve passing evidence, and continue unrelated work. Genuine owner decisions remain blocked and visible.

## Learning

The Doctrine Vault contains owner-approved rules. Evidence Memory contains outcomes, incidents, corrections, research, and measurements. Evidence cannot silently become doctrine. ANALYST may create deduplicated proposals and owner-gated missions, then measure whether deployed changes improve the baseline.

## Success Measures

- unattended completion by mission class;
- recoverable failures resolved without Charl;
- false owner escalations;
- deterministic gate pass rate;
- unauthorized red-zone action count;
- crash/restart state-loss count;
- substantial owner-review effort rate;
- delegated decision acceptance rate;
- validated improvement effectiveness rate.

Targets are measured rolling outcomes, not claims: 95%, 98%, below 2%, 100%, zero, zero, below 10%, 95%, and 80% respectively.

## Rollout

The control plane starts in observe-only mode. Delegated commands are enabled per capability only after tests, canary evidence, and trust thresholds pass. Existing CORE behavior remains available as rollback until the new cycle proves stable.

## Twelve-Point Delivery Map

1. Executive state: Supabase goals, policies, commands, recovery cases, and scorecards are durable and authoritative.
2. Workflow kernel: commands are idempotent; recovery is atomic, bounded, evidence-preserving, and crash-safe.
3. Approval levels: `auto`, `charlie_delegated`, and `charl_human` are deny-by-default and policy-bound.
4. Approval bundles: related genuine owner decisions are grouped into one evidence-backed request without combining execution authority.
5. Capability trust: outcomes promote or demote narrowly scoped capabilities; trust is never global.
6. Mission-class evaluations: versioned scenarios and deterministic gates must pass before a class is promoted.
7. Automated recovery: known recoverable block classes return to the responsible stage while unrelated queue work continues.
8. Portfolio scheduling: approved missions are ranked by urgency, goal alignment, revenue impact, business value, and dependencies.
9. Two-layer Vault: evidence memory may propose; only owner-approved, tested evidence may become doctrine.
10. Continuous ANALYST: terminal mission outcomes feed the existing operational analyst, while CHARLIE records capability outcomes and effectiveness.
11. Research radar: source-linked observations are stored for review; they never self-activate or silently change doctrine.
12. Security and identity: every command requires an explicit capability policy; red-zone actions remain Charl-only and notifications use a durable outbox.

## Activation Contract

- `CHARLIE_EXECUTIVE_MODE=off` disables the cycle.
- `CHARLIE_EXECUTIVE_MODE=observe` records proposed commands without mission mutation.
- `CHARLIE_EXECUTIVE_MODE=active` executes only policy-authorized internal recovery and queue-continuation commands.
- Missing tables, missing policies, invalid state, exhausted retries, or ambiguous ownership fail closed.
- Activation requires migration verification, the full CHARLIE test suite, verify gate, live canary observation, and a recorded rollback path.
