# Archive Review Queue

These areas still need Brain Guard review before any cleanup/removal:

- `docs/99-archive/`
- `planning/inbox/processed/`
- old prompts under `docs/99-archive/old-prompts/`
- superseded reports and migration notes.
- duplicate/superseded planning notes under `planning/`
- old business-module drafts after their decisions are migrated into the Vault
- external source briefs after their reusable context is migrated or marked not needed

Do not delete source material until its content has been migrated or explicitly marked not needed.

## Archive Gate

Before any source file is archived or removed, Brain Guard must verify:

1. the source appears in `VAULT_MIGRATION_INVENTORY.md` or another source-map file;
2. decisions, rules, SOPs, business context, agent boundaries, and data contracts were copied into the correct Vault file where useful;
3. the Vault target includes the source reference;
4. open questions were moved to `00-governance/OPEN_QUESTIONS.md`;
5. owner approval was given for archive/removal.
