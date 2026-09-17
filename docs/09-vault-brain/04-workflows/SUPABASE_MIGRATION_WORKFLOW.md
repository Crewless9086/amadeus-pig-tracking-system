# Supabase Migration Workflow

Before migration:

- confirm source and target ownership;
- run dry-run/reconciliation;
- define rollback;
- verify additive schema;
- apply only with explicit approval;
- record evidence and update Vault Brain.

## Evidence Sequence

1. Inventory exact source callers, tables/formulas, read/write ownership and
   target routes.
2. Back up the source and run a no-write import/verifier with explicit
   include/exclude and normalization rules.
3. Report source, mapped, imported, rejected, duplicate, quarantined and
   conflicting counts plus source checksums and representative mismatches.
4. Apply only additive schema under separate authority.
5. Import through an idempotent batch with source lineage and a reviewed
   batch-specific rollback.
6. Compare formula/read-model outputs in shadow mode before changing a route.
7. Cut over one bounded read or write family at a time; never infer write
   readiness from successful reads.
8. Verify production behavior, failure containment and rollback before the
   next family. Sheets export/fallback retirement is a later stability-window
   decision.

Conflicts and skipped records remain visible in typed review output and cannot
silently affect canonical projections. A historical report is evidence of its
own run only; fresh acceptance requires current source, target and route proof.

No production write without approval.
