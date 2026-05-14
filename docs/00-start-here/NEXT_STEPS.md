# Next Steps

## Purpose

Defines the approved build order from this point forward.

**Process (phases only, testing, when to involve Claude Code):**  
`docs/00-start-here/HOW_WE_WORK.md` — includes an editable **working position** table so you can see **which subsection we are on** without skipping ahead.

## Core Rule

Stabilize live order behavior before expanding features or polishing the app.

Orders are the profit section. They must be reliable before the system grows.

## Phase Status At A Glance

| Phase | Status | Next action |
| --- | --- | --- |
| Phase 1: Order Lifecycle Stabilization | Complete And Live-Verified | Keep regression checks only. |
| Phase 2: Quote And Invoice Generation | Complete Through 2.6 | Continue future document/operator polish only when planned. |
| Phase 3: Daily Order Summary | Complete And Scheduled-Run Verified | Monitor scheduled delivery. |
| Phase 4: Requested Item Sync Stabilization | 4.1, 4.2, and 4.3 Complete; 4.0 deferred | Move to Phase 5 unless a Phase 4 regression appears. |
| Phase 5: Safe Order Review For Sam | Complete through 5.8.1 one-turn quote delivery, live-verified | Move to Phase 5.9 n8n payload and Chatwoot attribute cleanup. |
| Phase 6: Web App Order Usability | In Progress / Ongoing | Continue after backend order truth is stable. |
| Phase 7: Broader Workflow Improvements | Not Started | Technical-debt checkpoint after order stability. |
| Phase 8: Breeding Board Improvements | Mostly Complete; 8D not built | 8D remains future work. |
| Phase 9: Pig, Weight, And Reporting Improvements | Not Started | Future. |
| Phase 10: Farm Operating System Integration | Not Started | Future. |

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

## Phase 1: Order Lifecycle Stabilization - Complete And Live-Verified

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

Follow-up planning note:

- Add an internal farm-manager notification after an order is approved and ready to coordinate collection. The planned recipient is Anton. The notification should include `Order_ID`, customer name, phone number, item list, total, payment type, collection location, date/time, and notes. This is not part of the already closed customer approval/rejection notification test; schedule it as a separate internal operations notification so it can be tested without changing the customer-facing message path.

## Phase 2: Quote And Invoice Generation - Complete Through 2.6

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

### 2.5 n8n Delivery - Complete And Live-Verified

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

### 2.6 Web App Document Controls - Complete And Browser-Verified

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

## Phase 3: Daily Order Summary - Complete And Scheduled-Run Verified

Goal: scheduled operational overview of current order state.

### 3.1 Backend Report Endpoint - Complete And Live Read-Only Verified

Status: Implemented And Live Read-Only Verified 2026-05-10.

Required outcome:

- `GET /api/reports/daily-summary` returns counts and lists grouped by status: new drafts, drafts missing payment method, pending approval, approved, cancelled today, completed today, orders needing attention - Done
- endpoint is independently testable - Done, supports optional `?date=YYYY-MM-DD`
- n8n reads only from this endpoint, not from sheets directly - Ready for Phase 3.2
- live read-only test for `2026-05-10` returned `success = true` with all expected section keys
- invalid date test returns `400` with a clear validation error

### 3.2 n8n Scheduled Delivery - Complete And Scheduled-Run Verified

Status: Complete And Scheduled-Run Verified 2026-05-10.

Required outcome:

- n8n scheduled workflow fires daily at 16:00 Africa/Johannesburg - Ready to activate
- calls backend summary endpoint - Verified: `GET https://amadeus-pig-tracking-system.onrender.com/api/reports/daily-summary`
- formats output and sends to Telegram or email - Manual Telegram test verified
- MVP fallback is no longer needed because the backend report endpoint exists
- first 16:00 scheduled run confirmed: one Telegram message received

## Phase 4: Requested Item Sync Stabilization - Complete Through 4.3; 4.0 Deferred

Goal: make Sam's order-line sync reliable.

### 4.0 Sales Stock Formula Gate Alignment - Deferred / Open

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

### 4.1 Fix Split Item Sync - Complete And Live-Verified

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

### 4.2 Define Partial Match Behavior - Complete And Live-Verified

Status: Complete And Live-Verified 2026-05-10.

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

Live verification 2026-05-10:

- Test used Chatwoot conversation `1742` and live stock guard **Grower `30_to_34_Kg`, quantity 3, split 1 Male + 2 Female**. Live `SALES_AVAILABILITY` had **0 Male** and **3 Female** in that band.
- `1.0` / `1.2` created draft `ORD-2026-011771` with header fields correct: `Requested_Quantity = 3`, `Requested_Sex = Any`, `Requested_Weight_Range = 30_to_34_Kg`, `Collection_Location = Riversdale`, `Payment_Method = Cash`, `ConversationId = 1742`.
- `ORDER_LINES` showed only two active rows, both `primary_2` Female in `30_to_34_Kg`; no `primary_1` Male row was created.
- Direct live sync response for the same order returned `success = true`, `complete_fulfillment = false`, `partial_fulfillment = true`, `fulfillment_status = partial`, `requested_total = 3`, `matched_total = 2`, `unmatched_total = 1`, `primary_1 = no_match`, `primary_2 = exact_match`, and `incomplete_items[]` for `primary_1`.
- Sam generated correct partial/no-match wording: only 2 Female pigs were added, the requested Male was unavailable, and 2 Male alternatives existed in `20_to_24_Kg`. Chatwoot marked the outbound WhatsApp send as `failed` because of the WhatsApp/template window, but the generated content was correct.
- `ORD-2026-011771` was cancelled after verification; `active_line_count = 0` and the matched pigs were released.

### 4.3 Validate `intent_type` And `status` - Complete And Live-Verified

Required outcome:

- either enforce these fields in backend sync or remove them from the required contract - Done in repo
- avoid fields that look important but do nothing - Done in repo

Repo fix summary 2026-05-11:

- `intent_type` is optional metadata only and is now validated when present. Allowed values: `primary`, `addon`, `nearby_addon`, `extractor_slot`.
- `status` defaults to `active` and backend sync now rejects any non-`active` value. Inactive/cancelled requested items are not a backend sync feature; callers must omit those items instead of sending them.
- Matching behavior still depends on `request_item_key`, `category`, `weight_range`, `sex`, and `quantity`; `intent_type` does not change allocation.
- Docs updated in `ORDER_LOGIC.md`, `DATA_MODELS.md`, `API_STRUCTURE.md`, `DATA_FLOW.md`, and `CHANGELOG.md`.

Verification completed locally:

- Valid payload with missing `intent_type`/`status` defaults cleanly to `status = active`.
- Valid payload with `intent_type = nearby_addon` and `status = active` passes.
- Invalid `intent_type` is rejected.
- Invalid `status = inactive` is rejected with a clear backend validation error.

Live verification 2026-05-11:

- Temporary Charl N draft `ORD-2026-07F5C8` was created for Phase 4.3 testing only, with `ConversationId = 1742`.
- Direct live sync with `intent_type = primary` and `status = active` passed validation and returned `success = true`. The requested Grower `30_to_34_Kg` Male item had no exact stock match, so no order lines were created.
- Direct live sync with `status = inactive` returned `400` with the expected validation error and did not alter order lines.
- Direct live sync with `intent_type = made_up` returned `400` with the expected allowed-value validation error and did not alter order lines.
- `ORD-2026-07F5C8` was cancelled after verification; final state was `Order_Status = Cancelled`, `Payment_Status = Cancelled`, `active_line_count = 0`, and `reserved_pig_count = 0`.

## Phase 5: Safe Order Review For Sam - Complete Through 5.7 Atomic Path; Cleanup/5.8 Next

Goal: let Sam understand saved order state without uncontrolled sheet access.

Decision:

- Keep `ORDER_MASTER` as the single operational order source for now.
- Do not split completed/cancelled orders into a separate live `ORDER_HISTORY` sheet yet; that would affect formulas, document links, API reads, and status flows.
- Add backend/Order Steward review actions that filter the data before Sam sees it.
- Sam must answer from backend-confirmed order truth, not direct sheet access.
- Plan an archive/history design as a later scaling step, with clear triggers.

### 5.1 Safe By-ID Order Context - Complete And Live

Current state:

- Backend `GET /api/orders/<order_id>` returns one order, matching `ORDER_LINES`, and generated `ORDER_DOCUMENTS`.
- `1.2 - Amadeus Order Steward` exposes read-only `get_order_context`.
- `1.0 - Sam-sales-agent-chatwoot` prefetches this context when it already has an `existing_order_id`.
- `1.2` formats a slim `existing_order_context` for Sam rather than exposing raw sheets.

Live reference:

- 2026-05-11: Read-only check on Charl N order `ORD-2026-BDEFCE` returned the draft header, 6 active lines, `active_line_total = 2100`, and `line_count_includes_cancelled = true`.

### 5.2 Safe Active Customer Order Lookup - Complete And Live-Verified

Required outcome:

- Sam can find the relevant active customer order even when Chatwoot `order_id` is missing or stale.
- Backend/steward lookup is filtered by safe identifiers such as `conversation_id`, `customer_phone`, or exact `order_id`.
- Response returns a safe summary only, not the full `/api/orders` list.
- If exactly one active order is found, return it as review context.
- If multiple active orders are found, return a short disambiguation list so Sam asks one clear question.
- If no active order is found, Sam must not invent an order; it should ask for the order reference or continue normal order flow.

Preferred action name:

- `get_active_customer_order_context`

Possible companion action:

- `find_customer_orders`

Important rule:

- `/api/orders` may remain available for the web app/admin, but it must not be exposed directly as a Sam tool because it returns the full order list and customer details.

Backend progress 2026-05-11:

- Added read-only endpoint `GET /api/orders/active-customer-context`.
- Lookup accepts `order_id`, `conversation_id`, or `customer_phone`.
- Active order statuses are `Draft`, `Pending_Approval`, and `Approved`.
- Response returns one safe `order_context`, a short `multiple_matches` list, `no_match`, or `terminal_order`.
- Safe context groups active lines by category, weight band, sex, status, reserved status, and unit price; it does not return pig IDs, tag numbers, raw sheet rows, or the full order list.

Local verification:

- Missing lookup identifiers return `400`.
- Exact Charl N order `ORD-2026-BDEFCE` returns `single_match` with 6 active draft lines grouped as 4 Female and 2 Male `2_to_4_Kg` Young Piglets.
- Charl N phone lookup returns `multiple_matches` for `ORD-2026-BDEFCE` and `ORD-2026-CEF70A`, which is the expected disambiguation case.

Steward export progress 2026-05-11:

- Added `1.2 - Amadeus Order Steward` switch branch `get_active_customer_order_context`.
- Branch calls backend `GET /api/orders/active-customer-context`.
- Formatter returns `active_order_context_fetch_ok`, `lookup_status`, `match_count`, `active_order_context`, `active_order_matches`, and `lookup_inputs`.

Sales agent export progress 2026-05-11:

- Added conservative `1.0 - Sam-sales-agent-chatwoot` fallback lookup path after the existing exact-order context check.
- If `ExistingOrderId` exists, the old `get_order_context` path still wins.
- If no `ExistingOrderId` exists, saved-order review/cancel/document-style messages can call `get_active_customer_order_context` through `1.2`.
- Normal new sales messages do not trigger active-order lookup.
- Single-match lookup injects safe order context into the existing order-state path; multiple-match lookup exposes short summaries so Sam can ask one disambiguation question.
- Live test correction: `HTTP - Get Conversation Messages` now builds its Chatwoot API URL from normalized `AccountId` and `ConversationId`, because `conversation.messages[0].account_id` and `conversation.messages[0].conversation_id` can be undefined.
- Live test correction: `1.2` `Switch - Route by Action` output `Get Active Customer Order Context` now uses `={{ $json.action }}` like the other branches.
- Live test correction: conversation ID is now the preferred lookup key. Phone lookup is fallback-only so older active orders on the same phone number do not override a clean conversation-specific match.

Live verification 2026-05-11:

- Clean conversation `1774` and temporary test order `ORD-2026-8B7FC8` verified the missing/stale `order_id` fallback.
- Sam correctly replied with one specific draft order: 1 male piglet, `5_to_6_Kg`, Riversdale collection, `R400`.
- Sam no longer included older Charl N active draft orders when the exact conversation ID matched the temporary order.
- Temporary test order `ORD-2026-8B7FC8` was cancelled after verification; its single line is `Cancelled`, `reserved_pig_count = 0`, and conversation `1774` active lookup now returns `no_match`.

### 5.3 Sam Review Wording Tests - Complete And Live-Verified

Test prompts:

- "What is on my order?"
- "How many pigs did I order?"
- "Is my order approved?"
- "What is still missing?"
- "Can you send my old quote/invoice again?"

Required outcome:

- Sam answers from backend/steward context.
- Sam distinguishes Draft, Pending Approval, Approved, Cancelled, and Completed.
- Sam does not claim reservations, approval, payment, quote, invoice, or collection unless the backend context confirms it.
- Old quote/invoice requests route toward document history/delivery, not manual sheet lookup.

Export progress 2026-05-11:

- Added a dedicated `ORDER REVIEW RESPONSE RULES` guard to the `1.0 - Sam-sales-agent-chatwoot` Sales Agent system prompt.
- The guard forces order-review replies to use `StewardCompact`, `OrderStateSummary`, `OrderID`, backend status fields, and `active_order_*` context first.
- Added `"What is still missing?"` / missing-detail wording to the active-order lookup trigger set.
- If one active order is matched, Sam must answer about that order only.
- If multiple active orders match, Sam must ask one disambiguation question.
- If no active order context is available, Sam must ask for the order reference instead of inventing an order.
- Quote/invoice requests must not invent document links or claim delivery without document context.

Live verification 2026-05-11:

- Updated `1.0` export was imported into n8n.
- Temporary Charl N order `ORD-2026-DDFEE6` was created on clean Chatwoot conversation `1774`.
- Backend active lookup returned one Draft order with 1 male Young Piglet, `5_to_6_Kg`, `R400`, Cash, Riversdale.
- All five Phase 5.3 prompts were accepted by the live workflow and project owner confirmed Sam's replies were good.
- Temporary order `ORD-2026-DDFEE6` was cancelled after verification; its single line is `Cancelled`, `reserved_pig_count = 0`, and conversation `1774` active lookup now returns `no_match`.

### 5.4 Persistent Order Intake State Design - Complete / Approved

Problem to solve:

- Sam can hold a natural conversation and repeat the right order details, but the deterministic order route can still lose those details when they are not present in the latest structured state.
- Recent-history reconstruction is not reliable enough for operations because older customer facts can fall outside the message window.
- A formal quote is a backend-generated PDF document; it is not the same thing as a chat quote or draft order.
- Draft order creation, quote generation, and later approval must be driven by backend-confirmed structured state, not Sam's prose.

Architecture decision:

- Add backend-owned persistent order intake state as the truth for in-progress sales conversations.
- Chatwoot attributes should remain lightweight routing hints only, not the source of truth for intake.
- n8n should orchestrate calls and pass compact context, not large duplicated raw payloads.
- Sam should handle natural wording and one clear next question, not own operational truth.

Planned sheets:

- `ORDER_INTAKE_STATE`: one active intake header per conversation/customer sales flow.
- `ORDER_INTAKE_ITEMS`: one row per requested item/category/weight/sex line in the intake.

Required behavior:

- Every customer turn can update intake state with newly confirmed facts.
- Backend returns known fields, missing fields, next allowed action, and safe reply facts.
- Sam asks only the next missing field.
- When required fields are complete and the customer asks for a formal quote, backend/n8n should create or update the draft, sync lines, generate the quote PDF, and offer/send it through the document path.
- When the customer clearly wants to proceed, backend/n8n should create or update the draft and sync lines.
- Multi-category requests must be represented as `requested_items[]`, not collapsed into one flat product field.
- Draft changes are allowed before approval and should update intake/draft/order lines.
- Approved/reserved/completed orders must not be silently changed by Sam; they should be blocked or routed to admin review.

Core intake state fields:

- `ConversationId`
- customer identity fields
- `Draft_Order_ID`
- `Intake_Status`
- `Collection_Location`
- `Collection_Time_Text`
- `Collection_Date`
- `Collection_Time`
- `Payment_Method`
- `Quote_Requested`
- `Order_Commitment`
- `Missing_Fields`
- `Next_Action`
- `Last_Customer_Message`
- `Updated_At`

Collection timing decision:

- Store customer wording such as "Friday at 14:00" in `Collection_Time_Text`.
- Store parsed `Collection_Date` / `Collection_Time` only when safe or confirmed.
- If the date is ambiguous, Sam should ask one confirmation question before relying on it operationally.

Core intake item fields:

- `Intake_ID`
- `Item_Key`
- `Quantity`
- `Category`
- `Weight_Range`
- `Sex`
- `Intent_Type`
- `Status`
- `Linked_Order_Line_IDs`

Settled design decisions:

- Draft creation requires the minimum operational fields: at least one active requested item with quantity/category/weight range, `Collection_Location`, customer identity/contact route, and a clear commitment signal. Do not create a Draft merely because two fields are known.
- `Payment_Method` is not required for the first Draft, but it is required before formal quote generation and before sending for approval.
- A formal quote request must create/update a backend Draft order first when no suitable Draft exists, then sync lines, generate the PDF, and offer/send it through the document delivery path.
- If the customer wants to proceed but has not asked for a formal quote, the system may create/update the Draft once ready, then Sam should ask whether the customer wants a formal quote PDF or wants to continue toward approval.
- AI-assisted extraction may propose intake patches, but the backend validates and merges them. n8n and Sam do not write intake state directly.
- Ambiguous edits such as "change the grower" when multiple grower items exist must return `ask_disambiguation`; Sam asks one clarifying question.
- Removed or replaced intake items are marked with `Status = removed` or `Status = replaced`, with timestamps/reason where available. They are not deleted.
- Closed intake rows are kept for audit/history.
- Abandoned open intake rows may later be marked closed with `Closed_Reason = abandoned` after an agreed inactivity window; draft-linked abandoned cases need a separate approved rule.

Design draft 2026-05-11:

- Added `docs/02-backend/ORDER_INTAKE_STATE_DESIGN.md`.
- Added planned sheet specs for `ORDER_INTAKE_STATE` and `ORDER_INTAKE_ITEMS`.
- No sheets, endpoints, workflow nodes, or runtime behavior have been created yet.
- Owner review/sign-off completed on 2026-05-11.
- Next step is Phase 5.5 implementation of backend-owned intake sheets and endpoints.

### 5.5 Backend Intake State Sheets And Endpoints - Complete And Live-Verified

Required outcome:

- Create documented sheet schemas for `ORDER_INTAKE_STATE` and `ORDER_INTAKE_ITEMS`. - Done in repo.
- Add backend endpoints to read/update intake state by `conversation_id`. - Done in repo.
- Backend merges new facts into existing intake state rather than replacing known facts with blanks. - Done in repo.
- Backend computes `missing_fields`, `ready_for_draft`, `ready_for_quote`, and `next_action`. - Done in repo.
- No live behavior should depend on this until shadow-mode verification passes. - Still applies.

Implemented endpoints:

- `GET /api/order-intake/context?conversation_id=<id>`
- `POST /api/order-intake/update`
- `POST /api/order-intake/<conversation_id>/reset`

Repo implementation 2026-05-12:

- Added `modules/orders/order_intake_service.py`.
- Added order intake routes under the existing `/api` order blueprint.
- Added `scripts/setup_order_intake_infrastructure.py` with dry-run default and `--apply` for live sheet creation.
- Added API docs and sheet changelog entries.
- Local verification passed:
  - Python compile check passed for intake service, order routes, and setup script.
  - Flask route map includes all three `/api/order-intake/*` endpoints.
  - Mocked in-memory intake test passed for create/update, item merge, `create_draft_then_quote` next action, context read, and reset/close.
- Live Google Sheet setup dry-run passed on 2026-05-12:
  - `ORDER_INTAKE_STATE` is currently missing and would be created with the documented headers.
  - `ORDER_INTAKE_ITEMS` is currently missing and would be created with the documented headers.
  - No live sheet changes were made during dry-run.
- Live Google Sheet setup apply passed on 2026-05-12:
  - Created `ORDER_INTAKE_STATE`.
  - Created `ORDER_INTAKE_ITEMS`.
  - Header verification passed for both sheets.
- Direct local-backend-to-live-sheet smoke test passed on 2026-05-12:
  - Test conversation: `PHASE55-TEST-20260512`.
  - Created intake `INTAKE-2026-6C3CD0` and item `INTAKEITEM-2026-C6680E`.
  - Update response returned `next_action = create_draft_then_quote`, `ready_for_draft = true`, `ready_for_quote = false`, and `missing_fields = ["draft_order_id"]`.
  - Context read returned `lookup_status = single_match`.
  - Reset closed the intake with `Closed_Reason = phase_5_5_smoke_test_complete`.
  - Post-reset context read returned `lookup_status = no_match`, confirming no active test intake remains.
- Deployed Render smoke test passed on 2026-05-12:
  - Test conversation: `PHASE55-RENDER-TEST-20260512`.
  - Created intake `INTAKE-2026-FD85E3` and item `INTAKEITEM-2026-2CAC20`.
  - `POST /api/order-intake/update` returned `next_action = create_draft_then_quote`, `ready_for_draft = true`, `ready_for_quote = false`, and `missing_fields = ["draft_order_id"]`.
  - `GET /api/order-intake/context` returned `lookup_status = single_match`.
  - `POST /api/order-intake/<conversation_id>/reset` closed the intake with `Closed_Reason = phase_5_5_render_smoke_test_complete`.
  - Post-reset context read returned `lookup_status = no_match`, confirming no active deployed-backend test intake remains.

Phase 5.5 is closed. Next phase is Phase 5.6 intake shadow mode in `1.0`.

### 5.6 Intake Shadow Mode In `1.0` - Complete And Live-Verified

Required outcome:

- `1.0 - Sam-sales-agent-chatwoot` calls intake update/read every customer turn but does not yet use it as the primary routing truth. - Live-verified.
- Compare backend intake state against the current `order_state`, Sam replies, and known problem transcripts. - Live-verified for the key missing-memory case.
- Prove the intake state retains facts after long conversations and repeated follow-up questions. - Live-verified for short follow-up commitment after prior facts were captured.
- Do not remove existing Chatwoot attributes or payload fields during shadow mode. - Preserved.

Repo implementation 2026-05-12:

- Added `Code - Build Intake Shadow Payload` after `Code - Format Chat History` and before `Ai Agent - Escalation Classifier`.
- Added `HTTP - Intake Shadow Update` calling `POST /api/order-intake/update`.
- Added `Code - Attach Intake Shadow Result` before `Ai Agent - Escalation Classifier`.
- Existing route decision, draft creation, update, sync, cancel, approval, and reply branches remain unchanged.
- Shadow result is attached as `intake_shadow_result`; raw backend response is attached as `intake_shadow_raw_response`.
- `HTTP - Intake Shadow Update` uses `continueOnFail` so a shadow-mode backend issue should not stop the existing customer reply path.

Local verification:

- `workflow.json` parses as valid JSON.
- Workflow now has 101 nodes.
- All connection source/target node names resolve.
- New common path is `Code - Format Chat History` -> `Code - Build Intake Shadow Payload` -> `HTTP - Intake Shadow Update` -> `Code - Attach Intake Shadow Result` -> `Ai Agent - Escalation Classifier`.
- New Code-node JavaScript passed syntax checks with Node.js.

Live verification 2026-05-12:

- Imported updated `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/workflow.json` into n8n and ran a safe shadow-mode test against Chatwoot conversation `1774`.
- First test message created intake `INTAKE-2026-4D7825` and item `INTAKEITEM-2026-39BF24` from: 1 Female Grower, `35_to_39_Kg`, Riversdale, Friday at 14:00, Cash.
- Backend context returned `lookup_status = single_match`, `quote_requested = true`, `safe_reply_facts` with the captured item/location/time/payment, and only `order_commitment` missing.
- Follow-up message `I want to proceed` updated the same intake instead of creating a disconnected state.
- Follow-up context returned `intake_status = Ready_For_Draft`, `order_commitment = true`, `missing_fields = []`, `next_action = create_draft`, and `ready_for_draft = true`.
- Existing live route behavior remained unchanged during shadow mode; no real draft order was created by Phase 5.6.

Acceptance tests:

- The transcript where the customer wants 1 female grower, `35_to_39_Kg`, Friday 14:00, Riversdale, Cash must retain those fields even after more than 25 messages. - Proven at backend state level for the captured facts; broader messy-human regression remains useful before replacing existing routing.
- "I told you what I want", "Yes", "I told you 1", and "I need a quote" must not erase known intake facts. - Covered by persistent backend merge behavior; keep as regression prompts for 5.7/5.8.

Phase 5.6 closure:

- Closed 2026-05-12. Intake state is now safe to use as the planned input for Phase 5.7, but existing routing remains the live operational path until 5.7 is implemented and verified.

### 5.7 Intake-Driven Draft Creation And Line Sync - Complete And Live-Verified

Required outcome:

- When intake is complete and the customer clearly wants to proceed, backend/n8n creates a draft order from intake state.
- `ORDER_MASTER` and `ORDER_LINES` are created from backend-confirmed intake state and `ORDER_INTAKE_ITEMS`.
- Multi-category and split-sex requests sync through `requested_items[]`.
- Existing Draft orders are updated, not duplicated, when the customer changes, adds, or removes items.

Implementation plan:

- Add a backend-owned action that converts a verified intake state into a Draft order action payload, using `ORDER_INTAKE_STATE` and active `ORDER_INTAKE_ITEMS` as the source of truth.
- In `1.0`, route only the proven case first: `intake_shadow_result.ready_for_draft = true` and `next_action = create_draft`.
- Call the existing `1.2 - Amadeus Order Steward` create-with-lines path where possible, instead of adding a second order-writing mechanism.
- After the draft is created, link the returned `order_id` back to the intake row as `Draft_Order_ID` and move intake status away from `Ready_For_Draft`.
- Keep the existing `order_state` route as fallback until intake-driven draft creation is live-verified.
- Do not wire formal quote PDF generation here; that remains Phase 5.8.

Repo implementation 2026-05-12:

- Updated `1.0 - Sam-sales-agent-chatwoot` export to promote only the verified intake-ready create path.
- `Code - Decide Order Route` now sets `CREATE_DRAFT` when `intake_shadow_result.ready_for_draft = true`, `next_action = create_draft`, and no draft is linked yet.
- `Set - Draft Order Payload` now uses backend-confirmed intake facts for the create payload when `debug_intake_ready_create_draft = true`.
- Intake-driven create uses existing `1.2` `create_order_with_lines`; no duplicate order-writing logic was added.
- Added `Code - Build Intake Draft Link Payload` and `HTTP - Link Intake Draft Order` after draft creation so the returned `order_id` is patched back to `ORDER_INTAKE_STATE.Draft_Order_ID`.
- The link branch returns no items unless the create came from intake readiness, so normal legacy draft creation does not call the intake endpoint.
- Formal quote generation remains out of scope for 5.7 and stays planned for 5.8.
- Live retest correction: first import did not create a draft because the intake result was only passed through the escalation classifier path, and the classifier output does not reliably preserve all incoming fields. The export now sends `Code - Attach Intake Shadow Result` to both `Ai Agent - Escalation Classifier` and `Merge - Sales Agent Context A`, while `Code - Format Chat History` feeds the shadow update first. This keeps `intake_shadow_result` available when `Code - Decide Order Route` runs.
- Second live retest correction: route decision still did not create a draft, so `Code - Decide Order Route` now reads `Code - Attach Intake Shadow Result` directly as a fallback if the merged item does not contain `intake_shadow_result`. It also reattaches `intake_shadow_result`, `intake_shadow_raw_response`, and `intake_shadow_payload` to its own output so `Set - Draft Order Payload` can use the verified intake facts.
- Third live retest correction: the later `Code - Should Create Draft Order?` node can overwrite `should_create_draft` based on older memory/missing-fact rules. The export now stamps intake-ready facts immediately in `Code - Attach Intake Shadow Result` and lets `Code - Should Create Draft Order?` treat the intake-ready signal as an approved create signal.

Local verification:

- `workflow.json` parses as valid JSON.
- Workflow now has 103 nodes.
- All connection source/target node names resolve.
- New/changed Code-node JavaScript passed syntax checks with Node.js.

Live verification 2026-05-12:

- Safe test conversation: Chatwoot conversation `1774`, intake `INTAKE-2026-4D7825`.
- Before test: intake was `Ready_For_Draft`, `next_action = create_draft`, `ready_for_draft = true`, with one active item: 1 Female Grower, `35_to_39_Kg`, Riversdale, Friday at 14:00, Cash.
- Live webhook test message `I want to proceed` created draft order `ORD-2026-A822D3`.
- Intake was linked back to `Draft_Order_ID = ORD-2026-A822D3`, changed to `Intake_Status = Draft_Created`, and now returns `next_action = sync_lines`.
- Order header was correct: `Order_Status = Draft`, `ConversationId = 1774`, `Customer_Name = Charl N`, `Requested_Category = Grower`, `Requested_Weight_Range = 35_to_39_Kg`, `Requested_Sex = Female`, `Requested_Quantity = 1`, `Collection_Location = Riversdale`, `Payment_Method = Cash`, `Created_By = Sam Phase 5.7 intake`.
- One active draft line was created: `OL-2026-95EC63`, Pig `PIG-2026-1F94`, tag `6`, Female, `35_to_39_Kg`, `Unit_Price = 1400`, `Request_Item_Key = item_1`, `Reserved_Status = Not_Reserved`.
- This test draft should be cancelled after owner confirmation so it does not keep test stock on an active draft.
- Follow-up broad regression found a Phase 5.7 gap before cleanup: not all natural commitment phrases are treated the same by intake and legacy routing. A test message using wording like `I would like to proceed` / `create a draft order` can leave intake below `Ready_For_Draft` while the legacy create route still fires. One regression draft, `ORD-2026-2B0D8A`, was created through the legacy path with `Created_By = Sam`, `Requested_Sex = Any`, and zero active lines. It was cancelled and conversation `1774` was reset to `no_match`.
- Required before n8n cleanup: expand/centralize commitment detection and prevent legacy header-only draft creation when requested item facts are present but intake is not ready. Then rerun a controlled multi-case regression and cancel/reset after every case.
- Fix prepared in repo on 2026-05-12: `Code - Build Intake Shadow Payload` now treats natural wording such as `I would like to proceed`, `create a draft order`, and `prepare the next step` as order commitment. `Code - Should Create Draft Order?` now blocks legacy header-only draft creation unless legacy state has line-ready `requested_items`; intake-ready creation remains allowed.
- Live retest after n8n import passed for the original failed wording: `ORD-2026-1450B2` was created from intake with 3 active Female Grower `30_to_34_Kg` lines, Riversdale, Cash. The test order was cancelled and the intake was closed.
- Wider batch should remain paused until two additional findings are fixed:
  - `ORD-2026-86CA53` created 2 active Weaner `10_to_14_Kg` lines but header `Requested_Sex` was `Any` even though the message requested `male`.
  - `ORD-2026-21BB6F` created a header-only Draft with zero active lines for 1 Female Weaner `15_to_19_Kg`; this confirms zero-line draft prevention still needs to apply after steward/line-sync results, not only before the legacy create route.
- All wider-batch test orders were cancelled: `ORD-2026-4FF699`, `ORD-2026-86CA53`, and `ORD-2026-21BB6F`. Conversation `1774` was verified clean afterward through local backend reads against the live sheet data.
- Google Sheets API quota was hit during the wider regression (`429 Read requests per minute per user`), which surfaced as Render `500` responses. Future live regression should be slower and smaller, or the backend should add retry/backoff/caching for sheet reads before high-volume testing.
- Fix prepared in repo:
  - `1.0 Code - Build Intake Shadow Payload` now lets the latest explicit customer sex (`Male` / `Female`) override stale `Any` values in existing `requested_items`.
  - `1.2 Code - Build Sync After Create Payload` sends `cancel_order_if_no_matches = true` only for the create-with-lines path.
  - Backend sync validation accepts `cancel_order_if_no_matches`.
  - `sync_order_lines_from_request` auto-cancels the newly-created Draft when that flag is set and `matched_total = 0`, returning `cancelled_empty_order = true` and `order_status = Cancelled`.
  - `1.2 Code - Format Create With Lines Result` treats that zero-match auto-cancel as not successful for Sam's downstream response.
- Local verification passed: workflow JSON parses, all workflow connections resolve, all Code-node JavaScript compiles, the stale `Any` -> `Male` simulation passes, and a backend mocked no-match sync returns `cancelled_empty_order = true`.
- Live targeted retest after backend deploy and workflow imports:
  - Male weaner sex preservation passed. `ORD-2026-8096C6` was created with header `Requested_Sex = Male` and two active Male Weaner `10_to_14_Kg` lines. The test order was cancelled.
  - The earlier Female Weaner `15_to_19_Kg` case is no longer a zero-match case because live stock now has one matching pig; it correctly created `ORD-2026-0B3C01` with one active Female Weaner `15_to_19_Kg` line. The test order was cancelled.
  - True zero-match workflow test using Female Weaner `7_to_9_Kg` left no active order for conversation `1774`.
  - Direct deployed-backend create+sync test proved the auto-cancel guard: `ORD-2026-009333` returned `cancelled_empty_order = true`, `fulfillment_status = no_match`, `matched_total = 0`, and final `Order_Status = Cancelled`.
  - Final cleanup verification returned `no_match` for both intake context and active customer order context on conversation `1774`.
- Wider regression after those fixes exposed a remaining structural issue in `1.2`: `create_order_with_lines` was still two backend calls (`create order` then `sync lines`). If the second call failed or timed out, an active zero-line Draft could remain. Example: `ORD-2026-CA751C`, created by `Sam Phase 5.7 intake`, had zero lines and was manually cancelled during cleanup.
- Structural fix prepared in repo:
  - Added backend endpoint `POST /api/master/orders/create-with-lines`.
  - Added backend service `create_order_with_lines(order_data, sync_data)`.
  - The backend now creates the order, syncs lines, and cancels the newly-created Draft if sync fails or if matched quantity is zero.
  - Updated `1.2 - order-steward` so `HTTP - Create With Lines Order` calls the atomic backend endpoint directly.
  - `HTTP - Create Order` still calls the normal header-only create endpoint.
  - Local validation passed: Python compiles, `1.2` JSON parses, all workflow connections resolve, Code-node JavaScript compiles, create-order URL and create-with-lines URL are correct, and a mocked zero-match atomic create returns `order_status = Cancelled`.
- Live retest after backend deploy and `1.2` import:
  - WR01 passed: `ORD-2026-A1F319` created 2 active Male Grower `20_to_24_Kg` lines, Albertinia, EFT; order was cancelled.
  - WR02 created the expected Female Grower `35_to_39_Kg` Draft `ORD-2026-63B833` with 1 active line, Riversdale, Cash; validation/cancel initially hit a Sheets quota-related `500`, then the order was cancelled in cleanup.
  - WR03 created the expected Male Piglet `5_to_6_Kg` Draft `ORD-2026-0F3604` with 2 active lines, Albertinia, Cash; cleanup initially hit a Sheets quota-related `500`, then the retry completed and active lookup returned `no_match`.
  - Final cleanup verification returned `no_match` for both intake context and active customer order context on conversation `1774`.
  - Important operational note: multi-case automated live tests still push Google Sheets read/write quota too hard. Further regression should run one case at a time with cooldown, or backend should add read caching/retry/backoff before larger automated batches.
- Single no-stock regression passed on 2026-05-13:
  - Request: 1 Female Weaner `7_to_9_Kg`, Riversdale, Friday 14:00, EFT.
  - Intake linked `ORD-2026-CBAE14`, but active customer lookup returned `no_match`.
  - Order detail confirmed `Order_Status = Cancelled`, `Payment_Status = Cancelled`, `active_line_count = 0`, and no order lines.
  - This verifies the atomic create-with-lines path does not leave an active zero-line Draft for a true no-stock request.

First live test scope:

- Use a safe Charl N Chatwoot conversation only.
- Start with the same verified facts: 1 Female Grower, `35_to_39_Kg`, Riversdale, Friday at 14:00, Cash.
- Confirm the intake reaches `Ready_For_Draft`. - Done.
- Confirm exactly one Draft order is created and `ConversationId` is stored. - Done: `ORD-2026-A822D3`, `ConversationId = 1774`.
- Confirm active order lines match the active intake items. - Done: one Female Grower `35_to_39_Kg` line.
- Confirm Chatwoot custom attributes are updated with the new draft order ID. - Pending manual/n8n execution confirmation; backend order and intake link are verified.

Draft edit behavior:

- Before approval: allow changes, additions, removals, and re-sync lines.
- After approval/reservation/completion: block automatic changes or route to admin review.
- Ambiguous item edits must ask one disambiguation question.

### 5.8 Automatic Formal Quote Readiness And Generation - Complete And Live-Verified

Required outcome:

- Formal quote PDF generation is backend-owned and should not depend on the customer using the correct quote-request wording.
- Draft orders may exist before all quote facts are known.
- A formal quote PDF is generated only when the draft is quote-ready: Draft status, active order lines, complete line count versus requested quantity, customer name, collection location, valid `Payment_Method = Cash|EFT`, and line prices.
- After draft create-with-lines, order header/payment updates, or line sync, backend checks quote readiness and automatically generates a quote when ready.
- If the latest quote already matches the current draft fingerprint, backend returns the existing quote instead of creating duplicate versions.
- Quote PDFs continue to use the Phase 2 backend document path and `ORDER_DOCUMENTS`.
- Sam must not claim a quote was generated or sent unless backend document generation/delivery confirms it.
- After a quote is generated automatically, Sam should say the quote is ready/generated, mention the reference when available, and ask whether the customer wants it sent.
- If the draft is not quote-ready, Sam should ask for the first missing required fact instead of offering a fake quote. Payment method should be asked as Cash/EFT before quote generation.
- Sam must keep the distinction clear: Draft order = saved structured order; formal quote = backend-generated PDF document; approval = human/farm-manager order acceptance and reservation step.
- Once an order is sent for approval or approved, Sam should not leave the customer guessing about who will contact them. The customer-facing copy should explain that after approval the farm manager will provide collection/contact details.

Decision confirmed 2026-05-13:

- Do not rely on customer prompt phrasing to trigger quote generation.
- Payment method changes total cost, so quote generation must wait for `Cash` or `EFT`.
- Preferred behavior is automatic background quote generation once all quote-ready facts are present; sending the document remains a separate confirmed action.

Repo implementation started 2026-05-13:

- First controlled slice targets existing-draft formal quote generation.
- `1.2 - Amadeus Order Steward` now supports `action = generate_quote`, calling backend `POST /api/orders/<order_id>/quote` and returning compact document fields (`document_id`, `document_ref`, `total`, `valid_until`, Drive URL availability).
- `1.0 - Sam-sales-agent-chatwoot` now has a `GENERATE_QUOTE` route for backend intake `next_action = generate_quote` or a detected quote request with an existing draft/payment method.
- Quote requests with no linked draft but complete intake now treat backend `next_action = create_draft_then_quote` as a safe draft-create trigger instead of falling through to chat-only reply. Automatic quote generation immediately after that new draft is still not wired in this slice.
- Sam prompt rules now explicitly separate Draft order, formal quote PDF, and approval.

Automatic quote-readiness implementation added 2026-05-13:

- `modules.documents.quote_service.auto_generate_quote_if_ready()` checks backend order detail and returns `quote_ready`, `missing_fields`, `generated`, `skipped`, and compact `document` details.
- Quote fingerprints are stored in `ORDER_DOCUMENTS.Notes` so repeat create/update/sync calls can skip duplicate quote versions when the draft has not changed.
- `POST /api/master/orders/create-with-lines`, `PATCH /api/master/orders/<order_id>`, and `POST /api/master/orders/<order_id>/sync-lines` attach `auto_quote` to the backend response after successful mutations.
- `1.2 - Order Steward` preserves `auto_quote` on create-with-lines, update, and sync results.
- `1.0 - Sam Sales Agent` includes `auto_quote` in `StewardCompact` and has wording guidance for automatically generated quotes.

Claude review blocker fixes added 2026-05-13:

- Quote fingerprint no longer includes volatile `order_line_id`; resyncing the same logical lines should not create a duplicate quote.
- Fingerprint now includes rendered customer fields (`customer_name`, `customer_phone`, `collection_date`) alongside payment/location/line content.
- Manual `POST /api/orders/<order_id>/quote` also stamps the current fingerprint, so the next automatic check can recognize it as current.
- Quote readiness overlays `ORDER_MASTER` fields and can fall back to `ORDER_MASTER` + `ORDER_LINES` if formula-driven `ORDER_OVERVIEW` is not current yet.
- Auto-quote hook skips immediately when sync/create results show partial or incomplete fulfillment, before any PDF generation attempt.

5.8 closure checks:

- Complete: draft reaches quote-ready with payment method present -> quote is generated automatically and Sam offers to send it.
- Complete: draft missing payment method -> no quote is generated and Sam asks Cash/EFT.
- Follow-up moved to Phase 5.8.1: explicit "send it" after quote-ready must call the existing document delivery path.

Live verification 2026-05-13:

- Direct backend create-with-lines without payment created `ORD-2026-2BF6EE` with one active Female Grower `35_to_39_Kg` line and returned `auto_quote.quote_ready = false`, `generated = false`, `missing_fields = ["payment_method"]`.
- Patching `ORD-2026-2BF6EE` to `Payment_Method = Cash` generated `DOC-2026-19D8D0`, `Q-2026-2BF6EE`, total `R1,400.00`.
- Re-syncing the same requested item cancelled/recreated the line but returned `auto_quote.reason = latest_quote_current` with the same document ID/ref; no duplicate quote version was created.
- Full workflow smoke via `1.0` webhook for safe conversation `1774` created `ORD-2026-BCC742` through `1.0 -> 1.2 -> backend`, generated `DOC-2026-3960F1`, `Q-2026-BCC742`, total `R1,400.00`, with a `Quote_Fingerprint` note.
- Cleanup completed: `ORD-2026-2BF6EE` and `ORD-2026-BCC742` were cancelled, and active lookup for conversation `1774` returned `no_match`.
- Chatwoot wording check passed. Sam replied: `Thanks, Charl. Your draft order (ORD-2026-BCC742) for 1 female grower pig (35-39 kg), collection at Riversdale on Friday at 14:00, with cash payment is ready. Your formal quote with reference Q-2026-BCC742 has also been generated. Would you like me to send the quote to you now?`
- Phase 5.8 is complete and live-verified. Quote sending remains a separate confirmed document-delivery step.

### 5.8.1 Quote Send Confirmation - Implemented In Repo

Required outcome:

- When Sam offers to send a generated/current quote and the customer confirms, the workflow must call backend document delivery before Sam says it was sent.
- The confirmation state must survive to the next customer turn through Chatwoot `custom_attributes.pending_action = send_quote`.
- `1.0` must route a short confirmation such as `Yes, please` to a real send action, not a reply-only promise.
- `1.2` must expose a steward action for sending the latest generated quote for an order.
- Backend must find the latest non-voided quote, delegate to the existing `send_order_document()` path, and return `document_status = Sent` only after delivery confirms.
- After the send attempt, `pending_action` must be cleared.

Repo implementation 2026-05-13:

- Backend added `POST /api/orders/<order_id>/quote/send-latest`.
- `1.2 - Order Steward` added `action = send_latest_quote`.
- `1.0 - Sam Sales Agent` added `SEND_QUOTE`, `Set - Build Send Quote Payload`, `Call 1.2 - Send Quote`, `HTTP - Clear Pending After Send Quote`, and `Set - Restore Send Quote Result`.
- Generated/current quote offers now set `pending_action = send_quote` after create, update, sync, and manual quote generation paths.
- Sam prompt now says `SEND_QUOTE` may only be described as sent when `BackendSuccess = true`.
- Extractor skips while `pending_action = send_quote`, so a short confirmation is not misread as an order edit.

Still required before closing 5.8.1:

- Complete. The final live phrase check passed after the `1.2` linear send correction.

Live smoke 2026-05-13:

- Backend deployed and `1.2` / `1.0` imported.
- Safe conversation `1774` created test order `ORD-2026-DA3EAC`: Draft, Cash, Riversdale, one active Female Grower `35_to_39_Kg` line.
- Direct quote generation created `DOC-2026-B05CD6`, `Q-2026-DA3EAC`, total `R1,400.00`.
- Direct `POST /api/orders/ORD-2026-DA3EAC/quote/send-latest` returned `success = true`, `delivery_webhook_sent = true`, `document_status = Sent`.
- Actual `1.0` confirmation route was tested with a synthetic inbound `Yes, please` and Chatwoot `pending_action = send_quote`; it called the steward/backend path and stamped `ORDER_DOCUMENTS.Sent_By = Sam Phase 5.8.1 quote send`, `Sent_At = 13 May 2026 11:05`.
- Cleanup completed: `ORD-2026-DA3EAC` cancelled, one line cancelled, intake `INTAKE-2026-DE3E83` closed, active lookup for conversation `1774` returned `no_match`.
- Direct backend create-with-lines control passed with `ORD-2026-7D0692`: `auto_quote.generated = true`, `DOC-2026-A12EEF`, `Q-2026-7D0692`; cleanup cancelled the order.
- Backend hardening prepared: `POST /api/orders/<order_id>/quote/send-latest` now runs `auto_generate_quote_if_ready()` if no quote exists yet, then sends the generated/latest quote. Local Flask monkeypatch passed with `quote_ensured = true` and `document_status = Sent`.
- Integrated retest after backend redeploy passed on conversation `1774`: follow-up `Yes, please create the draft order.` created `ORD-2026-1D782B`, auto-generated `DOC-2026-CAA774` / `Q-2026-1D782B`, wrote Chatwoot `pending_action = send_quote`, and Sam offered to send it.
- Follow-up `Yes, please` sent the PDF through `1.5`, changed the document to `Sent`, stamped `Sent_By = Sam Phase 5.8.1 quote send`, cleared Chatwoot `pending_action`, and Sam replied that the formal quote was sent.
- Cleanup completed: `ORD-2026-1D782B` cancelled, intake `INTAKE-2026-782FD8` closed, Chatwoot order attributes cleared, and both active lookup endpoints returned `no_match`.
- Parser edge fixed in repo: `create/prepare/make + draft` now counts as order commitment, so `create the draft and send me the quote` is covered. Local regex simulation confirms quote-only wording still does not trigger commitment.
- Follow-up patch prepared after exact-phrase live check: when a quote-requested create result is returned, `1.0` now suppresses the draft-only reply and calls `Call 1.2 - Send Quote` so backend `send-latest` can generate-if-needed and send. JSON and Code-node syntax validation passed.
- Backend-owned correction prepared after Claude review: removed the fragile `1.0` post-create fan-out/send branch, added backend `send_quote_if_ready` handling to create-with-lines, made `1.2` pass and echo `quote_send`, and made `1.0` set/clear `pending_action` from the backend `quote_send` result. Local validation passed; live deploy/import/retest remains required.
- Retest after upload/deploy did not pass: the live `1.0 -> 1.2` create path created a correct draft but did not generate/send the quote, while direct backend controls showed quote generation and `send-latest` work. Direct backend create-with-lines with `send_quote_if_ready = true` generated and delivered a PDF but timed out before marking `ORDER_DOCUMENTS` as `Sent`. Repo patch increases document-delivery webhook timeout to 90 seconds and keeps the n8n response parser tolerant. Deploy backend again and re-import the current `1.2` export before the next exact one-turn smoke.
- Follow-up correction: `1.2` now performs the post-create send as a second linear backend request after create-with-lines returns with `auto_quote.document.document_id`. The backend create request no longer receives `send_quote_if_ready`, avoiding the long single Flask request. Import updated `1.2` again, then rerun the exact one-turn smoke.
- Final one-turn smoke passed on `ORD-2026-D3BB1C`: draft and active line created, `Q-2026-D3BB1C` generated and sent through `1.5`, `ORDER_DOCUMENTS.Document_Status = Sent`, Chatwoot `pending_action` cleared, and Sam correctly said the formal quote had been sent. Cleanup cancelled the order, closed intake `INTAKE-2026-D9B528`, cleared Chatwoot attributes, and active lookup returned `no_match`.

Live test progress 2026-05-13:

- Temporary test draft `ORD-2026-AC3DFF` was created for Charl N with `ConversationId = 1742`, `Payment_Method = Cash`, and one active Female Grower `35_to_39_Kg` line.
- First direct `1.0` webhook quote request returned `ok = true` but did not generate a document, so the route did not reach `GENERATE_QUOTE`.
- n8n execution detail showed the workflow stopped earlier at `HTTP - Get Conversation Messages` with Chatwoot `404 Resource could not be found`.
- Backend control call proved document generation itself is healthy: `POST /api/orders/ORD-2026-AC3DFF/quote` generated `DOC-2026-1B44A1`, `Q-2026-AC3DFF`, total `R1,400.00`, file `QUO_2026_05_13_AC3DFF_V1_(R1,400.00)_Cash.pdf`.
- Route fix prepared after the failed `1.0` test: carry `PaymentMethod` through `Edit - Keep Chatwoot ID's`, and allow quote-intent + order ID to route to `GENERATE_QUOTE` even if `1.0` payment context is missing. Backend remains the final guard for missing payment method.
- History-fetch resilience fix prepared: `HTTP - Get Conversation Messages` now continues on fail so a Chatwoot history lookup 404 degrades to `ConversationHistory = N/A` instead of stopping the whole customer workflow.
- Retest after import passed the actual quote-generation route: `1.0 -> 1.2 -> backend` generated `DOC-2026-50E0D5`, `Q-2026-AC3DFF-V2`, total `R1,400.00`, created by `Sam Phase 5.8 quote`.
- Remaining issue from that retest: final `HTTP - Send Chatwoot Reply` returned Chatwoot `404 Resource could not be found` after the quote was generated. A URL fallback fix was prepared so the reply node can use current item IDs, `Edit - Keep Chatwoot ID's`, or `Code - Normalize Incoming Message` IDs instead of relying on only one source.
- Retest after the URL fallback generated `DOC-2026-ACE2E9`, `Q-2026-AC3DFF-V3`, total `R1,400.00`, created by `Sam Phase 5.8 quote`; final `HTTP - Send Chatwoot Reply` still returned Chatwoot `404`.
- Next reply-node fix prepared: make `HTTP - Send Chatwoot Reply` mirror the live-verified `1.4` Chatwoot send-message shape, using fixed account `147387`, normalized `ConversationId`, and an explicit JSON body.
- Final generation-and-reply retest passed after correcting the safe test order's `ConversationId` to `1774`:
  - `1.0 -> 1.2 -> backend` generated `DOC-2026-001270`, `Q-2026-AC3DFF-V5`, total `R1,400.00`, created by `Sam Phase 5.8 quote`.
  - Sam replied in Chatwoot: `Charl, your formal quote has been generated with reference Q-2026-AC3DFF-V5. Would you like me to send it to you now?`
  - This confirms generation only, with explicit customer confirmation before document sending.
- Test order cleanup completed: `ORD-2026-AC3DFF` was cancelled after verification, `active_line_count = 0`, `cancelled_line_count = 1`, `Payment_Status = Cancelled`.

### 5.9 n8n Payload And Chatwoot Attribute Cleanup - Planned After Intake Is Proven

Required outcome:

- Reduce duplicated fields passed between `1.0` nodes.
- Keep only compact, intentional objects in prompts and node transitions.
- Chatwoot custom attributes should be reduced to routing state such as `conversation_mode`, `order_id`, and `pending_action`.
- Do not remove legacy attributes or payload branches until intake-driven routing is live-verified.

Cleanup notes captured during 5.6/5.7:

- Remove the word `shadow` from runtime concepts once intake becomes the primary order-intake truth; keep a short historical note only in changelog/docs.
- Collapse duplicated order fact extraction so `ORDER_INTAKE_STATE` / `ORDER_INTAKE_ITEMS` become the primary source for draft/quote order facts.
- Reduce or remove legacy `order_state` create-draft logic once intake-driven create/update/quote flows are verified.
- Route mismatch fix is prepared: intake commitment detection is broader and legacy header-only draft creation is blocked unless line-ready `requested_items` exist. Cleanup should still leave one gate for draft creation, not two competing interpretations of commitment.
- Remove cross-node fallback reads added during 5.7 troubleshooting where they are no longer needed after the flow is simplified.
- Keep `1.2 - Amadeus Order Steward` as the only order-writing workflow; do not duplicate order creation or line sync in `1.0`.
- Keep Chatwoot attributes lightweight: `conversation_mode`, `order_id`, `order_status`, `pending_action`, and payment method only if still operationally useful.
- Review Sam prompt context and remove duplicated large payloads once compact intake + steward context is sufficient.

Progress 2026-05-13:

- Contract docs updated: `send_quote` is now documented as a valid Chatwoot `pending_action`, and `generate_quote` / `send_latest_quote` are documented as live steward actions.
- `1.0` runtime intake naming cleaned up: `intake_shadow_*` fields and the three intake shadow node names were renamed to primary intake naming.
- Chatwoot order-context writes now prefer current steward/result state before falling back to old Chatwoot attributes.
- `1.2 Code - Format Create With Lines Result` now echoes `payment_method` and `collection_location` from the normalized create payload so the successful create/send path can preserve `payment_method` in Chatwoot.
- Validation passed: `1.0` and `1.2` JSON parse, all Code-node JavaScript compiles, no `1.0` connection references are broken, and no `intake_shadow` runtime references remain.

### 5.10 Order Archive / History Scaling - Future Design, Not Now

Current decision:

- Keep completed and cancelled orders in `ORDER_MASTER` for now.
- Treat `ORDER_STATUS_LOG`, `ORDER_DOCUMENTS`, and `ORDER_LINES` as the audit/history layer.
- Use filtered API queries and web app views to separate active vs historical orders instead of physically moving rows.

Why not split yet:

- Moving terminal orders to a separate sheet would require every formula, API read, document link, order detail view, and status transition to understand two sources.
- It increases the risk of Sam, the web app, or document generation missing old orders.
- Current scale is small enough that filtered reads are simpler and safer.

Future trigger points:

- `ORDER_MASTER` becomes slow or hard to manage manually.
- Google Sheets formula recalculation becomes unreliable.
- Operational views become cluttered even with filters.
- We need long-term reporting or retention controls that are cleaner in a separate archive.

Preferred future approach:

- Add an archive/read model only after the active-order lookup is stable.
- If needed, create an `ORDER_HISTORY` or `ORDER_ARCHIVE` design where terminal orders are copied or mirrored with immutable references.
- Do not move rows manually without backend support and a tested lookup strategy.

## Phase 6: Web App Order Usability - In Progress / Ongoing

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

## Phase 7: Broader Workflow Improvements - Not Started

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

### 7.2 Database Scaling Review - Future Planning

Current decision:

- Keep Google Sheets as the operational data store for now while order behavior is still being stabilized.
- Do not migrate database storage during the active Sam/order workflow cleanup.
- Treat the recent Google Sheets `429` quota errors as a scaling warning, not an immediate blocker for current low-volume operations.

Why this matters:

- Google Sheets is useful for visibility, manual checks, and simple operational editing.
- It is not designed as a high-concurrency transactional database.
- Automated regression runs already showed quota pressure because each test case performs multiple backend reads/writes plus n8n workflow calls.
- Normal customer conversations are slower, so this is less urgent today, but sales volume will increase once meat sales and broader operations go live.

Preferred future direction:

- Evaluate moving transactional data to Postgres, with Supabase Postgres as the likely best option to assess first.
- Keep Google Sheets as reporting/export/operator visibility if still useful.
- Use Postgres as the source of truth for transactional tables that need indexes, concurrency, and atomic writes.

Candidate tables for future migration:

- `ORDER_MASTER`
- `ORDER_LINES`
- `ORDER_INTAKE_STATE`
- `ORDER_INTAKE_ITEMS`
- `ORDER_DOCUMENTS`
- later: pig stock / availability data if Sheets becomes too slow or fragile

Why Supabase Postgres is attractive:

- Managed Postgres with a usable dashboard/table editor.
- Better operator visibility than raw database-only hosting.
- Good fit for future web app/admin tooling.
- Supports proper indexes on `order_id`, `conversation_id`, `customer_phone`, `order_status`, and document references.
- Supports transactions so create order + sync lines + rollback/cancel can be handled as one database operation.

Cost planning:

- Expect roughly USD 25/month as a practical starting point for a Supabase Pro-style production database tier.
- Higher usage, backups, storage, or extra environments may increase this later.
- Revisit exact pricing and provider choice before implementation; do not lock in until the migration phase starts.

Suggested migration approach:

- First stabilize the current backend behavior and n8n flow.
- Add a backend data-access/repository layer so code is not tightly coupled to Google Sheets calls.
- Migrate order/intake/document transactional tables first.
- Keep Google Sheets read-only or synced as operational views during transition.
- Only retire Sheets as a source of truth after the web app and Sam are confirmed against Postgres.

### 7.3 Oom Sakkie Operational Order And Document Lookup - Future Planning

Goal:

- Let Oom Sakkie answer internal operator questions about orders without requiring the operator to open the web app or Google Sheets.

Required outcome:

- Oom Sakkie can look up open orders by order ID, customer name, or phone number.
- Oom Sakkie can summarize order status, items, totals, payment method, collection location/date, notes, and outstanding actions.
- Oom Sakkie can retrieve quote/invoice document records and provide or send the correct document link when an operator asks for it.
- Oom Sakkie must use backend order/document endpoints, not direct sheet guessing.
- If multiple orders match a name or phone number, Oom Sakkie must ask one disambiguation question.
- Customer-facing delivery of quotes/invoices remains controlled by the document delivery path; internal lookup must not accidentally send a document to a customer unless that action is explicit and confirmed.

Planning note:

- This complements Phase 6 web app usability. The web app remains the full operations interface; Oom Sakkie becomes the quick internal assistant for checks and document retrieval when operators are away from the app.

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

## Phase 9: Pig, Weight, And Reporting Improvements - Not Started

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

### 9.7 Business Scenario Calculator - Future Planning

Goal:

- Build a planning calculator where business assumptions can be changed and the totals recalculate automatically.

Preferred starting point:

- Google Sheet model first, because it is easier to inspect, adjust, and refine while the business scenarios are still changing.

Required outcome:

- Compare scenarios such as selling live stock, selling slaughter-ready animals, slaughtering and selling meat, and later selling meat directly.
- Allow editable assumptions for quantities, prices, costs, margins, survival/profit targets, and time periods.
- Calculate how many animals or meat units are needed to hit a monthly survival/profit target.
- Make formulas visible and maintainable, with clearly marked input cells vs calculated cells.
- Keep this separate from live operational order sheets; it is a planning model, not the system of record.

Clarification to confirm when this phase starts:

- Which first scenarios, cost lines, and target-profit fields should be included in the first calculator version.

## Phase 10: Farm Operating System Integration - Not Started

Goal: bring Sam, Oom Sakkie, the web app, backend modules, weather logging, Synsynk solar data, n8n workflows, and Google Sheets into one documented operating-system structure.

Timing rule:

- do not start this umbrella integration until Sam/order behavior is stable enough that expanding the system will not hide existing sales bugs

Required outcome:

- document every major workflow and platform under one system map
- define ownership for each module: sales, farm operations, pig records, worker assistant, weather, solar, reporting, notifications, and admin web app
- plan the web app as the main operating interface with clear modules for sales/orders, piggery, weather, irrigation, electricity/solar, and other farm systems as they are added
- the first screen after login should eventually make those modules easy to reach and show the most important status for each module
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
- Phase 5.8 automatic quote readiness — complete and live-verified 2026-05-13: backend `auto_quote` after create/update/sync, quote fingerprint duplicate skip, `1.2` propagation, `1.0` steward context/wording guidance, and Chatwoot wording confirmed.

Recommended next:

1. **Phase 5.9 cleanup** - reduce duplicated shadow/legacy routing after intake/quote behavior is proven.
2. **Phase 6** (parallel polish when useful) - web app order detail parity and action clarity.

Pick the next item deliberately before implementation so docs, workflow exports, and tests stay aligned.
