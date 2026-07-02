# Owner Decisions

Status: owner-reviewed governance decisions captured on 2026-07-02.

## Vault Brain Authority

The Vault Brain should become the primary active brain after owner review.

Reason: this clean and structured brain is what keeps CHARLIE, CHARLIE CORE, agents, business environments, and future teams aligned.

## Brain Guard

Brain Guard should become a visible CHARLIE specialist agent in the dashboard.

Brain Guard's role is to approve knowledge integrity only when the relevant docs are aligned. Brain Guard does not approve business actions, deployments, customer messages, public posts, payments, stock allocation, or farm lifecycle changes.

## Mission Vault Brain Field

Every mission should carry a `vault_brain_update_required` field.

Recommended values:

- `yes`
- `no`
- `unknown`

Required companion fields:

- `vault_brain_docs_used`
- `vault_brain_docs_changed`
- `vault_brain_update_reason`
- `brain_guard_status`

## Mission Doc Visibility

The `/charlie` dashboard should show which Vault Brain docs each mission used.

Reason: owner review, Analyst review, Brain Guard review, and future improvement agents need to see whether failures came from missing docs, weak docs, wrong docs, or ignored docs.

## Repo Cleanup Direction

After the Vault Brain is accepted and active, stale docs should be archived or removed only after their useful decisions have been migrated into the Vault Brain.

Rule: the repo should become cleaner, but the Vault Brain must stay the clean controlling structure.

## CHARLIE CORE Agent Direction

All key CHARLIE CORE workflow stages should eventually become true separate agents.

Priority direction:

1. Builder first.
2. Split Builder into focused build roles when needed, such as UI-focused and code-focused builders.
3. Allow controlled parallel work only when ownership boundaries, merge rules, tests, and Brain Guard checks are clear.

## Analyst Direction

Analyst should become a standing CHARLIE CORE improvement function, not a passive advisory note.

Analyst should:

- understand the CHARLIE CORE system;
- inspect outcomes, bugs, workflow failures, duplicated problems, and weak docs;
- run after missions, on a schedule, or by trigger;
- create improvement proposals for owner review;
- avoid duplicating the same unresolved issue repeatedly;
- merge related issues into one useful proposal when appropriate;
- push approved improvements into the CHARLIE CORE workflow.

Analyst may suggest and prepare improvements. Owner approval remains required before execution.

## Overnight Mission Confidence

Deep overnight missions without active human oversight require at least 96% confidence.

If confidence is below 96%, CHARLIE CORE must either reduce scope, add checkpoints, request owner review, or run only lower-risk stages.

## Beacon Department

Beacon is officially a shared Marketing department under CHARLIE.

Beacon should support multiple businesses and environments, not only Amadeus Farm.
