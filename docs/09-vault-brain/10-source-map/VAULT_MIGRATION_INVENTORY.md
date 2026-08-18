# Vault Migration Inventory

Status: first consolidation pass started 2026-07-02.

Purpose: track non-Vault markdown sources, classify them, and record where useful decisions/rules/context are migrated inside the Vault Brain.

Classification values:

- `migrated`: useful operating knowledge has been copied into focused Vault docs with source references.
- `active_reference`: keep as a live technical/runtime source; do not archive.
- `runtime_reference`: generated/export/runtime docs that explain live workflows or code contracts; keep near the runtime area.
- `archive_after_extract`: can move to archive later only after Brain Guard verifies useful content was migrated.
- `review_queue`: needs owner/Brain Guard review before migration or archive.

## High-Value Source Buckets

| Source bucket | Classification | Vault targets | Notes |
| --- | --- | --- | --- |
| `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md` | migrated + archived | `03-business/MEAT_SALES.md`, `08-business-rules/MEAT_SALES_RULES.md`, `04-workflows/SAM_MEAT_SALES_WORKFLOW.md`, `02-agents/sales/SAM.md` | Batch 25 retained focused launch and implementation gates; the original is history. |
| `docs/08-business-modules/PORK_SALES_MODEL.md` | migrated + archived | `03-business/MEAT_SALES.md`, `08-business-rules/MEAT_SALES_RULES.md`, `03-business/AMADEUS_MEAT_CUTTING_AND_COMMERCIAL_STANDARD.md` | Focused commercial authority retained; the long planning discussion is history. |
| `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md` | migrated + archived | `03-business/AMADEUS_FARM.md`, `08-business-rules/PIG_PURPOSE_RULES.md`, `06-data/FARM_DATA_MODEL.md` | Focused allocation/purpose and one-pig-one-truth rules retained. |
| `docs/08-business-modules/SAM_FARM_KNOWLEDGE_PACK.md` | migrated + archived | `02-agents/sales/SAM.md`, `04-workflows/SAM_MEAT_SALES_WORKFLOW.md` | Runtime wording configuration remains `config/sam_farm_knowledge.json`; it is not doctrine. |
| Owner-added Amadeus Private Transfers proposal | migrated | `03-business/AMADEUS_PRIVATE_TRANSFERS.md`, `02-agents/transport/FRED.md`, `08-business-rules/TRANSPORT_RULES.md` | Converted from raw paste into structured business doctrine. |
| `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md` | migrated + active_reference | `03-business/AMADEUS_FARM.md`, `06-data/*`, `04-workflows/SUPABASE_MIGRATION_WORKFLOW.md` | Architecture and data ownership source. |
| `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md` | migrated + active_reference | `01-identity/AGENT_ORGANOGRAM.md`, `02-agents/*`, `02-agents/AGENT_REGISTRY.md` | Specialist roster and approval rules. |
| `docs/05-ai/AGENT_ROLES.md` | migrated + active_reference | `02-agents/*`, `04-workflows/*`, `08-business-rules/*` | Short current operating role register. |
| `docs/05-ai/RESPONSE_RULES.md` | migrated + active_reference | `07-standards/CUSTOMER_RESPONSE_STANDARD.md`, agent docs | Customer-facing safety rules. |
| `docs/04-n8n/WORKFLOW_RULES.md` | migrated + active_reference | `04-workflows/N8N_WORKFLOW_SUITE.md`, `08-business-rules/*` | Live n8n rules stay beside workflow exports; doctrine migrated. |
| `docs/04-n8n/CHATWOOT_ATTRIBUTES.md` | migrated + active_reference | `06-data/ORDER_DATA_MODEL.md`, `06-data/MEAT_SALES_DATA_MODEL.md`, `04-workflows/SAM_MEAT_SALES_WORKFLOW.md`, `04-workflows/N8N_WORKFLOW_SUITE.md` | Canonical Chatwoot label/attribute register. |
| `docs/04-n8n/*` | migrated + active_reference | `04-workflows/N8N_WORKFLOW_SUITE.md`, standards/rules files | Workflow doctrine migrated; detailed runtime contracts stay active. |
| `docs/02-backend/*.md` | migrated + active_reference | `06-data/*`, `07-standards/*`, workflow docs | Backend doctrine migrated; technical contracts stay close to code. |
| `docs/03-google-sheets/*.md` | migrated + active_reference | `06-data/GOOGLE_SHEETS_LEGACY.md`, `06-data/FARM_DATA_MODEL.md`, `06-data/ORDER_DATA_MODEL.md` | Legacy schema/write rules migrated; sheet docs stay active while legacy/fallback remains. |
| `docs/06-operations/*.md` | migrated + review_queue | `07-standards/*`, `05-playbooks/*`, `10-source-map/*` | Standards/playbooks migrated; raw evidence logs still need later cleanup. |
| `static/assets/agents/*/agent.md` | migrated + active_reference | `02-agents/*`, `02-agents/AGENT_REGISTRY.md` | Runtime/static asset notes remain; Vault is canonical doctrine. |
| `planning/*.md` and `planning/inbox/**/*.md` | review_queue | `00-governance/OPEN_QUESTIONS.md`, relevant business/workflow docs | Do not bulk-archive without owner approval. |
| `planning/CHAT.md` | migrated + archived | `04-workflows/N8N_WORKFLOW_SUITE.md`, `07-standards/CUSTOMER_RESPONSE_STANDARD.md` | Archived to `docs/99-archive/legacy/planning_CHAT_2026-04_n8n_sales_agent_rewire.md`. |
| `docs/99-archive/**` | review_queue | Archive only | Already archive, but may contain historical decisions worth extracting later. |
| `external_sources/**/*.md` | review_queue | Relevant business/architecture docs | External briefs should be classified one by one when reused. |
| `supabase/migrations/README.md` | active_reference | `06-data/SUPABASE_CONTRACTS.md` | Technical migration readme remains beside migrations. |

## First Pass Extracted Decisions

- Meat Sales is the first money-first proof lane.
- Meat Sales must be pre-sold, legal, traceable, deposit-gated, and bank-confirmed before irreversible operations.
- SAM is Farm Sales CEO, not just a meat bot.
- SAM must use backend gates and farm knowledge, but cannot invent price, availability, payment, booking, slaughter, butcher, or delivery state.
- Pig purpose is dynamic and must be driven by weights, growth, litter quality, demand, and outlet timing.
- Unknown purpose is a data/classification problem, not an automatic sale/meat/slaughter decision.
- Amadeus Farm keeps one pig operational truth; agents and n8n must not create shadow truth.
- FRED/Amadeus Private Transfers is a separate business environment from SAM/Farm Sales.
- FRED requires legal, insurance, booking, calendar, pricing, payment, and dispatch gates before customer automation.
- n8n is an orchestration/integration layer, not data truth.
- Google Sheets remains legacy/runtime reference where explicitly still used, but formula views and sales display views are read-only.
- Backend/Supabase contracts require dry-run, reconciliation, rollback, health checks, and owner approval before production writes/cutover.
- Testing, deployment, security, and customer response standards have been promoted into Vault doctrine.

## Cleanup Rule

No source doc should be deleted or moved only because this inventory exists.

Brain Guard must confirm three things before archive cleanup:

1. useful decisions/rules/context were migrated into the correct Vault file;
2. the Vault file includes a source reference;
3. the owner approved archive/removal for that source or source bucket.

<!-- BATCH1_GENERATED_START -->

## Batch 1 Complete Tracked-Document Inventory — 2026-08-18

Status: owner-approved inventory/classification proposal only. No file move, deletion, doctrine rewrite, or runtime change is authorized by this table.

- Tracked Markdown/MDX documents: **513**
- Inside `docs/09-vault-brain`: **172**
- Outside live Vault: **341**
- Exact duplicate-content groups: **0**
- Reference count is a conservative literal path/basename occurrence count across tracked UTF-8 text; zero is a review signal, not deletion authority.
- Every proposed action requires Batch 2+ review and owner-approved execution.

### Proposed classification totals

| Classification | Count |
| --- | ---: |
| `active` | 139 |
| `active_reference` | 28 |
| `authoritative` | 13 |
| `historical` | 79 |
| `quarantined` | 2 |
| `retired` | 2 |
| `review_queue` | 163 |
| `runtime_reference` | 9 |
| `superseded` | 6 |
| `transitional` | 72 |

### Proposed action totals

| Action | Count |
| --- | ---: |
| `archive_or_delete_review` | 26 |
| `classify_manually` | 5 |
| `consolidate_then_archive_or_delete` | 19 |
| `consolidate_then_pointer_or_delete` | 16 |
| `extract_then_archive_or_delete` | 96 |
| `generate_or_reconcile` | 9 |
| `keep_archive` | 15 |
| `keep_review` | 152 |
| `keep_technical_review` | 17 |
| `keep_until_exit_test` | 72 |
| `split_active_runbook_from_history` | 75 |
| `split_doctrine_from_technical` | 11 |

### Repository-area totals

| Area | Count |
| --- | ---: |
| `00-start-here` | 16 |
| `01-architecture` | 11 |
| `02-backend` | 16 |
| `03-google-sheets` | 32 |
| `04-n8n` | 40 |
| `05-ai` | 9 |
| `06-operations` | 129 |
| `07-decisions` | 3 |
| `08-business-modules` | 10 |
| `09-vault-brain` | 172 |
| `99-archive` | 15 |
| `CLAUDE.md` | 1 |
| `docs` | 1 |
| `external_sources` | 6 |
| `planning` | 42 |
| `static` | 9 |
| `supabase` | 1 |

### Exact duplicate groups

None.

### Per-file proposal ledger

| Path | Lines | SHA-256 | Declared signal | Proposed lifecycle | Proposed action | Refs | Exact duplicate | Rationale |
| --- | ---: | --- | --- | --- | --- | ---: | --- | --- |
| `CLAUDE.md` | 161 | `844e19520b5e` | `unspecified` | `review_queue` | `classify_manually` | 4 | no | no safe automatic lifecycle conclusion |
| `docs/00-start-here/AGENT_ASSET_REGISTER.md` | 83 | `ef8b7f10f5fe` | `unspecified` | `review_queue` | `consolidate_then_pointer_or_delete` | 4 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/AGENT_PORTFOLIO_STATUS.md` | 218 | `ba12f0f4e6a4` | `historical` | `review_queue` | `consolidate_then_pointer_or_delete` | 3 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md` | 215 | `77fcadb6c33a` | `historical` | `review_queue` | `consolidate_then_pointer_or_delete` | 18 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md` | 393 | `bb6978cc74da` | `unspecified` | `review_queue` | `consolidate_then_pointer_or_delete` | 39 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md` | 17 | `1a92de4df646` | `historical` | `review_queue` | `consolidate_then_pointer_or_delete` | 22 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/CURRENT_STATE.md` | 355 | `01923159507e` | `historical` | `review_queue` | `consolidate_then_pointer_or_delete` | 83 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/DEPLOYMENT_SOP.md` | 84 | `1ce91ac8f19b` | `unspecified` | `review_queue` | `consolidate_then_pointer_or_delete` | 30 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/GLOSSARY.md` | 22 | `15bd096a2998` | `unspecified` | `review_queue` | `consolidate_then_pointer_or_delete` | 0 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/HOW_WE_WORK.md` | 92 | `519a8d2d164b` | `unspecified` | `review_queue` | `consolidate_then_pointer_or_delete` | 5 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/NEXT_STEPS.md` | 668 | `68a737b23d71` | `unspecified` | `review_queue` | `consolidate_then_pointer_or_delete` | 138 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/OPERATING_STATUS.md` | 178 | `7229613e2c76` | `unspecified` | `review_queue` | `consolidate_then_pointer_or_delete` | 6 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/OWNER_INBOX_GUIDE.md` | 54 | `7710e4eeaac8` | `unspecified` | `review_queue` | `consolidate_then_pointer_or_delete` | 13 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/PRODUCT_VISION.md` | 2324 | `65f8d21dbd88` | `unspecified` | `review_queue` | `consolidate_then_pointer_or_delete` | 10 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/PROJECT_OVERVIEW.md` | 44 | `e496e0b80599` | `unspecified` | `review_queue` | `consolidate_then_pointer_or_delete` | 3 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/README.md` | 63 | `22e65806e339` | `historical` | `review_queue` | `consolidate_then_pointer_or_delete` | 67 | no | startup doctrine competes with Vault until cutover |
| `docs/00-start-here/WORKFLOW.md` | 73 | `7deffa291a3e` | `active` | `review_queue` | `consolidate_then_pointer_or_delete` | 139 | no | startup doctrine competes with Vault until cutover |
| `docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md` | 278 | `08067d860635` | `controlling` | `active_reference` | `split_doctrine_from_technical` | 34 | no | architecture may remain technical only after doctrine extraction |
| `docs/01-architecture/CANONICAL_DOCUMENT_CATALOGUE_OWNERSHIP.md` | 32 | `1b43f309b44f` | `transitional` | `active_reference` | `split_doctrine_from_technical` | 0 | no | architecture may remain technical only after doctrine extraction |
| `docs/01-architecture/COMPONENT_OWNERSHIP.md` | 17 | `fa93c345560c` | `unspecified` | `active_reference` | `split_doctrine_from_technical` | 2 | no | architecture may remain technical only after doctrine extraction |
| `docs/01-architecture/DATA_FLOW_OVERVIEW.md` | 9 | `b83414ae79c4` | `unspecified` | `active_reference` | `split_doctrine_from_technical` | 0 | no | architecture may remain technical only after doctrine extraction |
| `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md` | 141 | `61f3c64bc7a4` | `unspecified` | `active_reference` | `split_doctrine_from_technical` | 14 | no | architecture may remain technical only after doctrine extraction |
| `docs/01-architecture/JARVIS_EXTERNAL_REFERENCE_REVIEW.md` | 178 | `dea672504027` | `unspecified` | `active_reference` | `split_doctrine_from_technical` | 0 | no | architecture may remain technical only after doctrine extraction |
| `docs/01-architecture/OOM_SAKKIE_AGENT_PROMPT_LIBRARY.md` | 833 | `48d132d7be79` | `unspecified` | `active_reference` | `split_doctrine_from_technical` | 4 | no | architecture may remain technical only after doctrine extraction |
| `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md` | 372 | `553178d9c973` | `unspecified` | `active_reference` | `split_doctrine_from_technical` | 20 | no | architecture may remain technical only after doctrine extraction |
| `docs/01-architecture/OOM_SAKKIE_VOICE_OPERATING_AGENT_PRD.md` | 959 | `de9db6810185` | `unspecified` | `active_reference` | `split_doctrine_from_technical` | 0 | no | architecture may remain technical only after doctrine extraction |
| `docs/01-architecture/SLACK_ARCHITECTURE_ASSESSMENT.md` | 351 | `756707de1513` | `unspecified` | `active_reference` | `split_doctrine_from_technical` | 0 | no | architecture may remain technical only after doctrine extraction |
| `docs/01-architecture/SYSTEM_ARCHITECTURE.md` | 348 | `ecb5a70dc697` | `historical` | `active_reference` | `split_doctrine_from_technical` | 7 | no | architecture may remain technical only after doctrine extraction |
| `docs/02-backend/API_STRUCTURE.md` | 875 | `280775807bb5` | `active` | `active_reference` | `keep_technical_review` | 16 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/DATABASE_SCALING_PLAN.md` | 577 | `45a6960d5593` | `unspecified` | `active_reference` | `keep_technical_review` | 6 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/DATA_MODELS.md` | 115 | `340996dea4ea` | `unspecified` | `active_reference` | `keep_technical_review` | 5 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/MODULE_STRUCTURE.md` | 82 | `41a579806646` | `unspecified` | `active_reference` | `keep_technical_review` | 1 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/ORDER_INTAKE_STATE_DESIGN.md` | 331 | `e577af8c0700` | `unspecified` | `active_reference` | `keep_technical_review` | 1 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/ORDER_LOGIC.md` | 314 | `cc854fa42ff5` | `active` | `active_reference` | `keep_technical_review` | 7 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/ORDER_VERIFICATION_MATRIX.md` | 223 | `794f9bf2fab4` | `active` | `active_reference` | `keep_technical_review` | 2 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/PIG_LIFECYCLE_OUTCOME_PLAN.md` | 139 | `eb5abc7ba1c0` | `active` | `active_reference` | `keep_technical_review` | 0 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/QUOTE_INVOICE_DESIGN.md` | 384 | `204b1edcfd96` | `unspecified` | `active_reference` | `keep_technical_review` | 7 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/README.md` | 36 | `541c80a79cc4` | `unspecified` | `active_reference` | `keep_technical_review` | 63 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/REFACTOR_PLAN.md` | 199 | `b9fc8ae79114` | `unspecified` | `active_reference` | `keep_technical_review` | 1 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/SAM_LIVESTOCK_CONTINUOUS_FOLLOWUP_CONTRACT.md` | 105 | `f126aeb8adc0` | `historical` | `active_reference` | `keep_technical_review` | 2 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/SAM_MEAT_INTAKE_CONTRACT.md` | 416 | `23ea7f0fc055` | `unspecified` | `active_reference` | `keep_technical_review` | 8 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md` | 446 | `122e351eac55` | `unspecified` | `active_reference` | `keep_technical_review` | 12 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md` | 1235 | `6d0e76a8e74a` | `unspecified` | `active_reference` | `keep_technical_review` | 20 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md` | 3100 | `b34c3d6a0168` | `active` | `active_reference` | `keep_technical_review` | 16 | no | code-adjacent schema/backend reference; cannot govern agents |
| `docs/03-google-sheets/BUSINESS_RULES.md` | 59 | `97a9b40e44ad` | `active` | `transitional` | `keep_until_exit_test` | 8 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/FIELD_DEFINITIONS.md` | 64 | `d8f148c8c754` | `unspecified` | `transitional` | `keep_until_exit_test` | 3 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/FORMULA_LOGIC.md` | 89 | `65b9326cc043` | `unspecified` | `transitional` | `keep_until_exit_test` | 8 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/README.md` | 76 | `8b906fb3d39d` | `unspecified` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/SHEET_CHANGELOG.md` | 86 | `b59c4544ad7b` | `active` | `transitional` | `keep_until_exit_test` | 3 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/SHEET_SCHEMA.md` | 125 | `636c7d5bd7df` | `unspecified` | `transitional` | `keep_until_exit_test` | 14 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/WRITE_OWNERSHIP.md` | 47 | `5f7ca5a03e2c` | `historical` | `transitional` | `keep_until_exit_test` | 9 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/LITTERS.md` | 34 | `f2733e850aaa` | `unspecified` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/LITTER_OVERVIEW.md` | 73 | `59b282cabcfe` | `active` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/LOCATION_HISTORY.md` | 27 | `d12614f4318f` | `unspecified` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/MATING_LOG.md` | 37 | `e2e42b8a8269` | `unspecified` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/MATING_OVERVIEW.md` | 51 | `d7d3eb277fa9` | `unspecified` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/MEDICAL_LOG.md` | 34 | `4de9e734e5e1` | `unspecified` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/ORDER_DOCUMENTS.md` | 56 | `318a05a6ce00` | `superseded` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/ORDER_INTAKE_ITEMS.md` | 77 | `8a442216d5dc` | `active` | `transitional` | `keep_until_exit_test` | 3 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/ORDER_INTAKE_STATE.md` | 85 | `3668d1a729f2` | `active` | `transitional` | `keep_until_exit_test` | 3 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/ORDER_LINES.md` | 13 | `ef62f86dcd93` | `unspecified` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/ORDER_MASTER.md` | 16 | `27f5445c8381` | `unspecified` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/ORDER_OVERVIEW.md` | 47 | `ac79cdcb03d8` | `unspecified` | `transitional` | `keep_until_exit_test` | 4 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/ORDER_STATUS_LOG.md` | 25 | `6d79633a57a6` | `unspecified` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/PEN_REGISTER.md` | 22 | `a0c8a09a7514` | `active` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/PIG_MASTER.md` | 19 | `d3d603b40e8b` | `unspecified` | `transitional` | `keep_until_exit_test` | 9 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/PIG_OVERVIEW.md` | 134 | `3c531700e256` | `unspecified` | `transitional` | `keep_until_exit_test` | 9 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/PRODUCT_REGISTER.md` | 27 | `9a17cebaca49` | `active` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/SALES_AVAILABILITY.md` | 39 | `06a3b9bf5a15` | `unspecified` | `transitional` | `keep_until_exit_test` | 11 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/SALES_PRICING.md` | 82 | `9a4d6befeeb3` | `unspecified` | `transitional` | `keep_until_exit_test` | 15 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/SALES_STOCK_DETAIL.md` | 104 | `6c2f26609529` | `active` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/SALES_STOCK_SUMMARY.md` | 125 | `e55419a3eb6c` | `active` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/SALES_STOCK_TOTALS.md` | 65 | `10c3501c4572` | `active` | `transitional` | `keep_until_exit_test` | 19 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/SYSTEM_SETTINGS.md` | 54 | `4a26542e18eb` | `unspecified` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/USERS.md` | 15 | `379f6a848b1b` | `unspecified` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/03-google-sheets/sheets/WEIGHT_LOG.md` | 27 | `212490b3224b` | `unspecified` | `transitional` | `keep_until_exit_test` | 9 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/CHANGELOG.md` | 905 | `31061f1d5546` | `unspecified` | `transitional` | `keep_until_exit_test` | 11 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/CHATWOOT_ATTRIBUTES.md` | 227 | `e1f6163c6154` | `active` | `transitional` | `keep_until_exit_test` | 16 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/DATA_FLOW.md` | 290 | `285b10ced1f3` | `unspecified` | `transitional` | `keep_until_exit_test` | 20 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/DO_NOT_CHANGE.md` | 109 | `a7b49f863ff9` | `authoritative` | `transitional` | `keep_until_exit_test` | 10 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/NODE_RESPONSIBILITIES.md` | 122 | `ae69f2d15671` | `active` | `transitional` | `keep_until_exit_test` | 9 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/OOM_SAKKIE_MANUAL_RECOVERY_CHECKLIST.md` | 149 | `aa1a8d3d2da2` | `active` | `transitional` | `keep_until_exit_test` | 3 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/OOM_SAKKIE_ROUTING_ARCHITECTURE_PLAN.md` | 350 | `bbe923a0ad73` | `active` | `transitional` | `keep_until_exit_test` | 3 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/README.md` | 116 | `109007db2591` | `active` | `transitional` | `keep_until_exit_test` | 62 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/WORKFLOW_MAP.md` | 231 | `6c604dfa67b2` | `unspecified` | `transitional` | `keep_until_exit_test` | 14 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/WORKFLOW_RULES.md` | 121 | `74120f718a88` | `unspecified` | `transitional` | `keep_until_exit_test` | 15 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/MEAT_INTAKE_HANDOFF_PLAN.md` | 150 | `dacff937ec06` | `unspecified` | `transitional` | `keep_until_exit_test` | 9 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md` | 2976 | `fcbdb5a813a3` | `unspecified` | `transitional` | `keep_until_exit_test` | 80 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/extractor-pipeline/README.md` | 80 | `e559d6bb04ca` | `unspecified` | `transitional` | `keep_until_exit_test` | 64 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/1.1 - Sam - sales-agent-escalation-telegram/README.md` | 215 | `8eb725b07f7b` | `unspecified` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/1.2 - order-steward/README.md` | 1157 | `d759d5684e07` | `active` | `transitional` | `keep_until_exit_test` | 64 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/1.3 - Sam-sales-agent-media-tool/README.md` | 390 | `34d2a7d069a6` | `unspecified` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/1.4 - outbound-order-notification/README.md` | 79 | `b7287524e632` | `unspecified` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/1.5 - outbound-document-delivery/README.md` | 99 | `282e0d54aace` | `unspecified` | `transitional` | `keep_until_exit_test` | 64 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/1.6 - daily-order-summary/README.md` | 80 | `62b611c8066d` | `unspecified` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2 - The GateKeeper/BACKEND_RELAY_WIRING_PLAN.md` | 161 | `fad958d520df` | `active` | `transitional` | `keep_until_exit_test` | 3 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2 - The GateKeeper/README.md` | 85 | `6bc708810cab` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.0 - OOM SAKKIE - Amadeus Assistant Agent/README.md` | 49 | `80f416251df0` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.0B - Oom Sakkie Backend Read-Only Relay/README.md` | 167 | `ce8b70ed3c99` | `active` | `transitional` | `keep_until_exit_test` | 64 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.1 - Amadeus Weather Sub-Agent/README.md` | 60 | `a410d00f65d8` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.1.1 - Amadeus Forecast Tool/README.md` | 41 | `a12de1a8a487` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.2 - Amadeus Sunsynk Sub-Agent/README.md` | 57 | `8cc17f00badf` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.3.1 - Build Daily Irrigation Plan/README.md` | 58 | `8e18c4ea78ad` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.3.2 - Run Irrigation Controller/README.md` | 94 | `ebddb84b2bfb` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.3.3 - Irrigation Status Tool/README.md` | 67 | `b4200c1b7666` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.4 - Amadeus Orders Sub Agent/README.md` | 90 | `4fb58a30d424` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.4.1 - Test Caller/README.md` | 31 | `b8ff9c2f5461` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.4.2 - Orders Approval Callback Handler/README.md` | 30 | `135f73c0c7bc` | `retired` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.4.3 - Order Approval Request Webhook/README.md` | 36 | `8a1104f42341` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.4.4 - Order Lookup Tool/README.md` | 107 | `03c09d6fc642` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/2.4.5 - Document Send Callback Handler/README.md` | 69 | `cbd889b0e62f` | `retired` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/ALERT - Farm Attention Digest/README.md` | 90 | `b85759ae6b76` | `active` | `transitional` | `keep_until_exit_test` | 63 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/ALERT - Power Backend Delivery/README.md` | 84 | `1df661dd62a5` | `active` | `transitional` | `keep_until_exit_test` | 64 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/ALERT - Weather Backend Delivery/README.md` | 73 | `20d0d761a33e` | `active` | `transitional` | `keep_until_exit_test` | 64 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/OOM_SAKKIE_ORDER_LOOKUP_PLAN.md` | 660 | `336b76f8775c` | `historical` | `transitional` | `keep_until_exit_test` | 1 | no | legacy/runtime contract pending proven retirement |
| `docs/04-n8n/workflows/ORDER_STEWARD_HANDOFF_CONTRACTS.md` | 288 | `dc8f04fab8f6` | `active` | `transitional` | `keep_until_exit_test` | 13 | no | legacy/runtime contract pending proven retirement |
| `docs/05-ai/AGENT_PORTFOLIO_REVIEW.md` | 153 | `d624f6e1dc2b` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 0 | no | agent/business doctrine must move exclusively to Vault |
| `docs/05-ai/AGENT_ROLES.md` | 92 | `6d6f8d85fa3e` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 18 | no | agent/business doctrine must move exclusively to Vault |
| `docs/05-ai/PROMPT_RULES.md` | 7 | `c80f5fa958d1` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 3 | no | agent/business doctrine must move exclusively to Vault |
| `docs/05-ai/README.md` | 8 | `bbe4b8d5c9a7` | `active` | `review_queue` | `consolidate_then_archive_or_delete` | 63 | no | agent/business doctrine must move exclusively to Vault |
| `docs/05-ai/RESPONSE_RULES.md` | 12 | `62304721d639` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 8 | no | agent/business doctrine must move exclusively to Vault |
| `docs/05-ai/agents/beacon/BEACON_SCOPE.md` | 316 | `e93854c2e01a` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 23 | no | agent/business doctrine must move exclusively to Vault |
| `docs/05-ai/agents/beacon/MEDIA_STORAGE_DECISION.md` | 134 | `1c940e2e474c` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 14 | no | agent/business doctrine must move exclusively to Vault |
| `docs/05-ai/agents/beacon/README.md` | 36 | `1187a63b25ce` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 63 | no | agent/business doctrine must move exclusively to Vault |
| `docs/05-ai/agents/sam/SAM_V3_LLM_FIRST_SHARED_CONTEXT_PLAN.md` | 162 | `9cf9dcf5721f` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 6 | no | agent/business doctrine must move exclusively to Vault |
| `docs/06-operations/AGENTIC_BUSINESS_OS_IMPLEMENTATION_ROADMAP.md` | 94 | `85d798904d81` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 1 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/AGENTIC_BUSINESS_OS_PHASE_2_7_EVIDENCE.md` | 103 | `b883cf708f25` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/AGENTIC_FARM_RUNTIME_PHASE0_DEPENDENCY_RETIREMENT_REGISTER.md` | 345 | `1e759f95ed31` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 6 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/AGENTIC_FARM_RUNTIME_PROGRAMME.md` | 23 | `8b9c9d69f5bd` | `historical` | `review_queue` | `split_active_runbook_from_history` | 19 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/AGENTIC_OPERATING_SYSTEM_PROGRAM.md` | 107 | `ae4e0b99649a` | `superseded` | `review_queue` | `split_active_runbook_from_history` | 4 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/BUILD_RELAY.md` | 187 | `101e33e2df66` | `active` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CHARLIE_AGENT_WORKFORCE.md` | 63 | `878bd155565d` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CHARLIE_BUILD_RELAY_PLAN.md` | 226 | `fd270f708799` | `active` | `review_queue` | `split_active_runbook_from_history` | 4 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CHARLIE_CORE_KERNEL_RELIABILITY.md` | 49 | `c44df24d36f4` | `quarantined` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CHARLIE_CORE_RUNTIME_RECOVERY.md` | 135 | `64a2be622c22` | `historical` | `review_queue` | `split_active_runbook_from_history` | 1 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CHARLIE_EXECUTIVE_CONTROL_PLANE.md` | 83 | `fb498ab2006f` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CHARLIE_EXECUTIVE_LIVENESS_CONTRACT.md` | 34 | `b59116fe8f06` | `active` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CHARLIE_LIVE_EXECUTIVE_V1.md` | 69 | `169afe2517be` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CHARLIE_PRIVATE_EXECUTIVE_INTERFACE.md` | 116 | `d8007e9260c8` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 5 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CHARLIE_PRIVATE_EXECUTIVE_MASTER_PLAN.md` | 173 | `ae7f826f5949` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 4 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CHARLIE_SHARED_AGENT_RUNTIME.md` | 48 | `63e44c7d6bc4` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CMQ_20260813_03_APPLICATION_PREVIEW_WIRING_HANDOVER.md` | 29 | `967c3c2d7845` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 2 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/CMQ_20260813_03_CANONICAL_CLAIM_EXECUTOR_COMPATIBILITY.md` | 58 | `b1318a2a485a` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CMQ_20260813_03_CANONICAL_PREVIEW_SOURCE_HANDOVER.md` | 26 | `577e3e434e82` | `active` | `historical` | `extract_then_archive_or_delete` | 2 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/CMQ_20260813_03_GROUPED_WEIGHT_MOVEMENT_RECONCILIATION.md` | 57 | `96033c8c1f0c` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CMQ_20260813_03_OOM_TYPED_PREVIEW_WIRING_HANDOVER.md` | 29 | `4c91ec7107ff` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 2 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/CMQ_20260813_05_ATOMIC_BOOTSTRAP_ADMISSION.md` | 53 | `2d7c3582a04d` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CMQ_20260813_05_CURRENT_PORTFOLIO_BASELINE_PLAN.md` | 143 | `a6541d65abf7` | `historical` | `review_queue` | `split_active_runbook_from_history` | 1 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CMQ_20260813_05_PHASE_A_PRIVATE_INPUT.md` | 73 | `9176bafad22f` | `historical` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CMQ_20260813_05_PHASE_A_SHADOW_CONTROL_TOWER.md` | 77 | `8b6650a09d1f` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CMQ_20260813_05_PORTFOLIO_CLASSIFICATION.md` | 11 | `9b0e61c84ab3` | `historical` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CODEX_CHAT_WORKFLOW.md` | 83 | `2ff5ad644abe` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CONTINUOUS_AGENT_ALIGNMENT_AUDIT_20260817.md` | 76 | `ba7ee2bcd033` | `historical` | `historical` | `extract_then_archive_or_delete` | 2 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md` | 216 | `e9e7711ca13a` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 18 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md` | 565 | `667ff366a778` | `active` | `review_queue` | `split_active_runbook_from_history` | 24 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/CORE_PROVIDER_ORIGIN_ACTIVATION_RAIL.md` | 31 | `a7cd9d7896cb` | `historical` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/FARM_OPERATING_DASHBOARD_V2_PLAN.md` | 126 | `84984595b4b7` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/GENERAL_TERMINAL_INTAKE_CONTRACT.md` | 59 | `3f9fa0b2dd44` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 6 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/GOOGLE_SHEETS_TO_SUPABASE_MIGRATION_PLAN.md` | 367 | `38c16a8b2891` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/GS_MIG_1_DRY_RUN_REPORT.md` | 131 | `6216668f25a9` | `active` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/GS_MIG_2_RECONCILIATION_REPORT.md` | 170 | `b26dc259b00c` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/GS_MIG_3A_DATA_ISSUE_REVIEW.md` | 151 | `a95af49887b0` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/GS_MIG_3B_IMPORT_POLICY_DECISIONS.md` | 81 | `a5b801604d0f` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/GS_MIG_3_BACKFILL_VERIFIER_REPORT.md` | 143 | `336daaf6acf5` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/GS_MIG_5_IMPORT_EXECUTION_REPORT.md` | 91 | `3689fe18048c` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/GS_MIG_5_INITIAL_IMPORT_PLAN.md` | 157 | `e6f7608c75b7` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/GS_MIG_6_CONFLICTING_WEIGHT_REVIEW.md` | 136 | `c7cc0574a195` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/GS_MIG_7B_FORMULA_SHADOW_REPORT.md` | 84 | `31031c7a89fa` | `active` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/GS_MIG_7_ROUTE_CUTOVER_REPORT.md` | 168 | `7e3ecfe4f4b8` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/GS_MIG_FINAL_AUDIT.md` | 173 | `f413a733a6eb` | `active` | `historical` | `extract_then_archive_or_delete` | 6 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/HERDMASTER_AUCTION_SALE_SOURCE_HANDOVER_20260808.md` | 120 | `6682ca20c873` | `historical` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/HERDMASTER_BREEDING_ATTENTION_UI_RECOVERY_PLAN_20260811.md` | 51 | `3824302cb2ce` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/HERDMASTER_BREEDING_EVIDENCE_QUALIFIED_HANDOVER.md` | 353 | `6403f31e765a` | `active` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/HERDMASTER_BREEDING_EXPOSURE_RECOVERY_AND_UNKNOWN_PARENT_PLAN_20260812.md` | 127 | `b2ae2b876ead` | `historical` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/HERDMASTER_BREEDING_EXPOSURE_RECOVERY_SOURCE_HANDOVER_20260812.md` | 100 | `8b348ac8c12d` | `active` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/HERDMASTER_EXPOSURE_CYCLE_TRANSITION_HANDOVER_20260812.md` | 59 | `a33bf8a9a25d` | `historical` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/HERDMASTER_FULL_LIFECYCLE_GENETIC_MERIT_DATA_UX_CONTRACT_20260813.md` | 402 | `d8b7dcb7567f` | `historical` | `review_queue` | `split_active_runbook_from_history` | 4 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/HERDMASTER_LITTER_SUPERSESSION_SOURCE_HANDOVER.md` | 88 | `dbf070fd2e53` | `historical` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/HERDMASTER_LITTER_WEANING_RECOVERY_LIT-2026-322B.md` | 108 | `d4d9ae9b35d2` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/HERDMASTER_MORTALITY_FIRST_REAL_ASSESSMENT_20260803.md` | 63 | `bc93ddc7d519` | `historical` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/HERDMASTER_MORTALITY_INTELLIGENCE_HANDOVER.md` | 36 | `8e9024ab9138` | `historical` | `historical` | `extract_then_archive_or_delete` | 1 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/HERDMASTER_NATURAL_HEALTH_LOSS_SOURCE_HANDOVER.md` | 90 | `9735c53ee93b` | `active` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/HERDMASTER_OP004_SALES_MULTILINE_INTEGRATION_HANDOFF_20260817.md` | 104 | `3c7dac5433a0` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/HERDMASTER_PIGLET_WEANING_OBSERVATION_PLAN_20260812.md` | 161 | `1f9bfd1963b1` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 4 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/HERDMASTER_PRACTICAL_MATING_SELECTION_PLAN.md` | 105 | `98323b10baa4` | `active` | `review_queue` | `split_active_runbook_from_history` | 6 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/HERDMASTER_PROACTIVE_MANAGEMENT_ROUND_HANDOVER.md` | 26 | `a9a37bd5a58e` | `active` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/HERDMASTER_SAM_REVIEW_HISTORY_ALLOWLIST_HANDOVER.md` | 74 | `ea4cd06dfeb7` | `historical` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/HERDMASTER_UNIFIED_BREEDING_CAPTURE_PLAN_20260812.md` | 92 | `4a8544ba0f52` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 5 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/HERDMASTER_WEANING_LED_MATING_RECOVERY_PLAN_20260811.md` | 44 | `695f9e343998` | `active` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/HERDMASTER_WEIGHING_BATCH_INTELLIGENCE_SOURCE_HANDOVER_20260811.md` | 40 | `0b623e7c6acc` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/HERDMASTER_WHOLE_HERD_NEXT_ROUND_HANDOVER.md` | 63 | `886b924f690b` | `active` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/HERDMASTER_ZIGAY_REVISED_SUPERSESSION_PREVIEW.md` | 103 | `1718a2d6ee7e` | `superseded` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/MISSION_LOOP_CONTRACT.md` | 124 | `98b4fa8971cc` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 6 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/OOM_SAKKIE_ACTIONABLE_DAILY_MANAGER_MISSION_20260812.md` | 139 | `04a2e4ec59ff` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 3 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/OOM_SAKKIE_AUTOMATIC_REASSESSMENT_HANDOVER.md` | 23 | `c281bbe355e7` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_BREEDING_ROUTING_TASK_RETIREMENT_HANDOVER_20260811.md` | 56 | `a67c3c2949ee` | `historical` | `historical` | `extract_then_archive_or_delete` | 2 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_BROWSER_BEHAVIOR_CHECKLIST.md` | 76 | `bec568e02ad1` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 4 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/OOM_SAKKIE_CONTEXTUAL_SPECIALIST_FOLLOWUP_HANDOVER.md` | 74 | `949cf6cd789b` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_DAILY_FARM_MANAGER_LOOP_HANDOVER.md` | 79 | `c0c7aea10761` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 2 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_DURABLE_MORNING_RUNTIME_HANDOVER_20260813.md` | 119 | `b542a7fe098f` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_FAMILY_ACCESS_SOURCE_HANDOVER.md` | 67 | `1aa58e9ea025` | `historical` | `historical` | `extract_then_archive_or_delete` | 6 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_FARM_MANAGER_ROUND_HANDOVER.md` | 288 | `fc916b20ee3e` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 2 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_FARM_MANAGER_SOURCE_HANDOVER.md` | 273 | `e2a42b7930d9` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_FARM_MANAGER_SPINE_SCORECARD_20260809.md` | 113 | `bb5414c9e2a5` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/OOM_SAKKIE_GENERIC_FAMILY_MESSAGE_LIFECYCLE_HANDOVER.md` | 68 | `a037a595e505` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_HERDMASTER_MANAGEMENT_CONSUMER_HANDOVER.md` | 145 | `0875c3c1bd62` | `active` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_HERDMASTER_MORTALITY_CONSUMPTION_HANDOVER.md` | 15 | `2833a8e56475` | `historical` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_LLM_SEMANTIC_FRONT_DOOR_HANDOVER.md` | 70 | `1d544b09b93d` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 2 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_MANAGER_QUALITY_COMPOSER_HANDOVER.md` | 32 | `563ec16c538b` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_OWNER_ATTENTION_QUEUE_SOURCE_HANDOVER.md` | 84 | `4a07a1113258` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 2 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_OWNER_OPERATIONAL_CONTINUATION_HANDOVER.md` | 52 | `02945d68fc5e` | `historical` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_OWNER_REQUEST_AGENT_LIFECYCLE_HANDOVER.md` | 142 | `7bbe7be194ad` | `active` | `historical` | `extract_then_archive_or_delete` | 2 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_P0_NATURAL_PREVIEW_CORRECTION_HANDOVER.md` | 78 | `43614ff2abe8` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_P0_OPERATIONAL_INTAKE_RECOVERY_HANDOVER.md` | 73 | `63932185b3ce` | `historical` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_P0_PIG125_LIFECYCLE_REENTRY_HANDOVER.md` | 36 | `a9ac5ba442ea` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_PROTECTED_ACTION_RECOVERY_HANDOVER_20260811.md` | 73 | `c8ef9f64f49d` | `historical` | `historical` | `extract_then_archive_or_delete` | 3 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_RELAY_PROVIDER_CHRONOLOGY_HANDOVER.md` | 21 | `16ef43eb6a5b` | `active` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_ROOTLINE_DAILY_PRESENTATION_HANDOVER.md` | 47 | `ad3a7cf95f0c` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 2 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_ROOTLINE_OPERATIONAL_INTAKE_HANDOVER.md` | 84 | `cea44690eba8` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_SENTINEL_SINGLE_SHOT_RUNBOOK.md` | 133 | `db8ed0dded79` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/OOM_SAKKIE_SPECIALIST_DISPATCH_ACK_HANDOVER.md` | 117 | `d5828e0b1405` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_SPECIALIST_OWNER_DECISION_BINDING_HANDOVER.md` | 78 | `cdfcc03a065e` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OOM_SAKKIE_WITHDRAWAL_RELAY_RECOVERY_HANDOVER.md` | 105 | `858f857aa3ef` | `historical` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OP004_LIVE_TRANSFER_DISCLOSURE_CONTRACT_20260816.md` | 163 | `4d5413c56305` | `superseded` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/OPERATIONAL_FIXES_EVIDENCE_LOG.md` | 772 | `ef1ccb05b5d3` | `active` | `historical` | `extract_then_archive_or_delete` | 4 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/OPERATIONAL_FIXES_MASTER_PLAN.md` | 374 | `fcb9a7df2787` | `transitional` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/PARINGS_EN_WERPSEL_LIFECYCLE_REDESIGN_PLAN.md` | 96 | `d6361638696e` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/PHASE_0_CONFIGURATION_GOVERNANCE_BASELINE.md` | 62 | `7a73ea3a535d` | `historical` | `review_queue` | `split_active_runbook_from_history` | 1 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/PHASE_1_SAFE_NAMESPACE_MIGRATION.md` | 76 | `7fcf540732bf` | `historical` | `review_queue` | `split_active_runbook_from_history` | 1 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/PIG_PROFILE_LIFE_RECORD_UI_PLAN_20260811.md` | 63 | `c8dde0d056ea` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/README.md` | 29 | `31ba4e80b92f` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 63 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/RELEASE_CHECKLIST.md` | 13 | `acf228725364` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 3 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/ROOTLINE_ADAPTIVE_IRRIGATION_MANAGEMENT.md` | 130 | `df319e6cf87c` | `historical` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/ROOTLINE_AGENTIC_DEVICE_MANAGEMENT_PLAN.md` | 92 | `af7148a884fa` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 5 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/ROOTLINE_AUGUST1_ESSENTIAL_WATER_PLAN.md` | 27 | `e23364178269` | `historical` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/ROOTLINE_C12345_CANARY_PREFLIGHT.md` | 154 | `1d0f448402af` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/ROOTLINE_CANONICAL_STATUS_AND_OWNER_ACCESS_RECOVERY_20260811.md` | 102 | `5903318d8c49` | `historical` | `historical` | `extract_then_archive_or_delete` | 4 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/ROOTLINE_EWELINK_OAUTH_ONBOARDING.md` | 63 | `b73b74139b60` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/ROOTLINE_OPERATING_KNOWLEDGE_REGISTER.md` | 135 | `6fff91fdb521` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 3 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/ROOTLINE_OPERATING_POLICY_REVIEW.md` | 185 | `a02e6113f1c2` | `superseded` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/ROOTLINE_PHASE_B_HARDWARE_INVENTORY.md` | 375 | `f71931ec03cf` | `authoritative` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/ROOTLINE_REMAINING_COMMISSIONING_PACKETS_20260818.md` | 25 | `acf2af2defe2` | `active` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/ROOTLINE_SONOFF_IRRIGATION_EXECUTION_CONTRACT.md` | 93 | `627db4688f0d` | `active` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/ROOTLINE_SPECIALIST_RESULT_CONTRACT.md` | 127 | `e2465ea17fd1` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/ROOTLINE_WATER_ENERGY_MANAGER_PHASE1.md` | 91 | `6d6a0cf6d7bc` | `historical` | `review_queue` | `split_active_runbook_from_history` | 1 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/RUNBOOK.md` | 13 | `9f23c9069816` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 3 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/SAM_BEACON_MEAT_FIRST_LAUNCH_READINESS_2026-07-03.md` | 136 | `f5d13714c324` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 0 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/SAM_INBOX_RECONCILIATION_TIMEOUT_HANDOVER.md` | 35 | `601289f493be` | `authoritative` | `historical` | `extract_then_archive_or_delete` | 2 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/SAM_LIVE_STOCK_COMPLETION_PROGRAM.md` | 49 | `f25525de59ac` | `historical` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/SAM_MANAGER_SUMMARY_PR691_HANDOVER.md` | 52 | `921af627f609` | `unspecified` | `historical` | `extract_then_archive_or_delete` | 0 | no | operational evidence/status should not remain discoverable doctrine |
| `docs/06-operations/SAM_MEAT_INTAKE_LIVE_SMOKE_CHECKLIST.md` | 132 | `52bcacb18196` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 2 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/TESTING_CHECKLIST.md` | 2170 | `930d6d617c72` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 7 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/TROUBLESHOOTING.md` | 14 | `31ac9b9e4b32` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 3 | no | mixed runbook, policy and evidence directory |
| `docs/06-operations/goals/README.md` | 15 | `a37e2504a76a` | `unspecified` | `review_queue` | `split_active_runbook_from_history` | 63 | no | mixed runbook, policy and evidence directory |
| `docs/07-decisions/ADR_0001_DOCUMENTATION_SOURCE_OF_TRUTH.md` | 22 | `749bff6d16f0` | `superseded` | `review_queue` | `classify_manually` | 1 | no | no safe automatic lifecycle conclusion |
| `docs/07-decisions/ADR_0002_CHARLIE_CORE_TERMINOLOGY_AND_CONFIGURATION.md` | 40 | `6cbf511a450a` | `historical` | `review_queue` | `classify_manually` | 1 | no | no safe automatic lifecycle conclusion |
| `docs/07-decisions/README.md` | 14 | `449c42f5ffed` | `unspecified` | `review_queue` | `classify_manually` | 63 | no | no safe automatic lifecycle conclusion |
| `docs/08-business-modules/FARM_CALENDAR_PLAN.md` | 201 | `4f8340310aa8` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 3 | no | agent/business doctrine must move exclusively to Vault |
| `docs/08-business-modules/MEAT_LAUNCH_CAMPAIGN_PACKET.md` | 176 | `fc564e120753` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 12 | no | agent/business doctrine must move exclusively to Vault |
| `docs/08-business-modules/MEAT_PRODUCTION_BATCH_WORKFLOW.md` | 70 | `4bc66af794e8` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 5 | no | agent/business doctrine must move exclusively to Vault |
| `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md` | 401 | `660e91169015` | `active` | `review_queue` | `consolidate_then_archive_or_delete` | 21 | no | agent/business doctrine must move exclusively to Vault |
| `docs/08-business-modules/MEAT_SALES_STRESS_TEST_REPORT.md` | 64 | `90ce6eb5549d` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 1 | no | agent/business doctrine must move exclusively to Vault |
| `docs/08-business-modules/MEAT_SALES_WHATSAPP_TEMPLATES.md` | 40 | `bd17fa51bb19` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 5 | no | agent/business doctrine must move exclusively to Vault |
| `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md` | 337 | `1698bd8bcc8b` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 19 | no | agent/business doctrine must move exclusively to Vault |
| `docs/08-business-modules/PORK_SALES_MODEL.md` | 7082 | `d3a8dd94a9f0` | `historical` | `review_queue` | `consolidate_then_archive_or_delete` | 22 | no | agent/business doctrine must move exclusively to Vault |
| `docs/08-business-modules/README.md` | 19 | `1d067bb6105e` | `active` | `review_queue` | `consolidate_then_archive_or_delete` | 63 | no | agent/business doctrine must move exclusively to Vault |
| `docs/08-business-modules/SAM_FARM_KNOWLEDGE_PACK.md` | 102 | `48424e16bcf9` | `unspecified` | `review_queue` | `consolidate_then_archive_or_delete` | 9 | no | agent/business doctrine must move exclusively to Vault |
| `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md` | 1035 | `d5e965c95c15` | `historical` | `historical` | `archive_or_delete_review` | 34 | no | non-current material inside live Vault |
| `docs/09-vault-brain/00-governance/BEACON_ACTIVATION_TIMEOUT_HANDOVER_2026-07-29.md` | 147 | `7e03e789e571` | `authoritative` | `authoritative` | `keep_review` | 0 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/BEACON_BMQ_20260813_02_HANDOVER.md` | 122 | `f233ee766944` | `unspecified` | `active` | `keep_review` | 0 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/BEACON_BMQ_20260813_03_HANDOVER.md` | 91 | `eb786c0b9996` | `unspecified` | `active` | `keep_review` | 0 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/BEACON_BMQ_20260813_04_HANDOVER.md` | 123 | `a6acb98c2982` | `historical` | `historical` | `archive_or_delete_review` | 0 | no | non-current material inside live Vault |
| `docs/09-vault-brain/00-governance/BEACON_HANDOVER_2026-07-27.md` | 68 | `d8c00d10c12c` | `authoritative` | `authoritative` | `keep_review` | 0 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/BEACON_MARKETING_PROPOSAL_HANDOVER_2026-07-29.md` | 75 | `f9e0748676f8` | `unspecified` | `active` | `keep_review` | 0 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/BEACON_TRUSTED_SERVER_READBACK_CORRECTION_HANDOVER_2026-08-01.md` | 84 | `3cb53212efdc` | `authoritative` | `authoritative` | `keep_review` | 0 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/BRAIN_GUARD.md` | 116 | `233bbdff44aa` | `unspecified` | `active` | `keep_review` | 31 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/CONTROL_TOWER_ASSESSMENT_AND_DISPATCH_PROTOCOL.md` | 319 | `dbc88934c434` | `controlling` | `authoritative` | `keep_review` | 14 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/DOCUMENT_LIFECYCLE_AND_LEGACY_RETIREMENT_STANDARD.md` | 101 | `756181255df4` | `quarantined` | `quarantined` | `archive_or_delete_review` | 13 | no | non-current material inside live Vault |
| `docs/09-vault-brain/00-governance/HERDMASTER_AUCTION_HANDOVER_2026-07-27.md` | 179 | `9aa2b8757913` | `unspecified` | `active` | `keep_review` | 0 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/OPEN_QUESTIONS.md` | 167 | `a3158657d771` | `unspecified` | `active` | `keep_review` | 5 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/OWNER_DECISIONS.md` | 107 | `02d57c7b4b29` | `active` | `active` | `keep_review` | 6 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/REVIEW_AND_APPROVAL_RULES.md` | 22 | `bee023f5198a` | `unspecified` | `active` | `keep_review` | 5 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md` | 28 | `04310ce1d226` | `active` | `active` | `keep_review` | 25 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/UPDATE_RULES.md` | 46 | `723a9eaf2740` | `authoritative` | `authoritative` | `keep_review` | 15 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/00-governance/VAULT_READINESS_SCORECARD.md` | 55 | `64f533fd0b26` | `historical` | `historical` | `archive_or_delete_review` | 1 | no | non-current material inside live Vault |
| `docs/09-vault-brain/01-identity/AGENT_ORGANOGRAM.md` | 86 | `3d7a36937cd3` | `unspecified` | `active` | `keep_review` | 10 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/01-identity/CHARLIE.md` | 82 | `66d95ce19489` | `active` | `active` | `keep_review` | 20 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/01-identity/CHARLIE_CORE.md` | 165 | `0e576919f4e6` | `unspecified` | `active` | `keep_review` | 32 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/01-identity/OOM_SAKKIE.md` | 75 | `aabd1ed11536` | `active` | `active` | `keep_review` | 12 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/01-identity/OWNER_CHARL.md` | 58 | `1b603fda6297` | `unspecified` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/01-identity/SYSTEM_HIERARCHY.md` | 30 | `f6eb986fd4d3` | `active` | `active` | `keep_review` | 12 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/AGENT_REGISTRY.md` | 106 | `2f19e4fc3e3e` | `active` | `active` | `keep_review` | 29 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/README.md` | 31 | `3c7a6449aa9a` | `unspecified` | `active` | `keep_review` | 63 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/_AGENT_TEMPLATE.md` | 83 | `c234107362e6` | `unspecified` | `active` | `keep_review` | 5 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/ARCHITECT.md` | 24 | `c85340b66b60` | `unspecified` | `active` | `keep_review` | 9 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/BRAIN_GUARD.md` | 45 | `f6c3be41bf56` | `active` | `active` | `keep_review` | 19 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/BUILDER.md` | 29 | `ac80624a6d6a` | `unspecified` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/BUSINESS_MODEL_AGENT.md` | 29 | `c3a660fd01a4` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/BUSINESS_REVIEWER.md` | 26 | `f6f984a03656` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/CONCEPT_STRATEGIST.md` | 29 | `79d6a17eae67` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/COUNCIL_SYNTHESIS.md` | 30 | `8ceb9bf4339f` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/CREATIVE_UI_DESIGNER.md` | 48 | `368989e1d310` | `active` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/EVIDENCE_REVIEWER.md` | 27 | `0ecd186b7c2b` | `unspecified` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/FRONTEND_DESIGN_IMPLEMENTER.md` | 51 | `dfe4537bd3dc` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/IDEA_EXPANDER.md` | 44 | `2967e2e87c70` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/IMPROVEMENT_ANALYST.md` | 61 | `bfa92e20e2f0` | `unspecified` | `active` | `keep_review` | 2 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/PLANNER.md` | 25 | `645810b6e789` | `unspecified` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/PRODUCT_ARCHITECT.md` | 43 | `0bdc142e21ee` | `unspecified` | `active` | `keep_review` | 5 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/PRODUCT_REVIEWER.md` | 27 | `4fdaf9aa3c82` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/PUBLISHER.md` | 28 | `3b59b7bb9b61` | `unspecified` | `active` | `keep_review` | 5 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/QA_RED_TEAM.md` | 33 | `b7831f85d2d0` | `unspecified` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/REVIEWER.md` | 25 | `0370d3f4b51d` | `unspecified` | `active` | `keep_review` | 16 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/RISK_AGENT.md` | 40 | `6babeeca50db` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/SECURITY_REVIEWER.md` | 27 | `8eb6c1b7a7ea` | `unspecified` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/SOURCE_MAPPER.md` | 47 | `66e6d5a8173b` | `active` | `active` | `keep_review` | 5 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/TECHNICAL_ARCHITECT.md` | 44 | `aaa05430f618` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/TESTER.md` | 24 | `7f1389998c88` | `active` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/UX_INTERACTION_DESIGNER.md` | 46 | `15071c9a8ec8` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/VISUAL_QA_REVIEWER.md` | 48 | `a6e4703a6568` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/charlie-core/VISUAL_REFERENCE_INTERPRETER.md` | 46 | `0c5c16ab2b3c` | `active` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/farm/GATEKEEPER.md` | 9 | `2e3398d26a6f` | `unspecified` | `active` | `keep_review` | 6 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/farm/HERDMASTER.md` | 80 | `7d4a743efae2` | `historical` | `historical` | `archive_or_delete_review` | 22 | no | non-current material inside live Vault |
| `docs/09-vault-brain/02-agents/farm/OOM_SAKKIE.md` | 113 | `1f2edf989d76` | `unspecified` | `active` | `keep_review` | 17 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/farm/QUARTERMASTER.md` | 37 | `8408440fa9bf` | `unspecified` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/farm/ROOTLINE.md` | 105 | `89af459a49df` | `unspecified` | `active` | `keep_review` | 11 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/marketing/BEACON.md` | 115 | `ba62fcfc8715` | `active` | `active` | `keep_review` | 19 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/marketing/BEACON_CREATIVE.md` | 7 | `00ad6bcaee48` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/marketing/BEACON_MEDIA_LIBRARIAN.md` | 31 | `08dcc750f50d` | `historical` | `historical` | `archive_or_delete_review` | 3 | no | non-current material inside live Vault |
| `docs/09-vault-brain/02-agents/marketing/BEACON_PERFORMANCE_ANALYST.md` | 7 | `5a094f503efe` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/marketing/BEACON_STRATEGY.md` | 7 | `075f9320fdff` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/owner-command/CHARLIE.md` | 67 | `d9b8b313c199` | `authoritative` | `authoritative` | `keep_review` | 14 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/sales/BUTCHER.md` | 13 | `1a1111966949` | `unspecified` | `active` | `keep_review` | 8 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/sales/BUTCHER_CUSTOM_CUTS_SALES_AGENT.md` | 9 | `34fe3ac7b308` | `unspecified` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/sales/LEDGER.md` | 9 | `e54e8a4f4849` | `unspecified` | `active` | `keep_review` | 8 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/sales/LIVE_PIG_SALES_AGENT.md` | 99 | `30a035584315` | `active` | `active` | `keep_review` | 26 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/sales/MEAT_SALES_AGENT.md` | 23 | `ca446d47f65c` | `unspecified` | `active` | `keep_review` | 8 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/sales/SAM.md` | 124 | `b4eea495f20c` | `quarantined` | `quarantined` | `archive_or_delete_review` | 44 | no | non-current material inside live Vault |
| `docs/09-vault-brain/02-agents/sales/SAM_MEAT_PERSONALITY.md` | 90 | `1014673a8413` | `active` | `active` | `keep_review` | 16 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/sales/SLAUGHTER_ABATTOIR_SALES_AGENT.md` | 9 | `d9a6aef467cd` | `unspecified` | `active` | `keep_review` | 2 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/02-agents/transport/FRED.md` | 50 | `43095a355cd9` | `unspecified` | `active` | `keep_review` | 7 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/03-business/AMADEUS_FARM.md` | 52 | `7c99d730bf8c` | `retired` | `retired` | `archive_or_delete_review` | 3 | no | non-current material inside live Vault |
| `docs/09-vault-brain/03-business/AMADEUS_MEAT_CUTTING_AND_COMMERCIAL_STANDARD.md` | 165 | `a20e3ae4f909` | `historical` | `historical` | `archive_or_delete_review` | 16 | no | non-current material inside live Vault |
| `docs/09-vault-brain/03-business/AMADEUS_PRIVATE_TRANSFERS.md` | 186 | `226b1910bd45` | `unspecified` | `active` | `keep_review` | 15 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/03-business/BEACON_MARKETING.md` | 41 | `9e158c9342d9` | `superseded` | `superseded` | `archive_or_delete_review` | 13 | no | non-current material inside live Vault |
| `docs/09-vault-brain/03-business/FUTURE_BUSINESS_IDEAS.md` | 11 | `0855834feab8` | `unspecified` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/03-business/LIVE_PIG_SALES.md` | 48 | `a65b3ef884cd` | `unspecified` | `active` | `keep_review` | 29 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/03-business/MEAT_SALES.md` | 155 | `0936ce1ef13b` | `active` | `active` | `keep_review` | 21 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/03-business/README.md` | 5 | `8140e250c9d8` | `unspecified` | `active` | `keep_review` | 66 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/03-business/SLAUGHTER_ABATTOIR_SALES.md` | 9 | `19d85dd8afa9` | `unspecified` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/03-business/_BUSINESS_TEMPLATE.md` | 23 | `3375474cf54f` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/BEACON_CAMPAIGN_WORKFLOW.md` | 77 | `25db8c1ad82f` | `superseded` | `superseded` | `archive_or_delete_review` | 8 | no | non-current material inside live Vault |
| `docs/09-vault-brain/04-workflows/BEACON_LIVE_STOCK_AWARENESS_WORKFLOW.md` | 98 | `6035d0782c87` | `unspecified` | `active` | `keep_review` | 10 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/BEACON_MEDIA_INTAKE_WORKFLOW.md` | 212 | `998f4bcdfbc3` | `unspecified` | `active` | `keep_review` | 8 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md` | 287 | `5b6345accdbe` | `authoritative` | `authoritative` | `keep_review` | 46 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/HERDMASTER_BREEDING_ATTENTION_WORKFLOW.md` | 251 | `9f65c331287d` | `historical` | `historical` | `archive_or_delete_review` | 3 | no | non-current material inside live Vault |
| `docs/09-vault-brain/04-workflows/HERDMASTER_NATURAL_HEALTH_AND_LOSS_INTAKE_WORKFLOW.md` | 133 | `f80fb3d6fe70` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/HERDMASTER_PURPOSE_REVIEW_WORKFLOW.md` | 9 | `66a08c39b372` | `unspecified` | `active` | `keep_review` | 8 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/N8N_WORKFLOW_SUITE.md` | 72 | `9fc5afe3d83e` | `transitional` | `active` | `keep_review` | 14 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/OOM_SAKKIE_OWNER_ATTENTION_QUEUE_WORKFLOW.md` | 108 | `db8974eb9f57` | `authoritative` | `authoritative` | `keep_review` | 6 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/OWNER_REVIEW_WORKFLOW.md` | 13 | `149e85d27b2a` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/README.md` | 18 | `af6984739a53` | `unspecified` | `active` | `keep_review` | 63 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/RELEASE_WORKFLOW.md` | 9 | `a54bce664be8` | `unspecified` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/ROOTLINE_CONTROL_ARCHITECTURE.md` | 288 | `9d7ce73cb99e` | `historical` | `historical` | `archive_or_delete_review` | 19 | no | non-current material inside live Vault |
| `docs/09-vault-brain/04-workflows/SAM_GENERAL_CONVERSATION.md` | 112 | `84501a10378a` | `unspecified` | `active` | `keep_review` | 22 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_CONTEXTUAL_SALES_WORKFLOW.md` | 146 | `489f6e00c6b7` | `unspecified` | `active` | `keep_review` | 0 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md` | 275 | `b002f54d1575` | `unspecified` | `active` | `keep_review` | 48 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md` | 96 | `ebf243c9acb9` | `unspecified` | `active` | `keep_review` | 35 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/SAM_SALES_AUTONOMY_LEVEL_1.md` | 94 | `59476f34fe51` | `unspecified` | `active` | `keep_review` | 0 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/SEND_BACK_WORKFLOW.md` | 9 | `8df1a2223725` | `unspecified` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/SUPABASE_MIGRATION_WORKFLOW.md` | 12 | `2d3a98d3aae4` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/04-workflows/_WORKFLOW_TEMPLATE.md` | 21 | `af32898c5f77` | `unspecified` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/05-playbooks/AGENT_BUILD.md` | 18 | `06d6d7ad8af3` | `unspecified` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/05-playbooks/BUGFIX.md` | 17 | `9d30b63c64b7` | `unspecified` | `active` | `keep_review` | 0 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/05-playbooks/DASHBOARD_UI.md` | 27 | `7d9c7115fab4` | `active` | `active` | `keep_review` | 0 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/05-playbooks/DATA_MIGRATION.md` | 30 | `56e18bf8983a` | `unspecified` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/05-playbooks/FEATURE_BUILD.md` | 31 | `1b3dc1121369` | `unspecified` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/05-playbooks/INCOME_STREAM.md` | 29 | `07904456b2bf` | `unspecified` | `active` | `keep_review` | 10 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/05-playbooks/LIVE_OPERATIONS_FIX.md` | 31 | `c714425efcfe` | `active` | `active` | `keep_review` | 8 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/05-playbooks/MARKETING_CAMPAIGN.md` | 5 | `b07a471b198e` | `unspecified` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/05-playbooks/SAM_LIVE_STOCK_HUMAN_SALES_PLAYBOOK.md` | 125 | `9d54323f66da` | `active` | `active` | `keep_review` | 18 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/05-playbooks/SAM_MEAT_HUMAN_SALES_PLAYBOOK.md` | 136 | `e66d1b256bf5` | `active` | `active` | `keep_review` | 20 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/06-data/BEACON_DATA_MODEL.md` | 60 | `2e71280a4d3c` | `unspecified` | `active` | `keep_review` | 0 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/06-data/BRAIN_AND_MEMORY_V2.md` | 190 | `5e94547d21af` | `unspecified` | `active` | `keep_review` | 11 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/06-data/CHARLIE_VAULT_TABLES.md` | 26 | `0bac871b67e9` | `unspecified` | `active` | `keep_review` | 2 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/06-data/FARM_DATA_MODEL.md` | 84 | `b304c2b5efd9` | `active` | `active` | `keep_review` | 27 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/06-data/GOOGLE_SHEETS_LEGACY.md` | 42 | `08229ef24c1e` | `unspecified` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/06-data/MEAT_SALES_DATA_MODEL.md` | 5 | `5c54e3f1596d` | `unspecified` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/06-data/ORDER_DATA_MODEL.md` | 76 | `beb9b79b7bcd` | `active` | `active` | `keep_review` | 14 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/06-data/README.md` | 7 | `d8fc49e36398` | `unspecified` | `active` | `keep_review` | 63 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/06-data/SUPABASE_CONTRACTS.md` | 103 | `85b4fb7262ef` | `active` | `active` | `keep_review` | 5 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/06-data/TELEMETRY_DATA_MODEL.md` | 65 | `dae58969b044` | `unspecified` | `active` | `keep_review` | 2 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/AGENTIC_ARCHITECTURE_STANDARD.md` | 56 | `7d5b28e397c3` | `authoritative` | `authoritative` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/AGENT_AUTHORITY_MATRIX.md` | 46 | `f5a9c2d6bb30` | `active` | `active` | `keep_review` | 11 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/AMADEUS_FARM_UI_FACELIFT_STANDARD.md` | 118 | `1f4dc4cf99e2` | `authoritative` | `authoritative` | `keep_review` | 2 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/CHANNEL_INVARIANT_CANONICAL_ACTION_STANDARD.md` | 104 | `dcb6d62eb57d` | `unspecified` | `active` | `keep_review` | 13 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md` | 108 | `141bb0ddb0a5` | `authoritative` | `authoritative` | `keep_review` | 29 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/CUSTOMER_RESPONSE_STANDARD.md` | 31 | `79b7005ffc00` | `unspecified` | `active` | `keep_review` | 2 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md` | 37 | `82212b583d63` | `unspecified` | `active` | `keep_review` | 10 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md` | 105 | `d0f34c7b744f` | `unspecified` | `active` | `keep_review` | 40 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/OOM_SAKKIE_TELEGRAM_MESSAGE_STANDARD.md` | 57 | `8d8fbba79e5d` | `active` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md` | 204 | `711faa17e5d3` | `unspecified` | `active` | `keep_review` | 27 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/SECURITY_AND_SECRETS_STANDARD.md` | 30 | `5a4149e91854` | `unspecified` | `active` | `keep_review` | 10 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/TESTING_STANDARD.md` | 62 | `358a5006b372` | `unspecified` | `active` | `keep_review` | 32 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md` | 80 | `f65168fd2804` | `active` | `active` | `keep_review` | 27 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/08-business-rules/AMADEUS_FARM_PUBLIC_KNOWLEDGE.md` | 88 | `853cd76dc5bc` | `unspecified` | `active` | `keep_review` | 2 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/08-business-rules/FARM_RULES.md` | 5 | `f4d34aebb3ff` | `unspecified` | `active` | `keep_review` | 6 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/08-business-rules/HERDMASTER_GENETIC_SELECTION_RULES.md` | 130 | `7098dae46c68` | `unspecified` | `active` | `keep_review` | 13 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md` | 154 | `65aa9dec4c56` | `active` | `active` | `keep_review` | 18 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/08-business-rules/LEGAL_AND_POPIA_REVIEW.md` | 11 | `db718167ec2c` | `unspecified` | `active` | `keep_review` | 4 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md` | 152 | `c5e4350227dc` | `active` | `active` | `keep_review` | 28 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/08-business-rules/MARKETING_RULES.md` | 17 | `108787fc68eb` | `superseded` | `superseded` | `archive_or_delete_review` | 8 | no | non-current material inside live Vault |
| `docs/09-vault-brain/08-business-rules/MEAT_PRODUCTION_RULES.md` | 30 | `0eac44e19498` | `unspecified` | `active` | `keep_review` | 6 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/08-business-rules/MEAT_SALES_RULES.md` | 77 | `bfbdd5ce540f` | `retired` | `retired` | `archive_or_delete_review` | 20 | no | non-current material inside live Vault |
| `docs/09-vault-brain/08-business-rules/MEDIA_PRIVACY_RULES.md` | 18 | `d483e5d3dd88` | `unspecified` | `active` | `keep_review` | 10 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/08-business-rules/PAYMENT_RULES.md` | 27 | `87ea22ee7288` | `unspecified` | `active` | `keep_review` | 10 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md` | 61 | `ce3e1fe47ae1` | `active` | `active` | `keep_review` | 18 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/08-business-rules/ROOTLINE_WATER_ENERGY_RULES.md` | 430 | `4b85ae0c597e` | `controlling` | `authoritative` | `keep_review` | 5 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/08-business-rules/TRANSPORT_RULES.md` | 33 | `baef9dd256ae` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/09-examples/GOLD_STANDARD_AGENT_CHARTER.md` | 3 | `a4ad0f29f6f8` | `unspecified` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/09-examples/GOLD_STANDARD_BUSINESS_PLAN.md` | 3 | `49c4c77666ae` | `unspecified` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/09-examples/GOLD_STANDARD_DASHBOARD.md` | 10 | `d0585018dcab` | `active` | `active` | `keep_review` | 11 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/09-examples/GOLD_STANDARD_LITTER_DETAIL_PR90.md` | 57 | `23d6ad9bdd47` | `active` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/09-examples/GOLD_STANDARD_LITTER_SUMMARY_PR89.md` | 48 | `f3e67ae7c076` | `active` | `active` | `keep_review` | 9 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/09-examples/GOLD_STANDARD_MISSION.md` | 3 | `2591edf41443` | `unspecified` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/09-examples/GOLD_STANDARD_RECOVERY_PACKET.md` | 45 | `4b741a362663` | `active` | `active` | `keep_review` | 11 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/09-examples/GOLD_STANDARD_REVIEW_PACKET.md` | 5 | `32ef4426b1cd` | `unspecified` | `active` | `keep_review` | 3 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/09-examples/README.md` | 18 | `1326cf51a21a` | `active` | `active` | `keep_review` | 64 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/09-examples/SAM_LIVE_STOCK_GOLD_STANDARD_REPLIES.md` | 175 | `6259dca3aae3` | `unspecified` | `active` | `keep_review` | 20 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/09-examples/SAM_MEAT_GOLD_STANDARD_REPLIES.md` | 91 | `ec4f94b6f2fc` | `active` | `active` | `keep_review` | 19 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md` | 110 | `8e83fbc9450b` | `historical` | `historical` | `archive_or_delete_review` | 8 | no | non-current material inside live Vault |
| `docs/09-vault-brain/10-source-map/ARCHIVE_REVIEW_QUEUE.md` | 29 | `8f2314cbfcbe` | `superseded` | `superseded` | `archive_or_delete_review` | 1 | no | non-current material inside live Vault |
| `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md` | 861 | `f8db2cea1760` | `historical` | `historical` | `archive_or_delete_review` | 10 | no | non-current material inside live Vault |
| `docs/09-vault-brain/10-source-map/MIGRATION_NOTES.md` | 11 | `bfeb0963d73d` | `active` | `active` | `keep_review` | 1 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/10-source-map/README.md` | 12 | `c50e66fe4365` | `superseded` | `superseded` | `archive_or_delete_review` | 63 | no | non-current material inside live Vault |
| `docs/09-vault-brain/10-source-map/REPO_CLEANUP_STATUS.md` | 45 | `c29a51e1c960` | `superseded` | `superseded` | `archive_or_delete_review` | 2 | no | non-current material inside live Vault |
| `docs/09-vault-brain/10-source-map/VAULT_MIGRATION_INVENTORY.md` | 65 | `a8098b469a73` | `active` | `active` | `keep_review` | 6 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/CHANGELOG.md` | 1449 | `fda7b72570d2` | `unspecified` | `active` | `keep_review` | 10 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/INDEX.md` | 95 | `fea7f39eff66` | `unspecified` | `active` | `keep_review` | 44 | no | current Vault candidate requires owner/agent audit |
| `docs/09-vault-brain/README.md` | 50 | `4bbd24076869` | `controlling` | `authoritative` | `keep_review` | 65 | no | current Vault candidate requires owner/agent audit |
| `docs/99-archive/README.md` | 16 | `78204fda1532` | `active` | `historical` | `keep_archive` | 63 | no | already isolated archive evidence |
| `docs/99-archive/legacy/README.md` | 5 | `dc2cc1a2b176` | `historical` | `historical` | `keep_archive` | 63 | no | already isolated archive evidence |
| `docs/99-archive/legacy/planning_CHAT_2026-04_n8n_sales_agent_rewire.md` | 2634 | `0f62c29b83f1` | `unspecified` | `historical` | `keep_archive` | 18 | no | already isolated archive evidence |
| `docs/99-archive/old-prompts/2026-06/CHARLIE_CORE_MASTER_PLAN_AND_CURSOR_PROMPT.md` | 1113 | `bb076a2a0443` | `unspecified` | `historical` | `keep_archive` | 0 | no | already isolated archive evidence |
| `docs/99-archive/old-prompts/2026-06/CHARLIE_CURSOR_PLANNING_PROMPT_ONLY.md` | 266 | `cea3bcfc57ed` | `unspecified` | `historical` | `keep_archive` | 0 | no | already isolated archive evidence |
| `docs/99-archive/old-prompts/2026-06/CHARLIE_CURSOR_PLAN_REVIEW_AND_APPROVAL_PROMPT.md` | 470 | `d7f472f7747e` | `unspecified` | `historical` | `keep_archive` | 0 | no | already isolated archive evidence |
| `docs/99-archive/old-prompts/2026-06/CURSOR_SINGLE_TERMINAL_RESET_PROMPT.md` | 75 | `b720c3f1b9b2` | `active` | `historical` | `keep_archive` | 0 | no | already isolated archive evidence |
| `docs/99-archive/old-prompts/2026-06/README.md` | 7 | `b0dbce79a6ef` | `historical` | `historical` | `keep_archive` | 63 | no | already isolated archive evidence |
| `docs/99-archive/old-prompts/README.md` | 5 | `ea41d09661dd` | `active` | `historical` | `keep_archive` | 63 | no | already isolated archive evidence |
| `docs/99-archive/old-screenshots-index.md` | 14 | `dec2248fda6d` | `active` | `historical` | `keep_archive` | 2 | no | already isolated archive evidence |
| `docs/99-archive/reports/2026-06/CHARLIE_ACTIVE_HANDOVER.md` | 420 | `3faea270c83e` | `active` | `historical` | `keep_archive` | 2 | no | already isolated archive evidence |
| `docs/99-archive/reports/2026-06/OVERNIGHT_DEBRIEF_2026-06-28.md` | 222 | `365e2efaf650` | `unspecified` | `historical` | `keep_archive` | 0 | no | already isolated archive evidence |
| `docs/99-archive/reports/2026-06/README.md` | 7 | `e9061c45b046` | `historical` | `historical` | `keep_archive` | 63 | no | already isolated archive evidence |
| `docs/99-archive/reports/README.md` | 5 | `5e3fc736f5db` | `active` | `historical` | `keep_archive` | 63 | no | already isolated archive evidence |
| `docs/99-archive/superseded/README.md` | 5 | `0e2451783edc` | `superseded` | `historical` | `keep_archive` | 63 | no | already isolated archive evidence |
| `docs/MIGRATION_INDEX.md` | 42 | `419b8f8475ae` | `unspecified` | `review_queue` | `classify_manually` | 0 | no | no safe automatic lifecycle conclusion |
| `external_sources/AMADEUS_HALF_CARCASS_CUTTING_STANDARD_v1.0.md` | 607 | `fa120f07df46` | `unspecified` | `review_queue` | `archive_or_delete_review` | 16 | no | external context is never doctrine without promotion |
| `external_sources/CODEX_FARM_UI_RESET_BRIEF.md` | 221 | `bbfe36875697` | `unspecified` | `review_queue` | `archive_or_delete_review` | 0 | no | external context is never doctrine without promotion |
| `external_sources/CODEX_FARM_UI_TARGET_SPECIALIST_WORKSPACE_BRIEF.md` | 375 | `7cd483ed5377` | `unspecified` | `review_queue` | `archive_or_delete_review` | 0 | no | external context is never doctrine without promotion |
| `external_sources/README.md` | 20 | `f8b9365f4bd7` | `unspecified` | `review_queue` | `archive_or_delete_review` | 63 | no | external context is never doctrine without promotion |
| `external_sources/telemetry/forecast/amadeus-forecast-logger/README.md` | 29 | `63567fbfe8f6` | `active` | `review_queue` | `archive_or_delete_review` | 63 | no | external context is never doctrine without promotion |
| `external_sources/telemetry/sunsynk/amadeus-sunsynk-logger/README.md` | 23 | `99c682a29fe3` | `unspecified` | `review_queue` | `archive_or_delete_review` | 64 | no | external context is never doctrine without promotion |
| `planning/CHARLIE_CORE_EXTENDED_PLAN.md` | 1225 | `6770c7ae94ff` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 2 | no | working material must not steer agent missions |
| `planning/CODEX_CHAT.md` | 185 | `b7d708fe0bb6` | `active` | `review_queue` | `extract_then_archive_or_delete` | 128 | no | working material must not steer agent missions |
| `planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md` | 643 | `e2d239b37d6d` | `active` | `review_queue` | `extract_then_archive_or_delete` | 8 | no | working material must not steer agent missions |
| `planning/ToDoList.md` | 45 | `4a9f0a97fb73` | `active` | `review_queue` | `extract_then_archive_or_delete` | 40 | no | working material must not steer agent missions |
| `planning/inbox/README.md` | 23 | `44f0e8f7283e` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 63 | no | working material must not steer agent missions |
| `planning/inbox/processed/2026-06/ToDoList_2026-06-28_operational_notes.md` | 21 | `5eb0c8b965c2` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 2 | no | working material must not steer agent missions |
| `planning/inbox/processed/2026-06/ToDoList_2026-06-30_live_app_review_notes.md` | 27 | `8e5f7ef67bb9` | `active` | `review_queue` | `extract_then_archive_or_delete` | 2 | no | working material must not steer agent missions |
| `planning/inbox/prompts/REPO_CLEANUP_AND_DOCS_GOVERNANCE_PROMPT.md` | 341 | `0a21aba2c4f2` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 0 | no | working material must not steer agent missions |
| `planning/storyworks/BUSINESS_STATE_LADDER.md` | 99 | `201e8d37d24b` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 9 | no | working material must not steer agent missions |
| `planning/storyworks/CHRONICLE_VAULT_CHANNEL_BIBLE.md` | 79 | `61c46e0c316d` | `historical` | `review_queue` | `extract_then_archive_or_delete` | 4 | no | working material must not steer agent missions |
| `planning/storyworks/DECISION_LOG.md` | 14 | `2660e59ae572` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 1 | no | working material must not steer agent missions |
| `planning/storyworks/MARKET_VALIDATION.md` | 109 | `55cdda48ff28` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 1 | no | working material must not steer agent missions |
| `planning/storyworks/PHASE_0_EXECUTIVE_DECISION_PACK.md` | 120 | `cdfbd554e964` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 4 | no | working material must not steer agent missions |
| `planning/storyworks/PHASE_0_VALIDATION_PLAN.md` | 100 | `934a340ca992` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 4 | no | working material must not steer agent missions |
| `planning/storyworks/PILOT_SCORECARD.md` | 58 | `96791d385865` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 1 | no | working material must not steer agent missions |
| `planning/storyworks/PRODUCTION_PLAYBOOK.md` | 61 | `82fe03c8fe4b` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 3 | no | working material must not steer agent missions |
| `planning/storyworks/README.md` | 51 | `007369ed3a1b` | `authoritative` | `review_queue` | `extract_then_archive_or_delete` | 66 | no | working material must not steer agent missions |
| `planning/storyworks/RIGHTS_AND_PROVENANCE_POLICY.md` | 45 | `a5aeab09fd3e` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 1 | no | working material must not steer agent missions |
| `planning/storyworks/STATUS.md` | 44 | `8032799226db` | `active` | `review_queue` | `extract_then_archive_or_delete` | 13 | no | working material must not steer agent missions |
| `planning/storyworks/STORYWORKS_BUSINESS_CHARTER.md` | 86 | `de888d13513a` | `authoritative` | `review_queue` | `extract_then_archive_or_delete` | 5 | no | working material must not steer agent missions |
| `planning/storyworks/UNIT_ECONOMICS.md` | 82 | `83ea67737129` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 4 | no | working material must not steer agent missions |
| `planning/storyworks/YOUTUBE_POLICY_RESEARCH.md` | 68 | `18897fef4b77` | `active` | `review_queue` | `extract_then_archive_or_delete` | 1 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/OWNER_REVIEW_PACKET.md` | 300 | `c9dcc3c19514` | `authoritative` | `review_queue` | `extract_then_archive_or_delete` | 0 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/PREPRODUCTION_DECISION_CANDIDATE.md` | 69 | `4d6e1c0078d6` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 3 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/PRONUNCIATION_REVIEW_SHEET.md` | 39 | `36402bc06fbe` | `historical` | `review_queue` | `extract_then_archive_or_delete` | 3 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/SYNTHETIC_NARRATION_EVALUATION.md` | 41 | `bf1dbeba2008` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 4 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/brief.md` | 48 | `6cc0dd021d2b` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 4 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/copyright_reuse_review.md` | 33 | `6ebbc8b2218a` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 2 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/description.md` | 22 | `812791439b57` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 2 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/disclosure_review.md` | 27 | `31b3b462ba97` | `historical` | `review_queue` | `extract_then_archive_or_delete` | 2 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/edit_plan.md` | 44 | `72f282c99780` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 7 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/fact_check.md` | 34 | `1b5e54705538` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 3 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/measurement_plan.md` | 46 | `0ea022417f28` | `historical` | `review_queue` | `extract_then_archive_or_delete` | 2 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/music_rights.md` | 20 | `c11b00c86d66` | `historical` | `review_queue` | `extract_then_archive_or_delete` | 3 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/narration_plan.md` | 44 | `a60ee3e1343c` | `authoritative` | `review_queue` | `extract_then_archive_or_delete` | 3 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/packaging.md` | 55 | `9ffeb3e9869f` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 3 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/prototypes/QA.md` | 32 | `cf541ab102ee` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 4 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/qa_report.md` | 42 | `f2b737e8b517` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 3 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/rights_evidence_index.md` | 25 | `085c19b7ea89` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 11 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/script.md` | 212 | `fad809cb5904` | `unspecified` | `review_queue` | `extract_then_archive_or_delete` | 15 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/sources.md` | 88 | `c3e856001c6f` | `historical` | `review_queue` | `extract_then_archive_or_delete` | 19 | no | working material must not steer agent missions |
| `planning/storyworks/pilots/petra/time_cost_report.md` | 31 | `1606f5fba390` | `active` | `review_queue` | `extract_then_archive_or_delete` | 2 | no | working material must not steer agent missions |
| `static/assets/agents/beacon/agent.md` | 7 | `cad47c3cc540` | `unspecified` | `runtime_reference` | `generate_or_reconcile` | 16 | no | runtime asset must derive from Vault doctrine |
| `static/assets/agents/butcher/agent.md` | 7 | `c7b340eed725` | `unspecified` | `runtime_reference` | `generate_or_reconcile` | 16 | no | runtime asset must derive from Vault doctrine |
| `static/assets/agents/gatekeeper/agent.md` | 7 | `662ef14224d9` | `unspecified` | `runtime_reference` | `generate_or_reconcile` | 16 | no | runtime asset must derive from Vault doctrine |
| `static/assets/agents/herdmaster/agent.md` | 7 | `6e5215cf8edd` | `unspecified` | `runtime_reference` | `generate_or_reconcile` | 16 | no | runtime asset must derive from Vault doctrine |
| `static/assets/agents/ledger/agent.md` | 7 | `637505753d22` | `unspecified` | `runtime_reference` | `generate_or_reconcile` | 16 | no | runtime asset must derive from Vault doctrine |
| `static/assets/agents/oom-sakkie/agent.md` | 7 | `93f13c410b92` | `unspecified` | `runtime_reference` | `generate_or_reconcile` | 16 | no | runtime asset must derive from Vault doctrine |
| `static/assets/agents/quartermaster/agent.md` | 7 | `a29c948f5d55` | `unspecified` | `runtime_reference` | `generate_or_reconcile` | 16 | no | runtime asset must derive from Vault doctrine |
| `static/assets/agents/rootline/agent.md` | 7 | `5f1df2abc192` | `unspecified` | `runtime_reference` | `generate_or_reconcile` | 16 | no | runtime asset must derive from Vault doctrine |
| `static/assets/agents/sam/agent.md` | 7 | `c8bed7bac373` | `unspecified` | `runtime_reference` | `generate_or_reconcile` | 16 | no | runtime asset must derive from Vault doctrine |
| `supabase/migrations/README.md` | 103 | `9a36ca432f6d` | `unspecified` | `active_reference` | `keep_technical_review` | 67 | no | code-adjacent schema/backend reference; cannot govern agents |

<!-- BATCH1_GENERATED_END -->
