# Next Steps

## Purpose

Defines the approved build order from this point forward.

**Process (phases only, testing, when to involve Claude Code):**  
`docs/00-start-here/HOW_WE_WORK.md` — includes an editable **working position** table so you can see **which subsection we are on** without skipping ahead.

## Core Rule

Stabilize live order behavior before expanding features or polishing the app.

Orders are the profit section. They must be reliable before the system grows.

### Staying on track (Cursor + Claude Code)

- **Single roadmap:** This file (`NEXT_STEPS.md`) is authoritative for **what comes next**. Open it at the start of every session; pick **one subsection** as scope unless you consciously expand it. **Do not jump to a later phase** because a new bug showed up — park it under the correct phase here (see **`HOW_WE_WORK.md`**).
- **Where we are:** Update the table in **`docs/00-start-here/HOW_WE_WORK.md`** §1 when you finish or repoint work.
- **Claude Code review:** **Not** required for every change. Use **`CLAUDE_REVIEW_HANDOFF.md`** mainly for **big / cross-cutting** edits; Cursor should **remind you** when that bar is met (see **`HOW_WE_WORK.md` §3** and **`CLAUDE.md`**).
- **Testing:** Scripted runs use **message order and required facts**, not rigid exact phrases — **`HOW_WE_WORK.md` §4**. Optional **random human smoke** when Cursor calls for it.
- **Scratch only:** **`planning/ToDoList.md`** must not drift into a competing plan — move items here, then shorten the scratch file.

Discovering overlapping problems is normal on a layered system; **prioritisation is not “more problems forever” but one phase subsection at a time.**

### Verified recently (pipeline hardening — May 2026)

- Live-verified: Test A sex-only enrich (`UPDATE_HEADER_AND_LINES`), Test B `get_order_context` with `active_line_count` / `line_count_includes_cancelled`. Test C (partial stock on first-turn create): steward data was correct; Sam wording fixed in repo **2026-05-08** (`partial_stock_detail`, `partial_fulfillment` on create path, prompt rules). **Test D — partial-stock multi-band (`primary_1` + `nearby_band_*`):** deterministic **`last_agent_offer.caps`** from **`sam_text_parse`** (**weaners** bullets, **`more in … kg ranges`**, no duplicate **`reThereAre`/`reAvail`**) plus **`Build Order State`** / **`Build Sync Existing Draft Payload`** enrich — **live-verified** end-to-end (WhatsApp: 3× primary band + 2× + 2× adjacent → 7 lines intent). **Order Intent Extractor (LLM)** remains optional; on n8n Cloud OpenAI-from-Code may fail — routing still works when regex caps are complete. Re-import **`1.0`** from repo; checklist **`docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/extractor-pipeline/README.md`** (includes **Extractor LLM design contract**). Changelog **`docs/04-n8n/CHANGELOG.md`** (2026-05-08 multi-band entry). Rollback extractor only: **`EXTRACTOR_ENABLED=false`**.

### Deploy note — 2026-05-07 (repo ready; import required)

The repo now includes: **partial line sync** (short stock still creates lines), **`GET /api/orders/<id>` exposes `payment_method`**, **`1.2` action `get_order_context`**, and **`1.0` prefetch** so draft header/payment can merge before `Code - Build Order State`. Re-import `docs/04-n8n/workflows/1.2 - order-steward/workflow.json` and `1.0 - Sam-sales-agent-chatwoot/workflow.json` into n8n, then deploy the Flask app so Render serves the backend changes. See `docs/04-n8n/CHANGELOG.md` (2026-05-07 entry) for the full checklist.

## Phase 1: Order Lifecycle Stabilization

Goal: make reject, cancel, release, and reservation state safe.

### 1.1 Fix Reject Behavior - Complete

Required outcome:

- rejecting an order updates header status
- linked reserved order lines are released/cancelled
- reserved pigs become available again through the sheet/formula chain
- `ORDER_STATUS_LOG` records the rejection
- Sam/web app receive a clear backend result

Current status:

- backend code cancels linked non-cancelled/non-collected lines
- backend code resets `Reserved_Pig_Count` to `0`
- backend code blocks completed orders from rejection
- live Google Sheets verification passed
- `SALES_AVAILABILITY` recovers correctly
- `ORDER_STATUS_LOG` entry is written

### 1.2 Add Customer Cancel Action - Complete And Live-Verified

Required outcome:

- add a backend cancel action/endpoint
- use `Order_Status = Cancelled`
- use `Approval_Status = Not_Required`
- use `Payment_Status = Cancelled`
- release/cancel linked lines
- write `ORDER_STATUS_LOG`
- expose through `1.2 - Order Steward` only after backend behavior is working

Current status:

- backend route `POST /api/orders/<order_id>/cancel` is implemented
- backend code cancels linked non-cancelled/non-collected lines
- backend code resets `Reserved_Pig_Count` to `0`
- backend code blocks completed orders from cancellation
- backend code keeps already rejected orders from being converted to customer-cancelled
- backend behavior was live-verified for line cancellation, reserved count recovery, availability recovery, and status log writing
- `1.2 - Order Steward` now exposes `cancel_order`
- `1.0 - Sam Sales Agent` now has guarded `CANCEL_PENDING`, `CANCEL_ORDER`, and `CLEAR_PENDING` routes
- two-turn Chatwoot cancellation is live-verified
- Chatwoot attribute preservation through escalation and human reply is live-verified
- cancellation after escalation is live-verified

### 1.2c Sync Order Lines After Draft Creation - Complete And Live-Verified

Required outcome:

- complete first-turn order requests create `ORDER_MASTER`
- if `requested_items[]` exists, the new draft immediately syncs matching `ORDER_LINES`
- Sam replies only after the draft and requested line sync path have completed
- no Merge node deadlock is introduced
- sync failure has a safe reply path and does not silently drop the customer

Current status:

- `1.0 Set - Draft Order Payload` sends `action = create_order_with_lines` when `order_state.requested_items[]` is non-empty
- `1.0` still owns routing only; it no longer contains the superseded Option A post-create sync branch
- `1.2 - Order Steward` owns the atomic create + sync branch
- `1.2 Code - Format Create With Lines Result` returns `success = true` only when both create and sync succeed
- live WhatsApp-to-Sheets verification passed on 2026-04-29 with `ORD-2026-879091`
- `ORDER_MASTER` had the new Draft order and `ORDER_LINES` had 3 matching Draft / Not_Reserved rows
- Sam referenced the order ID in the final reply on rerun

Follow-up, separate from Fix C:

- slim the Sales Agent prompt payload with a dedicated reply-context node so Sam receives only the fields needed for customer wording

### 1.3 Capture Payment Method Before Approval — Complete And Live-Verified

Manual prerequisites confirmed:
- `ORDER_MASTER` column Y = `Payment_Method` — added manually.
- `Sales_HumanEscalations` column S = `WebPaymentMethod` — added manually.

Required outcome:

- Sam asks the customer for Cash or EFT as part of order finalization, before offering to send for approval
- Payment method is stored on `ORDER_MASTER` via backend `PATCH /api/master/orders/<order_id>` — this is the source of truth
- Payment method is mirrored to Chatwoot `custom_attributes.payment_method` after backend success so future turns can read it without a backend lookup
- `Code - Normalize Incoming Message` in `1.0` reads `payment_method` from Chatwoot custom_attributes alongside `order_id`, `order_status`, and `pending_action`
- Payment method capture routes through the existing `ENRICH_EXISTING_DRAFT` path — no new Switch branch needed
- `Code - Build Enrich Existing Draft Payload` is updated to include `payment_method` when present
- All Chatwoot attribute write nodes in `1.0` and `1.1` must be audited and updated to include `payment_method` in their full-object snapshot before import — see `CHATWOOT_ATTRIBUTES.md`

Current status:

- backend `PATCH /api/master/orders/<order_id>` accepts `payment_method = Cash|EFT`
- backend writes `ORDER_MASTER.Payment_Method`
- backend rejects `payment_method` changes once the order is beyond `Draft`
- `1.0` detects `Cash` and `EFT`, routes through the existing enrich/update path, and mirrors `payment_method` to Chatwoot after backend success
- new `HTTP - Set Conversation Context After Update` writes the full Chatwoot snapshot after update/enrich paths
- `1.1` preserves `payment_method` through human reply release using `Sales_HumanEscalations.WebPaymentMethod`
- live verification passed on 2026-04-29 for Cash, EFT, next-turn readback, cancel-pending preservation, backend lock guard, no-draft handling, and escalation preservation

### 1.4 Wire Send For Approval From Sam — Complete And Live-Verified

Required outcome:

- Sam checks for active draft, at least one order line, and payment method before routing
- if any required field is missing, Sam tells the customer what is needed before proceeding
- `1.0` adds a `SEND_FOR_APPROVAL` branch to `Code - Decide Order Route`
- `1.0` calls `1.2` with `action=send_for_approval`
- `1.2 send_for_approval` branch calls backend `POST /api/orders/<order_id>/send-for-approval`
- backend validates: `Order_Status = Draft`, at least one ORDER_LINE, `Payment_Method` set, `customer_name` set, `collection_location` set
- `1.0` writes updated `order_status` to Chatwoot custom_attributes after backend confirms
- Sam tells the customer the order has been sent for approval — Sam does NOT say it is approved
- backend errors must return a customer-safe reply path in n8n; Sam must not go silent if a backend safety guard returns `400`

Current status:

- backend `send_order_for_approval` now validates: `Order_Status = Draft` (single clear check), `Payment_Method = Cash|EFT`, `Customer_Name` non-empty, `Collection_Location` non-empty, at least one non-cancelled `ORDER_LINE`
- backend returns clear `ValueError` messages for each guard that fails; route returns `400` with the message
- `1.2 HTTP - Send for Approval` has `neverError: true` so `400` responses are handled as data, not exceptions
- `1.2 Set - Format Send for Approval Result` returns conditional `order_status` (`Pending_Approval` on success, `Draft` on failure), conditional `approval_status`, and `backend_success`/`backend_error` fields
- `1.0 Code - Build Order State` detects `send_for_approval_intent` from customer phrases (send for approval, submit order, finalise order, confirm order, etc.)
- `1.0 Code - Decide Order Route` adds SEND_FOR_APPROVAL route: fires when `send_for_approval_intent + has_existing_draft + order_status = Draft + payment_method set`; falls through to REPLY_ONLY if payment method is missing (Sam sees the intent and asks for Cash/EFT)
- `1.0 Switch - Route Order Action` has new rule at index 6 for SEND_FOR_APPROVAL (REPLY_ONLY shifted to index 7)
- `1.0` new nodes: `Set - Build Send For Approval Payload` → `Call 1.2 - Send For Approval` → `HTTP - Set Chatwoot After Send Approval` → `Set - Restore Send For Approval Result` → `Merge - Final Replay Context` (index 1)
- Chatwoot write uses conditional order_status from 1.2 result — on success writes `Pending_Approval`, on failure preserves existing status
- all 4 new 1.0 nodes wired and JSON validated (83 nodes)
- Phase 1.4 bugfix expanded `send_for_approval_intent` detection to cover natural phrasings such as `send it for approval`, `send this through`, and `submit my order`
- live verification passed on 2026-04-30 with `ORD-2026-377DA3`: `send_for_approval_intent = true`, `order_route = SEND_FOR_APPROVAL`, `backend_success = true`, `order_status = Pending_Approval`, Chatwoot `order_status = Pending_Approval`, and Sam correctly said the order was sent for approval, not approved

Regression checks:

- missing `Payment_Method` should produce a customer-safe reply and no backend status change — failed in live test, then fixed and live re-tested 2026-05-04: routing stayed `REPLY_ONLY`, `reply_instruction` forced the payment-method question, Sam asked for Cash/EFT, backend was not called, and Draft status was preserved
- already `Pending_Approval` orders should not be submitted again — passed in live regression
- backend `400` guard failures should return a customer-safe reply rather than silence — passed in live regression 2026-05-04: backend rejected missing `Collection_Location`, Sam asked for the collection location, and did not claim the order was sent

Phase 1.4 fix applied and live re-tested 2026-05-04 — approval preflight block:

- `Code - Decide Order Route` now detects `send_for_approval_intent = true` with `sendForApprovalReady = false` and sets `reply_instruction` before the item reaches the Sales Agent
- missing-fields list is built from local checks; currently checks `payment_method`; future checks (no draft, wrong status) can be added in the same block
- when `payment_method` is missing: `reply_instruction = "INSTRUCTION: ... Ask exactly one question: Cash or EFT?"`
- order_route remains `REPLY_ONLY`; backend is not called; order_status is not changed; Draft is preserved
- `REPLY_ONLY` block in Sales Agent system message updated to honour `ReplyInstruction` as a hard override (mirrors the same rule already in the `SEND_FOR_APPROVAL` block)
- debug fields added: `debug_approval_preflight_blocked`, `debug_approval_missing_fields`
- no new Switch branches added
- backend `400` failures on the `SEND_FOR_APPROVAL` path are handled through `backend_success = false`, `backend_error`, and `reply_instruction`, preserving `Draft` status and producing a customer-safe reply

### 1.5 Lifecycle Guards — Complete And Live-Verified

Required outcome:

- backend rejects `Payment_Method` updates once `Order_Status` is `Pending_Approval` or later (`update_order` / `PATCH` master order)
- Sam-side routing in `1.0` checks `order_status` before sending `send_for_approval` — does not call backend if status is already `Pending_Approval`, `Approved`, `Cancelled`, or `Completed`
- completed orders cannot be cancelled or rejected without deliberate admin action (`reject_order` and `cancel_order` block `Completed`)
- cancelled orders cannot be re-approved (`approve_order` only accepts `Pending_Approval`, so `Cancelled`, `Draft`, and other statuses are rejected)
- reserved orders handle state rollback safely when cancel or reject is applied (reject/cancel line cleanup and `Reserved_Pig_Count` reset)

Follow-up deferred to later phases (not part of Phase 1.5 closure):

- approval auto-reservation — **Phase 1.8** after **Phase 1.6**; until then reservation stays a separate manual step (web app or workflow calling `POST /api/orders/<order_id>/reserve`)
- post-Phase 1.6: optional `approve_order` then reserve with `reserve_warning` on partial failure — **Phase 1.8**
- customer notification after approval/rejection — **Phase 1.9** (outbound n8n + webhook), not Sam `1.0`

Current status:

- backend `approve_order()` restricted to `Pending_Approval` only — live-verified 2026-05-04 (Draft cannot be approved via API; `Pending_Approval` approves successfully)
- backend payment method lock beyond `Draft` — implemented (see Phase 1.3 verification)
- Sam `send_for_approval` guarded to `Draft` — in place with Phase 1.4 regressions live-verified
- reject and customer-cancel paths block `Completed` and cancel/release linked lines as documented

### 1.6 Harden Reserve And Release Behavior - Complete And Live-Verified

Required outcome:

- reserve order lines should handle larger/multi-line orders without partial silent failure
- release should be safe to call more than once
- release should not affect unrelated orders
- cancelled/invalid lines should not remain reserved
- reserved count must match real reserved lines
- backend/web app should return a clear success/failure summary for each line
- if approval auto-reserves lines, reserve behavior must be hardened before or as part of that change

Current status — **Complete and live-verified** (backend + sheets 2026-05-05; order-detail banner messaging 2026-05-06):

- `reserve_order_lines` refactored: eligibility checks skip `Cancelled`/`Collected` lines, lines with no `Pig_ID`, and noop already-reserved lines; all ORDER_LINES mutations applied in one `batch_update_rows_by_id` call; response includes `line_results` (per-line action/reason), `changed_count` (rows written), and `warning` when some lines were skipped; `success = false` + HTTP 422 when nothing could be reserved
- `release_order_lines` refactored: only clears `Reserved_Status` where `Reserved`; only reverts `Line_Status` from `Reserved` to `Draft` for active (non-Cancelled) lines; `Collected` lines are skipped; idempotent (second call returns all noops); `Reserved_Pig_Count` set from actual post-release count via `_count_reserved_lines`; response includes `line_results` and `changed_count`
- `order_routes.py`: reserve route returns HTTP 422 when `success = false`; `errors` field present for UI consumption
- Docs updated: `API_STRUCTURE.md`, `ORDER_LOGIC.md`
- **Web app** (`static/js/orderDetail.js`): reserve/release success copy uses API `result.message` plus explicit `changed_count` (and `warning` when present). Operator re-check: first reserve shows row count + skip warning; second reserve shows “already reserved” + zero rows + same warning; first release shows row count; second release shows “no active reservations” + zero rows.

Verification notes (six tests):

- Mixed lines: reserve showed combined `warning` (terminal skips + no pig); two lines reserved as expected (UI summary: Reserved 2, Draft 1).
- Second reserve: success message now includes API text plus **explicit `changed_count`** (zero rows updated = idempotent noop is obvious in the banner).
- Release: success message; lines returned to draft-style summary (e.g. Draft 3; grower count unchanged).
- Second release: unchanged sheet state — banner now states **zero rows updated** explicitly (idempotent release).
- All-ineligible order: customer-safe `errors` message; order header counts remained consistent; HTTP 422 path confirmed.
- `SALES_AVAILABILITY` correct after release.

Manual verification checklist:

- [x] Order with 5 lines (2 cancelled, 1 no pig, 2 valid) → reserve → `line_results` has 5 entries; `changed_count = 2`; `warning` mentions 3 skipped; `reserved_pig_count = 2`
- [x] Call reserve again on same order → all 2 valid lines noop; `changed_count = 0`; `success = true`
- [x] Release → `line_results` shows 2 released, 3 noop/skipped; `reserved_pig_count = 0`; ORDER_MASTER count updated
- [x] Call release again → all noop; `changed_count = 0`; `success = true`; no sheet corruption
- [x] Order with no eligible lines (all cancelled) → reserve → `success = false`; HTTP 422; `errors` present
- [x] `SALES_AVAILABILITY` recovers reserved pigs after release

Web app closure (Phase 6-style polish, shipped with 1.6 sign-off — **verified 2026-05-06**):

- Order detail reserve/release successes use the API `result.message`, then append an explicit sentence for `changed_count` (`0` = no ORDER_LINES rows written; `N` = how many rows were updated). `warning` is appended after that when the API returns it.

### 1.7 Slim Sales Agent Reply Payload — Complete And Live-Verified

Current status: **complete** — WhatsApp minimal checklist (AUTO+draft + CLARIFY) passed **2026-05-07**.

Required outcome:

- add a dedicated reply-context shaping node before `Ai Agent - Sales Agent`
- remove raw Chatwoot webhook data, large debug fields, and sync internals from Sam's prompt
- keep only customer context, order action, order ID/status, backend success, sync success, slim order state, and reply instruction
- preserve full diagnostic data in earlier workflow nodes

Implementation notes:

- new node `Code - Slim Sales Agent User Context` added at canvas position [4336, -272] in `1.0` workflow
- all four main input paths (CLARIFY from `Switch - Clarify or Auto`; REPLY_ONLY from `Switch - Route Order Action` output index 7; `Merge - Final Replay Context`; `Merge - Draft Result With Reply Context`) rewired through the new node before reaching `Ai Agent - Sales Agent`
- node produces `sam_order_state_slim` (whitelisted order_state fields) and `sam_steward_result_compact` (short backend result)
- Sales Agent `text` prompt updated: `OrderState:` replaced with `OrderStateSummary:` + `StewardCompact:`
- Sales Agent `systemMessage` updated: OrderState paragraph replaced with OrderStateSummary paragraph; added "never treat OrderStateSummary as raw tool output" rule; CREATE_DRAFT section updated to reference OrderStateSummary
- workflow JSON validated post-edit (ConvertFrom-Json passed)
- docs updated: `DATA_FLOW.md` (new §1.0 Sales Agent Input Contract), `README.md` (node 31a, rewired connections)

**Live verification checklist (WhatsApp — minimal, Phase 1.7 only)**

*Goal:* Confirm Sam still behaves correctly when the Sales Agent prompt uses **`OrderStateSummary`** + **`StewardCompact`** only (no regression from the old fat `OrderState` dump). **Paraphrase every customer line** — these are ordered steps, not fixed scripts.

**Before you start**

- [x] **`1.0`** in n8n matches repo (import `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/workflow.json` if unsure).
- [x] Test on the real **Sam – WhatsApp** inbox you ship with.

**A — AUTO + draft / steward path (required)**

One thread. Walk through enough detail that the workflow reaches **draft create or draft enrich** (e.g. category, weight band, qty, collection site, timing, payment — in whatever order Sam asks; your wording can vary).

- [x] Sam’s replies stay **coherent** (understands thread; no obvious “empty state” confusion).
- [x] Where the backend creates/updates a draft, the customer-visible reply reflects it (**order id** or clear draft acknowledgement — same bar as before 1.7).
- [x] **No duplicate** Sam messages for a **single** customer message.
- [x] Sam does **not** re-ask for facts already established in the same thread unless the customer changes them.

**B — CLARIFY path (required)**

Same or **new** thread. Send something that should trigger **CLARIFY** (vague one-liner, incomplete spec, or benign off-topic — your choice of style).

- [x] Sam responds appropriately (**one** main clarifying steer or polite boundary), not gibberish or stuck loops.

**C — Remaining input paths (optional if A+B pass and time is short)**

The slim node sits on **four** paths. If something in daily ops naturally hits **REPLY_ONLY** / replay-style routing, note it; otherwise skip — **A+B passing** is the minimal bar for sign-off.

**Optional technical confirm (nice-to-have)**

- [ ] In n8n **Executions**, pick a run from steps A/B: **`Code - Slim Sales Agent User Context`** executes immediately before **`Ai Agent - Sales Agent`** for that branch.

**Sign-off:** **§1.7** closed **2026-05-07**; working position updated in **`HOW_WE_WORK.md`** §1.

### 1.8 Approval Auto-Reservation - Complete And Live-Verified

**Prerequisite:** Phase **1.6** is **closed** (reserve/release behaviour, per-line summaries, HTTP 422 on no-op reserve, web banner copy—all live-verified). Phase **1.7** is **closed** (slim Sales Agent input live-verified **2026-05-07**).

**Current status:** Complete and live-verified on 2026-05-09.

Required outcome:

- implement reserve-on-approve knowing reserve/release semantics are already hardened and failure summaries are clear in the API + order detail UI
- `approve_order` should set the approval state first, then attempt to reserve active order lines
- if reservation fails or partially fails, do not roll back the approval; write a warning to `ORDER_STATUS_LOG`, return `reserve_warning`, and let the admin web app surface the manual follow-up
- auto-reserve should ignore cancelled/inactive lines and report per-line outcomes clearly

Documentation / schema guard before implementation:

- verify the live Google Sheet headers against `docs/03-google-sheets/sheets/ORDER_MASTER.md`, `ORDER_LINES.md`, and `ORDER_STATUS_LOG.md` before writing code that depends on row position or log columns
- `ORDER_MASTER.Payment_Method` is already a live manually added column for Phase 1.3; do not remove or reorder it when checking approval behavior
- `ConversationId` was intentionally handled in Phase 1.9, not Phase 1.8

Verification notes:

- approve an order with all active lines eligible and confirm the order moves to `Approved` and lines become reserved
- approve an order with mixed active/cancelled/no-pig lines and confirm skipped lines are reported without rolling back approval
- approve an order where reservation returns a failure or warning and confirm `reserve_warning` is returned, `ORDER_STATUS_LOG` records the manual follow-up, and the web app can show the warning
- confirm `Reserved_Pig_Count` matches actual reserved lines after approval auto-reservation

Implementation note:

- backend and web-app support for reserve-on-approve has been added in repo
- live Google Sheets verification passed for a mixed-line order on 2026-05-09: `ORD-2026-102250` moved from `Pending_Approval` to `Approved`, one active draft line was reserved, one cancelled line was skipped as `terminal_line_status`, `Reserved_Pig_Count` became `1`, and `ORDER_STATUS_LOG` recorded both approval and the manual follow-up warning
- clean all-eligible approval path passed on 2026-05-09: `ORD-2026-7C79A8` moved to `Approved`, both active lines became `Reserved`, `Reserved_Pig_Count = 2`, and no `reserve_warning` was returned
- all-ineligible/no-reservation warning path passed on 2026-05-09: `ORD-2026-0FB697` moved to `Approved`, cancelled lines stayed cancelled/not reserved, `Reserved_Pig_Count = 0`, `reserve_warning = "No lines could be reserved."`, and `ORDER_STATUS_LOG` recorded the manual follow-up

### 1.9 Outbound Approval/Rejection Notifications - Complete And Live-Verified

Required outcome:

- create a separate outbound n8n workflow, planned as `1.4 - Outbound Order Notification`, for backend-driven customer messages after human approval or rejection
- backend should call `ORDER_NOTIFICATION_WEBHOOK_URL` after successful `approve_order` or `reject_order`
- webhook delivery should be non-blocking with a short timeout; backend should log a warning if notification delivery fails, not fail the order transition
- notification workflow should find the Chatwoot conversation from `ConversationId` on `ORDER_MASTER`
- store incoming `conversation_id` on `ORDER_MASTER.ConversationId` at draft creation time
- use the agreed generic message texts:
  - approval: `Your order has been approved. We have reserved the pigs linked to your order and will keep you posted on the next step.`
  - rejection: `Your order was reviewed, but we cannot approve it at this stage. We will follow up if there is another suitable option.`

Implementation status:

- live `ORDER_MASTER` has `ConversationId` as column 26 after `Payment_Method`
- backend stores `conversation_id` from new order payloads
- backend notification helper has been added for approval/rejection and does not roll back the order transition if delivery fails
- draft `1.4 - Outbound Order Notification` workflow docs/export have been added under `docs/04-n8n/workflows/1.4 - outbound-order-notification/`
- direct `1.4` webhook smoke test passed on 2026-05-09 with `conversation_id = 1742` and returned `sent = true`
- backend approval notification path passed on 2026-05-09: `ORD-2026-36CDE4` moved from `Pending_Approval` to `Approved`, one line reserved, `Reserved_Pig_Count = 1`, and `customer_notification_sent = true`
- backend rejection notification path passed on 2026-05-09: `ORD-2026-C3CEDF` moved from `Pending_Approval` to `Cancelled | Rejected`, one line cancelled/released, `Reserved_Pig_Count = 0`, and `customer_notification_sent = true`
- production backend must keep `ORDER_NOTIFICATION_WEBHOOK_URL=https://charln.app.n8n.cloud/webhook/order-notification` configured so deployed app approvals/rejections continue sending notifications

## Phase 2: Quote And Invoice Generation

Goal: backend generates quote and invoice documents. n8n delivers them only.

### 2.1 Design Document Schema - Complete For Implementation Planning

Required outcome:

- define what fields appear on a quote (order ID, customer name, line items with ex-VAT unit price, quantity, line total, VAT amount, grand total, payment method, collection location, quote number, quote date)
- define what fields appear on an invoice (same as quote plus invoice number, approval date)
- define numbering format for quotes and invoices (sequential, stored in a backend counter or dedicated sheet)
- define output format (PDF preferred) and storage/retrieval path
- document VAT calculation rule: `EFT` orders add 15% on top of ex-VAT line totals; `Cash` orders show ex-VAT totals as final
- confirm `ORDER_LINES.Unit_Price` is stored at line creation time — if not, add it before quote generation is built

Design draft:

- see `docs/02-backend/QUOTE_INVOICE_DESIGN.md`
- proposed direction: backend generates PDFs, uploads to Google Drive, records metadata in `ORDER_DOCUMENTS`, and n8n delivers only after backend generation succeeds
- proposed configurable business rules: future `SYSTEM_SETTINGS` sheet, including `quote_valid_days`, `vat_rate`, bank details, business details, and Drive folder IDs
- proposed references: full document refs (`Q-YYYY-XXXXXX`, `INV-YYYY-XXXXXX`) plus short customer payment ref (`XXXXXX`)
- proposed Drive filenames: `QUO_YYYY_MM_DD_XXXXXX_VN_(R10,580.00)_EFT.pdf` and `INV_YYYY_MM_DD_XXXXXX_VN_(R10,580.00)_EFT.pdf`

Open before implementation:

- create `SYSTEM_SETTINGS` and `ORDER_DOCUMENTS` through an admin setup script/backend setup utility
- use provided Google Shared Drive quote/invoice folder IDs
- include quote versioning in the first implementation
- require an existing generated quote before invoice generation
- invoice generation uses the latest non-voided quote version
- quote generation is allowed while an order is still `Draft`
- recommended Drive strategy: keep generated PDFs restricted; n8n uses authenticated Google Drive access to download by file ID and send as Chatwoot attachment
- n8n can be given authenticated Google Drive access to download generated PDFs by file ID
- Draft quotes should show a visible note: `Draft quote - subject to availability and approval`
- no remaining Phase 2.1 design questions before implementation planning

### 2.2 Document Infrastructure Setup - Complete And Live-Verified

Required outcome:

- create `SYSTEM_SETTINGS` and `ORDER_DOCUMENTS` through an admin setup script/backend setup utility
- document both sheets under `docs/03-google-sheets/sheets/`
- seed required settings:
  - `quote_valid_days`
  - `vat_rate`
  - business header fields
  - bank details
  - quote Drive folder ID
  - invoice Drive folder ID
- move/copy canonical logo asset to `static/document-assets/amadeus-logo.png`
- add backend helpers for settings reads and document-register writes
- verify live sheets exist with expected headers before building quote generation

Implementation order:

1. Add documented sheet schemas for `SYSTEM_SETTINGS` and `ORDER_DOCUMENTS`. - Done
2. Add `scripts/setup_document_infrastructure.py` to create missing sheets/headers and seed settings. - Done
3. Run the setup utility only after explicit approval because it writes to live Google Sheets. - Done 2026-05-09; created both live sheets and seeded 18 settings
4. Move/copy the canonical logo asset into the agreed runtime path. - Done: `static/document-assets/amadeus-logo.png`
5. Add backend helper functions in `modules/documents/document_service.py` that read settings and append/update document records. - Done
6. Add/verify Google Drive upload helper. - Done in `services/google_drive_service.py`; Shared Drive upload live-verified 2026-05-10
7. Choose the PDF generation library/approach for 2.3. - Proposed: ReportLab backend PDF rendering, dependency added at 2.3 implementation time

Drive upload verification:

- service account has folder access after sharing, but Google Drive returns `403` because service accounts do not have storage quota in normal My Drive folders
- resolution selected: use Google Shared Drive folders created from the Amadeus Workspace account and add the service account as content manager
- quote Shared Drive folder ID: `1r7oqIDMwZZi5T7BxC31y7UGNzn8Ud9ys`
- invoice Shared Drive folder ID: `1_kbfX69s6yeb-Zfdcpu5jse8H30HvLGr`
- live `SYSTEM_SETTINGS` was updated with the Shared Drive folder IDs on 2026-05-10
- live upload test passed on 2026-05-10: `PHASE_2_2_SHARED_DRIVE_UPLOAD_TEST.txt` uploaded to the quote folder with file ID `17HtPAumE9XJf2e8xtvQsTb0YpwCtEncI`

### 2.3 Backend Quote Endpoint - Complete And Live-Verified

Required outcome:

- backend endpoint generates quote document for a given `order_id` - Done: `POST /api/orders/<order_id>/quote`
- uses `ORDER_MASTER.Payment_Method` to determine VAT treatment - Done
- uses stored `ORDER_LINES.Unit_Price` (ex-VAT) for line calculations - Done; active lines with missing/zero price are rejected
- locks and stores the VAT rate on the quote record at generation time - Done
- returns document URL or file reference - Done
- supports quote versions (`V1`, `V2`, etc.) - Done
- allows quote generation while an order is still `Draft` - Done
- adds visible draft note when generated from `Draft`: `Draft quote - subject to availability and approval` - Done
- uploads PDF to the configured quote Drive folder - Done
- records metadata in `ORDER_DOCUMENTS` - Done

Live test:

- 2026-05-10: generated quote for `ORD-2026-01E18A`
- result: `DOC-2026-49BF16`, `Q-2026-01E18A`, version `1`
- file: `QUO_2026_05_10_01E18A_V1_(R3,200.00)_Cash.pdf`
- Drive file ID: `1FA50hJUf7q41jKGX3trRcEceaJbfSLk1`
- totals: subtotal `R3,200.00`, VAT `R0.00`, total `R3,200.00`
- `ORDER_DOCUMENTS` row verified and Drive metadata verified as `application/pdf`

Additional close-out tests:

- visual PDF inspection passed by project owner on 2026-05-10
- V2 versioning passed on 2026-05-10 for `ORD-2026-01E18A`: `DOC-2026-E706A4`, `Q-2026-01E18A-V2`, `QUO_2026_05_10_01E18A_V2_(R3,200.00)_Cash.pdf`
- EFT/VAT quote passed on 2026-05-10 after approved test update of `ORD-2026-01E18A` payment method from `Cash` to `EFT`: `DOC-2026-45F259`, `Q-2026-01E18A-V3`, subtotal `R3,200.00`, VAT `R480.00`, total `R3,680.00`, file `QUO_2026_05_10_01E18A_V3_(R3,680.00)_EFT.pdf`
- note: `ORD-2026-01E18A` now has `Payment_Method = EFT` after the approved EFT quote test

### 2.4 Backend Invoice Endpoint - Complete And Live-Verified

Required outcome:

- backend generates invoice after order is approved - Done: `POST /api/orders/<order_id>/invoice`
- uses the VAT rate locked on the corresponding quote, not recalculated - Done
- returns document URL or file reference - Done
- requires an existing non-voided generated quote - Done
- uses the latest non-voided quote version - Done
- uploads PDF to the configured invoice Drive folder - Done
- records metadata in `ORDER_DOCUMENTS` - Done

Live test:

- 2026-05-10: `ORD-2026-01E18A` was promoted from `Draft | Pending` to `Approved | Approved` for the invoice test and logged to `ORDER_STATUS_LOG`
- invoice generated from latest non-voided quote `Q-2026-01E18A-V3`
- result: `DOC-2026-EC0265`, `INV-2026-01E18A`, version `1`
- file: `INV_2026_05_10_01E18A_V1_(R3,680.00)_EFT.pdf`
- Drive file ID: `1w5peZn-imS-t0p7BAwTd2fIWWGPg2Dgq`
- totals inherited from quote: subtotal `R3,200.00`, VAT `R480.00`, total `R3,680.00`
- `ORDER_DOCUMENTS` row verified and Drive metadata verified as `application/pdf`

### 2.5 n8n Delivery

Status: Complete And Live-Verified 2026-05-10.

Required outcome:

- backend exposes `POST /api/order-documents/<document_id>/send` - Done
- delivery request requires explicit `conversation_id`; there is no customer-conversation fallback - Done
- `1.5 - Outbound Document Delivery` workflow added under `docs/04-n8n/workflows/1.5 - outbound-document-delivery/` - Done
- n8n downloads the generated PDF using authenticated Google Drive access by file ID - Live-verified
- n8n delivers the PDF to Chatwoot as an attachment - Live-verified
- n8n does not calculate VAT, totals, references, or invoice eligibility - Done
- Phase 2.5 tests used Chatwoot `conversation_id = 1742` only - Done
- direct webhook smoke test sent quote `DOC-2026-45F259` and left `ORDER_DOCUMENTS.Document_Status = Generated` because it bypassed backend sent-state update - Verified
- backend endpoint test sent invoice `DOC-2026-EC0265` and marked `ORDER_DOCUMENTS.Document_Status = Sent` with `Sent_By = Codex Phase 2.5 Backend Test` - Verified

### 2.6 Web App Document Controls

Status: Complete And Browser-Verified.

Required outcome:

- order detail page shows a Documents section - Done
- show generated document history from backend/`ORDER_DOCUMENTS` - Done
- buttons for `Generate Quote` and `Generate Invoice` - Done
- `Generate Invoice` only appears or succeeds when the backend says the order is eligible - UI disables until an active quote exists and order is Approved/Completed; backend remains final guard
- delivery buttons for generated quote/invoice documents - Done
- delivery requires explicit Chatwoot conversation ID and confirmation - Done
- show document type, ref, version, total, payment method, status, created date, Drive link, and sent state - Done
- show clear missing-data errors without requiring direct sheet access - Done
- operators should be able to handle quote/invoice workflows from the web app, not from Google Sheets - First slice done
- order detail page now also includes an editable Order Header section for requested quantity/category/weight/sex, collection location, notes, and Draft-only payment method changes
- order summary section made cleaner and more operational: customer, status, totals, lines, reserved count, document count, payment, collection, request summary, and notes
- document tiles are compact by default with an expand/collapse control for filename, dates, delivery state, notes, Drive link, and send action
- order line tiles are compact by default with an expand/collapse control for full details and edit/delete controls
- web app totals no longer rely on `ORDER_OVERVIEW.Final_Total` where cancelled lines can be included; API exposes `active_line_total` and UI uses latest document total for payable amount

Follow-up usability improvements to plan after browser verification:

- add order-list filters/search by status, customer, and document state
- add safer admin controls for cancelling/rejecting with typed reasons
- add line-level replacement flow so an operator can swap pigs without manually deleting and re-adding
- add document void/supersede controls before production operators start regenerating many versions
- add audit/history view from `ORDER_STATUS_LOG` and document sent events

## Phase 3: Daily Order Summary

Goal: scheduled operational overview of current order state.

### 3.1 Backend Report Endpoint

Status: Implemented And Live Read-Only Verified 2026-05-10.

Required outcome:

- `GET /api/reports/daily-summary` returns counts and lists grouped by status: new drafts, drafts missing payment method, pending approval, approved, cancelled today, completed today, orders needing attention - Done
- endpoint is independently testable - Done, supports optional `?date=YYYY-MM-DD`
- n8n reads only from this endpoint, not from sheets directly - Ready for Phase 3.2
- live read-only test for `2026-05-10` returned `success = true` with all expected section keys
- invalid date test returns `400` with a clear validation error

### 3.2 n8n Scheduled Delivery

Status: Complete And Scheduled-Run Verified 2026-05-10.

Required outcome:

- n8n scheduled workflow fires daily at 16:00 Africa/Johannesburg - Ready to activate
- calls backend summary endpoint - Verified: `GET https://amadeus-pig-tracking-system.onrender.com/api/reports/daily-summary`
- formats output and sends to Telegram or email - Manual Telegram test verified
- MVP fallback is no longer needed because the backend report endpoint exists
- first 16:00 scheduled run confirmed: one Telegram message received

## Phase 4: Requested Item Sync Stabilization

Goal: make Sam's order-line sync reliable.

### 4.0 Sales Stock Formula Gate Alignment

Status: Open - live sheet inspected read-only 2026-05-10.

Issue:

- `SALES_AVAILABILITY` currently shows 23 sale-ready pigs.
- `SALES_STOCK_DETAIL`, `SALES_STOCK_SUMMARY`, and `SALES_STOCK_TOTALS` currently total 31.
- The 8-row difference is the hard-coded `Newborn` information row in the sales stock formulas. That row bypasses `SALES_AVAILABILITY` and counts `PIG_OVERVIEW` rows where `Is_Sale_Ready = No`, `Status = Active`, `Calculated_Stage = Newborn`, and `Weight_Band = N/A`.
- Live read-only check showed `PIG_OVERVIEW.Is_Sale_Ready = Yes` rows are all `Purpose = Sale`; no `Grow_Out` pigs were included in the current 23 sale-ready rows after the owner's sheet change.

Risk:

- Sam reads `SALES_STOCK_SUMMARY`, `SALES_STOCK_TOTALS`, `SALES_STOCK_DETAIL`, and `SALES_AVAILABILITY`. If sales stock totals include information-only animals, Sam may quote a higher broad total than the true sale-ready count unless the workflow/prompt treats `Status = Not for Sale` rows as informational only.
- This belongs before split-sync testing because bad availability totals can make Sam's stock wording look wrong even when backend line sync is behaving correctly.

Required outcome:

- Decide whether `Newborn` rows should remain visible in Sam's sales tools or move to a separate information-only tool/view.
- Ensure all sale-ready counts used by Sam and backend order matching come from `SALES_AVAILABILITY` only.
- Reconcile the live formulas with `docs/03-google-sheets/sheets/SALES_AVAILABILITY.md`, `SALES_STOCK_DETAIL.md`, `SALES_STOCK_SUMMARY.md`, and `SALES_STOCK_TOTALS.md`.
- Add a sheet changelog entry when the final formula/view decision is approved.

### 4.1 Fix Split Item Sync

Status: Complete And Live-Verified 2026-05-10.

**Where grower split / header-line symptoms slot in:** This subsection. **Phase 4.2** (partial-match behavior and customer-facing honesty) aligns when stock cannot satisfy **`requested_items`**; **Phase 5** covers Sam reading **backend-filtered** order truth for review prompts. Fixing “Sam said we have X” without fixing inventory alignment is incomplete — treat **prompt / reply rules** and **sync / header persistence** together for this incident class.

Required outcome:

- `primary_1`, `primary_2`, and future split keys remain stable
- male/female split requests write all expected rows
- repeated sync does not duplicate rows
- old lines are released/cancelled before replacement

**Engineering note (expected line keys):** `sync_order_lines_from_request` allocates **per `requested_items` entry**. If **`SALES_AVAILABILITY`** has **no pig** matching **primary_1** (e.g. Male in band), **`primary_1` creates no rows** (`no_match`), while **`primary_2`** can still allocate — sheet lines then **correctly share** `primary_2` only. Duplicate keys on the sheet are **not sufficient evidence** of a tagging bug without checking **sync results** per key. Conversely, Sam must **not** claim a sex mix is **available** from memory-only / LLM narration when **`primary_1` would be `no_match`** — see **Key Business Rules** in **`CLAUDE.md`** and **§4.2**.

**Incident — 2026-05-09 (live WhatsApp, grower + split):** After a multi-turn thread, **`ORDER_MASTER`** showed **empty `Requested_Sex` / `Collection_Location`** while **`ORDER_LINES`** failed the intended **1 Male + 2 Female** allocation (often **Female-only rows**); Sam also **re-asked for collection location** in some variants despite **Riversdale**. **Overlap with fixes shipped 2026-05-09:** longer **`ConversationHistory`** (**25** msgs) and **`Code - Build Sales Agent Memory Summary`** (recap hints, **no** `male`-substring double-count on **`female`**) improve **hydration** on short turns — they **do not** replace **inventory-backed** wording, **`update_order`** header persistence rules, nor **partial-stock** UX. Treat **§4.1** as **open** until the live test below passes.

**Repo fix summary 2026-05-10:**

- `Code - Build Order State` now stores mixed-sex split requests as `ORDER_MASTER.Requested_Sex = Any`; exact sex quantities stay in `requested_items[]` and `ORDER_LINES`.
- `20-24kg` / `30-34kg` parsing no longer falls through to `2_to_4_Kg` from the trailing `24kg` / `34kg` text.
- Short confirmation from memory, such as `yes please`, now still routes to `UPDATE_HEADER_AND_LINES` when memory builds valid `requested_items[]`.
- First-turn `create_order_with_lines` now carries `collection_location`, `payment_method`, and `conversation_id` through `1.0`, `1.2`, and backend create.
- Backend in-memory split sync test passed: `primary_1` Male created 1 row, `primary_2` Female created 2 rows, repeated sync cancelled/recreated the same keys without duplicate active rows.

**Live verification 2026-05-10:**

- First run created `ORD-2026-78FB68`: split lines were correct, but `Collection_Location`, `Payment_Method`, and `ConversationId` were blank. That exposed the create-with-lines header gap; the test draft was cancelled after the fix.
- Retest after backend deploy and `1.0` / `1.2` re-import created `ORD-2026-25CC0D`: `Requested_Sex = Any`, `Requested_Weight_Range = 20_to_24_Kg`, `Requested_Quantity = 3`, `Collection_Location = Riversdale`, `Payment_Method = Cash`, `ConversationId = 1742`, and three active lines were correct (`primary_1` Male, `primary_2` Female x2).
- `ORD-2026-25CC0D` was cancelled after verification so test draft lines do not block stock matching.

**Regression test (fresh thread, after repo `1.0` re-import):**

1. Full exact-match test: use **Grower**, **20-24 kg**, qty **3**, message **"1 male and 2 females"**, then **Riversdale**, then **timing** (e.g. next Sunday), then **Cash**. Live stock checked 2026-05-10 had at least 1 Male + 2 Female in this band.
2. **`get_order_context`** / sheet: **`ORDER_MASTER.Requested_Sex`** and **`Collection_Location`** match conversation (if the product model stores only a **single** sex on the header, document the rule: e.g. **`Any`** + split only on **lines**, or encode split in **`Notes`** — but do not leave both blank when backend requires them for approval).
3. **`ORDER_LINES`:** three rows with **sex** == **1 Male, 2 Female** (or steward-documented equivalent), not three of one sex.
4. No **duplicate** outbound Sam messages; no **re-ask** for facts already in **`OrderStateSummary`** / memory for that thread.

**Partial/no-match guard test:** **Grower 30-34 kg**, qty **3**, **1 Male + 2 Female** should not be treated as a full exact sex split unless live stock changes. Live stock checked 2026-05-10 had three Female and zero Male in this band; expected result is `primary_1 = no_match` and `primary_2 = exact_match` for two Female rows, with Sam not claiming all three requested sex lines were available.

### 4.2 Define Partial Match Behavior

Status: Repo Fix Ready; Pending Import And Live Verification.

Required outcome:

- partial stock matches are returned clearly
- Sam does not confirm a complete update when backend only partially matched stock
- line totals must match requested quantity before success is treated as complete

Repo fix summary 2026-05-10:

- Backend `sync_order_lines_from_request` now separates technical `success` from business completeness. It returns `complete_fulfillment`, `fulfillment_status`, `requested_total`, `matched_total`, `unmatched_total`, and `incomplete_items`.
- `partial_fulfillment` now includes both `partial_match` and `no_match` outcomes. A split request with `primary_1 = no_match` and `primary_2 = exact_match` is no longer treated as complete just because the sync call succeeded.
- `1.2 - order-steward` passes the fulfillment fields through direct sync and `create_order_with_lines`.
- `1.0 - Sam-sales-agent-chatwoot` exposes `had_no_match`, `had_incomplete`, and detailed no-match/partial wording in `StewardCompact`; Sam's prompt now treats `complete_fulfillment = false` as an incomplete line sync.
- `Code - Build Extractor Inputs` now includes alternatives from `no_match` sync rows when building `last_agent_offer.caps`, so follow-up mix confirmations can still use backend-confirmed alternatives.

Verification completed locally:

- Workflow JSON parses for `1.0` and `1.2`.
- Mocked backend split sync: requested 3 Grower `30_to_34_Kg` pigs as 1 Male + 2 Female, with no Male and 2 Female available. Result: `success = true`, `complete_fulfillment = false`, `fulfillment_status = partial`, `requested_total = 3`, `matched_total = 2`, `unmatched_total = 1`, `primary_1 = no_match`, `primary_2 = exact_match`.
- Node-level checks confirm `StewardCompact.partial_stock_detail` includes no-match rows and extractor caps include no-match alternatives.

Next live check after backend deploy and workflow import:

1. Import updated `1.0 - Sam-sales-agent-chatwoot` and `1.2 - order-steward`.
2. Run the Phase 4.2 split no-match guard (`30-34kg`, 1 Male + 2 Female) only if live stock still has the same shortage.
3. Confirm Sam says only the matched quantity is on the draft and asks one follow-up question using alternatives.

### 4.3 Validate `intent_type` And `status`

Required outcome:

- either enforce these fields in backend sync or remove them from the required contract
- avoid fields that look important but do nothing

## Phase 5: Safe Order Review For Sam

Goal: let Sam understand saved order state without uncontrolled sheet access.

Preferred direction:

- add backend/Order Steward review action
- backend reads the relevant order data
- backend filters the result for Sam
- Sam answers based on backend-confirmed order truth

Possible actions:

- `review_order`
- `find_customer_orders`
- `get_active_customer_order_context`

## Phase 6: Web App Order Usability

Goal: make the app useful for daily order operations.

Focus areas:

- order list clarity
- order detail clarity
- visible line/reservation state
- reserve/release success feedback on order detail is done (API `message` + `changed_count` + `warning`); still need button visibility parity for approve/reject and other actions
- **Pen / location labels:** dropdowns and pig pickers should show **pen name** (human-readable) alongside or instead of raw **pen ID** wherever the app still exposes IDs only
- **Known route mismatch to park:** `static/js/litterDetail.js` currently calls `/api/pig-weights/litter/<id>/detail`, while the Flask route is `/api/pig-weights/litter/<id>`; fix under web app/pig detail usability unless it blocks live order work
- clear approve/reject/cancel buttons
- order detail actions must match backend rules: show approve/reject when `Order_Status = Pending_Approval`, reserve/release when appropriate; avoid forcing ops through OOM SAKKIE workflows when parity with API is intended
- safe release/reserve controls
- useful logs/history
- clear success/failure messages
- less manual debugging
- short progress/status messaging for background actions such as reserve, release, reject, and cancel

Rule:

Do not redesign the app before the backend order behavior is safe.

## Phase 7: Broader Workflow Improvements

Only after order stability:

### 7.0 Backend Verification And Service Boundary Cleanup

This is a planned technical-debt checkpoint, not a reason to delay Phase 1.8.

Required outcome:

- add focused backend verification around order lifecycle and requested-item sync before large refactors
- make the `order_service.py` split visible and deliberate, aligned with `docs/02-backend/REFACTOR_PLAN.md`
- do not split `order_service.py` until Phase 1 lifecycle behavior and Phase 4/5 order-truth behavior are stable enough to protect with tests or clear manual checklists
- keep Google Sheets append/write behavior tied to documented sheet headers, not hidden assumptions about column order

### 7.1 Intake (from planning triage — not yet scheduled)

Carry these when capacity allows; they do not block current order hardening.

- **1.0 payload hygiene:** reduce duplicated / noisy fields crossing nodes; prefer one structured slim object per stage
- **Sam + completed orders:** order history lookup (backend / `1.2` action) so Sam can reference past orders; customer asks for **old invoices** — tie to Phase 2 delivery when quotes/invoices exist
- **Chatwoot `order_id` lifecycle:** decide whether conversation custom attributes clear on **Completed**, or keep stable links plus a separate **customer order history** view
- **LLM vs Code:** short paraphrases may use hybrid extractor; inventory, price, and reservation stay **deterministic**. Prefer extending **`sam_text_parse`** + caps when wording drifts rather than replacing Code with LLM-only routing

Improvements also in scope:

- improve Sam order context
- improve AUTO reply quality where still needed
- fix and enable `1.3 - Media Tool`
- improve Telegram cleanup for human escalation
- expand monitoring and operational runbooks

## Phase 8: Breeding Board Improvements — Completed 2026-05-02

### 8A Optional Pen Movement On Add Mating — Complete

- `GET /api/pig-weights/breeding-options` now returns `current_pen_id` and `current_pen_name` for each sow and boar.
- `/master/add-mating` form shows sow and boar current pen after selection, and optional `Move sow to pen` / `Move boar to pen` dropdowns populated from `GET /api/pig-weights/pens`.
- `POST /api/pig-weights/master/matings` accepts optional `sow_move_to_pen_id` and `boar_move_to_pen_id`.
- Backend calls `_write_movement_if_needed()` for each; skips write if target equals current pen or is empty.
- Movement rows are written to `LOCATION_HISTORY` with `reason = "Moved during mating log"`, `moved_by = "Mating Form"`.

### 8B Move To Farrowing / Assume Pregnant Action — Complete

- New endpoint: `POST /api/pig-weights/master/matings/<mating_id>/assume-pregnant`
- Updates `MATING_LOG`: `Pregnancy_Check_Date = today`, `Pregnancy_Check_Result = Pregnant`, `Mating_Status = Confirmed_Pregnant`, `Outcome = Pregnant`, `Updated_At = today`.
- Blocked for matings with status `Farrowed`, `Cancelled`, or `Closed`.
- Optional: if `target_pen_id` is supplied, writes sow movement row to `LOCATION_HISTORY` with `reason = "Moved to farrowing pen"`.
- Does NOT create a litter. Litter creation remains via Add Litter.
- `/matings` Breeding Board shows a "Move to Farrowing / Assume Pregnant" button on all eligible open mating cards (not Farrowed/Cancelled/Closed, no linked litter). Clicking opens an inline form with a pen dropdown (farrowing pens listed first). On confirm, POSTs to the endpoint and reloads the board.

### 8C Needs Action Now — No Litter After 3 Weeks Trigger — Complete

- In `matings.js`, when `is_overdue_farrowing = "Yes"` and no `linked_litter_id` and no `actual_farrowing_date` and `daysToFarrowing < -21`, the board classifies the record as `Needs Action Now` with action text `"No litter after 3 weeks — review"`.
- Movement guidance text explains the situation: days past expected farrowing, check if she has farrowed or if repeat service is needed.

### 8D Not Yet Built — Mark Not Pregnant / Repeat Service

When a sow has been in a farrowing pen too long with no litter, the next action is to mark her as not pregnant and return to repeat service. This is not yet built. When implemented:

- `POST /api/pig-weights/master/matings/<mating_id>/mark-not-pregnant`
- Updates `MATING_LOG`: `Pregnancy_Check_Result = Not_Pregnant`, `Mating_Status = Repeat_Service`, `Outcome = Repeat_Required`, `Updated_At = today`.
- Optionally moves sow back to a service pen.
- Available only for `Confirmed_Pregnant` matings with no litter and no actual farrowing date.

## Phase 9: Pig, Weight, And Reporting Improvements

Only after live order stability unless the operational need becomes urgent.

### 9.1 New Litter Defaults And Weaning Reminder

Required outcome:

- new `PIG_MASTER` rows generated from a litter should default `Purpose = Unknown`
- animals with `Purpose = Unknown` must not appear as for-sale stock
- once animals are weaned, surface a reminder to assign purpose: `Grow_Out`, `Sale`, or `Breeding`

### 9.2 Pig Dropdown Usability

Required outcome:

- pig-related dropdowns should show tag number and pen name, not only pen ID
- tag numbers should display as three digits where appropriate: `001`, `010`, `090`, `100`

### 9.3 Weight Form Context

Required outcome:

- beside `Move to Pen (Optional)`, show the current pen as read-only helper context

### 9.4 Weight Report

Required outcome:

- after weights are entered, allow the user to generate a weekly weight report
- include summaries, grouped totals, pen counts, and useful decision-making commentary
- this covers post-entry reporting only; pre-weighing handwritten capture is the separate Phase 9.6 printable sheet

### 9.5 Dashboard Sold This Month Audit

Required outcome:

- verify how `SOLD THIS MONTH` is calculated
- reconcile the April mismatch where the dashboard showed 20 but the expected sold count was 40

### 9.6 Printable Farm Operation Sheets

Required outcome:

- add a web-app page for printable farm operation sheets, likely `/print-sheets`
- first template: weekly weight sheet used before animals are weighed
- allow the user to choose which animals appear on the sheet: all active pigs, by pen/camp, by purpose, for-sale animals, or grow-out/sale animals
- printed sheet must be human-readable for farm workers and must hide internal IDs such as `Pig_ID`
- include: `Tag Number`, `Vorige Gewig Datum`, `Vorige Gewig`, blank `Nuwe Gewig`, current `Kamp`, blank `Nuwe Kamp`, and blank `Notas`
- include total count and a blank or user-selected weighing date at the top of the sheet
- default sorting should support the real farm workflow, preferably grouped by current pen/camp and then tag number
- support laptop and phone browser printing with print-friendly CSS, with save-to-PDF as a natural browser option
- read from existing system truth only during print generation; do not write to Google Sheets when creating a printable sheet
- keep this separate from Phase 9.4: printable sheets are for handwritten field capture before weights are entered, while weight reports summarize data after weights are entered

Follow-up idea:

- after the printable sheet is useful, consider a bulk weight entry page that follows the same row order so handwritten weights can be entered quickly without searching for each pig individually

## Phase 10: Farm Operating System Integration

Goal: bring Sam, Oom Sakkie, the web app, backend modules, weather logging, Synsynk solar data, n8n workflows, and Google Sheets into one documented operating-system structure.

Timing rule:

- do not start this umbrella integration until Sam/order behavior is stable enough that expanding the system will not hide existing sales bugs

Required outcome:

- document every major workflow and platform under one system map
- define ownership for each module: sales, farm operations, pig records, worker assistant, weather, solar, reporting, notifications, and admin web app
- create a workflow register showing trigger, purpose, inputs, outputs, reads, writes, dependencies, and risk level for each n8n workflow
- create data contracts for information passed between workflows, backend endpoints, web app pages, Google Sheets, and external systems
- set up Oom Sakkie documentation in the same style as Sam: workflow map, data flow, node responsibilities, protected logic, and input/output contracts
- ensure important operational writes go through backend-controlled logic where possible instead of direct workflow-to-sheet writes
- keep AI agents responsible for interpretation and wording, not hidden data ownership or business-rule enforcement
- document backend module boundaries for orders, pig operations, farm worker tasks, weather logging, solar data, reporting, and notifications
- add logging and audit expectations for customer actions, worker actions, web-app actions, backend actions, weather imports, and solar imports
- make the web app the visible control panel where possible so operators can understand system state without jumping between platforms

## Current Choice Point

Recently completed:

- Phase 1.1 reject behavior
- Phase 1.2 customer cancel through backend, `1.2`, and `1.0`
- Phase 1.2c first-turn create-with-lines via `create_order_with_lines`
- Phase 1.3 payment method capture — backend, `1.0`, `1.2`, `1.1`, Chatwoot mirror, and lock guard live-verified 2026-04-29
- Phase 1.4 send_for_approval happy path — backend validations, `1.2` neverError + conditional result, `1.0` intent detection + routing + 4 new nodes + Chatwoot write live-verified 2026-04-30
- Phase 1.4 bugfix — `sendForApprovalIntent` regex expanded to cover "send it for approval", "send this through", "submit it/this/my order", etc.; SEND_FOR_APPROVAL moved before UPDATE checks in route priority; Sales Agent prompt tightened so Sam never overstates on REPLY_ONLY; live re-verification passed 2026-04-30
- Phase 1.4 approval preflight and backend `400` regressions — fixed and live re-tested 2026-05-04; missing payment method now asks Cash/EFT without backend call; backend guard failures preserve Draft status and return a customer-safe missing-field reply
- Phase 1.5 lifecycle guards — Complete And Live-Verified 2026-05-04: `approve_order` only from `Pending_Approval`; payment lock beyond Draft; reject/cancel vs `Completed`; defer auto-reservation (1.8) and outbound notifications (1.9)
- Phase 1.6 reserve/release hardening — **complete** 2026-05-05 (backend/sheets); 2026-05-06 (order-detail success banner: API `message` + `changed_count` + idempotent copy for second reserve/release)
- Phase 1.7 slim Sales Agent reply payload — complete and live-verified **2026-05-07**: `Code - Slim Sales Agent User Context` on all four paths into Sam; `OrderStateSummary` + `StewardCompact`; WhatsApp checklist A+B passed

Recommended next:

1. **Phase 2.1** — Design quote/invoice document schema and generation path.
2. **Phase 6** (parallel polish when useful) — Web app order detail parity and action clarity after the Phase 1.8 approval/reservation behavior.
3. Parked / not blocking Phase 1.9: litter detail route mismatch under Phase 6; backend verification and eventual `order_service.py` split under Phase 7.0.

Pick the next item deliberately before implementation so docs, workflow exports, and tests stay aligned.
