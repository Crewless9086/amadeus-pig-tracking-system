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

### 2026-05-08 — Sam partial-stock wording on `create_order_with_lines`

Type: `FIX` + `DOCS`

Issue: first-turn `CREATE_DRAFT` with `create_order_with_lines` returned correct `partial_match` in `sync_results`, but `1.2 Code - Format Create With Lines Result` did not set top-level `partial_fulfillment` / `results`, and `StewardCompact` only exposed a terse `summary`, so Sam defaulted to vague \"limited stock\" wording.

Change:

- **`1.2` `Code - Format Create With Lines Result`:** pass `partial_fulfillment` (from API or inferred from `partial_match` rows), duplicate `results` next to `sync_results` for callers that read `results`.
- **`1.0` `Code - Slim Sales Agent User Context`:** set `partial_fulfillment` when `had_partial`; add **`partial_stock_detail`** string (requested vs `added_to_draft`, band availability, same-category alternative bands from `alternatives[]`).
- **`1.0` Sam system prompt:** hardened **PARTIAL STOCK SYNC** rules (explicit X vs Y, list alternatives, single follow-up question; applies to create-with-lines as well as sync on existing draft).
- **`DATA_FLOW.md`:** document `partial_stock_detail`.

### 2026-05-07 — `Line_Count` vs active lines (documented + API)

Type: `DOCS` + `IMPROVEMENT`

- **Cause:** `ORDER_OVERVIEW.Line_Count` uses `COUNTIF(ORDER_LINES!$B:$B, order_id)` — it counts **all** line rows, including **`Cancelled`** (common after sync replace). Example: 3 active + 3 cancelled → sheet shows 6. **`send_for_approval`** uses only non-cancelled lines, so behaviour was already correct; the confusion risk is **human/Sam** reading `line_count` as “pigs on the order.”
- **API:** `GET /api/orders/<order_id>` → `order.active_line_count` = count of lines where `line_status !== "Cancelled"` (same rule as approval).
- **`1.2` `get_order_context` formatter:** passes `active_line_count` (falls back to counting slim lines if API not deployed yet) and `line_count_includes_cancelled: true`.
- **Docs:** `ORDER_OVERVIEW.md`, `API_STRUCTURE.md`, `DATA_FLOW.md`.

### 2026-05-07 — Partial sync lines, order context fetch, GET order `payment_method`

Type: `FIX` + `ADD` + `IMPROVEMENT`

**Backend**

- `sync_order_lines_from_request`: `partial_match` now creates `ORDER_LINES` for available pigs (up to requested quantity), not zero lines. Per-item payload includes `available_quantity`; top-level `partial_fulfillment` when any item was short.
- `GET /api/orders/<order_id>`: `order` object now includes `payment_method` from `ORDER_MASTER.Payment_Method` (overview alone does not carry it).

**`1.2 - Amadeus Order Steward`**

- New steward action `get_order_context`: `GET /api/orders/<id>` → `Code - Format Get Order Context Result` returns `order_context_fetch_ok`, `existing_order_context` (slim header + lines).
- `Set - Format Sync Order Lines Result` also passes through top-level `results` and `partial_fulfillment` for downstream Sam merge.

**`1.0 - Sam - Sales Agent - Chatwoot`**

- After `Code - Build Sales Agent Memory Summary`, when a draft `order_id` exists: `If` → `Set - Get Order Context Payload` → `Call 1.2 - Get Order Context` → merge into item → `Switch - Clarify or Auto`.
- `Code - Build Order State` merges fetched header into **empty** fields only; message + Chatwoot attributes win. Sex-only phrases (e.g. “any sex”) now set `should_enrich_existing_draft` without requiring order-intent gates on `msgSex`.
- `Code - Slim Sales Agent User Context` reads `results` or `sync_results`; sets `had_partial` / `partial_fulfillment` in `sam_steward_result_compact`.
- Sam system prompt: **PARTIAL STOCK SYNC** guidance when steward compact shows short allocation.

**Docs:** `DATA_FLOW.md`, `API_STRUCTURE.md`, `ORDER_LOGIC.md`.

Status: implemented in repo exports; **re-import both workflows to n8n** and run live tests (partial stock 6 vs 5, sex-only reply, Cash then send for approval).

### 2026-04-30 - Phase 1.4 Bugfix C — Test C: Sam Still Overstating On Backend 400 Path

Type: `FIX`

Component: `1.0 - SAM - Sales Agent - Chatwoot`, `1.2 - Amadeus Order Steward`

Change:

- `1.2 Set - Format Send for Approval Result` — replaced the `backend_error` expression with an IIFE that correctly parses the `continueOnFail` error format. When n8n `continueOnFail` catches an HTTP 4xx, it passes `{"error": "400 - {JSON_BODY}"}` as a concatenated string — `$json.errors` is absent. The new expression tries `$json.errors[0]` first (success-path JSON), then regex-matches and JSON-parses the `"STATUS - {JSON}"` string from `continueOnFail` to extract `errors[0]`, then falls back to the raw string. Result: `backend_error` now contains a clean customer-safe message like `"Collection location is required before sending for approval."` instead of the raw `"400 - {\"errors\":[...]}"` string.
- `1.2 Set - Format Send for Approval Result` — fixed `order_id` null-on-failure. Added fallback: `$json.order_id || $node["Code - Normalize Order Payload"].json["order_id"]`. When the HTTP node fails, `$json` holds only `{error: "..."}` — `$json.order_id` is undefined. The fallback reads the order_id that was passed into the steward before the HTTP call.
- `1.0 Ai Agent - Sales Agent` user prompt `text` — added five fields after `OrderID`: `BackendSuccess`, `BackendError`, `BackendMessage`, `FinalOrderStatus`, `ReplyInstruction`. Previously these fields were only in the workflow result object but not exposed to Sam in the per-turn prompt, so Sam could not read them and the system prompt rules had no effect.
- `1.0 Ai Agent - Sales Agent` system prompt — replaced the two duplicate SEND_FOR_APPROVAL blocks (first block was weaker, second block was added in Bugfix A but created a duplicate) with a single hardened block. The new block adds: (a) a HARD RULE that explicitly forbids any form of "order was sent" wording when `BackendSuccess` is not exactly `"true"`; (b) instruction to read `BackendError` directly and explain the specific missing field to the customer; (c) instruction to follow `ReplyInstruction` if non-empty.
- `1.0 Set - Restore Send For Approval Result` — added `reply_instruction` field. When `backend_success !== true`, it computes a deterministic instruction string: `"INSTRUCTION: Do not say the order was sent for approval. The backend returned: [backend_error]. Tell the customer what is needed. Do not mention sending for approval."` When `backend_success === true`, the field is empty. This gives Sam an unambiguous per-turn override that does not depend on nuanced rule interpretation.

Root cause:

Three compounding issues:
1. `continueOnFail` wraps the HTTP error as a string `"400 - {JSON}"` — `$json.errors` is undefined, so the Bugfix B fallback chain hit `$json.error` and returned the raw string instead of the clean message.
2. `$json.order_id` is undefined when `continueOnFail` fires — the Format node output contained `order_id: null`, which propagated to Sam and Chatwoot.
3. `BackendSuccess` and `BackendError` existed as workflow fields but were absent from the Sales Agent user prompt `text`, so Sam received no per-turn signal and the system prompt SEND_FOR_APPROVAL rules could not be applied.

Expected outcome:

On a forced backend 400 (e.g., Collection_Location blank): `backend_error` = `"Collection location is required before sending for approval."`, `order_id` = correct order ID (not null), Sam's user prompt contains `BackendSuccess: false` and `BackendError: Collection location...` and `ReplyInstruction: INSTRUCTION: Do not say...`. Sam tells the customer what is missing and does not say the order was sent.

Status: implemented; pending live re-verification of Test C

### 2026-04-30 - Phase 1.4 Bugfix B — Backend 400 Not Handled In 1.2

Type: `FIX`

Component: `1.2 - Amadeus Order Steward`

Change:

- `1.2 HTTP - Send for Approval` — added `continueOnFail: true` at the node root level. `neverError: true` in options alone was not preventing n8n from surfacing the 400 as a workflow error; `continueOnFail` catches it at the execution level as a fallback.
- `1.2 Set - Format Send for Approval Result` — fixed `backend_error` expression to read `$json.errors[0]` (backend route returns `errors: []` array on 400, not `error: ""`) with fallback chain: `$json.errors[0]` → `$json.error.message` (n8n continueOnFail object format) → `$json.error` (string) → `$json.message` → `""`. Fixed `success` expression to always return `"true"` or `"false"` rather than `"undefined"` when n8n error format omits the field.

Root cause:

Two separate issues combined to silence Sam on 400:
1. `neverError: true` did not prevent the HTTP node from throwing; downstream Format node never ran.
2. Backend route returns `{"success": false, "errors": ["..."]}` (plural array) but the Format node read `$json.error` (singular string) — always undefined even if the response was received.

Expected outcome:

When backend returns 400 (e.g., Collection_Location missing), the Format node runs, `backend_success = false`, `backend_error` contains the first error string from the backend, and Sam can tell the customer what is missing.

Status: implemented; needs live re-verification of Test C (forced backend 400 path)

### 2026-04-30 - Phase 1.4 Bugfix — SEND_FOR_APPROVAL Intent Detection And Sam Reply Guard

Type: `FIX`

Component: `1.0 - SAM - Sales Agent - Chatwoot`

Change:

- `1.0 Code - Build Order State` — replaced single-regex `sendForApprovalIntent` with a multi-pattern check that covers natural phrasings including "send it for approval", "send this for approval", "send it through", "send this through", "submit it", "submit this", "submit my order", "go ahead and submit", "ready for approval", "ready to submit", "finalise it/this/the order", "confirm the order/my order/this order". Previous regex only matched "send for approval" as a complete phrase and missed any phrasing with "it" or "this" inserted.
- `1.0 Code - Decide Order Route` — moved SEND_FOR_APPROVAL check to before UPDATE_HEADER_AND_LINES and UPDATE_HEADER_ONLY in the route priority chain. Previously SEND_FOR_APPROVAL was the last check before REPLY_ONLY; if the message carried enrichable order data (e.g., from memory hydration), it could incorrectly route to an update instead of approval submission.
- `1.0 Ai Agent - Sales Agent` system prompt — added explicit SEND_FOR_APPROVAL case to the ORDER ACTION CONTEXT section. Sam must: (a) on `backend_success=true` say the order has been sent for approval but NOT approved; (b) on `backend_success=false` explain what is missing using `backend_error`; (c) on `OrderAction=REPLY_ONLY` when customer asked to send for approval, not claim any submission happened — instead explain what is needed or say the details need to be confirmed first.

Reason:

Live test with "Yes, please send it for approval" showed `send_for_approval_intent = false` because the previous regex required the exact phrase "send for approval" without any intervening words. Sam routed to REPLY_ONLY and incorrectly told the customer "Your draft order will be sent for approval now" — a false statement since no backend action ran.

Expected outcome:

"Yes, please send it for approval", "send it through", "please submit my order" and similar phrasings all set `send_for_approval_intent = true`. If all prerequisites are met, the route goes to SEND_FOR_APPROVAL. Sam only confirms approval submission after backend confirms success.

Status: live-reverified 2026-04-30. Test phrase "Yes, please send it for approval" set `send_for_approval_intent = true`, routed to `SEND_FOR_APPROVAL`, returned `backend_success = true`, wrote Chatwoot `order_status = Pending_Approval`, and Sam replied that the order was sent for approval without saying it was approved.

### 2026-04-29 - Phase 1.4 — Wire Send For Approval From Sam

Type: `ADD`

Component: `modules/orders/order_service.py`, `1.0 - SAM - Sales Agent - Chatwoot`, `1.2 - Amadeus Order Steward`

Change:

- `modules/orders/order_service.py send_order_for_approval` — replaced the three separate status-block checks with a single `old_status != "Draft"` guard. Added prerequisite validation: `Payment_Method` must be `Cash` or `EFT`; `Customer_Name` must be non-empty; `Collection_Location` must be non-empty; at least one non-cancelled `ORDER_LINE` must exist for the order.
- `1.2 HTTP - Send for Approval` — added `neverError: true` to options so `400` backend errors are returned as data instead of throwing an exception and silencing Sam.
- `1.2 Set - Format Send for Approval Result` — changed `order_status` from hardcoded `"Pending_Approval"` to `$json.success === true ? 'Pending_Approval' : 'Draft'`. Changed `approval_status` to conditional. Added `backend_success` (boolean) and `backend_error` (string) fields so `1.0` can pass error context to Sam.
- `1.0 Code - Build Order State` — added `sendForApprovalIntent` detection from customer phrases (`send for approval`, `submit order`, `finalise order`, `confirm order`, `ready for approval`, `please submit`, `ready to submit`). Added `send_for_approval_intent` to `orderState`.
- `1.0 Code - Decide Order Route` — added `existingOrderStatus`, `paymentMethod`, `paymentMethodSet`, `sendForApprovalIntent`, and `sendForApprovalReady` variables. Added `SEND_FOR_APPROVAL` route: fires when intent is detected, draft exists, order is in Draft status, and payment method is set. If payment method is missing, falls through to `REPLY_ONLY` so Sam can ask the customer for Cash/EFT. Added `debug_send_for_approval_intent`, `debug_send_for_approval_ready`, `debug_payment_method_set` debug fields.
- `1.0 Switch - Route Order Action` — added SEND_FOR_APPROVAL rule at index 6. REPLY_ONLY shifted to index 7.
- `1.0` — four new nodes added: `Set - Build Send For Approval Payload` → `Call 1.2 - Send For Approval` → `HTTP - Set Chatwoot After Send Approval` → `Set - Restore Send For Approval Result` → `Merge - Final Replay Context` (index 1).
- `HTTP - Set Chatwoot After Send Approval` writes full attribute snapshot: uses `order_status` from `1.2` result (conditional: `Pending_Approval` on success, existing status on failure), clears `pending_action`, preserves `payment_method`.

Reason:

Phase 1.3 captured the payment method. Phase 1.4 completes the customer-initiated send-for-approval path. Sam can now route from customer message through `1.2` to the backend, which validates all prerequisites before changing the order status. Backend errors return a customer-safe path — Sam receives `backend_success: false` and `backend_error` and can explain what is missing.

Expected outcome:

When a customer says "please send for approval" (with payment method set, draft active, and order lines present), Sam routes to SEND_FOR_APPROVAL. The backend validates all prerequisites and moves the order to `Pending_Approval`. The Chatwoot attribute is updated to `order_status = Pending_Approval`. If the backend returns a 400 (e.g., payment method missing on the sheet), Sam receives the error message and can tell the customer what is needed. Sam never says the order is approved — only that it has been sent for approval.

Status: happy path live-verified 2026-04-30 with `ORD-2026-377DA3`. Remaining regression checks: missing `Payment_Method`, already `Pending_Approval`, and backend `400` customer-safe reply path.

### 2026-04-29 - Phase 1.3 — Payment Method Capture

Type: `ADD`

Component: `modules/orders/order_service.py`, `1.0 - SAM - Sales Agent - Chatwoot`, `1.2 - Amadeus Order Steward`, `1.1 - SAM - Sales Agent - Escalation Telegram`

Change:

- `modules/orders/order_service.py update_order` — accepts `payment_method` field. Validates value must be `Cash` or `EFT`. Rejects update if `Order_Status` is not `Draft`. Maps to `Payment_Method` column in `ORDER_MASTER`.
- `1.0 Code - Normalize Incoming Message` — reads `payment_method` from `conversation.custom_attributes` and exposes it as `PaymentMethod`.
- `1.0 Code - Build Order State` — detects payment method keywords in the current message (`cash` → `Cash`, `eft`/`bank transfer`/`electronic transfer`/`internet banking` → `EFT`). Adds `payment_method` (from stored attribute) and `detected_payment_method` (from current message) to `order_state`. Includes `detectedPaymentMethod !== ""` in `messageHasNewUsefulInfo`.
- `1.0 Code - Build Enrich Existing Draft Payload` — forwards `detected_payment_method` as `payment_method` in the enrich payload when it is `Cash` or `EFT`. Includes it in `sentFieldCount` and return.
- `1.0` — all Chatwoot attribute write nodes updated to include `payment_method` in every write: `HTTP - Set Conversation Order Context`, `HTTP - Set Conversation Context After Update`, `HTTP - Clear Pending After Cancel`, `HTTP - Set Pending Cancel Action`, `HTTP - Clear Pending Action`, `HTTP - Set Conversation Human Mode`.
- `1.0 HTTP - Set Conversation Context After Update` — new update/enrich-path Chatwoot mirror node. It writes the full attribute snapshot after `update_order`, using the newly captured payment method before falling back to the previously stored Chatwoot value.
- `1.0 Edit - Build Ticket Data` — adds `WebPaymentMethod` field from `Code - Normalize Incoming Message`.
- `1.0 Google Sheet - Append row in sheet` — adds `WebPaymentMethod` to `columns.value` and schema.
- `1.2 Code - Normalize Order Payload` — adds `payment_method: clean(input.payment_method)`.
- `1.2 Code - Build Update Order Payload` — forwards `payment_method` to `patch_body` when it is `Cash` or `EFT`. Includes in `updatableFieldCount`.
- `1.1 Release Conversation to Auto` — adds `payment_method: $('Get Ticket Detail').item.json.WebPaymentMethod || ""` to the Chatwoot attribute snapshot.

Reason:

Payment method (`Cash` or `EFT`) is required before `send_for_approval` (Phase 1.4). It must be captured from the customer conversation, stored on `ORDER_MASTER`, and mirrored to Chatwoot so it survives across escalation and multi-turn conversations. The VAT treatment on quotes and invoices depends on this field.

Expected outcome:

When a customer says "I'll pay cash" or "EFT", Sam detects it via `Code - Build Order State`, routes through `ENRICH_EXISTING_DRAFT`, and the backend stores `Payment_Method = Cash` (or `EFT`) on `ORDER_MASTER`. All Chatwoot attribute writes preserve the value so it is not erased by later turns. The field survives escalation via `WebPaymentMethod` in `Sales_HumanEscalations`.

Status: live-verified 2026-04-29. Cash and EFT capture both update `ORDER_MASTER.Payment_Method` and Chatwoot `payment_method`; next-turn readback works; cancel-pending and escalation preserve the field; backend lock guard returns `400` and leaves the sheet value unchanged once the order is beyond `Draft`; no-draft handling does not write payment method without an active order.

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
