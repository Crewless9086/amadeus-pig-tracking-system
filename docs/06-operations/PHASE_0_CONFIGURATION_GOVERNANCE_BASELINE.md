# Phase 0 Configuration Governance Baseline

Status: implementation evidence for owner review.

Date: 2026-07-19.

No environment values were printed, committed, changed or sent to another system. No Render setting was changed.

## Inventory result

The secrets-safe audit classified 99 local `.env` key names and 20 Render backend key names, with zero unknown keys and zero current plane-placement mismatches. Configuration is operationally classifiable, but not semantically clean.

## Confirmed ambiguity

- `CHARLIE_CORE_NOTIFICATION_MODE` belongs to CORE relay/notification behavior but is present locally and on Render under the CHARLIE namespace.
- `CHARLIE_TELEGRAM_TRANSPORT` is assigned to CHARLIE Executive transport, but does not distinguish Executive ingress from CORE relay notifications.

## Legacy families

Local configuration contains 27 keys in historical families: `CHARLIE_PRIVATE_*`, `CHARLIE_BUILD_RELAY_*`, `CHARLIE_AGENT_MODEL_*`, `CHARLIE_MODEL_*`, `CHARLIE_RUNNER_*` and `CHARLIE_REQUIRE_*`. Render contains 11 `CHARLIE_PRIVATE_*` keys. None may be removed until canonical aliases exist and live canaries pass.

## Reference audit caveat

Literal reference scanning marks dynamically constructed model-routing names as apparently unused. They are not dead merely because their complete strings do not appear in source. `RENDER_API_KEY` is operator-only by design. `SUPABASE_PROJECT_REF` needs explicit Phase 1 usage confirmation. No key may be deleted based only on literal search.

## Proposed namespace matrix

| Current family | Owner | Canonical family | Primary plane |
| --- | --- | --- | --- |
| `CHARLIE_PRIVATE_*` | CHARLIE Executive | `CHARLIE_*` | Render backend and optional local diagnostics |
| `CHARLIE_EXECUTIVE_*` | CHARLIE Executive | unchanged | Render backend/local |
| `CHARLIE_BUILD_RELAY_*` | CORE relay | `CORE_RELAY_*` | local CORE; hosted only where relay remains required |
| `CHARLIE_AGENT_MODEL_*` | CORE model routing | `CORE_AGENT_MODEL_*` | local CORE/CI |
| `CHARLIE_MODEL_*` | CORE model routing | `CORE_MODEL_*` | local CORE/CI |
| `CHARLIE_RUNNER_*` | CORE runtime | `CORE_RUNNER_*` or specific runtime/execution names | local CORE/CI |
| `CHARLIE_REQUIRE_*` | CORE governance | `CORE_REQUIRE_*` | local CORE/CI |
| `CHARLIE_CORE_NOTIFICATION_MODE` | CORE relay | `CORE_NOTIFICATION_MODE` | local CORE plus hosted compatibility if consumed there |
| `CHARLIE_TELEGRAM_TRANSPORT` | CHARLIE Executive | retain or clarify as `CHARLIE_TELEGRAM_INGRESS_TRANSPORT` | Render backend/local diagnostic |

## Phase 1 migration sequence

1. Confirm canonical names against active readers and deployment planes.
2. Implement one shared canonical-first resolver.
3. Reject differing canonical and legacy values without printing either.
4. Test absent, legacy-only, canonical-only, equal-dual and conflicting-dual cases.
5. Add canonical local keys while retaining legacy keys; run CORE canaries.
6. Add canonical Render keys while retaining legacy keys; deploy and run owner-only CHARLIE canaries.
7. Observe both planes through an agreed stability window.
8. Produce a separate retirement proposal; delete nothing without owner review.

## Rollback contract

- Capture key names, source revision and status without values before each plane change.
- Keep legacy keys during code and deployment rollback.
- Local rollback restores the prior promoted CORE commit and manifest.
- Render rollback restores the prior deployed commit.
- Conflict, missing required key, failed cold start, failed webhook canary or failed owner authentication stops migration.
- Secret rotation remains separate unless exposure is detected.

## Phase 0 exit assessment

Terminology, ownership, ambiguity, legacy families, staged migration and rollback are explicit. Before merge, documentation linkage, expanded validation and CI must pass. Phase 1 must not edit `.env` or Render until this baseline is merged and its ADR is accepted.
