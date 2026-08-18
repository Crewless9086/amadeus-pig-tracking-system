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

## Vault Cutover Batch 1 — 2026-08-18

Status: `INVENTORY_COMPLETE / CLASSIFICATION_PROPOSED / NO_PHYSICAL_CHANGE`.

Owner-approved boundary: inventory and classification only. This batch did not
move or delete a file, rewrite doctrine, alter runtime configuration, invoke an
agent, or change production state.

Exact baseline: authoritative main `59c34f961c2c84bfa182b783987c806ac838fabe`
in clean worktree `C:\tmp\vault-cutover-batch1-20260818`.

### Measured repository position

- 513 tracked Markdown/MDX documents.
- 172 documents inside `docs/09-vault-brain`.
- 341 documents outside the intended live Vault.
- 0 byte-identical duplicate-content groups.
- 163 documents require manual lifecycle classification.
- 96 planning documents are proposed for extraction before archive/delete review.
- 75 operational documents are proposed for separation of current runbook from history.
- 72 transitional documents must remain until their explicit exit tests pass.
- 9 static agent assets require generation/reconciliation from Vault authority.

The complete file-by-file ledger, content hashes, declared lifecycle signals,
reference counts and proposed actions are recorded in
`VAULT_MIGRATION_INVENTORY.md`. A proposed action is not deletion authority.

### Priority conflict families for Batch 2 review

1. **Competing doctrine authority:** `ACTIVE_DOCS_SOURCE_MAP.md` and legacy
   start/architecture/AI documents still allow non-Vault files to steer missions.
2. **Agent standing orders:** CORE, Oom Sakkie, ROOTLINE, HERDMASTER, SAM and
   BEACON rules are split between Vault agent files, operations evidence,
   architecture documents, business modules and runtime assets.
3. **BEACON/Meta safety:** farm-awareness storytelling rules and livestock-sales
   implementation history can be read as competing publication doctrine.
4. **Operational status duplication:** current-state, next-step, mission-register,
   handover and evidence-log files mix durable rules with dated state.
5. **UI/FACELIFT routing:** the Vault Facelift Standard exists, but every UI
   mission does not yet have one deterministic mandatory pack.
6. **Data authority:** Supabase canonical truth, Google Sheets transitional
   fallback and historical n8n write paths require explicit non-competing labels.
7. **Runtime projections:** `static/assets/agents/*/agent.md` are manually
   maintained projections rather than demonstrably generated Vault derivatives.
8. **Runtime programme pointer:** the canonical architecture programme and its
   historical operations-path pointer must not both appear authoritative.
9. **Planning material:** active-looking plans, prompts and storyworks documents
   can steer terminals despite not being accepted doctrine.

### Required audit order before physical cleanup

1. Governance and authority routing.
2. Cross-agent common operating contract.
3. CORE and Oom Sakkie.
4. ROOTLINE and HERDMASTER.
5. BEACON and SAM, including Meta safety.
6. CODEX UI and mandatory Facelift pack.
7. Documents and remaining specialist packs.
8. Data/workflow authority and runtime-derived assets.
9. Historical extraction, archive and deletion proposals for owner approval.

Until those audits finish, `GOVERNANCE_ALIGNMENT_HOLD` remains active: no new
feature implementation should use unresolved legacy doctrine as mission authority.

## Vault Cutover Batch 2 - Authority Routing

Status: `DESIGN_APPLIED / PHYSICAL_CUTOVER_NOT_STARTED`.

Batch 2 establishes one normative doctrine root, two narrow registered
cross-system exceptions, deterministic mission packs and explicit evidence-only
classes. It does not move, archive or delete files. It does not activate Brain
Guard, change production configuration or claim runtime enforcement.

Decisions:

- `docs/09-vault-brain/` is the only normative agent-doctrine root.
- The canonical Runtime Programme and mandatory Control Tower handover template
  remain narrow controlling exceptions outside the Vault.
- The mission register and start-here files are current-state/operator
  projections, not reusable doctrine.
- Legacy agent/business/architecture docs, n8n/Sheets docs, planning material,
  handovers, evidence logs and static agent assets receive explicit non-doctrine
  dispositions in `ACTIVE_DOCS_SOURCE_MAP.md`.
- Every UI mission requires the Facelift pack.
- Every BEACON livestock-awareness/Meta mission requires the awareness workflow
  and cannot import livestock availability or sales calls-to-action.

Remaining before physical cleanup: implement deterministic pack enforcement;
complete the ordered agent-by-agent contradiction audit; produce the exact
pointer/archive/delete manifest; obtain owner approval for that manifest.
