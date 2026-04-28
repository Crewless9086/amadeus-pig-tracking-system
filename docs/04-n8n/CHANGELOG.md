# n8n Changelog

## Purpose

Tracks approved n8n workflow documentation and behavior decisions.

## Change Types

- `DOCS`: documentation-only update
- `FIX`: behavior fix
- `IMPROVEMENT`: existing behavior improvement
- `ADD`: new workflow/node/feature
- `REFACTOR`: structure change without intended behavior change
- `REMOVE`: deleted workflow/node/behavior

## Current Entries

### 2026-04-27 - Phase 1.2b Customer Cancel Wired Into n8n

Type: `ADD`

Component: `1.0 - SAM - Sales Agent - Chatwoot`, `1.2 - Amadeus Order Steward`

Change:

- Added `cancel_order` handling to `1.2` with `reason`, backend cancel endpoint call, and formatted cancel result.
- Added guarded customer-cancel routing to `1.0` using `CANCEL_PENDING`, `CANCEL_ORDER`, and `CLEAR_PENDING`.
- Added Chatwoot `pending_action = cancel_order` confirmation state and clear paths.
- Updated protected workflow docs and live action lists to include `cancel_order`.

Reason:

Customer cancellation must be handled through backend truth, not direct sheet edits or unconfirmed Sam replies.

Expected outcome:

Sam asks for one confirmation before cancelling, calls the backend only after confirmation, and only tells the customer the order is cancelled after backend success.

Status: implemented in exports; needs live n8n import and two-turn verification

### 2026-04-27 - Four Workflow Suite Documented

Type: `DOCS`

Component: `docs/04-n8n`

Change:

- Documented the n8n workflow suite as four workflows: `1.0`, `1.1`, `1.2`, and `1.3`.
- Rewrote the root n8n docs around suite flow, data contracts, node responsibilities, workflow rules, and protected logic.
- Confirmed `1.0 - SAM - Sales Agent - Chatwoot` as the customer-facing hub.
- Confirmed `1.1 - SAM - Sales Agent - Escalation Telegram` as the human reply bridge.
- Confirmed `1.2 - Amadeus Order Steward` as the order action worker.
- Confirmed `1.3 - SAM - Sales Agent - Media Tool` as the official media workflow number.

Reason:

The workflow documentation needed to reflect all uploaded workflow exports, not only the original `1.0` flow.

Expected outcome:

Future backend, AI, and n8n changes can use the `04-n8n` docs as the workflow source of truth.

Status: documented

### 2026-04-27 - Media Tool Kept Disabled

Type: `DOCS`

Component: `1.3 - SAM - Sales Agent - Media Tool`

Change:

- Documented `1.3` as the official media tool workflow.
- Documented that `Send_Pictures` should remain disabled until the media workflow is fixed and tested.
- Noted that the raw `1.0` workflow export still contains cached n8n metadata naming the media tool as `1.2`; this should be corrected in n8n on the next workflow update/export.

Reason:

The media tool is useful but not ready for customer use.

Expected outcome:

Sam will not send media until the workflow is explicitly enabled after review.

Status: planned/future fix

### 2026-04-27 - Order Review Direction Confirmed

Type: `DOCS`

Component: `1.0` and `1.2`

Change:

- Documented the preferred future order-review path: Sam should request order context through `1.2 - Amadeus Order Steward` and backend APIs rather than directly reading `ORDER_OVERVIEW` as a production tool.
- Documented direct `ORDER_OVERVIEW` read access as diagnostic or possible fallback, not the preferred build direction.

Reason:

Backend-mediated order review gives better customer matching, filtering, privacy, and testability.

Expected outcome:

Future order context work should add or improve backend/order-steward review actions instead of giving Sam uncontrolled sheet access.

Status: approved direction

### 2026-04-27 - Live Order Steward Actions Scoped

Type: `DOCS`

Component: `1.2 - Amadeus Order Steward`

Change:

Documented only these actions as currently live for `1.0`:

- `create_order`
- `update_order`
- `sync_order_lines_from_request`

Reason:

The steward workflow contains more capability than `1.0` currently uses. The docs should not imply all steward actions are active Sam tools.

Expected outcome:

Future actions can be enabled one at a time with explicit testing and documentation.

Status: documented

### 2026-04-27 - Telegram Cleanup Desired

Type: `IMPROVEMENT`

Component: `1.1 - SAM - Sales Agent - Escalation Telegram`

Change:

Documented Telegram message cleanup after human reply as a desired improvement.

Reason:

The human handoff channel should not remain cluttered after a ticket is answered.

Expected outcome:

Future work should safely delete only the relevant Telegram messages after reply, without deleting unrelated messages.

Status: planned

### 2026-04-27 - Private Repo Export Detail Accepted

Type: `DOCS`

Component: workflow exports

Change:

Confirmed that workflow exports and READMEs may keep full local technical detail because this repository is private.

Reason:

Detailed exports make the system easier to rebuild and debug locally.

Expected outcome:

No redaction pass is required for current private documentation. If the repository is shared or made public, credentials and tokens must be redacted or rotated.

Status: accepted for private repo

## Historical Notes

The older 2026-04 stabilization work focused mainly on `1.0` reply integrity:

- CLARIFY path should preserve the AI Sales Agent response.
- `ai_reply_output` protects useful AI replies from merge/composer overwrites.
- `cleaned_reply` is the safe final outbound field for `1.0` customer replies.
- Merge nodes and the generic `output` field remain high-risk areas.

## Entry Template

```text
Date:
Workflow/component:
Type:
Change:
Reason:
Expected outcome:
Status:
```
