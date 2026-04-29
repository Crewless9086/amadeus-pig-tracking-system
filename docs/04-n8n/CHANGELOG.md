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

### 2026-04-29 - Fix C Option B1 — Create Order With Lines (Atomic)

Type: `FIX`

Component: `1.0 - SAM - Sales Agent - Chatwoot`, `1.2 - Amadeus Order Steward`

Change:

- `1.0 Set - Draft Order Payload` — `action` field is now a conditional expression: sends `create_order_with_lines` when `order_state.requested_items[]` is non-empty, otherwise sends `create_order`.
- `1.0 Set - Draft Order Payload` — new `requested_items` field forwards `order_state.requested_items` to `1.2`.
- `1.0 Code - Store Draft Order Context` — jsCode reverted to simple pass-through (no cross-node reference). Fans out directly to `HTTP - Set Conversation Order Context` (index 0) and `Merge - Draft Result With Reply Context` (index 1).
- `1.2 Switch - Route by Action` — new rule at index [11] matching `action === create_order_with_lines`, output key `Create Order With Lines`.
- Five new nodes added to `1.2` forming the `create_order_with_lines` branch: `Set - Build Create With Lines Body` → `HTTP - Create With Lines Order` → `Code - Build Sync After Create Payload` → `HTTP - Sync New Draft Lines` → `Code - Format Create With Lines Result`.
- `Code - Format Create With Lines Result` — top-level `success` requires both `create_success === true` AND `syncResp.success === true`. Sam will not confirm the order if sync fails.
- Previous Fix C Option A nodes removed from `1.0`: `IF - Draft Has Requested Items`, `Code - Build Sync New Draft Lines Payload`, `Call 1.2 - Sync New Draft Lines`, `Code - Restore Draft Sync Result`.

Reason:

First-turn committed orders with `requested_items[]` were creating `ORDER_MASTER` only. `ORDER_LINES` were not created until a later update path. Fix C Option A added a post-create sync branch inside `1.0`, but this violated the `1.0`/`1.2` ownership boundary. Option B1 moves the full create+sync operation into `1.2` as a single atomic action, keeping `1.0` as a router only.

Expected outcome:

When Sam routes to `CREATE_DRAFT` and `requested_items` is non-empty, `1.2` creates the draft and syncs order lines atomically. `success=true` guarantees both operations completed. Sam's reply references the order ID and the lines are present in `ORDER_LINES` before Sam replies.

Follow-up (separate, not part of this fix):

The Sales Agent AI receives a large merged payload. A future `Code - Build Sales Reply Context` node could slim this to only what Sam needs for her reply (order_id, order_status, sync_results summary, customer context).

Status: live-verified 2026-04-29. `ORD-2026-879091` created in Draft; `ORDER_LINES` has 3 rows with `exact_match` / `matched_quantity=3` / `request_item_key=primary_1`. Sam's reply referenced the order ID.

### 2026-04-29 - Fix C Option A — Superseded

Type: `REMOVE`

Component: `1.0 - SAM - Sales Agent - Chatwoot`

Change:

Nodes `IF - Draft Has Requested Items`, `Code - Build Sync New Draft Lines Payload`, `Call 1.2 - Sync New Draft Lines`, `Code - Restore Draft Sync Result` were implemented in `1.0` as a post-create sync branch but were removed before going live.

Reason:

Superseded by Fix C Option B1. Placing create+sync logic inside `1.0` violated the `1.0`/`1.2` ownership boundary. Option B1 moves the full operation into `1.2` as a single action.

Status: removed — never live-tested. See Fix C Option B1 above.

### 2026-04-29 - Chatwoot Attribute Register Added

Type: `DOCS`

Component: `docs/04-n8n`

Change:

- Added `CHATWOOT_ATTRIBUTES.md` as the canonical register for Chatwoot conversation attributes, contact attributes, and labels.
- Documented the full-object replacement risk for Chatwoot conversation custom attributes.
- Documented active attribute writes in `1.0` and `1.1`.
- Documented outstanding risks for `1.3` media attribute writes and label endpoint behavior.

Reason:

Live testing showed multiple failures caused by partial Chatwoot custom attribute writes erasing order context. The workflow suite needs one source of truth before adding more order behavior.

Expected outcome:

Future changes can verify Chatwoot labels and custom attributes against one documented contract before import or live testing.

Status: documented; `1.1` expression-safe release verified 2026-04-29

### 2026-04-29 - Phase 1.2c Escalation Path Attribute Fix

Type: `FIX`

Component: `1.0 - SAM - Sales Agent - Chatwoot`, `1.1 - SAM - Sales Agent - Escalation Telegram`

Change:

- Fixed `HTTP - Set Conversation Human Mode` in `1.0` — now writes all seven Chatwoot fields including `order_id`, `order_status`, `pending_action` on escalation. Previously only wrote four escalation-specific fields, erasing order context.
- Fixed `Edit - Keep Chatwoot ID's` in `1.0` — now carries `existing_order_id`, `existing_order_status`, `conversation_mode` forward so the Escalation Classifier has order context.
- Updated `Ai Agent - Escalation Classifier` user prompt in `1.0` — now includes `ExistingOrderId`, `ExistingOrderStatus`, `PendingAction` so the classifier can make order-aware routing decisions.
- Updated `Ai Agent - Escalation Classifier` system prompt in `1.0` — added cancel routing rule: if `ExistingOrderId` is present and customer asks to cancel, route to AUTO (not ESCALATE).
- Updated `Edit - Build Ticket Data` in `1.0` — now writes `WebOrderId`, `WebOrderStatus`, `WebPendingAction` to the `Sales_HumanEscalations` sheet at escalation time.
- Fixed `Release Conversation to Auto` in `1.1` — now reads `WebOrderId`, `WebOrderStatus`, `WebPendingAction` back from the escalation sheet and preserves them in the Chatwoot reset. Previously wrote only `conversation_mode: AUTO`, erasing all order context when the human replied.

Reason:

If a customer was escalated and the human did not immediately reply, the customer's next message arrived with empty order context — `ExistingOrderId` was blank, routing logic could not find the active order, and the system could incorrectly create a new draft instead of recognising the existing order. A cancel request during or after an escalation would also incorrectly route to ESCALATE rather than through the cancel confirmation flow.

Expected outcome:

Order context (`order_id`, `order_status`, `pending_action`) survives through escalation and human reply. The Escalation Classifier will not escalate routine cancel requests when an active order is present.

Status: live-verified 2026-04-29. `Sales_HumanEscalations` preserved `WebOrderId`, `WebOrderStatus`, and `WebPendingAction`; `1.1` restored Chatwoot attributes with real evaluated values; a follow-up customer cancellation routed through `AUTO` and `CANCEL_ORDER` successfully.

### 2026-04-29 - Phase 1.2b Live Test Fixes

Type: `FIX`

Component: `1.0 - SAM - Sales Agent - Chatwoot`, `1.2 - Amadeus Order Steward`

Change:

- Fixed `1.2` Switch node connection array — `cancel_order` was routed to the `add_order_line` path due to incorrect positional indexing. Re-indexed all 11 connections.
- Fixed three cancel-path Chatwoot write nodes in `1.0` (`HTTP - Set Pending Cancel Action`, `HTTP - Clear Pending Action`, `HTTP - Clear Pending After Cancel`) to always write all four core attribute fields, preventing `order_id` erasure.
- Added safety guard in `Code - Decide Order Route` — blocks `CREATE_DRAFT` route when `pending_action = cancel_order` but `existing_order_id` is empty, preventing accidental draft creation during a broken cancel confirm.
- Fixed CREATE_DRAFT order_id data flow — `Code - Store Draft Order Context` now fans out directly to both `HTTP - Set Conversation Order Context` (leaf) and `Merge - Draft Result With Reply Context` (index 1). This ensures `order_id` from the 1.2 result reaches the AI agent prompt. Previously the HTTP node sat between them and replaced `$json` with the Chatwoot API response before the merge.

Reason:

Live test after initial Phase 1.2b wiring revealed four separate bugs: wrong Switch routing in 1.2, order_id erasure on CANCEL_PENDING, order_id absent from AI agent prompt after CREATE_DRAFT, and missing guard for cancel confirm with empty order.

Expected outcome:

Two-turn cancel flow works end-to-end. Sam correctly references order ID in draft creation reply. Cancel confirmation cannot accidentally trigger CREATE_DRAFT.

Status: live-verified. Sam correctly referenced order ID after CREATE_DRAFT. Cancel confirmation cannot accidentally trigger CREATE_DRAFT. Cancel flow was re-tested after escalation fixes and successfully cancelled `ORD-2026-367706`.

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
