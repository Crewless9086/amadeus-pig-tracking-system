# n8n Documentation

## Purpose

This folder is the source of truth for the n8n workflow layer of the Amadeus Pig Tracking and Sales System.

It documents:

- the workflow suite and how each workflow relates to the others
- workflow exports and human-readable workflow notes
- node responsibilities and protected fields
- data contracts between Chatwoot, n8n, backend, Google Sheets, Telegram, Google Drive, and AI tools
- rules that must be followed before changing workflow behavior

## Workflow Suite

| Workflow | Folder | Status | Role |
| --- | --- | --- | --- |
| `1.0 - SAM - Sales Agent - Chatwoot` | `workflows/1.0 - Sam-sales-agent-chatwoot/` | Active hub | Main customer conversation workflow from Chatwoot. |
| `1.1 - SAM - Sales Agent - Escalation Telegram` | `workflows/1.1 - Sam - sales-agent-escalation-telegram/` | Active support workflow | Human reply handling from Telegram back to Chatwoot. |
| `1.2 - Amadeus Order Steward` | `workflows/1.2 - order-steward/` | Active worker workflow | Backend order actions called by `1.0`. |
| `1.3 - SAM - Sales Agent - Media Tool` | `workflows/1.3 - Sam-sales-agent-media-tool/` | Disabled until fixed | Sends media/images through Chatwoot when enabled. |
| `1.4 - Outbound Order Notification` | `workflows/1.4 - outbound-order-notification/` | Planned/import pending | Receives backend approval/rejection events and sends the customer Chatwoot message. |
| `1.5 - Outbound Document Delivery` | `workflows/1.5 - outbound-document-delivery/` | Live-verified 2026-05-10 | Receives backend document-delivery events and sends generated quote/invoice PDFs as Chatwoot attachments. |
| `2.0 - Daily Order Summary` | `workflows/2.0 - daily-order-summary/` | Draft/import pending | Scheduled operations summary from backend report endpoint to Telegram. |

## Folder Map

| File | Purpose |
| --- | --- |
| `WORKFLOW_MAP.md` | High-level suite map and workflow-by-workflow flow. |
| `DATA_FLOW.md` | Field contracts and cross-workflow payload movement. |
| `CHATWOOT_ATTRIBUTES.md` | Canonical Chatwoot labels, conversation attributes, contact attributes, and snapshot rules. |
| `NODE_RESPONSIBILITIES.md` | Node and workflow responsibilities. |
| `WORKFLOW_RULES.md` | Rules for AUTO, CLARIFY, ESCALATE, order tools, media, and human handoff. |
| `DO_NOT_CHANGE.md` | Protected fields, routes, node contracts, and fragile behavior. |
| `CHANGELOG.md` | n8n documentation and workflow change history. |
| `workflows/` | One folder per n8n workflow with `README.md` and `workflow.json`. |

## Core Architecture

```mermaid
flowchart TD
  chatwoot[Chatwoot] --> workflow10["1.0 Sales Agent Chatwoot"]
  workflow10 --> sheetsSales["Sales Stock Sheets"]
  workflow10 --> farmDoc["Farm Info Doc"]
  workflow10 --> workflow12["1.2 Order Steward"]
  workflow12 --> backend["Flask Backend API"]
  backend --> googleSheets["Google Sheets"]
  workflow10 --> escalationSheet["Human Escalation Sheet"]
  workflow10 --> telegram[Telegram Alert]
  telegram --> workflow11["1.1 Escalation Telegram"]
  workflow11 --> chatwoot
  workflow11 --> escalationSheet
  workflow10 -. disabled tool .-> workflow13["1.3 Media Tool"]
  workflow13 --> googleDrive[Google Drive]
  workflow13 --> chatwoot
  backend --> workflow14["1.4 Outbound Order Notification"]
  workflow14 --> chatwoot
  backend --> workflow15["1.5 Outbound Document Delivery"]
  workflow15 --> googleDrive[Google Drive]
  workflow15 --> chatwoot
  schedule["Schedule"] --> workflow20["2.0 Daily Order Summary"]
  workflow20 --> backend
  workflow20 --> telegram
```

## Current Build Decisions

- `1.0` is the only customer-entry workflow.
- `1.2` is the preferred path for order review and order actions. Sam should not directly write order sheets.
- First-turn committed orders with `requested_items[]` use `create_order_with_lines`; `1.2` owns the create + sync operation and returns a combined result.
- Direct read access to `ORDER_OVERVIEW` may be useful later, but the safer planned direction is to expose order review through `1.2` and the backend so identity matching, filtering, and permissions stay controlled.
- `1.3` is officially the media workflow number, but the media tool remains disabled until fixed and tested.
- `1.4` is the outbound order notification workflow. It must only send backend-confirmed approval/rejection messages and must use `ConversationId` from `ORDER_MASTER`.
- `1.5` is the outbound document delivery workflow. It must only send backend-generated quote/invoice PDFs and must not calculate totals or VAT.
- `2.0` is the daily operations summary workflow. It must read from the backend summary endpoint, not directly from order sheets.
- Telegram cleanup after human reply is desired but should be treated as a planned improvement unless confirmed implemented.
- This repo is private, so workflow exports may keep full technical detail for local build planning.

## Update Rule

When any n8n workflow changes, update the matching workflow folder and then update any affected root docs in this folder.
