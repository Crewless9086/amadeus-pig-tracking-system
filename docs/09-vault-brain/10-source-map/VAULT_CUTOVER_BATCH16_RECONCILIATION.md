# Vault Cutover Batch 16 Reconciliation

Status: `COMPLETE / THREE WRAPPERS ARCHIVED / DURABLE FACTS RETAINED`
Date: 2026-08-18
Baseline: `fc195acab2db88aba7c759ea31bcdc6674a94fe1`

## Scope And Result

Batch 16 completely reviewed and reconciled:

- `docs/07-decisions/ADR_0001_DOCUMENTATION_SOURCE_OF_TRUTH.md`;
- `docs/07-decisions/ADR_0002_CHARLIE_CORE_TERMINOLOGY_AND_CONFIGURATION.md`;
- `docs/MIGRATION_INDEX.md`.

The files are preserved intact under `docs/99-archive/vault-cutover/` and no
longer appear in the active documentation tree.

## Retained Durable Facts

- `SOURCE_OF_TRUTH_RULES.md` now makes the corrected authority boundary
  explicit: the focused Vault governs; placement anywhere under `docs/` does
  not create authority; planning and legacy material remain non-authoritative.
- `CHARLIE_CORE.md` retains the CHARLIE/CORE identity split and configuration
  namespace ownership.
- `DEPLOYMENT_STANDARD.md` retains the local/hosted/CI/GitHub/Supabase
  configuration planes and the fail-closed canonical-key/legacy-alias rollout.
- `MIGRATION_NOTES.md` records this physical reconciliation. The generated
  physical-cutover manifest replaces the completed legacy migration index.

## Boundaries

- Archive was used instead of deletion so dated rationale remains recoverable.
- No owner decision was changed or inferred.
- No runtime configuration, environment variable, deployment, provider,
  database, customer, farm or hardware state was changed.
- The remaining physical queue is 178 documents in Batches 17 through 27.
