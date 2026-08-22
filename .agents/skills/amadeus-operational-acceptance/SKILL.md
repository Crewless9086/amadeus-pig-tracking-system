---
name: amadeus-operational-acceptance
description: Prove an Amadeus change after implementation through exact deployment, genuine owner-visible journeys, canonical and provider readback, replay, containment, and unattended continuity. Use before calling any mission or feature an owner outcome.
---

# Prove Operational Acceptance

Use after implementation or release review. This is an evidence workflow, not a substitute runtime inside Amadeus.

## Establish the acceptance contract

Read the complete mission standard, mission record, selected active doctrine, implementation handover, independent review, and release approval. Derive each explicit acceptance requirement and the authoritative evidence source that can prove it.

Choose only the tools relevant to the journey:

- Git/GitHub for exact reviewed and merged revisions and CI.
- Deployment/provider inspection for exact loaded revision, service health, schedules, delivery, and callbacks.
- Browser control for what the owner actually sees and does, including language, buttons, mobile layout, and concise decisions.
- Read-only canonical database inspection for exact state, events, work items, identities, receipts, and duplicate counts.
- Hardware/provider readback for queue, device, or physical effects.

Browser text never substitutes for canonical truth, and database state never substitutes for provider delivery or physical observation when those are part of the promised outcome.

## Acceptance sequence

1. Reconfirm exact current main, reviewed head, merge commit, deployment identity, loaded revision, configuration/feature gates, and collision state.
2. Verify preconditions and zero unexpected pending effects before a protected or physical action.
3. Execute or observe one genuine owner-origin journey. Do not replay a historical event when the mission requires a later genuine event.
4. Capture the owner-visible decision and completion through the real provider or deployed UI.
5. Read back every affected canonical entity and event, including related work that must close and unrelated work that must remain open.
6. Verify provider, queue, device, and physical effects where applicable. Never infer a physical result from an API response.
7. Prove idempotent replay/duplicate safety, concurrency behavior, and failure containment without reversing legitimate business facts.
8. Establish automatic follow-up and then a later terminal-independent cycle when the mission promises continued operation.
9. Compare the final owner journey with the prior journey and state the owner work actually removed.

## Decision rule

For every requirement classify evidence as proven, contradicted, incomplete, indirect, or missing. Any material incomplete, indirect, or missing item means `NO BUSINESS OUTCOME` and the mission remains active.

Call an owner outcome only when the owner can genuinely use the result and all promised canonical, provider, and physical effects are verified at the correct scope. A merge, deploy, health check, heartbeat, screenshot, or test suite alone is never sufficient.

Return the tracked full handover and Control Tower Check Receipt, including exact revisions, timestamps, identities, redacted evidence locations, replay/rollback results, later-cycle proof, remaining unknowns, and one owner action only if unavoidable.
