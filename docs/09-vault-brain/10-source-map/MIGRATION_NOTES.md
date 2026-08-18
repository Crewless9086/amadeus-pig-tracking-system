# Vault Brain Migration Notes

2026-07-02:

- Flat first-pass Vault Brain files were split into structured folders.
- No old active source docs were deleted.
- Content was consolidated into focused files for owner review.
- First source consolidation pass began: meat sales, pork business model, pig purpose/allocation, farm operating map, SAM knowledge, and private transfers were migrated into focused Vault files with source references.
- Added `VAULT_MIGRATION_INVENTORY.md` so future Brain Guard cleanup can classify source docs before archive/removal.
- Second consolidation pass migrated backend data contracts, Supabase rules, Google Sheets legacy rules, telemetry rules, n8n workflow doctrine, testing/deployment/security/customer standards, and operations playbooks.
- Archived old `planning/CHAT.md` n8n sales-agent scratch to `docs/99-archive/legacy/planning_CHAT_2026-04_n8n_sales_agent_rewire.md`.

2026-08-18 - Vault Cutover Batch 16:

- Reconciled the accepted documentation source-of-truth decision into focused
  Vault governance: `docs/` location alone no longer implies authority.
- Reconciled CHARLIE/CORE identity, configuration namespaces, environment
  planes and fail-closed legacy-alias migration into focused identity and
  deployment standards.
- Archived the two dated ADR wrappers and the completed legacy migration index
  intact. The physical-cutover manifest is now the current migration ledger.
