# Data Migration Playbook

Use additive migrations, dry-run/reconciliation, rollback plan, verification queries, and explicit owner approval before production writes.

## Standard Sequence

1. Define current source and target source of truth.
2. Document schema and ownership.
3. Create additive migration only.
4. Add health/schema verifier.
5. Run dry-run import or plan-only generator.
6. Review include/exclude rules.
7. Apply only after explicit approval.
8. Verify row counts, date ranges, and selected field values.
9. Compare read models.
10. Cut over reads behind a controlled route/flag only after comparison passes.
11. Cut over writes only after rollback/operator views are accepted.
12. Update Vault and source map.
13. Classify every remaining legacy caller as active route, compatibility
    fallback, import/export/admin, reference-only or test-only.
14. Retire fallback only after a fresh stability-window and rollback review;
    do not treat completed route cutover as automatic deletion authority.

## Hard Stops

- No destructive migration without exact approval.
- No production write when the source-of-truth boundary is unclear.
- No sheet cleanup before backup/import/compare acceptance.
- No conflicting or identity-ambiguous source row may silently become
  canonical truth; retain it in governed review/quarantine evidence.

## Source References

- `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md`
- `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`
- `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`
