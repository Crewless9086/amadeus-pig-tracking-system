# Vault Brain Source Map

## Purpose

This map records where the first Vault Brain pass pulled information from. Brain Guard keeps this current when new documents become authoritative or old documents are superseded.

## Highest-Level Active Sources

| Source | Vault Brain use |
| --- | --- |
| `docs/00-start-here/README.md` | active hierarchy, operating truth, canonical docs |
| `docs/00-start-here/CURRENT_STATE.md` | live state, CHARLIE/SAM/Oom/FRED status, Supabase migration status |
| `docs/00-start-here/WORKFLOW.md` | intake, triage, priority, phase rules, release discipline |
| `docs/00-start-here/DEPLOYMENT_SOP.md` | branch, staging, commit, deploy rules |
| `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md` | mission contract, approval levels, runner/review/release rules |
| `docs/00-start-here/PRODUCT_VISION.md` | Oom Sakkie command room UI/product principles |

## Architecture And Data Sources

| Source | Vault Brain use |
| --- | --- |
| `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md` | source-of-truth model, Supabase direction, operating modules |
| `docs/01-architecture/COMPONENT_OWNERSHIP.md` | layer ownership rule |
| `docs/02-backend/DATA_MODELS.md` | order data contracts |
| `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md` | Supabase foundation gate |
| `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md` | order schema direction |
| `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md` | telemetry/read-model direction |
| `docs/03-google-sheets/WRITE_OWNERSHIP.md` | legacy sheet ownership |
| `docs/03-google-sheets/BUSINESS_RULES.md` | sheet-era farm rules |

## Workflow Sources

| Source | Vault Brain use |
| --- | --- |
| `docs/04-n8n/WORKFLOW_RULES.md` | n8n suite rules and safe modes |
| `docs/04-n8n/DO_NOT_CHANGE.md` | protected workflow fields and behaviors |
| `docs/04-n8n/WORKFLOW_MAP.md` | workflow suite map and Oom Sakkie aliases |
| `docs/04-n8n/CHATWOOT_ATTRIBUTES.md` | Chatwoot label/attribute ownership |
| `docs/04-n8n/workflows/*/README.md` | workflow-specific contracts |

## Agent And Business Sources

| Source | Vault Brain use |
| --- | --- |
| `docs/05-ai/AGENT_ROLES.md` | practical agent boundaries |
| `docs/05-ai/RESPONSE_RULES.md` | customer response rules |
| `docs/05-ai/agents/beacon/BEACON_SCOPE.md` | Beacon department scope |
| `docs/05-ai/agents/beacon/MEDIA_STORAGE_DECISION.md` | Beacon media storage and authority |
| `docs/05-ai/agents/sam/SAM_V3_LLM_FIRST_SHARED_CONTEXT_PLAN.md` | Sam LLM-first direction |
| `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md` | money-first meat sales plan |
| `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md` | pig allocation and pork business rules |
| `docs/08-business-modules/PORK_SALES_MODEL.md` | pork sales model detail |
| `docs/08-business-modules/MEAT_LAUNCH_CAMPAIGN_PACKET.md` | Beacon campaign packet |
| `config/sam_farm_knowledge.json` | Sam farm knowledge facts |

## Operations Sources

| Source | Vault Brain use |
| --- | --- |
| `docs/06-operations/TESTING_CHECKLIST.md` | test expectations |
| `docs/06-operations/RUNBOOK.md` | operational runbook |
| `docs/06-operations/RELEASE_CHECKLIST.md` | release evidence |
| `docs/06-operations/CHARLIE_BUILD_RELAY_PLAN.md` | CHARLIE relay planning |
| `docs/06-operations/GOOGLE_SHEETS_TO_SUPABASE_MIGRATION_PLAN.md` | migration program |

## Decisions And Planning Sources

| Source | Vault Brain use |
| --- | --- |
| `docs/07-decisions/ADR_0001_DOCUMENTATION_SOURCE_OF_TRUTH.md` | docs canonical source decision |
| `planning/CHARLIE_CORE_EXTENDED_PLAN.md` | staged CHARLIE CORE plan |
| `planning/ToDoList.md` | live scratchpad policy and owner notes |
| `planning/inbox/README.md` | raw owner-note intake policy |

## Runtime/Code Sources

| Source | Vault Brain use |
| --- | --- |
| `modules/charlie/mission_store.py` | mission status/source pack behavior |
| `modules/charlie/vault_store.py` | normalized Vault writes |
| `modules/charlie/execution_bridge.py` | agent runner/review packet behavior |
| `modules/charlie/improvement_analyst.py` | current analyst scope |
| `static/js/charlieMissionControl.js` | dashboard behavior |
| `templates/charlie.html` | dashboard structure |
| `tests/test_charlie_*.py` | behavior expectations |
| `static/assets/agents/*/agent.md` | agent asset/personality details |

## First-Pass Coverage Note

This first pass consolidates active, high-signal docs and source-coded behavior. It does not delete old docs, and it does not claim every archived historical note has been manually migrated line-for-line. Brain Guard must continue reviewing archive and processed planning docs before old material is removed.
