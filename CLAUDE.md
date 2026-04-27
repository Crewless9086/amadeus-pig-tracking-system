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
4. Backend creates/updates orders based on the decision
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
| `POST` | `/api/orders/{order_id}/complete` | Complete order |
| `GET` | `/api/orders` | List all orders |
| `GET` | `/api/orders/{order_id}` | Order detail with lines |
| `GET` | `/api/orders/available-pigs` | Available pigs from `SALES_AVAILABILITY` |

## Project Documentation (Critical Documentation)

The `docs/` directory contains living documentation that must be consulted before making changes:

| File | When to Read |
|---|---|
| `docs/01-architecture/SYSTEM_ARCHITECTURE.md` | Before touching component boundaries |
| `docs/00-start-here/CURRENT_STATE.md` | Before starting any work — shows what's broken |
| `docs/00-start-here/NEXT_STEPS.md` | Before adding features — shows prioritized roadmap |
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
- **Sales Categories**: Young Piglets, Weaner Piglets, Grower Pigs, Finisher Pigs, Ready for Slaughter.

## Current System State

**Phase**: ACTIVE BUILD (mid-stage) | **Stability**: PARTIALLY STABLE

Known instabilities (check `docs/00-start-here/CURRENT_STATE.md` for latest):
- AUTO reply integrity — Composer node can override valid AI answers
- Reply system field confusion at merge points in n8n
- Order routing inconsistency across workflow paths
- Order line sync logic needs verification

Stabilization is prioritized over new features — see `docs/00-start-here/NEXT_STEPS.md` for the 5-phase roadmap.
