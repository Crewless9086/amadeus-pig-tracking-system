---
name: amadeus-implement
description: Implement or repair bounded Amadeus repository work from current main with canonical-system reuse, collision control, tests, and exact evidence. Use for development workers; not for release or owner-outcome acceptance.
---

# Implement Amadeus Work

Implement the requested mission outcome without creating a competing product system. Product doctrine, authority, business rules, and canonical identities remain in the tracked Vault and database.

## Before editing

1. Fetch `origin/main` and record exact main, worktree head, ahead/behind, dirt, open PRs, active agents, and overlapping files or migrations.
2. Read the complete mission standard and only the active authority documents selected for this scope. Read the existing mission, lineage, and relevant handover completely.
3. State the bounded outcome, explicit non-scope, protected effects, failure containment, and acceptance evidence.
4. Use a fresh isolated worktree from current main unless continuing the explicitly assigned PR lineage.
5. Require the dispatch to name a workspace-local artifact directory and runtime directory. Default to `control-tower-artifacts/<mission-or-pr>/` and `.codex-runtime/missions/<mission-or-pr>/`; do not invent an external output path.

## Implementation invariants

- Reuse canonical services, identities, events, queues, providers, confirmation rails, localisation, and data models. Do not add parallel workflows or stores merely to make a test pass.
- Preserve unrelated user work and historical evidence. Unknown remains Unknown.
- Treat database migrations and external actions as authority-bearing code. Make mismatches fail before mutation and verify semantic structure, not matching words or literals.
- Test real production-shaped inputs and actual call paths. Fixtures must not invent fields the provider or caller does not supply.
- Keep protected confirmation, idempotency, concurrency, rollback, least privilege, and canonical readback intact.
- Do not broaden authority, enable automation, contact owners/customers/providers, mutate production, or operate hardware unless the exact task expressly authorizes it.

## Proof and handover

Run focused domain, security, data-integrity, adversarial, and relevant wider regression tests. Run Brain Guard/Vault alignment, diff checks, and hosted exact-head CI. Explain skips and environmental limits.

Return the exact base/head, files changed, tests and adversarial cases, PR/CI state, collisions, unknowns, protected effects, rollback state, and next acceptance action using the tracked feedback handover template. Say `NO BUSINESS OUTCOME` unless genuine operational acceptance has already occurred. Do not merge, deploy, or claim loaded revision unless assigned that separate authority.

Write working handovers, evidence summaries, screenshots, and comparisons only under the assigned mission artifact directory. Write generated payloads, test databases, caches, and disposable outputs only under the assigned runtime directory. Canonical durable documents still use their governed repository paths. Do not use `%TEMP%`, AppData, Desktop, Documents, `C:\\tmp`, or broad environment-variable overrides for routine work.
