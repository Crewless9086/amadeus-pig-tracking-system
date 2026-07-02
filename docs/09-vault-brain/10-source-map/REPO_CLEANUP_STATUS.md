# Repo Cleanup Status

Status: active cleanup control, started 2026-07-02.

Goal: make the repo clean without deleting operational memory, workflow contracts, or evidence that CHARLIE CORE still needs.

## Current Cleanup Position

| Area | State | Cleanup action |
| --- | --- | --- |
| `docs/09-vault-brain/` | Canonical brain/doctrine layer. | Keep and grow. |
| `docs/00-start-here/` | Active operator/startup docs and mission protocol. | Keep active; source-map to Vault. |
| `docs/01-architecture/` | Active architecture/reference docs. | Keep active until Vault has full replacement and code references are updated. |
| `docs/02-backend/` | Active technical contracts and migration plans. | Keep active beside code; migrate doctrine into Vault. |
| `docs/03-google-sheets/` | Legacy/runtime schema truth. | Keep while Sheets remain fallback/reference. |
| `docs/04-n8n/` | Active workflow/runtime contracts. | Keep beside n8n exports; Vault carries doctrine. |
| `docs/05-ai/` | Active agent/prompt/runtime references. | Keep while runtime agents and prompt plans depend on them. |
| `docs/06-operations/` | Runbooks, test evidence, migration reports. | Keep; extract standards/playbooks into Vault. Archive only superseded reports after owner approval. |
| `docs/08-business-modules/` | Business source docs. | Keep as active references until owner accepts Vault replacements. |
| `docs/99-archive/` | Archive. | Keep. Use for old scratch/plans. |
| `planning/CODEX_CHAT.md` | Active runner scratchpad. | Keep. Do not commit incidental runner dirt unless mission requires it. |
| `planning/ToDoList.md` | Owner scratch/inbox. | Keep as live scratchpad. |
| `planning/CHAT.md` | Old n8n sales-agent rewire scratch. | Archived to `docs/99-archive/legacy/planning_CHAT_2026-04_n8n_sales_agent_rewire.md`. |
| `external_sources/` | Imported external context/source projects. | Keep; review one by one before reuse or deletion. |
| `static/assets/agents/` | Runtime/UI agent asset notes. | Keep; canonical doctrine is Vault agent docs. |

## Cleanup Rules

- Do not delete source docs only because their knowledge was summarized.
- Do not move runtime docs while code/workflows/tests still reference them.
- Archive old scratch only when no code/docs reference it and useful decisions were migrated or marked not needed.
- Every cleanup action must update this file or `VAULT_MIGRATION_INVENTORY.md`.

## Current Cleanliness Estimate

- Vault structure/usefulness: `82-87%` after this pass.
- Repo documentation control: `70-75%`.
- Physical repo cleanup: `25-30%`, because many source docs remain active references by design.

Next cleanup targets:

1. Review `docs/06-operations/OPERATIONAL_FIXES_EVIDENCE_LOG.md` and split durable lessons from raw evidence.
2. Review `docs/08-business-modules/*` with owner; archive business drafts only after owner accepts Vault replacements.
3. Review `external_sources/` and mark each source as keep/reference/archive/delete.
4. Add deprecation headers to docs that are superseded by Vault but still kept for history.
