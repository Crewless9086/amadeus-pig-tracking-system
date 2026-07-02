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
| `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md` | migrated + active_reference | `03-business/MEAT_SALES.md`, `08-business-rules/MEAT_SALES_RULES.md`, `04-workflows/SAM_MEAT_SALES_WORKFLOW.md`, `02-agents/sales/SAM.md` | Active launch status and implementation gates remain useful as reference. |
| `docs/08-business-modules/PORK_SALES_MODEL.md` | migrated + active_reference | `03-business/MEAT_SALES.md`, `08-business-rules/MEAT_SALES_RULES.md` | Deep business model, pricing philosophy, loyalty, cold-chain, and open planning questions. |
| `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md` | migrated + active_reference | `03-business/AMADEUS_FARM.md`, `08-business-rules/PIG_PURPOSE_RULES.md` | Allocation/purpose rules and one-pig-one-truth operating principle. |
| `docs/08-business-modules/SAM_FARM_KNOWLEDGE_PACK.md` | migrated + active_reference | `02-agents/sales/SAM.md`, `04-workflows/SAM_MEAT_SALES_WORKFLOW.md` | Runtime knowledge still lives in `config/sam_farm_knowledge.json`. |
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
