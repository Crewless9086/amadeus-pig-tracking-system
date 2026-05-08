# Documentation Migration Index

## Purpose

Tracks legacy documentation sources and their new canonical homes.

## Status Meaning

- `Content copied`: the legacy content has been copied into `docs/` but still needs cleanup and verification.
- `Reviewed empty`: the legacy file was checked and had no content to migrate.
- `Export migrated`: the legacy workflow export was parsed and written as JSON.
- `Removed after migration`: the legacy file was deleted after its replacement was created under `docs/`.

## Legacy Sources

| Legacy source | New home | Status |
| --- | --- | --- |
| `CLAUDE.md` | `docs/00-start-here/`, `docs/01-architecture/`, `docs/06-operations/` | Reviewed as source material |
| `project-memory/CORE/README.md` | `docs/00-start-here/README.md` | Removed after migration |
| `project-memory/CORE/PROJECT_OVERVIEW.md` | `docs/00-start-here/PROJECT_OVERVIEW.md` | Removed after migration |
| `project-memory/CORE/CURRENT_STATE.md` | `docs/00-start-here/CURRENT_STATE.md` | Removed after migration |
| `project-memory/CORE/NEXT_STEPS.md` | `docs/00-start-here/NEXT_STEPS.md` | Removed after migration |
| `project-memory/CORE/SYSTEM_ARCHITECTURE.md` | `docs/01-architecture/SYSTEM_ARCHITECTURE.md` | Removed after migration |
| `project-memory/BACKEND/API_STRUCTURE.md` | `docs/02-backend/API_STRUCTURE.md` | Removed after migration |
| `project-memory/BACKEND/ORDER_LOGIC.md` | `docs/02-backend/ORDER_LOGIC.md` | Removed after migration |
| `project-memory/DATA/GOOGLE_SHEET_SCHEMA.md` | `docs/03-google-sheets/SHEET_SCHEMA.md` | Removed after migration |
| `project-memory/DATA/FORMULA_LOGIC.md` | `docs/03-google-sheets/FORMULA_LOGIC.md` | Removed after migration |
| `project-memory/DATA/BUSINESS_RULES.md` | `docs/03-google-sheets/BUSINESS_RULES.md` | Removed after migration |
| `project-memory/WORKFLOW CONTROL/WORKFLOW_MAP.md` | `docs/04-n8n/WORKFLOW_MAP.md` | Removed after migration |
| `project-memory/WORKFLOW CONTROL/DATA_FLOW.md` | `docs/04-n8n/DATA_FLOW.md` | Removed after migration |
| `project-memory/WORKFLOW CONTROL/WORKFLOW_RULES.md` | `docs/04-n8n/WORKFLOW_RULES.md` | Removed after migration |
| `project-memory/WORKFLOW CONTROL/NODE_RESPONSIBILITIES.md` | `docs/04-n8n/NODE_RESPONSIBILITIES.md` | Removed after migration |
| `project-memory/WORKFLOW CONTROL/DO_NOT_CHANGE.md` | `docs/04-n8n/DO_NOT_CHANGE.md` | Removed after migration |
| `project-memory/WORKFLOW CONTROL/CHANGELOG.md` | `docs/04-n8n/CHANGELOG.md` | Removed after migration |
| `project-memory/AI/AGENT_ROLES.md` | `docs/05-ai/AGENT_ROLES.md` | Removed after migration |
| `project-memory/AI/PROMPT_RULES.md` | `docs/05-ai/PROMPT_RULES.md` | Removed after migration |
| `project-memory/n8n_Current_Workflow.md` | `docs/04-n8n/workflows/sales-agent-chatwoot/workflow.json` | Removed after migration |
| `planning/ToDoList.md` | `docs/00-start-here/NEXT_STEPS.md` | Planning pointer only; use NEXT_STEPS |

## Migration Rule

Do not delete or archive remaining legacy files until the replacement document is cleaned, reviewed, and accepted.
