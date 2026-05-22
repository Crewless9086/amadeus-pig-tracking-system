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
| Phase 5: Safe Order Review For Sam | Complete through 5.8.1 one-turn quote delivery; Phase 5.9 cleanup slice 2 live-verified | Continue Phase 5.9 cleanup only if another narrow cleanup slice is chosen deliberately. |
| Phase 6: Web App Order Usability | 6.1 And 6.2 Complete; broader Phase 6 ongoing | Continue only with deliberate small usability slices. |
| Phase 7: Broader Workflow Improvements | 7.0, 7.1, 7.2 Complete; 7.3C Complete And Live-Verified; 7.3D Complete And Live-Verified | Weather/Solar/Oom Sakkie UX notes captured for later deliberate slices. |
| Phase 8: Breeding Board Improvements | 8D Live-Verified; 8E/8F Planned | Plan breeding-board sorting before the next breeding analytics work. |
| Phase 9: Pig, Weight, And Reporting Improvements | 9.1A Live-Verified; 9.1B Browser-Verified; 9.2A/9.2B Owner-Verified; 9.3/9.3B Owner-Verified; 9.4 Current Slice Complete; 9.5 Visible; 9.5B Planned; 9.6A Browser-Verified; Parked For Now | Resume only when a parked 9.x refinement becomes the selected priority. |
| Phase 10: Farm Operating System Integration | 10.1 Complete; 10.2A Verified; 10.2B/C Dry-Run Complete; 10.2D Applied And Verified; 10.2E Complete; 10.2F Deployed And Verified; 10.2G Planned; 10.2H Verified; 10.2I Verified; 10.2J Verified; 10.2K1/10.2K2/10.2K3 Verified; 10.2L Local; 10.2L2 Owner-Pending; 10.2L3 Local; 10.2L4 Complete And Deployed-Verified; 10.3A Inventory Complete; 10.3B Agreed; 10.3C Applied And Verified; 10.3D/10.3E Deployed-Verified; 10.3F Deployed And Verified; 10.3G Live-Verified; 10.3H Local | Deploy and verify `/api/telemetry/power/recent`, then decide whether Oom Sakkie should use it for last-24h questions. |
| Phase 11: Pork Sales Business Module | Discovery Source Captured | Refine business model doc before implementation planning. |

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

### 5.9 n8n Payload And Chatwoot Attribute Cleanup - In Progress

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

Live smoke 2026-05-14:

- After importing the updated `1.0` and `1.2`, the exact one-turn quote message passed again on safe conversation `1774`.
- Workflow created `ORD-2026-E3BFCF` with one active Female Grower `35_to_39_Kg` line, Riversdale collection, and `payment_method = Cash`.
- Quote `DOC-2026-923849` / `Q-2026-E3BFCF` was generated and sent through `1.5`; `ORDER_DOCUMENTS.Document_Status = Sent`, `Sent_At = 14 May 2026 02:20`, `Sent_By = Sam Phase 5.7 intake`, total `R1,400.00`.
- The new runtime note on the line is `Phase 5.9 intake extraction`, confirming the renamed intake path is live.
- Direct Chatwoot attribute read was not possible without the Chatwoot API token, but backend order/document state confirmed the create/generate/send path and preserved `Cash` on the order.
- Cleanup completed: `ORD-2026-E3BFCF` cancelled, `INTAKE-2026-AA2FAC` closed, active customer lookup returned `no_match`, and intake lookup returned `no_match`.

Progress 2026-05-17:

- `1.0` route cleanup prepared without changing the proven order/quote/send graph: removed remaining `debug_*` routing fields from create gating, route decision, and lead classification outputs.
- Removed the fragile route-decision fallback reads from `Code - Should Create Draft Order?`, `Code - Decide Order Route`, and `Code - Build Intake Draft Link Payload`; these nodes now rely on item-local intake/steward fields.
- `Set - Draft Order Payload` now carries `created_from_intake` and `intake_id` into `1.2`, so the intake-draft link node can use the steward result instead of reading old node state.
- `1.2` now preserves and echoes `created_from_intake`, `intake_id`, conversation/customer IDs, channel, language, `payment_method`, and `collection_location` on the create-with-lines result.
- `1.0` workflow README updated to current Phase 5.9 intake naming, while keeping historical 5.6/5.7 notes clear.
- Local validation passed after cleanup: both workflow JSON exports parse, all Code-node JavaScript compiles, `1.0` connection references are intact, and the targeted `debug_intake` / `debug_quote` / `intake_shadow` / route-fallback reads are gone.
- First post-upload smoke created `ORD-2026-3E46B8` and generated `DOC-2026-44FC1C` / `Q-2026-3E46B8`, but did not send the PDF; quote stayed `Generated`.
- Follow-up fix prepared in `1.2`: `Set - Build Create With Lines Body` no longer hard-codes `send_quote_if_ready = false`; it now mirrors `Code - Normalize Order Payload`, and the post-create send IF checks the same normalized/body flag. Re-import `1.2` before retesting.
- Retest after `1.2` upload created and linked `ORD-2026-D547AD`, but immediate quote generation/send still missed; a delayed direct `send-latest` control generated and sent `DOC-2026-0519FE` / `Q-2026-D547AD`.
- Backend timing hardening prepared: `send-latest` and create-time quote-send now retry quote readiness briefly when the only blocker is likely Google Sheets visibility lag (`order`, `active_order_lines`, or `complete_order_lines`). Deploy backend before the next one-turn smoke.
- Restart-recovery test on 2026-05-17 found leftover smoke draft `ORD-2026-683FC3` and intake `INTAKE-2026-25FCA7` on safe conversation `1774`: draft/header/line were correct, but no quote document existed. Production `send-latest` and direct production quote generation both returned `500`; local repo code generated `DOC-2026-8D3420` / `Q-2026-683FC3` successfully against live Sheets/Drive, and production then sent that existing quote successfully (`Document_Status = Sent`). Cleanup cancelled `ORD-2026-683FC3`, closed the intake, cleared Chatwoot attributes, and verified active order/intake lookups returned `no_match`. Do not call Phase 5.9 closed until production quote generation passes in the real one-turn path without local recovery.
- Fresh one-turn smoke on 2026-05-17 after cleanup reproduced the live n8n gap: `1.0` accepted the exact create-and-send quote message and created `ORD-2026-644D1A` with one active Female Grower `35_to_39_Kg` line, Cash, Riversdale, and generated `DOC-2026-02ADA4` / `Q-2026-644D1A`, but the document remained `Generated` until a direct backend `send-latest` control marked it `Sent`. Intake `INTAKE-2026-56A068` also stayed unlinked (`draft_order_id` blank), which matches a stale/lean `1.2` create result that does not echo `created_from_intake` / `send_quote_if_ready`. Repo patch added defensive metadata recovery in `1.0 Code - Store Draft Order Context`; local validation passed for JSON parse, all Code-node JavaScript, and the `1.2` create-with-lines post-create send branch connections. Re-import current `1.2` and updated `1.0`, then rerun the exact one-turn smoke. Cleanup cancelled `ORD-2026-644D1A`, closed the intake, cleared Chatwoot attributes, and active order/intake lookups returned `no_match`.
- Final Phase 5.9 slice-2 smoke passed on 2026-05-17 after n8n API upload of active `1.0` (`V73HaIqVpzv44SFc`) and `1.2` (`YDRs6fwde7MzPYn7`): `1.2 Set - Build Create With Lines Body` now keeps backend create `send_quote_if_ready = false`, `1.2` sends the latest quote in a separate post-create request after a 45-second quota-cooldown Code node, and `1.0 Code - Store Draft Order Context` is a simple pass-through again because `1.2` echoes create metadata. Exact one-turn message on safe conversation `1774` created `ORD-2026-6E5A81`, linked intake `INTAKE-2026-F787C6` (`draft_order_id = ORD-2026-6E5A81`), generated `DOC-2026-E8A19A` / `Q-2026-6E5A81`, sent the PDF through `1.5`, and marked `ORDER_DOCUMENTS.Document_Status = Sent` with `Sent_By = Sam Phase 5.9 intake`. n8n executions `1.2 #44579` and `1.0 #44581/#44582` succeeded. Cleanup cancelled `ORD-2026-6E5A81`, closed the intake, cleared Chatwoot attributes, and active order/intake lookups returned `no_match`.

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
- reserve/release success feedback on order detail is done (API `message` + `changed_count` + `warning`)
- **Pen / location labels:** dropdowns and pig pickers should show **pen name** (human-readable) alongside or instead of raw **pen ID** wherever the app still exposes IDs only
- **Known route mismatch to park:** `static/js/litterDetail.js` currently calls `/api/pig-weights/litter/<id>/detail`, while the Flask route is `/api/pig-weights/litter/<id>`; fix under web app/pig detail usability unless it blocks live order work
- clear approve/reject/cancel buttons
- order detail actions must match backend rules: show approve/reject when `Order_Status = Pending_Approval`, show cancel before terminal statuses, reserve/release when appropriate; avoid forcing ops through OOM SAKKIE workflows when parity with API is intended
- safe release/reserve controls
- useful logs/history
- clear success/failure messages
- less manual debugging
- short progress/status messaging for background actions such as reserve, release, reject, and cancel

Rule:

Do not redesign the app before the backend order behavior is safe.

### 6.1 Order Detail Action Parity - Complete For Now

Implementation added 2026-05-17:

- `/order/<order_id>` now exposes a `Cancel Order` button wired to `POST /api/orders/<order_id>/cancel`.
- Order action visibility now hides all order-level actions for `Cancelled` and `Completed`, shows approve/reject only for `Pending_Approval`, shows complete only for `Approved`, and shows cancel for non-terminal Draft/Pending/Approved orders.
- Reserve, release, send-for-approval, approve, reject, cancel, and complete actions now disable the action row while running and show short working labels.
- Approve, reject, cancel, and complete require confirmation before calling the backend.
- Order action success text now prefers backend `message`, preserves reserve/release `changed_count` detail, and appends `warning` / `reserve_warning` where returned.

Verification so far:

- `node --check static/js/orderDetail.js` passed.
- Flask app import via `.venv` passed.

Owner acceptance / follow-up:

- Cancel action was browser-tested by owner and working.
- Owner will continue live testing during normal use and make notes for a future small polish pass if needed.

### 6.2 Orders List Usability - Complete For Now

Implementation added 2026-05-17:

- `/orders` now follows the same operating pattern as Sales Availability: summary cards, filter grid, clear filters button, and operational cards.
- Added status tabs for Active, Draft, Pending Approval, Approved, Completed, Cancelled, and All.
- Default tab is Active so cancelled/completed history no longer dominates the working view.
- Added filters for search, order source, payment method, and collection location.
- Order cards now show status/approval, payment method, request summary, active lines, reserved count, value, collection location, source, and updated date.

Verification so far:

- `node --check static/js/orders.js` passed.
- Flask test client returned the updated `/orders` template.
- Local dev server restarted and now serves the updated `/orders` page.

Still required:

- Owner will continue live testing during normal use and make notes for a future small polish pass if needed.

## Phase 7: Broader Workflow Improvements - In Progress

Only after order stability:

### 7.0 Backend Verification And Service Boundary Cleanup - Complete

This is a planned technical-debt checkpoint, not a reason to delay Phase 1.8.

Current status:

- 7.0A verification inventory added: `docs/02-backend/ORDER_VERIFICATION_MATRIX.md`.
- 7.0B local test harness started with stdlib `unittest` and mocked Google Sheets boundaries.
- Passing coverage added for `create_order`, `update_order`, basic order-line CRUD, `reserve_order_lines`, `release_order_lines`, `send_order_for_approval`, `approve_order` reserve-warning behavior, `reject_order`, `cancel_order`, `complete_order`, `sync_order_lines_from_request`, `get_active_customer_order_context`, and mocked route smoke behavior for order detail, create/update order, create/update/delete order lines, reserve/release, lifecycle actions, and sync validation/auto-quote attachment.
- First small backend boundary extracted: `modules/orders/order_status_log.py` owns status log ID generation and `ORDER_STATUS_LOG` appends; `order_service._write_order_status_log` remains as a compatibility wrapper.
- Second small backend boundary extracted: `modules/orders/order_reservation.py` owns reserve/release behavior; `order_service` keeps imported compatibility names for current routes and lifecycle code.
- Third small backend boundary extracted: `modules/orders/order_write.py` owns create/update order and basic order-line CRUD behavior; `order_service` keeps imported compatibility names for current routes and create-with-lines integration.
- Fourth small backend boundary extracted: `modules/orders/order_read.py` owns list/detail/active-customer lookup behavior; `order_service` keeps imported compatibility names for current routes.
- Fifth backend boundary extracted: `modules/orders/order_line_sync.py` owns requested-item matching and sync behavior; `order_service` keeps imported compatibility names for current routes and create-with-lines integration.
- Sixth backend boundary extracted: `modules/orders/order_lifecycle.py` owns send-for-approval, approve, reject, cancel, and complete behavior; `order_service` keeps imported compatibility names for current routes.
- Cleanup completed: legacy in-file bodies and unused imports were removed from `modules/orders/order_service.py`; it is now a compatibility facade over the extracted modules, with `create_order_with_lines(...)` kept as the current orchestration wrapper.
- Full mocked verification passed after cleanup, route CRUD smoke coverage, and Google Sheets cache coverage: 65 tests green on 2026-05-18.
- Controlled production checkpoint on 2026-05-18 exposed a deploy/live gap: direct production `POST /api/master/orders/create-with-lines` wrote `ORD-2026-D15B1E` with one active Female Grower `35_to_39_Kg` line but returned `500` instead of a clean response and did not attach a quote document. Cleanup succeeded: `ORD-2026-D15B1E` is `Cancelled`, `Payment_Status = Cancelled`, active lines `0`, cancelled lines `1`, and active lookup for conversation `1774` returned `no_match`.
- Local-code/live-data checkpoint on 2026-05-18 passed against the current workspace code: `ORD-2026-900422` returned `201`, `create_success = true`, `sync_success = true`, `complete_fulfillment = true`, auto-generated `DOC-2026-B474FD` / `Q-2026-900422`, and cleanup cancelled the order with active lookup back to `no_match`.
- Post-deploy production retest on 2026-05-18 still returned `500` from `POST /api/master/orders/create-with-lines`, but the write path mostly completed: `ORD-2026-CF8C38` was created with one active line and generated `Q-2026-CF8C38`. Cleanup succeeded through local-code/live-data access: final state `Cancelled`, `Payment_Status = Cancelled`, active lines `0`, cancelled lines `1`, and active lookup for conversation `1774` returned `no_match`.
- Render logs confirmed the production `500` was Google Sheets `429` read quota at `client.open(GOOGLE_SHEET_NAME)` / spreadsheet metadata fetch, not a failed order state transition.
- Google Sheets service fix prepared: cache the gspread client, opened spreadsheet, and worksheet handles per process, and retry quota-related `APIError` calls with a short backoff. Added unit coverage to confirm repeated worksheet access does not reopen the spreadsheet.
- Final production checkpoint passed on 2026-05-18 after deploying the Google Sheets cache/retry fix: `ORD-2026-BBF8B3` returned cleanly with `success = true`, `create_success = true`, `sync_success = true`, `complete_fulfillment = true`, one active Female Grower `35_to_39_Kg` line, and generated `DOC-2026-6B90C2` / `Q-2026-BBF8B3`. Cleanup cancelled the order; final state `Cancelled`, `Payment_Status = Cancelled`, active lines `0`, cancelled lines `1`, and active lookup for conversation `1774` returned `no_match`.
- Phase 7.0 is complete.

Required outcome:

- add focused backend verification around order lifecycle and requested-item sync before large refactors
- make the `order_service.py` split visible and deliberate, aligned with `docs/02-backend/REFACTOR_PLAN.md`
- do not split `order_service.py` until Phase 1 lifecycle behavior and Phase 4/5 order-truth behavior are stable enough to protect with tests or clear manual checklists
- keep Google Sheets append/write behavior tied to documented sheet headers, not hidden assumptions about column order

Verification command:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

### 7.1 Intake And Payload Hygiene - Complete

Carry these when capacity allows; they do not block current order hardening.

#### 7.1A Payload Ownership Map - Complete

Decision:

- Do not edit workflow JSON until the payload ownership map is agreed.
- Keep `1.2 - Amadeus Order Steward` as the only order-writing workflow.
- Sam must not read or write order sheets directly. Sam should receive compact, backend-confirmed context through tools/workflow results.
- Inventory, pricing, reservation, order writes, quote generation, and document sending remain deterministic backend/steward actions.

Current problem:

- `1.0` currently carries overlapping facts across `order_state`, `intake_payload`, `intake_result`, `intake_raw_response`, `sales_agent_memory`, Chatwoot custom attributes, and `1.2` steward results.
- The same facts can appear in several places: `order_id`, `conversation_id`, `payment_method`, `collection_location`, requested items, quote state, and `pending_action`.
- This works, but it makes workflow changes fragile because downstream nodes may read old/stale values from a fallback source.

Ownership map:

| Object / layer | Owns | Should not own |
| --- | --- | --- |
| `ORDER_INTAKE_STATE` / `ORDER_INTAKE_ITEMS` | pre-draft customer intent, requested items, collection preference, payment method while order facts are still being gathered | final order status, document status, reservation state |
| `order_state` in `1.0` | temporary turn-level routing facts and normalized customer message interpretation | long-term order truth, document truth, stock truth |
| `1.2` steward normalized payload | one action request at a time, already cleaned for backend route calls | broad Sam prompt context or unrelated conversation memory |
| backend order APIs | confirmed order header, lines, lifecycle state, active-order lookup, quote/document records | customer conversation wording or LLM interpretation |
| Chatwoot custom attributes | lightweight routing state only: `conversation_mode`, active `order_id`, `order_status`, `pending_action`, and maybe `payment_method` while operationally useful | order history, full requested items, raw intake payloads, quote/document details |
| Sam prompt context / `StewardCompact` | compact read-only summary for the customer reply | raw workflow payloads, full sheets data, duplicated internal debug fields |

Planned cleanup order:

1. Document exact handoff contracts between `1.0` and `1.2`: create draft, update draft, sync lines, cancel, send for approval, generate quote, send quote, active lookup.
2. Standardize a slim `steward_result` / `order_context` shape for Sam replies so prompt context does not depend on raw node output.
3. Standardize Chatwoot custom attribute writes into one helper pattern or a small set of equivalent nodes that always preserve the approved lightweight fields.
4. Remove stale fallback reads only after each consuming node has one agreed source of truth.
5. Add narrow validation before each workflow import: JSON parse, Code-node JavaScript compile, connection integrity, and targeted payload-shape checks.

Open decisions before implementation:

- When an order becomes `Completed`, should Chatwoot keep `order_id` for follow-up context or clear it so a new order can start cleanly?
- Should cancelled orders keep `order_id` until the next customer order intent, or should cancel cleanup clear it immediately?
- Should `payment_method` remain a Chatwoot attribute, or should it only be read from backend active-order context?
- What compact fields should Sam receive for old/completed orders once order history lookup exists?

Recommendation:

- Keep only one active order linked in Chatwoot at a time.
- Use backend active-order lookup for current order context.
- Add a future read-only backend/steward action for old order history instead of giving Sam direct sheet access.
- Keep `payment_method` in Chatwoot for now because escalation and pending actions still use it, but treat it as a cache, not the source of truth.

#### 7.1B `1.0` -> `1.2` Handoff Contracts - Complete

Completed on 2026-05-18:

- Added `docs/04-n8n/workflows/ORDER_STEWARD_HANDOFF_CONTRACTS.md`.
- Documented the shared normalized fields accepted by `1.2`.
- Documented action contracts for `create_order_with_lines`, `update_order`, `sync_order_lines_from_request`, `cancel_order`, `send_for_approval`, `generate_quote`, `send_latest_quote`, `get_order_context`, and `get_active_customer_order_context`.
- Added `tests/test_workflow_contracts.py` to verify:
  - `1.2 Switch - Route by Action` still supports the required actions.
  - `1.2 Code - Normalize Order Payload` still normalizes the required handoff fields.
  - `1.0` still has the expected steward execute nodes.

Next 7.1 implementation slice after approval:

- 7.1C should standardize the slim `steward_result` / `order_context` shape used for Sam replies and Chatwoot updates before removing duplicated payload fields.

#### 7.1C Slim Steward Result And Order Context Shape - Complete

Completed on 2026-05-18:

- Extended `docs/04-n8n/workflows/ORDER_STEWARD_HANDOFF_CONTRACTS.md` with the consumer-facing result/context shapes:
  - `sam_order_state_slim`
  - `sam_steward_result_compact`
  - `existing_order_context`
  - approved Chatwoot custom attribute fields
- Documented what Sam may receive as compact backend-confirmed context and what must not be passed into Sam prompt context.
- Extended `tests/test_workflow_contracts.py` to verify:
  - `1.0 Code - Slim Sales Agent User Context` still emits the compact Sam context fields.
  - `1.2 Code - Format Get Order Context Result` still preserves the slim current-order context fields.

Next 7.1 implementation slice after approval:

- 7.1D should decide the Chatwoot `order_id` lifecycle policy for active, cancelled, completed, and old-order follow-up scenarios before workflow cleanup.

#### 7.1D Chatwoot `order_id` Lifecycle Policy - Complete

Completed on 2026-05-18:

- Extended `docs/04-n8n/workflows/ORDER_STEWARD_HANDOFF_CONTRACTS.md` with the Chatwoot `order_id` lifecycle policy.
- Decision: Chatwoot keeps one lightweight current-order pointer, not order history.
- Active orders keep the linked `order_id`; cancelled and completed orders may remain linked for immediate follow-up, but Sam must not mutate terminal orders.
- A new order may replace the linked `order_id` only after a clear new-order intent and successful backend draft creation.
- Multiple active matches must ask one disambiguation question and must not overwrite Chatwoot with a guessed order.
- Old order follow-up should use read-only backend/steward lookup later; do not store old order history or document details in Chatwoot custom attributes.
- Extended `tests/test_workflow_contracts.py` to verify every Chatwoot custom attribute write in the exported `1.0` workflow preserves the approved lightweight fields: `order_id`, `order_status`, `conversation_mode`, `pending_action`, and `payment_method`.

Next 7.1 implementation slice after approval:

- 7.1E should standardize the actual Chatwoot write pattern in workflow JSON only after deciding whether to keep separate HTTP write nodes or move toward a small helper-style pattern.

#### 7.1E Chatwoot Write Pattern Standardization - Complete

Completed on 2026-05-18:

- Decision: keep the existing separate Chatwoot HTTP write nodes for now to reduce workflow import risk.
- Standardized the outlier `HTTP - Set Conversation Human Mode` custom-attribute body to the same n8n expression style as the other write nodes.
- Documented the approved Chatwoot custom-attribute field order in `docs/04-n8n/workflows/ORDER_STEWARD_HANDOFF_CONTRACTS.md`:
  - `order_id`
  - `order_status`
  - `conversation_mode`
  - `pending_action`
  - `payment_method`
- Extra escalation fields remain allowed only after the five standard fields on the human-mode write.
- Extended `tests/test_workflow_contracts.py` to protect the approved writer-node list, required lightweight fields, and field order.

Next 7.1 implementation slice after approval:

- 7.1F should run a controlled local workflow-export validation pass and then decide whether this cleanup is ready for n8n import/live smoke, or whether one more narrow JSON cleanup is needed first.

#### 7.1F Workflow Export Validation - Complete

Completed on 2026-05-18:

- Extended `tests/test_workflow_contracts.py` with local workflow-export validation:
  - both `1.0` and `1.2` workflow exports parse as JSON
  - both exports have expected `nodes` and `connections`
  - every workflow connection references an existing node
  - every Code-node JavaScript block syntax-checks with Node using an async wrapper to match n8n Code-node behavior
- Targeted workflow contract suite passed with 10 tests.
- Full local suite passed with the broader backend and workflow checks.
- Decision: from local validation, the current exports are ready for controlled n8n import/live smoke.
- Recommended live smoke after import:
  - confirm existing linked order context still reads
  - confirm pending quote/cancel custom attributes are preserved
  - confirm human escalation still preserves order context
  - keep the test narrow to avoid Google Sheets quota pressure

Next 7.1 implementation slice after approval:

- 7.1G should be the controlled n8n import/live smoke checkpoint for the `1.0` export change, with `1.2` re-imported only if the live workflow is behind the repo export.

#### 7.1G n8n Import And Readback Smoke - Complete

Completed on 2026-05-18:

- Uploaded `1.0 - SAM - Sales Agent - Chatwoot` (`V73HaIqVpzv44SFc`) through the n8n public API.
- The API update needed the older live endpoint behavior: `PUT /api/v1/workflows/{id}` with `name`, `nodes`, `connections`, and a sanitized `settings` object. `active` is read-only and `settings.binaryMode` is rejected by the public API.
- Readback confirmed:
  - `1.0` remained active.
  - `1.0` has 112 nodes.
  - `HTTP - Set Conversation Human Mode` matches the local standardized 7.1E expression.
- Checked live `1.2 - Amadeus Order Steward` (`YDRs6fwde7MzPYn7`) without re-importing:
  - `1.2` remained active.
  - `1.2` has 55 nodes.
  - node count, connection count, and node names match the repo export.
- No forced customer escalation smoke was run because it would create unnecessary Chatwoot/Telegram side effects for a one-node custom-attribute expression cleanup.

Next 7.1 implementation slice after approval:

- Monitor the next natural live create/update/pending-action/escalation run and record whether Chatwoot custom attributes remain correct, or move on to the next planned Phase 7 item if no regression appears.

#### 7.1 Closure - Complete

Completed on 2026-05-18:

- Phase 7.1 is complete through 7.1A-G.
- `1.0` was uploaded to n8n and verified by API readback.
- `1.2` was checked against the repo export and not re-imported because the live workflow matched structurally.
- Local workflow contract validation remains in `tests/test_workflow_contracts.py`.
- Full local suite passed with 75 tests after the n8n upload/readback documentation.
- Remaining action is monitoring only: if the next natural live create/update/pending-action/escalation run shows a Chatwoot custom-attribute regression, log it under Phase 7.1 as a follow-up bug rather than reopening the whole cleanup phase.

Future follow-ups, not blockers for closing 7.1:

- **1.0 payload hygiene:** reduce duplicated / noisy fields crossing nodes; prefer one structured slim object per stage
- **Sam + completed orders:** order history lookup (backend / `1.2` action) so Sam can reference past orders; customer asks for **old invoices** — tie to Phase 2 delivery when quotes/invoices exist
- **Chatwoot custom attribute cleanup:** apply the 7.1D lifecycle policy consistently when workflow JSON cleanup starts.
- **LLM vs Code:** short paraphrases may use hybrid extractor; inventory, price, and reservation stay **deterministic**. Prefer extending **`sam_text_parse`** + caps when wording drifts rather than replacing Code with LLM-only routing

Improvements also in scope:

- improve Sam order context
- improve AUTO reply quality where still needed
- fix and enable `1.3 - Media Tool`
- improve Telegram cleanup for human escalation
- expand monitoring and operational runbooks

### 7.2 Database Scaling Review - Planning Complete

Planning status:

- Started on 2026-05-18 after Phase 7.1 was closed.
- This is planning only. Do not build a database migration, add a new provider, or change production data storage during this slice.
- The goal is to decide the future architecture and safe migration path before implementation.
- Detailed planning source: `docs/02-backend/DATABASE_SCALING_PLAN.md`.
- Owner review is accepted for the current planning level.
- Phase 7.2 is closed as a planning checkpoint. Database implementation remains gated for a future deliberate phase.

Current decision:

- Keep Google Sheets as the operational data store for now while order behavior is still being stabilized.
- Do not migrate database storage immediately after the Phase 7.1 workflow cleanup.
- Treat the recent Google Sheets `429` quota errors as a scaling warning, not an immediate blocker for current low-volume operations.
- Keep the Google Sheets cache/retry fix in place and monitor whether normal live traffic stays stable.
- Owner review captured: long-term direction is Postgres-backed operations with Google Sheets used only during migration, not as the permanent operator system.

Why this matters:

- Google Sheets is useful for visibility, manual checks, and simple operational editing.
- It is not designed as a high-concurrency transactional database.
- Automated regression runs already showed quota pressure because each test case performs multiple backend reads/writes plus n8n workflow calls.
- Normal customer conversations are slower, so this is less urgent today, but sales volume will increase once meat sales and broader operations go live.

Preferred future direction:

- Evaluate moving transactional data to Postgres, with Supabase Postgres as the likely best option to assess first.
- Keep Google Sheets as reporting/export/operator visibility only during migration.
- Use Postgres as the source of truth for transactional tables that need indexes, concurrency, and atomic writes.
- Keep n8n and Sam behind backend APIs. They should not write directly to Postgres any more than they should write directly to operational Google Sheets.

Working recommendation:

- Treat Google Sheets as the current operational source of truth until the backend has a clear data-access boundary.
- Build toward a repository/data-access layer inside the Flask backend first.
- Design the database schema before choosing final provider settings or moving data.
- Start with orders/intake/documents only. Do not include the full piggery data model in the first migration unless Sheets becomes unstable for those pages too.

Candidate tables for future migration:

- `ORDER_MASTER`
- `ORDER_LINES`
- `ORDER_INTAKE_STATE`
- `ORDER_INTAKE_ITEMS`
- `ORDER_DOCUMENTS`
- `ORDER_STATUS_LOG`
- `SALES_PRICING`
- later: pig stock / availability data if Sheets becomes too slow or fragile

Candidate indexes / lookup keys:

- `order_id`
- `order_status`
- `conversation_id`
- `customer_phone`
- `customer_name`
- `order_line_id`
- `pig_id`
- `document_id`
- `document_ref`
- `intake_id`
- `created_at` / `updated_at`

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

Key risks to plan for:

- Dual-write drift if Sheets and Postgres are both writable at the same time.
- Data migration mistakes around order statuses, cancelled lines, document references, and intake-to-order links.
- n8n workflows accidentally bypassing backend APIs if direct database access is introduced.
- Web app pages assuming sheet-specific column names or formula outputs.
- Operator visibility loss if Google Sheets disappears before the web app has replacement views.
- Formula behavior being lost or changed if sheet formulas are not mapped to backend calculations, SQL views, or stored snapshots before migration.
- Cost and backup planning being ignored until after production data has moved.

Suggested migration approach:

- First stabilize the current backend behavior and n8n flow.
- Add a backend data-access/repository layer so order code is not tightly coupled to Google Sheets calls.
- Define schemas and migrations for order/intake/document tables.
- Add import/export scripts and dry-run checks against a copied dataset.
- Run read-only shadow comparisons first: backend reads from Sheets and compares equivalent Postgres rows without serving Postgres to users.
- Move selected backend reads to Postgres only after comparison passes.
- Move writes only when transactions, backups, and rollback are ready.
- Keep Google Sheets read-only or synced as operational views during transition.
- Only retire Sheets as a source of truth after the web app, Sam, and operational reports are confirmed against Postgres.
- Replace Google Sheets formulas deliberately: business decisions in backend services, read-only summaries in SQL/API views, and historical document values as stored snapshots.
- Pricing should use effective-dated records: future prices can be entered ahead of time, and the backend selects the newest valid price for the order/quote date while copying the selected price onto each order line.
- Owner-confirmed test marker: `Customer_Name = Charl N` should be excluded from the production import.
- Real cancelled customer orders with documents or payments should become archived history after a suitable period, not active operational clutter.
- Sheet retirement should be systematic: replace and accept the matching web app/API view first, then make the Sheet read-only/synced, then retire it.

7.2A planning tasks - Accepted:

- Inventory every backend function that reads/writes the candidate order/intake/document sheets. - Captured in `DATABASE_SCALING_PLAN.md`.
- Identify sheet formulas/views that depend on those sheets. - Captured in `DATABASE_SCALING_PLAN.md`; owner formula question captured and replacement strategy drafted.
- Define the minimum Postgres schema for `ORDER_MASTER`, `ORDER_LINES`, `ORDER_INTAKE_STATE`, `ORDER_INTAKE_ITEMS`, `ORDER_DOCUMENTS`, `ORDER_STATUS_LOG`, and `SALES_PRICING`. - Drafted in `DATABASE_SCALING_PLAN.md`.
- Decide whether Google Sheets should become read-only reporting, synced operator view, or be retired per table. - Owner decision: use only during migration, then retire per table once replacement web views are accepted.
- Define import rules for historical data. - Owner direction captured: import useful business data, exclude test data, and exclude `Charl N` test orders.
- Draft a migration checklist with rollback rules before any implementation. - Drafted in `DATABASE_SCALING_PLAN.md`.
- Confirm pricing effective-date behavior. - Owner decision captured and drafted in `DATABASE_SCALING_PLAN.md`.
- Define Sheet retirement acceptance rules. - Drafted in `DATABASE_SCALING_PLAN.md`; replacement views must be accepted before Sheets are retired.

7.2B implementation gate:

- Do not start implementation until 7.2A is reviewed and accepted.
- Before implementation, run a Claude Code review because this will be cross-cutting across backend, web app, n8n assumptions, data contracts, and operations.
- Implementation should start with tests and adapters, not with a production database cutover.
- 7.2B is not started now. Treat it as future implementation work only when database migration becomes the selected priority.

### 7.3 Oom Sakkie Operational Order And Document Lookup - 7.3C Complete And Live-Verified

Goal:

- Let Oom Sakkie answer internal operator questions about orders without requiring the operator to open the web app or Google Sheets.

Planning source:

- `docs/04-n8n/workflows/OOM_SAKKIE_ORDER_LOOKUP_PLAN.md`

Live workflow baseline imported:

- `2 - The GateKeeper`
- `2.0 - OOM SAKKIE - Amadeus Assistant Agent`
- `2.1 - Amadeus Weather Sub-Agent`
- `2.1.1 - Amadeus Forecast Tool`
- `2.2 - Amadeus Sunsynk Sub-Agent`
- `2.3.1 - Build Daily Irrigation Plan`
- `2.3.2 - Run Irrigation Controller`
- `2.4 - Amadeus Orders Sub Agent`
- `2.4.1 - Test Caller`
- `2.4.2 - Orders Approval Callback Handler`
- `2.4.3 - Order Approval Request Webhook`
- `ALERT - Local Weather Station`
- `ALERT - Sunsynk`
- `ALERT - Weather Forecast`

Required outcome:

- Oom Sakkie can look up open orders by order ID, customer name, or phone number.
- Oom Sakkie can summarize order status, items, totals, payment method, collection location/date, notes, and outstanding actions.
- Oom Sakkie can retrieve quote/invoice document records and provide or send the correct document link when an operator asks for it.
- Oom Sakkie must use backend order/document endpoints, not direct sheet guessing.
- If multiple orders match a name or phone number, Oom Sakkie must ask one disambiguation question.
- Customer-facing delivery of quotes/invoices remains controlled by the document delivery path; internal lookup must not accidentally send a document to a customer unless that action is explicit and confirmed.

Planning note:

- This complements Phase 6 web app usability. The web app remains the full operations interface; Oom Sakkie becomes the quick internal assistant for checks and document retrieval when operators are away from the app.

Recommended direction:

- Start read-only.
- Build around the existing live `2.#` workflow suite. Do not create a replacement Oom Sakkie path.
- Preserve `2 - The GateKeeper` as the access-control entry point.
- Preserve existing `2.4` order approval behavior.
- Use existing backend endpoints first where practical:
  - `GET /api/orders/<order_id>`
  - `GET /api/orders/active-customer-context`
  - `GET /api/orders`
- Add a controlled `GET /api/orders/search` endpoint if name/phone matching should be backend-owned before workflow implementation.
- Keep document sending behind an explicit confirmation step and the existing backend document-send endpoints.

7.3A planning tasks:

- Review and accept the Oom Sakkie lookup plan.
- Review imported live `2.#` workflow READMEs.
- Read-only order lookup belongs in new `2.4.4 - Order Lookup Tool`. - Owner decision after safety review; preserve existing `2.4` approval behavior.
- Decide whether 7.3B should add `GET /api/orders/search` before workflow work. - Recommended: yes, keep matching backend-owned.
- Decide whether Oom Sakkie may show Google Drive URLs to operators or only document refs/statuses. - Recommended first slice: refs/statuses only.
- Decide whether invoice sending is in 7.3 or future-only. - Recommended: future-only; prove quote lookup/send guard first.
- Confirm the first operator channel for Oom Sakkie. - Recommended: existing Telegram Oom Sakkie path through `2 - The GateKeeper` and `2.0`.

7.3A recommended path:

- Build lookup into new `2.4.4 - Order Lookup Tool`; do not edit/import the live approval `2.4` workflow for lookup.
- Add backend `GET /api/orders/search` first.
- Add backend `GET /api/orders/<order_id>/operator-summary` as the compact internal-safe detail contract for Oom Sakkie.
- Add read-only `2.4.4` actions first: `find_order`, `get_order_summary`, `get_order_documents`.
- Keep document sending out of the first live lookup slice.

7.3B backend contract:

- Drafted in `docs/02-backend/API_STRUCTURE.md`.
- `GET /api/orders/search` returns compact match rows for `order_id`, `customer_phone`, `customer_name`, or `conversation_id`.
- `GET /api/orders/<order_id>/operator-summary` returns compact `order_summary`, grouped `line_summary`, `document_summary`, `outstanding_actions`, and `safe_document_actions`.
- First slice must not return Google Drive URLs and must not send documents.

7.3B local implementation:

- Backend endpoints added locally:
  - `GET /api/orders/search`
  - `GET /api/orders/<order_id>/operator-summary`
- Search and operator-summary helpers added to `modules/orders/order_read.py`.
- Routes added in `modules/orders/order_routes.py`.
- Existing `/api/orders/<order_id>` route left unchanged.
- Focused route/read tests added.
- Full local suite passed with 82 tests.
- Backend deployed and read-only production smoke passed:
  - `/api/orders/search` with no identifier returned expected `400`.
  - `/api/orders/search?customer_name=Charl%20N&status_scope=all&limit=3` returned compact multiple matches.
  - `/api/orders/ORD-2026-3E46B8/operator-summary` returned compact order, document, outstanding action, and safe document action data.
  - No Google Drive URL was returned by the operator summary.
- Read-only `2.4.4 - Order Lookup Tool` workflow created in n8n and read back into the repo:
  - n8n workflow ID: `1VNdetSbgP0ffNyH`
  - current n8n status: active and wired into `2.0`
  - local export: `docs/04-n8n/workflows/2.4.4 - Order Lookup Tool/workflow.json`
  - local README: `docs/04-n8n/workflows/2.4.4 - Order Lookup Tool/README.md`
  - local validation passed: JSON parsed, node count checked, and all Code node JavaScript compiled
  - `2.4 - Amadeus Orders Sub Agent` was left untouched
- Next step: wire `2.0 - OOM SAKKIE - Amadeus Assistant Agent` to call `2.4.4` through a new `Orders_Info_Tool`, then test exact order lookup before broader name/phone lookup.

7.3C local workflow update:

- `2.0 - OOM SAKKIE - Amadeus Assistant Agent` now has an `Orders_Info_Tool` node pointing to `2.4.4`.
- `2.0` prompt now routes order status, order summary, customer/order search, and quote/invoice document lookup questions to the order lookup tool.
- `2.4.4` now accepts raw `input` as well as structured fields so Oom Sakkie can pass the full operator message safely.
- `2.4.4` uploaded and read back from n8n successfully on 2026-05-18.
- `2.0` API upload is blocked by n8n server-side `500`; the same failure occurs when PUTting the unchanged live export, so the 2026-05-18 update was completed through the n8n UI.
- `2.0` readback confirmed active, 17 nodes, and `Orders_Info_Tool` pointing to `1VNdetSbgP0ffNyH`.
- `2.4.4` readback confirmed active, 10 nodes, and declared trigger inputs.
- Telegram routing fix applied:
  - disabled `2.4`'s normal-message approval trigger because it intercepted general Oom Sakkie messages and dropped non-approval text
  - refreshed `2 - The GateKeeper` activation so it owns normal Telegram messages
  - superseded by the 2026-05-19 Path A recovery: GateKeeper now owns both normal messages and approval/document callbacks; `2.4.2` is retired from the live path
- Exact Oom Sakkie smoke passed:
  - `Hi` routed through the GateKeeper and received a normal assistant reply.
  - `Show me order ORD-2026-3E46B8` returned the expected cancelled order summary and quote reference.
- Document lookup smoke passed:
  - `What documents are on order ORD-2026-3E46B8?` returned quote `Q-2026-3E46B8`, generated status, total, and valid-until date.
- Name search/disambiguation smoke passed:
  - `Find order for Charl N` returned multiple active draft matches and asked the operator to choose one order ID.
- Phone search no-match smoke passed:
  - `Find orders for 0645087806` returned no matching active orders.
- Follow-up parked:
  - Oom Sakkie phone/name search currently defaults to active orders only.
  - Later enhancement: support explicit historical/all-status wording such as `search all orders for 064...` without changing the default active lookup behavior.
- 7.3C status: complete and live-verified.
- Pending: plan 7.3D document-send guard before adding any send behavior.

7.3C workflow wiring plan:

- Add `Orders_Info_Tool` to existing `2.0 - OOM SAKKIE - Amadeus Assistant Agent`.
- Point `Orders_Info_Tool` to new `2.4.4 - Order Lookup Tool`.
- Add separate read-only `2.4.4` switch branches:
  - `find_order`
  - `get_order_summary`
  - `get_order_documents`
- Keep existing `2.4` approval branches unchanged:
  - `request_order_approval`
  - `process_order_approval_reply`
  - `invalid_callback`
- Do not route lookup through `Telegram Trigger - Approval Chat`.
- Do not add document-send actions in this slice.

7.3B implementation gate:

- Do not update workflow JSON until 7.3A is accepted.
- Read-only lookup must pass before adding any document-send action.
- Document send must use backend endpoints, never direct workflow-to-Chatwoot delivery.

7.3 side-track captured for later:

- `2.3.2 - Run Irrigation Controller` currently contains direct IFTTT webhook key usage in its HTTP node URL expressions.
- Short-term hardening: move the IFTTT Maker key into n8n credential storage or protected n8n environment variables such as `IFTTT_BASE_URL` and `IFTTT_MAKER_KEY`.
- Medium-term hardening: route irrigation start/stop through backend-controlled endpoints so the backend owns secrets, zone validation, cooldowns, audit logs, safety locks, and error handling.
- Do not expand irrigation commands through Oom Sakkie until this hardware-control secret/safety plan is addressed.

## Phase 8: Breeding Board Improvements — 8D Live-Verified

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

### 8D Mark Not Pregnant / Repeat Service — Live-Verified

When a sow has been in a farrowing pen too long with no litter, the next action is to mark her as not pregnant and return to repeat service.

- `POST /api/pig-weights/master/matings/<mating_id>/mark-not-pregnant`
- Updates `MATING_LOG`: `Pregnancy_Check_Result = Not_Pregnant`, `Mating_Status = Repeat_Service`, `Outcome = Repeat_Required`, `Updated_At = today`.
- Optionally moves sow back to a non-farrowing service/holding/sow/gilt pen and writes `LOCATION_HISTORY` with reason `Moved for repeat service`.
- Available only for `Confirmed_Pregnant` matings with no litter and no actual farrowing date.
- Blocks non-confirmed matings, linked litters, actual farrowing dates, missing target pens, and farrowing target pens.
- Supports `dry_run: true` so live real matings can be validated without writing to `MATING_LOG` or `LOCATION_HISTORY`.
- `/matings` Breeding Board shows a `Mark Not Pregnant / Repeat Service` button on eligible confirmed-pregnant cards. Clicking opens an inline form with a non-farrowing pen dropdown. On confirm, POSTs to the endpoint and reloads the board.
- Focused service/route tests, full local unittest suite, and JavaScript syntax check passed.
- Dry-run live verification passed on 2026-05-19 against real eligible mating `MAT-2026-E05BC0` / Lolly. The endpoint returned planned updates for `Pregnancy_Check_Result = Not_Pregnant`, `Mating_Status = Repeat_Service`, and `Outcome = Repeat_Required`, with `dry_run = true` and `movement_logged = false`.
- After the dry-run, a live reread confirmed the real record was unchanged: still `Confirmed_Pregnant`, `Pregnant`, and `Updated_At = 2026-05-02`.
- Live write verification passed on 2026-05-20: Baby's mating `MAT-2026-1565CF` was marked `Pregnancy_Check_Result = Not_Pregnant`, `Mating_Status = Repeat_Service`, `Outcome = Repeat_Required`, `is_open = No`, with no linked litter and no unintended pen move.

### 8E Breeding Board Sorting - Planned

Source note moved from `planning/ToDoList.md`.

Required outcome:

- Make `/matings` tile order more useful and predictable within each status section.
- `Needs Action Now` should sort from most urgent to least urgent.
- `Closed / Farrowed` should sort latest to oldest, preferably by real `actual_farrowing_date` where available, then fallback dates.
- Other sections should use the date that best matches the action the user needs to take, not just raw creation order.
- Keep this as a focused frontend/backend sorting slice before adding larger breeding analytics.

Questions to answer when planning:

- Which exact section names should be treated as operational priority sections?
- For `Closed / Farrowed`, should `Farrowed`, `Repeat_Service`, `Cancelled`, and other closed outcomes be mixed together or grouped separately?
- Should overdue pregnancy checks sort ahead of overdue farrowing checks when both appear in the same section?

### 8F Fertility, Bloodline, And Breeding Suggestions - Discovery Captured

Source note moved from `planning/ToDoList.md`.

Goal:

- Build useful breeding analytics that compare fertility and litter performance across breeding males and females, then eventually support suggested matings.

Potential future outcomes:

- Track fertility rounds per sow and boar: matings, confirmed pregnancies, repeat services, farrowed litters, litter size, survival, and weaning outcomes.
- Compare breeding animals in a way that is easy to understand on a web-app page.
- Help decide whether to keep or remove breeding animals based on repeat-service rate, litter size, piglet survival, growth, and owner-defined rules.
- Avoid close-family matings by using parent, litter, and bloodline data.
- Suggest best mating options using fertility, relatedness, litter history, and business goals.
- Keep suggestions operator-approved; the system should explain why a mating is suggested or blocked.

Planning notes:

- This needs careful data modelling before implementation because it will become part of the breeding strategy and bloodline optimization.
- It likely needs new derived metrics from `MATING_LOG`, `MATING_OVERVIEW`, `LITTERS`, `LITTER_OVERVIEW`, `PIG_MASTER`, and parent relationships.
- It should not be squeezed into the existing `/matings` board as a quick visual tweak.

Questions to answer when planning:

- Which breeding KPIs matter most first: conception rate, repeat-service count, litter size, born alive, weaned count, survival rate, average growth, or profitability?
- What data do we already have reliably, and what needs to start being captured before the analytics can be trusted?
- How strict should family/bloodline avoidance be, and how many generations should be checked?
- Should the first version be a read-only analytics page before any automated mating suggestions?

## Phase 9: Pig, Weight, And Reporting Improvements - 9.1A Live-Verified; 9.1B Browser-Verified; 9.2A/9.2B Owner-Verified; 9.3/9.3B Owner-Verified; 9.4 Current Slice Complete; 9.5 Visible; 9.5B Planned; 9.6A Browser-Verified; Parked For Now

Only after live order stability unless the operational need becomes urgent.

### 9.1 New Litter Defaults And Weaning Reminder — Complete / Live-Verified

Required outcome:

- new `PIG_MASTER` rows generated from a litter should default `Purpose = Unknown` — 9.1A implemented, tested, deployed, and live-verified
- animals with `Purpose = Unknown` must not appear as for-sale stock
- once animals are weaned, surface a reminder to assign purpose: `Grow_Out`, `Sale`, or `Breeding`

Future direction:

- At weaning, the system should eventually suggest purpose based on birth weight, weaning weight, growth rate, litter quality, and owner-defined rules.
- Suggested classes should include breeding candidate, grow-out, sale, and later slaughter-ready/meat-stream eligibility.
- Suggestions should explain the reason and remain operator-approved, not silently force purpose changes.
- This ties into Phase 11 because multiple revenue streams need flexible pig allocation from weaning through sale/slaughter weight.

9.1A verification state:

- Local focused litter tests and the full local test suite passed.
- Production route smoke passed after deploy: `/api/pig-weights/status` returned running, and invalid litter creation returned the expected `400` validation errors without writing data.
- Live verification passed on real farm data:
  - `LIT-2026-9E4A` for Lolly generated 11 active piglet rows in `PEN-002`, all with `Animal_Type = Piglet`, `Status = Active`, `On_Farm = Yes`, `Source = Born_on_Farm`, and `Purpose = Unknown`.
  - `LIT-2026-EB92` for Shupe generated 8 active piglet rows in `PEN-003`, all with `Animal_Type = Piglet`, `Status = Active`, `On_Farm = Yes`, `Source = Born_on_Farm`, and `Purpose = Unknown`.
  - Linked matings `MAT-2026-E05BC0` and `MAT-2026-78148F` were marked `Farrowed`, `is_open = No`, and linked to their created litters.

9.1B litter attention dashboard:

- Added `LITTER_OVERVIEW` as a configured read source.
- Added backend `get_litter_attention_summary()` for read-only dashboard reminders.
- Dashboard response now includes `litter_attention`.
- Dashboard renders a compact `Litter Attention` section with links to `/litter/<litter_id>`.
- Reminder rules in this slice: include rows where `Needs_Attention = Yes`, and include weaned litters with active piglets as `Weaned - review purpose`.
- No Google Sheet writes are added.
- Focused backend tests and `node --check static/js/dashboard.js` passed locally.
- Deployed and browser-verified on 2026-05-19.
- Tile link issue fixed: `litterDetail.js` now calls the existing `GET /api/pig-weights/litter/<litter_id>` route instead of the obsolete `/detail` path.
- Owner confirmed dashboard tile opens the litter detail page after deploy.

9.1C litter attention and weaning workflow - planned:

- Source notes moved from `planning/ToDoList.md`.
- Review how `LITTER_OVERVIEW.Needs_Attention` is calculated and make the reason visible to the user. If a litter tile says it needs attention, the app should explain what action is needed.
- Clarify when litter-level tracking should stop or change after weaning. Litter data should remain useful historically, but post-weaning growth and outcomes should move to individual pig records where appropriate.
- Add a litter tile/detail action to mark a litter as weaned.
- Marking a litter as weaned should ask for the weaning date.
- On confirmation, apply the weaning date to the related live/active piglets and update the litter state in a controlled backend-owned write.
- Dead, sold, or off-farm piglets should not distort active litter age/growth/average metrics after their exit state is known.
- Weaning should feed the future purpose-classification workflow: breeding candidate, grow-out, sale, and later slaughter/meat stream eligibility.

Questions to answer when planning:

- What exact sheet/formula currently drives `Needs_Attention`, and which reasons should be shown in the UI?
- Should weaned litters disappear from the dashboard attention list once every active piglet has a purpose?
- Which fields should be updated when marking a litter as weaned: `LITTERS`, generated `PIG_MASTER` rows, both, or a future Supabase table?
- Should the first weaning action be Google Sheets-backed, or should it wait for the pig/litter Supabase migration?

### 9.2 Pig Dropdown Usability — Complete / Owner-Verified

Required outcome:

- pig-related dropdowns should show tag number and pen name, not only pen ID
- tag numbers should display as three digits where appropriate: `001`, `010`, `090`, `100`

9.2A dropdown label slice:

- Backend `/api/pig-weights/parent-options` and `/api/pig-weights/pigs` now include `current_pen_name`.
- `2.0` breeding options already included current pen names; frontend now uses them in labels.
- Add Litter mother/father dropdowns, Add Mating sow/boar dropdowns, and Weight Entry pig dropdown now prefer labels like `S5 - Kraam Saal 01 (PIG-...)`.
- Numeric-only tag numbers display with three slots, for example `001`, `010`, `099`, `120`.
- Dropdown sorting uses the tag/name first, not `PIG_ID`.
- IDs remain available in the label as secondary context.
- Focused backend tests and JavaScript syntax checks passed locally.
- Deployed and owner-verified in the browser: Add Litter, Add Mating, and Weight Entry dropdown labels display correctly.

9.2B pig list tag formatting - owner-verified:

- Source note moved from `planning/ToDoList.md`.
- `/pigs` should display numeric pig tags in the same three-digit format used elsewhere: `001`, `010`, `099`, `120`.
- Pig list sorting should be predictable and numeric-aware, not text order and not raw `PIG_ID` order.
- Default: numeric-only tags sort low-to-high by padded tag number; named or non-numeric tags sort predictably by their display text.
- Keep this as a small visual/read-only consistency slice.
- Implementation state:
  - `/pigs` now formats numeric-only tag numbers with three slots.
  - The pig list uses numeric-aware display ordering before rendering.
  - Search matches raw tags, padded tags, and `PIG_ID`.
  - Pig profile links still use the unchanged `pig_id`.
  - Verification passed: `node --check static/js/pigList.js`, focused frontend contract tests, and full local unittest suite at 166 tests.
  - Deployed and owner-verified on 2026-05-21; owner confirmed `/pigs` tag display is much better.

Browser check result:

- Open `/pigs` after deploy and confirm numeric tags show as `001`, `010`, `099`, `120`.
- Confirm the default order is useful for scanning and detail links still open the correct pig profile.
- Confirm search works with both raw and padded tag input.
- Owner confirmed the display is improved and usable.

### 9.3 Weight Form Context — Complete / Owner-Verified

Required outcome:

- beside `Move to Pen (Optional)`, show the current pen as read-only helper context

9.3 implementation state:

- The weight form now shows a `Current pen: ...` helper line below `Moved To Pen (Optional)`.
- The helper updates when the selected pig changes and uses the selected pig's `current_pen_name` plus `current_pen_id` where available.
- If no pig is selected, the helper says to select a pig first; if the selected pig has no current pen, it says the current pen is not recorded.
- Form submission remains unchanged and still sends `moved_to_pen_id` only when a target pen is selected.
- `node --check static/js/pigWeights.form.js` passed.
- Focused local tests passed: `tests.test_frontend_route_contracts`, `tests.test_pig_weights_dropdown_options`, and `tests.test_pig_weights_utils`.
- Full local unittest suite passed: 117 tests.
- Deployed and owner-verified on `/pig-weights` on 2026-05-20.

9.3B weight form UX refinements - owner-verified:

- Source notes moved from `planning/ToDoList.md`.
- Remove or neutralize the browser up/down spinner behavior on the weight input so accidental mouse-wheel scrolling does not change the entered weight.
- Improve `/pig-weights` layout so the primary save action is visible in the first section without unnecessary scrolling.
- Keep the form efficient for live farm use, especially on mobile or while entering many weights.
- This should remain a frontend usability slice unless backend validation needs tightening.
- Implementation state:
  - `New Weight (kg)` now uses spinner-hiding styling and blocks mouse-wheel value changes.
  - A primary `Save Weight` button appears directly after the required weight/date inputs.
  - A second `Save Weight` button remains after optional notes for users who complete the whole form.
  - Both buttons share the same submit flow and disabled/saving state.
  - Save payload is unchanged.
  - Verification passed: `node --check static/js/pigWeights.form.js`, focused frontend contract tests, and full local unittest suite at 165 tests.
  - Deployed and owner-verified on 2026-05-21; owner confirmed the weight form looks better.

Browser check result:

- Deploy/browser check: confirm mouse-wheel scrolling over the weight input does not change the value, and confirm the top save button is visible and saves correctly.
- Owner confirmed the updated form is better and moved on to the next slice.

### 9.4 Weight Report — Current Slice Complete; 9.4C3/C4/D Planned

Required outcome:

- after weights are entered, allow the user to generate a weekly weight report
- include summaries, grouped totals, pen counts, and useful decision-making commentary
- this covers post-entry reporting only; pre-weighing handwritten capture is the separate Phase 9.6 printable sheet

Owner decisions:

- Default view: `Today`.
- First report scope: active/on-farm pigs only.
- Condition notes: include them in the detail table for the first slice, then review whether they are useful or too noisy.
- Print support: reports should support normal browser printing. This does not replace Phase 9.6 printable field capture sheets.

9.4A backend report contract:

- Added read-only `GET /api/pig-weights/weight-report?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&pen_id=PEN-...`.
- Reads from `WEIGHT_LOG`, `PIG_OVERVIEW`, and `PEN_REGISTER`.
- Filters out inactive/off-farm pigs.
- Returns summary totals, pen summary, and detailed weight rows.
- Calculates previous weight, change, days since previous, and growth per day where previous data exists.
- Does not write to Google Sheets.

9.4B web app page:

- Added `/weight-report`.
- Defaults date range to today.
- Includes date range controls, optional pen filter, `Today`, `Run Report`, and `Print` actions.
- Shows summary cards, pen summary table, and detailed active-pig weight rows.
- Added dashboard links to `Weight Report`.
- Uses normal browser print flow with print CSS.

Verification state:

- `node --check static/js/weightReport.js` passed.
- Focused service and frontend route tests passed.
- Local route smoke passed: `/weight-report` returned `200`.
- Local API smoke passed: valid report returned `200`, invalid date returned `400`.
- Deployed and owner-verified on 2026-05-20; owner confirmed the report is usable after 9.4C1 refinements.

9.4C report usability refinements - owner review captured:

- Duplicate same-day pig weights:
  - The report should detect when one pig has more than one weight entry on the same date.
  - Duplicate/same-day entries should be highlighted with a clear symbol or visual marker.
  - Open question: should duplicate entries be treated as a warning only, or should the latest entry become the "official" one for reporting?
- Delete/edit weight entries:
  - This needs planning before implementation because `WEIGHT_LOG` is a historical log and currently append-only.
  - Preferred direction: add explicit edit/delete actions with audit protection, not silent row changes.
  - Open question: should delete mean hard delete from `WEIGHT_LOG`, or safer soft-void/cancel so the original entry remains traceable?
- Table readability:
  - Add light row separators or zebra-style row treatment.
  - Increase column spacing/padding in the bottom tables.
  - Remove `Condition Notes` from the first detail table layout unless a better expandable/detail pattern is added.
  - Show pen name only in the report tables; hide `Pen_ID` to save space.
- Sortable report columns:
  - Default report order should remain grouped by pen, because it matches the farm workflow.
  - Future enhancement: make the `Pig`/tag and `Pen` table headers clickable so the user can switch ascending/descending order without changing the default.
  - Sorting should keep numeric tags human-friendly, for example `001`, `002`, `010`, not text order.
- Interactive rows:
  - Desired future behavior: clicking a weight row opens that weight entry for review/edit.
  - Align this with the weight form so the report table and weight form use the same interaction pattern.
  - This should be a separate edit-history slice because it changes write behavior.
- Loss flags:
  - Add a dedicated `Loss Flagged` table or section so pigs with negative weight change are easy to find.
- Summary usefulness:
  - Average weight can mislead when different ages, pens, stages, and groups are mixed.
  - Improve summary cards toward decision-useful signals, for example: pigs weighed, pigs not weighed in selected group, gainers, loss flags, no-previous-weight count, average gain by pen/stage, and largest losses.
  - Open question: which summary signals should replace or reduce plain average weight in the first refinement?
- Date column:
  - If the report date range is a single date, the detail table may hide the repeated date column to reduce wasted space.
  - If the report covers multiple dates, keep the date column.
- Active/off-farm display:
  - Owner preference changed from "active only" to possibly showing all weighed pigs, with inactive/off-farm rows greyed and struck through.
  - Open question: should the API default include all weighed pigs with status metadata, or keep active-only as default and add an `include_inactive=true` toggle?

Recommended 9.4C split:

1. **9.4C1 Visual/read-only refinements** - duplicate marker, loss-flag section, better table spacing, remove notes, pen name only, hide date on single-day reports, and improve summary cards. No writes. Implemented locally 2026-05-20.
2. **9.4C2 Weight duplicate prevention now / edit-delete later** - near-term Google Sheets solution is duplicate prevention with explicit `Add anyway` confirmation; full edit/delete/void audit is deferred to Supabase. Implemented locally 2026-05-20.
3. **9.4C3 Interactive row implementation** - only after 9.4C2 is agreed. Planned, not started.
4. **9.4C4 Sortable report headers** - planned enhancement: keep default pen grouping, then allow clickable `Pig`/tag and `Pen` headers to toggle ascending/descending order.

9.4C1 implementation state:

- Backend now marks duplicate same-day pig weights with `duplicate_same_day` and `duplicate_entry_count`.
- Backend now returns a dedicated `loss_flags` list.
- Summary includes gain count, loss flag count, no-previous-weight count, and duplicate same-day count.
- Weight report page now has a dedicated `Loss Flags` table.
- Detail table removes `Condition Notes` from the visible columns.
- Report tables use light row separators/zebra treatment and wider column padding.
- Pen display shows pen name only where available, not `Pen_ID`.
- Numeric pig tags on `/weight-report` must display as three digits, matching the pig weight dropdowns, and report rows should sort by numeric tag order within each pen.
- Single-day reports hide the repeated date column; date remains visible for multi-day reports.
- Edit/delete and clickable row behavior remain parked under 9.4C2/9.4C3.
- `node --check static/js/weightReport.js` passed.
- Focused report service tests passed.
- Full local unittest suite passed: 121 tests.
- Deployed and owner-verified on 2026-05-20.

9.4D future feed guidance / pen performance planning:

- Source note from owner after 9.4C1 live review.
- Future idea: use pen-level weight performance to guide feeding decisions.
- If a pen is below a target growth rate, for example below `0.300 kg/day` or another owner-defined target, the system could flag that pen for feed review.
- Longer-term goal: calculate suggested feed amounts from what is in each pen, current growth performance, target growth, pig count, stage/weight, and available feed strategy.
- The system should support worker-ready feeding lists once rules are mature.
- The feeding recommendation should also account for waste: if pigs start wasting feed, the system should recommend holding back rather than blindly increasing.
- This connects to future land-grown feed planning because more available farm-grown feed may allow higher-volume feeding strategies.
- Keep this as planning for now; do not auto-change feed rules from weight data until targets, feed types, pen groups, and waste checks are defined.

Questions to answer when planning:

- What target growth rates should apply by stage/weight band/purpose?
- Should targets be per pen, per pig stage, per purpose, or per feed type?
- What feed types and amounts are currently used, and what feed types may come from the land later?
- How should feed waste be recorded: worker note, daily feed log, or pen-level observation?
- Should first implementation be read-only guidance before any worker feeding list changes?

9.4C2 duplicate prevention decision:

- Do not build full edit/delete on Google Sheets.
- Do not hard-delete weight entries.
- Defer true edit/void/replace with audit trail until Supabase, where history and permissions can be handled properly.
- Near-term Google Sheets behavior:
  - When saving a weight, backend checks whether the same `Pig_ID` already has a `WEIGHT_LOG` entry for the selected `Weight_Date`.
  - If no entry exists, save normally.
  - If an entry exists, block the first save and return the existing entry metadata.
  - The web app must ask for explicit confirmation before adding a second same-day entry.
  - If the user confirms, save with an explicit duplicate override.
  - This prevents accidental duplicates while still allowing intentional repeat weights.
- Implementation state:
  - Backend returns HTTP `409` with `duplicate_weight = true` when an unconfirmed duplicate is detected.
  - Frontend shows an explicit confirmation before resubmitting with `allow_duplicate = true`.
  - No edit/delete/void behavior was added.
  - `node --check static/js/pigWeights.form.js` passed.
  - Focused duplicate and frontend contract tests passed.
  - Full local unittest suite passed: 124 tests.
  - Deployed and owner-verified on 2026-05-20.

9.4 report tag formatting follow-up:

- Source note from owner after 9.4C2 live verification: `/weight-report` table tags were still showing raw unpadded numeric values.
- Implemented local fix on 2026-05-20 so report tables display numeric pig tags as three digits and backend report rows sort with a numeric-aware tag key.
- Owner clarified the default pen-grouped order is acceptable and should remain the default; clickable sortable `Pig`/tag and `Pen` headers are logged as a later usability option.
- Verification passed: `node --check static/js/weightReport.js`, focused report/frontend tests, and full local unittest suite at 125 tests.
- Deployed and owner-verified on 2026-05-20; owner confirmed tags display correctly on `/weight-report`.

### 9.5 Dashboard Sold This Month Audit — Implemented Locally; 9.5B Planned

Required outcome:

- verify how `SOLD THIS MONTH` is calculated
- reconcile the April mismatch where the dashboard showed 20 but the expected sold count was 40
- reshape the dashboard metric so it can support three sales streams:
  - `Livestock`: the current order-driven live pig sales flow.
  - `Slaughter`: pigs taken to slaughter/abattoir as an intermediate sale channel.
  - `Meat`: future direct pork/carcass/meat sales from the business plan.

Decision:

- Use `PIG_MASTER` exits as the near-term source of truth because all streams eventually mean a pig left the farm.
- Keep current completed livestock orders as `Exit_Reason = Sold`.
- Count abattoir/intermediate slaughter exits separately from livestock where `Exit_Reason` or `Status` indicates slaughter/abattoir.
- Add a future-ready meat stream count, but do not build the full meat order model here.
- Plan the deeper meat-sales workflow under Phase 11, not Phase 9.5.

Planned approach:

- Inspect the current dashboard count source in backend code and the sheet columns/views it reads.
- Define the intended business rule for `SOLD THIS MONTH`, including whether it should count pigs, order lines, completed sales, exit records, or another source of truth.
- Compare the dashboard result against the expected April count and the current month using read-only checks first.
- Fix only after the source-of-truth rule is clear.
- Add a focused test so future dashboard work does not reintroduce the mismatch.

Implementation state:

- Backend now returns `sold_this_month` as total monthly sales exits.
- Backend also returns `livestock_sold_this_month`, `slaughter_sold_this_month`, and `meat_sold_this_month`.
- Dashboard now displays `Sales This Month` plus the three stream counts.
- Focused tests added for monthly sales stream classification and dashboard labels.
- Verification passed: `node --check static/js/dashboard.js`, focused dashboard/frontend tests, and full local unittest suite at 127 tests.
- Deployed/browser-visible on 2026-05-20; owner confirmed the three stream cards are in place.

9.5B follow-up planning - sales stream counts and Rand values:

- Owner note: the three stream cards are useful as a start, but the sales/income streams need clearer planning later.
- Current month can show `0` if no livestock/meat exits were logged; the known slaughter item was not logged yet, so it cannot be counted until the exit/sale event exists in the data.
- Future dashboard should separate:
  - `Sales count`: number of sale transactions per stream.
  - `Item/pig count`: number of pigs/items sold per stream.
  - `Sales value`: Rand total per stream.
- Suggested display shape:
  - top sales line/card: total sales count and total Rand value, similar visual weight to the Herd total
  - underneath: `Livestock`, `Slaughter`, and `Meat`, each with count and Rand value
- Data-source questions before implementation:
  - For livestock, should Rand value come from completed `ORDER_MASTER`/latest invoice, collected `ORDER_LINES`, or pig exit records linked by `Exit_Order_ID`?
  - For slaughter/abattoir sales, where should the sale transaction and Rand value be logged if there is no customer order?
  - For meat sales, should value come only from the future meat order/deposit/invoice flow under Phase 11?
- Do not fake currency totals from pig count only. Implement Rand values only once the sale value source is explicit.

Recommended 9.5B split:

1. **9.5B1 Display wording cleanup** - keep the current dashboard count behavior, but label it clearly as pig/item exits for now so it is not confused with Rand income. Deployed and owner-verified 2026-05-21.
2. **9.5B2 Slaughter sale logging decision** - define where a slaughter/abattoir sale is recorded when there is no normal customer order. This likely needs either:
   - a lightweight sale transaction record linked to `PIG_MASTER.Exit_Reason = Sold to Abattoir`; or
   - a future Supabase-backed `sales_transactions` table covering livestock, slaughter, and meat streams.
3. **9.5B3 Livestock value source** - use completed `ORDER_MASTER.Final_Total` as the livestock Rand source only when the completed order is trusted and not a test order. Avoid summing pig exit rows because one order can contain many pigs.
4. **9.5B4 Dashboard value cards** - once value sources exist, show:
   - total sales transactions this month
   - total Rand value this month
   - per-stream transaction count, pig/item count, and Rand value
5. **9.5B5 Supabase alignment** - because orders/sales are already being shadow-imported to Supabase, avoid building a complex Google Sheets-only transaction model unless needed immediately.

Recommended near-term decision:

- Do not implement Rand values yet.
- First, add or define the source-of-truth logging shape for slaughter/abattoir sales.
- Treat livestock sales as order transactions, not pig-count transactions.
- Treat slaughter and meat as future transaction streams that need their own sale record before the dashboard can show honest Rand totals.

Questions to answer before implementation:

- For the recent slaughter/abattoir sale that was not logged, what facts do we need to record: date, pig IDs/count, abattoir/customer, weight, price per kg, total amount, transport/fee deductions, and payment status?
- Should slaughter sales be entered through a simple web form, or first captured manually in a sheet/table until the workflow is clearer?
- Should the future common table be named generically, for example `sales_transactions`, so it can cover livestock, slaughter, and meat?
- Should livestock completed orders eventually create a linked sale transaction automatically when an order is completed?
- Should the dashboard show `Sales Exits This Month` now, and reserve `Sales Value This Month` until the transaction model exists?

9.5B1 implementation state:

- Dashboard sales cards now use exit wording:
  - `Sales Exits This Month`
  - `Livestock Exits`
  - `Slaughter Exits`
  - `Meat Exits`
- Backend values are unchanged and still come from current monthly `PIG_MASTER` exit counts.
- No Rand values or transaction calculations were added.
- Verification passed: `node --check static/js/dashboard.js`, focused dashboard/frontend tests, and full local unittest suite at 166 tests.
- Deployed and owner-verified on 2026-05-21; owner confirmed the wording change is done.

9.5B2 slaughter/abattoir sale logging decision - planning:

- Problem:
  - A slaughter/abattoir sale can happen without a normal customer order.
  - `PIG_MASTER` can tell us a pig left the farm, but it is not enough to calculate honest Rand income.
  - Dashboard Rand totals need a transaction/value source, not a pig-count guess.
- Recommended data shape for the future sale record:
  - `Sale_ID`
  - `Sale_Date`
  - `Sale_Stream` (`Livestock`, `Slaughter`, `Meat`)
  - `Buyer_Name` or `Destination`
  - `Linked_Order_ID` where applicable
  - `Pig_Count`
  - linked `Pig_ID` values or a child table for sale animals
  - `Live_Weight_Kg` where known
  - `Carcass_Weight_Kg` where known
  - `Price_Per_Kg` or `Unit_Price`
  - `Gross_Total`
  - `Deductions` such as transport, slaughter, processing, or commission
  - `Net_Total`
  - `Payment_Status`
  - `Notes`
- Recommended implementation direction:
  - Do not create a Google Sheets-only patch unless a slaughter sale must be logged before the Supabase sales model is ready.
  - Prefer a Supabase-backed `sales_transactions` table later, with child rows for linked pigs/items.
  - Completed livestock orders can later auto-create or link to a `sales_transactions` row.
  - Slaughter/abattoir sales can later be entered through a small internal form and linked to the pigs that exited.
  - Future meat/carcass sales should use the same transaction family rather than a separate one-off model.
- Minimum manual logging rule until built:
  - If a slaughter/abattoir sale happens now, record at least the sale date, pig count, pig IDs/tags, buyer/destination, total amount, and payment status in a temporary note/source so it can be backfilled later.
- Decision needed before build:
  - Should `sales_transactions` be introduced in Supabase before dashboard Rand values, or should we create a temporary Google Sheets sale log first?
  - Should slaughter sale entry be a simple internal web form, or should it wait for the broader Phase 11 pork/meat business module?

### 9.6 Printable Farm Operation Sheets — 9.6A Browser-Verified

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

Printing and printer-connection discovery:

- Source note moved from `planning/ToDoList.md`.
- The first implementation should use the browser's normal print flow (`window.print()` / print stylesheet), which supports installed Wi-Fi, network, USB, and save-to-PDF printers through the device/browser.
- Direct silent printing from the web app to a printer is usually restricted by browsers for security and should not be assumed for the first slice.
- If true one-click/direct printer sending is needed later, plan a separate local print-agent or device-specific integration after the printable pages are useful.

Questions to answer when planning:

- Which devices will print most often: farm laptop, office PC, or phone?
- Is the printer already installed on those devices over Wi-Fi/network?
- Is browser print acceptable for the first version, or is unattended/direct printing a hard requirement?

Follow-up idea:

- after the printable sheet is useful, consider a bulk weight entry page that follows the same row order so handwritten weights can be entered quickly without searching for each pig individually

Recommended 9.6 split:

1. **9.6A Printable weight capture sheet** - build `/print-sheets` with the first printable weekly weight sheet only.
2. **9.6B Sheet filters and polish** - add useful filters after 9.6A works: all active pigs, by pen/camp, by purpose, for-sale animals, grow-out/sale animals.
3. **9.6C Bulk weight entry idea** - future planning only; use the same row order as the printed sheet to speed up data entry later.

9.6A first-slice assumptions:

- Use normal browser printing only (`window.print()` and print CSS).
- Do not write to Google Sheets when generating the printable sheet.
- Use current active/on-farm pig truth from existing pig endpoints or a new read-only backend endpoint if the existing data shape is not enough.
- Default row order: current pen/camp, then numeric tag number.
- Hide internal `Pig_ID` from the printed worker-facing sheet.
- Include blank columns for `Nuwe Gewig`, `Nuwe Kamp`, and `Notas`.
- Include previous weight/date and current camp so the worker can write against the latest known context.

Open planning questions before implementation:

- Printed labels: English only for consistency across the app.
- Default selection: all active/on-farm pigs, with option to narrow to one or multiple pens.
- Optional columns: park for later. Sex and purpose may be useful sometimes, but should become selectable optional columns rather than always visible.

9.6A implementation state:

- Added `/print-sheets`.
- Added first printable sheet: `Weekly Weight Capture Sheet`.
- Uses existing read-only `GET /api/pig-weights/pigs` and `GET /api/pig-weights/pens`.
- Does not write to Google Sheets.
- Defaults to all active/on-farm pigs.
- Supports one or multiple pen filters.
- Uses English labels.
- Prints through normal browser print.
- Hides internal `Pig_ID` from the worker-facing sheet.
- Rows sort by current pen/camp and numeric tag number.
- Future optional columns such as sex, stage, and purpose are parked under 9.6B.
- Verification passed: `node --check static/js/printSheets.js`, focused frontend/route tests, and full local unittest suite at 129 tests.
- Deployed and owner-verified on 2026-05-20; owner confirmed `/print-sheets` is good for now.

### 9.7 Business Scenario Calculator — Future Planning

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

## Phase 10: Farm Operating System Integration - Planning Next

Goal: bring Sam, Oom Sakkie, the web app, backend modules, weather logging, Synsynk solar data, n8n workflows, and Google Sheets into one documented operating-system structure. WE can use teh n8n API to get these workflows in but we need to confirm them before we just bring them in and then start the file and documentation for them. 

Timing rule:

- Sam/order behavior is stable enough to start planning Phase 10.
- Do not build new cross-system integrations directly on Google Sheets if those integrations are likely to move to Supabase/Postgres soon.
- Do not attempt a full database migration before the operating-system map is clear.
- Recommended sequence: plan the operating-system architecture first, set up Supabase foundations second, then integrate modules behind backend APIs.

Required outcome:

- document every major workflow and platform under one system map
- define ownership for each module: sales, farm operations, pig records, worker assistant, weather, solar, reporting, notifications, and admin web app
- plan the web app as the main operating interface with clear modules for sales/orders, piggery, weather, irrigation, electricity/solar, and other farm systems as they are added
- the first screen after login should eventually make those modules easy to reach and show the most important status for each module
- create a workflow register showing trigger, purpose, inputs, outputs, reads, writes, dependencies, and risk level for each n8n workflow
- create data contracts for information passed between workflows, backend endpoints, web app pages, Google Sheets, and external systems
- set up Oom Sakkie documentation in the same style as Sam: workflow map, data flow, node responsibilities, protected logic, and input/output contracts
- ensure important operational writes go through backend-controlled logic where possible instead of direct workflow-to-sheet writes
- ensure hardware-control secrets such as IFTTT irrigation keys are stored in protected credentials/env values, not workflow expressions or sheet data
- prefer backend-owned hardware-control endpoints for irrigation start/stop before expanding Oom Sakkie irrigation commands
- keep AI agents responsible for interpretation and wording, not hidden data ownership or business-rule enforcement
- document backend module boundaries for orders, pig operations, farm worker tasks, weather logging, solar data, reporting, and notifications
- add logging and audit expectations for customer actions, worker actions, web-app actions, backend actions, weather imports, and solar imports
- make the web app the visible control panel where possible so operators can understand system state without jumping between platforms

Recommended Phase 10 sequence:

1. **10.0 Operating system map and data ownership** - document every module, workflow, sheet/table, backend endpoint, trigger, owner, risk level, and read/write direction. This is planning/documentation only.
2. **10.1 Supabase foundation** - set up environment secrets, migration tooling, backup/restore expectations, dev/prod decision, connection tests, and a repository/data-access pattern. No production cutover yet.
3. **10.2 First migration boundary: orders/sales transactions** - migrate the Phase 7.2 candidate tables first: orders, order lines, intakes, documents, status logs, and pricing. Keep backend APIs as the only write path.
4. **10.3 Farm telemetry review** - inventory weather, Sunsynk, irrigation, and alert data. Decide whether telemetry should move to Supabase before rebuilding Oom Sakkie solar/power answers.
5. **10.4 Operating dashboard / farm home** - only after the core data contracts are clear, build the web app home/dashboard that brings orders, piggery, weather, power, irrigation, and alerts together.
6. **10.5 Workflow integration cleanup** - update n8n workflows to call backend APIs/Supabase-backed endpoints instead of direct sheet reads/writes where appropriate.

Recommendation:

- Do **not** choose "Supabase first" as a full migration before Phase 10 planning.
- Do **not** choose "Phase 10 integrations first" on top of the current Google Sheets layout.
- Choose a hybrid: **Phase 10A architecture map first, then Supabase foundation, then one bounded migration/integration slice at a time**.
- Reason: Phase 10 needs a clear system map to avoid moving the wrong data, while Supabase is needed before deeper integration so we do not build new features around a data layer we plan to retire.

10A working source:

- `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md`

10A implementation state:

- Created first operating-system map.
- Captured module ownership for sales/orders, documents, pig records, weights, breeding, pork/meat planning, weather, Sunsynk, irrigation, and farm dashboard.
- Captured integration boundaries for Sam, Oom Sakkie, backend, Google Sheets, Supabase, and n8n alerts.
- Captured first data ownership register and migration priority.
- Confirmed recommended sequence: operating map first, Supabase foundation second, bounded migration/integration slices after that.
- Planning review with owner is next.

10.1 Supabase foundation working source:

- `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md`

10.1 planning state:

- Created first Supabase foundation plan.
- Captured owner-required setup details, proposed env vars, security rules, migration tooling options, backend repository pattern, first migration boundary, telemetry/Sunsynk handling, n8n access rules, LLM-friendly read-model direction, folder strategy, setup checklist, and open decisions.
- Owner review comments captured and converted into guided defaults: use existing Supabase Pro project as foundation/staging first, plain SQL migrations in `supabase/migrations/`, backend-only Supabase access, `/health/database` smoke test, orders/sales first, telemetry after the first database path is proven, and Google Sheets visible until database-backed views are proven.
- Render env var plan and local `.env` guidance are captured.
- First foundation implementation slice added locally: `supabase/migrations/` marker, backend `GET /health/database`, and tests proving missing config is safe and no connection string is returned on failure.
- Local verification passed on 2026-05-21: focused database tests passed, full unittest suite passed at 132 tests, and `/health/database` returns safe `503` / `not_configured` before `DATABASE_URL` is added.
- Deployed verification passed on 2026-05-21: Render `DATABASE_URL` connects successfully to Supabase and `/health/database` returns `success = true`, `status = ok`, `configured = true`, `database = postgres`, and harmless UTC database time.
- Phase 10.1B local baseline added: `supabase/migrations/202605210001_foundation_migration_log.sql` creates only internal `app_private.migration_log`, and backend `GET /health/database/foundation` verifies that baseline. No business tables or imports.
- Local verification passed on 2026-05-21: focused database tests passed at 6 tests, full local unittest suite passed at 135 tests, and migration contract test confirms no business tables are created.
- Deployed verification passed on 2026-05-21: owner ran the baseline SQL in Supabase SQL Editor and `/health/database/foundation` returned `success = true`, `status = ok`, migration ID `202605210001_foundation_migration_log`, and applied timestamp `2026-05-21T01:19:31.638474+00:00`.
- No Supabase schema migration, data import, or production cutover has started.
- Phase 10.2 planning source created: `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`.
- Owner accepted 10.2 recommended defaults on 2026-05-21.
- Phase 10.2A empty-table migration prepared: `supabase/migrations/202605210002_create_order_sales_tables.sql`.
- Backend schema verifier prepared: `GET /health/database/order-schema`.
- Local verification passed on 2026-05-21: focused database tests passed at 9 tests and full local unittest suite passed at 138 tests.
- Deployed verification passed on 2026-05-21: owner ran the SQL migration and `/health/database/order-schema` confirmed all seven expected order/sales tables with `missing_tables = []`.
- Phase 10.2B import dry-run script prepared: `scripts/order_sales_import_dry_run.py`.
- Dry-run reads Google Sheets only, writes nothing to Supabase, and reports `writes_to_supabase = false`.
- Local verification passed on 2026-05-21: focused dry-run tests passed at 5 tests and full local unittest suite passed at 143 tests.
- Live summary-only dry-run passed on 2026-05-21 with `writes_to_supabase = false`.
- Dry-run counts: 26 included orders, 103 included order lines, 27 included intakes, 7 included intake items, 6 included documents, 62 included status logs, and 21 included pricing rows.
- Follow-up needed before import mapping: `ORDER_STATUS_LOG` has 157 rows with missing parent order links and 111 rows linked to excluded test orders.
- Owner decision: unlinked test/status-log data can stay in Sheets but should be excluded from Supabase import if it is not linked to an included main order.
- Status-log diagnostic prepared: `scripts/order_status_log_diagnostic.py`; reads `ORDER_MASTER` and `ORDER_STATUS_LOG` only and writes nothing.
- Local verification passed on 2026-05-21: focused diagnostic/dry-run tests passed at 7 tests and full local unittest suite passed at 145 tests.
- Live status-log diagnostic passed on 2026-05-21 with `writes_to_supabase = false` and `writes_to_sheets = false`: 62 included candidates, 157 missing-parent logs, 111 test-parent logs, and 0 missing-order-id logs.
- Import mapping rule: include only the 62 included-candidate status logs by default; exclude missing-parent/test-parent logs unless owner manually approves exceptions later.
- Phase 10.2C payload mapping added to the dry-run script. It maps included rows to Supabase-shaped payload samples, still with `writes_to_supabase = false` and `writes_to_sheets = false`.
- Owner rule applied: unlinked intake rows are excluded from the first import boundary.
- Local verification passed on 2026-05-21: focused payload/dry-run tests passed at 7 tests and full local unittest suite passed at 147 tests.
- Live payload sample report passed on 2026-05-21 with `writes_to_supabase = false` and `writes_to_sheets = false`.
- Live mapped payload counts: 26 orders, 103 order lines, 0 order intakes, 0 order intake items, 6 order documents, 62 order status logs, and 21 sales pricing rows.
- Review finding before real import: some mapped orders are cancelled historical customer orders; owner should review whether all 26 included orders are worth importing before any actual insert.
- Owner decision update: first import should include completed real orders only, plus pricing reference data. Draft/pending/approved/cancelled/rejected history stays in Sheets unless manually approved later.
- Completed-only dry-run passed on 2026-05-21 with `writes_to_supabase = false` and `writes_to_sheets = false`: 3 completed orders, 53 linked order lines, 0 intakes, 0 intake items, 0 documents, 11 linked status logs, and 21 pricing rows.
- Phase 10.2D shadow import script prepared: `scripts/order_sales_shadow_import.py`.
- Default mode is plan-only; `--apply` is required before any Supabase write.
- Local verification passed on 2026-05-21: focused shadow-import/dry-run tests passed at 12 tests and full local unittest suite passed at 152 tests.
- Live plan-only run passed on 2026-05-21 with `writes_to_supabase = false` and `writes_to_sheets = false`; counts matched the approved completed-only boundary.
- Apply attempt with missing local `DATABASE_URL` failed safely before writing anything.
- First real apply attempt hit a `NotNullViolation`; the transaction rolled back and no Supabase rows were written.
- Timestamp normalization fix added, then shadow import `--apply` passed on 2026-05-21.
- Supabase verification confirms batch `IMPORT-20260521-COMPLETED-ORDERS-V1`: 3 orders, 53 order lines, 0 intakes, 0 intake items, 0 documents, 11 status logs, and 21 pricing rows.
- Phase 10.2E shadow read comparison passed on 2026-05-21: Google Sheets source mapping and Supabase batch `IMPORT-20260521-COMPLETED-ORDERS-V1` matched with `mismatch_count = 0`.
- Phase 10.2F read-only shadow endpoint implemented locally: `GET /api/shadow/orders/<order_id>/compare`.
- Local verification passed on 2026-05-21: focused shadow route/service tests passed at 32 tests and full local unittest suite passed at 164 tests.
- Local API smoke passed for `ORD-2026-0B29D7`: HTTP 200, `success = true`, `status = ok`, and `mismatch_count = 0`.
- Deployed verification passed on 2026-05-21 for `ORD-2026-0B29D7`: `success = true`, `status = ok`, `mismatch_count = 0`, `writes_to_sheets = false`, and `writes_to_supabase = false`.
- No backend read/write cutover, UI change, n8n change, or Google Sheet retirement has started.
- Phase 10.2G sales transaction extension planning added to `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`.
- 10.2G proposed tables: `sales_transactions` and `sales_transaction_items`.
- 10.2G purpose: support honest Rand values for livestock, slaughter/abattoir, and future meat/carcass sales without inferring income from pig exit counts.
- 10.2G is planning only: no SQL migration, backend route, dashboard Rand value, order cutover, or pig migration has started.
- Owner decisions captured: use constrained values now, create tables and verifier before a form, automate completed livestock transaction links later, keep deductions as a single total for now with a future child-table option, and keep buyer phone fields.
- Phase 10.2H sales transaction empty-table migration prepared locally: `supabase/migrations/202605210003_create_sales_transaction_tables.sql`.
- Phase 10.2H backend verifier prepared locally: `GET /health/database/sales-transaction-schema`.
- Local verification passed on 2026-05-21: focused database tests passed at 12 tests and full local unittest suite passed at 169 tests.
- Phase 10.2H deployed verification passed on 2026-05-21: owner ran the SQL migration and `/health/database/sales-transaction-schema` returned `success = true`, `status = ok`, migration ID `202605210003_create_sales_transaction_tables`, both expected tables found, and `missing_tables = []`.
- No backend/dashboard/order behavior changed.
- Phase 10.2I read-only sales transaction API implemented locally: `GET /api/sales-transactions`.
- 10.2I reads Supabase only and returns `writes_to_sheets = false` and `writes_to_supabase = false`.
- 10.2I supports optional `sale_stream = Livestock|Slaughter|Meat` and `limit`.
- Local route smoke without `DATABASE_URL` returned safe `503` / `not_configured`.
- Local verification passed on 2026-05-21: focused sales transaction/database tests passed at 17 tests and full local unittest suite passed at 174 tests.
- No records, write form, dashboard Rand totals, or order automation were added.
- Phase 10.2I deployed verification passed on 2026-05-21: `GET /api/sales-transactions` returned `success = true`, `status = ok`, `count = 0`, empty `sales_transactions`, and read-only source flags.
- Phase 10.2J sales transaction dry-run validator implemented locally: `POST /api/sales-transactions/dry-run`.
- 10.2J validates slaughter/livestock/meat transaction payloads and calculates gross, deductions, net total, item count, and pig count.
- 10.2J does not connect to Supabase and writes nothing to Supabase or Google Sheets.
- Local route smoke passed with a valid slaughter payload.
- Local verification passed on 2026-05-21: focused sales transaction tests passed at 8 tests and full local unittest suite passed at 177 tests.
- No real create endpoint, sale IDs, dashboard Rand totals, order automation, or pig status changes were added.
- Phase 10.2J deployed verification passed on 2026-05-21: dry-run slaughter payload returned `success = true`, `mode = dry_run`, `gross_total = 1200`, `deductions_total = 100`, `net_total = 1100`, and both write flags remained false.
- Phase 10.2K controlled sales transaction create-flow plan added to `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`.
- 10.2K planned first write endpoint: `POST /api/sales-transactions`.
- 10.2K first scope: `Slaughter` only, Supabase write only, no Google Sheets writes.
- Guardrails: atomic insert, duplicate pig protection, no dashboard Rand totals, no pig status changes, no order automation, no form yet.
- Planned implementation split: backend create service first, safe deployed write test second, cancellation/void planning third, internal form later.
- Real slaughter workflow captured for 10.2K: pigs go to `Bartelsfontein` abattoir, butcher/buyer is currently `JC Slaghuis`, carcass weight may or may not be provided, payment normally arrives about two weeks later by bank transfer/EFT, and the sale is VAT-relevant.
- Status rule for slaughter planning: delivered/slaughtered but unpaid should be `sale_status = Confirmed` and `payment_status = Unpaid`; after EFT payment, update to `sale_status = Completed` and `payment_status = Paid`.
- Pig `S10` was reported on 2026-05-21 as recently slaughtered and marked as slaughtered in Google Sheets. Treat it as a possible later real transaction candidate only after the Supabase create/cancel flow is proven.
- VAT handling is now an explicit planning point: before dashboard financial reporting, decide/add structured VAT fields rather than hiding VAT permanently in notes.
- Phase 10.2K1 backend create service implemented locally: `POST /api/sales-transactions` supports `Slaughter` only, requires `created_by`, writes Supabase header/items atomically, blocks duplicate pig IDs, and writes nothing to Google Sheets.
- Local verification passed on 2026-05-21: focused sales transaction tests passed at 15 tests, local missing-config route smoke returned safe `503`, and full local unittest suite passed at 184 tests.
- Phase 10.2K1/10.2K2 deployed verification passed on 2026-05-21: synthetic transaction `SALE-2026-F17E16` was created for `PIG-TEST-102K2-20260521`, read back through `GET /api/sales-transactions`, and duplicate-pig protection returned `409 duplicate_pig` on a second create attempt.
- The synthetic test row remains in Supabase as a clear test transaction. It is not linked to a real pig/order.
- No real `S10` transaction has been written.
- Phase 10.2K3 cancellation/void flow implemented locally: `POST /api/sales-transactions/<sale_id>/cancel` requires `cancelled_by` and `cancel_reason`, marks `sale_status = Cancelled`, sets `payment_status = Cancelled`, appends an audit note, and never hard-deletes rows.
- Local verification passed on 2026-05-21: focused sales transaction tests passed at 20 tests, local missing-config cancel route smoke returned safe `503`, and full local unittest suite passed at 191 tests.
- Phase 10.2K3 deployed verification passed on 2026-05-21: synthetic transaction `SALE-2026-F17E16` was cancelled, duplicate release was proven by creating `SALE-2026-28EF1B` with the same synthetic pig ID, and the second synthetic transaction was also cancelled.
- Final readback shows both synthetic slaughter transactions are cancelled.
- No real `S10` transaction has been written.
- Phase 10.2L internal slaughter sale form implemented locally at `/sales/slaughter`.
- The form defaults to `JC Slaghuis`, `Bartelsfontein`, `Unpaid`, `Confirmed`, and `EFT`; it loads active pigs, creates slaughter transactions, shows recent slaughter transactions, and can cancel non-cancelled transaction rows.
- Local verification passed on 2026-05-21: `node --check static/js/slaughterSale.js`, focused frontend/sales tests passed at 27 tests, local page smoke returned `200`, and full local unittest suite passed at 192 tests.
- Phase 10.2L2 payment/final amount update implemented locally: `PATCH /api/sales-transactions/<sale_id>/payment` updates a non-cancelled slaughter transaction amount, payment status, sale status, payment method, optional carcass weight, and appends an audit note.
- `/sales/slaughter` now has an `Update Payment` action for non-cancelled rows.
- Local verification passed on 2026-05-21: `node --check static/js/slaughterSale.js`, focused sales/frontend tests passed at 23 tests, local missing-config update route smoke returned safe `503`, and full local unittest suite passed at 200 tests.
- 10.2L2 real-value test is parked by owner decision on 2026-05-21 until the real JC Slaghuis sale value is known.
- Do not treat this as blocked implementation work; return to it when the butcher payment/final amount is available.
- Next step: continue with the next selected Phase 10 slice while keeping S10/payment completion as an owner-pending follow-up.
- Phase 10.2L3 slaughter form UX polish implemented locally: added a top save action, transaction search, sale-status filter, payment-status filter, clear filters action, filtered transaction count, and clearer status pills.
- 10.2L3 intentionally keeps the form single-pig only; multi-pig/batch slaughter remains a planned follow-up.
- Local verification passed on 2026-05-21: `node --check static/js/slaughterSale.js`, frontend contract tests passed at 10 tests, local page smoke returned `200`, and full local unittest suite passed at 200 tests.
- Next step: deploy 10.2L3 and owner-check `/sales/slaughter`, then plan 10.2L4 multi-pig slaughter batch entry before changing the data logic.
- Phase 10.2L4 multi-pig slaughter batch plan added: one slaughter batch should be one `sales_transactions` row with multiple `sales_transaction_items` rows.
- 10.2L4 plan confirms batch/header holds slaughter date, buyer, abattoir, payment status, sale status, payment method, and batch total; item rows hold each pig, optional weights, optional per-pig amount, and notes.
- Recommended amount approach: support both batch total and optional per-pig amounts, but do not auto-split a batch total across pigs until allocation rules are approved.
- Planned implementation sequence: add `payment_date`, extend backend multi-item create, build multi-pig selector, update payment with batch total/payment date, then run a synthetic two-pig batch test.
- Open decisions remain before implementation: per-pig amount UI from start or later, payment-date requirement rule, carcass-weight estimate rule, and paid-batch correction rule.
- Phase 10.2L4A payment-date schema migration implemented locally: `supabase/migrations/202605210004_add_sales_transaction_payment_date.sql`.
- Backend verifier added locally: `GET /health/database/sales-payment-date-schema`.
- Local verification passed on 2026-05-21: focused database tests passed at 15 tests, local missing-config verifier smoke returned safe `503`, and full local unittest suite passed at 203 tests.
- Phase 10.2L4A deployed verification passed on 2026-05-21: `/health/database/sales-payment-date-schema` returned `success = true`, `status = ok`, migration ID `202605210004_add_sales_transaction_payment_date`, applied timestamp `2026-05-21T15:45:04.636332+00:00`, and `payment_date_column_found = true`.
- Phase 10.2L4B backend multi-item create support implemented locally: create already writes multiple item rows under one sale header; validation now blocks duplicate `pig_id` values inside the submitted batch before any database write.
- 10.2L4B keeps scope narrow: no Google Sheets writes, no pig status changes, no auto batch-total split, and no form change yet.
- Local verification passed on 2026-05-21: focused sales transaction create/dry-run/route tests passed at 17 tests and full local unittest suite passed at 206 tests.
- Phase 10.2L4C form multi-pig selector implemented locally: `/sales/slaughter` now has one batch header with add/remove pig rows, per-pig amount, optional carcass weight, optional pig note, calculated batch total, duplicate-selection blocking, and the same Supabase create endpoint.
- 10.2L4C still does not update Google Sheets or pig status, and it does not solve final delayed payment handling yet.
- Local verification passed on 2026-05-21: `node --check static/js/slaughterSale.js`, focused frontend/sales tests passed at 27 tests, local page smoke returned `200`, and full local unittest suite passed at 206 tests.
- Phase 10.2L4D payment update with batch total/payment date implemented locally: payment update now requires `payment_date` when marking a transaction Paid, updates header totals/payment/date/status, and does not silently reallocate a final batch total across multiple pig item rows.
- Single-pig payment updates still update that one item amount and optional carcass weight; multi-pig batch payment updates leave item rows unchanged until allocation rules are approved.
- Local verification passed on 2026-05-21: `node --check static/js/slaughterSale.js`, focused update/route/frontend tests passed at 25 tests, local page smoke returned `200`, and full local unittest suite passed at 208 tests.
- Phase 10.2L4E deployed synthetic batch test passed on 2026-05-21: created two-pig synthetic batch `SALE-2026-17736A`, confirmed active duplicate create was blocked with `409`, updated payment to `Paid` with `payment_date = 2026-05-21`, cancelled the batch, then confirmed duplicate-pig release by creating reuse batch `SALE-2026-0C9DE0` and cancelling it.
- 10.2L4E deployed page smoke passed: `/sales/slaughter` loaded and included the multi-pig row container and batch total UI.
- Synthetic test pig IDs used: `PIG-TEST-L4E-A-20260521180640` and `PIG-TEST-L4E-B-20260521180640`; both synthetic transactions were cancelled.
- Phase 10.2L4 closed on 2026-05-21 after deployed synthetic verification; manual UI owner smoke is optional, not a blocker.
- S10 / real JC Slaghuis payment completion remains owner-pending until the real amount is known.
- Phase 10.3 telemetry review selected as the next Phase 10 slice.
- Phase 10.3 working source created: `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`.
- 10.3 plan scope: inventory weather, Sunsynk, forecast, irrigation, and alert data; design compact backend read models for Oom Sakkie and dashboard use; keep working weather stable; fix the slow Sunsynk path by moving toward backend/Supabase prepared payloads rather than more agent-over-sheet loops.
- 10.3 initial repo inventory result: no backend telemetry modules or local telemetry ingestion scripts were found in this repo; current telemetry knowledge is in n8n workflow exports/docs, so external logger/cron/script locations still need owner confirmation.
- External source folders imported and filed under `external_sources/`: Sunsynk logger, local weather station logger, forecast logger, and non-telemetry landing-page source. One forecast `.env` file is present but ignored by git.
- 10.3A partial inventory now captures each logger's env vars, external API, sheet write target, and likely role.
- 10.3 planned sequence: inventory first, design Sunsynk current-state read model, propose telemetry schema, decide ingestion path, build one read-only backend endpoint, update `2.2`, then align weather/forecast and irrigation command boundaries.
- Owner confirmed telemetry loggers run as Render cron services; irrigation appears to be n8n-run.
- Owner confirmed production spreadsheets for Sunsynk, Weather, and Irrigation.
- Local Google Sheets inventory is blocked until the three telemetry spreadsheets are shared with service account `amadeuspigtrackersystem@amadeus-farm-weather-bot.iam.gserviceaccount.com`.
- Owner proposed retention/rollup direction: keep current state, roll 5-minute readings into daily summaries, then monthly/yearly summaries, and avoid keeping unnecessary raw bulk forever.
- Recommendation captured: keep raw 5-minute data only for a short tested retention window first, keep daily/monthly/yearly rollups long-term, and do not delete raw data until rollup jobs and backup/export rules are proven.
- Service account access confirmed for the three telemetry sheets.
- Weather and irrigation tab/header/formula inventory succeeded.
- Sunsynk metadata inventory succeeded, but values reads timed out even on tiny ranges, confirming the current Sunsynk sheet is not a good live answer source for Oom Sakkie.
- 10.3A conclusion: keep weather stable for now, treat irrigation as a later hardware-control/audit design, and prioritize Sunsynk current-state backend/Supabase read model first.
- 10.3B Sunsynk current-state read model planned in `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`: first endpoint should be `GET /api/telemetry/power/current` with source freshness, current battery/solar/load/grid/generator state, deterministic flags, backend-prepared summary, and explicit stale/unavailable behavior.
- Owner agreed the 10.3B payload direction.
- 10.3C telemetry schema proposal added to `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`: first migration should be power-first with `telemetry_sources`, `power_readings_5min`, `power_latest_state`, and `telemetry_alerts`; rollups wait until calculation rules are confirmed.
- Owner agreed to implement 10.3C.
- Phase 10.3C first telemetry power schema migration implemented locally: `supabase/migrations/202605210005_create_telemetry_power_tables.sql`.
- Backend verifier implemented locally: `GET /health/database/telemetry-power-schema`.
- Migration creates `telemetry_sources`, `power_readings_5min`, `power_latest_state`, and `telemetry_alerts`, and seeds `sunsynk-main-inverter`; it imports no telemetry readings, changes no Render logger, and changes no n8n workflows.
- Local verification passed on 2026-05-21: focused database tests passed at 18 tests, local missing-config verifier smoke returned safe `503`, and full local unittest suite passed at 211 tests.
- Phase 10.3C deployed verification passed on 2026-05-21: `/health/database/telemetry-power-schema` returned `success = true`, `status = ok`, migration ID `202605210005_create_telemetry_power_tables`, all four expected tables found, `missing_tables = []`, and `sunsynk_source.source_id = sunsynk-main-inverter` with `stale_after_minutes = 15`.
- Future Supabase migrations can be run directly from the local workspace when `DATABASE_URL` is available locally and network/database command approval is granted; still inspect SQL first, run exactly one migration file, then verify through the matching backend health endpoint.
- 10.3D ingestion decision: existing Render Sunsynk logger should call the Flask backend, not write directly to Supabase. Backend owns validation, raw/latest writes, summary flags, and Oom Sakkie read model.
- 10.3E backend endpoints implemented locally: `POST /api/telemetry/power/ingest` protected by `TELEMETRY_INGEST_API_KEY`, and `GET /api/telemetry/power/current` for Oom Sakkie/dashboard current-state reads.
- Local verification passed on 2026-05-21: focused telemetry tests passed at 8 tests, local route smokes returned safe config failures, and full local unittest suite passed at 219 tests.
- 10.3D/10.3E deployed verification passed on 2026-05-21: synthetic ingest returned `success = true`, `status = ok`, `source_id = sunsynk-main-inverter`, `reading_id = PWR-FEC6256BECB7`, and `source.writes_to_supabase = true`.
- Deployed current-state readback passed: `/api/telemetry/power/current` returned battery `82%`, battery state `charging`, solar `3120 W`, load `1240 W`, grid state `not_using_grid`, generator `off`, deterministic flags, and stale summary because the synthetic timestamp was intentionally old.
- Security note: rotate `TELEMETRY_INGEST_API_KEY` before wiring the real Render Sunsynk logger if the current test key was pasted into chat or logs.
- 10.3F Sunsynk logger update implemented locally in `external_sources/telemetry/sunsynk/amadeus-sunsynk-logger/main.py`.
- Logger now posts to backend ingest when `AMADEUS_BACKEND_URL` and `TELEMETRY_INGEST_API_KEY` are set, while keeping Google Sheets as a transition mirror unless `GOOGLE_SHEETS_ENABLED=false`.
- Logger README added with required Render cron env vars.
- First Render cron recovery test failed in the Google Sheets mirror path with `gspread` 404, and `/api/telemetry/power/current` still showed the old synthetic reading.
- Logger hardened locally so a successful backend ingest is not failed by a Google Sheets mirror error.
- Render cron source was moved to the main `amadeus-pig-tracking-system` repo with root directory `external_sources/telemetry/sunsynk/amadeus-sunsynk-logger`; a trailing-space root directory issue was corrected.
- Phase 10.3F deployed verification passed on 2026-05-22: Render cron printed `backend_ingest_enabled = true`, `backend_ingest_success = true`, reading ID `PWR-49F0F62E4F21`, `google_sheets_written = true`, and timestamp `2026-05-22T00:28:20+02:00`.
- `/api/telemetry/power/current` read back the real fresh state with `data_age_minutes = 0`, `is_stale = false`, battery `47%`, battery state `discharging`, load `872 W`, no solar, no grid, and no generator.
- Local syntax verification passed with `python -m py_compile`.
- Next step: update Oom Sakkie `2.2` to call `/api/telemetry/power/current` instead of scanning Sunsynk Google Sheets.
- 10.3G local workflow update prepared on 2026-05-22:
  - `2.2 - Amadeus Sunsynk Sub-Agent` is now a deterministic backend current-power worker: `When Executed by Another Workflow` -> `HTTP - Get Current Power State` -> `Code - Format Current Power Answer`.
  - Removed the `AI Sunsynk Agent`, `OpenAI Chat Model`, and all Sunsynk Google Sheets tool nodes from `2.2`.
  - `2.0 - OOM SAKKIE` `Sunsynk_Info_Tool` description now points to the backend/Supabase current-power endpoint and states that daily totals/kWh/last-24h trends are planned for later read models.
  - Local JSON parse verification passed for both workflow exports.
  - Backend endpoint readback before import showed fresh data with `data_age_minutes = 2`, `is_stale = false`, battery `47%`, load `785 W`, no solar, no grid, and no generator.
- Next step: import `docs/04-n8n/workflows/2.2 - Amadeus Sunsynk Sub-Agent/workflow.json` and `docs/04-n8n/workflows/2.0 - OOM SAKKIE - Amadeus Assistant Agent/workflow.json` into n8n, then ask Oom Sakkie a current power question.
- 10.3G live verification passed on 2026-05-22 after importing `2.2` and `2.0`.
- Telegram test `What's the power like now?` returned quickly with current backend/Supabase data: battery `46%` discharging, solar `0.0 kW`, load `1.0 kW`, grid not using grid `0 W`, generator off `0 W`, latest reading `22 May 2026, 00:40`, and data age `4 minutes`.
- This confirms Oom Sakkie power questions no longer depend on slow Sunsynk Google Sheets reads for current status.
- Remaining future telemetry work: daily totals/kWh/last-24h power read models, weather/forecast backend alignment, and later irrigation/audit modeling.
- 10.3H local backend slice prepared on 2026-05-22:
  - Added read-only `GET /api/telemetry/power/recent?hours=24`.
  - Endpoint summarizes recent `power_readings_5min` rows with sample-based battery range, average/max solar/load, grid/generator active sample counts, approximate active minutes, hourly buckets, data coverage, and explicit limitations.
  - It deliberately does not report kWh, cost, import, or export totals until reliable Sunsynk energy counters or approved interval-integration rules are added.
  - Focused telemetry/workflow tests pass at 11 tests after updating the old Sunsynk workflow contract.
  - Full local test suite passes at 221 tests.
- Next step: deploy backend, verify `/api/telemetry/power/recent?hours=24` on Render, then decide whether `2.2` should answer last-24h trend questions from this endpoint.

Farm home/dashboard idea:

- Source note moved from `planning/ToDoList.md`.
- After login, the web app should eventually open on a useful farm home page that brings the wider operating system together.
- Desired first-viewport signals: current weather, short forecast, power/solar state, and navigation into pig system, weather, power, irrigation, orders, and other modules as they mature.
- The page may include farm photos as a quiet rotating background/screensaver element, but operational information must remain readable and useful.
- Treat this as an operating dashboard, not a marketing landing page.
- This belongs in Phase 10 because it depends on weather, solar, irrigation, pig records, and order modules having stable documented contracts.
- Broader app layout note moved from `planning/ToDoList.md`: the desktop app should use available screen width better, with a consistent page template so information is not unnecessarily squeezed into the middle.
- Mobile/PWA note moved from `planning/ToDoList.md`: investigate whether the app should support installable mobile behavior, for example a Progressive Web App pattern, so phone use feels closer to an app while still running through the browser.
- UX rule: do not redesign every page separately. Establish shared layout conventions for page width, filters, tabs, tables, action placement, mobile behavior, and desktop density.
- Shared template/layout follow-up moved from `planning/ToDoList.md`: define a reusable page template for new pages so forms, tables, filters, action buttons, and page width stay consistent.

Slaughter form refinement notes:

- Source note moved from `planning/ToDoList.md` after first `/sales/slaughter` owner use.
- The save action should be easier to reach without unnecessary scrolling, likely by adding a top action row or sticky action behavior consistent with the weight form.
- The bottom transaction table should use the agreed table layout pattern with filters and clearer spacing.
- The slaughter form needs a planned multi-pig workflow because more than one pig may go to slaughter at a time.
- Multi-pig planning needs to decide whether each pig has its own amount/weight line or whether the batch has one total with per-pig item details.
- Payment date is separate from slaughter date and should be captured once the butcher pays.
- The real amount may arrive later than slaughter date, so payment/final amount update needs a payment date field before financial reporting.
- Consider estimating carcass weight from latest live weight, but keep it clearly marked as an estimate until actual carcass weight is supplied.
- Do not expand the current single-pig form into a multi-pig financial workflow without a short planning slice first.

Questions to answer when planning:

- Which widgets are essential for the first version: weather now, forecast, power status, irrigation status, breeding alerts, litter attention, order attention, or farm photos?
- Should the home page replace the current first screen after login or be a separate `/home` route first?
- What information is safe to show on a shared farm screen without exposing customer/order details?
- Should mobile/PWA work be a small app-shell enhancement first, or wait until Supabase-backed modules settle?
- What desktop max-width/layout pattern should be used for operational pages: full-width tables, constrained forms, two-column detail pages, or module-specific templates?
- For `/sales/slaughter`, should the next refinement be UX/table polish first, or multi-pig batch entry first?
- For slaughter batches, should amount be captured per pig, as one batch total split across pigs, or both?
- Should payment date be required only when `payment_status = Paid`, or optional for all payment updates?

## Phase 11: Pork Sales Business Module - Discovery Source Captured

Goal: incorporate the new Amadeus Farm pork sales model without breaking the current live pig sales and order system.

Source document:

- `docs/08-business-modules/PORK_SALES_MODEL.md`

Current decision:

- Treat the pork sales model as a business-module source document first, not an implementation backlog.
- Owner can keep adding assumptions, prices, cut-set details, legal/compliance notes, delivery rules, packaging ideas, and customer-offer wording to the source document.
- Implementation planning starts only after the business model is stable enough to turn into phases safely.

What this module will eventually affect:

- product types: live pig, assisted slaughter, full carcass, half carcass, custom cut
- order lifecycle: deposit, balance due, slaughter booking, processing, packing, delivery/collection
- inventory planning: weaning classification, suggested purpose, live weight, allocation, slaughter date, carcass yield, packed weight
- finance: VAT, costs, clean profit per pig, clean profit per batch/month
- web app modules: orders, customers, processing, delivery, finance, labels, loyalty/branding
- Sam/Oom Sakkie: customer wording, internal operating prompts, order checks, document retrieval
- Google Sheets/data model: new sheets or tables for carcass orders, cut sets, processing batches, delivery routes, payments, and cost assumptions

Planning rule:

- Do not retrofit carcass meat sales into the current live-pig order flow by quick patches.
- First capture the business rules clearly, then design data contracts and phased migration.
- Existing live pig sales must continue working while the meat module is introduced.
- Prefer one pig source of truth with purpose/revenue-stream fields or views before creating a separate slaughter-ready pig sheet; only split data storage if processing/batch needs clearly justify it.

Immediate next action:

- Keep refining `docs/08-business-modules/PORK_SALES_MODEL.md`.
- When ready, ask for a dedicated planning pass to split the module into safe implementation phases.
- This is cross-cutting enough that a Claude Code review should be used before implementation starts.

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
- Phase 7.0 backend verification and service-boundary cleanup — complete 2026-05-18: order service modules extracted, cleanup done, Google Sheets quota cache/retry deployed, and production create-with-lines checkpoint passed.
- Phase 7.1 intake and payload hygiene — complete 2026-05-18: handoff contracts, slim context shapes, Chatwoot lifecycle/write policy, workflow validation tests, and n8n `1.0` upload/readback completed.
- Phase 7.2 database scaling review — planning complete 2026-05-18: future Postgres direction, owner decisions, draft schema, formula replacement strategy, import rules, Sheet retirement rules, rollback gates, and Supabase Pro signup captured in `docs/02-backend/DATABASE_SCALING_PLAN.md`.
- Phase 8D repeat-service action — live-verified 2026-05-20: Baby's mating `MAT-2026-1565CF` was marked `Pregnancy_Check_Result = Not_Pregnant`, `Mating_Status = Repeat_Service`, `Outcome = Repeat_Required`, `is_open = No`, with no linked litter and no unintended pen move.
- Phase 8D follow-up fix — deployed and live-verified 2026-05-20: date parsing now accepts full month names from Google Sheet formulas, for example `9 June 2026` and `10 September 2026`; Baby's new mating `MAT-2026-9EFC4E` now shows expected check `2026-06-09` and expected farrowing `2026-09-10` from the live API.
- Phase 9.1A new litter defaults — live-verified 2026-05-20: Lolly's `LIT-2026-9E4A` created 11 piglets and Shupe's `LIT-2026-EB92` created 8 piglets; generated rows have `Purpose = Unknown` and `Source = Born_on_Farm`.
- Phase 9.1B litter attention dashboard — deployed and browser-verified 2026-05-19.
- Phase 9.2A pig dropdown usability — deployed and owner-verified 2026-05-20.
- Phase 9.3 weight form context — deployed and owner-verified 2026-05-20: current-pen helper added beside optional move pen, save payload unchanged, syntax/focused tests and full unittest suite passed.
- Phase 9.4A/B/C1 weight report — owner-verified 2026-05-20: read-only report endpoint and `/weight-report` page with Today default, active-pig filtering, pen grouping, detail rows, browser print support, duplicate markers, loss flags, improved table spacing, pen-name-only display, and single-day date hiding; focused tests, full local unittest suite, local route/API smoke, deploy, and browser review passed.
- Phase 9.4C2 duplicate prevention — deployed and owner-verified 2026-05-20: duplicate same-pig/same-date weight saves return `409` until explicitly confirmed; true edit/delete/void audit remains deferred to Supabase.
- Phase 9.4 report tag formatting — implemented locally 2026-05-20: `/weight-report` numeric pig tags display as three digits and rows sort by numeric-aware tag order within each pen; focused checks and full local suite passed.

Additional verification:

- Phase 9.4 report tag formatting deploy check - owner-verified 2026-05-20: deployed `/weight-report` displays numeric pig tags correctly; default pen grouping remains accepted.
- Phase 9.6A printable weight capture sheet - deployed and browser-verified 2026-05-20: `/print-sheets` shows the read-only weekly weight capture sheet with English labels, all-active default, multi-pen filtering, browser print support, and no Google Sheets writes.

Recommended next:

1. **Phase 10.3 telemetry review** - selected as the next Phase 10 slice after 10.2L4 was closed. Inventory weather, Sunsynk, irrigation, and alert data before changing the slow Oom Sakkie power path.
2. **Next Supabase order decision point** - later choose between feature-flagged order read model planning or broader completed-order import/reimport process.
3. **Pork Sales Business Module discovery** - continue refining `docs/08-business-modules/PORK_SALES_MODEL.md` in parallel as owner notes become available; do not implement yet.

7.3D planning note:

- Use Telegram buttons where they make operator actions easier, similar to the approval workflow.
- Buttons may support actions like `Send latest quote`, `Choose quote Q-...`, `Cancel`, or `Open order summary`.
- Buttons must not bypass confirmation, backend destination checks, document eligibility checks, or backend-owned send endpoints.
- Approval buttons and document-send buttons must remain separate paths.
- Decision: use one explicit send button after Oom Sakkie has shown document/order/customer context.
- Button text must be specific, for example `Send quote to customer`, with a nearby `Cancel` button.
- Backend must re-check the latest/non-voided quote, order, confirmed destination conversation, and stale/replaced document state at click time.
- Existing backend send endpoints already exist, but they require explicit `conversation_id` and should not be called directly by Oom Sakkie without a prepare/confirm guard.
- Recommended first implementation plan:
  - add backend `prepare_latest_quote_send` contract that returns safe button context but sends nothing - Done and deployed
  - add backend `send_latest_quote_confirmed` contract for button callbacks that re-checks safety, then calls existing send logic - Done and deployed
  - add a separate document-send callback worker workflow, `2.4.5`, and route to it from the existing callback entry point so there is not a second active Telegram callback trigger - Done and deployed
  - keep `1.5 - Outbound Document Delivery` unchanged as the backend-owned Chatwoot attachment delivery path
- Invoice sending remains future-only unless explicitly approved.

7.3D backend prepare endpoint:

- Added `POST /api/orders/<order_id>/quote/prepare-send`.
- It prepares order/document/destination context and Telegram button labels/callback data.
- It does not send anything and does not call n8n or Chatwoot.
- Focused route tests passed.

7.3D backend confirmed-send endpoint:

- Added `POST /api/orders/<order_id>/quote/send-latest-confirmed`.
- Requires `document_id` and `conversation_id`.
- Re-checks order existence, latest quote, selected document ID, document type, and voided/superseded state before sending.
- Calls existing `send_order_document` only after checks pass.
- Focused route tests passed.

7.3D workflow state:

- `2.0` local export passes Telegram chat/user context into `Orders_Info_Tool`.
- `2.4.4` is active in n8n and adds `prepare_latest_quote_send`, calls the backend prepare endpoint, and sends operator-only Telegram confirmation buttons.
- `2.4.5 - Document Send Callback Handler` is active in n8n as workflow `8b14lAqmyrD0LYZz`.
- `2.4.2` is retired from the live path because its active Telegram callback trigger can take over the Oom Sakkie bot webhook. GateKeeper now owns both `message` and `callback_query` updates and routes quote callbacks to `2.4.5`.
- `2.0 - OOM SAKKIE - Amadeus Assistant Agent` was manually imported/updated through the n8n UI by the owner on 2026-05-18.
- n8n API verification confirms live `2.0` now passes `telegram_chat_id` and `telegram_user_id` into `Orders_Info_Tool`.
- n8n API verification confirms `2.4.5 - Document Send Callback Handler` exists as workflow `8b14lAqmyrD0LYZz` and is active.
- Claude review accepted Path A: keep callback routing in GateKeeper, do not move callbacks into `2.0`, add authorization coverage to GateKeeper's callback branch, use diagnostic-first webhook reset, preserve `2.0` as the normal-message AI/tool workflow, and retire/archive `2.4.2`. Revised plan: `docs/04-n8n/OOM_SAKKIE_ROUTING_ARCHITECTURE_PLAN.md`.
- 2026-05-19 live recovery completed: owner manually uploaded the cleaned GateKeeper workflow and replaced the Telegram Trigger node; `Hi` routed through GateKeeper to `2.0`, and Oom Sakkie replied.
- Repo export refreshed from live n8n GateKeeper workflow `s8QaxmqT69Z5mhvE`, so the current trigger node is preserved in `docs/04-n8n/workflows/2 - The GateKeeper/workflow.json`.
- Recovery checklist retained for future incidents: `docs/04-n8n/OOM_SAKKIE_MANUAL_RECOVERY_CHECKLIST.md`.
- 2026-05-19 quote-send prepare test reached `2.4.4`, displayed Telegram buttons, and `Cancel` routed through GateKeeper to `2.4.5` successfully. No customer document was sent.
- Duplicate prepare acknowledgement was fixed in live `2.0`: `2.4.4` sends the direct button message, then `2.0` suppresses the follow-up AI acknowledgement when output contains the quote-send preparation pattern.
- Safety fix deployed: backend now blocks quote-send prepare and confirmed-send for terminal orders (`Cancelled`, `Completed`, or rejected approval state).
- Tool-skip issue fixed in live `2.0`: `Simple Memory` was removed/disconnected so repeated prepare requests call `2.4.4` instead of answering from memory.
- 2026-05-19 real send button test passed with `ORD-2026-71609C`: quote `Q-2026-71609C` / document `DOC-2026-AD8111` was sent to Chatwoot conversation `1774`, WhatsApp received the quote PDF message, backend document status became `Sent`, and n8n GateKeeper `45071` plus `2.4.5` `45072` succeeded.
- Test order cleanup passed: `ORD-2026-71609C` was cancelled after the successful send test; one line was cancelled and reserved count is zero.
- Final 7.3D smoke passed on 2026-05-19 with fresh order `ORD-2026-46D437`: prepare produced only one Telegram button message, `Cancel` left quote `Q-2026-46D437` / `DOC-2026-67813E` as `Generated`, prepare again produced one message, `Send quote to customer` sent the PDF to Chatwoot conversation `1774`, WhatsApp received the quote, and backend recorded `Document_Status = Sent`, `Sent_By = Charl`, `Sent_At = 2026-05-19`.
- Final test order cleanup passed: `ORD-2026-46D437` was cancelled after the successful send test; one line was cancelled, payment status became `Cancelled`, and reserved pig count is zero.
- Phase 7.3D is complete and live-verified.

Pick the next item deliberately before implementation so docs, workflow exports, and tests stay aligned.

7.3E weather LLM triage note:

- Source note moved from `planning/ToDoList.md`: workflow `2.1` is giving LLM errors in the system.
- Keep `2.1` as the weather sub-agent; do not merge it into Oom Sakkie or the order workflows while triaging.
- First checks: latest `2.1` executions, failing node name, input payload to the failing LLM node, model/credential status, JSON-only output parser behavior, and whether `2.1.1` forecast tool is still returning usable data.
- Desired fix style: smallest contained workflow/backend/doc update, followed by one live Oom Sakkie weather question and one direct `2.1` execution check.
- 2026-05-19 diagnosis: recent `2.1` executions `45114`, `45118`, and `45120` failed at `Weather Router (JSON Plan)` because model `chatgpt-4o-latest` was rejected. Later executions `45121`, `45123`, and `45125` failed at the same node because OpenAI received `input[1].content[0].text = null`.
- Execution `45125` confirmed the weather station sheet data was fresh (`2026-05-19 5:10:18`) and the failure was not weather data availability. The trigger payload into `2.1` was `{ "input": null }`.
- Prepared fix: `2.0` `Weather_Info_Tool` now uses n8n `$fromAI('weather_question', ...)` for the sub-workflow input with a safe fallback, and `2.1` `Weather Router (JSON Plan)` uses `gpt-5.5` plus a non-null prompt fallback (`current weather at the farm`).

7.3F Oom Sakkie Navigation Buttons - Planned UX Enhancement:

- Source note moved from `planning/ToDoList.md`.
- Add Telegram buttons where they make Oom Sakkie easier for farm users, especially when the user sends a greeting or a broad prompt rather than a specific question.
- First button row idea: `Weather`, `Solar`, `Orders`; later add modules as they become stable.
- Weather flow idea after tapping `Weather`: show a short useful summary and offer buttons such as `Now`, `Today`, and `Forecast` if those options prove helpful.
- Buttons should complement natural language, not replace it. Users must still be able to ask normal questions and get the same results.
- Keep one Telegram trigger through GateKeeper. Button callbacks must be deterministic and authorized before reaching tool workflows.

Questions to answer when planning:

- Should greeting buttons be shown only on `Hi`/empty broad prompts, or also after every Oom Sakkie response?
- Which first buttons are genuinely useful enough for daily use: `Weather`, `Solar`, `Orders`, `Irrigation`, or `Pig System`?
- Should each button immediately call a tool, or first ask a smaller choice such as `Now` / `Today` / `Forecast`?
- Regression coverage added in `tests/test_workflow_contracts.py`: `2.0` weather tool must use AI-supplied input, and `2.1` must not reference `chatgpt-4o-latest` or send a nullable router prompt.
- Follow-up check requested for `2.2 - Amadeus Sunsynk Sub-Agent` and `2.1.1 - Amadeus Forecast Tool` because these features had also stopped responding reliably.
- 2026-05-19 `2.2` diagnosis: recent execution `45137` was called with valid input (`What's the power like now?`) but was cancelled after about three minutes. The run reached `Sunsynk Current Overview` but did not return a final agent answer. Prepared workflow hardening (`$fromAI('sunsynk_question', ...)`, prompt fallback, `maxIterations = 4`, no-repeat-tool instruction) was not enough; owner retest still ran too long. Decision: stop quick workflow tweaking and defer `2.2` to a dedicated Sunsynk data/backend/Supabase architecture review.
- 2026-05-19 `2.1.1` diagnosis: workflow is active but had no recent executions, which means the current weather path is not calling it. Prepared hardening: optional forecast offsets now default to blank strings instead of nullable values so direct/future calls remain safe. Keep a future design note open on whether `2.1` should call `2.1.1` again or continue using the `Forecast_10Day_Current` sheet directly.
- Regression coverage added for `2.2` and `2.1.1`: Sunsynk tool input must use AI-supplied input, Sunsynk agent must have input fallback and iteration cap, and forecast optional offsets must not pass raw nulls.
- Sunsynk follow-up scope: inventory Sunsynk backend folders/modules if present, n8n workflows (`2.2`, `ALERT - Sunsynk`), Google Sheets tabs (`Amadeus_Sunsynk_Log`, `Sunsynk_Current_Overview`, `Sunsynk_Daily_Summary`, `Sunsynk_Last24h_Hourly`, `Sunsynk_5min_Intervals`, `Sunsynk_Alert_Log`), data volume, read/query patterns, and whether this should move to Supabase/Postgres as farm telemetry before rebuilding the assistant answer path.
