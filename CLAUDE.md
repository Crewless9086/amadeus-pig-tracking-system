# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Amadeus Pig Tracking & Sales System** — an integrated platform that automates livestock sales conversations, order creation, and customer handling with minimal human intervention.

## Development Commands

### Running the Flask Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python app.py

# Run with gunicorn (production)
gunicorn app:app
```

### Environment Setup

Required environment variables (create a `.env` file):
```
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
GOOGLE_SHEET_NAME=<your-sheet-name>
```

`service_account.json` must be present (not committed) — obtain from Google Cloud Console.

## Architecture

The system is a **multi-layer orchestration pipeline**:

```
Customer (WhatsApp/Messenger/etc.)
    ↓
Chatwoot  (communication layer)
    ↓
n8n       (orchestration engine — workflow automation)
    ↓
AI Agents (decision layer — sales conversation + escalation classification)
    ↓
Flask API (backend — order management and business logic)
    ↓
Google Sheets (data layer — single source of truth)
```

### Core Flow

1. Customer message arrives → Chatwoot webhook fires → n8n picks it up
2. n8n normalizes the message and passes it to the AI Sales Agent
3. Escalation Classifier decides: **AUTO** (process automatically) / **CLARIFY** (ask customer) / **ESCALATE** (hand to human)
4. Steward + Flask create/update orders based on routed actions and **sheet-backed** availability (**not** unmanaged LLM claims)
5. Response sent back through Chatwoot

### Backend (Flask)

- `app.py` — Flask application entry point with all route registrations
- `modules/orders/` — order CRUD, service logic, and validation
- `modules/pig_weights/` — weight tracking and mating management
- `services/google_sheets_service.py` — all Google Sheets read/write operations
- `config/app_config.py` — credentials and sheet name configuration

### Data Layer (Google Sheets)

Two categories of sheets — **never write to formula-driven sheets**:

| Type | Examples | Rule |
|---|---|---|
| Master (writable) | `PIG_MASTER`, `ORDER_MASTER`, `ORDER_LINES`, `LITTERS`, `WEIGHT_LOG`, `MEDICAL_LOG`, `MATING_LOG` | Read and write |
| Formula-driven (read-only) | `PIG_OVERVIEW`, `SALES_AVAILABILITY`, `ORDER_OVERVIEW`, `SALES_STOCK_*` | Read only — formulas auto-populate |

### API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/master/orders` | Create draft order |
| `PATCH` | `/api/master/orders/{order_id}` | Update order header |
| `POST` | `/api/master/orders/{order_id}/sync-lines` | Sync requested order lines |
| `POST` | `/api/master/order-lines` | Create order line |
| `PATCH` | `/api/master/order-lines/{order_line_id}` | Update order line |
| `DELETE` | `/api/master/order-lines/{order_line_id}` | Delete order line |
| `POST` | `/api/orders/{order_id}/reserve` | Reserve pigs |
| `POST` | `/api/orders/{order_id}/release` | Release pigs |
| `POST` | `/api/orders/{order_id}/send-for-approval` | Trigger approval flow |
| `POST` | `/api/orders/{order_id}/approve` | Approve order |
| `POST` | `/api/orders/{order_id}/reject` | Reject order |
| `POST` | `/api/orders/{order_id}/cancel` | Customer-cancel order |
| `POST` | `/api/orders/{order_id}/complete` | Complete order |
| `GET` | `/api/orders` | List all orders |
| `GET` | `/api/orders/{order_id}` | Order detail with lines |
| `GET` | `/api/orders/available-pigs` | Available pigs from `SALES_AVAILABILITY` |

## Collaboration: Cursor conductor vs Claude Code worker

Use this repo with **two complementary roles**:

| Role | Tool | Responsibility |
|---|---|---|
| **Conductor** | Cursor chat (Composer / agent) | Triage incoming issues, propose minimal changes, sequence work against **`NEXT_STEPS.md`**, avoid scope creep |
| **Worker** | Claude Code (`claude.ai/code`) implementing in-repo | Heavy refactors, wide file search, systematic patches with repo context from **`CLAUDE.md`** |

**Yes — run substantial or cross-cutting checks past Claude Code** when a change spans many nodes, Flask + n8n + docs, or you want a second pass on correctness and duplication. Paste **`docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md`** into Claude Code after filling the placeholders.

### Stay on track (anti–rabbit-hole)

1. **`docs/00-start-here/NEXT_STEPS.md`** is the single approved build order — start every session here and attach **one phase item** as your scope boundary.
2. **`docs/00-start-here/CURRENT_STATE.md`** inventories known pain points; use it only to **explain** breakage, not to grow scope mid-task (log new items in **`NEXT_STEPS`** under the correct phase instead).
3. **`planning/ToDoList.md`** is **scratch only** — do not treat it as a second roadmap; migrate bullets into **`NEXT_STEPS`** and clear the scratch file.

If Cursor and Claude disagree, **`NEXT_STEPS.md`** wins unless the docs are updated explicitly.

---

## Project Documentation (Critical Documentation)

The `docs/` directory contains living documentation that must be consulted before making changes:

| File | When to Read |
|---|---|
| `docs/01-architecture/SYSTEM_ARCHITECTURE.md` | Before touching component boundaries |
| `docs/00-start-here/CURRENT_STATE.md` | Before starting any work — shows what's broken |
| `docs/00-start-here/NEXT_STEPS.md` | Before adding features — shows prioritized roadmap |
| `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md` | Copy-paste prompt for Claude Code second-pass reviews |
| `docs/03-google-sheets/BUSINESS_RULES.md` | Before changing AI behavior or order logic |
| `docs/03-google-sheets/SHEET_SCHEMA.md` | Before any sheet read/write operation |
| `docs/02-backend/API_STRUCTURE.md` | Before modifying Flask endpoints |
| `docs/02-backend/ORDER_LOGIC.md` | Before touching draft/line/reservation logic |
| `docs/04-n8n/WORKFLOW_MAP.md` | Before touching n8n integration |
| `docs/04-n8n/WORKFLOW_RULES.md` | Before changing escalation/decision logic |
| `docs/04-n8n/DATA_FLOW.md` | Before changing field ownership or data mutations |

## Key Business Rules

- **Draft Logic**: Never create a new draft if one exists for the customer — always update the existing draft.
- **Availability Gate**: Pigs must have `Available_For_Sale = Yes` before being shown to customers.
- **Pricing**: Must come from `SALES_PRICING` sheet — never invent prices.
- **Collection Only**: No delivery — customers must collect. AI must not promise exceptions.
- **No Premature Promises**: AI must not promise reservations or availability until the backend confirms.
- **Availability wording (sex mix / counts)**: Do not tell the customer that specific animals are “available” for a split (e.g. 1 male + 2 females) unless **steward / `get_order_context` / sync results** support it — conversation memory and LLM replies are **not** inventory. Track fixes under **`NEXT_STEPS.md` Phase 4.1–4.2**.
- **Sales Categories**: Young Piglets, Weaner Piglets, Grower Pigs, Finisher Pigs, Ready for Slaughter.

## Current System State

**Phase**: ACTIVE BUILD (mid-stage) | **Stability**: PARTIALLY STABLE

Known instabilities (check `docs/00-start-here/CURRENT_STATE.md` for latest):
- AUTO reply integrity — Composer node can override valid AI answers
- Reply system field confusion at merge points in n8n
- Order routing inconsistency across workflow paths
- Split requested item sync still needs hardening for multi-key requests
- Sales Agent reply prompt receives an oversized merged payload and should be slimmed
- Phase 1.4 backend `400` reply path needs live re-test after latest `1.2` import
- Approval auto-reservation is planned but must wait until reserve/release hardening is complete
- Approval/rejection customer notifications should be a separate outbound n8n workflow, not Sam's inbound `1.0`

Stabilization is prioritized over new features — see `docs/00-start-here/NEXT_STEPS.md` for the current roadmap.
