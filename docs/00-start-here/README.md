# Start Here

## Purpose

This folder is the entry point for the Amadeus Pig Tracking and Sales System documentation.

## Current Documentation Source Of Truth

The canonical project documentation lives in `docs/`.

Use this folder first to understand:

- what the project is
- what is working now
- what is risky
- what the approved build order is

## Key Files

| File | Purpose |
| --- | --- |
| `PROJECT_OVERVIEW.md` | Plain-language system overview and layer map. |
| `CURRENT_STATE.md` | Current project status and live risks. |
| `NEXT_STEPS.md` | Approved build order and current first task. |
| `GLOSSARY.md` | Shared terms used across docs, backend, n8n, Sheets, and AI. |

## Main Documentation Areas

| Folder | Purpose |
| --- | --- |
| `docs/02-backend/` | Flask API, order logic, backend data models, module structure, and refactor plan. |
| `docs/03-google-sheets/` | Sheet schema, formulas, ownership, fields, and business rules. |
| `docs/04-n8n/` | n8n workflow suite, data flow, node responsibilities, protected logic, and workflow exports. |
| `docs/05-ai/` | AI roles, prompt rules, and response rules. |
| `docs/06-operations/` | Testing, release, troubleshooting, and runbook guidance. |
| `docs/07-decisions/` | Architecture and documentation decisions. |

## Current Build Focus

Orders come first.

The order system is live and profit-critical, so the next build work must stabilize reject, cancel, release, reservation, and requested-item sync before app polish or new features.

## Rule For Agents

Before changing code, workflows, Sheets, or prompts:

1. Read the relevant docs area.
2. Keep the change scoped.
3. Update docs when behavior changes.
4. Run the relevant testing checklist.
