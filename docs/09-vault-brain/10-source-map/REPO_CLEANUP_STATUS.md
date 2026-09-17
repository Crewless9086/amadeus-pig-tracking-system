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
| `docs/05-ai/` | No tracked documents remain after Batches 5 and 6. | Legacy files are preserved under the Vault cutover archive; runtime retrieval must not load them as current sources. |
| `docs/06-operations/` | Runbooks, test evidence, migration reports. | Keep; extract standards/playbooks into Vault. Archive only superseded reports after owner approval. |
| `docs/08-business-modules/` | Physically retired in Batch 25. | Originals preserved under `docs/99-archive/vault-cutover/`; focused Vault packs are authoritative. |
| `docs/99-archive/` | Archive. | Keep. Use for old scratch/plans. |
| `planning/CODEX_CHAT.md` | Technical runtime projection; non-doctrine and non-durable. | Keep minimal compatibility path; never infer mission activity or authority. |
| `planning/ToDoList.md` | Technical owner scratchpad; non-doctrine and non-durable. | Keep minimal and untriaged only; durable outcomes use governed intake/register paths. |
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

Next cleanup targets are governed by the exact remaining batches in
`VAULT_PHYSICAL_CUTOVER_MANIFEST.md`. Batch 20 completed the general-operations
split; Batches 21-27 own the remaining domain/history families, Batch 28 owns
transitional exit tests, and Batch 29 owns deployed Brain Guard acceptance.

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
- 72 transitional documents are reconciled under exactly two named blocked
  exits in `TRANSITIONAL_EXIT_TEST_REGISTER.md`; they must remain until those
  complete tests pass.
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
9. **Planning material:** active-looking plans and prompts are reconciled;
   the complete Storyworks package is archived by Batch 27
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

## Vault Cutover Batch 3 - Enforcement And Principal-Agent Audit

Status: `SOURCE_ENFORCEMENT_COMPLETE / DEPLOYED_ACCEPTANCE_PENDING`.

Machine enforcement now:

- classifies missions into additive CORE, Oom Sakkie, ROOTLINE, HERDMASTER,
  SAM livestock, SAM meat, BEACON campaign, BEACON livestock-awareness, UI and
  Documents packs;
- loads common and matched pack files at mandatory priority;
- reports missing mandatory files and incomplete packs;
- blocks legacy, planning, archive, external-source and static-agent documents
  when claimed as doctrine;
- blocks current-state registers, start-here projections, handovers, scorecards,
  examples and changelogs when claimed as doctrine;
- preserves only the two registered outside-Vault controlling exceptions; and
- validates every pack file and authority-map registration in the deterministic
  repository alignment audit.

### Principal-agent contradiction audit

| Pack | Competing material found | Binding Batch 3 disposition | Remaining remediation |
| --- | --- | --- | --- |
| Common governance | `docs/00-start-here/*`, mission/current-state registers and historical governance handovers | Current-state or evidence only; never reusable doctrine | Reconcile projections, then pointer/archive review |
| CORE | planning master plans and numerous `docs/06-operations/CHARLIE*` recovery/runtime records | Technical or historical evidence only | Extract the few current runtime procedures into focused runbooks; retire stale plans |
| Oom Sakkie | architecture roster/prompt library, n8n routing plans and many operational handovers | Vault pack governs; external files are technical/transitional/history | Classify exact handovers and retain only current provider/runbook evidence |
| ROOTLINE | device, commissioning, irrigation and operating-policy documents across operations/n8n | Vault pack governs decisions; hardware/provider contracts remain technical evidence | Separate current device runbooks from dated commissioning history |
| HERDMASTER | breeding, litter, weighing, mortality and sales handovers under operations and Vault governance | Handovers excluded from doctrine; focused agent/workflow/rules govern | Extract accepted husbandry rules and reconcile gaps agent by agent |
| SAM | `docs/05-ai`, business modules, backend contracts, n8n workflows and build plans | Vault sales packs govern; backend is technical; n8n/Sheets are transitional | Reconcile unique live channel/data facts, then pointer/archive review |
| BEACON | old Vault handovers, `docs/05-ai` scope/media files and launch packets | Handovers excluded; exact campaign/awareness pack governs | Extract any unique provider/media facts; prohibit sales drift in awareness lane |
| UI | legacy page plans and dashboard guidance outside the focused standards | Owning agent pack plus Facelift/UI standards governs every UI mission | Review legacy UI plans for unique examples only |
| Documents | catalogue architecture and n8n/Sheets delivery workflows without a focused Documents agent/workflow pack | Fail closed | Create one owner-reviewed Vault Documents pack before autonomous use |

The file-level Batch 1 ledger remains the exact remediation source. This audit
does not authorize moving or deleting any listed file.

## Vault Cutover Batch 4 - Exact Physical-Cutover Manifest

Status: `MANIFEST_COMPLETE / NO_PHYSICAL_CHANGE / OWNER_EXECUTION_APPROVAL_PENDING`.

The deterministic manifest covers all 513 tracked source Markdown/MDX files at
baseline `66d4667d6ecc4eda9c59c3ff06795494cda0a53b`. Every entry records its
full current digest, physical line count, exact references across all tracked
UTF-8 text, disposition, exact destination or replacement, blockers and an
explicit false physical-authorization flag.

| Disposition | Count |
| --- | ---: |
| Keep canonical Vault | 172 |
| Keep controlling exception | 2 |
| Keep current state | 2 |
| Keep technical | 27 |
| Keep transitional until exit test | 72 |
| Keep existing archive | 15 |
| Reconcile generated projection | 9 |
| Convert to pointer after reconciliation | 18 |
| Extract unique facts, then archive | 117 |
| Split current runbook, then archive history | 73 |
| Archive candidate awaiting later approval | 6 |
| Delete candidate | 0 |

No document currently meets the strict deletion test. Historical evidence
defaults to archive; transitional n8n/Sheets material remains blocked by exit
tests; static agent cards remain until generated projections are proven; and
pointer candidates retain their full source until unique facts reconcile.

Review artifacts:

- `VAULT_PHYSICAL_CUTOVER_MANIFEST.md`
- `VAULT_PHYSICAL_CUTOVER_MANIFEST.json`
- `scripts/build_vault_cutover_manifest.py`

This batch does not move, archive, delete or rewrite any source document.

## Vault Cutover Batch 5 - First Physical Cleanup Slice

Status: `SLICE_COMPLETE / FIVE FILES ARCHIVED / ZERO DELETIONS`.

Owner approved one bounded physical slice with a separate exact approval still
required for every deletion. The five top-level `docs/05-ai` governance files
were reconciled, moved intact to
`docs/99-archive/vault-cutover/docs/05-ai/`, and removed from active doctrine
and active-reference routing.

At the end of Batch 5, the agent-specific BEACON and SAM files remained
physically in `docs/05-ai`.
No runtime, provider, production-data, authority or deployed-agent behavior
changed. The regenerated manifest is the source for the next owner-reviewed
slice and grants no further physical authority.

## Vault Cutover Batch 6 - Remaining AI References

Status: `SLICE_COMPLETE / DOCS_05_AI_FULLY_ARCHIVED / ZERO DELETIONS`.

The three BEACON documents and one SAM v3 build plan that remained under
`docs/05-ai` were reconciled and archived intact. Current authority resolves to
focused Vault packs; current technical truth resolves to code, migrations,
tests, provider evidence and the Implementation Source Map.

No runtime or production effect occurred. The regenerated manifest grants no
further physical authority.

## Vault Cutover Batch 7 - Superseded External UI Briefs

Status: `SLICE_COMPLETE / TWO UI BRIEFS ARCHIVED / ZERO DELETIONS`.

Two zero-reference external UI briefs were preserved intact in the Vault
cutover archive. Their accepted direction is governed by the mandatory
Facelift and UI Dashboard standards rather than by historical build prompts.

The external-source index and current forecast, Sunsynk and carcass documents
remain in place. No doctrine rewrite, runtime or production effect occurred.
The regenerated manifest grants no further physical authority.

## Vault Cutover Batch 8 - External Candidate Reconciliation

Status: `RECONCILIATION_COMPLETE / ARCHIVE_CANDIDATES_ZERO / ZERO DELETIONS`.

The four remaining external archive candidates were reviewed and retained as
current technical/source evidence. The carcass standard remains consumed by
meat workflows and tests; the external index retains secret-handling rules; the
forecast and Sunsynk READMEs retain current provider/ingest contracts.

Vault doctrine remains authoritative. No physical or runtime effect occurred.

## Vault Cutover Batch 9 - Legacy Navigation Pointers

Status: `SLICE_COMPLETE / SEVEN POINTERS / ZERO DELETIONS`.

Seven small legacy navigation/process files now contain only compatibility
pointers to focused Vault authority. Their original content remains in Git
history. Referenced CORE paths were retained, and no runtime, provider,
production-data or authority change occurred.

## Vault Cutover Batch 10 - Root/Status Navigation Pointers

Status: `SLICE_COMPLETE / FIVE POINTERS / ZERO DELETIONS`.

The root Claude guidance, asset register, two dated status files and owner inbox
guide now contain only minimal compatibility/technical routing. Their original
content remains in Git history. No runtime, provider, production-data or
authority change occurred.

## Vault Cutover Batch 11 - Technical Operating Contracts

Status: `SLICE_COMPLETE / THREE POINTERS / ZERO DELETIONS`.

The legacy runner, mission protocol and deployment SOP now point to focused
current Vault contracts. Required runner and release procedures were first
consolidated into those existing files. No runtime, activation, deployment,
provider, production-data or authority change occurred.

## Vault Cutover Batch 12 - Current-State And Roadmap Projections

Status: `SLICE_COMPLETE / TWO POINTERS / ZERO DELETIONS`.

The legacy current-state dashboard and next-steps roadmap now point to the
durable Control Tower register and focused Vault mission workflow. Their dated
content remains in Git history, and the `NEXT_STEPS.md` compatibility fallback
cannot offer obsolete missions. `PRODUCT_VISION.md` remains for a later bounded
reconciliation. No runtime or production effect occurred.

## Vault Cutover Batch 13 - Final Start-Here Projection

Status: `SLICE_COMPLETE / ONE POINTER / ZERO DELETIONS`.

The product-vision path now routes to focused Oom Sakkie identity and UI
standards. Unique durable experience principles were retained; duplicated
agent, provider, phase and asset material remains only in Git history. The
start-here projection queue is empty. No runtime or production effect occurred.
