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
| Phase 8: Breeding Board Improvements | 8D Live-Verified; 8E Owner-Verified; 8F First Slice Owner-Verified; Drill-In Browser-Accepted For Now | Next: collect real-use notes before adding mating suggestions. |
| Phase 9: Pig, Weight, And Reporting Improvements | 9.1A Live-Verified; 9.1B Browser-Verified; 9.1C Deployed And Browser-Verified; 9.2A/9.2B Owner-Verified; 9.3/9.3B Owner-Verified; 9.4 Current Slice Complete; 9.5 Visible; 9.5B Planned; 9.6A Browser-Verified; 9.6C Bulk Partial-Upload Local Ready; 9.7F Newborn Health Live-Verified; 9.7G Deployed And Owner-Verified; 9.7H Browser-Accepted; 9.7I Return Navigation Deployed/Working; 9.7J Sex Count Browser-Checked; Sales Dashboard Accepted For Now | Next: keep 9.6C open for next real-batch pen-move confirmation; continue Oom Sakkie/Jarvis runtime foundation after the next bundled Claude review. |
| Phase 10: Farm Operating System Integration | 10.1 Complete; 10.2A Verified; 10.2B/C Dry-Run Complete; 10.2D Applied And Verified; 10.2E Complete; 10.2F Deployed And Verified; 10.2G Planned; 10.2H Verified; 10.2I Live-Verified; 10.3J4 Live-Verified; 10.3K Live-Verified; 10.3L4 Live-Verified And Cleaned; 10.3N Live-Verified And Cleaned; 10.3O Planned; 10.3P Deployed And Verified; 10.3Q Live-Verified; 10.3R Deployed And Verified; 10.3S Dry-Run Complete; 10.3T Applied And Verified; 10.3U/V Live-Verified; 10.3W8 Scheduled Run Verified; Farm Home Dashboard Live-Verified; 10.6A Owner-Tested; 10.6B Owner-Tested; 10.6C Local Ready; 10.6D Local Ready; 10.6E Local Ready; 10.6F Local Ready; 10.6G Local Ready; 10.6H Local Ready; 10.6I Local Ready; 10.6J Owner-Tested; 10.6K Local Ready; 10.6L Owner-Tested; 10.6M Owner-Tested; 10.6N Owner-Tested; 10.6O Local Ready; 10.6P Local Ready; 10.6Q Local Ready; 10.6R Local Ready; 10.6S Local Ready; 10.6T Local Ready; 10.6U Local Ready; 10.6V Local Ready; 10.6W Local Ready; 10.6X Local Ready; 10.6Y Local Ready; 10.6Z Local Ready | Next: browser-test spoken stop commands, inspect the local Voice Session log, smoke the expanded read-only tool set, verify Available Checks and Safety Status panels from the local browser, open the Review Packet locally, test unsupported action refusal/mixed action safety notes, and confirm traces carry a stable kiosk session ID. |
| Phase 10.7: Oom Sakkie Specialist Agent Roster | 10.7G Local Ready | Planned-only specialist manifests, advisory trace-review endpoint, user-action-triggered kiosk advisor panel, combined advisor trace reader, and advisor SQL hardening exist. No live delegation, autonomous loops, write tools, auto-marking, or second user-facing brain. |
| Phase 11: Pork Sales Business Module | 11A Local Ready | Deploy/browser-check read-only pig allocation readiness before any meat-sales writes. |

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
- `ALERT - Sunsynk` - historical only; replaced by `ALERT - Power Backend Delivery` on 2026-05-23 and removed from repo workflow exports.
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

## Phase 8: Breeding Board Improvements — 8D Live-Verified; 8E Owner-Verified; 8F Browser-Accepted For Now

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

### 8E Breeding Board Sorting - Owner-Verified

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

Implementation state 2026-06-01:

- `/matings` now uses section-aware sorting instead of one generic date sort.
- `Needs Action Now` sorts by operational urgency first: no litter after three weeks, overdue farrowing, then overdue pregnancy checks; ties sort by the relevant overdue date.
- `Closed / Farrowed` sorts newest to oldest by actual farrowing date where available, then expected farrowing date, then mating date.
- `Move Soon / Prepare`, `Upcoming Pregnancy Checks`, and `All Open Matings` continue to sort by the relevant upcoming action date.
- Closed or linked-litter records are classified into `Closed / Farrowed` before overdue flags are considered, so completed records do not stay in action sections because of old formula flags.
- Added a closed-loop `Add Litter` shortcut on eligible mating cards. It links to `/master/add-litter?mating_id=<id>`.
- Add Litter now reads the `mating_id` query parameter and preselects the mating, which fills mother, father, expected farrowing date, and pen through the existing form logic.
- Saving the litter continues to use the existing backend path that links the litter back to the mating and closes the mating flow.
- Local verification passed: `node --check static/js/matings.js`, `node --check static/js/addLitter.js`, focused frontend/mating/litter tests, `/matings` and `/master/add-litter?mating_id=...` route smoke, and full local unittest suite at 307 tests.
- Owner deployed and browser-tested on 2026-06-01. Sorting and the `Add Litter` closed-loop shortcut are working and accepted for now.

### 8F Fertility, Bloodline, And Breeding Suggestions - Browser-Accepted For Now

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
- Owner note moved from scratch 2026-05-26: add clearer mating-level attention groups/reasons as well as litter-level attention. Matings and litters are intertwined, but they are not the same record; the app should make that distinction obvious and show what each mating or litter needs next.

8F first slice decisions and implementation state 2026-06-01:

- Start with a read-only analytics page before any automated mating suggestions.
- First KPI scope: mating count, confirmed-pregnant count, repeat-service count, farrowed count, open count, litter count, born-alive average, weaned average, and survival percentage.
- Added read-only backend API `GET /api/pig-weights/breeding-analytics`.
- Added `/breeding-analytics` page and linked it from `/matings`.
- Source data is existing `MATING_OVERVIEW` and `LITTER_OVERVIEW`; no Google Sheets or Supabase writes.
- Page has separate sow and boar performance tables.
- This is not a recommendation engine yet. It is a visibility slice so owner can inspect whether current data is trustworthy enough for future breeding suggestions.
- Local verification passed: `node --check static/js/breedingAnalytics.js`, `node --check static/js/matings.js`, focused breeding/frontend/mating tests, route smokes for `/breeding-analytics` and `/api/pig-weights/breeding-analytics`, and full local unittest suite at 309 tests.
- Owner deployed/browser-checked `/breeding-analytics` and confirmed it is working on 2026-06-01.
- Next 8F step should stay read-only: add drill-in/data-quality context before any automated mating suggestions.

8F drill-in/data-quality implementation state 2026-06-01:

- Added read-only backend API `GET /api/pig-weights/breeding-analytics/<pig_id>`.
- Added `/breeding-analytics/<pig_id>` detail page and changed the overview animal links to open that breeding analytics detail instead of the generic pig profile.
- Detail page displays the selected sow/boar's current KPI summary, related mating rows, related litter rows, and data-quality flags gathered from `MATING_OVERVIEW` and `LITTER_OVERVIEW`.
- Current flags are informational only: overdue pregnancy check, overdue farrowing, farrowed without linked litter, closed without clear litter/repeat-service outcome, missing born-alive count, missing weaned count, pig-record/born-alive mismatch, and existing litter attention reasons.
- No automated mating suggestions, no Google Sheets writes, and no Supabase writes were added.
- Local verification passed: `node --check static/js/breedingAnalytics.js`, `node --check static/js/breedingAnalyticsDetail.js`, focused breeding/frontend/mating tests at 33 tests, route smoke for `/breeding-analytics/<pig_id>`, route smoke for `GET /api/pig-weights/breeding-analytics`, and full local unittest suite at 312 tests.
- Next action: deploy and browser-check `/breeding-analytics`, then open several sow/boar rows and confirm the detail view makes the data easy to understand before planning any suggestion engine.

## Phase 9: Pig, Weight, And Reporting Improvements - 9.1A Live-Verified; 9.1B Browser-Verified; 9.2A/9.2B Owner-Verified; 9.3/9.3B Owner-Verified; 9.4 Current Slice Complete; 9.5 Visible; 9.5B Planned; 9.6A Browser-Verified; 9.6C Deployed / Awaiting Owner Live Test; 9.7 Planned

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
- Owner direction 2026-05-26: the system should increasingly intertwine captured events instead of relying on duplicate manual updates. Mating -> litter -> generated piglets -> death/exits/weaning/sales/slaughter should flow through backend-owned actions that update the right source records and logs. The long-term goal is parent/litter/bloodline reporting that can show outcomes such as sold, slaughtered, died, finishers, meat stream, slow growers, fast growers, and retained breeding candidates for each sow/boar pairing.

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

9.1C litter attention and weaning workflow - deployed and browser-verified:

- Source notes moved from `planning/ToDoList.md`.
- Review how `LITTER_OVERVIEW.Needs_Attention` is calculated and make the reason visible to the user. If a litter tile says it needs attention, the app should explain what action is needed.
- Owner note 2026-05-26: litter attention currently opens the litter detail page, but the detail view does not give the operator a clear action to resolve the attention item. Plan the next slice so each attention reason has an obvious action path, for example mark weaned, review purpose/classification, update piglet state, or dismiss/resolve when no action is needed.
- Clarify when litter-level tracking should stop or change after weaning. Litter data should remain useful historically, but post-weaning growth and outcomes should move to individual pig records where appropriate.
- Add a litter tile/detail action to mark a litter as weaned.
- Marking a litter as weaned should ask for the weaning date.
- On confirmation, apply the weaning date to the related live/active piglets and update the litter state in a controlled backend-owned write.
- Dead, sold, or off-farm piglets should not distort active litter age/growth/average metrics after their exit state is known.
- Weaning should feed the future purpose-classification workflow: breeding candidate, grow-out, sale, and later slaughter/meat stream eligibility.

Implementation state 2026-05-26:

- Litter detail now receives `attention` metadata from `LITTER_OVERVIEW`, including reason, recommended action, litter status, wean date, active pig count, and action type.
- Litter detail page shows an attention/action panel instead of only showing piglets.
- Added `POST /api/pig-weights/litter/<litter_id>/mark-weaned`.
- First action is deliberately narrow: the operator chooses a wean date, backend counts active/on-farm piglets for the litter, updates `LITTERS.Weaned_Count` / `LITTERS.Wean_Date` when those columns exist, and stamps linked active piglets in `PIG_MASTER` with `Litter_Size_Weaned`, `Wean_Date`, and `Updated_At`.
- Sold/off-farm piglets are excluded from the active weaning count.
- Purpose/classification changes are not automatic yet; weaned litters with active piglets remain a future `review_purpose` workflow.
- Local verification passed: focused litter service tests, dashboard service tests, frontend route contract tests, and `node --check static/js/litterDetail.js`.

Follow-up audit 2026-05-30:

- Real attention checks for `LIT-2026-OTY0`, `LIT-2026-0LBF`, and `LIT-2026-8A0F` showed the attention list is still correctly driven by `LITTER_OVERVIEW.Needs_Attention`.
- `LIT-2026-OTY0`: `Born_Alive = 12`, `Pig_Master_Row_Count = 10`, `Weaned_Count = 10`, `Wean_Date = 5 March 2026`, `Active_Pig_Count = 5`, `Exited_Pig_Count = 5`; reason is `Linked pig records do not match born alive count`. This is a record-reconciliation issue, not a simple weaning action.
- `LIT-2026-0LBF`: `Born_Alive = 11`, `Pig_Master_Row_Count = 9`, `Wean_Date = 28 Feb 2026`, blank `Weaned_Count`, `Active_Pig_Count = 1`, `Exited_Pig_Count = 8`; reason is `Linked pig records do not match born alive count`. This needs reconciliation of born-alive/history rows and weaning count before it should disappear from attention.
- `LIT-2026-8A0F`: `Born_Alive = 8`, `Pig_Master_Row_Count = 8`, `Tagged_Pig_Count = 0`, `Untagged_Pig_Count = 8`, `Active_Pig_Count = 6`, `Exited_Pig_Count = 2`; reason is `Piglets need tag numbers`. This should stay visible until linked piglets have tag numbers or the tagging rule changes.
- Local code now maps attention reasons to specific action types: `reconcile_litter_records`, `complete_born_alive`, `assign_tag_numbers`, `review_litter`, `review_purpose`, or `mark_weaned`.
- Litter detail no longer shows the `Mark as Weaned` form for record-mismatch or missing-tag attention reasons. It only shows that form when the backend returns `action_type = mark_weaned`.
- Local verification passed on 2026-05-30: focused dashboard/litter/frontend tests passed at 19 tests, `node --check static/js/litterDetail.js` passed, and local API checks returned the expected reason/action pairs for the three real litters above.
- Remaining closure step: deploy and browser-check the litter detail pages for those three litters, then either fix the underlying sheet records/tags or leave the attention items visible as legitimate operational work.
- Owner deployed the first action-reason hardening on 2026-05-30 and reconciled `LIT-2026-OTY0` / `LIT-2026-0LBF` in the source records.
- Follow-up local fix on 2026-05-30: `Weaned - review purpose` now appears only when an active/on-farm piglet in the litter still has blank or `Unknown` purpose. Older weaned litters whose active piglets already have `Sale`, `Grow_Out`, or `Breeding` should not stay on the dashboard just because the future auto-classification function does not exist yet.
- Local dashboard API check after the purpose-review fix returned one legitimate litter attention item: `LIT-2026-8A0F` / Sow Olivia / `Piglets need tag numbers`. Owner decision: keep this item visible for now because these piglets only get tags later once they are marked.
- Future purpose-classification function remains planned: when active weaned piglets still have blank/`Unknown` purpose, the system should eventually suggest or assign purpose from weight/growth/litter rules. For older data where purpose is already set, the workaround is to treat the existing purpose as accepted and not show `review purpose`.
- Owner deployed and browser-verified this slice on 2026-05-30. Dashboard/litter attention now looks correct: reconciled older litters no longer show purpose-review noise, and `LIT-2026-8A0F` remains visible as the intended tag-number reminder.

Lifecycle automation planning note:

- Future piglet death action should be available from the easiest user context, either pig profile/list or litter detail.
- Piglets that die after live birth and before weaning should still have `PIG_MASTER` rows because they were part of `born_alive`. Marking a piglet as died should update `PIG_MASTER` status/on-farm/exit fields, log the date/reason, and let `LITTER_OVERVIEW` recalculate survival and active counts.
- Piglets or pigs that die after weaning are also important records and should keep their pig row with the correct death/exit date and reason so growth, survival, parent, and bloodline analytics remain honest.
- Weaning should update litter-level historical fields and linked active piglet fields, without overwriting sold/dead/off-farm history.
- Completed sales/order pickup should mark linked pigs as no longer on farm, set the correct exit reason/order link, and feed parent/litter performance reporting.
- Slaughter/meat sales should similarly connect the sales transaction, pig exit state, carcass/weight fields where known, and future revenue-stream analytics.
- These workflows should become backend-owned actions, not manual edits across multiple sheets.
- Parent and bloodline analytics should be based on these lifecycle events so each sow/boar can be evaluated by fertility, litter size, survival, growth, sale/slaughter/meat outcomes, retained breeding candidates, and profitability.
- Supabase migration rule: litter attention and row-count checks must distinguish `total_born` from `born_alive`. Stillborn and mummified piglets count in litter outcome metrics, but they should not require live pig rows in the pig master table. Missing-pig attention should compare generated/live pig records to `born_alive`, not `total_born`.
- Supabase migration rule: model pig lifecycle/death events explicitly. Pre-weaning death and post-weaning death are both valuable outcomes. Keep the pig record, store death/exit date and reason, and derive litter survival, weaned count checks, sow/boar performance, and bloodline metrics from those events.
- Sheet improvement: add `LITTER_OVERVIEW.Attention_Reason` at the end of the table so the dashboard and operator can see what is missing, for example born-alive count missing, linked pig records do not match born-alive count, or piglets need tag numbers. Add it at the end rather than between existing columns to avoid shifting current references.

Questions to answer when planning:

- What exact sheet/formula currently drives `Needs_Attention`, and which reasons should be shown in the UI?
- Should weaned litters disappear from the dashboard attention list once every active piglet has a purpose?
- Which fields should be updated when marking a litter as weaned: `LITTERS`, generated `PIG_MASTER` rows, both, or a future Supabase table?
- Should the first weaning action be Google Sheets-backed, or should it wait for the pig/litter Supabase migration?

Decision for first slice:

- Use the current Google Sheets-backed pig/litter source because the live litter workflow still writes there.
- Keep the write backend-owned and limited to weaning fields only.
- Defer purpose/classification, sale allocation, and dismiss/resolve actions to later slices.

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
- Owner note 2026-05-26: the dashboard still showed `0` for slaughter even after a slaughter sale/update was entered. Investigate whether the slaughter sale was saved as a Supabase `sales_transactions` row, whether it has the correct `sale_stream = Slaughter`, status/payment fields, date, item rows, and whether the dashboard summary is reading that transaction source instead of only old pig-exit counts. Desired behavior: show one slaughter sale and its Rand value once the transaction source is defined and trusted.
- 2026-05-26 local implementation: dashboard summary now reads a monthly Supabase `sales_transactions` aggregate for non-cancelled transactions and exposes transaction count plus `net_total` value by stream. The home dashboard shows `count / Rand value` for Livestock, Slaughter, and Meat sales, while old pig-exit counts remain available as separate audit fields. Local test-client without `DATABASE_URL` safely reports the transaction source as not configured; Render should activate the Supabase path through its configured `DATABASE_URL`.
- 2026-05-26 live verification passed: owner confirmed the live dashboard now displays the slaughter sale value.
- Future dashboard should separate:
  - `Sales count`: number of sale transactions per stream.
  - `Item/pig count`: number of pigs/items sold per stream.
  - `Sales value`: Rand total per stream.
- Owner note moved from scratch 2026-05-26: add a full sales summary screen later that brings all sale streams together with totals, Rand value, and filters by date/year/month. It should show a professional overview and allow drilling into each stream or sale record.
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

Future stock valuation note moved from `planning/ToDoList.md` on 2026-06-01:

- Later, add an estimated current farm stock value view that values active pigs by stage, purpose, weight band, and approved pricing assumptions.
- This should be clearly labelled as estimated stock value, not actual income.
- It can use piglets, weaners, growers, finishers, slaughter-ready animals, and later meat options once the pricing assumptions are trusted.
- Do not build this until the lifecycle outcome and sales transaction paths are trustworthy enough that sold/dead/slaughtered/off-farm animals are not accidentally included.

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
- Owner note moved from `planning/ToDoList.md` on 2026-05-30: the printable weight capture sheet should later become an editable bulk-capture workflow. The user should be able to fill in new weights, optional camp/pen moves, and notes in a sheet-like page, then save all rows in one batch. Backend validation should detect duplicates or mistakes before committing, and only accepted rows should be written.
- Owner selected 9.6C on 2026-06-01 because bulk weighing will be used later the same day.
- Draft-saving is required so partially typed work is not lost when the operator walks away. First recommended slice: local browser draft storage tied to date/filter/user-device, with a later Supabase shared-draft option only if needed.
- Rows with blank weight must be skipped and must not create weight-log records.
- Upload should be a deliberate batch commit after review, not auto-save to Google Sheets per row.
- Backend validation should preflight the batch before commit: valid pig IDs, valid dates, positive numeric weights, duplicate same-pig/same-date weights, and valid optional destination pens.
- Duplicate same-pig/same-date handling should reuse the existing duplicate-prevention rule. Default should block the affected row and show it in review rather than silently writing a second weight.
- Optional pen movement should use the existing weight-with-optional-move behavior: only log movement when a destination pen is selected and differs from the current pen.

9.6C open questions before implementation:

- Should the first draft save be local to the same device/browser, or must drafts be shared across devices/users immediately?
- Should one weighing date apply to the whole batch, or should individual rows be allowed to override the date?
- For duplicate weights on the same pig/date, should the batch upload block those rows by default, or should an operator be able to confirm and write duplicates from the review screen?
- Should bulk entry live as a new page, for example `/bulk-weights`, or as an editable mode/tab inside `/print-sheets`?

9.6C owner decisions 2026-06-01:

- First draft save can be local to the same device/browser.
- One weighing date applies to the whole batch.
- Duplicate same-pig/same-date weights should be blocked by default and shown in review.
- Bulk entry should be a new page accessible from Print Sheets and the single Add Weight page.

9.6C local implementation state 2026-06-01:

- Added `/bulk-weights` page.
- Added links from `/print-sheets` and `/pig-weights`.
- Page uses active pig row order matching the printable sheet: current pen/camp, then numeric tag number.
- Page supports multi-pen filtering, one batch date, new weight, optional new pen, and notes.
- `Save Draft` stores typed rows in browser `localStorage` for the selected date.
- `Upload Batch` runs backend preflight first, shows accepted/skipped/blocked counts, asks for confirmation, then writes valid new rows. Duplicate/existing same-pig/same-date rows are skipped instead of blocking the whole batch.
- Blank weight rows are skipped and do not create `WEIGHT_LOG` rows.
- Backend added `POST /api/pig-weights/weights-batch/preflight` and `POST /api/pig-weights/weights-batch`.
- Backend flags invalid pigs, invalid dates, non-positive/invalid weights, invalid destination pens, duplicate rows in the batch, and existing same-pig/same-date weights before commit. A batch with at least one valid new row may still upload; blocked rows are returned in the review payload and are not written.
- Optional pen movement reuses the existing weight-with-optional-move behavior.
- Local verification passed: `node --check static/js/bulkWeights.js`, focused bulk/frontend tests, full local unittest suite at 305 tests, route smoke for `/bulk-weights`, and no-op batch upload guard.
- Owner deployed the `/bulk-weights` changes on 2026-06-01.
- 2026-06-01 owner decision: keep 9.6C open while the farm does a live bulk-weight test later today or soon after; close only after owner confirms the flow is correct with real data.
- Remaining closure step: owner browser-test the local/deployed `/bulk-weights` flow with real weighing data before marking 9.6C deployed/browser-verified. Owner confirmed on 2026-06-04 that this must wait until real weights are available.
- 2026-06-08 live-data correction: owner reported a 68-row bulk weighing session looked like only 20 rows in the daily weight report. Code audit found no 20-row cap in `/bulk-weights` preflight/save; the likely mismatch was `/weight-report` hiding historical weight rows for pigs that are no longer currently `Active` / `On_Farm = Yes`. Local fix keeps historical weight rows visible, adds `status`, `on_farm`, `active_on_farm`, and `not_active_on_farm_count`, and marks rows that are no longer active/on-farm instead of silently dropping them. Verification passed: focused bulk/report/litter/frontend tests and JS syntax checks.
- 2026-06-08 live upload correction: owner saved a bulk draft, then `Upload Batch` stopped when some rows already had weights for the date. Local fix changed bulk upload to partial-save semantics: upload all valid new rows, skip duplicate/existing rows, keep true failed rows visible for correction, and update the local draft accordingly. Verification passed: focused bulk/frontend tests and `node --check static/js/bulkWeights.js`.

Recommended 9.6 split:

1. **9.6A Printable weight capture sheet** - build `/print-sheets` with the first printable weekly weight sheet only.
2. **9.6B Sheet filters and polish** - add useful filters after 9.6A works: all active pigs, by pen/camp, by purpose, for-sale animals, grow-out/sale animals.
3. **9.6C Bulk weight entry from printable sheet** - selected 2026-06-01; use the same row order as the printed sheet to speed up data entry later.

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

### 9.7 Lifecycle Outcome Tracking — Planned Next

Owner decision 2026-06-01:

- Make lifecycle outcome tracking the next deliberate farm-efficiency slice after current live checks.
- The goal is to make every important animal outcome feed the correct pig, litter, sow, boar, sales, slaughter, and dashboard reporting paths.
- This should improve the truthfulness of the whole farm picture before automated recommendations are built.

Required outcome:

- Define and implement backend-owned lifecycle actions for the main outcomes instead of relying on disconnected manual sheet edits.
- Start with the most operationally important outcomes:
  - death/removal
  - sale/live-stock exit
  - slaughter/abattoir exit
  - weaning outcome
  - later meat-stream movement
- Each action should update the correct source records/logs once and expose enough readback for the web app to show what happened.
- Pig-level state should stay accurate: `Status`, `On_Farm`, exit/death/slaughter/sale fields, current pen, and relevant dates.
- Litter-level and breeding-level reporting should receive the outcome context needed for survival, weaning, growth, retained/sold/slaughtered/dead counts, and future sow/boar performance.
- Dashboard reporting should use these lifecycle outcomes rather than guessing from partial fields.
- Pre-weaning deaths must keep the pig row/history because they are part of born-alive and survival history; do not delete or hide those rows as if they never existed.
- Actions should be auditable and operator-controlled; do not silently rewrite historical outcomes or auto-classify animals without owner approval.

Recommended first implementation slice:

1. **9.7A Outcome map and current-state audit**
   - Inventory current fields, formulas, pages, and write paths for death, sale, slaughter, weaning, and removal.
   - Identify which outcomes already have a backend action and which still depend on manual edits.
   - Produce a clear action matrix: event, source table/sheet, required inputs, records updated, reports affected, and unresolved questions.
2. **9.7B Death/removal action**
   - Add the first controlled action for death/removal if no complete backend-owned path exists.
   - Capture date, reason/category, notes, recorded-by, and whether it happened pre-weaning or post-weaning.
   - Update pig state and logs while preserving the pig row for survival history.
3. **9.7C Sales/slaughter outcome linking**
   - Make completed Supabase sales/slaughter transactions feed the pig/litter/breeding outcome views cleanly.
   - Avoid double-counting exits already represented in `PIG_MASTER`.
4. **9.7D Reporting feedback**
   - Add read-only outcome summaries to relevant pig, litter, sow/boar, and dashboard views.
5. **9.7E Detail readback and closed-action cleanup**
   - Hide outcome action panels when the underlying transaction is already closed/paid/completed.
   - Add read-only lifecycle history to pig and litter detail pages so closed records still explain what happened.

Questions to answer during 9.7A:

- Which current sheet fields are the source of truth for death date, exit date, exit reason, slaughter date, and sale stream?
- Is there already a death/removal log sheet, or should the first implementation use existing `PIG_MASTER` fields plus a new audit log?
- For pre-weaning deaths, should the action require selecting the litter and piglet row, or can it infer the litter from the pig record?
- For slaughter outcomes, should completion of a paid/closed slaughter transaction update pig state automatically, or should there be an explicit operator confirmation step first?
- What dashboard numbers should change immediately after each outcome type?

9.7A audit state 2026-06-01:

- Created `docs/02-backend/PIG_LIFECYCLE_OUTCOME_PLAN.md` as the planning source for lifecycle outcome tracking.
- Current audit found that born-alive piglet creation, litter weaning, and order-based live-stock sale completion already have backend-owned actions.
- Current audit found that Supabase slaughter transactions intentionally do not update `PIG_MASTER` yet, so slaughter pig/litter/breeding outcome linking remains a gap.
- Current audit found no complete backend-owned death/removal action; this is the recommended first build slice because it directly affects survival, litter, sow/boar, and dashboard truth.
- Recommended next implementation: 9.7B controlled death/removal action on pig detail, preserving the pig row and litter links for historical outcome reporting.

9.7B local implementation state 2026-06-01:

- Added backend service `mark_pig_death_or_removal()`.
- Added route `POST /api/pig-weights/pig/<pig_id>/lifecycle/death`.
- Added a controlled `Lifecycle Outcome` form to `/pig/<pig_id>`, visible only for active/on-farm pigs.
- Supported reasons are `Died`, `Culled`, `Lost`, `Removed`, and `Other`.
- Successful actions update `PIG_MASTER.Status`, `On_Farm`, `Exit_Date`, `Exit_Reason`, `General_Notes`, and `Updated_At` while preserving the pig row and litter/parent links.
- Terminal/off-farm pigs are blocked; correction mode remains a future separate workflow.
- Local verification passed: `node --check static/js/pigDetail.js`, focused pig lifecycle/frontend tests at 27 tests, route smoke for `/pig/<pig_id>` plus invalid lifecycle payload, and full local unittest suite at 316 tests.
- Owner can see the action in the UI after deploy, but it has not been live-tested yet.
- Remaining closure step: browser-check with a safe known/test case before using it for a real farm death/removal event.
- 2026-06-02 dry-run verification added: `POST /api/pig-weights/pig/<pig_id>/lifecycle/death` accepts `dry_run = true`, validates the pig and returns planned updates without writing to Google Sheets.
- Real dry-run check against active pig `PIG-2026-42B7` returned `rows_updated = 0` and planned `Status = Removed`, `On_Farm = No`, `Exit_Date = 02 Jun 2026`, `Exit_Reason = Removed`; immediate readback confirmed the pig remained `Active` / `On_Farm = Yes`.
- Do not create/delete dummy live pig rows for this closure. Real write closure should wait for an actual farm case or an explicitly approved test pig row that can remain marked as test history.
- Verification passed: focused pig lifecycle tests and full local unittest suite at 330 tests.

9.7C local implementation state 2026-06-01:

- Added backend service `confirm_slaughter_pig_exits()`.
- Added route `POST /api/sales-transactions/<sale_id>/confirm-pig-exits`.
- Added a `Pig Exit Confirmation` form to the slaughter sale detail page.
- This action is explicit and operator-triggered; it does not run automatically when a sale is created, completed, or paid.
- It reads the Supabase sales transaction and linked item rows, then updates linked `PIG_MASTER` rows only if all linked pigs still exist, are not terminal, and are still on farm.
- Successful confirmation sets linked pigs to `Status = Slaughtered`, `On_Farm = No`, `Exit_Date`, `Exit_Reason = Sold to Abattoir`, optional `Carcass_Weight_Kg`, `General_Notes`, and `Updated_At`.
- It writes to Google Sheets `PIG_MASTER` and does not write to Supabase.
- If any linked pig is missing, terminal, or already off farm, no pig rows are updated and the action returns a blocking error.
- Local verification passed: `node --check static/js/slaughterSaleDetail.js`, `node --check static/js/pigDetail.js`, focused sales lifecycle/routes/frontend/pig lifecycle tests at 38 tests, route smoke for `/sales/slaughter/<sale_id>` plus missing-config confirm endpoint, and full local unittest suite at 320 tests.
- Remaining closure step: deploy and browser-check on an existing slaughter sale. If the linked pig was already manually marked slaughtered, the endpoint should block and report that no pig rows were updated.

9.7D local implementation state 2026-06-02:

- Added read-only monthly lifecycle outcome counts to `get_dashboard_summary()`.
- Dashboard herd panel now shows `Outcomes This Month`.
- Counts come from `PIG_MASTER.Exit_Date`, `Status`, and `Exit_Reason`.
- Displayed counts: sold, slaughtered, dead, and removed.
- This is intentionally separate from sales transaction values so animal outcome truth is not confused with income.
- No new write path was added.
- Local verification passed: `node --check static/js/dashboard.js`, focused dashboard/frontend tests at 22 tests, dashboard route smoke, and full local unittest suite at 320 tests.
- Remaining closure step: deploy and browser-check that the home dashboard shows the new outcome line correctly.
- 2026-06-02 deploy feedback: outcome block made the neighboring dashboard cards look stretched/empty. Local layout refinement compacted the outcome counts into a strip and set dashboard grid items to align to their content height instead of stretching all cards to the tallest card.
- Layout refinement verification passed: `node --check static/js/dashboard.js`, focused dashboard/frontend tests at 22 tests, dashboard route smoke, and full local unittest suite at 320 tests.

9.7E local implementation state 2026-06-02:

- Owner screenshot showed `/sales/slaughter/SALE-2026-1DE373` as `Completed` and `Paid`, while the `Pig Exit Confirmation` action still displayed.
- Slaughter sale detail now treats `Completed`, `Cancelled`, or `Paid` slaughter sales as closed and hides the confirm action.
- Backend `confirm_slaughter_pig_exits()` also blocks closed/paid/cancelled slaughter transactions, so a direct API call cannot update pigs through a closed sale.
- `/pig/<pig_id>` now includes read-only lifecycle history from `PIG_MASTER`: wean date/weight, exit date/reason, linked exit order, and carcass weight.
- `/litter/<litter_id>` now includes read-only lifecycle outcome counts from `PIG_MASTER`: active, sold, slaughtered, dead, removed, and other.
- No historical correction workflow was added; if old data is inconsistent after a sale is closed, that should become a deliberate correction/audit slice rather than reopening the normal action button.
- Local verification passed: `node --check static/js/slaughterSaleDetail.js`, `node --check static/js/pigDetail.js`, `node --check static/js/litterDetail.js`, focused lifecycle/frontend tests at 33 tests, and full local unittest suite at 323 tests.
- Remaining closure step: deploy and browser-check that `SALE-2026-1DE373` no longer shows `Pig Exit Confirmation`, and that pig/litter detail pages show the read-only outcome history clearly.
- Owner deployed and confirmed `Pig Exit Confirmation` no longer shows for the closed sale.
- Local API inspection was fixed by loading `.env` at Flask app startup with `override=False`; Render env vars still take precedence.
- Real data inspection found `SALE-2026-1DE373` linked to `PIG-2026-C390` / tag `S10`; the pig was already `Slaughtered` and `On_Farm = No`, but `PIG_MASTER.Exit_Date` was returned by Google as `14 May`, `Exit_Reason` was `Slaughtered`, and `Exit_Order_ID` was blank.
- Added backend-only closed slaughter reconciliation endpoint `POST /api/sales-transactions/<sale_id>/reconcile-pig-exits`.
- Reconciliation is dry-run-first by default, only works for completed/paid slaughter sales, refuses cancelled sales, and refuses any linked pig that is not already `Slaughtered` / off-farm.
- Applied reconciliation for `SALE-2026-1DE373`: `PIG-2026-C390` now has `Exit_Order_ID = SALE-2026-1DE373`, `Exit_Reason = Sold to Abattoir`, and readback shows lifecycle `exit_date = 2026-05-14`.
- Date parsing now handles Supabase ISO timestamps with timezone and Google Sheets day-month display values such as `14 May`.
- Verification passed: real API readback for `PIG-2026-C390`, `node --check static/js/slaughterSaleDetail.js`, and full local unittest suite at 329 tests.

9.7F litter newborn health action - Live-Tested Complete:

- Owner note moved from scratch on 2026-06-02: litters need reminders for vaccination, earmarking, and deworming based on days since birth once the exact timing is confirmed with the farm.
- Corrected owner/farm process on 2026-06-03: in the first few days, the real newborn-health action is Panacur + Ecomectin only. Earmarks and eartags happen around weaning, because piglets are too young earlier and the sow is still too involved.
- Preferred workflow is similar to bulk weights: printable capture sheet plus a digital bulk table where current live piglets/litters can be ticked off and fields captured in one batch.
- Do not implement broader bulk health capture until the required day offsets, products/actions, and data destination are agreed.
- Owner decisions 2026-06-02/03: this belongs inside the existing `Needs_Attention` litter flow; newborn health action uses Ecomectin 1% as `Antiparasitic` + Panacur 4% as `Deworming`, plus vaccination only if/when a true vaccine product exists; product selection must come from `PRODUCT_REGISTER`; treatments must create normal `MEDICAL_LOG` treatment rows; earmarking should be structured pig-level truth, but belongs with the wean/tag action rather than the first-days treatment action.
- First backend slice is local: `POST /api/pig-weights/litter/<litter_id>/newborn-health` supports dry-run-first newborn health capture. It finds active/on-farm piglets in the litter, plans `Earmarked = Yes` / `Earmark_Date`, and plans/appends `MEDICAL_LOG` rows for selected antiparasitic/deworming/vaccination product IDs.
- `PIG_MASTER` columns are set as `AK = Earmarked` and `AL = Earmark_Date`.
- Current `PRODUCT_REGISTER` real readback has `PRD-001 Ecomectin 1%`, `PRD-002 Panacur 4%`, and `PRD-003 Electro Guard`; no vaccination product was visible yet.
- Real dry-run against `LIT-2026-9E4A` with `PRD-001 Ecomectin 1%` and `PRD-002 Panacur 4%` previewed 10 piglet earmark updates and 20 `MEDICAL_LOG` rows: 10 `Antiparasitic` Ecomectin rows and 10 `Deworming` Panacur rows; `writes_to_sheets = false`.
- Litter detail UI wiring is local: `/litter/<litter_id>` now has a hidden newborn health action form that appears when the litter attention reason/action indicates earmarking, antiparasitic/deworming, or newborn health. It loads products from `PRODUCT_REGISTER`, defaults Ecomectin/Panacur when present, previews first, invalidates stale previews when fields change, and applies only after operator confirmation.
- Newborn health is now a first-class computed litter attention reason in the backend. For active, not-yet-weaned litters, missing earmark date, missing Ecomectin/antiparasitic record, or missing Panacur/deworming record takes priority before tag-number attention. Litters with `Litter_Status = Weaned` or a parseable `Wean_Date` are excluded from this live newborn-health reminder so old records do not flood daily attention.
- Historical backfill note: later build a small reconciliation/bulk backfill screen or script for older litters. It should select old litters, set actual earmark date if known, add actual Ecomectin/Panacur treatment dates if known, dry-run first, and apply only after review.
- Supabase migration note: pig earmark fields and all `MEDICAL_LOG` treatment rows/products must be included in the future pig/medical migration so newborn health actions are not lost when operational data moves out of Google Sheets.
- Future note: the first implementation applies to all active/on-farm piglets in the litter. Per-pig untick/exception handling is noted for later but intentionally not included yet because this action should normally apply to all linked live piglets.
- Verification passed: focused litter service tests and full local unittest suite at 332 tests.
- Live test passed on 2026-06-03 with `LIT-2026-9E4A`: 10 active/on-farm piglets were updated, the dead/off-farm piglet was skipped, 10 Ecomectin rows and 10 Panacur rows were written to `MEDICAL_LOG`, and litter attention moved on to tag-number attention.

9.7G correct newborn/weaning attention timing - Deployed And Owner-Verified:

- Problem found during 9.7F live test: newborn health, earmarks, tags, and weaning are not one action. The system should not keep showing a litter as needing tag numbers weeks before the tag/wean action is relevant.
- Correct process target:
  - First few days after birth: Panacur + Ecomectin treatment only.
  - Around weaning: earmarks + eartags/tag numbers + wean date/count should be handled together.
  - Dashboard and Telegram should show weaning/tag attention only when it becomes actionable.
- Proposed attention timing:
  - Use an estimated wean date per litter.
  - Default weaning age is 35 days after birth.
  - Start dashboard `Needs Attention` and Telegram attention for wean/tag action from 3 days before estimated wean date.
  - Preferred planning option to evaluate during build: start showing the action from the closest Monday to the 3-day warning window, so weekly planning can catch the work cleanly.
  - Do not show tag-number attention before that window, unless there is an explicit data-quality/reconciliation issue.
- Required build slice:
  - Add/backend-compute an estimated wean date for litter detail and attention output. - Local
  - Change newborn health attention so it no longer requires `Earmarked` / `Earmark_Date`. - Local
  - Move earmark/tag capture into the weaning/tag action path. - First local step: newborn-health UI no longer exposes the earmark checkbox; a full wean/tag action path remains future work.
  - Keep old/historical litters from flooding attention. - Local
  - Surface estimated/target wean date clearly on `/litter/<litter_id>`. - Local
  - Make the litter detail page use the wide layout and table pattern already started in 9.7F. - Done in 9.7F; 9.7G added timing cards.
- Telegram note: wean/tag reminders should use the farm attention digest path, not a separate one-off workflow, with useful timing such as morning planning and possibly midday/end-of-day reminders.
- Local implementation details:
  - Default estimated wean date is `Farrowing_Date` / piglet `Date_Of_Birth` + 35 days.
  - Tag/wean attention starts 3 days before estimated wean date.
  - If the system cannot parse a birth/farrowing date, it does not suppress the attention item because timing cannot be trusted.
  - `/litter/<litter_id>` now returns/displays birth date, estimated wean date, wean/tag attention start date, planning Monday, days until estimated wean, default wean age, and attention window.
  - Dashboard litter attention suppresses early tag-number reminders until the attention window, while still allowing data-quality/reconciliation reasons to show.
  - Real-data check on 2026-06-04 for `LIT-2026-9E4A`: birth date `2026-05-18`, estimated wean date `2026-06-22`, attention start `2026-06-19`, days until wean `18`, and dashboard attention returned clean.
  - Verification passed: `node --check static/js/litterDetail.js`, focused litter/dashboard/frontend tests, route smoke for `/litter/LIT-2026-9E4A`, and full local unittest suite at 336 tests.
  - Owner deployed and confirmed the feature is working on 2026-06-04.

9.7H fast pre-weaning piglet death capture - In Progress:

- Problem found during mating-to-litter live use: adding a litter with `total born = 9`, `born alive = 7`, and `stillborn = 2` created too many live piglet rows. Stillborn piglets should be logged as dead/off-farm on date of birth, not require later manual death edits.
- Required correction for Add Litter:
  - Owner decision 2026-06-03: keep dead pig rows for history.
  - Stillborn rows must be created as `Dead` / `On_Farm = No` with exit/death date equal to birth date and reason `Stillborn`.
  - Born-alive rows should remain active/on-farm unless later marked dead or removed.
  - Local correction is implemented: Add Litter now creates active/on-farm rows from `born_alive`, creates stillborn rows as dead/off-farm history rows, and keeps stillborn/death reasons in lifecycle outcome counts as `dead`.
  - Verification passed on 2026-06-04: focused litter service tests and full local unittest suite at 337 tests.
- Required litter detail action:
  - Add a fast `Mark Piglets Dead` action on `/litter/<litter_id>` for pre-weaning cases.
  - Before sex/tag data exists, allow count + date + reason and select from active untagged/unsexed piglets.
  - If sex is available but tags are not, ask for male/female counts so the update can choose matching piglets.
  - Once tag numbers exist, require selecting specific piglets or using the individual pig lifecycle form.
  - Reason options should include `Stillborn`, `Died after birth`, `Crushed by sow`, `Weak piglet`, and `Unknown`.
  - Update `PIG_MASTER` status/on-farm/exit fields and preserve litter/parent history.
  - Keep this as dry-run-first or preview-before-apply.
- Local implementation details:
  - Added `POST /api/pig-weights/litter/<litter_id>/piglet-deaths`.
  - Added a litter detail side-panel `Piglet Death Capture` form with event date, reason, count, optional male/female counts, recorded-by, notes, preview, and save.
  - Dry-run preview selects active/on-farm piglets only and shows exactly which rows will be updated.
  - If no pig IDs are supplied, untagged/unsexed piglets can be selected by count.
  - If sex exists, the action requires male/female counts.
  - If tag numbers exist, the backend blocks count-based updates until a future specific-pig selection UI or the individual pig lifecycle form is used.
  - Apply updates `PIG_MASTER.Status = Dead`, `On_Farm = No`, `Exit_Date`, `Exit_Reason`, `General_Notes`, and `Updated_At`.
  - Verification passed on 2026-06-04: `node --check static/js/litterDetail.js`, focused litter/frontend tests at 38 tests, local route smoke for the new endpoint, and full local unittest suite at 340 tests.

9.7H2 litter print/capture sheet alignment - Planned after owner sample:

- Owner note 2026-06-03: father has a specific paper capture format for litters, and the system should eventually match that printout style more closely.
- Future build should align the litter print sheet, litter detail table, and any bulk litter upload/capture form so the printed workflow and web workflow feel like the same process.
- Owner note 2026-06-10: after a litter is captured and the piglet rows exist, the owner needs an editable table-style workflow to enter tag numbers, weaned weights, and current/target pens for the whole litter in one pass instead of opening every piglet individually.
- Planned direction:
  - Add a litter-level bulk capture/edit table from `/litter/<litter_id>`.
  - Keep it preview-before-save, with one deliberate `Save Batch` action.
  - Support spreadsheet-like entry for tag number, weaned weight, and pen fields.
  - Validate duplicate tag numbers, existing same-date weights, and invalid pens before commit.
  - Preserve individual pig rows and audit history; do not overwrite existing tag/weight/pen data silently.
  - Reuse the existing bulk-weight partial-save behavior where practical so valid rows can save while duplicate/invalid rows stay visible for correction.
- Owner will provide a sample before implementation.
- Keep wide browser layouts and table format as the default for these operational pages.

9.7J litter sex-count capture from attention detail - Local Ready:

- Owner request 2026-06-08: on `/litter/LIT-2026-EB92`, add an attention-detail action to enter how many active piglets are male and female, similar to piglet death capture, so the linked pig rows get `Sex` filled once the farm has the real counts.
- Added backend service `record_litter_piglet_sex_counts()`.
- Added `POST /api/pig-weights/litter/<litter_id>/sex-counts`.
- The action is preview-before-save and only fills active/on-farm piglets whose `Sex` is still blank. It does not overwrite existing sex values.
- If male + female counts exceed blank-sex active piglets, the backend blocks with a clear error and writes nothing.
- `/litter/<litter_id>` now shows a `Sex Count Capture` side panel when active piglets still have blank sex, with action date, male count, female count, recorded-by, notes, preview, and save.
- Applying the action updates `PIG_MASTER.Sex`, `Updated_At`, and `General_Notes`; it writes to Google Sheets only after preview and explicit confirmation, and writes nothing to Supabase.
- Local verification passed: `node --check static/js/litterDetail.js`, focused litter/frontend tests, and focused bulk/report/litter/frontend test suite.
- First owner browser check passed on 2026-06-08: `LIT-2026-6EC0` and `LIT-2026-1025` received male/female counts and first medical records through the litter action flow.

9.7I smart return/back navigation - Deployed/working:

- Problem found during litter table use: opening a pig from a litter works, but the pig profile only links back to Pig List, not the litter/page the user came from.
- Preferred direction:
  - Add a lightweight return-context system for internal links, for example query parameters or session/local storage.
  - When navigating from a litter to a pig, show `Back to Litter` on the pig detail page.
  - Keep normal `Back to Pig List` available when the user came from the pig list.
  - Avoid browser-history-only behavior as the only solution, because direct links and refreshed pages should still show sensible actions.
  - Apply the same pattern later to sales, reports, matings, and dashboards where drill-ins are used.
- Implementation details:
  - Litter piglet table links now include `return_to=/litter/<litter_id>` and `return_label=Back to Litter`.
  - Pig detail header link now reads safe internal return context and changes the main back action to `Back to Litter` when opened from a litter.
  - Unsafe return paths are ignored so the link cannot become an external redirect.
  - Verification passed on 2026-06-04: `node --check static/js/litterDetail.js`, `node --check static/js/pigDetail.js`, frontend route contract tests, and full local unittest suite at 340 tests.
  - Owner deployed and tested the litter-to-pig `Back to Litter` path; it is working.
  - Owner confirmed the next deployed slice is working on 2026-06-04: `/litter/<litter_id>` header link goes back to Dashboard by default, and pig profile child links pass `Back to Pig Profile` return context into weight capture, weight history, treatment, treatment history, movement, movement history, and family tree.
  - Second sweep deployed and owner browser-checked as working on 2026-06-04: sales dashboard rows pass `Back to Sales Dashboard`; slaughter sale ledger rows pass `Back to Slaughter Sales`; sale detail reads safe return context with sensible fallback; breeding analytics drill-ins pass `Back to Analytics`; breeding detail litter links pass `Back to Breeding Detail`; and breeding board pig/litter links pass `Back to Breeding Board`.
  - Verification passed on 2026-06-04 for the second sweep: `node --check` on all touched JS files, frontend route contract tests, and full local unittest suite at 341 tests.
  - Remaining follow-up note: after browser acceptance, walk through reports and any remaining dashboard/list/detail paths that do not start from these pages.

### 9.8 Business Scenario Calculator — Future Planning

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
7. **10.6 Oom Sakkie operating agent** - plan and build the conversational farm operator as a backend-owned orchestrator, not a direct-write chatbot. PRD added at `docs/01-architecture/OOM_SAKKIE_VOICE_OPERATING_AGENT_PRD.md`.

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
- Pig `S10` was reported on 2026-05-21 as recently slaughtered and marked as slaughtered in Google Sheets. It later became the first real JC Slaghuis slaughter/payment close-out verification after the Supabase create/cancel flow was proven.
- VAT handling is now an explicit planning point: before dashboard financial reporting, decide/add structured VAT fields rather than hiding VAT permanently in notes.
- Phase 10.2K1 backend create service implemented locally: `POST /api/sales-transactions` supports `Slaughter` only, requires `created_by`, writes Supabase header/items atomically, blocks duplicate pig IDs, and writes nothing to Google Sheets.
- Local verification passed on 2026-05-21: focused sales transaction tests passed at 15 tests, local missing-config route smoke returned safe `503`, and full local unittest suite passed at 184 tests.
- Phase 10.2K1/10.2K2 deployed verification passed on 2026-05-21: synthetic transaction `SALE-2026-F17E16` was created for `PIG-TEST-102K2-20260521`, read back through `GET /api/sales-transactions`, and duplicate-pig protection returned `409 duplicate_pig` on a second create attempt.
- The synthetic test row remains in Supabase as a clear test transaction. It is not linked to a real pig/order.
- At the 10.2K1/10.2K2 checkpoint, no real `S10` transaction had been written; this changed later after the create/cancel/payment path was proven.
- Phase 10.2K3 cancellation/void flow implemented locally: `POST /api/sales-transactions/<sale_id>/cancel` requires `cancelled_by` and `cancel_reason`, marks `sale_status = Cancelled`, sets `payment_status = Cancelled`, appends an audit note, and never hard-deletes rows.
- Local verification passed on 2026-05-21: focused sales transaction tests passed at 20 tests, local missing-config cancel route smoke returned safe `503`, and full local unittest suite passed at 191 tests.
- Phase 10.2K3 deployed verification passed on 2026-05-21: synthetic transaction `SALE-2026-F17E16` was cancelled, duplicate release was proven by creating `SALE-2026-28EF1B` with the same synthetic pig ID, and the second synthetic transaction was also cancelled.
- Final readback shows both synthetic slaughter transactions are cancelled.
- At the 10.2K3 checkpoint, no real `S10` transaction had been written; this changed later after the form/payment path was proven.
- Phase 10.2L internal slaughter sale form implemented locally at `/sales/slaughter`.
- The form defaults to `JC Slaghuis`, `Bartelsfontein`, `Unpaid`, `Confirmed`, and `EFT`; it loads active pigs, creates slaughter transactions, shows recent slaughter transactions, and can cancel non-cancelled transaction rows.
- Local verification passed on 2026-05-21: `node --check static/js/slaughterSale.js`, focused frontend/sales tests passed at 27 tests, local page smoke returned `200`, and full local unittest suite passed at 192 tests.
- Phase 10.2L2 payment/final amount update implemented locally: `PATCH /api/sales-transactions/<sale_id>/payment` updates a non-cancelled slaughter transaction amount, payment status, sale status, payment method, optional carcass weight, and appends an audit note.
- `/sales/slaughter` now has an `Update Payment` action for non-cancelled rows.
- Local verification passed on 2026-05-21: `node --check static/js/slaughterSale.js`, focused sales/frontend tests passed at 23 tests, local missing-config update route smoke returned safe `503`, and full local unittest suite passed at 200 tests.
- 10.2L2 real-value test was parked by owner decision on 2026-05-21 until the real JC Slaghuis sale value was known.
- This follow-up was completed and verified on 2026-05-23 after the owner entered the actual payment/final amount.
- Next step: continue with the selected Phase 10 telemetry/irrigation slices.
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
- S10 / real JC Slaghuis payment completion was completed and verified on 2026-05-23. Sale `SALE-2026-1DE373` is `Completed` and `Paid`, final amount `R2892.94`, payment date `2026-05-23`, carcass weight `68 kg`, pig `PIG-2026-C390` / tag `S10`, buyer `JC Slaghuis`, destination `Bartelsfontein`. Focused sales transaction tests passed at 35 tests. This follow-up is closed for now.
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
- Recommendation captured: keep raw 5-minute data only for a short tested retention window first, keep daily/monthly/yearly rollups long-term, and do not delete raw data or old telemetry Sheets until Supabase import, rollup jobs, backup/export, and comparison checks are proven.
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
- First deployed check returned `success = true` with 24 rows and all expected sections, but the 24-hour window still included the old synthetic test row (`82%`, `3120 W`) because that row had no real cron raw payload.
- Follow-up local patch excludes rows where `raw_payload is null` from `/api/telemetry/power/recent`, so synthetic/manual test rows do not skew real trend answers.
- Focused telemetry/workflow tests still pass at 11 tests after the exclusion patch.
- 10.3H deployed verification passed after the exclusion patch: `/api/telemetry/power/recent?hours=24` returned `success = true`, 24 real cron rows, first reading `2026-05-21T22:28:20+00:00`, last reading `2026-05-22T00:20:21+00:00`, battery range `42%` to `47%`, average load `0.9 kW`, maximum solar `0.0 kW`, and no grid/generator activity.
- The synthetic `82%` / `3120 W` row is no longer present in the live response.
- 10.3I local workflow update prepared on 2026-05-22:
  - `2.2 - Amadeus Sunsynk Sub-Agent` now routes current/live questions to `/api/telemetry/power/current`.
  - It routes recent, last-24h, overnight, and trend questions to `/api/telemetry/power/recent?hours=24`.
  - kWh, cost, import, and export total questions are answered with the sample-based recent profile plus a clear limitation, not guessed totals.
  - `2.0 - OOM SAKKIE` `Sunsynk_Info_Tool` description now tells the main assistant that current state and sample-based recent profiles are supported.
- 10.3I live verification passed on 2026-05-22 after importing updated `2.2` and `2.0`:
  - `What's the power like now?` returned current backend/Supabase data with battery `41%`, load `0.8 kW`, no solar, no grid, no generator, and latest reading age `0 minutes`.
  - `What happened with the power in the last 24 hours?` returned a sample-based recent profile with 34/288 readings, battery range `41%` to `47%`, average load `0.9 kW`, no solar, and no grid/generator use.
  - `Did we use grid power last night?` correctly reported about `0 minutes` of grid use from `0` samples.
  - `How much solar did we make today?` did not invent kWh and included the limitation that kWh, cost, import, and export totals are not confirmed yet.
  - Minor polish note: the recent profile can repeat the sample-based limitation because backend operator notes and workflow formatting both include it. This is harmless and can be cleaned up in a later wording polish pass.
- Next step: park Sunsynk for now and move to weather/forecast Supabase/backend alignment.
- 10.3J weather/forecast alignment started on 2026-05-22:
  - Current `2.1 - Amadeus Weather Sub-Agent` is sheet-backed and uses two LLM calls: router JSON plan and answer JSON.
  - `2.1` reads `LLM_Latest_Reading`, `Forecast_10Day_Current`, and `Daily_Pivot`.
  - `2.1.1 - Amadeus Forecast Tool` calls Open-Meteo directly but is not currently the normal Oom Sakkie weather path.
  - Weather and forecast Render cron logger source folders are present under `external_sources/telemetry/`.
  - Proposed sequence is now documented in `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`: contract first, then schema, ingest endpoints, logger update, read endpoints, and only then `2.1` workflow simplification.
- 10.3J1 weather/forecast read-model contract drafted on 2026-05-22:
  - First build should include `/api/telemetry/weather/current` and `/api/telemetry/weather/forecast?days=3`.
  - `/api/telemetry/weather/today` is planned as a follow-up unless it is very low-risk to include after current/forecast are proven.
  - Contracts define success/unavailable payloads, units, source freshness, deterministic flags, and summary wording rules.
  - Google Sheets mirror writes should remain during the transition.
  - Do not edit/import `2.1` until backend endpoints are deployed and direct endpoint tests pass.
- 10.3J2 local implementation prepared on 2026-05-22:
  - Added migration `supabase/migrations/202605220001_create_telemetry_weather_tables.sql`.
  - Added source rows for `weather-station-main` and `open-meteo-forecast-main`.
  - Added tables `weather_readings`, `weather_latest_state`, and `weather_forecast_snapshots`.
  - Added backend service `modules/telemetry/weather_service.py`.
  - Added read endpoints:
    - `GET /api/telemetry/weather/current`
    - `GET /api/telemetry/weather/forecast?days=3`
  - Added protected ingest endpoints:
    - `POST /api/telemetry/weather/ingest`
    - `POST /api/telemetry/weather/forecast/ingest`
  - Added health endpoint `/health/database/telemetry-weather-schema`.
  - Added focused unit tests for weather ingest, forecast ingest, current read, forecast read, route registration, and migration safety.
  - No n8n workflow changes were made.
- 10.3J2 validation update on 2026-05-22:
  - Syntax compile passed for the weather service, telemetry routes, database service, and app wiring.
  - Focused weather/database tests passed, then broader telemetry/database/workflow tests passed at 53 tests.
  - Migration `202605220001_create_telemetry_weather_tables` was applied directly to Supabase from the local workspace.
  - Supabase schema health verified `success = true`, `missing_tables = []`, and sources `weather-station-main` and `open-meteo-forecast-main` were present.
  - Direct local Supabase read checks returned clean unavailable responses before logger ingest for current weather and forecast.
  - Synthetic local ingest is blocked until `TELEMETRY_INGEST_API_KEY` is added to the local `.env`; Render already has the key for deployed endpoint testing.
- 10.3J2 deployed read verification on 2026-05-22:
  - `/health/database/telemetry-weather-schema` returned `success = true`, `status = ok`, no missing tables, and both weather/forecast telemetry sources.
  - `/api/telemetry/weather/current` returned a clean unavailable response before logger ingest.
  - `/api/telemetry/weather/forecast?days=3` returned a clean unavailable response before forecast ingest.
  - Synthetic deployed ingest returned `401 unauthorized` with the available test key, so the backend is enforcing auth but the current Render `TELEMETRY_INGEST_API_KEY` value must be confirmed before readback can be completed.
- 10.3J2 synthetic deployed ingest/readback passed on 2026-05-22:
  - `POST /api/telemetry/weather/ingest` accepted the current ingest key and wrote reading `WTH-5D66D385B9F5`.
  - `/api/telemetry/weather/current` read back `success = true`, temperature `14.2 C`, humidity `86%`, wind `5.4 km/h`, rain today `0.4 mm`, and source `weather-station-main`.
  - `POST /api/telemetry/weather/forecast/ingest` wrote 3 forecast rows.
  - `/api/telemetry/weather/forecast?days=3` read back `success = true`, `returned_days = 3`, rain expected on 2 days, and source `open-meteo-forecast-main`.
  - Current Supabase weather/forecast values are synthetic test values until the real weather and forecast loggers overwrite them.
- 10.3J3 local logger update prepared on 2026-05-22:
  - First owner weather cron run still showed the old Sheets-only output, so the logger code needed the backend-post step.
  - Weather logger now posts normalized current readings to `POST /api/telemetry/weather/ingest` when `BACKEND_INGEST_ENABLED=true`.
  - Forecast logger now posts normalized forecast snapshots to `POST /api/telemetry/weather/forecast/ingest` when `BACKEND_INGEST_ENABLED=true`.
  - Both loggers keep Google Sheets mirror writes enabled through `GOOGLE_SHEETS_ENABLED=true`.
  - Both loggers print JSON results with `backend_ingest_success`, `google_sheets_written`, and any backend/sheet errors for Render log checking.
- 10.3J3 logger verification passed on 2026-05-22:
  - Weather and forecast Render cron services were updated to point at the pig-tracking repo paths and ran successfully.
  - `/api/telemetry/weather/current` read back fresh real station data: temperature `14 C`, humidity `96%`, wind `8 km/h`, rain today `0 mm`, data age `0`, source `weather-station-main`.
  - `/api/telemetry/weather/forecast?days=3` read back fresh real Open-Meteo forecast data: 3 returned days, rain possible on 1 day, data age `0`, source `open-meteo-forecast-main`.
  - Real logger data has overwritten the synthetic test values in Supabase.
- 10.3J4 local workflow simplification prepared on 2026-05-22:
  - `2.1 - Amadeus Weather Sub-Agent` now routes weather questions deterministically and reads only backend endpoints.
  - Current/now questions call `/api/telemetry/weather/current`.
  - Forecast/tomorrow/coming-weather questions call `/api/telemetry/weather/forecast?days=3`.
  - Old Google Sheets and LLM nodes are intentionally removed from `2.1`.
  - `2.0 - OOM SAKKIE` `Weather_Info_Tool` description now describes the backend/Supabase weather worker.
  - Workflow contract tests pass at 15 tests.
- 10.3J4 live verification passed on 2026-05-22 after importing updated `2.1` and `2.0`:
  - `What is the weather like now?` returned current backend weather: temperature `14 C`, humidity `96%`, wind `4 km/h`, gusts `4 km/h`, rain now `0 mm/h`, rain today `0 mm`, pressure `1013.9 hPa`, and latest reading age `0 minutes`.
  - `What is the weather forecast for the next few days?` returned the 3-day backend forecast for 22-24 May 2026, with rain possible on 1 day and forecast age `1 minute`.
  - Answers did not mention tools, workflows, Google Sheets, or Supabase.
- Owner selected the next telemetry order: 1) weather `today`/daily summary, 2) weather alert alignment, 3) irrigation/audit planning.
- 10.3K local weather today endpoint prepared on 2026-05-22:
  - Added `GET /api/telemetry/weather/today` with optional `date=YYYY-MM-DD`.
  - Endpoint summarizes existing Supabase `weather_readings` by local farm day.
  - It reports reading count, coverage estimate, first/last reading, min/max/average temperature, average humidity, max wind/gust, rain total, max rain rate, flags, summary notes, and limitations.
  - It excludes synthetic test rows via `raw_payload.test = true` protection.
  - Local live Supabase readback returned real-only data for 2026-05-22: 5 readings, coverage `8.1%`, temperature `14 C`, rain total `0 mm`, and max wind `9 km/h`.
  - Broader telemetry/database/workflow tests pass at 55 tests.
- 10.3K deployed verification passed on 2026-05-22:
  - `/api/telemetry/weather/today` returned `success = true`, 25 real readings, coverage `30.5%`, temperature range `14 C` to `15 C`, average temperature `14.24 C`, rain total `0 mm`, max wind `9 km/h`, and max gust `10 km/h`.
  - `/api/telemetry/weather/today?date=2026-05-22` returned the same result.
  - The old synthetic `0.4 mm` rain row was excluded.
- 10.3K `2.1` local routing update prepared on 2026-05-22:
  - Today/daily/rain-today weather questions now route to `/api/telemetry/weather/today`.
  - Current weather and forecast routes remain unchanged.
  - Workflow/weather tests pass at 26 tests.
- First live Telegram check still returned the current-weather answer, so the local workflow update was hardened:
  - `2.0` now passes the exact Telegram message into `2.1` before the AI-generated weather-question fallback.
  - `2.1` now checks additional possible input fields and has a stronger `what happened ... today` matcher.
- 10.3K live verification passed on 2026-05-22 after importing the hardened `2.0` and `2.1` workflows:
  - `What happened with the weather today?` returned the today-summary branch.
  - Result included 30 readings, 34.5% coverage, temperature `14 C` to `15 C`, average `14.4 C`, average humidity `94.6%`, rain total `0 mm`, max rain rate `0 mm/h`, max wind `9 km/h`, max gust `10 km/h`, and measurement window `22 May 2026, 04:49` to `07:10`.
- 10.3L weather alert alignment planned on 2026-05-22:
  - Owner agreed to use the backend/Supabase approach rather than Sheets-first alert workflows.
  - Existing `ALERT - Local Weather Station` and `ALERT - Weather Forecast` remain documented but should not become the source of truth.
  - Backend should own alert rules, cooldowns, duplicate prevention, and alert history in `telemetry_alerts`.
  - n8n should later become a thin scheduled caller and Telegram delivery layer.
  - Proposed backend endpoint: `POST /api/telemetry/weather/alerts/evaluate`.
  - Optional read endpoint: `GET /api/telemetry/weather/alerts/recent?hours=24`.
  - First rule group: station stale, raining now, rain today, heavy rain now, sustained wind, high gust, low/high temperature, forecast rain, forecast heavy rain, forecast wind, forecast strong wind.
  - First safe recipient: Charl only.
  - Default quiet hours: `21:00` to `06:00` Africa/Johannesburg.
  - `HIGH` current-condition alerts may send during quiet hours; normal `MED` and `INFO` planning alerts should wait until quiet hours end.
  - Repeated unresolved alerts resend only after cooldown, or sooner only if severity increases or values worsen materially.
  - Detailed plan lives in `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`.
- 10.3L2 backend evaluator implemented locally on 2026-05-22:
  - Added protected `POST /api/telemetry/weather/alerts/evaluate`.
  - Uses the existing telemetry ingest key.
  - Supports `{"dry_run": true}` for safe no-write tests.
  - Reads `weather_latest_state`, recent `weather_readings`, latest `weather_forecast_snapshots`, and recent `telemetry_alerts`.
  - Applies backend-owned rule, cooldown, and quiet-hours policy.
  - Returns `sendable_alerts`, `held_alerts`, and `suppressed_alerts`.
  - Writes only sendable alerts in apply mode; does not send Telegram messages.
  - Focused weather tests pass at 13 tests; telemetry/database/workflow suite passes at 57 tests.
  - Real Supabase dry-run returned `success = true`, `mode = dry_run`, and zero current alert candidates under normal weather conditions.
- 10.3L2 deployed dry-run verification passed on 2026-05-22:
  - Production `POST /api/telemetry/weather/alerts/evaluate` with `{"dry_run": true}` returned `success = true`, `status = ok`, `mode = dry_run`.
  - It returned zero candidates, zero sendable/held/suppressed alerts, quiet hours inactive, and `writes_to_supabase = false`.
- 10.3L2 backend audit test path prepared locally:
  - `POST /api/telemetry/weather/alerts/evaluate` supports `{"include_test_alert": true}`.
  - Dry-run can inspect a `BACKEND_AUDIT_TEST` candidate without writing.
  - Apply mode writes one clearly marked `BACKEND_AUDIT_TEST` row to `telemetry_alerts`.
  - The message states no Telegram message was sent.
  - n8n must not deliver `BACKEND_AUDIT_TEST`.
  - Focused weather tests pass at 14 tests.
- 10.3L2 backend audit apply verification passed on 2026-05-22:
  - Production audit dry-run with `{"dry_run": true, "include_test_alert": true}` returned one `BACKEND_AUDIT_TEST` candidate and `writes_to_supabase = false`.
  - Production audit apply with `{"include_test_alert": true}` wrote alert `ALT-F20D2245949B`.
  - Supabase verification confirmed the row exists with `area = weather`, `alert_type = BACKEND_AUDIT_TEST`, `severity = info`, `status = Open`, `details.test = true`, and `details.safe_to_ignore = true`.
  - No Telegram message was sent.
- 10.3L4 n8n weather alert delivery planned on 2026-05-22:
  - Build a new thin workflow named `ALERT - Weather Backend Delivery`.
  - Do not edit/reactivate the old Sheets-first alert workflows.
  - Backend evaluator remains the source of truth for thresholds, cooldowns, quiet hours, alert history, and duplicate prevention.
  - n8n only calls backend, filters sendable alerts, formats Telegram messages, and sends them.
  - First recipient scope is Charl only.
  - `BACKEND_AUDIT_TEST` and any `details.test = true` alert must never be delivered.
  - Manual tests must prove dry-run and audit-test responses send no Telegram messages.
  - Detailed plan lives in `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`.
- 10.3L4 local workflow export built on 2026-05-22:
  - Export: `docs/04-n8n/workflows/ALERT - Weather Backend Delivery/workflow.json`
  - README: `docs/04-n8n/workflows/ALERT - Weather Backend Delivery/README.md`
  - Workflow is inactive by default.
  - It calls `POST /api/telemetry/weather/alerts/evaluate`.
  - n8n Cloud denied `$env` access in the HTTP node, so the workflow uses a manually configured `X-Amadeus-Telemetry-Key` header value matching Render's `TELEMETRY_INGEST_API_KEY`.
  - It filters out dry-run responses, `BACKEND_AUDIT_TEST`, and any alert where `details.test = true`.
  - It sends through `Telegram - Oom Sakkie` to Charl-only chat ID `5721652188`.
  - Workflow contract tests pass at 16 tests.
- 10.3L4 manual n8n verification passed on 2026-05-23:
  - Manual dry-run with `include_test_alert = true` returned one backend audit candidate.
  - `Code - Extract Sendable Alerts` correctly output zero items because `mode = dry_run`.
  - No Telegram delivery occurred.
  - Workflow was reset to `dryRun = true` and `includeTestAlert = false`.
  - Workflow was activated for a scheduled dry-run trial every 15 minutes.
- 10.3L4 scheduled dry-run verification passed on 2026-05-23:
  - Execution `47520` ran from the schedule with `mode = trigger`.
  - `Code - Build Evaluate Request` sent `{"dry_run": true}`.
  - `HTTP - Evaluate Weather Alerts` returned `success = true`, `status = ok`, `mode = dry_run`, `candidate_count = 0`, `sendable_count = 0`, `held_count = 0`, and `suppressed_count = 0`.
  - `Code - Extract Sendable Alerts` output zero items, so Telegram delivery was not reached.
- 10.3L4 live scheduled verification passed on 2026-05-23:
  - Workflow was active with `dryRun = false` and `includeTestAlert = false`.
  - Execution `47527` ran from the schedule with `mode = trigger`.
  - `Code - Build Evaluate Request` sent an empty body `{}` and `workflow_mode = apply`.
  - `HTTP - Evaluate Weather Alerts` returned `success = true`, `status = ok`, `mode = apply`, `candidate_count = 0`, `sendable_count = 0`, `held_count = 0`, `suppressed_count = 0`, `source.writes_to_supabase = true`, and `written_alert_ids = []`.
  - `Code - Extract Sendable Alerts` output zero items, so Telegram delivery was not reached because there were no real alerts.
- Legacy weather alert cleanup completed on 2026-05-23:
  - `ALERT - Local Weather Station` is inactive/archived in n8n and its repo export has been removed.
  - `ALERT - Weather Forecast` is inactive/archived in n8n and its repo export has been removed.
  - `ALERT - Weather Backend Delivery` remains active and is the only live weather alert delivery workflow.
- 10.3M planning notes captured from owner on 2026-05-23:
  - Future Sunsynk value reporting should use the farm Eskom reference rate of `R9.10/kWh` unless a later tariff model replaces it.
  - Do not show Rand/kWh totals until reliable Sunsynk energy counters or approved interval-integration rules are in place.
  - n8n should remain for now as a thin integration layer for Telegram, Chatwoot, schedules, and delivery; backend/Supabase should own truth, calculations, state, and safety rules.
  - Human alerts and automation triggers must be separated. Rain, wind, heat, battery, and pump conditions may notify humans, but irrigation/pump actions need separate backend-owned trigger/audit policies.
  - Owner note 2026-05-26: future alert, notification, and update delivery should support additional Telegram recipients besides Charl. Plan recipient configuration deliberately with authorization, severity/area subscriptions, quiet-hours behavior, and test/audit filtering before broadening delivery.
- 10.3N Sunsynk/power alert backend alignment prepared locally on 2026-05-23:
  - Added protected backend endpoint `POST /api/telemetry/power/alerts/evaluate`.
  - Backend evaluates current power alert candidates from `power_latest_state`, `telemetry_sources`, and recent `telemetry_alerts`.
  - Backend-owned rules cover not logging, battery low/medium/high, grid active, generator active, and a `POWER_BACKEND_AUDIT_TEST` path.
  - Backend applies cooldown and quiet-hours policy and writes only sendable alerts in apply mode.
  - Added workflow export `docs/04-n8n/workflows/ALERT - Power Backend Delivery/workflow.json`.
  - New workflow started dry-run by default, calls `/api/telemetry/power/alerts/evaluate`, filters out dry-run/test/audit alerts, and sends through `Telegram - Oom Sakkie` only when real sendable alerts exist.
  - `ALERT - Sunsynk` has been removed after the backend-driven replacement was imported, dry-run tested, live-tested, and accepted.
  - Focused power telemetry tests and workflow contract tests pass.
- 2026-05-23 backend and n8n dry-run checks passed:
  - Direct backend dry-run returned `success = true`, `mode = dry_run`, two real candidates, one sendable battery-low alert, one quiet-hours-held grid-active alert, and no Supabase writes.
  - Direct backend audit dry-run returned `POWER_BACKEND_AUDIT_TEST` as a test candidate with no writes.
  - Manual n8n dry-run execution returned the real candidates but `Code - Extract Sendable Alerts` emitted zero items because workflow mode was still `dry_run`; no Telegram message was sent.
  - Manual n8n audit dry-run execution returned `POWER_BATTERY_LOW` plus `POWER_BACKEND_AUDIT_TEST`, but the extract node emitted zero items because dry-run/test alerts are blocked; no Telegram message was sent.
- 2026-05-23 live n8n execution `47565` passed:
  - Workflow ran in `apply` mode with two backend candidates.
  - `POWER_BATTERY_LOW` was sendable, written to Supabase as `ALT-C758569F3D95`, extracted, formatted, and sent through Telegram successfully.
  - `POWER_GRID_ACTIVE` was correctly held during quiet hours.
  - Supabase verification found `ALT-C758569F3D95` in `telemetry_alerts` with status `Open`.
  - Owner made `ALERT - Power Backend Delivery` live and removed the old `ALERT - Sunsynk` workflow from n8n.
  - Repo cleanup removed `docs/04-n8n/workflows/ALERT - Sunsynk/` so the legacy export does not get reintroduced by mistake.
- Next step: continue with the next telemetry/backend slice.

### 10.3O Irrigation Inventory And Control Boundary - Planned

Selected after weather and power alerts were moved onto backend/Supabase delivery.

Goal:

- Understand the current irrigation workflows and design the safety/audit boundary before any valve-control changes.
- Keep this phase planning/inventory only until the owner explicitly approves a later build phase.

Current workflow inventory:

- `2.3.1 - Build Daily Irrigation Plan`
  - Export status: active.
  - Runs daily at `00:05`.
  - Reads `ZONES`, `RULES`, and `Forecast_24hr_Current`.
  - Writes `DAILY_PLAN`, `STATE`, and `LOG` in `Amadeus_Irrigation_Logs`.
  - This is planning/state automation, not direct hardware control.
- `2.3.2 - Run Irrigation Controller`
  - Export status: inactive.
  - Reads `STATE`, `RULES`, `LLM_Latest_Reading`, `ZONES`, and `DAILY_PLAN`.
  - Contains direct IFTTT start/stop HTTP nodes.
  - Can control real irrigation hardware if activated.

Hard guardrails:

- Do not activate `2.3.2`.
- Do not edit IFTTT start/stop nodes.
- Do not add Oom Sakkie commands that start/stop irrigation.
- Do not move secrets or change live credentials until a specific credential migration plan is approved.
- Do not create backend hardware-control endpoints until the audit model and safety locks are agreed.

Recommended design direction:

- Backend/Supabase should own irrigation command requests, safety checks, cooldowns, manual overrides, audit rows, and final action status.
- n8n should eventually become a thin scheduler/delivery layer, not the permanent owner of valve-control decisions.
- Weather and power can provide advisory gates, but automatic irrigation/pump changes must be separate from human alerts.

Owner answers captured on 2026-05-23:

- Both currently loaded zones are safe to run automatically. They already run from the controller's own app on automatic timers; this is why `2.3.2` has stayed inactive.
- Approval needs clarification: this can mean either a person approving an action or a system rule authorizing it. For safety planning, treat this as two layers:
  - **System approval:** backend checks zone rules, season runtime, priority, allowed windows, weather, power, cooldown, and lockouts.
  - **Human approval:** owner/operator approval for manual override, first live tests, emergency restart, or any unusual action.
- Maximum runtime is not a single fixed value. It depends on the zone configuration, what is planted, season, priority, and the existing `summer_minutes` / `winter_minutes` style zone fields.
- Weather and power should eventually drive adaptive actions:
  - forecast helps build the daily plan;
  - current weather can pause, update, skip, or reschedule the active plan;
  - rain should pause irrigation and then trigger a later evaluation/reschedule;
  - high heat may allow drip irrigation but not sprinklers;
  - wind should block or delay sprinkler zones above the agreed threshold;
  - skipped zones should gain priority compared with zones that already received water;
  - low battery or poor power state should be able to hold non-critical irrigation/pump actions.
- Emergency stop options:
  - manual shutoff outside the system remains required;
  - original controller app can still stop the irrigation;
  - future Oom Sakkie stop command may be allowed only after strong confirmation and backend audit;
  - system-triggered stop should prefer shutting down safely when there is uncertainty.
- First backend slice should be read-only status first. Operational control comes later after the status path is trusted.

Long-term smart irrigation target:

- The system should use zone setup, crop/planting data, season runtime, priority, forecast, current weather, and power state to build and adapt the irrigation plan.
- The system should inform the owner what is running, how long it will run, what the day plan is, when a plan changes, when irrigation stops, and when a zone changes.
- A future web page should allow zones to be added and edited so the plan builder has clean inputs.
- Treat irrigation as a core farm operating system, not a small helper workflow. Later phases will add more devices, sensors, and trigger rules, so the model must be extensible from the start.

Fertilizer and tank-control notes captured on 2026-05-23:

- There are two additional valves that behave differently from normal irrigation zones.
- Fertilizer injection valve:
  - used to add fertilizer into the water system;
  - should run while irrigation is running;
  - expected behavior is about `1 minute` every `30 minutes` per valve-open window;
  - should be modeled differently from a normal irrigation zone because it is an auxiliary action tied to another active zone/run.
- Fertilizer mixing valve:
  - used to mix fertilizer tanks;
  - expected behavior is daily at a set time for about `30 minutes`;
  - should be modeled as a scheduled support task, not as a crop irrigation zone.
- Future tank triggers are expected:
  - tank full;
  - tank empty;
  - possibly other sensor states later.
- These tank states should become structured sensor inputs/events so irrigation and fertilizer logic can use them safely.

Remaining follow-up decisions:

- Confirm exact zone names/IDs that are currently loaded and safe.
- Confirm who can approve manual override actions.
- Confirm sprinkler wind threshold and heat threshold.
- Confirm low-battery threshold for holding irrigation/pumps.
- Confirm what fields are missing from the current `ZONES` sheet for crop/planting needs.
- Confirm whether the first web/backend build should expose read-only status from Sheets first, or migrate irrigation zone/plan/state data to Supabase first.
- Confirm whether fertilizer injection should pause when irrigation pauses, and whether it should restart/resume with the active irrigation zone.
- Confirm whether fertilizer mixing can run independently of irrigation and what should block it, for example tank empty, low battery, or manual lockout.
- Confirm first expected tank sensor types and how they are currently detected.

### 10.3P Irrigation Read-Only Status Endpoint - Proposed Next Slice

Purpose:

- Give Oom Sakkie, the future dashboard, and the owner a safe irrigation status view before any control work.
- Read current irrigation state and today's plan without changing plans, valves, IFTTT, or controller state.

Proposed backend endpoint:

- `GET /api/telemetry/irrigation/status`

Read-only sources:

- `Amadeus_Irrigation_Logs`
- `STATE`
- `DAILY_PLAN`
- `ZONES`
- `RULES`
- recent `LOG`
- later: backend weather current/forecast and power current as advisory context

Source-of-truth note:

- Supabase remains the target source of truth for irrigation.
- Reading the existing Google Sheet is only a temporary bridge for the first read-only status endpoint.
- Zone editing, adaptive planning, fertilizer logic, tank sensors, and hardware-control actions should wait for a proper Supabase-backed model.

Response should include:

- current status: `IDLE`, `RUNNING`, `PAUSED`, `BLOCKED`, or `UNKNOWN`
- current zone, if any
- next planned zone
- today's planned zones with planned minutes, status, reason, actual start/end
- total planned minutes and completed minutes
- recently completed/skipped/paused events
- advisory gates only:
  - rain/wind/heat caution;
  - low-battery/power caution;
  - stale weather/power data;
  - tank full/empty later when sensors exist
- clear safety flags:
  - `read_only = true`
  - `can_control = false`
  - `hardware_commands_enabled = false`

Strict exclusions:

- No IFTTT calls.
- No Google Sheet writes.
- No plan rebuilds.
- No status updates.
- No Oom Sakkie start/stop commands.

Recommended implementation order:

1. Build backend service that reads `STATE`, `DAILY_PLAN`, `ZONES`, and recent `LOG`. - Done locally.
2. Add `GET /api/telemetry/irrigation/status`. - Done locally.
3. Test locally against read-only data. - Done locally.
4. Deploy and verify endpoint. - Done.
5. Only after this works, update Oom Sakkie to answer irrigation status questions.

Local result on 2026-05-23:

- `GET /api/telemetry/irrigation/status` is registered locally.
- Direct service read against `Amadeus_Irrigation_Logs` returned `success = true`, `status = ok`, `mode = read_only`.
- Safety flags returned:
  - `read_only = true`;
  - `can_control = false`;
  - `hardware_commands_enabled = false`.
- Today returned two planned zones:
  - `C12345` / `C - Kamp`, `60` minutes;
  - `B12345` / `B - Kamp`, `60` minutes.
- Source confirms `writes_to_sheets = false` and `writes_to_supabase = false`.
- Focused telemetry tests passed.

Deployed result on 2026-05-23:

- Render endpoint returned `success = true`, `status = ok`, `mode = read_only`.
- Safety flags returned correctly:
  - `read_only = true`;
  - `can_control = false`;
  - `hardware_commands_enabled = false`.
- Source confirmed `writes_to_sheets = false` and `writes_to_supabase = false`.
- Current state returned `IDLE`, current/last zone `C12345` / `C - Kamp`.
- Today returned two planned zones for `2026-05-23`:
  - `C12345` / `C - Kamp`, `60` minutes, `PLANNED`;
  - `B12345` / `B - Kamp`, `60` minutes, `PLANNED`.
- Recent events show daily `PLAN_CREATED` rows.
- Follow-up note: `next_zone_id` currently follows `STATE.next_zone_id` when present. If this should instead be recalculated from plan priority/water score, refine before wiring Oom Sakkie wording.

Next-zone clarity patch prepared on 2026-05-23:

- Endpoint still keeps `STATE.next_zone_id` as the authoritative displayed `next_zone_id` when present.
- Endpoint now also returns `state_next_zone_id`, `computed_next_zone_id`, `next_zone_source`, and `next_zone_mismatch`.
- If the sheet state and computed priority/water-score result differ, the response adds an operator note instead of silently hiding the mismatch.
- Local focused telemetry tests passed after this patch.

### 10.3Q Oom Sakkie Read-Only Irrigation Status Tool - Live-Verified

Purpose:

- Let Oom Sakkie answer irrigation status questions through the backend read-only endpoint.
- Keep `2.3.2 - Run Irrigation Controller` inactive and untouched.
- Keep all irrigation control out of Oom Sakkie until a later command/audit/safety phase.

Local workflow changes prepared on 2026-05-23:

- Added `docs/04-n8n/workflows/2.3.3 - Irrigation Status Tool/workflow.json`.
- Added `docs/04-n8n/workflows/2.3.3 - Irrigation Status Tool/README.md`.
- Updated `2.0 - OOM SAKKIE - Amadeus Assistant Agent` with `Irrigation_Info_Tool`.
- `2.3.3` calls `GET /api/telemetry/irrigation/status` only.
- `2.3.3` formats current state, today's plan, next-zone state/computed fields, recent events, rules, and read-only safety flags.
- `2.3.3` has no Telegram Trigger, no Google Sheets node, no IFTTT node, and no hardware-control path.
- Workflow contract tests now protect the new read-only irrigation worker and the `2.0` tool wiring.

Manual import/test order:

1. Import `docs/04-n8n/workflows/2.3.3 - Irrigation Status Tool/workflow.json`.
2. Run `2.3.3` manually with input `What is the irrigation status?`.
3. Confirm the answer is status-only and says it cannot start/stop/change irrigation.
4. Import updated `docs/04-n8n/workflows/2.0 - OOM SAKKIE - Amadeus Assistant Agent/workflow.json`.
5. Ask Telegram Oom Sakkie: `What is the irrigation status?`
6. Confirm only GateKeeper, `2.0`, and `2.3.3` execute. `2.3.2` must not execute.
7. Ask a control-style question such as `Start irrigation` and confirm Oom Sakkie does not start anything and says control requires a separate approved hardware-control path.

Live result on 2026-05-23:

- Owner imported/tested `2.3.3` and updated `2.0`.
- Oom Sakkie irrigation status questions now work.
- Control-style safety test also passed.
- `2.3.2 - Run Irrigation Controller` remains inactive and must stay out of the read-only Oom Sakkie path.

### 10.3R Irrigation Supabase Data Model - Proposed Next Backend/Data Slice

Purpose:

- Move irrigation from a sheet-shaped operating record toward a proper Supabase model before dashboards, zone editing, adaptive planning, fertilizer logic, tank sensors, or hardware-control actions.
- Keep the first Supabase slice data-only and read-only from the app/API perspective.
- Do not build any command/control endpoints in this slice.

Recommended tables:

- `irrigation_zones` - configured water zones such as `C12345` / `C - Kamp`, season runtimes, priority, irrigation type, active flag, and crop/context fields.
- `irrigation_daily_plans` - one plan header per local date and plan source/version.
- `irrigation_plan_items` - zone-level rows for each daily plan, planned minutes, status, water score, planned/actual times, and reason.
- `irrigation_state_snapshots` - latest/readback state from the current sheet/controller path.
- `irrigation_events` - append-only event/audit log such as `PLAN_CREATED`, `ZONE_STARTED`, `ZONE_COMPLETED`, `PAUSED`, `SKIPPED`.
- `irrigation_auxiliary_devices` - fertilizer injection valves, fertilizer mixing valve, future pump/support devices.
- `irrigation_auxiliary_tasks` - non-zone support tasks such as fertilizer injection window or daily tank mixing.
- `irrigation_sensor_states` - tank full/empty, future level sensors, and other inputs that should drive planning safely later.

Guardrails:

- No writes back to Google Sheets.
- No IFTTT calls.
- No `2.3.2` activation.
- No Oom Sakkie start/stop commands.
- No automatic plan rebuilds from Supabase yet.
- No dashboard work until the schema and verifier are accepted.

Recommended implementation order:

1. Create the empty Supabase irrigation schema migration. - Done.
2. Add backend schema verifier endpoint. - Done.
3. Run local tests. - Done.
4. Apply migration to Supabase. - Done.
5. Verify deployed schema. - Done.
6. Plan a read-only sheet-to-Supabase import/dry-run for zones, current plans, state, and log rows. - Done.

Local/Supabase result on 2026-05-23:

- Migration file: `supabase/migrations/202605230001_create_irrigation_tables.sql`.
- Applied successfully through `scripts/apply_supabase_migration.py`.
- Local verifier endpoint added: `GET /health/database/irrigation-schema`.
- Local verifier returned `success = true`, `status = ok`, migration ID `202605230001_create_irrigation_tables`, and `missing_tables = []`.
- Expected/found tables:
  - `irrigation_zones`;
  - `irrigation_daily_plans`;
  - `irrigation_plan_items`;
  - `irrigation_state_snapshots`;
  - `irrigation_events`;
  - `irrigation_auxiliary_devices`;
  - `irrigation_auxiliary_tasks`;
  - `irrigation_sensor_states`.
- Source row found: `irrigation-controller-main`, `source_type = irrigation`, `provider = n8n_sheet_bridge`, `stale_after_minutes = 60`.
- This migration imports no data, creates no command/control endpoint, and changes no live irrigation behavior.

Deployed verification on 2026-05-23:

- Render `/health/database/irrigation-schema` returned `success = true`, `status = ok`.
- Migration ID: `202605230001_create_irrigation_tables`.
- `missing_tables = []`.
- All eight expected irrigation tables were found.
- Source row found: `irrigation-controller-main`, `provider = n8n_sheet_bridge`, `source_type = irrigation`, `stale_after_minutes = 60`.

### 10.3S Irrigation Sheet-to-Supabase Dry-Run Import - Dry-Run Complete

Purpose:

- Map current `Amadeus_Irrigation_Logs` sheet data into the new Supabase irrigation table shapes without writing anything.
- Prove the mapping before any import, dashboard, or operating cutover.

Implemented on 2026-05-23:

- Added `scripts/irrigation_import_dry_run.py`.
- Added focused tests in `tests/test_irrigation_import_dry_run.py`.
- The dry-run reads `Amadeus_Irrigation_Logs` only and writes nothing to Supabase or Google Sheets.
- Real Google Sheet dry-run passed with:
  - `ZONES`: 2 source rows -> 2 `irrigation_zones` rows.
  - `DAILY_PLAN`: 146 source rows -> 73 `irrigation_daily_plans` rows and 146 `irrigation_plan_items` rows.
  - `STATE`: 1 source row -> 1 `irrigation_state_snapshots` row.
  - `LOG`: 77 source rows -> 77 `irrigation_events` rows.
  - `irrigation_auxiliary_devices`, `irrigation_auxiliary_tasks`, and `irrigation_sensor_states`: 0 rows for now.
- `duplicates.zone_ids = []`.
- `link_issues = {}`.
- `writes_to_supabase = false` and `writes_to_sheets = false`.

Review notes:

- The existing irrigation sheet is small enough to import, but this should still not be applied automatically.
- `STATE` currently maps to one snapshot ID (`IRRSTATE-MAIN`). A real import path should decide whether state snapshots should be append-only by timestamp or latest-state upsert only.
- Plan item IDs currently follow the sheet's `plan_id` values, for example `2026-03-12_C12345`.
- Event IDs are generated from source row and timestamp. This is acceptable for dry-run; the apply/import path should keep the same deterministic rule or use a dedicated import ID strategy.
- No auxiliary/fertilizer/tank data was imported yet because those controls need their own config and safety model.

Owner decision on 2026-05-23:

- Treat `STATE` as the latest irrigation truth, matching the current Google Sheet model.
- A real import should upsert `irrigation_state_snapshots` by `state_snapshot_id`, for example `IRRSTATE-MAIN`.
- Do not append a new state row every time the current state changes.
- Use `irrigation_events`, `irrigation_daily_plans`, and `irrigation_plan_items` for historical questions such as what happened today or what was planned.
- If detailed state history becomes useful later, add a separate history table deliberately; do not overload the latest-state table now.
- The operational irrigation plan should mean today's active working plan. It should be refreshed/rebuilt daily and should not expose combined historical plans as the current plan.

Next backend/data slice:

- Build a controlled `--apply` import path for the mapped irrigation history.
- Apply behavior must use latest-state upsert for `STATE`.
- Continue to exclude hardware control, IFTTT calls, command queues, and `2.3.2` activation.

### 10.3T Irrigation Controlled Supabase Import - Applied And Verified

Purpose:

- Import the approved irrigation sheet history into Supabase using the proven 10.3S mapping.
- Keep the import controlled, explicit, and non-hardware.

Implemented on 2026-05-23:

- Extended `scripts/irrigation_import_dry_run.py` with explicit `--apply` mode.
- Added `scripts/irrigation_import_verify.py`.
- Added `tests/test_irrigation_import_verify.py`.
- Added compatibility migration `supabase/migrations/202605230002_add_irrigation_state_source_sheet_row.sql`.
- The first apply attempt failed safely with `UndefinedColumn` and rolled back; no rows were written.
- The compatibility migration added `source_sheet_row` to `irrigation_state_snapshots`.
- The second apply succeeded with import batch `IMPORT-20260523-IRRIGATION-SHEET-V1`.

Imported rows:

- `irrigation_zones`: 2.
- `irrigation_daily_plans`: 73.
- `irrigation_plan_items`: 146.
- `irrigation_state_snapshots`: 1.
- `irrigation_events`: 77.

Verification:

- `scripts/irrigation_import_verify.py --pretty` verified the Supabase counts directly.
- `state_strategy_verified = true`.
- Supabase has exactly one latest-state row:
  - `state_snapshot_id = IRRSTATE-MAIN`;
  - `current_status = IDLE`;
  - `current_zone_id = C12345`;
  - `next_zone_id = C12345`;
  - `import_batch_id = IMPORT-20260523-IRRIGATION-SHEET-V1`.

Safety result:

- No Google Sheets writes.
- No n8n workflow changes.
- No IFTTT calls.
- No command/control endpoint.
- `2.3.2 - Run Irrigation Controller` remains inactive.

Next backend/data slice:

- Plan a Supabase-backed irrigation read endpoint or service path so current status, today's active plan, and recent history can come from Supabase instead of the temporary Google Sheet bridge.
- The current plan read must select today/latest active plan only, not combine all historical imported plan rows.

### 10.3U Supabase-Backed Irrigation Status Read Path - Local Ready

Purpose:

- Let the existing irrigation status endpoint read from Supabase for current state, today's active plan, and recent events.
- Keep the sheet bridge available while daily planner writes still happen in the sheet.
- Keep the endpoint read-only.

Implementation:

- `GET /api/telemetry/irrigation/status` now supports source selection through `IRRIGATION_STATUS_SOURCE`.
- Default remains `google_sheets` so deployed behavior does not change unexpectedly.
- Supported values:
  - `google_sheets`: current bridge behavior.
  - `supabase`: force Supabase read; no sheet fallback.
  - `auto`: try Supabase first, then fall back to the sheet bridge if Supabase has no plan rows for the requested day or cannot be read.
- Supabase read path selects:
  - latest `irrigation_state_snapshots` row;
  - one active plan header for the requested local date;
  - only plan items for that selected daily plan;
  - recent events from `irrigation_events`.
- This protects the current-plan rule: old imported plans stay historical and are not combined into today's visible plan.

Local verification:

- Unit tests passed for the existing sheet path and the new Supabase path.
- Live-style local Flask check with `IRRIGATION_STATUS_SOURCE=supabase` returned `success = true`, `source = supabase`, `daily_plan_id = IRRPLAN-2026-05-23`, read-only safety flags, and today's two imported plan items only.

Deployment note:

- Do not switch Render to `IRRIGATION_STATUS_SOURCE=supabase` permanently until the daily planner or a sync job writes today's refreshed plan into Supabase.
- Safer interim deployment option is `IRRIGATION_STATUS_SOURCE=auto`, once tested, because it can fall back to the existing sheet bridge when Supabase does not yet have the current day's plan.

### 10.3V Irrigation Daily Supabase Sync - Applied Locally

Purpose:

- Sync only the current working irrigation slice from the sheet into Supabase.
- Avoid re-importing or exposing all historical plans as the current plan.
- Keep the sync manual/explicit until scheduling is planned.

Implemented:

- Added `scripts/irrigation_daily_sync.py`.
- Added `tests/test_irrigation_daily_sync.py`.
- Default mode is plan-only.
- Explicit `--apply` writes to Supabase in one transaction.
- Sync scope:
  - all configured zones from `ZONES`;
  - requested date only from `DAILY_PLAN`;
  - latest `STATE` rows as latest-state upsert;
  - `LOG` rows dated for the requested date or linked to the requested date's plan rows.

Local live result for `2026-05-23`:

- Plan-only check returned:
  - 1 daily plan: `IRRPLAN-2026-05-23`;
  - 2 plan items: `2026-05-23_C12345`, `2026-05-23_B12345`;
  - 1 state row: `IRRSTATE-MAIN`;
  - 1 event;
  - 2 zones.
- Apply succeeded with batch `SYNC-IRRIGATION-2026-05-23`.
- Supabase-backed status check returned:
  - `source = supabase`;
  - `daily_plan_id = IRRPLAN-2026-05-23`;
  - exactly today's two plan items;
  - `current.status = IDLE`;
  - read-only safety flags.

Deployment/test next:

- Backend deployed and default source verified on Render.
- Default deployed endpoint still uses `source = google_sheets`.
- Deployed response returned today's two planned zones, latest `STATE`, and read-only safety flags.
- `IRRIGATION_STATUS_SOURCE=auto` was enabled on Render and verified.
- Auto response returned `source = supabase`, `today.daily_plan_id = IRRPLAN-2026-05-23`, exactly two current plan rows, and read-only safety flags.
- Minor follow-up: recent event output showed the same `PLAN_CREATED` event twice because both the historical import and daily sync contain that logical event. Local fix now dedupes recent events for display; redeploy before final closure.
- Redeployed dedupe fix verified: recent `PLAN_CREATED` appears once for `2026-05-23`.
- Do not schedule the sync until the manual deployed path is proven.

### 10.3W Telemetry Rollup Planning - In Progress

Purpose:

- Define how power, weather, and irrigation data should be summarized before dashboards or scheduled jobs are built.
- Avoid dashboard queries over raw high-frequency data.
- Protect old telemetry Google Sheets until Supabase import/rollup comparisons are trusted.

Recommended defaults captured:

- Keep raw power 5-minute readings for at least `90 days` initially.
- Keep raw weather readings for at least `90 days` initially.
- Keep irrigation events/plans long-term because they are lower volume and operationally important.
- Keep daily, monthly, and yearly rollups permanently.
- Keep current/latest status in latest-state tables, not history scans.
- Use current/latest endpoints for Oom Sakkie current questions.
- Use daily/monthly/yearly rollups for dashboard and reporting questions.

Rollup direction:

- Power daily rollups should include sample coverage, battery min/max/avg, load/solar averages and peaks, grid/generator active minutes, and estimated or confirmed kWh fields.
- Weather daily rollups should include sample coverage, temperature min/max/avg, humidity average, rain total, max rain rate, wind/gust max, and irrigation caution flags.
- Irrigation daily rollups should include planned/completed/skipped/paused counts, planned/completed minutes, hold reasons, event count, and notes.
- Monthly rollups should be built from daily rollups.
- Yearly rollups should be built from monthly rollups.

Important power rule:

- Prefer confirmed Sunsynk energy counters if available.
- If only 5-minute W samples are available, kWh/Rand values must be marked as estimated.
- Estimated values must store method, calculation version, sample count, coverage, and tariff.
- Planning tariff remains `R9.10/kWh` until a proper tariff table is created.

Google Sheet protection rule:

- Do not delete or clear old telemetry Sheets yet.
- First export/download backups.
- Import or roll up useful history into Supabase.
- Compare row counts, date ranges, sample days, and totals.
- Only archive/clean after owner acceptance.

Suggested next implementation order:

1. Finalize owner defaults for retention and estimation.
2. Create empty rollup tables and health verifier.
3. Build daily rollup generator in plan-only mode.
4. Apply one-day rollups for known-good dates.
5. Compare rollups against existing current/today/recent endpoints.
6. Plan schedules only after manual rollups are trusted.

Questions to answer:

Owner decisions:

- `90 days` is accepted as the initial raw retention window for power and weather.
- Old telemetry Sheets may be deleted after backup/import/compare acceptance; the goal is not to leave old sheets hanging around forever.
- Irrigation rollups should include fertilizer and tank placeholders now, because those operations are already in use.
- `R9.10/kWh` remains the planning/default tariff until a tariff table exists.

Updated next implementation direction:

- Create empty rollup tables with 90-day raw retention documented.
- Include nullable fertilizer/tank fields in `irrigation_daily_rollups`.
- Keep Google Sheet deletion blocked until backup/import/compare is accepted.

10.3W2 implementation result:

- Added and applied `supabase/migrations/202605230003_create_telemetry_rollup_tables.sql`.
- Added backend verifier `GET /health/database/telemetry-rollup-schema`.
- Created empty daily/monthly/yearly rollup tables for power, weather, and irrigation.
- Included power estimated kWh/value fields with `R9.10/kWh` as the planning tariff.
- Included irrigation fertilizer/tank placeholders for future reporting.
- Verification passed: focused database tests `25 OK`, broader telemetry/database tests `59 OK`, and local Supabase health returned all nine expected rollup tables with `missing_tables = []`.
- No rollup data, schedules, dashboards, sheet deletion, or hardware-control path was added.

Next implementation direction:

- Build 10.3W3 as a plan-only daily rollup generator.
- Start with one date and report intended writes before applying anything.
- Keep old telemetry Sheets untouched until backup/import/compare acceptance.

10.3W3 implementation result:

- Added plan-only script `scripts/telemetry_daily_rollup_plan.py`.
- Added focused tests in `tests/test_telemetry_daily_rollup_plan.py`.
- The script reads one ZA local date from Supabase and returns candidate rows for `power_daily_rollups`, `weather_daily_rollups`, and `irrigation_daily_rollups`.
- It writes nothing: `writes_to_sheets = false`, `writes_to_supabase = false`.
- Live plan-only run for `2026-05-23` returned one candidate row for each daily rollup table.
- Power/weather both had `118/288` samples and `40.97%` coverage because the selected date was still in progress.
- Irrigation returned plan `IRRPLAN-2026-05-23`, two planned zones, `120` planned minutes, and deduped event count `1`.
- Verification passed: focused rollup tests `5 OK`; broader telemetry/database tests `64 OK`.

Next implementation direction:

- Review the plan-only payload shape.
- If accepted, build 10.3W4 as a manual one-date apply path.
- Do not schedule rollups or delete old telemetry Sheets yet.

10.3W4 implementation result:

- `scripts/telemetry_daily_rollup_plan.py` now supports `--apply`.
- Default remains plan-only.
- Apply mode upserts only one selected date into the three daily rollup tables and uses one transaction.
- Applied `2026-05-23` manually.
- Supabase verification confirmed:
  - `power_daily_rollups`: `sample_count = 119`, `coverage_pct = 41.32`, estimated load `7.9714 kWh`, estimated solar `2.5383 kWh`;
  - `weather_daily_rollups`: `sample_count = 119`, `coverage_pct = 41.32`, temp `9 C` to `14 C`, rain `0 mm`;
  - `irrigation_daily_rollups`: `IRRPLAN-2026-05-23`, two planned zones, `120` planned minutes, event count `1`.
- This was a current-day test apply, so the low coverage is expected. Final daily rollups should normally run after the day closes unless marked partial.
- No schedule, monthly/yearly rollup, dashboard, sheet cleanup, or control path was added.

Next implementation direction:

- Add a daily rollup read/compare endpoint, or add an after-day-close apply guard before scheduling.

10.3W5 implementation result:

- Added read-only route `GET /api/telemetry/rollups/daily?date=YYYY-MM-DD`.
- Added `modules/telemetry/rollup_service.py`.
- Added tests in `tests/test_telemetry_rollup_service.py`.
- Endpoint returns stored daily rollups, current raw/source counts, comparison flags, and operator notes.
- Local Supabase check for `2026-05-23` returned stored power/weather/irrigation rollups and correctly detected current-day drift:
  - power stored `119` samples vs current `120`;
  - weather stored `119` samples vs current `121`;
  - irrigation event and plan counts still matched.
- Endpoint is read-only and reports `writes_to_supabase = false`.
- Verification passed: focused rollup service tests `3 OK`; broader telemetry/database tests `69 OK`.

Next implementation direction:

- Add an after-day-close guard before any scheduled rollup apply.
- Keep current-day rollup applies manual/testing only unless explicitly marked partial.

10.3W6 implementation result:

- Added after-day-close guard to `scripts/telemetry_daily_rollup_plan.py --apply`.
- Apply now refuses today/future ZA dates by default with `status = day_not_closed`.
- Added explicit manual override `--allow-partial`.
- Verified normal apply for `2026-05-23` refused because it is still today.
- Verified `--allow-partial` refreshed the test rollups intentionally.
- Read/compare endpoint then showed stored/current sample counts matching at `179` for both power and weather, while still warning coverage below `75%`.
- Verification passed: focused rollup script tests `8 OK`; broader telemetry/database tests `70 OK`.

Next implementation direction:

- Decide the first safe schedule time, likely after midnight ZA for the previous day, for example `00:15` to `00:30`.
- Do not schedule until we agree the run timing and recovery behavior.

10.3W7 implementation result:

- Owner selected `00:15` Africa/Johannesburg as the daily rollup schedule time.
- Added `--previous-day` to `scripts/telemetry_daily_rollup_plan.py`.
- Verified previous-day plan-only selected `2026-05-22` while today was `2026-05-23`.
- Verified previous-day apply worked without `--allow-partial`.
- Compare endpoint for `2026-05-22` confirmed:
  - power stored/current sample count `283`, coverage `98.26%`, quality `complete`;
  - weather stored/current sample count `231`, coverage `80.21%`, quality `usable`;
  - irrigation event and plan counts matched.
- Verification passed: broader telemetry/database tests `71 OK`.

Render cron command:

```bash
python scripts/telemetry_daily_rollup_plan.py --previous-day --apply
```

Schedule:

- `00:15` Africa/Johannesburg.
- If cron uses UTC only: `22:15` UTC.

Next implementation direction:

- Backend repo containing the script was deployed by owner on 2026-05-25.
- Render cron `amadeus-telemetry-daily-rollups` was created by owner on 2026-05-25 and built successfully.
- Command: `python scripts/telemetry_daily_rollup_plan.py --previous-day --apply`.
- Schedule shown by Render: `10:15 PM UTC`, which is `00:15 Africa/Johannesburg`.
- There is no `render.yaml` / Render Blueprint in this repo, so the live cron is dashboard-managed unless Render API credentials or an infrastructure-as-code path is provided.
- First scheduled run verified on 2026-05-26 with `/api/telemetry/rollups/daily?date=2026-05-25`.
- Result: `success = true`, `status = ok`, all three rollups found, no Supabase writes from the read endpoint.
- Power: stored/current `288/288`, coverage `100%`, quality `complete`.
- Weather: stored/current `287/288`, coverage `99.65%`, quality `complete`.
- Irrigation: stored/current `0` events and `0` plan items, both matched.

Farm home/dashboard idea:

- Source note moved from `planning/ToDoList.md`.
- After login, the web app should eventually open on a useful farm home page that brings the wider operating system together.
- Desired first-viewport signals: current weather, short forecast, power/solar state, and navigation into pig system, weather, power, irrigation, orders, and other modules as they mature.
- Owner note 2026-05-26: the home page should use the wider desktop screen properly. The current app often feels squeezed into a centered block because the shared `.page-card` layout is capped around `960px`; the farm home should use a wider operational canvas with dense, readable panels instead of a narrow center column.
- Template rule logged 2026-05-26:
  - Use the existing narrow centered `page-card` pattern for forms, focused detail screens, and simple CRUD pages.
  - Use the wider `ops-shell` / `ops-dashboard` pattern for operating dashboards, status boards, reporting overviews, and cross-module pages.
  - Wide operational pages should target roughly `1500px` to `1680px` of desktop canvas, use responsive grid panels, avoid nested cards, and keep information dense enough for daily farm scanning.
  - Do not redesign each page separately; build future high-level pages from the same operational-dashboard conventions unless a page has a clear reason to stay form-like.
- The page may include farm photos as a quiet rotating background/screensaver element, but operational information must remain readable and useful.
- Treat this as an operating dashboard, not a marketing landing page.
- This belongs in Phase 10 because it depends on weather, solar, irrigation, pig records, and order modules having stable documented contracts.
- Broader app layout note moved from `planning/ToDoList.md`: the desktop app should use available screen width better, with a consistent page template so information is not unnecessarily squeezed into the middle.
- Mobile/PWA note moved from `planning/ToDoList.md`: investigate whether the app should support installable mobile behavior, for example a Progressive Web App pattern, so phone use feels closer to an app while still running through the browser.
- UX rule: do not redesign every page separately. Establish shared layout conventions for page width, filters, tabs, tables, action placement, mobile behavior, and desktop density.
- Shared template/layout follow-up moved from `planning/ToDoList.md`: define a reusable page template for new pages so forms, tables, filters, action buttons, and page width stay consistent.
- 2026-05-26 local implementation result:
  - Replaced the `/` dashboard with a read-only wide `ops-shell` / `ops-dashboard` layout.
  - First slice uses existing endpoints only: weather current/today/forecast, power current, irrigation status, daily rollup compare, pig-weight dashboard, and daily order summary.
  - Added wide dashboard CSS with responsive desktop/mobile grids while leaving existing narrow form/detail pages on `page-card`.
  - Added frontend route contract coverage for the wide dashboard template and read-only API usage.
  - Local checks passed: frontend route contract tests, dashboard/rollup service tests, JS syntax check, Flask route smoke through the project virtualenv, and browser-serving smoke at `http://127.0.0.1:5000/`.
  - Owner desktop browser review 2026-05-26: layout direction accepted and data now loads after replacing stale local server processes on port `5000`.
  - Minor polish note: improve tight metric wrapping where values such as rollup quality `complete` can split across two lines; then do a final desktop/mobile review before deploy.
  - 2026-05-26 polish applied: compact metric cards now auto-fit to avoid cramped four-column tiles in narrow panels, metric values no longer split words mid-word, machine labels such as `not_using_grid`, `google_sheets`, and `complete` display as human-readable text, and the dashboard script has a refreshed cache-buster.
- 2026-05-26 live verification passed: owner confirmed the live home page is good after deploy.

Dashboard and notification follow-up notes moved from `planning/ToDoList.md` on 2026-05-30:

- Herd tile audit: the dashboard `Herd` card currently shows a total head count, but the visible breakdown numbers do not add back up to that total. Next dashboard audit should inspect the backend source fields and either add the missing categories to fill the space or clarify the labels so the total and breakdown reconcile.
- Farm `Needs Attention` Telegram reminder: send important farm attention items to Telegram so they are visible even when the web app is not opened first. This must avoid spam through digest timing, cooldowns, change detection, or severity grouping. Preferred direction is backend-owned attention summary and n8n as the thin Telegram delivery layer, matching the weather/power alert pattern.
  - 2026-05-30 local first slice: added read-only backend endpoint `GET /api/reports/farm-attention-summary`.
  - The endpoint combines existing order attention and litter attention, returns `digest_lines`, reports `mode = read_only`, and explicitly reports no Supabase writes, no Google Sheets writes, and no Telegram send.
  - Local verification passed: `python -m unittest tests.test_farm_attention_summary tests.test_pig_weights_dashboard_service` and `node --check static/js/dashboard.js`.
  - Owner deployed the backend endpoint on 2026-05-30.
  - Production smoke on 2026-05-30 returned `success = true`, `status = ok`, `mode = read_only`, `attention_total = 1`, and current digest item `LIT-2026-8A0F: Piglets need tag numbers`; backend source flags remained no Supabase writes, no Google Sheets writes, and no Telegram send.
  - 2026-05-30 local n8n slice: added inactive workflow export `ALERT - Farm Attention Digest`.
  - Workflow starts with `dryRun = true`, calls only `/api/reports/farm-attention-summary`, sends only to Charl when deliberately enabled, suppresses empty digests, suppresses duplicate content hashes, and enforces a minimum-hours-between-sends guard through workflow static data.
  - Owner uploaded the updated workflow export to n8n on 2026-05-30.
  - n8n API verification on 2026-05-30 confirmed workflow `kd5wrJEgBfUNNxnb` is active.
  - Manual execution `49136` stopped at `Code - Extract Sendable Digest` with zero output.
  - Manual executions `49137` and `49138` reached `Telegram - Send Farm Attention Digest` and `Code - Record Sent Digest`; both sent the expected digest: `attention_total = 1`, `orders = 0`, `litters = 1`, `LIT-2026-8A0F: Piglets need tag numbers`.
  - Manual repeated sends are not valid duplicate-suppression proof because n8n manual executions do not reliably persist workflow static data.
  - Next action: observe the next scheduled execution. If the digest content is unchanged, it should stop at `Code - Extract Sendable Digest`; if content changes, a send is acceptable.
- Telegram alert/message usefulness polish:
  - Make alert messages easier to scan by adding clear symbols/emoji and consistent formatting by alert type/severity. Power, current weather, forecast, and farm `Needs Attention` should be visually distinct in Telegram while still keeping readable text.
  - Improve timing so Oom Sakkie stays useful without becoming spammy. Owner examples: farm `Needs Attention` digest around morning planning time, perhaps 06:30, again around 13:00, and possibly end-of-day if useful.
  - Rain alerts should be practical: alert when meaningful rain starts during awake hours, avoid repeated spam while it continues, then send a rain-stopped/period-total summary and a daily total at a set time.
  - This needs alert-rule planning, cooldown/change-detection, quiet-hours handling, and digest scheduling. Do not treat it as presentation-only once timing/rain rules are changed.
  - Owner screenshot reference: `screenshots/Telegram Alerts.png`.
- Dashboard visual cues: add weather and solar/power symbols or small visual states to the home dashboard so weather and energy status are easier to scan. Keep visuals functional, not decorative, and preserve readable text for exact values.
- Farm task/reminder/project management: future planning item for important dates, reminders, task ownership, projects, and idea logging. This needs a proper model and should not be squeezed into the current attention list as ad hoc notes.
- Weather station to Windy integration: research whether the local weather station can publish to Windy. Treat as an external integration planning task first; do not change the existing weather ingestion path until the Windy upload method, API requirements, station ID handling, and data ownership are understood.
- Future alert preferences page: once the web app has login/user identity, add a preferences screen where each user can choose which alert/update types they receive, digest timing, repeat/cooldown intervals, quiet hours, and summary schedule. Keep this later-later; do not build before auth, recipient configuration, and alert delivery safety are settled.
- Slack architecture assessment moved from scratch notes to `docs/01-architecture/SLACK_ARCHITECTURE_ASSESSMENT.md` on 2026-06-05. Recommendation: do not implement Slack now; keep it as a future optional human visibility/notification adapter only, never as agent memory, event bus, or source of truth.
- Oom Sakkie voice operating agent PRD added on 2026-06-06: `docs/01-architecture/OOM_SAKKIE_VOICE_OPERATING_AGENT_PRD.md`. Recommendation after reviewing the Trillion public site and owner goal for a local farm PC: build the backend text orchestrator plus local `/oom-sakkie` kiosk page first (`POST /api/oom-sakkie/message` + `GET /oom-sakkie`) using approved read-only tools. The kiosk should show what Oom Sakkie heard, what tool/agent it called, the answer, trace ID, and links/cards for the relevant farm screens. Then add push-to-talk/Telegram voice notes, then consider wake-word/Home Assistant/custom local voice gateway. Do not start with always-on hardware, public posting, direct writes, or physical controls. Prompt backbone added at `docs/01-architecture/OOM_SAKKIE_AGENT_PROMPT_LIBRARY.md`; Trillion's private prompt playbook was not publicly accessible, so the library is Amadeus-specific and inspired only by public product patterns. Owner-provided Trillion-style playbooks are now logged and adapted in the prompt library: repo/code sentinel, cloud/local memory, read-only Supabase connector, Chief of Staff helper, context handoff, mobile voice PWA, personality persistence, voice latency streaming, security hardening, head-of-design sub-agent, living self-knowledge, cost dashboard, and sub-agent factory. These are backlog layers behind the read-only kiosk/orchestrator MVP, not immediate build scope.

### 10.6A Oom Sakkie Kiosk MVP - Owner-Tested

Source documents:

- `docs/01-architecture/OOM_SAKKIE_VOICE_OPERATING_AGENT_PRD.md`
- `docs/01-architecture/OOM_SAKKIE_AGENT_PROMPT_LIBRARY.md`

Claude architecture review result on 2026-06-06:

- Revise first, then build a narrow OS-1 + OS-4 slice.
- Do not create a second uncoordinated Oom Sakkie brain next to live n8n `2.0`.
- Decide the long-term orchestrator location before code.

Architecture decision before implementation:

- Confirmed direction on 2026-06-06: Flask/backend becomes the single long-term Oom Sakkie brain. n8n/GateKeeper stays Telegram I/O, callback routing, and scheduled work, then later forwards Telegram messages to `/api/oom-sakkie/message`.
- First implementation may leave live Telegram routing unchanged until the kiosk endpoint is proven.
- `2.0 - OOM SAKKIE` should eventually become a thin forwarder, not a second routing brain.
- Do not cut Telegram over until the kiosk/backend path is boring.

Determinism during migration:

- Use exact-match/rule routing before the LLM classifier.
- Known live phrasings for power/weather/farm attention should skip the LLM and route directly to tools.
- LLM classification runs only after rules do not match.
- Low confidence still returns `needs_clarification = true`.

Telegram migration gates:

1. Build endpoint and kiosk; leave Telegram unchanged.
2. Run kiosk daily for about two weeks and inspect traces for wrong tool selection, dropped stale warnings, and ambiguity.
3. Add a parallel Telegram route to `/api/oom-sakkie/message`, feature-flagged and limited to Charl's chat ID first.
4. Run parallel for about one week and compare old n8n answers with backend answers.
5. Treat disagreements as new-path bugs until proven otherwise.
6. Cut over `2.0` to a thin forwarder only after the parallel run is clean.
7. Keep `2.1`, `2.2`, and `2.3.3` exports as references for about 30 days after cutover, then archive.

Required first slice:

- `GET /oom-sakkie` - local kiosk page, text-only.
- `POST /api/oom-sakkie/message` - text-only read-only orchestrator endpoint.
- No mic, no TTS, no wake word, no writes.
- Three tools only:
  - `farm_attention_summary`
  - `power_current`
  - `weather_today`

Required response contract:

```json
{
  "answer": "",
  "tool_used": "",
  "trace_id": "",
  "risk_level": 0,
  "links": [],
  "stale_warnings": [],
  "needs_clarification": false
}
```

Required backend design:

- Add typed `OomSakkieTool` registry in code, likely under `modules/oom_sakkie/`.
- Every tool declares:
  - `name`
  - `input_schema`
  - `output_schema`
  - `risk_level`
  - `requires_confirmation`
  - `handler`
- Use a typed risk enum, with read-only as level `0`.
- Tool selection must have a confidence floor.
- Low-confidence tool selection returns `needs_clarification = true` rather than guessing.
- Stale-data fields from power/weather endpoints must be surfaced in `stale_warnings`.
- No multi-turn memory promise in this slice.

Trace store:

- Preferred: Supabase `oom_sakkie_traces`.
- Trace rows should be append-only.
- Minimum fields:
  - `trace_id`
  - `channel`
  - `session_id`
  - `user_text`
  - `intent`
  - `confidence`
  - `tool_name`
  - `tool_args_json`
  - `tool_result_summary`
  - `tool_result_hash`
  - `answer`
  - `risk_level`
  - `stale_warnings_json`
  - `links_json`
  - `created_at`

Kiosk UX:

- Large readable room-screen UI: roughly `18px` body, `32px` answer baseline.
- Kiosk shows only: user text, checking status, answer, links, stale warnings, collapsed trace ID.
- Keep the first page operational, not decorative.
- No 3D avatar, particles, or animated character in MVP.
- Future confirmation panel pattern: exact backend payload preview, not paraphrased text.

Tests required:

- Tool registry contract test: every tool has schema, risk level, confirmation flag, and handler.
- Orchestrator route tests: representative phrasing maps to the three expected tools.
- Stale-data test: stale power/weather markers become `stale_warnings`.
- Low-confidence test: returns `needs_clarification = true`.
- Route/page smoke: `/oom-sakkie` and `/api/oom-sakkie/message`.

Live verification before expanding:

- Use kiosk on the actual farm PC or local browser.
- Ask at least 20 real text questions across attention, power, and weather.
- Log failures/surprises before adding tools or voice.
- Do not start push-to-talk, TTS, more agents, more tools, or any write tool until the read-only loop has been used daily and behaves boringly.

Do not build yet:

- always-on wake word
- always-on room microphone
- browser push-to-talk
- TTS
- Afrikaans/multi-language behavior
- customer-facing message generation
- Meta/Facebook posting
- auto-purpose-classification writes
- irrigation start/stop or `2.3.2` activation
- direct Google Sheets/Supabase writes from the orchestrator
- autonomous agent loops
- new Telegram trigger workflows

Local implementation status 2026-06-06:

- Added `modules/oom_sakkie/` backend-owned read-only orchestrator.
- Added typed `OomSakkieTool` registry with the three MVP tools.
- Added rule-first classifier for farm attention, power, and weather.
- Added `POST /api/oom-sakkie/message`.
- Added `GET /oom-sakkie` text-only kiosk page.
- Added Supabase migration `202606060001_create_oom_sakkie_traces.sql`.
- Applied the trace-table migration locally against Supabase using `scripts/apply_supabase_migration.py`.
- Confirmed trace writes return `stored = true`.
- Confirmed local HTTP smoke:
  - `hello` returns `needs_clarification = true`.
  - `what needs attention today` routes to `farm_attention_summary`.
  - `what is the power like now` routes to `power_current`.
  - `weather today please` routes to `weather_today`.
- Full local unittest suite passed at 353 tests.

Deploy/browser-check next:

- Deploy backend and static/template changes.
- Open `/oom-sakkie`.
- Ask the same three smoke questions.
- Confirm traces are written in Supabase.
- Leave Telegram unchanged.

Owner test result:

- Owner tested `/oom-sakkie` after implementation and confirmed it answered the expected questions correctly.
- Keep Telegram unchanged until later parallel-run migration.

### 10.6B Oom Sakkie Read-Only Tool Expansion - Owner-Tested

Goal:

- Make the backend-as-brain kiosk useful beyond the first three MVP questions while keeping the same safety posture.

Scope:

- Add only read-only backend tools.
- Keep deterministic rule-first routing.
- Keep trace writes for every request.
- Keep `needs_clarification = true` on ambiguous requests.
- Do not add LLM routing yet unless a question cannot be handled safely with rules.
- Do not touch Telegram routing.

Recommended next tools:

1. `dashboard_summary` - wraps the existing dashboard/home read model for broad "how is the farm?" questions.
2. `pig_allocation_readiness` - wraps the Phase 11A allocation readiness endpoint/service.
3. `meat_planning` - wraps the Phase 11A meat planning endpoint/service.
4. `sales_dashboard` - wraps the sales dashboard read model.

Why this order:

- These tools already have backend read models.
- They make the kiosk immediately useful for the farm owner.
- They support the business goal without adding writes, Telegram changes, customer messages, public posting, or voice complexity.

Tests required:

- Registry contract still passes for all tools.
- Representative phrasing routes to each new tool.
- Unknown or ambiguous text still returns `needs_clarification = true`.
- Stale/limitation warnings are surfaced when the wrapped read model provides them.
- Full local unittest suite passes.

Do not build in 10.6B:

- Telegram cutover.
- Push-to-talk or TTS.
- LLM classifier as the default path.
- Write tools or confirmation actions.
- Customer-facing/Sam actions.
- Meta/Facebook post drafting.

Local implementation status 2026-06-06:

- Added `dashboard_summary`, `pig_allocation_readiness`, `meat_planning`, and `sales_dashboard` to the typed Oom Sakkie registry.
- Added rule-first routing for broad farm overview, pig allocation, meat planning, and sales dashboard phrasing.
- Direct local smoke with `.env` loaded returned:
  - `how is the farm` -> `dashboard_summary`, trace stored.
  - `show me pig allocation` -> `pig_allocation_readiness`, trace stored.
  - `what pigs are ready for meat` -> `meat_planning`, trace stored.
  - `sales dashboard overview` -> `sales_dashboard`, trace stored.
- The meat planning answer surfaces the read-only/no-save warning.
- Telegram remains unchanged.

Deploy/browser-check next:

- Deploy backend changes.
- Open `/oom-sakkie`.
- Ask the four new smoke questions above.
- Confirm traces store in Supabase.
- Keep Telegram unchanged.

Owner test result:

- Owner tested the expanded kiosk questions and confirmed they answered as expected.

### 10.6C Oom Sakkie Trace Visibility - Local Ready

Goal:

- Make daily review practical before any Telegram migration by showing recent backend brain traces in the kiosk and through a read-only API.

Implemented locally:

- Added `GET /api/oom-sakkie/traces`.
- Added recent trace readback from Supabase `oom_sakkie_traces`.
- Added a Recent Checks panel on `/oom-sakkie`.
- Recent rows show question, chosen tool, created time, and trace ID.
- Added refresh button.
- Kept trace display read-only.
- No Telegram changes, no writes beyond existing trace inserts, no voice, no LLM router.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused Oom Sakkie/frontend tests passed.
- Full local unittest suite passed at 356 tests.
- Local HTTP smoke for `/api/oom-sakkie/traces?channel=kiosk&limit=3` returned `success = true` and recent trace rows.

Deploy/browser-check next:

- Deploy backend/static/template changes.
- Open `/oom-sakkie`.
- Confirm Recent Checks loads.
- Ask a new question.
- Confirm the new trace appears after answer or refresh.

### 10.6D Oom Sakkie Trace Feedback - Local Ready

Goal:

- Make the two-week kiosk review window measurable by letting the owner mark whether each backend-brain trace was correct before any Telegram cutover.

Implemented locally:

- Added Supabase migration `202606060002_create_oom_sakkie_trace_feedback.sql`.
- Added append-only table `public.oom_sakkie_trace_feedback` linked to `oom_sakkie_traces`.
- Added validated feedback types: `correct`, `wrong_tool`, `stale_or_missing_data`, `bad_wording`, and `needs_follow_up`.
- Added `POST /api/oom-sakkie/traces/<trace_id>/feedback`.
- Extended `GET /api/oom-sakkie/traces` to return the latest feedback summary for each trace.
- Added compact feedback controls to the Recent Checks panel on `/oom-sakkie`.
- No Telegram changes, no voice, no LLM router, no farm-data writes, and no customer-facing/Sam actions.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused Oom Sakkie/frontend tests passed at 33 tests.
- Supabase migration applied locally.
- Local HTTP smoke fetched one recent trace, posted `correct` feedback, and confirmed `latest_feedback` returned on the next trace read.

Deploy/browser-check next:

- Deploy backend/static/template/migration changes.
- Open `/oom-sakkie`.
- Confirm Recent Checks still loads.
- Mark one trace as `Correct` and save.
- Refresh Recent Checks and confirm the reviewed status remains visible.
- Keep Telegram unchanged.

### 10.6E Oom Sakkie Review Summary - Local Ready

Goal:

- Give the kiosk trial a simple quality signal before Telegram migration: total checks, reviewed checks, issue rate, unreviewed count, and recent reviewed problem traces.

Implemented locally:

- Added `GET /api/oom-sakkie/traces/review-summary`.
- Summary reads latest feedback per trace so repeated review changes do not inflate counts.
- Added 14-day kiosk summary metrics on `/oom-sakkie`: checks, reviewed, issues, and unreviewed.
- Added recent reviewed problem trace list below the metric strip.
- Summary refreshes after new answers, manual refresh, and feedback saves.
- No Telegram changes, no voice, no LLM router, no farm-data writes, and no customer-facing/Sam actions.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused Oom Sakkie/frontend tests passed at 34 tests.
- Local HTTP smoke for `/api/oom-sakkie/traces/review-summary?channel=kiosk&days=14` returned `status = ok`, 20 kiosk traces, 1 reviewed trace, 0 problem traces, and per-tool counts.

Deploy/browser-check next:

- Deploy backend/static/template changes.
- Open `/oom-sakkie`.
- Confirm the review summary strip appears above Recent Checks.
- Save feedback on a trace and confirm counts update after refresh.
- Keep Telegram unchanged.

### 10.6F Oom Sakkie Trace Review Filters - Local Ready

Goal:

- Make daily trace review faster by filtering Recent Checks to all, unreviewed, issue, or reviewed traces during the kiosk trial.

Implemented locally:

- Extended `GET /api/oom-sakkie/traces` with `review=all|unreviewed|issues|reviewed`.
- Invalid review filter values fall back to `all`.
- Added filter buttons to `/oom-sakkie` above Recent Checks.
- Active filter stays selected when traces refresh after a feedback save.
- No Telegram changes, no voice, no LLM router, no farm-data writes, and no customer-facing/Sam actions.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused Oom Sakkie/frontend tests passed at 35 tests.
- Local HTTP smoke confirmed:
  - `review=all` returned mixed reviewed/unreviewed rows.
  - `review=unreviewed` returned only unreviewed rows.
  - `review=issues` returned zero rows with current data.
  - `review=reviewed` returned reviewed rows.

Deploy/browser-check next:

- Deploy backend/static/template changes.
- Open `/oom-sakkie`.
- Click All, Unreviewed, Issues, and Reviewed.
- Confirm rows change as expected.
- Keep Telegram unchanged.

### 10.6G Oom Sakkie Trace Detail Expanders - Local Ready

Goal:

- Let the owner inspect a saved trace answer, tool-result summary, stale warnings, and links directly from Recent Checks without re-asking the question or opening the database.

Implemented locally:

- Added an expandable `Show saved answer` details area to each recent trace row.
- Detail area renders the stored answer, tool result summary, stale warnings, and links already returned by `GET /api/oom-sakkie/traces`.
- No backend schema changes were needed.
- No Telegram changes, no voice, no LLM router, no farm-data writes, and no customer-facing/Sam actions.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed at 24 tests.
- Local HTTP smoke confirmed trace rows include `answer`, `tool_result_summary`, `stale_warnings`, `links`, and `latest_feedback`.

Deploy/browser-check next:

- Deploy static/template changes.
- Open `/oom-sakkie`.
- Expand `Show saved answer` on a few recent traces.
- Confirm answer, warnings, and links render clearly.
- Keep Telegram unchanged.

### 10.6H Oom Sakkie Trace Search - Local Ready

Goal:

- Make it easy to find a past kiosk trace by question text, saved answer text, tool name, or trace ID during the review window.

Implemented locally:

- Extended `GET /api/oom-sakkie/traces` with `q=<search text>`.
- Search combines with the existing `review` filter.
- Search text is bounded before it reaches the query.
- Added a debounced search box and Clear button above Recent Checks.
- No Telegram changes, no voice, no LLM router, no farm-data writes, and no customer-facing/Sam actions.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused Oom Sakkie/frontend tests passed at 36 tests.
- Local HTTP smoke confirmed `q=power` returned matching trace rows and a nonsense term returned zero rows.

Deploy/browser-check next:

- Deploy backend/static/template changes.
- Open `/oom-sakkie`.
- Search for `power`, `weather`, and a trace ID fragment.
- Confirm filters still combine correctly with search.
- Keep Telegram unchanged.

### 10.6I Oom Sakkie Voice Readiness Preflight - Local Ready

Goal:

- Show whether the current kiosk browser is ready for the later push-to-talk voice slice before opening the microphone or adding STT/TTS vendors.

Implemented locally:

- Added a `Voice Readiness` preflight panel to `/oom-sakkie`.
- Browser-side checks show:
  - secure origin status (`window.isSecureContext`)
  - microphone API availability (`navigator.mediaDevices.getUserMedia` capability only)
  - browser TTS availability (`speechSynthesis`)
- The panel does not request microphone permission and does not start audio capture.
- No Telegram changes, no push-to-talk, no TTS playback, no wake word, no LLM router, and no farm-data writes.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed at 24 tests.
- Local route smoke confirmed `/oom-sakkie` serves the `Voice Readiness` panel and states that no microphone is opened yet.

Deploy/browser-check next:

- Deploy static/template changes.
- Open `/oom-sakkie` on the target kiosk browser.
- Confirm `Secure origin`, `Mic API`, and `Browser TTS` statuses.
- If `Secure origin` is blocked, finish LAN HTTPS (`farm-pc.local` or equivalent) before any push-to-talk work.
- Keep Telegram unchanged.

### 10.6J Oom Sakkie Browser Speech Draft - Local Ready

Goal:

- Let the owner draft a kiosk question by speaking into the browser, while still requiring explicit review and pressing `Ask` before the backend brain runs.

Implemented locally:

- Added a `Talk` button beside the existing text input.
- Uses browser `SpeechRecognition` / `webkitSpeechRecognition` when available.
- Recognition language is set to `en-ZA`.
- Recognized speech fills the existing text input and updates `You Asked`.
- Speech recognition is single-utterance (`continuous = false`) and interim results are allowed.
- The browser does not auto-submit recognized text. Owner must still press `Ask`.
- Browser SpeechRecognition support is now shown in Voice Readiness.
- No backend STT vendor, no Deepgram/OpenAI Whisper, no TTS playback, no wake word, no always-on mic, no Telegram changes, and no farm-data writes.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed at 24 tests.
- Local route smoke confirmed `/oom-sakkie` serves the Talk button, voice status line, and draft-before-send copy.

Browser-check next:

- Open `/oom-sakkie` in Chrome on the laptop.
- Click `Talk`; approve mic permission if the browser prompts.
- Say one short question.
- Confirm the transcript appears in the text input.
- Edit the transcript if needed.
- Press `Ask` manually.
- Confirm the normal backend answer and trace flow still work.
- Keep Telegram unchanged.

### 10.6K Oom Sakkie Browser TTS Playback - Local Ready

Goal:

- Let the owner hear the latest kiosk answer through local browser text-to-speech without adding a TTS vendor, wake word, always-on microphone, or automatic listen/speak loop.

Implemented locally:

- Added answer-panel controls: `Speak Answer`, `Stop Speech`, and an opt-in `Speak replies` checkbox.
- Uses browser `speechSynthesis` and `SpeechSynthesisUtterance` when available.
- Speech playback language is set to `en-ZA`, with a conservative speaking rate.
- Manual `Speak Answer` reads the currently displayed answer.
- `Speak replies` auto-speaks backend answers only after the explicit `Ask` action returns.
- `Stop Speech` cancels current playback.
- Starting a new backend question cancels any active speech.
- Speaking an answer stops any active browser speech-recognition capture first and does not restart the mic afterwards.
- No backend TTS vendor, no Deepgram/OpenAI Whisper, no wake word, no always-on mic, no Telegram changes, and no farm-data writes.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Local route smoke confirmed `/oom-sakkie` serves the speech controls and `Speak replies` toggle.

Browser-check next:

- Open `/oom-sakkie` in Chrome on the laptop.
- Ask a normal text or drafted voice question.
- Click `Speak Answer` and confirm the answer plays through the laptop speakers.
- Click `Stop Speech` and confirm playback stops.
- Enable `Speak replies`, ask another question, and confirm the answer speaks only after the backend returns.
- Confirm the mic does not start automatically after speech finishes.
- Keep Telegram unchanged.

### 10.6L Oom Sakkie Talk & Ask Correction Window - Local Ready

Goal:

- Add a faster optional local voice turn while preserving a short human correction/cancel window before the backend brain runs.

Implemented locally:

- Added `Talk & Ask` beside the existing tested `Talk` and `Ask` controls.
- `Talk` still only drafts speech into the text box and never submits.
- `Talk & Ask` starts one browser speech-recognition capture, writes the transcript into the existing input, then waits 2 seconds before submitting.
- Added `Cancel Send`, visible only during the 2-second correction window.
- Editing the text during the correction window cancels the pending send.
- Pressing `Ask` manually during the correction window cancels the pending auto-send first, preventing duplicate submissions.
- Browser TTS playback is cancelled before a new backend question starts.
- No always-on microphone, no wake word, no backend STT vendor, no Telegram changes, no LLM default router, and no farm-data writes.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.
- Local route smoke confirmed `/oom-sakkie` serves `Talk & Ask` and `Cancel Send`.

Browser-check next:

- Open `/oom-sakkie` in Chrome on the laptop.
- Click `Talk & Ask`.
- Say one short question.
- Confirm the transcript appears and `Cancel Send` shows during the 2-second window.
- Let it send once and confirm the answer/trace flow works.
- Repeat, then click `Cancel Send` and confirm no backend request is sent.
- Repeat, edit the text during the 2-second window, and confirm auto-send is cancelled.
- Keep Telegram unchanged.

Owner test result:

- Owner tested `Talk & Ask` and confirmed it worked as expected.

### 10.6M Oom Sakkie Optional Continue Conversation - Local Ready

Goal:

- Let the kiosk behave like a simple local voice assistant for consecutive turns, while staying opt-in, half-duplex, and browser-local.

Implemented locally:

- Added `Continue conversation` beside the answer speech controls.
- The toggle is off by default.
- Enabling it also enables `Speak replies`, because continuation is tied to the browser finishing a spoken backend answer.
- Continuation only runs after an automatic spoken backend reply finishes.
- Manual `Speak Answer` does not trigger another listening cycle.
- `Stop Speech`, a new manual `Ask`, or starting a new voice capture cancels continuation for the current spoken reply.
- A speech-run guard prevents a cancelled old utterance from starting a new listen cycle later.
- The next listen cycle uses the existing `Talk & Ask` path, including the 2-second cancel/edit window before sending.
- No always-on microphone, no wake word, no backend STT vendor, no vendor TTS, no Telegram changes, no LLM default router, and no farm-data writes.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.
- Local route smoke confirmed `/oom-sakkie` serves `Continue conversation`.

Browser-check next:

- Open `/oom-sakkie` in Chrome on the laptop.
- Enable `Continue conversation`.
- Confirm `Speak replies` turns on.
- Use `Talk & Ask` for a question.
- Let Oom Sakkie answer and speak.
- Confirm it starts listening again only after the spoken answer finishes.
- Confirm the next recognized question still shows the 2-second `Cancel Send` window.
- Click `Stop Speech` during a spoken reply and confirm it does not start listening again.
- Keep Telegram unchanged.

Owner test result:

- Owner tested optional `Continue conversation` and confirmed it worked.

### 10.6N Oom Sakkie Voice Loop Stop And Cap Guard - Local Ready

Goal:

- Add an explicit hard stop and a bounded loop limit before making the local voice experience any more autonomous.

Implemented locally:

- Added `Stop Conversation`, visible while continuation/listening/speaking/pending-send voice behavior is active.
- `Stop Conversation` cancels pending auto-send, active browser speech recognition, and active browser TTS.
- It turns off `Continue conversation` and resets the continuation counter.
- `Stop Speech`, manual `Ask`, and new voice capture still cancel continuation for the current reply.
- Added a maximum of 5 continued turns before the browser pauses the conversation automatically.
- Added a speech-run guard so a cancelled old utterance cannot trigger another listen cycle later.
- No always-on microphone, no wake word, no backend STT vendor, no vendor TTS, no Telegram changes, no LLM default router, and no farm-data writes.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.
- Local route smoke confirmed `/oom-sakkie` serves `Stop Conversation`.

Browser-check next:

- Enable `Continue conversation` and ask a spoken question.
- Click `Stop Conversation` while the loop is active and confirm it turns off continuation.
- Confirm no mic capture restarts after stopping.
- Let the loop run several short turns and confirm it pauses after 5 continued turns.
- Keep Telegram unchanged.

Owner test result:

- Owner tested voice loop stop/cap behavior and confirmed it worked.

### 10.6O Oom Sakkie Spoken Stop Commands - Local Ready

Goal:

- Let the owner stop the local voice loop hands-free without sending stop/cancel wording to the backend as a farm question.

Implemented locally:

- Added browser-only spoken stop command detection during the `Talk & Ask` auto-submit path.
- Recognized stop phrases include `stop`, `stop conversation`, `stop listening`, `cancel`, `cancel send`, `never mind`, `nevermind`, `pause`, and `pause conversation`.
- When a stop phrase is heard, the browser calls the existing `Stop Conversation` behavior.
- The recognized stop phrase is not submitted to `/api/oom-sakkie/message`.
- Added a small kiosk hint listing practical stop words.
- No always-on microphone, no wake word, no backend STT vendor, no vendor TTS, no Telegram changes, no LLM default router, and no farm-data writes.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.
- Local route smoke confirmed `/oom-sakkie` serves the spoken stop hint.

Browser-check next:

- Enable `Continue conversation`.
- Let Oom Sakkie start the next listening cycle.
- Say `stop conversation`.
- Confirm it stops locally and does not send a backend request.
- Repeat with `cancel` or `never mind`.
- Keep Telegram unchanged.

### 10.6P Oom Sakkie Local Voice Session Log - Local Ready

Goal:

- Make local browser voice-loop testing reviewable without sending browser voice lifecycle events to Supabase or changing backend traces.

Implemented locally:

- Added a `Voice Session` panel under Voice Readiness.
- The panel records the latest 12 browser-local voice events only.
- Events include listening start, transcript drafts, auto-send scheduled/cancelled, backend answered, speaking, speech finished, continuation, stop phrase heard, loop paused, and speech errors.
- Added `Clear` for the local event log.
- The panel explicitly states: `Local browser events only. Nothing here is sent to Supabase.`
- No backend endpoint, no Supabase table, no Telegram changes, no backend STT/TTS vendor, no wake word, no always-on mic, no LLM default router, and no farm-data writes.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.
- Local route smoke confirmed `/oom-sakkie` serves the `Voice Session` panel.

Browser-check next:

- Use `Talk`, `Talk & Ask`, `Speak Answer`, `Continue conversation`, and spoken stop commands.
- Confirm the `Voice Session` panel logs the browser lifecycle events.
- Confirm `Clear` empties the panel.
- Keep Telegram unchanged.

### 10.6Q Oom Sakkie Quick Read-Only Checks - Local Ready

Goal:

- Make the kiosk useful from across the room or on a touchscreen without requiring typing or voice for common safe checks.

Implemented locally:

- Added quick-check buttons under the ask bar:
  - `Attention`
  - `Power`
  - `Weather Today`
  - `Meat Ready`
  - `Sales`
- Each button fills the existing input and calls the existing `ask()` path.
- Quick checks use the same `/api/oom-sakkie/message` endpoint, trace writes, stale warnings, links, and review refresh as typed questions.
- No new backend tools, no write actions, no Telegram changes, no backend STT/TTS vendor, no wake word, no always-on mic, no LLM default router, and no farm-data writes beyond existing Oom Sakkie trace inserts.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.
- Local route smoke confirmed `/oom-sakkie` serves the quick-check buttons.

Browser-check next:

- Open `/oom-sakkie`.
- Click each quick-check button.
- Confirm the answer panel, trace ID, tool used, warnings, links, Recent Checks, and Voice Session log behave normally.
- Keep Telegram unchanged.

### 10.6R Oom Sakkie Read-Only Telemetry Tool Expansion - Local Ready

Goal:

- Expand Oom Sakkie's backend-as-brain tool catalog with approved read-only telemetry/status wrappers that already exist in the Flask backend.

Implemented locally:

- Added typed read-only tools:
  - `power_recent` - wraps the 24-hour power profile.
  - `weather_now` - wraps current weather state.
  - `weather_forecast` - wraps 3-day weather forecast.
  - `irrigation_status` - wraps read-only irrigation status.
- Added rule-first deterministic routing for:
  - recent power/profile/trend questions,
  - current weather questions,
  - forecast/next-few-days weather questions,
  - irrigation/watering status questions.
- Control-style irrigation wording such as `start irrigation` routes to the read-only status tool and returns the explicit warning: no start/stop command was sent.
- Added `Irrigation` to kiosk quick checks.
- No new backend endpoint, no write tool, no hardware command, no Telegram change, no backend STT/TTS vendor, no wake word, no always-on mic, no LLM default router, and no farm-data writes beyond existing Oom Sakkie trace inserts.

Verification:

- Focused Oom Sakkie service tests passed.
- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.

Browser-check next:

- Ask:
  - `show me the recent power profile`
  - `weather now please`
  - `weather forecast for the next few days`
  - `what is the irrigation status`
  - `start irrigation`
- Confirm every response is read-only, risk level `0`, and traces store normally.
- Confirm `start irrigation` does not perform any control action and says no start/stop command was sent.
- Keep Telegram unchanged.

### 10.6S Oom Sakkie Tool Catalog Transparency - Local Ready

Goal:

- Make the backend-as-brain registry visible in the kiosk and through a read-only API so operators and review sessions can see exactly which tools are active, their risk levels, and whether confirmation is required.

Implemented locally:

- Added `list_tool_catalog()` to serialize the runtime `TOOL_REGISTRY`.
- Added `GET /api/oom-sakkie/tools`.
- The endpoint returns tool names, descriptions, risk labels, numeric risk levels, confirmation flags, input schemas, output schemas, and a kiosk policy block:
  - `max_risk_level = 0`
  - `write_tools_enabled = false`
- Added an `Available Checks` kiosk panel that renders the registry and can be refreshed manually.
- No tool is executed by this endpoint.
- No trace is written by this endpoint.
- No Telegram change, backend STT/TTS vendor, wake word, always-on mic, LLM default router, write tool, hardware command, or farm-data write was added.

Verification:

- Focused Oom Sakkie service tests passed.
- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.

Browser-check next:

- Open `/oom-sakkie`.
- Confirm `Available Checks` lists the current runtime tools.
- Confirm all current tools show `risk 0: READ_ONLY`.
- Confirm no current tool says `confirmation required`.
- Refresh the panel and confirm the same list returns.
- Keep Telegram unchanged.

### 10.6T Oom Sakkie Unsupported Action Guard - Local Ready

Goal:

- Make unsupported write/control/message-style requests fail closed with explicit read-only wording instead of a vague clarification, while preserving approved read-only deterministic routes.

Implemented locally:

- Added an unsupported action guard inside `/api/oom-sakkie/message`.
- The guard catches write/control/message-style wording such as:
  - `delete`
  - `send`
  - `post`
  - `start`
  - `stop`
  - `turn on`
  - `turn off`
- The guard only fires after approved read-only rules fail to match.
- Result: `start irrigation` still routes to read-only `irrigation_status` and warns that no start/stop command was sent.
- Unsupported action requests return:
  - `needs_clarification = true`
  - `action_blocked = true`
  - `risk_level = 0`
  - no `tool_used`
  - warning that no write/control/message/physical action was performed.
- The request is still traceable through the existing Oom Sakkie trace path.
- No Telegram change, backend STT/TTS vendor, wake word, always-on mic, LLM default router, write tool, physical control, or farm-data write beyond existing trace inserts was added.

Verification:

- Focused Oom Sakkie service tests passed.
- Full local unittest suite passed.

Browser-check next:

- Ask `send the customer an order message`.
- Confirm the answer says the kiosk is read-only.
- Confirm `action_blocked` behavior through the response/trace if inspecting API output.
- Ask `start irrigation`.
- Confirm it still returns read-only irrigation status and says no start/stop command was sent.
- Keep Telegram unchanged.

### 10.6U Oom Sakkie Browser-Local Session ID - Local Ready

Goal:

- Give Oom Sakkie traces a stable local kiosk session ID so repeated checks from the same browser profile can be grouped during review, without adding login, cookies, or a memory model.

Implemented locally:

- Added `SESSION_STORAGE_KEY = "oom_sakkie_session_id"` in the kiosk JS.
- Added `getSessionId()`:
  - reuses the existing local `oom_sakkie_session_id` when present,
  - creates a `kiosk-<timestamp>-<suffix>` ID when missing,
  - stores it in `window.localStorage`,
  - falls back to an empty string if local storage is unavailable.
- `/api/oom-sakkie/message` now receives `session_id: getSessionId()`.
- This is trace grouping only.
- This is not authentication, not user identity, and not multi-turn memory.
- No Telegram change, backend STT/TTS vendor, wake word, always-on mic, LLM default router, write tool, physical control, or farm-data write beyond existing trace inserts was added.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.

Browser-check next:

- Open `/oom-sakkie` in the kiosk Chrome profile.
- Ask two checks.
- Inspect recent trace records and confirm they carry the same `session_id`.
- Refresh the page and ask another check.
- Confirm the same local session ID is reused.
- Keep Telegram unchanged.

### 10.6V Oom Sakkie Runtime Policy Visibility - Local Ready

Goal:

- Make the current Oom Sakkie safety posture visible from the backend and kiosk so review sessions can confirm the assistant is still local, read-only, and not quietly routing through Telegram, write tools, physical controls, or vendor voice.

Implemented locally:

- Added `modules/oom_sakkie/policy.py`.
- Added `GET /api/oom-sakkie/policy`.
- The endpoint returns:
  - `mode = local_kiosk_read_only`
  - `backend_as_brain = true`
  - `telegram_cutover_enabled = false`
  - `llm_router_enabled = false`
  - `write_tools_enabled = false`
  - `physical_controls_enabled = false`
  - `backend_voice_vendors_enabled = false`
  - `always_on_mic_enabled = false`
  - `browser_speech_mode = push_to_talk_only`
  - `trace_writes_enabled = true`
  - kiosk max risk `0`
  - read-only/write tool counts
  - blocked capabilities list.
- Added a `Safety Status` kiosk panel that renders the policy and can be refreshed manually.
- This is visibility only.
- No tool is executed by this endpoint.
- No trace is written by this endpoint.
- No Telegram change, backend STT/TTS vendor, wake word, always-on mic, LLM default router, write tool, physical control, or farm-data write was added.

Verification:

- Focused Oom Sakkie service tests passed.
- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.

Browser-check next:

- Open `/oom-sakkie`.
- Confirm `Safety Status` shows:
  - local read-only mode,
  - backend brain on,
  - max risk `0: READ_ONLY`,
  - all tools read-only,
  - write tools off,
  - Telegram cutover off,
  - always-on mic off.
- Refresh the panel and confirm values remain stable.
- Keep Telegram unchanged.

### 10.6W Oom Sakkie Review Packet - Local Ready

Goal:

- Give the owner and Claude a single read-only JSON packet for morning review instead of asking them to manually collect policy, tool registry, review summary, and recent traces from separate endpoints.

Implemented locally:

- Added `GET /api/oom-sakkie/review-packet`.
- The packet includes:
  - runtime policy,
  - typed tool catalog,
  - trace review summary,
  - recent kiosk traces,
  - component status codes.
- Added a `Review Packet` link in the kiosk trace filter row.
- This endpoint executes no tools.
- This endpoint writes no traces.
- It only reuses existing read-only registry, policy, and trace-read functions.
- No Telegram change, backend STT/TTS vendor, wake word, always-on mic, LLM default router, write tool, physical control, or farm-data write was added.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.
- Local route smoke confirmed the endpoint returns policy, tools, review summary, and recent traces.

Browser-check next:

- Open `/oom-sakkie`.
- Click `Review Packet`.
- Confirm the JSON includes `policy`, `tools`, `review_summary`, and `recent_traces`.
- Use this packet as part of the Claude review prompt.
- Keep Telegram unchanged.

### 10.6X Oom Sakkie Claude-Review Hardening - Local Ready

Source:

- Claude review after 10.6W flagged small hardening items before daily kiosk use:
  - cap `user_text`,
  - split stale warnings from safety notes,
  - surface continue-conversation settings in policy,
  - derive confirmation-required tools,
  - test low-confidence routing,
  - add a Flask route test that does not require DB config.

Implemented locally:

- Capped incoming `text` in `/api/oom-sakkie/message` to 2,000 chars before trace writing.
- Split tool output and API response fields:
  - `stale_warnings` now stays for stale/limited data warnings,
  - `safety_notes` now carries read-only/no-write/no-control disclaimers.
- Added migration `supabase/migrations/202606060003_add_oom_sakkie_safety_notes.sql`.
- Applied the migration locally; `oom_sakkie_traces` now has `safety_notes_json`.
- Updated trace insert/readback so recent traces and review packets include `safety_notes`.
- Updated kiosk answer and trace-detail rendering to show safety notes separately from stale warnings.
- Mixed action/read requests such as `send weather to John` now answer the read-only weather check but add a safety note that no write/message/control/physical action was performed.
- `/api/oom-sakkie/policy` now:
  - derives `requires_confirmation_tools` from the registry,
  - exposes `continue_conversation_max_turns = 5`,
  - exposes `voice_auto_send_ms = 2000`.
- Added tests for:
  - text cap before trace writing,
  - synthetic low-confidence match,
  - mixed action/read safety note,
  - trace SQL placeholder drift,
  - route-level `/api/oom-sakkie/message` shape without DB config,
  - policy route shape.
- No auth was added to `/api/oom-sakkie/review-packet`; this remains acceptable only under the current local/trusted-LAN kiosk assumption and must be revisited before exposing another device or cutting Telegram over.

Verification:

- Applied `supabase/migrations/202606060003_add_oom_sakkie_safety_notes.sql`.
- Focused Oom Sakkie service tests passed.
- Focused route tests passed.
- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.
- Local route smoke confirmed:
  - unsupported `send the customer an order message` is blocked with `safety_notes`,
  - mixed `send weather to John` answers `weather_today` with a safety note,
  - `start irrigation` remains read-only and has safety notes, not stale warnings,
  - policy exposes `5` continue turns and `2000` auto-send ms,
  - review packet returns expected keys.

Browser-check next:

- Ask `send weather to John`.
- Confirm Oom Sakkie answers the weather check but shows a safety note that no message/action was performed.
- Ask `start irrigation`.
- Confirm it returns irrigation status and safety notes, with no stale warning unless actual data is stale.
- Confirm `Safety Status` shows continue cap `5 turns` and auto-send `2000 ms`.
- Open `Review Packet` and confirm recent traces include `safety_notes`.
- Keep Telegram unchanged.

### 10.6Y Oom Sakkie Review Endpoint Local-Access Guard - Local Ready

Source:

- Claude review flagged `/api/oom-sakkie/review-packet` as useful but sensitive because it exposes recent questions, answers, trace IDs, policy, and tool state.

Implemented locally:

- Added `modules/oom_sakkie/access.py`.
- Sensitive review/admin-style endpoints now require loopback access by default:
  - `GET /api/oom-sakkie/tools`
  - `GET /api/oom-sakkie/policy`
  - `GET /api/oom-sakkie/review-packet`
  - `GET /api/oom-sakkie/traces`
  - `GET /api/oom-sakkie/traces/review-summary`
  - `POST /api/oom-sakkie/traces/<trace_id>/feedback`
- Non-loopback requests receive:
  - HTTP `403`
  - `status = review_access_denied`
- Private LAN review access is denied by default.
- To explicitly allow private LAN review access later, set:
  - `OOM_SAKKIE_REVIEW_ALLOW_PRIVATE_LAN=true`
- `/api/oom-sakkie/message` remains unchanged.
- `/api/oom-sakkie/policy` now reports:
  - review endpoint default: `loopback_only`
  - private LAN override env var name.
- The kiosk `Safety Status` panel shows review access mode.
- No Telegram change, backend STT/TTS vendor, wake word, always-on mic, LLM default router, write tool, physical control, or farm-data write beyond existing trace inserts was added.

Verification:

- Route tests cover loopback allow, non-local denial, and private-LAN env override.
- Focused Oom Sakkie route tests passed.
- Focused Oom Sakkie service tests passed.
- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.

Browser-check next:

- Use the kiosk from the local browser on the same machine.
- Confirm `Available Checks`, `Safety Status`, trace review, feedback, and `Review Packet` still work locally.
- Confirm `Safety Status` shows review access as `loopback_only`.
- Do not enable `OOM_SAKKIE_REVIEW_ALLOW_PRIVATE_LAN` unless explicitly deciding to review from another trusted LAN device.
- Keep Telegram unchanged.

### 10.6Z Oom Sakkie Trace Append-Only DB Guard - Local Ready

Source:

- Claude review noted that trace append-only behavior was enforced by application code only. This was acceptable for local-only kiosk use, but cheap to harden at the DB layer before wider exposure.

Implemented locally:

- Added migration `supabase/migrations/202606060004_lock_oom_sakkie_trace_append_only.sql`.
- The migration creates `public.prevent_oom_sakkie_trace_mutation()`.
- Added triggers that block:
  - `UPDATE` on `public.oom_sakkie_traces`
  - `DELETE` on `public.oom_sakkie_traces`
  - `UPDATE` on `public.oom_sakkie_trace_feedback`
  - `DELETE` on `public.oom_sakkie_trace_feedback`
- Inserts remain allowed.
- This protects the trace and feedback audit trail from accidental mutation through any DB client using normal table access.
- No Telegram change, backend STT/TTS vendor, wake word, always-on mic, LLM default router, write tool, physical control, or farm-data write beyond existing trace inserts was added.

Verification:

- Applied `supabase/migrations/202606060004_lock_oom_sakkie_trace_append_only.sql`.
- Focused Oom Sakkie service and route tests passed.
- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.
- Local route smoke confirmed `/api/oom-sakkie/message` can still insert a new trace after the triggers were applied.

Browser-check next:

- Ask a normal kiosk question.
- Confirm Recent Checks still refresh and show the new trace.
- Keep Telegram unchanged.

### 10.7 Oom Sakkie Specialist Agent Roster - Planned

Source:

- Owner scratch note in `planning/ToDoList.md` requested a future self-sustaining crew of named agents feeding Oom Sakkie/Jarvis: media, developer/code, design, delegation, security, business, analytics, crop/plant specialist, and other growth roles.
- Public Trillion positioning uses a crew model around revenue, code, customers, data, communications, and intelligence. The Amadeus version should be farm-first and governed by the local safety model.

Canonical planning doc:

- `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md`

Planned roster:

- `Oom Sakkie` - user-facing farm brain.
- `Sentinel` - security and safety advisor.
- `Forge` - code steward.
- `Prism` - design director.
- `Ledger` - business and profit advisor.
- `Atlas` - farm data analyst.
- `Rootline` - crop and plant specialist.
- `Herdmaster` - pig management specialist.
- `Butcher` - pork pipeline specialist.
- `Beacon` - media and market voice.
- `Quartermaster` - operations and inventory planner.
- `Gatekeeper` - routing and approval controller.

Hard constraints:

- Oom Sakkie remains the user-facing brain.
- Specialists feed Oom Sakkie; they do not become separate user-facing assistants.
- Every specialist starts read-only or draft-only.
- Human approval is mandatory before writes, customer messages, public posts, Telegram cutover, or physical controls.
- No autonomous loops until trace review and approval policy are stable.

First build candidate:

- Phase 10.7A should create manifest/review scaffolding only:
  - typed specialist manifest schema,
  - runtime-readable roster document or context file,
  - read-only list endpoint or CLI,
  - tests for risk levels and approval flags.
- Do not implement live LLM delegation yet.
- Do not implement the Agent Factory yet.

### 10.7A Oom Sakkie Specialist Manifest Scaffolding - Local Ready

Goal:

- Make the future agent crew concrete and reviewable without creating live agents, autonomous loops, second brains, or tool execution.

Implemented locally:

- Added `modules/oom_sakkie/specialists.py`.
- Added typed `SpecialistManifest` records for:
  - `Sentinel`
  - `Forge`
  - `Prism`
  - `Ledger`
  - `Atlas`
  - `Rootline`
  - `Herdmaster`
  - `Butcher`
  - `Beacon`
  - `Quartermaster`
  - `Gatekeeper`
- Added loopback-protected `GET /api/oom-sakkie/specialists`.
- The endpoint returns:
  - `status = planned_only`
  - `delegation_enabled = false`
  - `autonomous_loops_enabled = false`
  - the specialist manifests.
- Added specialists to `/api/oom-sakkie/review-packet`.
- Added a local `Specialists` kiosk link beside `Review Packet`.
- No live LLM delegation, autonomous worker, write tool, Telegram change, public posting, physical control, or second user-facing brain was added.

Verification:

- Focused Oom Sakkie service and route tests passed.
- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.
- Full local unittest suite passed.

Browser-check next:

- Open `/oom-sakkie` from the local browser.
- Click `Specialists`.
- Confirm the JSON says `planned_only`, `delegation_enabled = false`, and `autonomous_loops_enabled = false`.
- Confirm the names and roles feel right before building any real specialist behavior.

### 10.7B Oom Sakkie Trace Review Advisor - Local Ready

Source:

- Owner scratch note requested an analyst-style helper that can review conversations and suggest what to do next so the system can improve without the owner manually inspecting every trace.

Goal:

- Add the first safe analyst/reviewer slice without creating an autonomous agent, automatic feedback marking, live LLM delegation, or a second user-facing brain.

Implemented locally:

- Added `modules/oom_sakkie/review_advisor.py`.
- Added loopback-protected `GET /api/oom-sakkie/review-advisor`.
- The advisor reads existing trace review summary, reviewed issue traces, and unreviewed traces.
- The endpoint returns:
  - `mode = advisory_only`
  - `autonomous_marking_enabled = false`
  - `writes_feedback = false`
  - a prioritized `review_queue`
  - `suggested_actions`
  - source endpoint statuses.
- Added a local `Review Advisor` kiosk link beside `Review Packet` and `Specialists`.
- The advisor never calls a model, never executes tools, never writes feedback, never changes trace rows, and never marks a conversation correct or incorrect by itself.
- No live LLM delegation, autonomous worker, write tool, Telegram change, public posting, physical control, backend STT/TTS vendor, wake word, always-on mic, or second user-facing brain was added.

Verification:

- Service tests cover advisory-only output, queue prioritization, high problem-rate suggestions, and unconfigured trace-store behavior.
- Route tests cover the local advisor endpoint and non-local denial.
- Frontend contract tests cover the route and kiosk link.

Browser-check next:

- Open `/oom-sakkie` locally.
- Click `Review Advisor`.
- Confirm it opens JSON with `mode = advisory_only`, `writes_feedback = false`, and a useful review queue.
- Use it as a guide for manual trace feedback; do not treat it as automatic review.

### 10.7C Oom Sakkie Review-Surface Caveat Hardening - Local Ready

Source:

- Claude review after 10.7B passed with nits and asked to document the reverse-proxy assumption, make message endpoint access explicit, add proxy/empty-address regression tests, and optionally add a DATABASE_URL-gated append-only trigger integration test.

Implemented locally:

- `/api/oom-sakkie/policy` now includes `message_endpoint_access`:
  - `default = reachable_wherever_flask_is_reachable`
  - `route = POST /api/oom-sakkie/message`
  - note that this is the local brain endpoint, not a review/admin endpoint.
- `/api/oom-sakkie/policy` now includes a `review_endpoints_access.reverse_proxy_caveat`.
- Kiosk `Safety Status` now shows `Message access` separately from `Review access`.
- PRD safety notes now document:
  - review endpoint loopback checks are safe only while Flask sees the real client IP,
  - reverse proxies require trusted proxy handling before relying on loopback protection,
  - `/api/oom-sakkie/message` is intentionally reachable wherever Flask is reachable during the local MVP.
- PRD memory/safety notes now document append-only trace correction policy:
  - corrections are new feedback/superseding rows,
  - original traces are not edited or deleted,
  - future privacy deletion must be explicitly designed instead of weakening triggers.
- Added tests for:
  - `is_review_request_allowed(None)` and empty address denial,
  - current behavior ignoring `X-Forwarded-For`,
  - policy message-access and reverse-proxy caveat fields,
  - specialist manifest valid modes and `Beacon` draft-only/risk-1 invariant,
  - optional DATABASE_URL-gated append-only trigger enforcement.

Verification:

- Focused Oom Sakkie service and route tests passed.
- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.

Browser-check next:

- Open `/oom-sakkie`.
- Confirm `Safety Status` shows both `Review access` and `Message access`.
- Do not deploy behind a reverse proxy until trusted proxy handling is deliberately configured and reviewed.

### 10.7D Oom Sakkie Kiosk Review Advisor Panel - Local Ready

Goal:

- Make the advisory trace-review helper useful from the local kiosk without asking the owner to inspect raw JSON first.

Implemented locally:

- Added a `Review Advisor` panel under the review summary on `/oom-sakkie`.
- The panel is user-action-triggered and does not auto-poll:
  - it loads on page open,
  - refreshes after a kiosk question,
  - refreshes with the Recent Checks refresh,
  - and has its own manual `Refresh` button.
- It calls `GET /api/oom-sakkie/review-advisor?channel=kiosk&days=14&limit=12`.
- It shows:
  - the advisory guard line (`advisory_only`, auto-marking off, feedback writes off),
  - suggested actions,
  - the top review queue items with priority, reason, tool, trace ID, and user text.
- The renderer uses DOM text nodes for trace content and does not inject trace text as HTML.
- No automatic trace marking, model call, autonomous loop, tool execution, Telegram change, write tool, physical control, backend STT/TTS vendor, wake word, always-on mic, or second user-facing brain was added.

Verification:

- Frontend route contracts pin the panel, endpoint fetch, advisory wording, and CSS classes.
- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.

Browser-check next:

- Open `/oom-sakkie`.
- Confirm the `Review Advisor` panel appears below the review summary.
- Click `Refresh`.
- Confirm it shows the guard line plus useful suggestions or a clear empty state.
- Use the panel only to guide manual feedback decisions.

### 10.7E Oom Sakkie Advisor Wording And Proxy-Test Tightening - Local Ready

Source:

- Claude review after 10.7D found the advisor implementation was safe, but the wording said `manual refresh only` while the code refreshes after page load, kiosk questions, and review refreshes. Claude also asked for the inverse forwarded-header regression test.

Implemented locally:

- Updated roadmap/current-review wording to describe the advisor as `user-action-triggered, no auto-polling`.
- Kept the current behavior because it gives immediate post-question advisor feedback without timers, writes, model calls, or hidden automation.
- Added the inverse `X-Forwarded-For` regression test:
  - `REMOTE_ADDR = 203.0.113.10`
  - `HTTP_X_FORWARDED_FOR = 127.0.0.1`
  - expected result: review endpoint denied with `403`.
- Frontend contract now pins that the advisor guard line displays backend `data.mode`, `data.autonomous_marking_enabled`, and `data.writes_feedback`.

Verification:

- Focused route/frontend tests passed locally.

Browser-check next:

- Open `/oom-sakkie`.
- Confirm `Review Advisor` appears after page load.
- Ask a kiosk question and confirm the advisor refreshes after the answer.
- Confirm there is no timed/background polling.

### 10.7F Oom Sakkie Advisor Trace Read Consolidation - Local Ready

Source:

- Claude noted the advisor still used multiple trace-list reads. This was not a blocker at home volume, but consolidating the two trace-list reads is cheap and reduces unnecessary DB pressure from the kiosk advisor panel.

Implemented locally:

- Added `list_review_advisor_traces()` in `modules/oom_sakkie/trace_store.py`.
- It reads reviewed issue traces and unreviewed traces in one combined ranked query.
- It returns separate `issue_traces` and `unreviewed_traces` arrays.
- Updated `modules/oom_sakkie/review_advisor.py` to use the combined trace reader.
- Kept the public `/api/oom-sakkie/review-advisor` response shape unchanged.
- No auto-polling, auto-marking, model call, tool execution, Telegram change, write tool, physical control, backend STT/TTS vendor, wake word, always-on mic, or second user-facing brain was added.

Verification:

- Service tests cover safe unconfigured behavior and the combined ranked query shape.
- Focused Oom Sakkie service and route tests passed.

Browser-check next:

- Open `/oom-sakkie`.
- Confirm the Review Advisor still loads and shows the same queue/suggestions.
- If the panel ever feels slow after trace volume grows, the next optimization is combining review summary and advisor traces into one endpoint-specific query.

### 10.7G Oom Sakkie Advisor SQL Window And Test Hardening - Local Ready

Source:

- Claude review after 10.7F flagged one real low-risk issue and two test tightenings:
  - advisor trace reader had no created-at time window,
  - `_trace_row` positional mapping had no guard,
  - advisor SQL test inspected compiled string constants instead of captured executed SQL.

Implemented locally:

- `list_review_advisor_traces()` now accepts `days` with default `14`.
- The advisor trace CTE now filters:
  - `t.created_at >= now() - (%(days)s::text || ' days')::interval`
- `get_review_advisor()` passes the same `days` value into both review summary and advisor trace reads.
- Added an inline comment documenting that `channel_filter` is a constant SQL fragment and the channel value is still parameter-bound.
- Added tests for:
  - `_trace_row` 19-field positional mapping,
  - captured advisor SQL via a mocked `psycopg.connect`,
  - `union all`, `row_number() over`, `partition by queue_kind`, and the created-at window,
  - route-level `days` argument plumbing into `get_review_advisor`.
- No response-shape change, auto-polling, auto-marking, model call, tool execution, Telegram change, write tool, physical control, backend STT/TTS vendor, wake word, always-on mic, or second user-facing brain was added.

Verification:

- Focused Oom Sakkie service and route tests passed.
- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.

Browser-check next:

- Open `/oom-sakkie`.
- Confirm the Review Advisor still loads.
- Open `/api/oom-sakkie/review-advisor?channel=kiosk&days=14&limit=12` locally and confirm the response remains `advisory_only`.

### 10.7H Oom Sakkie Kiosk Advisor Window And Voice Loop Counter - Local Ready

Source:

- Claude review after 10.7G passed the hardening work and flagged two small UI honesty nits:
  - the Review Advisor used a 14-day window but the kiosk did not say that,
  - the continue-conversation cap was in policy but the running turn count was not visible.

Implemented locally:

- The Review Advisor guard line now shows `last 14 days` from the backend `days` payload.
- The voice status row now has a `Voice loop 0 of 5` counter that appears only while Continue Conversation is enabled.
- The counter updates after each continued spoken turn and hides again when continuation is stopped or disabled.
- Frontend route contracts pin the advisor window label, voice-loop counter element, JS counter renderer, and CSS class.
- No endpoint change, auto-polling, auto-marking, model call, tool execution, Telegram change, write tool, physical control, backend STT/TTS vendor, wake word, always-on mic, or second user-facing brain was added.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend contract tests passed.

Browser-check next:

- Open `/oom-sakkie`.
- Confirm the Review Advisor guard line says `last 14 days`.
- Enable `Speak replies` and `Continue conversation`; confirm the voice-loop counter appears and increments during continued turns.

### 10.7I Oom Sakkie Trace-Driven Router And Power Answer Tightening - Local Ready

Source:

- Owner tested the kiosk question set and confirmed the mic/voice-loop safety behavior worked, but the assistant felt too basic.
- A direct trace review showed the safety path was holding, but several natural phrasings from the test set fell into generic clarification:
  - `which pigs should I look at for slaughter`
  - `are there any sales issues`
  - `do we need to water anything`
  - `do I need to worry about anything today`
  - `what animals do we have on the farm`
  - `what can you do`
- The trace review also exposed a safety wording gap: `turn the pump on` was not detected by the action guard phrase shape.
- Owner feedback marked current power wording as too blunt and less useful than the dashboard.

Implemented locally:

- Added trace-driven deterministic aliases:
  - slaughter wording routes to `meat_planning`,
  - sales issue wording routes to `sales_dashboard`,
  - water/pump wording routes to read-only `irrigation_status`,
  - worry/anything-today wording routes to `farm_attention_summary`,
  - broad animal/pig-on-farm wording routes to `dashboard_summary`.
- Added a read-only capabilities response for `what can you do` / help-style prompts. It lists current checks and explicitly says it cannot send messages, change records, start irrigation, post publicly, or perform physical actions.
- Hardened the action guard for separated control phrases such as `turn the pump on` and `switch the inverter off`.
- Enriched `power_current` wording with battery state, grid watts/state, and data age using fields already returned by the existing backend endpoint.
- Added tests for the new aliases, capability response, dynamic control phrase detection, pump-control read-only behavior, and enriched power-current wording.
- No LLM router, endpoint expansion, auto-polling, auto-marking, tool execution beyond the selected read-only tool, Telegram change, write tool, physical control, backend STT/TTS vendor, wake word, always-on mic, or second user-facing brain was added.

Verification:

- Focused Oom Sakkie service and route tests passed.
- Full local unittest suite passed at 390 tests.
- `node --check static/js/oomSakkie.js` passed.

Browser-check next:

- Re-ask the previously weak natural phrasings above.
- Confirm `turn the pump on` remains read-only and reports that no write/control/physical action was performed.
- Confirm `what can you do` gives a useful current-scope answer.
- Confirm current power now gives more operational context than only battery/solar/load.

### 10.7J Oom Sakkie Capability Fallback Precedence Fix - Local Ready

Source:

- Claude review after 10.7I found that `help` / `help me` capability detection ran before domain rule classification.
- That meant natural prompts such as `help me with the weather` could return the generic capabilities answer instead of routing to the intended read-only tool.

Implemented locally:

- Moved the capabilities response after deterministic tool classification and after the unsupported-action block.
- Domain-specific help prompts now route to the domain tool first:
  - `help me with the weather` -> `weather_today`
  - `I need help with the power` -> `power_current`
  - `can you help me check irrigation` -> `irrigation_status`
  - `help me understand sales` -> `sales_dashboard`
- Bare capability/help prompts still return the read-only capability answer.
- Capability trace confidence now uses `1.0` for consistency with other float confidence values.
- No LLM router, endpoint expansion, auto-polling, auto-marking, write tool, physical control, backend STT/TTS vendor, wake word, always-on mic, Telegram change, live specialist delegation, or second user-facing brain was added.

Verification:

- Focused Oom Sakkie service and route tests passed.
- Full local unittest suite passed at 390 tests.

Browser-check next:

- Ask `help me with the weather`; confirm it routes to weather rather than the capability answer.
- Ask `what can you do`; confirm it still returns the capability answer.

### 10.7K Oom Sakkie Bounded LLM Fallback Router - Local Ready

Source:

- Owner wants Oom Sakkie to become a smarter operating system instead of only a basic rule reader.
- The safe next step is not tool autonomy or writes. It is a bounded fallback classifier that runs only after deterministic rules, unsupported-action blocking, and capability/help fallback have declined.

Implemented locally:

- Added `modules/oom_sakkie/llm_router.py`.
- The LLM router is off unless `OOM_SAKKIE_LLM_ROUTER_ENABLED` is truthy and both `OPENAI_API_KEY` and `OOM_SAKKIE_LLM_ROUTER_MODEL` are configured.
- It uses an OpenAI-compatible chat-completions endpoint, configurable through `OOM_SAKKIE_LLM_ROUTER_URL`, with a bounded timeout.
- The LLM may only return one of the existing approved read-only tools, or a clarification request.
- Returned tool names are validated against the runtime read-only registry; unknown/write tool names are rejected.
- `/api/oom-sakkie/policy` now exposes `llm_router` status, provider shape, env names, allowed tools, max risk, and `can_write = false`.
- `handle_message()` precedence is now:
  1. deterministic rule match,
  2. unsupported action block when no rule matched,
  3. capability/help fallback when no rule matched,
  4. bounded LLM fallback when no rule matched,
  5. normal low-confidence clarification.
- Tests prove:
  - the default router policy is disabled/unconfigured and cannot write,
  - the LLM fallback can select an existing read-only tool,
  - LLM clarification does not call a tool,
  - unsupported actions do not call the LLM,
  - capability requests do not call the LLM,
  - parser rejects unknown/write tool names.
- No write tool, physical control, Telegram cutover, backend STT/TTS vendor, wake word, always-on mic, live specialist delegation, autonomous loop, or second user-facing brain was added.

Verification:

- Focused Oom Sakkie service and route tests passed.
- Full local unittest suite passed at 395 tests.
- `node --check static/js/oomSakkie.js` passed.

Activation notes:

- Do not enable this on the kiosk until Claude reviews the slice.
- When enabled, start with local testing only:
  - `OOM_SAKKIE_LLM_ROUTER_ENABLED=true`
  - `OPENAI_API_KEY=<secret in .env, never chat>`
  - `OOM_SAKKIE_LLM_ROUTER_MODEL=<approved model>`
- Keep Telegram unchanged.
- Keep all tools read-only.

Browser-check next after review and env setup:

- Ask a phrase that no deterministic rule handles but should map to an existing read-only tool.
- Confirm the response includes an intent reason beginning with the LLM route reason.
- Ask an ambiguous phrase and confirm it asks one clarification question.
- Ask a write/control phrase and confirm the LLM is not used and the action is blocked.

### 10.7L Oom Sakkie LLM Fallback Privacy And Failure-Mode Hardening - Local Ready

Source:

- Claude review after 10.7K passed the bounded LLM architecture, but flagged that enabling the router changes the privacy posture because unrouted user text would be sent to the configured LLM endpoint.
- Claude also asked for direct tests of env gating, network/parse failure, and low-confidence LLM tool selection.

Implemented locally:

- `llm_router_policy()` now exposes:
  - `outbound_endpoint_when_enabled`
  - `sends_user_text_when_enabled = true`
- The kiosk Safety Status panel now shows:
  - `LLM fallback`
  - `LLM configured`
  - `LLM sends text`
  - `LLM endpoint`
- Added an inline router comment stating that the LLM-visible tool list is guidance only; parse-time registry allowlist validation remains the real safety gate.
- Added tests that prove:
  - disabled/missing env configuration returns `None` without making a network call,
  - network failure returns `None`,
  - invalid JSON returns `None`,
  - low-confidence LLM tool selection falls back to clarification instead of executing a tool,
  - the frontend policy panel renders the LLM privacy fields.
- No behavior widening, write tool, physical control, Telegram cutover, backend STT/TTS vendor, wake word, always-on mic, live specialist delegation, autonomous loop, or second user-facing brain was added.

Verification:

- Focused Oom Sakkie service, route, and frontend contract tests passed.
- Full local unittest suite passed at 399 tests.
- `node --check static/js/oomSakkie.js` passed.

Browser-check next:

- Open `/oom-sakkie`.
- Confirm Safety Status shows LLM fallback off, LLM configured no, LLM sends text off, and LLM endpoint not used.
- Do not enable the router until a deliberate local experiment window is chosen.

### 10.7M Oom Sakkie LLM Router Smoke Harness - Local Ready

Source:

- Owner agreed to run a local LLM fallback experiment before asking for another Claude review.
- Current `.env` does not yet contain `OOM_SAKKIE_LLM_ROUTER_ENABLED`, `OPENAI_API_KEY`, or `OOM_SAKKIE_LLM_ROUTER_MODEL`, so a live outbound test cannot run yet.

Implemented locally:

- Added `scripts/oom_sakkie_llm_router_smoke.py`.
- The script loads `.env`, prints router enabled/configured/can-write/privacy status without printing secrets, and refuses to call the network unless the router is fully configured.
- When configured, it sends a small fixed prompt set through `handle_message()` with channel `kiosk_llm_smoke`, so traces are separated from normal kiosk use.
- The prompt set includes:
  - ambiguous read-only routing prompts,
  - an unsafe delete request that must stay blocked,
  - a capability prompt that must stay off the LLM path.

Verification:

- Smoke harness dry run confirmed router disabled/unconfigured and skipped without an outbound call.
- `python -m py_compile scripts/oom_sakkie_llm_router_smoke.py` passed.
- Focused Oom Sakkie service, route, and frontend contract tests passed.

How to run after env setup:

```powershell
.\venv\Scripts\python.exe -c "from scripts.oom_sakkie_llm_router_smoke import main; raise SystemExit(main())"
```

Required `.env` values, set locally only and never pasted into chat:

```text
OOM_SAKKIE_LLM_ROUTER_ENABLED=true
OPENAI_API_KEY=<secret>
OOM_SAKKIE_LLM_ROUTER_MODEL=<approved OpenAI-compatible chat model>
```

### 10.7N Oom Sakkie LLM Router Local Smoke - Verified

Source:

- Owner added a valid `OPENAI_API_KEY`, enabled the router, and set `OOM_SAKKIE_LLM_ROUTER_MODEL=gpt-5.4-mini`.

Verified locally:

- Diagnostic script reached `https://api.openai.com/v1/chat/completions` and returned `HTTP 200`.
- The API resolved the model to `gpt-5.4-mini-2026-03-17`.
- Smoke harness with router enabled returned:
  - `give me the energy situation` -> `power_current`
  - `check if the outside conditions are a problem` -> `weather_now`
  - `which farm area should I inspect first` -> `farm_attention_summary`
  - `delete a pig record` -> action blocked before LLM/tool execution
  - `what can you do` -> capability answer, no LLM tool
- Router prompt was tuned to prefer the best safe read-only tool for broad operational questions, while still using clarification when no approved tool is a reasonable fit.
- Tests were hardened so local `.env` router enablement does not make unit tests spend API calls or depend on external state.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` passed.
- Full local unittest suite passed at 399 tests with router env enabled locally.
- `node --check static/js/oomSakkie.js` passed.
- Smoke traces are separated under channel `kiosk_llm_smoke`.

Operational rule:

- Keep the router on only for the local experiment window until traces are reviewed.
- Keep Telegram unchanged.
- Keep all tools read-only.
- Mark any bad LLM-routed traces honestly so the Review Advisor can drive the next tuning pass.

### 10.7O Oom Sakkie LLM Answer Composer - Local Ready

Source:

- Owner tested the LLM router but the kiosk still felt basic.
- Diagnosis: the LLM router only improves tool selection for questions that deterministic rules do not catch. Questions already matched by rules still use the same deterministic formatter.
- The next safe step is answer composition after tool execution, not letting the LLM choose actions or modify tool results.

Implemented locally:

- Added `modules/oom_sakkie/llm_answer.py`.
- Added independent env gate `OOM_SAKKIE_LLM_ANSWER_ENABLED`.
- The answer composer runs only after a read-only tool has already returned a deterministic answer.
- It receives only user text, tool name, deterministic answer, stale warnings, and safety notes.
- It cannot choose tools, call tools, write records, send messages, or perform control actions.
- Unsafe model output claiming a write/control action such as saved/sent/started/stopped is rejected and the deterministic answer is used instead.
- Runtime policy and kiosk Safety Status now expose:
  - `LLM answer`,
  - `Answer sends summary`,
  - composer configured/enabled/can-write state.
- Smoke script now prints final answers and composer enabled/configured state.

Verified locally:

- With composer off, smoke still returned the old deterministic summaries.
- With `OOM_SAKKIE_LLM_ANSWER_ENABLED=true` for the smoke process:
  - `give me the energy situation` produced a smoother power answer while preserving the same facts.
  - `check if the outside conditions are a problem` produced a smoother weather answer while preserving the same facts.
  - `which farm area should I inspect first` changed from a raw attention list to an operator-style answer: start with litter attention because piglets need newborn health records.
  - `delete a pig record` remained action-blocked.
  - `what can you do` remained the local capability answer.
- Full local unittest suite passed at 402 tests.
- `node --check static/js/oomSakkie.js` passed.

How to enable locally after review:

```text
OOM_SAKKIE_LLM_ANSWER_ENABLED=true
```

Operational rule:

- Treat this as presentation-only. It may improve wording, but the deterministic tool result remains the source of truth.
- Keep router/composer traces under review during the local experiment.
- If answers become too fluffy, turn this one env var off and the system falls back to deterministic wording.

### 10.7P Oom Sakkie Alive State And Provenance Strip - Local Ready

Source:

- Owner wanted the kiosk to feel more alive and useful, inspired by the Usejarvis reference.
- External Usejarvis source was inspected read-only and documented at `docs/01-architecture/JARVIS_EXTERNAL_REFERENCE_REVIEW.md`.
- Decision: borrow the state/provenance ideas, not the runtime, installer, sidecar, or desktop-control code.

Implemented locally:

- Added `pipeline` metadata to `/api/oom-sakkie/message` responses:
  - `route_source`,
  - `answer_source`,
  - `state`,
  - `llm_router_used`,
  - `llm_answer_used`,
  - `tool_checked`.
- Added a visible answer pipeline strip on `/oom-sakkie`:
  - Route,
  - Answer,
  - State.
- Added trace details for intent confidence and route reason.
- Made the top status pill stateful with visual differences for:
  - listening,
  - checking,
  - speaking,
  - answered,
  - blocked/error.
- Added frontend contract tests so the provenance strip and state metadata do not disappear silently.
- Added service tests so rule routing, LLM routing, action blocking, capability answers, deterministic answers, and LLM-composed answers expose the correct pipeline metadata.

Verified locally:

- Focused Oom Sakkie service/frontend tests passed.
- Full local unittest suite passed at 402 tests.
- `node --check static/js/oomSakkie.js` passed.

Operational rule:

- This is visibility only. It does not add new tools, writes, Telegram cutover, physical control, wake word, always-on mic, or specialist delegation.
- Use this strip during testing to tell whether a basic answer is basic because:
  - the route was rule-based,
  - the answer composer was off,
  - the answer composer fell back,
  - or the LLM router selected the tool.

### 10.7Q Oom Sakkie Presence Orb And Stronger Spoken Voice - Local Ready

Source:

- Owner tested 10.7P and reported that answers still felt like the system was reading raw results, not speaking like an agent.
- Owner also clarified the desired kiosk feel: a futuristic living circle/entity that moves while listening, thinking, and speaking, then brings the information forward.

Implemented locally:

- Strengthened `modules/oom_sakkie/llm_answer.py`:
  - answer composer now identifies as Oom Sakkie, the farm operating co-pilot,
  - explicitly says not to read tables back like a clerk,
  - leads with operational meaning before facts,
  - avoids generic assistant openers,
  - keeps the same hard fact boundary: use only backend answer, stale warnings, and safety notes,
  - still rejects output that claims actions such as saved/sent/started/stopped/changed,
  - raised answer-composer temperature from `0.2` to `0.55` for less flat wording.
- Added a central `/oom-sakkie` agent presence panel:
  - animated orb,
  - ring/core/scan layers,
  - visible presence line,
  - state-specific behavior for idle/listening/checking/answered/speaking/blocked/error.
- Wired the orb to the existing status state machine in `static/js/oomSakkie.js`; it does not open the mic, call tools, or run anything independently.
- Added frontend contract tests for the presence markup, JS state wiring, and CSS animation hooks.
- Added a backend prompt contract test so the answer composer does not drift back to generic/read-the-table wording.

Verified locally:

- `python -m unittest tests.test_oom_sakkie_service tests.test_frontend_route_contracts` -> 68 tests OK, 1 skipped.
- `node --check static/js/oomSakkie.js` passed.

Operational rule:

- This is presentation and voice only. It adds no new authority, no write path, no physical control, no wake word, no always-on mic, no Telegram cutover, and no live specialist delegation.
- To hear the improved wording, `OOM_SAKKIE_LLM_ANSWER_ENABLED=true` must be set and Flask must be restarted.
- If the composer ever gets too fluffy, turn off `OOM_SAKKIE_LLM_ANSWER_ENABLED`; deterministic wording remains the fallback.

### 10.7R Oom Sakkie Capped Context Briefing Composer - Local Ready

Source:

- Owner confirmed the orb was visible but known-tool answers still felt like raw backend summaries.
- Diagnosis: the LLM answer composer was active, but it only received the deterministic one-line summary, stale warnings, and safety notes. It could rephrase but not brief from structured read-only data.

Implemented locally:

- `compose_answer_with_llm()` now accepts `raw_context`.
- `handle_message()` passes the read-only tool result's `raw` payload, or the tool result itself, into the composer.
- The answer payload includes capped `backend_context` via `_safe_json_excerpt()`:
  - JSON serialized with `default=str`,
  - ASCII-safe,
  - capped at 3000 characters,
  - still after read-only tool execution only.
- Composer prompt now says:
  - use only backend answer/context/warnings/notes,
  - prioritize what the owner should look at first when multiple items exist,
  - do not recite every ID unless useful for inspection.
- Runtime policy and kiosk Safety Status now disclose `Answer sends context` / `sends_capped_tool_context_when_enabled`.
- Added tests for:
  - policy disclosure,
  - prompt/context contract,
  - frontend policy field rendering.

Verified locally:

- `python -m unittest tests.test_oom_sakkie_service tests.test_frontend_route_contracts` -> 68 tests OK, 1 skipped.
- `node --check static/js/oomSakkie.js` passed.
- Local smoke with `OOM_SAKKIE_LLM_ANSWER_ENABLED=true`:
  - `what needs attention today?` -> answer source `llm_composer`; prioritizes litter queue.
  - `which farm area should I inspect first?` -> route `llm_router`, answer source `llm_composer`; identifies litter area first and highlights the most urgent litter from structured context.
  - `what is the power doing now?` -> answer source `llm_composer`; concise power briefing.
  - `what happened with the weather today?` -> answer source `llm_composer`; includes rain, temperature, and wind from structured context.

Operational rule:

- This is still read-only presentation. The composer cannot select tools, call tools, write records, send messages, or control equipment.
- It does send more farm context outbound when enabled, so keep the Safety Status disclosure visible and rotate/disable the env var if testing should stop.

### 10.7S Oom Sakkie Read-Only Operating Brief Tool - Local Ready

Source:

- Owner wants Oom Sakkie to do more work per turn instead of answering one narrow backend read at a time.
- Safe next slice: one composite read-only tool that gathers existing read-only checks and lets the briefing composer summarize them.

Implemented locally:

- Added `farm_operating_brief` to the Oom Sakkie tool registry.
- The tool calls existing read-only wrappers only:
  - `farm_attention_summary`,
  - `power_current`,
  - `weather_today`,
  - `irrigation_status`.
- It combines summaries, links, stale warnings, safety notes, and raw per-section context into one tool result.
- Added deterministic routing for:
  - `farm operating brief`,
  - `farm brief`,
  - `daily brief`,
  - `morning brief`,
  - `status report`,
  - `jarvis check`,
  - `full farm check`,
  - `what should I know`,
  - `bring me up to speed`.
- Added a kiosk quick action: `Brief`.
- Updated LLM-router guidance so broad briefing/status-report prompts choose `farm_operating_brief`.
- Tightened the answer-composer prompt for operating briefs: at most three short sentences covering first priority, system status, and safety/stale note.
- Added tests for:
  - registry contract,
  - deterministic routing,
  - composite brief output,
  - quick-action markup,
  - voice prompt length rule.

Verified locally:

- `python -m unittest tests.test_oom_sakkie_service tests.test_frontend_route_contracts` -> 69 tests OK, 1 skipped.
- `node --check static/js/oomSakkie.js` passed.
- Local smoke with `OOM_SAKKIE_LLM_ANSWER_ENABLED=true`:
  - `give me the farm operating brief` -> `tool = farm_operating_brief`, `answer_source = llm_composer`.
  - `bring me up to speed` -> `tool = farm_operating_brief`, `answer_source = llm_composer`.
  - `what should i know before i go outside` -> `tool = farm_operating_brief`, `answer_source = llm_composer`.

Operational rule:

- This is not autonomy. It is one user-initiated read-only turn that aggregates existing read-only checks.
- No write tools, physical controls, Telegram cutover, always-on mic, wake word, or specialist delegation were added.

### 10.7T Oom Sakkie Operating Brief Required Sections - Local Ready

Source:

- Owner tested the operating brief and reported that weather was omitted from the spoken answer.
- Diagnosis:
  - The composite tool did call weather, but the composer could treat sections as optional.
  - The previous capped context used the full nested raw payload, so important sections could be crowded by verbose earlier sections.
  - The safety filter could reject valid negated safety wording such as `No start/stop command was sent` because it matched `sent`.

Implemented locally:

- `farm_operating_brief` now returns compact `llm_context`:
  - `kind = farm_operating_brief`,
  - `required_sections = ["attention", "power", "weather", "irrigation"]`,
  - compact per-section status, summary, stale warnings, and safety notes.
- `handle_message()` now prefers `tool_result["llm_context"]` over verbose raw payload when calling the answer composer.
- Composer prompt now explicitly says: for `farm_operating_brief`, mention all required sections: attention/priority, power, weather, and irrigation.
- Unsafe-output filter now still rejects positive action claims, but allows negated safety statements such as `No start or stop command was sent`.
- Added tests for:
  - compact `llm_context` shape,
  - weather included in compact context,
  - service passes compact context to composer,
  - prompt includes required-section rule,
  - negated safety wording is accepted while unsafe positive action claims remain rejected.

Verified locally:

- `python -m unittest tests.test_oom_sakkie_service tests.test_frontend_route_contracts` -> 70 tests OK, 1 skipped.
- `node --check static/js/oomSakkie.js` passed.
- Note: a direct live diagnostic hit Google Sheets quota `429` while repeatedly checking the operating brief. Avoid repeated live smokes until the quota cools down; use the browser once for confirmation.

Operational rule:

- The operating brief must include all four sections, even if one section is only a short `no issue` line.
- This remains read-only and user-initiated only.

### 10.7U Oom Sakkie Top Voice Controls - Local Ready

Source:

- Owner confirmed the operating brief works, but the `Talk` controls were too low on the page and required scrolling.

Implemented locally:

- Moved `Talk` and `Talk & Ask` into the top presence panel.
- Kept the text input and `Ask` submit button in the bottom input bar.
- Added `.oom-presence-actions` styling so voice controls are visible in the first viewport and touch-friendly.
- Added responsive CSS so the controls stay usable on narrow screens.
- Added a frontend contract assertion that the voice buttons are inside the presence panel and not inside the bottom form.

Verified locally:

- Pending current full-suite run in this batch.

Operational rule:

- This is placement only. The microphone still opens only after an explicit button press; no always-on mic, wake word, backend STT/TTS, write tool, or physical control was added.

### 10.7V Oom Sakkie Human-Approved Learning Queue - Local Ready

Source:

- Owner wants the system to become more sustainable and learn from itself, but under human approval.
- Safe first slice: convert reviewed trace feedback into improvement proposals without changing code, prompts, tools, routes, or farm data automatically.

Implemented locally:

- Added `modules/oom_sakkie/learning_advisor.py`.
- Added protected endpoint `GET /api/oom-sakkie/learning-advisor`.
- Added kiosk `Learning Queue` panel.
- Learning Queue is deterministic and advisory-only:
  - no LLM call,
  - no code write,
  - no feedback write,
  - no farm-data write,
  - human approval required.
- Proposal types:
  - `routing_review` for `wrong_tool`,
  - `data_freshness_review` for `stale_or_missing_data`,
  - `answer_style_review` for `bad_wording`,
  - `tool_gap_review` for `needs_follow_up`,
  - `tool_pattern_review` when repeated issue patterns appear for one tool.
- UI renders proposals with `.textContent`; trace/user text is not inserted as HTML.
- Learning Queue refreshes with the existing review data and also has its own Refresh button.
- Added tests for:
  - proposal generation,
  - advisory-only safety flags,
  - protected route success and non-local denial,
  - frontend panel/JS contract.

Verified locally:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 83 tests OK.
- `node --check static/js/oomSakkie.js` passed.

Operational rule:

- This is not self-modifying software. It is an evidence queue. Codex/the owner still decide and apply any code or prompt change manually.
- Do not let the Learning Queue auto-approve, auto-edit, or auto-run a code-generation step without a separate explicit approval gate.

### 10.7W Oom Sakkie Explicit LLM Learning Analyst - Local Ready

Source:

- Owner confirmed the long-term plan: one specialist should learn/analyze traces with an LLM, another builder specialist can later prepare patches, and all changes stay human-approved.
- Safe next slice: build the LLM analyst as an explicit protected action, not an automatic loop.

Implemented locally:

- Added `modules/oom_sakkie/learning_llm.py`.
- Added env gate `OOM_SAKKIE_LLM_LEARNING_ENABLED`.
- Added protected endpoint `POST /api/oom-sakkie/learning-advisor/analyze`.
- Added `Analyze` button to the kiosk Learning Queue.
- The endpoint:
  - reads the same reviewed issue traces as the deterministic Learning Queue,
  - sends capped issue trace excerpts and deterministic proposals to the configured OpenAI-compatible model only when explicitly triggered,
  - returns validated learning proposals,
  - rejects unknown proposal kinds,
  - forces `approval_required = true`,
  - never writes code, feedback, prompts, tools, routes, or farm data.
- The kiosk renders LLM proposals in the same Learning Queue panel using `.textContent`.

Policy and safety:

- Disabled unless `OOM_SAKKIE_LLM_LEARNING_ENABLED=true`.
- Uses existing model/key envs: `OOM_SAKKIE_LLM_ROUTER_MODEL` and `OPENAI_API_KEY`.
- Protected by the same review endpoint access guard.
- `GET /learning-advisor` stays deterministic and free; the LLM only runs on explicit `POST /analyze`.

Verified locally:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 87 tests OK.
- `node --check static/js/oomSakkie.js` passed.

Operational rule:

- This is still not the builder. It is the Learning Analyst only.
- A future Forge/Builder specialist may prepare a patch from an approved proposal, but this endpoint must never apply code changes.

### 10.7X Oom Sakkie Trace-Driven Composer Lane Guard - Local Ready

Source:

- Owner marked several traces as `bad_wording`.
- Pattern found in live traces: single-tool answers were adding cross-system disclaimers such as `Power and weather were not evaluated here`.
- That is safe but not human; Oom Sakkie sounded like an audit log instead of an operator.

Implemented locally:

- Tightened the answer-composer prompt:
  - non-brief tools must stay in their own lane,
  - do not mention unrelated systems that were not checked,
  - do not say `no stale warning` or `no safety note` when there are none.
- Added post-composer guard:
  - for non-`farm_operating_brief` tools, reject answers containing off-topic disclaimer fragments such as `not part of this`, `not evaluated`, `weren't evaluated`, `not provided here`, `no stale warning`, or `no safety note`,
  - normalizes curly apostrophes before checking,
  - falls back to deterministic wording when rejected.
- Kept `farm_operating_brief` exempt because it is allowed to discuss multiple systems.
- Added tests for:
  - prompt rule,
  - off-topic single-tool disclaimer rejection,
  - curly-apostrophe `weren’t evaluated` case,
  - safe negated action wording remains accepted.

Verified locally:

- Focused Oom Sakkie service/routes/frontend tests: `88 tests OK`.
- `node --check static/js/oomSakkie.js` passed.
- Live style check after guard:
  - meat answer no longer mentions weather/power,
  - weather forecast no longer says `No stale warning`,
  - irrigation answer with off-topic cross-system wording is rejected and falls back to deterministic wording.

Operational rule:

- This is trace-driven wording hardening only. It adds no tool authority, writes, controls, or autonomy.

### 10.7Y Oom Sakkie Learning Build Brief Packet - Local Ready

Purpose:

- Bridge the Learning Queue toward a future Forge/Builder workflow without allowing the kiosk to edit code.
- Turn one human-reviewed learning proposal into a scoped engineering packet that Codex, Claude, or a human can inspect.

Implemented locally:

- Added `modules/oom_sakkie/learning_packet.py`.
- Added protected endpoint `POST /api/oom-sakkie/learning-advisor/build-packet`.
- Added `Build Brief` buttons to Learning Queue proposals.
- Added hidden kiosk panel `oom_learning_packet` that renders the generated packet with `.textContent`.
- The packet includes:
  - proposal summary,
  - recommended files to inspect,
  - verification commands,
  - out-of-scope constraints,
  - a markdown brief suitable for review.

Safety:

- No LLM call.
- No code write.
- No tool/prompt mutation.
- No feedback write.
- No farm-data write.
- Review endpoint access guard applies.
- Human approval remains required before any implementation.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 92 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 417 tests OK.

### 10.7Z Oom Sakkie Human-Approved Implementation Queue - Local Ready

Purpose:

- Make the system more proactive without giving it implementation authority.
- Auto-prepare review briefs when the Learning Queue has strong enough evidence.
- Keep the owner in control: briefs can be opened, ignored, or manually approved for a future coding session.

Implemented locally:

- Added deterministic implementation-queue builder in `modules/oom_sakkie/learning_packet.py`.
- Added protected endpoint `GET /api/oom-sakkie/learning-advisor/implementation-queue`.
- Added kiosk `Implementation Queue` panel.
- The queue auto-prepares in-memory build briefs only when:
  - a proposal is high priority,
  - a repeated tool pattern is detected,
  - or evidence mentions two or more issue traces.
- Added `Open Brief` buttons that display the generated packet in the existing text-only build-brief panel.

Safety:

- No LLM call.
- No code write.
- No patch application.
- No prompt/tool mutation.
- No feedback write.
- No farm-data write.
- Review endpoint access guard applies.
- Human approval remains required before implementation.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 95 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 420 tests OK.

### 10.8A Oom Sakkie Approve For Build Gate - Local Ready

Purpose:

- Add the first explicit approval gate after a build brief.
- Create a structured build request object that a future Forge/Builder agent can consume.
- Keep approval separate from code generation and deployment.

Implemented locally:

- Added `approve_build_request()` in `modules/oom_sakkie/learning_packet.py`.
- Added protected endpoint `POST /api/oom-sakkie/learning-advisor/approve-build`.
- Added `Approve for Build` button to the build brief panel.
- Added approval result rendering with:
  - build request ID,
  - `builder_enabled = false`,
  - `writes_code_now = false`,
  - `applies_changes_now = false`,
  - next gate: `builder_agent_review_and_patch_approval`.

Safety:

- Approval does not edit files.
- Approval does not run a builder.
- Approval does not apply a patch.
- Approval does not deploy.
- Approval does not change prompts/tools.
- Approval does not write farm data.
- The future Builder/Forge step must still be explicitly run and separately reviewed.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 99 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 424 tests OK.

### 10.8B Oom Sakkie Persistent Build Request Queue - Local Ready

Purpose:

- Make approved build requests durable so they survive refresh and can become the input queue for a future Forge/Builder agent.
- Keep approval separate from implementation, patch review, and deploy approval.

Implemented locally:

- Added `modules/oom_sakkie/build_request_store.py`.
- Added Supabase migration `supabase/migrations/202606070001_create_oom_sakkie_build_requests.sql`.
- Added append-only table `public.oom_sakkie_build_requests`.
- Added DB checks that force:
  - `mode = build_request_only`,
  - `status = approved_for_build`,
  - `builder_enabled = false`,
  - `writes_code_now = false`,
  - `applies_changes_now = false`.
- Added append-only update/delete blocking triggers.
- `POST /api/oom-sakkie/learning-advisor/approve-build` now attempts to persist the build request.
- Added protected `GET /api/oom-sakkie/build-requests`.
- Added kiosk `Approved Build Requests` panel.

Safety:

- Persistence records approval only.
- No Builder/Forge agent is run.
- No code is written.
- No patch is applied.
- No deploy is triggered.
- No prompt/tool/farm-data mutation occurs.
- If `DATABASE_URL` is missing or migration is not applied, the store reports that clearly instead of pretending persistence worked.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 105 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 430 tests OK.

### 10.8C Oom Sakkie Build Request Event Log - Local Ready

Purpose:

- Preserve append-only build request history while still allowing corrections such as `ignored` or `review_note`.
- Avoid deleting or editing approved build requests, including smoke/test records.

Implemented locally:

- Added migration `supabase/migrations/202606070002_create_oom_sakkie_build_request_events.sql`.
- Added append-only table `public.oom_sakkie_build_request_events`.
- Added `record_build_request_event()` in `modules/oom_sakkie/build_request_store.py`.
- `approve-build` now records an `approved` event after successful persistence.
- `GET /api/oom-sakkie/build-requests` returns the latest event per request.
- Added protected `POST /api/oom-sakkie/build-requests/<build_request_id>/events`.
- Added kiosk `Ignore` action for build requests.

Safety:

- Events are append-only.
- No original request is edited or deleted.
- Allowed event types are `approved`, `ignored`, and `review_note`.
- Event recording does not run a builder, edit files, apply patches, deploy, mutate prompts/tools, or touch farm data.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 109 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- Applied migration `supabase/migrations/202606070002_create_oom_sakkie_build_request_events.sql`.
- Marked synthetic persistence smoke request `OSK-BUILD-7073A29F701E` as `ignored` through append-only event route.
- `python -m unittest` -> 434 tests OK.

### 10.8D Oom Sakkie Forge Handoff Packet - Local Ready

Purpose:

- Prepare the exact packet a future Builder/Forge agent would consume.
- Stop one step before execution so Claude can review the safety boundary.

Implemented locally:

- Added `modules/oom_sakkie/forge_handoff.py`.
- Added protected endpoint `POST /api/oom-sakkie/build-requests/forge-handoff`.
- Added kiosk `Forge Handoff` button on approved build requests.
- Added text-only handoff panel.
- The handoff contains:
  - build request ID,
  - objective,
  - evidence,
  - approved scope,
  - verification commands,
  - no-go rules,
  - original build brief,
  - required pre-patch output.

Safety:

- Does not run a Builder/Forge agent.
- Does not edit files.
- Does not apply patches.
- Does not deploy.
- Requires owner to explicitly run the future Builder step.
- Requires separate patch review.
- Requires separate deploy approval.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 113 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 438 tests OK.

Claude review gate:

- This is the right checkpoint before building actual Builder/Forge execution.
- Ask Claude to review `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md` before the next step.

### 10.8E Oom Sakkie Forge Handoff Persisted-ID Hardening - Local Ready

Source:

- Claude review flagged that `POST /api/oom-sakkie/build-requests/forge-handoff` accepted an arbitrary `build_request` payload.
- The output was text-only and not directly unsafe, but it weakened the invariant that only persisted approved requests can generate Forge handoffs.

Implemented locally:

- Added `get_build_request()` to `modules/oom_sakkie/build_request_store.py`.
- Changed Forge Handoff route to accept `build_request_id` only.
- Route now loads the persisted build request before generating the handoff.
- Kiosk now sends only `build_request_id` for Forge Handoff.
- Added tests for:
  - missing DB config lookup behavior,
  - route lookup through persisted store,
  - 404 when the build request is not found,
  - frontend contract that only the ID is sent.

Safety:

- Browser payload is no longer treated as the build-request source of truth.
- Forge Handoff can only be generated for a persisted build request.
- Still does not run a builder, edit files, apply patches, deploy, mutate prompts/tools, or touch farm data.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 114 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 439 tests OK.

### 10.8F Oom Sakkie Patch Proposal Gate - Local Ready

Source:

- Claude review recommended adding a patch-review gate before the first real Builder/Forge run.
- The existing Forge Handoff packet already says patch review is required, but no persisted patch proposal/review surface existed yet.

Implemented locally:

- Added `modules/oom_sakkie/patch_proposal_store.py`.
- Added Supabase migration `supabase/migrations/202606070003_create_oom_sakkie_patch_proposals.sql`.
- Added append-only `public.oom_sakkie_patch_proposals`.
- Added append-only `public.oom_sakkie_patch_proposal_events`.
- Added DB constraints that keep `applies_patch = false` and `deploys = false`.
- Added protected `POST /api/oom-sakkie/build-requests/<build_request_id>/patch-proposals`.
- Added protected `GET /api/oom-sakkie/patch-proposals`.
- Added protected `POST /api/oom-sakkie/patch-proposals/<patch_proposal_id>/events`.
- Added kiosk `Patch Proposal Gate` panel where the owner can paste Builder/Forge output.
- Added `Record Patch Proposal` action on approved build request rows.
- Added patch review events:
  - `approved_for_patch`,
  - `rejected`,
  - `review_note`.

Safety:

- `Approve Patch` means approved for manual patch application outside the kiosk.
- Does not run a builder.
- Does not edit files.
- Does not apply patches.
- Does not deploy.
- Does not mutate prompts/tools/farm data.
- Stores proposals and review decisions append-only.

Verification:

- Applied migration `supabase/migrations/202606070003_create_oom_sakkie_patch_proposals.sql`.
- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 124 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 449 tests OK.

Next gate:

- Ask Claude to review `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md` before the first real Builder/Forge run.
- First real Builder/Forge run remains manual:
  1. Generate Forge Handoff.
  2. Paste prompt into separate Builder/Forge tool.
  3. Read Builder plan/output.
  4. Paste proposal into Patch Proposal Gate.
  5. Approve or reject the proposal.
  6. Apply any patch manually outside the kiosk only after approval.
  7. Run verification before commit/deploy.

### 10.8G Oom Sakkie Patch Gate Review Nits - Local Ready

Source:

- Claude passed Phase 10.8E-F and flagged small follow-ups:
  - stale payload shape in one non-local Forge Handoff test,
  - confusing FK-backed `503` if a patch proposal event targeted a missing proposal,
  - confirm the advisor `last 14 days` guard is pinned by frontend contract tests.

Implemented locally:

- Updated `test_forge_handoff_route_denies_non_local_review_access` to send the current `build_request_id` payload.
- Confirmed `tests/test_frontend_route_contracts.py` pins `last ${data.days || 14} days`.
- Added `get_patch_proposal()` to `modules/oom_sakkie/patch_proposal_store.py`.
- `record_patch_proposal_event()` now pre-checks the target proposal and returns `404 patch_proposal_not_found` before insert when missing.
- Added tests for `get_patch_proposal()` not-configured behavior and the missing-proposal event path.

Safety:

- Still does not run a builder.
- Still does not edit files.
- Still does not apply patches.
- Still does not deploy.
- Still does not mutate prompts/tools/farm data.
- Patch proposal events remain append-only review records only.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 125 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 450 tests OK.

Next strategic gate:

- Decide whether to build Deploy Approval Gate before the first production-affecting Builder patch.
- For a tiny first local-only patch, manual deploy/commit review is acceptable; for anything touching alerts, orders, customer messaging, telemetry writes, or production behavior, build the deploy gate first.

### 10.8H Oom Sakkie Deploy Approval Gate - Local Ready

Status: local-ready.

Purpose:

- Close the last approval-gap Claude flagged before production-affecting Builder patches.
- Record deploy decisions append-only without running a deploy.
- Require an approved patch proposal before manual deploy approval can be recorded.

Implemented locally:

- Added `modules/oom_sakkie/deploy_decision_store.py`.
- Added Supabase migration `supabase/migrations/202606070004_create_oom_sakkie_deploy_decisions.sql`.
- Added append-only `public.oom_sakkie_deploy_decisions`.
- Added DB constraints that keep:
  - `runs_deploy = false`,
  - `deploys_now = false`.
- Added protected `POST /api/oom-sakkie/patch-proposals/<patch_proposal_id>/deploy-decisions`.
- Added protected `GET /api/oom-sakkie/deploy-decisions`.
- Added kiosk `Deploy Approval Gate` panel.
- Added deploy decision types:
  - `approved_for_manual_deploy`,
  - `rejected`,
  - `deferred`,
  - `review_note`.
- `approved_for_manual_deploy` requires the target patch proposal's latest event to be `approved_for_patch`.

Safety:

- Does not run a deploy.
- Does not edit files.
- Does not apply patches.
- Does not run subprocesses.
- Does not mutate prompts/tools/farm data.
- Stores decisions append-only.

Verification:

- Applied migration `supabase/migrations/202606070004_create_oom_sakkie_deploy_decisions.sql`.
- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 135 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 460 tests OK.

Current Builder/Forge manual chain:

1. Learning Queue proposes an improvement from reviewed traces.
2. Owner opens Build Brief.
3. Owner approves for build.
4. Approved build request is stored append-only.
5. Owner generates Forge Handoff from stored build request.
6. Owner pastes Forge Handoff into separate Builder/Forge tool.
7. Builder proposes plan/patch outside the kiosk.
8. Owner records the patch proposal in Patch Proposal Gate.
9. Owner approves or rejects the patch proposal.
10. Owner applies approved patch manually outside the kiosk.
11. Owner runs verification.
12. Owner records deploy decision in Deploy Approval Gate.
13. Any deploy remains manual outside the kiosk.

### 10.8I Oom Sakkie Workbench Simplification And Work Status Tool - Local Ready

Status: local-ready.

Purpose:

- Reduce kiosk clutter by keeping the main screen focused on the living voice surface.
- Keep the audit/build controls available, but tucked behind a clear `System Workbench` disclosure.
- Let the owner ask Oom Sakkie what needs approval instead of hunting across panels.
- Reduce manual text-selection friction for Forge Handoff prompts.

Implemented locally:

- Wrapped the busy Recent Checks / Learning Queue / Build Request / Patch Proposal / Deploy Approval panels in a collapsed `System Workbench`.
- Added styling for the workbench summary and content area.
- Added a `Copy Forge Prompt` button that copies the generated Forge prompt to the clipboard after an explicit click.
- Added kiosk quick action `Approvals` with prompt `What needs my approval?`.
- Added read-only tool `system_work_status`.
- Added deterministic routing aliases for:
  - `what needs my approval`,
  - `what are you building`,
  - `what needs review`,
  - related build/patch/deploy status wording.
- `system_work_status` reads only the existing approved build request, patch proposal, and deploy decision queues.
- It returns counts and the next suggested human step in `llm_context`.
- It includes safety note: no build, patch, or deploy was run.

Safety:

- Does not run Builder/Forge.
- Does not automatically paste into or call an external coding agent.
- Does not edit files.
- Does not apply patches.
- Does not deploy.
- Does not mutate prompts/tools/farm data.
- Clipboard copy requires an owner click because browsers intentionally gate clipboard writes behind user activation.
- The approval queue status is read-only and uses existing append-only stores.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 136 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 461 tests OK.

Next safe direction:

- Use the calmer kiosk daily and ask `What needs my approval?` to check the current build/patch/deploy queues.
- Keep actual Builder/Forge execution outside the kiosk until a separate, explicit execution agent is designed and reviewed.
- If the workbench still feels busy, split it into tabs or separate views; do not remove the audit trail.

### 10.8J Oom Sakkie Workbench Pipeline Clarity - Local Ready

Status: local-ready.

Purpose:

- Make the workbench read like a step-by-step pipeline instead of a flat pile of records.
- Move completed/moved work out of the active bucket after the owner advances it.
- Keep all gates visible and audited without forcing the owner to infer which record belongs to which step.

Implemented locally:

- Approved Build Requests now render as:
  - `Needs Forge Handoff / Builder Plan`,
  - `Already Moved Or Closed`.
- Patch Proposal Gate now renders as:
  - `Needs Patch Review`,
  - `Approved - Ready For Deploy Decision`,
  - `Rejected / Closed`.
- Added work-stage badges and grouped action buttons.
- Added `Use This Build Request In Patch Gate` beside the Forge Handoff prompt.
- When a patch proposal is recorded, the build request receives append-only `review_note`: `Patch proposal recorded; moved to Patch Proposal Gate.`
- That review note moves the build request out of the active handoff bucket on refresh.
- Patch approval/rejection now refreshes deploy decisions as well as patch proposals.
- Deploy decision recording now refreshes patch proposals as well as deploy decisions.

Safety:

- Still does not run Builder/Forge.
- Still does not edit files.
- Still does not apply patches.
- Still does not deploy.
- Still does not mutate prompts/tools/farm data.
- The only state change added is an append-only build-request `review_note` after a patch proposal is recorded.
- Clipboard and handoff actions remain explicit owner clicks.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest tests.test_frontend_route_contracts tests.test_oom_sakkie_routes tests.test_oom_sakkie_service` -> 136 tests OK.
- `python -m unittest` -> 461 tests OK.

Manual check:

1. Open `System Workbench`.
2. Confirm build requests show under `Needs Forge Handoff / Builder Plan`.
3. Open Forge Handoff and click `Use This Build Request In Patch Gate`.
4. Record a patch proposal.
5. Confirm the build request moves to `Already Moved Or Closed`.
6. Confirm the patch proposal appears under `Needs Patch Review`.
7. Approve the patch proposal.
8. Confirm it moves to `Approved - Ready For Deploy Decision`.

### 10.8K Oom Sakkie Deploy Instructions And Business Advisor Seed - Local Ready

Status: local-ready.

Purpose:

- Make the deploy-ready bucket explain exactly what the owner must do next.
- Keep Oom Sakkie's `what needs my approval?` answer aligned with the visible workbench stages.
- Start the Business Advisor as a real read-only farm/commercial tool, not a write-capable sales agent.

Implemented locally:

- Added `What this needs now` instruction card to patch proposals in `Approved - Ready For Deploy Decision`.
- The instruction card tells the owner to:
  - read the patch proposal or diff in the editor,
  - apply it manually outside the kiosk only if happy,
  - run verification commands,
  - paste verification result before recording deploy approve/defer.
- Improved deploy verification placeholder wording.
- `system_work_status` now ignores build requests that already moved to Patch Proposal Gate.
- `system_work_status` now counts deploy-ready patch proposals only when no deploy decision has been recorded for that patch proposal.
- Added read-only `business_growth_brief`.
- Added deterministic routing for:
  - `business advisor`,
  - `business growth`,
  - `grow sales`,
  - `grow the business`,
  - `make money`,
  - `what should we sell`,
  - `what should i promote`,
  - `commercial focus`.
- `business_growth_brief` combines:
  - read-only `sales_dashboard`,
  - read-only `meat_planning`.
- It returns commercial focus, sales/meat counts, and next advisory action in `llm_context`.

Safety:

- Business Advisor is read-only.
- It does not draft customer messages.
- It does not post to social media.
- It does not sell, reserve, invoice, or change stock.
- It does not run Builder/Forge.
- It does not apply patches or deploy.
- Deploy instruction card is explanatory only.
- Deploy decision route remains record-only.

Compressed agent timeline:

1. **Now:** Oom Sakkie is the operating interface; deterministic tools plus LLM answer composer make answers more human.
2. **Next:** Business Advisor grows from `business_growth_brief` into a stronger read-only commercial brief across stock, orders, meat pipeline, and attention gaps.
3. **Then:** Sentinel/System Health watches trace/build/deploy health and raises approval-ready issues.
4. **Then:** Forge/Builder remains outside the kiosk at first, but receives better structured handoffs and patch/deploy review state.
5. **After trust:** Draft-only media/sales agents can propose posts/messages/offers for approval.
6. **Last:** customer/public writes, Telegram cutover, physical controls, and autonomous execution only after explicit approval gates and Claude review.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_frontend_route_contracts tests.test_oom_sakkie_routes` -> 138 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 463 tests OK.

Manual check:

1. Ask Oom Sakkie: `what needs my approval?`
2. Confirm moved build requests are not counted as active handoff work.
3. Open an approved patch proposal under `Approved - Ready For Deploy Decision`.
4. Confirm the row shows `What this needs now`.
5. Ask Oom Sakkie: `what should we sell next?`
6. Confirm it uses `business_growth_brief` and gives read-only commercial advice.

### 10.8L Oom Sakkie Workbench Next Action And Visual Separation - Local Ready

Status: local-ready.

Purpose:

- Reduce owner effort by showing the next workbench action before the long audit lists.
- Make build/patch/deploy sections visually easier to scan while keeping the full audit trail.
- Give Business Advisor a first-screen quick action.

Implemented locally:

- Added `oom_workbench_next_action` at the top of `System Workbench`.
- The card summarizes active:
  - build handoffs,
  - patch reviews,
  - deploy decisions.
- It recommends the next item to handle:
  - oldest build request needing Forge Handoff,
  - oldest patch proposal needing review,
  - oldest approved patch needing verification/deploy decision.
- Added workbench count pills.
- Strengthened visual separation between work sections and work records.
- Added `Business` quick action with prompt `What should we sell next?`.

Safety:

- UI guidance only.
- Does not run Builder/Forge.
- Does not edit files.
- Does not apply patches.
- Does not deploy.
- Does not mutate prompts/tools/farm data.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest tests.test_frontend_route_contracts tests.test_oom_sakkie_service tests.test_oom_sakkie_routes` -> 138 tests OK.
- `python -m unittest` -> 463 tests OK.

Manual check:

1. Open `System Workbench`.
2. Confirm the first card says `Next action`.
3. Confirm it shows build/patch/deploy counts.
4. Scroll and confirm each group has a clear heading and separated cards.
5. Click `Business` and confirm it asks `What should we sell next?`.

### 10.8M Oom Sakkie Work Status Honesty - Local Ready

Status: local-ready.

Purpose:

- Close Claude's Low finding that `system_work_status` could say "0 items" during a DB/store outage.
- Keep approval-status answers honest before the owner starts relying on the `Approvals` quick action.
- Clean up deploy-decision dependency-check ordering.

Implemented locally:

- `system_work_status` now inspects the HTTP/status code from:
  - `list_build_requests`,
  - `list_patch_proposals`,
  - `list_deploy_decisions`.
- Any non-200 sub-call produces a stale warning:
  - `System work status is incomplete: <store> unavailable (status <code>).`
- If a store is unavailable because it is not configured, the tool returns `status = not_configured`.
- If a configured store fails, the tool returns `status = degraded`.
- Summary wording now says the status is incomplete when any store could not be read.
- Counts are still best-effort from the stores that were readable.
- `record_deploy_decision()` now checks local `psycopg` availability before loading the patch proposal.

Safety:

- No builder execution.
- No file edits.
- No patch application.
- No deploy.
- No prompt/tool/farm-data mutation.
- This is failure visibility only.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 139 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 464 tests OK.

Manual check:

1. Ask `What needs my approval?` under normal DB configuration.
2. Temporarily run a process without `DATABASE_URL` and ask the same question.
3. Confirm the answer includes a stale warning/incomplete status instead of confidently saying nothing is waiting.

### 10.8N Oom Sakkie Business Advisor Context Upgrade - Local Ready

Status: local-ready.

Purpose:

- Make the Business Advisor less dumb by separating real marketable stock from young/not-ready stock.
- Give the owner a concrete commercial recommendation backed by pig/category details.
- Keep the output read-only and approval-friendly.

Implemented locally:

- `business_growth_brief` now computes:
  - total listed stock,
  - marketable listed stock,
  - young/not-ready stock,
  - ready meat candidates.
- Marketable stock excludes `Not For Sale` and `Out of Stock` rows.
- Ready meat candidates include:
  - pig ID,
  - tag number,
  - pen,
  - latest weight,
  - recommended action,
  - marketing readiness.
- Summary now includes:
  - commercial focus,
  - marketable category breakdown,
  - young/not-ready count,
  - ready candidate tags/pen/weights,
  - one owner-facing follow-up question.
- `llm_context` now exposes:
  - `owner_question`,
  - `marketable_stock`,
  - `young_or_not_ready_stock`,
  - `ready_meat_candidates`.

Safety:

- Still read-only advice.
- Does not draft an offer yet.
- Does not post.
- Does not message customers.
- Does not sell, reserve, invoice, or mutate stock.
- Does not run Builder/Forge, apply patches, or deploy.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 139 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest` -> 464 tests OK.
- Live read-only smoke returned:
  - 21 marketable pigs,
  - 34 young/not-ready pigs,
  - ready meat candidates tag 2 and tag 3 in D1.

Manual check:

1. Ask `What should we sell next?`
2. Confirm the answer distinguishes marketable stock from young/not-ready stock.
3. Confirm it names the ready meat candidates.
4. Confirm it asks a follow-up question instead of sending/posting/selling anything.

### 10.8O Oom Sakkie Role-Specific Spoken Composer Rules - Local Ready

Status: local-ready.

Purpose:

- Move Oom Sakkie closer to the intended Jarvis-style interaction without adding tool authority.
- Make LLM-composed Business Advisor answers sound like advice instead of table narration.
- Make approval-status answers lead with what the owner should do next.

Implemented locally:

- Updated `modules/oom_sakkie/llm_answer.py` prompt contract.
- For `business_growth_brief`, the composer must:
  - sound like a business advisor,
  - lead with the commercial move,
  - name the stock or ready pigs that justify it,
  - ask exactly one approval-style follow-up question from `backend_context.owner_question` when present.
- For `system_work_status`, the composer must:
  - state the next owner action first,
  - mention build/patch/deploy counts only if useful.
- Existing hard boundaries remain:
  - use only backend facts,
  - do not invent numbers,
  - do not claim saved/sent/started/stopped/posted/changed,
  - preserve stale warnings and safety notes.

Safety:

- Composer remains env-gated by `OOM_SAKKIE_LLM_ANSWER_ENABLED`.
- It cannot choose tools.
- It cannot call tools.
- It cannot write records.
- It cannot send messages, post, sell, reserve, apply patches, or deploy.
- If composer output is unsafe/off-topic/invalid, deterministic backend wording is used.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 139 tests OK.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Ensure `OOM_SAKKIE_LLM_ANSWER_ENABLED=true` in the local environment.
2. Ask `What should we sell next?`
3. Confirm the answer sounds advisory and asks one approval-style follow-up question.
4. Ask `What needs my approval?`
5. Confirm it leads with the next owner action.

Supabase RLS hardening verification:

- 2026-05-27 Security Advisor warned about `rls_disabled_in_public`.
- Migration `supabase/migrations/202605270001_enable_rls_on_public_tables.sql` was prepared to enable RLS on current public tables without adding anon/auth policies.
- Owner applied the migration and verified Security Advisor on 2026-05-30.
- Result: `0 errors` and `0 warnings`.
- Remaining `RLS Enabled No Policy` rows are info-level suggestions and are expected for the current backend-only `DATABASE_URL` access pattern.
- Do not add broad anon/auth policies unless a future browser/Supabase Auth design is explicitly approved.

Herd tile audit result:

- Local audit on 2026-05-30 confirmed the backend counts already reconcile when all counted categories are visible.
- Live-style local summary returned `on_farm_pigs = 103`: `18` sows, `3` boars, `0` gilts, `45` piglets, `17` weaners, `19` growers, and `1` finisher.
- The dashboard mismatch was a display issue: the tile only showed sows, boars, weaners, and finishers, so the visible breakdown summed to `39`.
- Local fix adds `Gilts`, `Piglets`, and `Growers` to the Herd tile and binds them to the existing backend summary fields.
- Local verification passed: `node --check static/js/dashboard.js`, focused frontend/dashboard tests passed at 14 tests, and local route smoke confirmed the new Herd IDs render.
- Owner deployed and browser-verified the Herd tile fix on 2026-05-30.

Farm attention summary result:

- Local first slice on 2026-05-30 adds `GET /api/reports/farm-attention-summary`.
- This is backend-owned and read-only: it aggregates daily order attention plus litter attention, prepares digest lines, and sends nothing.
- It is intended as the source contract for the later Telegram reminder workflow, so n8n can remain a thin caller/delivery layer.
- Owner deployed the backend endpoint on 2026-05-30.
- Production smoke on 2026-05-30 confirmed one current digest item, `LIT-2026-8A0F: Piglets need tag numbers`, and no backend writes or Telegram send.
- Local n8n workflow export `ALERT - Farm Attention Digest` is prepared inactive and dry-run by default.
- It implements the first delivery guardrails: no empty sends, no dry-run sends, no repeat content hash, and a minimum hours-between-sends check.
- Owner uploaded the updated workflow export to n8n on 2026-05-30.
- Manual Telegram send verification passed on 2026-05-30 through executions `49137` and `49138`.
- Manual no-output gate verification passed on 2026-05-30 through execution `49136`.
- First scheduled duplicate-suppression observation passed through n8n execution `49154`: trigger-mode run stopped at `Code - Extract Sendable Digest` with zero output, Telegram did not run, and no sent digest was recorded.
- Backend severity grouping remains a possible future refinement.

Slaughter form refinement notes:

- Source note moved from `planning/ToDoList.md` after first `/sales/slaughter` owner use.
- The save action should be easier to reach without unnecessary scrolling, likely by adding a top action row or sticky action behavior consistent with the weight form.
- The bottom transaction table should use the agreed table layout pattern with filters and clearer spacing.
- The slaughter form needs a planned multi-pig workflow because more than one pig may go to slaughter at a time.
- Owner note 2026-05-26: the slaughter update action currently opens in a browser/Google-style prompt that is awkward to use. Preferred direction is an in-app update form/modal/panel that exposes the required fields clearly before saving, especially final amount, payment status, payment date, carcass weight, and notes.
- 2026-05-30 local UX slice: replaced the browser-prompt payment update flow with an in-page `Update Slaughter Payment` panel.
- The panel exposes final amount, payment status, payment method, payment date, sale status, carcass weight for one-pig transactions, updated-by, and update note before saving.
- The existing backend payment update endpoint remains the source of truth; this slice does not change Supabase schema, sale transaction rules, or the multi-pig transaction model.
- Local verification passed: `node --check static/js/slaughterSale.js`, focused frontend/sales transaction tests, and local Flask route smoke for `/sales/slaughter`.
- Owner local browser check passed on 2026-05-30: clicking `Update Payment` opens the in-page update panel and the flow appears correct.
- 2026-05-30 local layout/table slice: widened `/sales/slaughter` to a 1640px operational canvas, split the create form and transaction ledger into a responsive two-column workspace, and compressed the transaction table by grouping transaction/date, buyer/destination, and amount/item count.
- Local verification passed: `node --check static/js/slaughterSale.js`, focused frontend/sales transaction tests, and local Flask route smoke for `/sales/slaughter`.
- 2026-05-31 local table/detail slice:
  - Slaughter transactions now sort by newest `created_at` first, then sale date and sale ID.
  - Completed/paid rows are treated as closed in the table and no longer show update/cancel actions.
  - Table action buttons are smaller (`Update`, `Cancel`) for open rows.
  - Table rows are clickable and keyboard accessible, opening `/sales/slaughter/<sale_id>`.
  - Added read-only sale detail API `GET /api/sales-transactions/<sale_id>` and detail page with a back button, sale/payment summary, and item rows.
  - Local verification passed: JS syntax checks for `slaughterSale.js` and `slaughterSaleDetail.js`, focused frontend/sales read/routes/update tests, and route smoke for `/sales/slaughter` plus `/sales/slaughter/SALE-2026-1DE373`.
- 2026-05-31 local sales overview/reporting slice:
  - Reworked `/sales-dashboard` from stock-only summary into a wider sales reporting screen.
  - Added filters for period, selected month, selected year, custom date range, and sales stream.
  - Added totals for all sales, livestock, slaughter, and meat using loaded Supabase `sales_transactions`.
  - Added a clickable transaction ledger with drill-in route `/sales/transactions/<sale_id>`.
  - Kept existing current stock availability summary as a secondary section below the transaction report.
  - Local verification passed: `node --check static/js/salesDashboard.js`, `node --check static/js/slaughterSaleDetail.js`, focused frontend/sales read/routes tests, and local route smoke for `/sales-dashboard` plus `/sales/transactions/SALE-2026-1DE373`.
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
- Should the slaughter payment/final-amount update be a modal, inline expandable row, or separate edit page?

## Phase 11: Pork Sales Business Module - Discovery Source Captured

Goal: incorporate the new Amadeus Farm pork sales model without breaking the current live pig sales and order system.

Source document:

- `docs/08-business-modules/PORK_SALES_MODEL.md`
- `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md`

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

- Start Phase 11A with a practical integration/readiness map before building new meat-sales workflow screens.
- Keep refining `docs/08-business-modules/PORK_SALES_MODEL.md` as the owner source, but use Phase 11A to translate it into safe implementation slices.
- This is cross-cutting enough that a Claude Code review should be used before implementation starts.

### 11A Pork Business Integration Readiness Map - Local Ready

Purpose:

- Make the pork business module useful without creating disconnected screens.
- Show how current farm data should flow from litter/weaning to pig growth, purpose/allocation, sale/slaughter/meat stream, revenue, and reporting.
- Keep this read-only/planning-first until the ownership of each action and data source is clear.

Recommended first output:

- Implementation bridge document:
  - Created `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md` as the Phase 11A source.
  - Defines the current sources, allocation/readiness buckets, first read-only route/API, backend-owned future actions, open thresholds, and non-goals.

- A simple implementation bridge that defines:
  - current sources already working: `PIG_MASTER`, `LITTERS`, `WEIGHT_LOG`, `MATING_LOG`, Supabase `sales_transactions`, Supabase `sales_transaction_items`, and current order tables.
  - business decisions needed before writes: when a pig becomes livestock-sale candidate, slaughter candidate, meat candidate, retained breeding candidate, or not for sale.
  - the first useful read-only screen/API: a “Pig Allocation Readiness” view using existing pig status, purpose, age/stage, latest weight, pen, litter/parent, and sale/slaughter state.
  - data gaps that must wait for real use: bulk weights, actual carcass weights, butchery/packaging costs, customer meat-order deposits, and cold-chain/delivery rules.
  - which actions must remain backend-owned: mark weaned, classify purpose/allocation, confirm slaughter exit, create meat order/deposit, assign pig to meat order, record processing yield, complete delivery/payment.

Practical build direction after 11A:

- Build read-only readiness/reporting first.
- Add write actions only when the farm process is clear and the user can test them in real scenarios.
- Do not start with a complex calculator or full meat order form; those should use the readiness map and real farm data as inputs.

Next build candidate:

- `GET /api/pig-weights/pig-allocation-readiness`
- `/pig-allocation`
- Read-only, full-width table with filters and explainable readiness buckets.

Local implementation state 2026-06-04:

- Added `GET /api/pig-weights/pig-allocation-readiness`.
- Added `/pig-allocation` as a read-only, full-width planning table.
- Added dashboard shortcut `Pig Allocation`.
- First conservative readiness buckets are `Needs Data`, `Growing`, `Livestock Candidate`, `Slaughter Candidate`, `Meat Candidate`, `Retain / Breeding Candidate`, `Allocated`, and `Exited`.
- The API returns explicit `writes_to_sheets = false` and `writes_to_supabase = false`.
- No purpose/status/allocation writes were added.
- Local verification passed: `node --check static/js/pigAllocation.js`, Python compile check for touched backend files, focused allocation service test, frontend route contract tests, full local unittest suite at 343 tests, and local route smoke for `/pig-allocation` plus `/api/pig-weights/pig-allocation-readiness`.

Owner model clarification 2026-06-04:

- The allocation model must be growth- and quality-based, not a hard static weight split.
- Purpose should be suggested after weaning from wean weight, average daily gain, and litter/parent quality.
- Fast growers from good litters should first be reviewed as breeding candidates, then meat candidates if not retained.
- Current grow-out pigs mainly go to slaughter/abattoir until the meat business is active; livestock sale is the fallback for slow growers/underperformers to reduce feed cost.
- Meat candidates should be young and within the configured meat weight window; if not pre-sold before exceeding the window, they should fall back to slaughter/abattoir.
- Unknown purpose should stay as a classification/data issue and should not silently become a candidate bucket.
- Next practical code slice should add growth context and litter-quality context to `/pig-allocation` before adding settings pages, write actions, or meat-order forms.

Local refinement state 2026-06-04:

- Added `Needs Classification` as a separate bucket for pigs that have identity/weight data but still have unknown purpose.
- Added read-only growth context to the API/page: wean date, wean weight, days since wean, latest weight, days since latest weight, average daily gain, and growth class.
- Added read-only litter quality context to the API/page: born alive, weaned count, survival rate, sow/boar IDs/tags, litter quality, and reason.
- Fast growers from good litters are now flagged as `Retain / Breeding Candidate` for review before meat/slaughter allocation.
- Slow growers are flagged toward `Livestock Candidate` before static weight rules.
- Still no writes, no settings page, and no automatic purpose changes.
- Verification passed: `node --check static/js/pigAllocation.js`, Python compile check for allocation service, focused allocation/frontend tests at 24 tests, full local unittest suite at 344 tests, and route/API smoke confirmed the new fields are present.

Growth band refinement 2026-06-05:

- Growth class should be clearer than only slow/normal/fast.
- Use lifetime average daily gain as the main growth signal where possible: latest weight divided by age/days on farm.
- Keep post-wean ADG visible as secondary context.
- First bands are `Extremely Slow` under `0.100 kg/day`, `Slow` under `0.200`, `Below Target` under `0.300`, `Steady` under `0.400`, `Good` under `0.500`, and `Exceptional` at/above `0.500`.
- UI should display both the class and the actual kg/day value so owner can tune the model from real use.

Readiness timing refinement 2026-06-05:

- Add read-only estimated meat and abattoir ready dates from lifetime ADG.
- Meat readiness uses the configured meat minimum weight.
- Abattoir readiness uses the configured abattoir/slaughter minimum weight.
- First abattoir range adjusted to `80-95 kg` to match the current fallback outlet rather than overlapping the meat window.

Outlet recommendation refinement 2026-06-05:

- Added read-only `Recommended Action`/`Outlet Priority` to `/pig-allocation`.
- Extremely slow and slow growers point toward livestock sale as soon as practical.
- Meat-window pigs point toward meat preorder/interest generation.
- Abattoir stays the fallback for grow-out pigs that miss the meat opportunity or reach the heavier abattoir window.
- Added `Marketing Readiness` so the system can later separate internal planning, ready-for-listing, ready-for-interest, blocked, and closed cases.
- Future weekly Telegram summaries and Meta-compliant Facebook/Instagram post drafts should use these same signals, but no auto-posting, auto-message, Supabase write, or Google Sheets write automation is approved yet.
- Keep the approval path explicit: first system-generated recommendations, then owner-approved wording/compliance rules, then optional scheduled draft generation, and only much later approved publishing automation.

Allocation settings read-model refinement 2026-06-05:

- Centralized Phase 11A allocation thresholds in backend-owned `DEFAULT_ALLOCATION_SETTINGS`.
- `/api/pig-weights/pig-allocation-readiness` now returns raw `thresholds` plus human-readable `business_rules`.
- `/pig-allocation` now shows the active rules above the table: meat window, abattoir window, livestock trigger, growth target, slow-growth trigger, good-litter threshold, stale-weight window, and rule source.
- This keeps the rules visible and easy to tune later without adding a settings write page yet.
- Still no purpose/status/allocation writes, no Google Sheets writes, no Supabase writes, and no Telegram/Meta automation.

Suggested-purpose signal refinement 2026-06-05:

- Added read-only `Suggested Purpose`, `Suggested Purpose Reason`, and `Suggested Purpose Confidence` to the allocation API/page.
- This sits beside the stored `Purpose` so the owner can compare what the sheet currently says against what the system recommends.
- Current suggestions are advisory only: `Needs Review`, `Grow Out`, `Livestock Sale`, `Meat`, `Abattoir Slaughter`, `Breeding Review`, `Already Allocated`, and `Closed`.
- This is the bridge before any future backend-owned classify/update action.

Meat planning read-model refinement 2026-06-05:

- Added `GET /api/pig-weights/meat-planning`.
- Added `/meat-planning` as a read-only planning page linked from dashboard and pig allocation.
- The endpoint uses allocation readiness as its source and groups pigs into `ready_now`, `next_14_days`, `next_30_days`, `future`, and `fallback_abattoir`.
- The page shows meat pipeline count, ready-now count, near-term counts, fallback abattoir count, and minimum preorder demand needed now/within 30 days.
- Still no meat orders, deposits, customer records, pig allocations, Telegram messages, Meta posts, Supabase writes, or Google Sheets writes.

Temporary demand scenario refinement 2026-06-05:

- Added local-only expected demand inputs to `/meat-planning` for demand now and demand within 30 days.
- The page calculates surplus/shortfall against the read-only meat pipeline.
- This is deliberately not saved and does not create demand, preorder, deposit, customer, allocation, Supabase, or Google Sheets records.
- Use this during browser/live review to decide what the first real demand/preorder data contract should contain.

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
- Phase 9.1C litter attention action path — deployed and browser-verified 2026-05-30: detail pages show reason-specific action guidance, `Mark as Weaned` only appears for true weaning actions, purpose-review noise is suppressed for older litters whose active piglets already have accepted purpose values, and `LIT-2026-8A0F` remains as the legitimate tag-number reminder.
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

### 10.8P Oom Sakkie Business Offer Outline - Local Ready

Purpose:

- Move the Business Advisor from a basic data reader toward a useful commercial co-pilot without crossing into customer/public action.
- Let Oom Sakkie explain the internal shape of a possible offer opportunity from existing read-only sales and meat-planning facts.
- Keep the owner in control before any future draft-only customer copy, public post, quote, reservation, sale, or stock change.

What changed:

- `business_growth_brief` now adds `llm_context.offer_brief_outline`.
- The outline is explicitly `mode = internal_outline_only`.
- For ready meat candidates, the outline names:
  - opportunity title,
  - target buyer type,
  - ready-stock evidence,
  - ready tags/pen/weight as stock basis,
  - owner approval requirement,
  - next step before any customer-facing draft.
- For listed marketable stock, the outline names the listed-stock sales push and asks for a buyer segment before any customer wording.
- If no obvious stock opportunity exists, the outline says demand discovery should happen first.
- The outline records what was not done:
  - no customer message drafted,
  - no public post drafted,
  - no quote created,
  - no sale/reservation/stock change made.
- Deterministic routing now treats `offer brief`, `commercial brief`, and `prepare ... offer` as `business_growth_brief`.
- Added an `Offer Brief` quick action on the kiosk with prompt `Prepare an internal offer brief.`
- The env-gated answer composer now has a Business Advisor rule: if `backend_context.offer_brief_outline` exists, summarize it as an internal offer brief outline only, not customer-facing copy.

Verification:

- Focused Oom Sakkie tests confirmed:
  - `business_growth_brief` still stays `RiskLevel.READ_ONLY`,
  - `offer_brief_outline.mode == internal_outline_only`,
  - ready candidates appear in the outline basis,
  - approval and no-action language is present,
  - `prepare an offer brief` routes to `business_growth_brief`,
  - the kiosk exposes `Prepare an internal offer brief.` as a quick action,
  - answer-composer prompt pins `internal offer brief outline only` and `not customer-facing copy`.
- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` passed at 139 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 464 tests.

Safety status:

- Still no customer message drafting.
- Still no public post drafting.
- Still no quote/order creation.
- Still no stock reservation or sale.
- Still no Supabase/Google Sheets farm-data write from this tool.
- Still no Builder/Forge execution, patch application, or deploy.

North-star tracking:

- End goal remains a farm operating/business interface that feels alive and useful, with Oom Sakkie as the user-facing brain.
- Build path remains staged:
  1. read-only operating visibility,
  2. read-only specialist/business advice,
  3. internal proposal outlines,
  4. draft-only customer/media/business packets behind human approval,
  5. human-approved builder/patch/deploy gates,
  6. carefully gated write/post/sell/control actions only after repeated review.

### 10.9A Oom Sakkie Agent Runtime Foundation - Local Ready

Purpose:

- Shift the work from patching single answers toward a real Jarvis-like agent platform for the farm.
- Give the planned specialist crew a runtime shape: identity, personality, role, memory sources, tool allowlist, risk limit, output contract, approval rules, and routing hints.
- Keep the first runtime slice advisory only. It must not run live agent delegation, autonomous loops, writes, posts, sales, controls, Builder/Forge, patch application, or deploy.

What changed:

- Added `modules/oom_sakkie/agent_runtime.py`.
- Added `AgentRuntimeManifest` for the planned crew.
- Added read-only runtime status:
  - `mode = advisory_runtime_foundation`,
  - `runtime_enabled = false`,
  - `dispatch_enabled = false`,
  - `autonomous_loops_enabled = false`,
  - `writes_enabled = false`.
- Added per-agent fields:
  - `personality`,
  - `memory_sources`,
  - `allowed_tools`,
  - `risk_limit`,
  - `output_contract`,
  - `approval_rules`,
  - `routing_hints`.
- Added recommendation-only routing:
  - `recommend_agent_for_text(text)`,
  - returns `mode = dispatch_recommendation_only`,
  - returns `runs_agent = false`,
  - returns `writes = false`,
  - explains which planned agent would handle the question and why.
- Added protected endpoints:
  - `GET /api/oom-sakkie/agents`,
  - `POST /api/oom-sakkie/agents/recommend`.
- Added `agent_runtime` into `/api/oom-sakkie/review-packet`.
- Added kiosk `Agent Crew Foundation` panel that renders the crew and states dispatch/autonomous loops are off.
- Added `Agents` review link.

Initial crew platform:

- Sentinel: safety/security reviewer.
- Forge: builder/code/test planner.
- Prism: UI/design advisor.
- Ledger: business/profit advisor.
- Atlas: analytics/trends/anomaly advisor.
- Rootline: weather/crop/irrigation advisor.
- Herdmaster: pig lifecycle/herd specialist.
- Butcher: pork/meat/slaughter pipeline specialist.
- Beacon: marketing/media draft specialist.
- Quartermaster: tasks/supplies/operations planner.
- Gatekeeper: routing/approval controller.

Safety status:

- No live delegation.
- No autonomous loops.
- No specialist LLM calls.
- No tool execution through `/agents/recommend`.
- No write tools.
- No customer/public output.
- No Builder/Forge execution.
- No patch/deploy automation.
- This is a platform foundation and visibility layer only.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 145 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 470 tests.

Manual check:

1. Reload `/oom-sakkie`.
2. Open `System Workbench`.
3. Confirm `Agent Crew Foundation` loads named agents with personalities, roles, and allowed tools.
4. Confirm guard line says runtime/dispatch/autonomous loops are off.
5. Open `/api/oom-sakkie/agents` locally and confirm all runtime/write flags are false.
6. Optional local POST to `/api/oom-sakkie/agents/recommend` with text such as `should we post a marketing update?`; confirm it recommends Beacon but says `runs_agent = false`.

### 10.9B Oom Sakkie Agent Crew Status Tool - Local Ready

Purpose:

- Let the owner ask Oom Sakkie about the agent crew from the normal chat path.
- Make the agent platform visible as an assistant capability, not only a hidden workbench/API panel.
- Keep this recommendation-only: no live specialist dispatch, no agent LLM calls, no specialist tool execution, and no writes.

What changed:

- Added read-only registry tool `agent_crew_status`.
- Added deterministic routing for phrases such as:
  - `which agent should handle ...`,
  - `show me the agent crew`,
  - `who handles ...`,
  - `agent platform`,
  - `jarvis agents`.
- `handle_message()` now passes bounded `user_text` into tool handlers as context. Existing handlers ignore it; `agent_crew_status` uses it only for recommendation.
- `agent_crew_status` calls the same recommendation-only runtime helper from Phase 10.9A.
- Tool output states:
  - which planned agent would handle the question,
  - why it was selected,
  - that no specialist was dispatched,
  - that no specialist tool ran,
  - that no write was performed.
- Added `Agents` quick action with prompt `Which agent should handle this?`

Safety status:

- Tool remains `RiskLevel.READ_ONLY`.
- No specialist runtime execution.
- No autonomous loop.
- No write, post, sale, message, control, Builder/Forge, patch, or deploy.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 147 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 472 tests.

Manual check:

1. Reload `/oom-sakkie`.
2. Click `Agents`.
3. Ask `which agent should handle a marketing post?`
4. Confirm the answer names Beacon but says no specialist was dispatched.

### 10.9C Oom Sakkie Agent Activity Stage - Local Ready

Purpose:

- Move the kiosk toward the Jarvis-style controller/team model captured in `screenshots/Jarvis screen layout.mp4`.
- Make Oom Sakkie visibly act as the controller while the relevant planned specialist opens a read-only workspace.
- Show color changes by active specialist so the owner can follow who is "working" without enabling live dispatch yet.

Design reference note:

- The owner-provided MP4 is retained as a visual target: Oom Sakkie controls the interaction, specialist agents open their own visible work areas, colors shift as work moves between agents, and the owner can see what each agent is doing.
- Local frame extraction was not available in this environment because no video reader/ffmpeg stack is installed, so this phase logs and implements from the owner's described design intent.

What changed:

- Added `build_agent_activity()` in `modules/oom_sakkie/agent_runtime.py`.
- `handle_message()` now adds an `agent_activity` payload to successful read-only tool responses.
- The payload includes:
  - `controller = oom_sakkie`,
  - active planned agent slug/name/personality/role/color,
  - workspace title/state/tool/reason/owner text,
  - hard safety flags: `runs_agent = false`, `dispatch_enabled = false`, `autonomous_loops_enabled = false`, `writes = false`.
- Mapped current read-only tools to visible primary agents:
  - business/sales tools -> Ledger,
  - power/farm operating brief -> Atlas,
  - weather/irrigation -> Rootline,
  - pig dashboard/allocation -> Herdmaster,
  - meat planning -> Butcher,
  - system work -> Forge,
  - farm attention -> Quartermaster,
  - crew recommendation -> selected recommended agent when available, otherwise Gatekeeper.
- Added a first-viewport `Agent Activity Stage` under the Oom Sakkie presence orb.
- The stage shows:
  - controller state,
  - active specialist workspace,
  - current read-only tool,
  - routing reason,
  - dispatch/loop/write guard.
- The presence orb and workspace border now change color by active specialist.
- Added responsive CSS so the controller/workspace stack cleanly on narrow screens.

Safety status:

- This is a display/activity layer only.
- No live specialist dispatch.
- No specialist LLM call.
- No autonomous loop.
- No specialist tool execution beyond the existing single read-only tool path.
- No write, post, sale, message, control, Builder/Forge run, patch application, or deploy.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 149 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 474 tests.

Manual check:

1. Reload `/oom-sakkie`.
2. Ask `what is the power doing now`; confirm Atlas opens and the orb shifts cyan.
3. Ask `what should we sell next`; confirm Ledger opens and the orb shifts green.
4. Ask `what is the irrigation status`; confirm Rootline opens and the orb shifts teal.
5. Ask `which agent should handle a marketing post`; confirm Beacon opens and the answer still says no specialist was dispatched.

### 10.9D Oom Sakkie Agent Handoff Lane - Local Ready

Purpose:

- Make the controller/team model easier to follow on screen.
- Show the visible sequence for each read-only answer: Oom Sakkie receives the request, a specialist workspace opens, an existing read-only backend tool supplies facts, and owner approval remains the gate for anything beyond advice.
- Keep the UI closer to the Jarvis reference without turning planned specialists into live autonomous agents yet.

What changed:

- `build_agent_activity()` now returns a four-step `handoff_lane`:
  - `controller` -> Oom Sakkie received one bounded read-only turn,
  - `specialist_workspace` -> visible-only planned agent workspace opened,
  - `read_only_tool` -> existing backend read-only tool supplied facts,
  - `owner_gate` -> no write/post/sale/control/patch/deploy can run here.
- The kiosk Agent Activity Stage now includes an `Agent handoff lane`.
- The lane is rendered with DOM nodes and `.textContent`, not dynamic HTML.
- CSS presents the lane as four compact process cards on desktop and stacked cards on narrow screens.
- Frontend contracts pin the lane markup, JS renderer, DOM creation path, and CSS hooks.

Safety status:

- Visual handoff only.
- No live specialist dispatch.
- No specialist LLM call.
- No autonomous loop.
- No new tool authority.
- No write, post, sale, message, physical control, Builder/Forge run, patch application, or deploy.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 149 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 474 tests.

Manual check:

1. Reload `/oom-sakkie`.
2. Ask `what should we sell next`.
3. Confirm the handoff lane shows Controller / Specialist Workspace / Read Only Tool / Owner Gate.
4. Confirm the owner-gate card says no write/post/sale/control/patch/deploy can run here.

### 10.9E Oom Sakkie Agent Crew Brief - Local Ready

Purpose:

- Let Oom Sakkie explain how the planned specialist team would work together on broader requests.
- Move from single-agent recommendation toward a controller-led team plan without enabling live dispatch.
- Give the owner a practical view of which specialist would inspect which part of a problem before any future multi-agent runtime is allowed.

What changed:

- Added `build_agent_crew_brief(text)` to the agent runtime foundation.
- The helper selects a scenario from the owner text:
  - commercial growth,
  - farm operations,
  - pig pipeline,
  - system build,
  - weather/irrigation,
  - general fallback.
- The helper returns `mode = crew_plan_only` with a planned sequence of agents, each including:
  - order,
  - slug/name/personality/role/color,
  - what that specialist would inspect,
  - allowed read-only tools,
  - `runs_agent = false`,
  - `writes = false`.
- Added read-only tool `agent_crew_brief`.
- Added deterministic routing for phrases such as:
  - `crew brief`,
  - `team brief`,
  - `agent team`,
  - `which agents would work together`,
  - `coordinate the team`,
  - `multi-agent`,
  - `agent plan`.
- Added kiosk quick action `Team Brief` with prompt `Give me the agent team brief for growing the farm business.`

Safety status:

- Plan-only.
- No specialist dispatch.
- No specialist LLM call.
- No autonomous loop.
- No specialist tool execution.
- No write, post, sale, message, physical control, Builder/Forge run, patch application, or deploy.
- Future execution still requires owner approval before live multi-agent dispatch.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 151 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 476 tests.

Manual check:

1. Reload `/oom-sakkie`.
2. Click `Team Brief`.
3. Confirm the answer names a planned sequence such as Ledger, Butcher, Beacon, Sentinel.
4. Confirm the safety note says no specialist was dispatched and no write was performed.
5. Confirm the active workspace follows the first planned specialist but the guard still says dispatch/loops/writes are off.

### 10.9F Oom Sakkie Visible Crew Sequence - Local Ready

Purpose:

- Make the plan-only Team Brief visible on the Agent Activity Stage.
- Show the owner the planned specialist sequence as cards, not only answer text.
- Continue building toward the Jarvis-style controller/team display while keeping execution disabled.

What changed:

- `agent_activity` now includes `crew_sequence` when the tool result contains a crew brief.
- The sequence is bounded to six planned agents.
- Each sequence card includes:
  - step/order,
  - agent name/personality,
  - what the agent would inspect,
  - `runs no`,
  - `writes no`.
- Added `oom_agent_crew_sequence` to the kiosk Agent Activity Stage.
- Added `renderAgentCrewSequence()` in `static/js/oomSakkie.js`.
- The sequence area is hidden by default and appears only when a crew brief is returned.
- Crew sequence cards use the same agent color language as the active workspace.
- Dynamic sequence content uses DOM nodes and `.textContent`.

Safety status:

- Visual plan only.
- No specialist dispatch.
- No specialist LLM call.
- No autonomous loop.
- No specialist tool execution.
- No write, post, sale, message, physical control, Builder/Forge run, patch application, or deploy.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 152 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 477 tests.

Manual check:

1. Reload `/oom-sakkie`.
2. Click `Team Brief`.
3. Confirm a `Planned specialist sequence` row appears with Ledger / Butcher / Beacon / Sentinel cards.
4. Confirm each card says `runs no | writes no`.
5. Ask a normal single-tool question such as `what is the power doing now`; confirm the sequence row hides again.

### 10.9G Oom Sakkie Agent Activation Plan - Local Ready

Purpose:

- Make the path from planned agents to real agents explicit and trackable.
- Let Oom Sakkie answer what needs to happen before agents become live.
- Keep the activation plan inside the runtime as a read-only contract, not just a vague idea in chat.

What changed:

- Added `get_agent_activation_plan()` to `modules/oom_sakkie/agent_runtime.py`.
- The plan returns:
  - `mode = activation_plan_only`,
  - runtime/dispatch/autonomous-loop/write flags all false,
  - activation stages:
    - foundation visible,
    - read-only dry-run,
    - human-approved dispatch,
    - draft-only outputs,
    - controlled writes,
  - recommended next stage: `read_only_dry_run`,
  - recommended first candidate: Sentinel,
  - required locked-until gates,
  - blocked capabilities.
- Added read-only tool `agent_activation_plan`.
- Added deterministic routing for phrases such as:
  - `agent activation`,
  - `activate agents`,
  - `make agents live`,
  - `agent roadmap`,
  - `what is next for the agents`,
  - `when can agents go live`.
- Added kiosk quick action `Agent Roadmap` with prompt `What is the agent activation plan?`

Safety status:

- Read-only plan only.
- No specialist dispatch.
- No specialist LLM call.
- No autonomous loop.
- No runtime flag is enabled.
- No write, post, sale, message, physical control, Builder/Forge run, patch application, or deploy.
- First live slice remains locked behind owner approval and a future append-only dispatch/audit gate.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 154 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 479 tests.

Manual check:

1. Reload `/oom-sakkie`.
2. Click `Agent Roadmap`.
3. Confirm Oom Sakkie says the next safe stage is a read-only dry-run.
4. Confirm Sentinel is recommended first.
5. Confirm the safety note says no specialist was dispatched and no runtime flag was enabled.

### 10.9H Oom Sakkie Sentinel Dry-Run Review - Local Ready

Purpose:

- Start the first specialist activation rehearsal without enabling live specialist dispatch.
- Let Sentinel review whether the current tool/runtime foundation is safe enough for a future read-only dry-run.
- Keep the result deterministic, read-only, and auditable before any specialist LLM or dispatch loop exists.

What changed:

- Added `build_sentinel_dry_run_review(tool_catalog)` to `modules/oom_sakkie/agent_runtime.py`.
- The review returns:
  - `mode = sentinel_dry_run_review_only`,
  - selected agent: Sentinel,
  - runtime/dispatch/autonomous-loop/write/specialist-LLM flags all false,
  - read-only tool audit,
  - non-read-only / confirmation-required tool lists,
  - blockers before any live specialist dry-run,
  - recommendation and next gate.
- Added read-only tool `sentinel_dry_run_review`.
- Added deterministic routing for phrases such as:
  - `sentinel dry-run`,
  - `safety dry-run`,
  - `first agent dry run`,
  - `specialist dry-run`,
  - `agent dry-run review`.
- Added kiosk quick action `Sentinel Dry Run` with prompt `Run the Sentinel dry-run review.`
- Agent Activity Stage maps the tool to Sentinel so the visible workspace uses the Sentinel identity/color.

Safety status:

- Read-only review only.
- No specialist dispatch.
- No specialist LLM call.
- No autonomous loop.
- No specialist tool execution.
- No runtime flag is enabled.
- No write, post, sale, message, physical control, Builder/Forge run, patch application, or deploy.
- Future live dry-run remains locked behind owner approval, append-only dispatch/audit trail, and review.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 155 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 480 tests.

Manual check:

1. Reload `/oom-sakkie`.
2. Click `Sentinel Dry Run`.
3. Confirm the answer says this is an advisory-only rehearsal and live dispatch remains locked.
4. Confirm Sentinel opens in the Agent Activity Stage.
5. Confirm the safety note says no specialist was dispatched, no specialist LLM ran, no specialist tool executed, and no write was performed.
6. Confirm the review lists blockers before any live specialist dry-run.

### 10.9I Oom Sakkie LLM Message Guard And Safety Follow-Ups - Local Ready

Purpose:

- Close Claude's pass-with-nits follow-ups before widening daily use.
- Prevent unauthenticated non-local `/api/oom-sakkie/message` callers from creating outbound paid LLM calls when LLM flags are enabled.
- Promote the reverse-proxy caveat to a hard deployment rule.
- Add stronger tests for unsafe LLM composer output, action-guard wording, and live Postgres review-gate constraints.

What changed:

- Added message access helpers in `modules/oom_sakkie/access.py`:
  - `/message` remains reachable wherever Flask is reachable while LLM router/answer features are off,
  - when an LLM surface is enabled, `/message` must pass the same loopback/private-LAN guard before it can trigger outbound API calls,
  - denied responses return `status = message_access_denied`.
- `modules/oom_sakkie/routes.py` now applies the message guard before `handle_message()`.
- Runtime policy now exposes:
  - `message_endpoint_access.llm_guard_active`,
  - `message_endpoint_access.llm_guard_rule`,
  - `default = local_guard_required_when_llm_enabled` when the guard is active.
- The action guard now treats `irrigate` as a control verb, and deterministic routing maps it to read-only `irrigation_status`.
- The PRD now says no same-host reverse proxy may sit in front of review routes until trusted proxy handling is deliberately configured and reviewed.
- Added a DATABASE_URL-gated live Postgres integration test for build/patch/deploy CHECK constraints:
  - `builder_enabled = true` is rejected,
  - `applies_patch = true` is rejected,
  - `runs_deploy = true` is rejected.
- Added an end-to-end `handle_message()` test proving unsafe LLM composer output such as `I updated...` falls back to the deterministic answer.

Safety status:

- No new write tools.
- No live specialist dispatch.
- No specialist LLM execution.
- No autonomous loop.
- No Builder/Forge run, patch application, or deploy.
- `/message` is still open for plain deterministic local use while LLM flags are off.
- `/message` becomes local/private-LAN guarded before outbound LLM calls can happen.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 161 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 486 tests.

Manual check:

1. With LLM flags off, ask a normal kiosk question and confirm `/api/oom-sakkie/message` still works.
2. With any LLM router/answer/learning env enabled, confirm `/api/oom-sakkie/policy` shows `message_endpoint_access.llm_guard_active = true`.
3. Ask `irrigate zone 3 now`; confirm it returns read-only irrigation status and safety notes, not an action.
4. Do not deploy behind a reverse proxy until trusted proxy handling and auth/rate-limit policy are deliberately reviewed.

### 10.9J Oom Sakkie Agent Dry-Run Request Gate - Local Ready

Purpose:

- Build the missing append-only owner approval/audit rail before any future live specialist dry-run.
- Let the system record a Sentinel read-only dry-run request without actually running Sentinel.
- Give Oom Sakkie a read-only queue-status answer for future dry-run approvals.

What changed:

- Added migration `supabase/migrations/202606080001_create_oom_sakkie_agent_dry_runs.sql`.
- The migration creates:
  - `oom_sakkie_agent_dry_run_requests`,
  - `oom_sakkie_agent_dry_run_events`.
- DB constraints force:
  - `mode = read_only_dry_run_request_only`,
  - `status = approved_for_read_only_dry_run`,
  - `dry_run_enabled = false`,
  - `dispatch_enabled = false`,
  - `runs_specialist_llm = false`,
  - `runs_specialist_tools = false`,
  - `writes = false`.
- DB triggers make both tables append-only.
- Added `modules/oom_sakkie/agent_dry_run_store.py`:
  - `record_agent_dry_run_request()`,
  - `list_agent_dry_run_requests()`,
  - `record_agent_dry_run_event()`.
- Only `sentinel` is allowed for this first request-gate slice; other specialists return `specialist_dry_run_not_approved_yet`.
- Added protected local-only routes:
  - `GET /api/oom-sakkie/agent-dry-runs`,
  - `POST /api/oom-sakkie/agent-dry-runs`,
  - `POST /api/oom-sakkie/agent-dry-runs/<dry_run_request_id>/events`.
- Added read-only `agent_dry_run_status` tool.
- Added deterministic routing for dry-run queue/status phrasing.
- Added kiosk quick action `Dry-Run Queue` with prompt `What is the agent dry-run queue status?`

Safety status:

- Records approval intent only.
- Does not run Sentinel.
- Does not dispatch any specialist.
- Does not call a specialist LLM.
- Does not execute specialist tools.
- Does not write farm data.
- Does not run Builder/Forge, apply patches, or deploy.
- Future dry-run execution remains locked behind a separate manually reviewed implementation step.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 170 tests.
- Applied migration `202606080001_create_oom_sakkie_agent_dry_runs.sql`.
- Live-style smoke created dry-run request `OSK-AGENT-DRYRUN-B2E07585AD` and event `OSK-AGENT-DRYRUN-EVENT-0542A235E334`; all execution flags remained false.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 495 tests.

Manual check:

1. Reload `/oom-sakkie`.
2. Click `Dry-Run Queue`.
3. Confirm Oom Sakkie reports agent dry-run queue status and says no specialist was dispatched.
4. Use `/api/oom-sakkie/agent-dry-runs` locally to inspect the recorded request queue if needed.
5. Do not treat this as live specialist execution; it is an approval/audit rail only.

### 10.9K Oom Sakkie Message Guard Policy Consistency - Local Ready

Purpose:

- Close Claude's 10.9I/J pass-with-nits finding.
- Make `/api/oom-sakkie/policy` report the exact same LLM env set that `modules/oom_sakkie/access.py` uses to guard `/api/oom-sakkie/message`.
- Avoid operator confusion where `/message` is guarded because learning LLM is enabled, but policy says the guard is inactive.

What changed:

- Added public helper `is_llm_message_guard_active()` in `modules/oom_sakkie/access.py`.
- `is_message_request_allowed()` now uses that helper instead of calling the private LLM-surface check directly.
- `modules/oom_sakkie/policy.py` now imports the shared guard env list and helper.
- Runtime policy now exposes:
  - `message_endpoint_access.llm_guard_envs`,
  - `llm_guard_active` derived from the same env set as access enforcement,
  - guard wording that names router, answer composer, and learning analyst.
- Added regression coverage for the exact mismatch Claude found: `OOM_SAKKIE_LLM_LEARNING_ENABLED=true` now makes policy report `message_endpoint_access.llm_guard_active = true`.
- Cleared LLM env inside the basic `/message` route shape test so local developer env settings cannot make that test flaky.

Safety status:

- No new route authority.
- No new write tools.
- No specialist dispatch.
- No specialist LLM execution.
- No autonomous loop.
- No Builder/Forge run, patch application, or deploy.
- This is an honesty/consistency fix only; access enforcement was already fail-safe.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 171 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 496 tests.

Manual check:

1. Set only `OOM_SAKKIE_LLM_LEARNING_ENABLED=true`.
2. Open `/api/oom-sakkie/policy` locally.
3. Confirm `message_endpoint_access.llm_guard_active = true`.
4. Confirm `message_endpoint_access.llm_guard_envs` lists router, answer, and learning envs.
5. Keep `/message` local/private-LAN guarded whenever any listed LLM env is enabled.

### 10.9L Oom Sakkie Sentinel Dry-Run Handoff Packet - Local Ready

Purpose:

- Move one step closer to real specialist dry-runs without enabling execution.
- Require a persisted Agent Dry-Run Request before generating a Sentinel handoff packet.
- Give the owner a structured, reviewable packet for a future Sentinel dry-run while keeping all runtime flags off.

What changed:

- Added `modules/oom_sakkie/agent_dry_run_handoff.py`.
- Added `get_agent_dry_run_request()` to `modules/oom_sakkie/agent_dry_run_store.py`.
- Added protected route `POST /api/oom-sakkie/agent-dry-runs/handoff`.
- The route accepts only:
  - `{"dry_run_request_id": "OSK-AGENT-DRYRUN-..."}`.
- The route loads the stored dry-run request by ID before generating a packet.
- Synthetic handoff payloads are not accepted.
- The handoff builder rejects any request where one of these flags is truthy:
  - `dry_run_enabled`,
  - `dispatch_enabled`,
  - `runs_specialist_llm`,
  - `runs_specialist_tools`,
  - `writes`.
- The packet returns:
  - `mode = agent_dry_run_handoff_only`,
  - `runs_specialist = false`,
  - `runs_specialist_llm = false`,
  - `runs_specialist_tools = false`,
  - `dispatch_enabled = false`,
  - `writes = false`,
  - a Sentinel prompt that explicitly says not to claim inspection, call tools, produce code, or approve itself.

Safety status:

- Packet only.
- Does not run Sentinel.
- Does not dispatch a specialist.
- Does not call a specialist LLM.
- Does not execute specialist tools.
- Does not write farm data.
- Does not run Builder/Forge, apply patches, or deploy.
- Future dry-run execution remains a separate owner-approved step.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 174 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 499 tests.

Manual check:

1. Create or use an existing Sentinel dry-run request ID.
2. POST locally to `/api/oom-sakkie/agent-dry-runs/handoff` with only `dry_run_request_id`.
3. Confirm the response says `mode = agent_dry_run_handoff_only`.
4. Confirm every execution flag is false.
5. Read the prompt and confirm it asks Sentinel for a plan only, not execution.

### 10.9M Oom Sakkie Sentinel Dry-Run Result Gate - Local Ready

Purpose:

- Add the append-only record where a future Sentinel dry-run result can be stored for owner review.
- Keep result recording separate from dry-run request approval and handoff generation.
- Preserve the same safety boundary: the kiosk records what was proposed/reviewed, but does not execute Sentinel or apply any runtime change.

What changed:

- Added migration `supabase/migrations/202606080002_create_oom_sakkie_agent_dry_run_results.sql`.
- The migration creates:
  - `oom_sakkie_agent_dry_run_results`,
  - `oom_sakkie_agent_dry_run_result_events`.
- DB constraints force:
  - `mode = dry_run_result_review_only`,
  - `status = recorded_for_owner_review`,
  - `runs_specialist = false`,
  - `dispatch_enabled = false`,
  - `runs_specialist_llm = false`,
  - `runs_specialist_tools = false`,
  - `writes = false`,
  - `applies_runtime_change = false`.
- DB triggers make both result tables append-only.
- Added `modules/oom_sakkie/agent_dry_run_result_store.py`:
  - `record_agent_dry_run_result()`,
  - `list_agent_dry_run_results()`,
  - `record_agent_dry_run_result_event()`.
- Result recording requires an existing dry-run request and currently accepts only Sentinel requests.
- Added protected local-only routes:
  - `POST /api/oom-sakkie/agent-dry-runs/<dry_run_request_id>/results`,
  - `GET /api/oom-sakkie/agent-dry-run-results`,
  - `POST /api/oom-sakkie/agent-dry-run-results/<dry_run_result_id>/events`.
- Result events are limited to:
  - `accepted_for_learning`,
  - `rejected`,
  - `review_note`.

Safety status:

- Records result/review text only.
- Does not run Sentinel.
- Does not dispatch any specialist.
- Does not call a specialist LLM.
- Does not execute specialist tools.
- Does not write farm data.
- Does not apply runtime changes.
- Does not run Builder/Forge, apply patches, or deploy.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 181 tests.
- `node --check static/js/oomSakkie.js` passed.
- Applied migration `202606080002_create_oom_sakkie_agent_dry_run_results.sql`.
- Live-style smoke against request `OSK-AGENT-DRYRUN-B2E07585AD` created result `OSK-AGENT-DRYRUN-RESULT-2FBFA47000FC` and event `OSK-AGENT-DRYRUN-RESULT-EVENT-4DADAE8AD1B3`; all execution/runtime/write flags remained false.
- Full local `python -m unittest` passed at 506 tests.

Manual check:

1. Use a persisted Sentinel dry-run request ID.
2. POST a result to `/api/oom-sakkie/agent-dry-runs/<id>/results`.
3. Confirm the response says `mode = dry_run_result_review_only`.
4. Confirm every execution/runtime/write flag is false.
5. Add a `review_note`, `rejected`, or `accepted_for_learning` event only after reading the result.

### 10.9N Oom Sakkie Sentinel Review Queue Status - Local Ready

Purpose:

- Make the new dry-run result gate visible through normal Oom Sakkie chat.
- Keep one `Dry-Run Queue` quick action instead of adding more clutter.
- Let the owner ask what Sentinel dry-run requests/results need review without opening raw endpoints.

What changed:

- `agent_dry_run_status` now reads:
  - recent dry-run requests,
  - recent dry-run results.
- The answer now reports:
  - request count,
  - requests waiting for manual review,
  - cancelled requests,
  - result count,
  - results waiting for owner review,
  - results accepted for learning.
- If either the request queue or result queue is unavailable, the tool returns a stale warning instead of confidently saying nothing is waiting.
- Runtime flags now include `applies_runtime_change = false`.
- Deterministic routing now catches:
  - `sentinel result queue`,
  - `dry-run result`,
  - `dry-run results`,
  - `sentinel review queue`.
- The kiosk quick action still says `Dry-Run Queue`, but now asks `What is the Sentinel dry-run result queue status?`

Safety status:

- Read-only queue status only.
- Does not create dry-run requests.
- Does not create dry-run results.
- Does not accept/reject results.
- Does not run Sentinel.
- Does not dispatch specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data or apply runtime changes.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 182 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local `python -m unittest` passed at 507 tests.

Manual check:

1. Reload `/oom-sakkie`.
2. Click `Dry-Run Queue`.
3. Confirm Oom Sakkie mentions both dry-run requests and dry-run results.
4. Confirm the safety note says no specialist was dispatched and no runtime change was applied.

### 10.9O Oom Sakkie Sentinel Dry-Run Result Review Packet - Local Ready

Purpose:

- Make one stored Sentinel dry-run result easy for the owner to review.
- Keep the result review anchored to a persisted `dry_run_result_id` instead of accepting synthetic payloads.
- Prepare the future owner-approval conversation without running Sentinel or applying any runtime change.

What changed:

- Added `get_agent_dry_run_result(dry_run_result_id)`.
- Added `build_agent_dry_run_result_review_packet(dry_run_result)`.
- Added protected `GET /api/oom-sakkie/agent-dry-run-results/<dry_run_result_id>/review-packet`.
- The packet returns:
  - result text,
  - findings,
  - latest review event,
  - owner options: `accepted_for_learning`, `rejected`, `review_note`,
  - a visible review guard with every execution/runtime/write flag false.
- The packet builder rejects any stored result with unsafe execution flags before returning a packet.

Safety status:

- Review-packet only.
- Does not run Sentinel.
- Does not dispatch specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not accept/reject the result by itself.
- Does not apply runtime changes.
- Does not run Builder/Forge, apply patches, or deploy.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 186 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Use a persisted dry-run result ID.
2. Open `/api/oom-sakkie/agent-dry-run-results/<id>/review-packet` from the local browser.
3. Confirm `mode = dry_run_result_review_packet`.
4. Confirm `owner_options` lists accept/reject/review-note only.
5. Confirm every review guard execution/runtime/write flag is false.

### 10.9P Oom Sakkie Sentinel Result Review UI - Local Ready

Purpose:

- Move Sentinel dry-run result review out of raw JSON and into the kiosk workbench.
- Let the owner review, accept for learning, reject, or add a note from clear cards.
- Keep every action event-only; no specialist execution or runtime change.

What changed:

- Added `Sentinel Result Review` panel inside the System Workbench.
- Added refresh button `oom_refresh_agent_result_reviews`.
- Added result review container `oom_agent_result_reviews`.
- Kiosk now loads `/api/oom-sakkie/agent-dry-run-results?limit=8` with the rest of review data.
- Result cards are grouped into:
  - `Needs Owner Review`,
  - `Reviewed / Closed`.
- Each card shows:
  - result ID,
  - linked dry-run request ID,
  - result text,
  - findings,
  - latest event,
  - review-only guard.
- Card actions:
  - `Open Review Packet` fetches the protected packet route,
  - `Accept For Learning` records `accepted_for_learning`,
  - `Reject` records `rejected`,
  - `Add Note` records `review_note`.
- Workbench `Next action` now includes pending Sentinel result reviews before build/patch/deploy work.

Safety status:

- UI-only plus append-only event recording.
- Does not run Sentinel.
- Does not dispatch specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not apply runtime changes.
- Does not run Builder/Forge, apply patches, or deploy.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 186 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Reload `/oom-sakkie`.
2. Open `System Workbench`.
3. Find `Sentinel Result Review`.
4. Confirm the existing smoke result appears as a card.
5. Click `Open Review Packet` and confirm it renders below the queue.
6. Use `Add Note` first if testing safely; it should record text only and refresh the card.
7. Only click `Accept For Learning` or `Reject` when you mean to record that decision.

### 10.9Q Oom Sakkie Agent Learning Evidence - Local Ready

Purpose:

- Make accepted Sentinel dry-run results useful after owner approval.
- Let Oom Sakkie answer what the agent system has learned so far.
- Keep this as evidence summarization only, not runtime behavior.

What changed:

- Added read-only `agent_learning_evidence` tool.
- Added deterministic routing for:
  - `what did Sentinel learn`,
  - `agent learning evidence`,
  - `accepted Sentinel`,
  - `what have agents learned`.
- Added kiosk quick action `Agent Learning`.
- The tool reads recent dry-run results and filters only those whose latest event is `accepted_for_learning`.
- Output includes accepted result IDs, linked request IDs, findings, accepted timestamp, and accepted note.

Safety status:

- Read-only evidence summary only.
- Does not run Sentinel.
- Does not dispatch specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not apply runtime changes.
- Does not run Builder/Forge, apply patches, or deploy.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 187 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Reload `/oom-sakkie`.
2. Click `Agent Learning`.
3. Confirm Oom Sakkie reports accepted Sentinel evidence, not pending/rejected results.
4. Confirm the safety note says no specialist was dispatched and no runtime change was applied.

### 10.9R Oom Sakkie Agent Learning Ledger UI - Local Ready

Purpose:

- Make accepted agent learning evidence visible in the System Workbench.
- Separate accepted evidence from the Sentinel result review queue.
- Give the owner a readable ledger of what the agent platform is allowed to remember for future planning.

What changed:

- Added `Agent Learning Ledger` panel inside the System Workbench.
- Added refresh button `oom_refresh_agent_learning_ledger`.
- Added ledger container `oom_agent_learning_ledger`.
- The ledger reuses the dry-run result list but displays only results whose latest event is `accepted_for_learning`.
- Each ledger card shows:
  - dry-run result ID,
  - linked request ID,
  - specialist slug,
  - accepted timestamp,
  - result text,
  - accepted findings,
  - owner acceptance note.

Safety status:

- UI-only accepted-evidence display.
- Does not run Sentinel.
- Does not dispatch specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not apply runtime changes.
- Does not run Builder/Forge, apply patches, or deploy.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 187 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Reload `/oom-sakkie`.
2. Open `System Workbench`.
3. Find `Agent Learning Ledger`.
4. Confirm the accepted Sentinel result appears there.
5. Confirm pending/rejected/review-note-only results are not shown as learning evidence.

### 10.9S Oom Sakkie Accepted Learning Roadmap Link - Local Ready

Purpose:

- Let the agent roadmap reflect owner-accepted Sentinel learning evidence.
- Keep accepted evidence as planning context only, not as runtime permission.

What changed:

- Added a shared accepted-learning snapshot helper inside `modules/oom_sakkie/tools.py`.
- `agent_learning_evidence` and `agent_activation_plan` now use the same accepted-result filtering:
  - only `latest_event.event_type = accepted_for_learning`,
  - bounded to the latest accepted evidence,
  - no pending/rejected/review-note-only result becomes learning evidence.
- `agent_activation_plan` now reports whether accepted Sentinel evidence exists when the owner asks for the agent roadmap.
- The roadmap summary explicitly says runtime remains locked.
- The roadmap `llm_context` now includes:
  - `accepted_learning_count`,
  - `accepted_learning`,
  - existing false runtime/dispatch/write flags.

Safety status:

- Read-only evidence plumbing only.
- Does not run Sentinel.
- Does not dispatch specialists.
- Does not call a specialist LLM.
- Does not execute specialist tools.
- Does not write farm data.
- Does not apply runtime changes.
- Does not run Builder/Forge, apply patches, or deploy.

Verification:

- Added tests that the activation roadmap:
  - works when no accepted evidence exists,
  - surfaces one accepted Sentinel result when present,
  - keeps `dispatch_enabled = false`,
  - keeps the no-runtime-change safety note.

Manual check:

1. Open `/oom-sakkie`.
2. Click `Agent Roadmap`.
3. Confirm Oom Sakkie mentions accepted Sentinel learning evidence if a result has been accepted.
4. Confirm the answer still says no specialist was dispatched and runtime remains locked.

### 10.9T Oom Sakkie Visible Agent Roadmap Panel - Local Ready

Purpose:

- Put the Agent Roadmap where the owner expected to find it: inside the System Workbench.
- Make the path to live agents visible without requiring a chat question.

What changed:

- Added protected read-only endpoint `GET /api/oom-sakkie/agents/activation-plan`.
- The endpoint returns:
  - the current activation plan,
  - accepted Sentinel learning evidence,
  - accepted learning count,
  - review guard flags with specialist/runtime/write actions false.
- Added `Agent Roadmap` panel in the Workbench below `Agent Crew Foundation`.
- Added refresh button `oom_refresh_agent_roadmap`.
- Added JS renderer `renderAgentRoadmap(data)` and loader `loadAgentRoadmap()`.
- The panel shows:
  - recommended next stage,
  - accepted evidence count,
  - first safe candidate,
  - activation stages,
  - up to three accepted Sentinel evidence cards.

Safety status:

- Read-only panel data only.
- Does not run Sentinel.
- Does not dispatch specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not apply runtime changes.
- Does not run Builder/Forge, apply patches, or deploy.

Verification:

- Added route tests for:
  - local roadmap endpoint shape,
  - non-local denial,
  - no runtime/write guard flags.
- Added frontend contract checks for the panel, refresh button, fetch route, renderer, and safety copy.

Manual check:

1. Open `/oom-sakkie`.
2. Open `System Workbench`.
3. Find `Agent Roadmap` directly under `Agent Crew Foundation`.
4. Confirm it shows the next stage, first safe candidate, accepted evidence count, and runtime locked guard.
5. Click `Refresh` and confirm it reloads without sending a chat message.

### 10.9U Oom Sakkie Sentinel Dry-Run Request Button - Local Ready

Purpose:

- Let the owner start the next safe agent gate from the visible Agent Roadmap panel.
- Reduce raw endpoint/manual JSON work while keeping all execution disabled.

What changed:

- Added `Request Sentinel Dry-Run` button to the `Agent Roadmap` panel.
- Added JS handler `requestSentinelDryRun(button)`.
- The handler posts to the existing protected append-only request endpoint:
  - `POST /api/oom-sakkie/agent-dry-runs`.
- The payload is fixed to:
  - `specialist_slug = sentinel`,
  - `requested_by = kiosk`,
  - owner text explaining it came from the Roadmap panel,
  - guardrails forbidding dispatch, specialist LLM execution, specialist tool execution, writes, posts, sales, controls, patches, and deploys.
- On success the Roadmap panel immediately shows the recorded request ID and the false execution flags.

Safety status:

- Records owner approval intent only.
- Does not run Sentinel.
- Does not dispatch specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not apply runtime changes.
- Does not run Builder/Forge, apply patches, or deploy.

Verification:

- Added frontend contract checks for the Roadmap request button, request function, request endpoint, Sentinel slug, and no-run copy.
- Added route test that the Roadmap-style request remains request-only with every execution flag false.

Manual check:

1. Open `/oom-sakkie`.
2. Open `System Workbench`.
3. In `Agent Roadmap`, click `Request Sentinel Dry-Run`.
4. Confirm a card appears with a new `OSK-AGENT-DRYRUN-...` request ID.
5. Confirm the card says Sentinel did not run and dispatch / specialist LLM / tools / writes are off.

### 10.9V Oom Sakkie Sentinel Dry-Run Mini-Pipeline UI - Local Ready

Purpose:

- Make the first specialist gate usable end-to-end from the Workbench.
- Keep the owner out of raw JSON endpoints while preserving manual approval and no-execution boundaries.

What changed:

- Added `Sentinel Dry-Run Requests` panel inside the System Workbench.
- The panel loads `GET /api/oom-sakkie/agent-dry-runs?limit=8`.
- Each request card shows:
  - request ID,
  - specialist slug,
  - purpose,
  - latest event if present,
  - dispatch / specialist LLM / specialist tools / writes guard flags.
- Each pending request has:
  - `Open Handoff` button,
  - `Use For Result` button.
- Added `Sentinel dry-run handoff` display panel:
  - calls `POST /api/oom-sakkie/agent-dry-runs/handoff`,
  - renders the prompt as text,
  - includes `Copy Sentinel Handoff`.
- Added `Record Sentinel Result` form:
  - dry-run request ID,
  - result text,
  - optional findings, one per line,
  - posts to `POST /api/oom-sakkie/agent-dry-runs/<id>/results`.

Safety status:

- Request queue is read-only.
- Handoff is prompt-only.
- Result recording is append-only review text.
- Does not run Sentinel.
- Does not dispatch specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not apply runtime changes.
- Does not run Builder/Forge, apply patches, or deploy.

Verification:

- Added frontend contract checks for:
  - dry-run request panel,
  - handoff panel,
  - result recorder inputs/button,
  - request queue fetch,
  - handoff POST,
  - result POST,
  - no-run display copy.

Manual check:

1. Open `/oom-sakkie`.
2. Open `System Workbench`.
3. Find `Sentinel Dry-Run Requests`.
4. Click `Open Handoff` on a request.
5. Confirm the handoff prompt appears and guard says runs specialist / LLM / tools / writes are off.
6. Click `Use For Result`.
7. Paste a short reviewed result and findings.
8. Click `Record Result For Review`.
9. Confirm the result appears in `Sentinel Result Review` for Accept / Reject / Note.

### 10.9W Oom Sakkie Workbench Sentinel Next Action - Local Ready

Purpose:

- Make the Workbench `Next action` card follow the Sentinel dry-run pipeline order.
- Avoid telling the owner to review a result before the request handoff step is visible.

What changed:

- The Workbench now tracks latest dry-run request queue data.
- `Next action` counts now include:
  - `Sentinel handoff`,
  - `Sentinel result`,
  - `Build`,
  - `Patch`,
  - `Deploy`.
- Priority order is now:
  1. pending Sentinel dry-run request handoff,
  2. pending Sentinel dry-run result review,
  3. build handoff,
  4. patch review,
  5. deploy decision.
- Loading or refreshing dry-run requests updates the next-action card.
- Recording a dry-run result refreshes dry-run requests, result reviews, and roadmap state.

Safety status:

- UI state only.
- Does not run Sentinel.
- Does not dispatch specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not apply runtime changes.

Verification:

- Added frontend contract coverage for:
  - `latestAgentDryRunRequestsData`,
  - `pendingAgentRequests`,
  - `Sentinel handoff`,
  - `Open Sentinel handoff for`.

Manual check:

1. Open `/oom-sakkie`.
2. Open `System Workbench`.
3. If a Sentinel request exists, confirm `Next action` says to open the Sentinel handoff.
4. After recording a result, confirm `Next action` moves to Sentinel result review.

### 10.9X Oom Sakkie Live-PG Audit Rail Smoke - Local Ready

Purpose:

- Close Claude's strongest remaining test gap: prove the append-only triggers and no-execution CHECK constraints on the Oom Sakkie audit rails against a real Postgres when `DATABASE_URL` is available.
- Keep the test gated so normal local/CI runs skip it when no database is configured.

What changed:

- Extended `tests/test_oom_sakkie_service.py` with a live-PG append-only smoke for:
  - `oom_sakkie_build_requests`,
  - `oom_sakkie_build_request_events`,
  - `oom_sakkie_patch_proposals`,
  - `oom_sakkie_patch_proposal_events`,
  - `oom_sakkie_deploy_decisions`,
  - `oom_sakkie_agent_dry_run_requests`,
  - `oom_sakkie_agent_dry_run_events`,
  - `oom_sakkie_agent_dry_run_results`,
  - `oom_sakkie_agent_dry_run_result_events`.
- The test inserts one valid audit chain, then asserts `UPDATE` and `DELETE` both raise an `append-only` exception for every table.
- Extended the existing live-PG no-execution CHECK test to also reject:
  - `dry_run_enabled = true` on `oom_sakkie_agent_dry_run_requests`,
  - `runs_specialist = true` on `oom_sakkie_agent_dry_run_results`.

Safety status:

- Test-only.
- Runs only when `DATABASE_URL` and `psycopg` are available.
- Inserts audit test rows only.
- Does not run specialists.
- Does not dispatch agents.
- Does not call specialist LLMs.
- Does not execute tools.
- Does not write farm operating data.
- Does not apply runtime changes.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 192 tests with database-gated tests skipped when `DATABASE_URL` is unavailable.
- `node --check static/js/oomSakkie.js` passed.

Manual/live check:

1. Ensure Supabase migrations through `202606080002_create_oom_sakkie_agent_dry_run_results.sql` are applied.
2. Set `DATABASE_URL`.
3. Run:

   ```powershell
   .\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service.OomSakkieServiceTests.test_live_pg_review_gate_constraints_reject_action_flags_when_database_url_is_configured tests.test_oom_sakkie_service.OomSakkieServiceTests.test_live_pg_review_gate_tables_are_append_only_when_database_url_is_configured
   ```

4. Expected: both pass; no audit table permits mutation or execution flags.

### 10.9Y Oom Sakkie Prism Dry-Run Request Gate - Local Ready

Purpose:

- Start the next planned specialist safely after Sentinel by adding Prism to the same request -> handoff -> reviewed result rail.
- Keep this as dry-run planning only; Prism still does not run.

What changed:

- `agent_dry_run_store.py` now has an explicit approved dry-run allowlist: `sentinel`, `prism`.
- Prism requests default to the same no-execution mode and only expose read-only context.
- `agent_dry_run_handoff.py` now supports approved specialists from the allowlist and generates a specialist-specific prompt:
  - Sentinel remains the safety/readiness reviewer.
  - Prism is the kiosk/interface design reviewer.
- `agent_dry_run_result_store.py` now preserves the approved request's specialist slug in review-only result records instead of hard-coding Sentinel.
- The Agent Roadmap panel now has `Request Prism Dry-Run` next to `Request Sentinel Dry-Run`.
- Prism request UI posts an append-only dry-run request with guardrails:
  - no live dispatch,
  - no specialist LLM execution,
  - no specialist tool execution,
  - no generated assets/code edits/patch/deploy,
  - owner review required for any future result.

Safety status:

- Records request intent only.
- Handoff is prompt-only.
- Result recording remains append-only review text.
- Does not run Prism.
- Does not dispatch specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not generate assets.
- Does not edit code, apply patches, or deploy.

Verification:

- Added service tests for Prism request params, Prism handoff packet, and Prism result params.
- Added route test for Prism dry-run request creation through the existing protected endpoint.
- Added frontend contract checks for the Prism request button and payload.
- Focused Oom Sakkie service/routes/frontend tests passed at 196 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Open `/oom-sakkie`.
2. Open `System Workbench`.
3. Find `Agent Roadmap`.
4. Click `Request Prism Dry-Run`.
5. Confirm a Prism request appears in `Sentinel Dry-Run Requests` / dry-run request queue.
6. Open its handoff and confirm it says Prism is the kiosk/interface design reviewer.
7. Confirm guard flags still say dispatch, specialist LLM, tools, and writes are off.

### 10.9Z Oom Sakkie Generic Agent Dry-Run Workbench Labels - Local Ready

Purpose:

- Remove Sentinel-specific UI wording from the shared dry-run rail now that Prism can also enter it.
- Keep the Workbench easier to follow as the planned crew grows.

What changed:

- Renamed live Workbench labels:
  - `Sentinel Dry-Run Requests` -> `Agent Dry-Run Requests`,
  - `Record Sentinel Result` -> `Record Agent Result`,
  - `Sentinel Result Review` -> `Agent Result Review`.
- Updated JS empty/error/next-action copy from Sentinel-specific wording to generic agent wording.
- Handoff cards now use the packet's `specialist_name`, so Sentinel and Prism are named correctly.
- Workbench `Next action` now says `agent handoff` / `agent result review` instead of `Sentinel handoff` / `Sentinel result review`.

Safety status:

- UI wording only.
- Does not change routes, DB schema, or allowed operations.
- Does not run agents.
- Does not dispatch specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not apply runtime changes, patches, or deploys.

Verification:

- Updated frontend contract assertions for the generic dry-run Workbench labels.
- Focused Oom Sakkie service/routes/frontend tests passed at 196 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Open `/oom-sakkie`.
2. Open `System Workbench`.
3. Confirm shared panels read `Agent Dry-Run Requests`, `Record Agent Result`, and `Agent Result Review`.
4. Confirm Sentinel and Prism request rows still show their specific `specialist_slug`.

### 10.9AA Oom Sakkie Agent Dry-Run Browser Behavior Contracts - Local Ready

Purpose:

- Retire the remaining dry-run UI behavior gap without widening runtime authority.
- Pin the shared Agent Dry-Run request/result Workbench behavior now that Sentinel and Prism both use it.

What changed:

- Fixed the last Sentinel-specific empty-state strings in the shared dry-run queue.
- Added frontend contract coverage that the agent dry-run/result UI:
  - has no `setInterval` background polling,
  - loads dry-run requests/results/review packets only through explicit fetch paths,
  - wires request, result-record, accept, reject, and review-note actions through explicit button handlers,
  - keeps render-only sections free of hidden fetches or event writes,
  - renders generic empty states for agent requests/results.

Safety status:

- Test and UI-copy hardening only.
- Does not add routes, migrations, tools, LLM calls, specialist dispatch, specialist tool execution, farm writes, runtime changes, Builder/Forge execution, patch application, or deploys.
- Review/event writes remain append-only and owner-clicked only.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 197 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Open `/oom-sakkie`.
2. Open `System Workbench`.
3. Confirm `Agent Dry-Run Requests` and `Agent Result Review` do not refresh on a timer.
4. Confirm request/result/event actions happen only after clicking the relevant button.
5. Confirm empty states say `agent`, not only `Sentinel`.

### 10.9AB Oom Sakkie Approved Read-Only Dry-Run Cohort - Local Ready

Purpose:

- Let the planned farm/business specialists enter the same append-only dry-run request -> handoff -> reviewed-result rail as Sentinel and Prism.
- Build more of the agent platform without enabling live specialist dispatch or external authority.

What changed:

- Expanded the approved dry-run request allowlist to the risk-0 read-only specialists:
  - `ledger`,
  - `atlas`,
  - `rootline`,
  - `herdmaster`,
  - `butcher`,
  - `quartermaster`,
  - plus existing `sentinel` and `prism`.
- Kept `beacon`, `forge`, and `gatekeeper` out of the dry-run allowlist for now because they touch public draft, code/build, or routing-policy surfaces.
- Added fixed default read-only tool context for each approved specialist.
- Added specialist names/roles to the dry-run handoff prompt so each packet reads as that planned specialist while still saying it is a dry-run handoff only.
- Added one selected-specialist dropdown in the Agent Roadmap panel instead of adding a long row of buttons.

Safety status:

- No specialist runs.
- No specialist LLM executes.
- No specialist tool executes.
- No farm data is written.
- No public/customer output is generated.
- No Builder/Forge, patch, deploy, Telegram cutover, physical control, or runtime flag is enabled.
- Request/result/event records remain append-only owner-reviewed planning/audit records.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 200 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Open `/oom-sakkie`.
2. Open `System Workbench`.
3. In `Agent Roadmap`, choose Ledger/Atlas/Rootline/Herdmaster/Butcher/Quartermaster from the dropdown.
4. Click `Request Selected Dry-Run`.
5. Confirm an append-only request appears and every visible guard still says dispatch, specialist LLM, specialist tools, and writes are off.

### 10.9AC Oom Sakkie Activation Roadmap Cohort Visibility - Local Ready

Purpose:

- Make the Agent Roadmap reflect the same approved dry-run cohort as the backend request gate.
- Keep the owner-facing roadmap honest about what is allowed now: dry-run request records only, not live runtime.

What changed:

- The activation plan now includes Sentinel, Prism, Atlas, Ledger, Rootline, Herdmaster, Butcher, and Quartermaster as dry-run candidates.
- Each candidate exposes `dry_run_request_allowed = true` while `allowed_now = false` keeps live runtime locked.
- Beacon, Forge, and Gatekeeper remain absent from the dry-run candidate list.
- The kiosk Agent Roadmap now renders an `Approved dry-run candidates` section with each candidate's first slice and guard line.

Safety status:

- Roadmap/display data only.
- Does not run agents, dispatch specialists, call specialist LLMs, execute specialist tools, write farm data, produce customer/public output, run Builder/Forge, apply patches, deploy, cut over Telegram, or control hardware.
- Dry-run request authority remains bounded by the append-only request gate from 10.9AB.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 200 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Open `/oom-sakkie`.
2. Open `System Workbench`.
3. Refresh `Agent Roadmap`.
4. Confirm `Approved dry-run candidates` lists the approved cohort.
5. Confirm each guard reads dry-run request allowed and runtime locked.

### 10.9AD Oom Sakkie Specialist Dry-Run Handoff Quality - Local Ready

Purpose:

- Make approved specialist handoff packets useful enough for owner-reviewed dry-run planning.
- Give each planned specialist a role-specific review shape without executing the specialist.

What changed:

- Added fixed specialist review guides for Sentinel, Prism, Ledger, Atlas, Rootline, Herdmaster, Butcher, and Quartermaster.
- Each handoff packet now includes:
  - `focus_questions`,
  - `required_context`,
  - `risk_checks`,
  - `owner_approval_question`.
- Handoff prompts now include those specialist-specific sections before the generic no-go rules.
- Ledger handoffs now explicitly check business/profit risk such as fake revenue, unapproved price changes, and customer-facing wording.
- Rootline handoffs now explicitly check physical-control risk such as pump/control commands and stale weather/irrigation assumptions.

Safety status:

- Pure packet/prompt text generation only.
- Does not run specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not produce customer/public output.
- Does not run Builder/Forge, apply patches, deploy, cut over Telegram, or control hardware.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 201 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Create or open a Ledger or Rootline dry-run request.
2. Generate its handoff.
3. Confirm the packet names the correct specialist role.
4. Confirm the prompt says not to call tools, not to claim inspection, and to wait for owner approval.
5. Confirm role-specific focus/context/risk sections are present.

### 10.9AE Oom Sakkie Specialist Result Evidence Boundaries - Local Ready

Purpose:

- Make reviewed dry-run results safer to accept by showing exactly what accepted evidence may and must not influence.
- Keep accepted learning useful for future planning without creating hidden runtime authority.

What changed:

- Added deterministic result-review profiles for Sentinel, Prism, Ledger, Atlas, Rootline, Herdmaster, Butcher, and Quartermaster.
- Result review packets now include:
  - `evidence_kind`,
  - `may_influence`,
  - `must_not_influence`,
  - `owner_review_question`.
- Ledger evidence may guide business-brief questions and internal offer planning, but must not influence customer messages, price changes, quotes, or invoices.
- Rootline evidence may guide read-only weather/irrigation inspection questions, but must not influence pump/valve commands, irrigation schedules, or physical controls.
- The kiosk review packet panel now displays Evidence kind, May influence, Must not influence, and Owner question.

Safety status:

- Review packet and UI display only.
- Does not run specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not produce customer/public output.
- Does not enable runtime flags, run Builder/Forge, apply patches, deploy, cut over Telegram, or control hardware.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 203 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Open an Agent Result Review packet.
2. Confirm Evidence kind, May influence, Must not influence, and Owner question are visible.
3. Confirm accepting evidence still records only an append-only review event.
4. Confirm no specialist/runtime/write guard changes after acceptance.

### 10.9AF Oom Sakkie Per-Specialist Dry-Run Queue Status - Local Ready

Purpose:

- Let Oom Sakkie answer which planned specialists have dry-run requests/results in the review queue.
- Make the agent queue easier to understand without reading raw Workbench lists.

What changed:

- `agent_dry_run_status` now calculates `specialist_counts` for loaded request/result rows.
- Counts include:
  - total requests,
  - requests waiting,
  - total results,
  - results waiting,
  - accepted-for-learning results.
- The spoken/display summary now includes per-specialist queue items such as `ledger: 1 request(s), 1 result(s)`.

Safety status:

- Read-only queue summarization only.
- Does not run specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not change review events, runtime flags, Builder/Forge, patches, deploys, Telegram, public output, or physical controls.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 203 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Ask Oom Sakkie: `What is the agent dry-run queue status?`
2. Confirm the answer includes queue totals and specialist-specific queue items when present.
3. Confirm the safety note still says no specialist was dispatched and no runtime change was applied.

### 10.9AG Oom Sakkie Generic Agent Learning Evidence - Local Ready

Purpose:

- Make accepted dry-run learning evidence match the widened approved specialist cohort.
- Stop owner-facing runtime wording from implying accepted learning is Sentinel-only now that Ledger, Rootline, Herdmaster, Butcher, Quartermaster, Atlas, and Prism can also produce reviewed evidence.

What changed:

- `accepted_agent_learning_snapshot` now includes `accepted_by_specialist` counts.
- `agent_learning_evidence` now says accepted agent result(s), not accepted Sentinel result(s).
- `agent_activation_plan` now reports accepted learning evidence by specialist when evidence exists.
- The Agent Roadmap panel now labels the section `Accepted agent learning` and uses generic accepted-agent fallback copy.
- Tool description for `agent_learning_evidence` now says accepted agent learning evidence.

Safety status:

- Read-only evidence summarization only.
- Accepted evidence remains planning context only.
- Does not run specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not change review events, enable runtime flags, run Builder/Forge, apply patches, deploy, cut over Telegram, produce public/customer output, or control hardware.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 203 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Accept dry-run result evidence for any non-Sentinel approved specialist, such as Ledger or Rootline.
2. Ask Oom Sakkie: `What did the agents learn from accepted results?`
3. Confirm the answer says accepted agent evidence and names the specialist count.
4. Confirm the safety note still says no specialist was dispatched and no runtime change was applied.

### 10.9AH Oom Sakkie Roadmap Learning Counts - Local Ready

Purpose:

- Make the Agent Roadmap panel show which planned specialists already have accepted evidence.
- Keep the owner-facing roadmap useful as the approved dry-run cohort grows.

What changed:

- `GET /api/oom-sakkie/agents/activation-plan` now returns `accepted_by_specialist`.
- The Agent Roadmap panel now displays a compact `accepted by specialist` line.
- Frontend and route tests pin the new field and rendered label.

Safety status:

- Read-only route/panel data only.
- Does not create requests, results, or events.
- Does not run specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not enable runtime flags, run Builder/Forge, apply patches, deploy, cut over Telegram, produce public/customer output, or control hardware.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 203 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Open `/oom-sakkie`.
2. Open `System Workbench`.
3. Refresh `Agent Roadmap`.
4. Confirm the `Accepted agent learning` section shows `accepted by specialist ...`.
5. Confirm all runtime/write/dispatch guards remain locked.

### 10.9AI Oom Sakkie Audit Rail CI Workflow - Local Ready

Purpose:

- Convert the DATABASE_URL-gated audit-rail smoke from an optional local check into a CI-enforced check when GitHub Actions runs.
- Keep append-only/no-execution guarantees tested against a real disposable Postgres database.

What changed:

- Added `.github/workflows/oom-sakkie-audit-rails.yml`.
- The workflow starts a Postgres 16 service.
- It installs `requirements.txt`.
- It applies the reviewed Oom Sakkie audit migrations only:
  - trace tables,
  - trace safety notes,
  - trace append-only triggers,
  - build request/event tables,
  - patch proposal/event tables,
  - deploy decision table,
  - agent dry-run request/event tables,
  - agent dry-run result/event tables.
- It runs `python -m unittest` with `DATABASE_URL` configured, so the live-PG audit rail checks execute instead of skipping.
- It runs `node --check static/js/oomSakkie.js`.

Safety status:

- CI/test configuration only.
- Uses a disposable GitHub Actions Postgres service.
- Does not add routes, tools, runtime authority, specialist dispatch, specialist LLM/tool execution, farm writes, public/customer output, Builder/Forge execution, patch application, deploy, Telegram cutover, or physical controls.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 204 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Push a branch or open a PR.
2. Confirm the `Oom Sakkie Audit Rails` workflow starts.
3. Confirm migrations apply in order.
4. Confirm the full unittest suite runs with `DATABASE_URL` configured.
5. Confirm the append-only/no-execution live-PG tests do not skip in CI.

### 10.9AJ Oom Sakkie Browser Behavior Checklist - Local Ready

Purpose:

- Make Claude's requested browser-behavior pass repeatable without adding Playwright or another dependency yet.
- Give the owner one clear checklist for the now-busier multi-specialist Workbench UI.

What changed:

- Added `docs/06-operations/OOM_SAKKIE_BROWSER_BEHAVIOR_CHECKLIST.md`.
- The checklist covers:
  - multi-specialist dry-run request UI,
  - handoff and result review,
  - accepted learning and roadmap counts,
  - no background polling,
  - explicit owner-click event actions,
  - browser voice start/stop and five-turn loop cap.
- Added frontend contract coverage that the CI workflow and browser checklist exist and name the core safety expectations.

Safety status:

- Documentation and regression coverage only.
- Does not run specialists.
- Does not call specialist LLMs.
- Does not execute specialist tools.
- Does not write farm data.
- Does not enable runtime flags, run Builder/Forge, apply patches, deploy, cut over Telegram, produce public/customer output, or control hardware.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 204 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Follow `docs/06-operations/OOM_SAKKIE_BROWSER_BEHAVIOR_CHECKLIST.md`.
2. Record any failures as owner feedback before widening the runtime foundation further.

### 10.9AK Oom Sakkie Audit Rail CI Scope Hardening - Local Ready

Purpose:

- Keep the audit-rail CI job focused on the Oom Sakkie safety rail it is meant to prove.
- Avoid future unrelated real-DB tests failing this job because only the Oom Sakkie audit migrations are applied.

What changed:

- `.github/workflows/oom-sakkie-audit-rails.yml` now runs:

```powershell
python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts
```

- The workflow still starts disposable Postgres, applies the reviewed Oom Sakkie audit migrations, and runs `node --check static/js/oomSakkie.js`.
- Frontend contract coverage now pins the scoped command.

Safety status:

- CI/test configuration only.
- Does not touch production data.
- Does not add routes, tools, runtime authority, specialist dispatch, specialist LLM/tool execution, farm writes, public/customer output, Builder/Forge execution, patch application, deploy, Telegram cutover, or physical controls.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 204 tests.
- Full local unittest suite passed at 534 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Push a branch or open a PR.
2. Confirm `Oom Sakkie Audit Rails` applies the Oom Sakkie audit migrations.
3. Confirm the workflow runs the focused Oom Sakkie test modules, not unrelated DB suites.
4. Confirm the DATABASE_URL-gated live-PG Oom Sakkie tests execute in CI.

### 10.9AL Oom Sakkie Agent Runtime Readiness Tool - Local Ready

Purpose:

- Let Oom Sakkie explain what is still blocking real/live agents.
- Keep the Jarvis end goal concrete while runtime authority remains locked.

What changed:

- Added `get_agent_runtime_readiness()` in `modules/oom_sakkie/agent_runtime.py`.
- Added read-only tool `agent_runtime_readiness`.
- Added deterministic routing for phrases such as:
  - `are we ready for live agents`,
  - `what still blocks runtime`,
  - `before agents can run`.
- The readiness payload reports:
  - ready gates,
  - manual gates,
  - locked gates,
  - approved dry-run candidates,
  - blocked capabilities,
  - next safe action.

Safety status:

- Read-only checklist only.
- Runtime remains disabled.
- Dispatch remains disabled.
- Specialist LLM/tool execution remains disabled.
- Writes, public/customer output, Builder/Forge execution, patch application, deploy, Telegram cutover, and physical controls remain blocked.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 206 tests.
- `node --check static/js/oomSakkie.js` passed.

Manual check:

1. Ask Oom Sakkie: `Are we ready for live agents?`
2. Confirm it uses `agent_runtime_readiness`.
3. Confirm the answer says manual checks are still required and live-authority gates remain locked.
4. Confirm the safety note says no specialist was dispatched and no runtime/write/public/control action occurred.

### 10.9AM Oom Sakkie Browser Behavior Smoke Gate - Local Ready

Purpose:

- Turn the most important browser-behavior checklist items into an automated local/CI smoke.
- Keep this dependency-free until live specialist execution is actually being considered.

What changed:

- Added `tests/oom_sakkie_browser_behavior_smoke.js`.
- The smoke executes the real `static/js/oomSakkie.js` in a small fake DOM.
- It fails if kiosk startup creates background polling intervals.
- It fails if kiosk startup performs hidden POST requests.
- It verifies startup performs only read-only GET loads.
- It simulates owner clicks for:
  - Sentinel dry-run request,
  - agent dry-run result recording,
  - quick ask message submission.
- It verifies those POSTs occur only after explicit click handlers fire.
- The GitHub Actions audit-rail workflow now runs the smoke after `node --check`.

Safety status:

- Test/CI hardening only.
- No browser automation dependency was added.
- No routes, tools, migrations, runtime flags, specialist dispatch, LLM calls, writes, public/customer output, Builder/Forge execution, patch application, deploy, Telegram cutover, or physical controls were added.

Verification:

- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- Focused Oom Sakkie service/routes/frontend tests passed at 207 tests.
- `node --check static/js/oomSakkie.js` passed.
- Full local unittest suite passed at 537 tests.

Manual check:

1. Confirm the next `Oom Sakkie Audit Rails` GitHub Actions run includes `Run Oom Sakkie browser behavior smoke`.
2. Keep `docs/06-operations/OOM_SAKKIE_BROWSER_BEHAVIOR_CHECKLIST.md` as the human browser pass until a full Playwright suite is deliberately added.

### 10.9AN Oom Sakkie Agent Operating Contracts - Local Ready

Purpose:

- Make each planned specialist's boundaries explicit before any live runtime exists.
- Let Oom Sakkie answer what each agent may inspect, what it must not do, and which owner gate blocks it.

What changed:

- Added `get_agent_operating_contracts()` in `modules/oom_sakkie/agent_runtime.py`.
- Added read-only tool `agent_operating_contracts`.
- Added deterministic routing for phrases such as:
  - `what are the agent operating contracts`,
  - `what must agents not do`,
  - `specialist rules`.
- Each contract includes:
  - focus,
  - allowed read-only tools,
  - memory sources,
  - output contract,
  - must-not-do list,
  - owner gate,
  - dry-run request eligibility.
- Beacon, Forge, and Gatekeeper stay locked out of the dry-run request cohort.

Safety status:

- Read-only planning contracts only.
- Runtime remains disabled.
- Dispatch remains disabled.
- Specialist LLM/tool execution remains disabled.
- Writes, public/customer output, Builder/Forge execution, patch application, deploy, Telegram cutover, and physical controls remain blocked.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 209 tests.

Manual check:

1. Ask Oom Sakkie: `What are the agent operating contracts?`
2. Confirm it uses `agent_operating_contracts`.
3. Confirm Ledger cannot send customer messages, Rootline cannot start pumps/valves, and Beacon cannot post publicly.
4. Confirm the answer says these are planning contracts only, not runtime authority.

### 10.9AO Oom Sakkie Agent Contracts Review Endpoint - Local Ready

Purpose:

- Make the operating contracts directly inspectable by reviewers and future UI without going through chat.
- Keep the endpoint protected and review-only.

What changed:

- Added protected `GET /api/oom-sakkie/agents/contracts`.
- The route returns `get_agent_operating_contracts()` plus a `review_guard` with all execution/runtime/write flags false.
- Added route tests for:
  - successful local contract inspection,
  - non-local access denial.
- Added frontend route contract coverage for the new endpoint.

Safety status:

- Read-only route only.
- Loopback/private-LAN review guard applies.
- Runtime remains disabled.
- Dispatch remains disabled.
- Specialist LLM/tool execution remains disabled.
- Writes, public/customer output, Builder/Forge execution, patch application, deploy, Telegram cutover, and physical controls remain blocked.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 211 tests.

Manual check:

1. Open `/api/oom-sakkie/agents/contracts` locally.
2. Confirm `mode = agent_operating_contracts_only`.
3. Confirm `review_guard.runs_specialist = false`, `dispatch_enabled = false`, and `writes = false`.
4. Confirm Beacon, Forge, and Gatekeeper are listed under `locked_out_of_dry_run`.

### 10.9AP Oom Sakkie Agent Activation Preflight - Local Ready

Purpose:

- Give Oom Sakkie one read-only preflight summary before any live agent authority exists.
- Combine readiness, contracts, activation plan, browser-smoke, and audit-rail status into one answer/endpoint.

What changed:

- Added `get_agent_activation_preflight()` in `modules/oom_sakkie/agent_runtime.py`.
- Added read-only tool `agent_activation_preflight`.
- Added protected `GET /api/oom-sakkie/agents/preflight`.
- Added deterministic routing for phrases such as:
  - `agent activation preflight`,
  - `before activating agents`,
  - `preflight runtime`.
- The preflight reports:
  - ready checks,
  - manual checks,
  - locked checks,
  - dry-run allowed cohort,
  - locked-out dry-run agents,
  - next safe action,
  - next gate.

Safety status:

- Read-only preflight only.
- Runtime remains disabled.
- Dispatch remains disabled.
- Specialist LLM/tool execution remains disabled.
- Writes, public/customer output, Builder/Forge execution, patch application, deploy, Telegram cutover, and physical controls remain blocked.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 215 tests.

Manual check:

1. Ask Oom Sakkie: `Run the agent activation preflight.`
2. Confirm it uses `agent_activation_preflight`.
3. Open `/api/oom-sakkie/agents/preflight` locally.
4. Confirm `summary_status = not_ready_for_live_dispatch`.
5. Confirm the manual checks include GitHub Actions green, owner browser pass, and Claude review.

### 10.9AQ Oom Sakkie Activation Preflight Wording Hardening - Local Ready

Purpose:

- Make preflight wording honest about configured gates versus confirmed live results.

What changed:

- `audit_rail_ci` now reports `status = configured`, not `pass`.
- `browser_behavior_smoke` now reports `status = configured`, not `pass`.
- The details explicitly say GitHub green status and owner browser pass remain manual checks.

Safety status:

- Wording/data honesty only.
- No route, tool, migration, runtime, dispatch, specialist LLM/tool, write, public output, patch, deploy, Telegram, or physical-control authority changed.

### 10.9AR Oom Sakkie Agent Authority Matrix - Local Ready

Purpose:

- Make every future agent authority area visible before any of it can be enabled.
- Let Oom Sakkie answer which powers are locked and what gates would be required later.

What changed:

- Added `get_agent_authority_matrix()` in `modules/oom_sakkie/agent_runtime.py`.
- Added read-only tool `agent_authority_matrix`.
- Added protected `GET /api/oom-sakkie/agents/authority-matrix`.
- Added deterministic routing for phrases such as:
  - `agent authority matrix`,
  - `which agent powers are locked`,
  - `what can agents control`.
- The matrix lists locked future authorities:
  - live specialist dispatch,
  - specialist LLM loop,
  - specialist tool execution,
  - farm data writes,
  - customer/public output,
  - Builder/patch execution,
  - deploy execution,
  - Telegram cutover,
  - physical controls.

Safety status:

- Read-only matrix only.
- `enabled_count = 0`.
- Runtime remains disabled.
- Dispatch remains disabled.
- Specialist LLM/tool execution remains disabled.
- Writes, public/customer output, Builder/Forge execution, patch application, deploy, Telegram cutover, and physical controls remain blocked.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 219 tests.

Manual check:

1. Ask Oom Sakkie: `Show me the agent authority matrix.`
2. Confirm it uses `agent_authority_matrix`.
3. Open `/api/oom-sakkie/agents/authority-matrix` locally.
4. Confirm `enabled_count = 0` and `locked_count = authority_count`.
5. Confirm physical controls and deploy execution are locked at risk level 5.

### 10.9AS Oom Sakkie Authority Lock Source Alignment - Local Ready

Purpose:

- Reduce future drift between activation plan, preflight, and authority matrix lock-state.

What changed:

- Authority rows now include `blocked_capability`.
- `agent_activation_plan.blocked_capabilities` is derived from the authority matrix source.
- `agent_activation_preflight.locked_checks` is derived from the same authority source.
- `agent_authority_matrix.areas` is built through the same authority-row helper.
- Added a drift test proving:
  - activation-plan blocked capabilities match the matrix,
  - preflight locked checks match the matrix,
  - risk level, lock reason, and required gates stay synchronized.

Safety status:

- Internal consistency hardening only.
- No route, tool, migration, runtime, dispatch, specialist LLM/tool, write, public output, patch, deploy, Telegram, or physical-control authority changed.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 220 tests.

### 10.9AT Oom Sakkie Authority Unlock Readiness - Local Ready

Purpose:

- Let Oom Sakkie answer which locked authority would be lowest-risk to design later without recommending any unlock now.
- Keep the owner/Claude gate explicit before any authority work.

What changed:

- Added `get_agent_authority_unlock_readiness()` in `modules/oom_sakkie/agent_runtime.py`.
- Added read-only tool `agent_authority_unlock_readiness`.
- Added protected `GET /api/oom-sakkie/agents/unlock-readiness`.
- Added deterministic routing for phrases such as:
  - `which authority should we unlock first`,
  - `authority unlock readiness`,
  - `lowest risk authority`.
- The payload reports:
  - `summary_status = planning_only_no_unlock_recommended`,
  - `enabled_count = 0`,
  - lowest-risk planning candidates,
  - high-risk hard-no authorities,
  - required gates before any unlock work.

Safety status:

- Read-only planning only.
- No unlock is recommended.
- Runtime remains disabled.
- Dispatch remains disabled.
- Specialist LLM/tool execution remains disabled.
- Writes, public/customer output, Builder/Forge execution, patch application, deploy, Telegram cutover, and physical controls remain blocked.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 224 tests.

Manual check:

1. Ask Oom Sakkie: `Which authority should we unlock first?`
2. Confirm it uses `agent_authority_unlock_readiness`.
3. Open `/api/oom-sakkie/agents/unlock-readiness` locally.
4. Confirm `summary_status = planning_only_no_unlock_recommended`.
5. Confirm physical controls are in `hard_no_authorities`.

### 10.9AU Oom Sakkie Runtime Inspection Invariant Test - Local Ready

Purpose:

- Prevent future drift where one agent inspection surface accidentally reports an authority flag as enabled.

What changed:

- Added a focused invariant test over:
  - `get_agent_runtime_status()`,
  - `get_agent_activation_plan()`,
  - `get_agent_runtime_readiness()`,
  - `get_agent_operating_contracts()`,
  - `get_agent_activation_preflight()`,
  - `get_agent_authority_matrix()`,
  - `get_agent_authority_unlock_readiness()`.
- The test asserts every authority flag present on those surfaces stays false.

Safety status:

- Test-only hardening.
- No runtime behavior, route, tool, migration, dispatch, specialist LLM/tool, write, public output, patch, deploy, Telegram, or physical-control authority changed.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 225 tests.

### 10.9AV Oom Sakkie Dispatch Decision Rail Blueprint - Local Ready

Purpose:

- Prepare the next possible low-risk live-authority design as a reviewable blueprint only, before any dispatch decision rail code exists.

What changed:

- Added `get_agent_dispatch_decision_rail_blueprint()` in `modules/oom_sakkie/agent_runtime.py`.
- Added read-only tool `agent_dispatch_decision_rail_blueprint`.
- Added deterministic routing for `dispatch rail blueprint`, `dispatch approval rail`, and similar phrases.
- Added protected `GET /api/oom-sakkie/agents/dispatch-rail-blueprint`.
- The blueprint names proposed future tables, endpoint shapes, required tests, non-goals, and the owner/Claude gate required before implementation.
- Runtime inspection invariant coverage now includes the dispatch rail blueprint.

Safety status:

- Blueprint-only.
- No dispatch rail migration, store, event endpoint, runtime flag, specialist dispatch, specialist LLM/tool call, farm write, public output, patch, deploy, Telegram cutover, or physical-control authority exists.
- The blueprint returns all runtime/dispatch/write/public/control flags false and `summary_status = blueprint_only_no_dispatch`.
- The protected route returns a false-all review guard.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 229 tests.

Manual check:

1. Ask Oom Sakkie: `Show me the dispatch rail blueprint.`
2. Confirm it uses `agent_dispatch_decision_rail_blueprint`.
3. Open `/api/oom-sakkie/agents/dispatch-rail-blueprint` locally.
4. Confirm `summary_status = blueprint_only_no_dispatch`.
5. Confirm `dispatch_enabled`, `specialist_llm_enabled`, `specialist_tools_enabled`, and `writes_enabled` are all false.

### 10.9AW Oom Sakkie Agent Runtime Review Packet - Local Ready

Purpose:

- Create one protected, read-only packet that bundles the current agent runtime inspection surfaces for a cheaper bulk Claude review.

What changed:

- Added `get_agent_runtime_review_packet()` in `modules/oom_sakkie/agent_runtime.py`.
- Added read-only tool `agent_runtime_review_packet`.
- Added deterministic routing for `runtime review packet`, `bulk Claude review`, and similar phrases.
- Added protected `GET /api/oom-sakkie/agents/runtime-review-packet`.
- The packet bundles runtime status, readiness, operating contracts, activation preflight, authority matrix, unlock readiness, and the dispatch rail blueprint.
- The packet includes `claude_prompt = Read docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md and run the current review.`

Safety status:

- Review-packet only.
- No runtime flag, specialist dispatch, specialist LLM/tool call, farm write, public output, patch, deploy, Telegram cutover, or physical-control authority exists.
- The packet returns all runtime/dispatch/write/public/control flags false and `summary_status = ready_for_bulk_claude_review_not_live_dispatch`.
- The protected route returns a false-all review guard.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 233 tests.

Manual check:

1. Ask Oom Sakkie: `Show me the agent runtime review packet.`
2. Confirm it uses `agent_runtime_review_packet`.
3. Open `/api/oom-sakkie/agents/runtime-review-packet` locally.
4. Confirm it contains `payloads.dispatch_blueprint.summary_status = blueprint_only_no_dispatch`.
5. Confirm `dispatch_enabled`, `specialist_llm_enabled`, `specialist_tools_enabled`, and `writes_enabled` are all false.

### 10.9AX Oom Sakkie Playwright Browser Behavior Gate - Local Ready / CI Ready

Purpose:

- Add the real-browser behavior gate Claude requested before any future dispatch-rail implementation work.

What changed:

- Added `package.json` with `test:oom-sakkie:browser`.
- Added `playwright.config.js`.
- Added `tests/oom_sakkie_playwright_behavior.spec.js`.
- Added `.github/workflows/oom-sakkie-browser-behavior.yml`.
- The Playwright spec opens the real `/oom-sakkie` page, stubs all `/api/oom-sakkie/**` calls with read-only JSON, checks startup has no hidden POSTs and no interval polling, and checks dry-run/result/message POSTs happen only after explicit owner clicks.
- Frontend contract tests now pin the workflow, package script, config, and safety phrases.

Safety status:

- Test/CI only.
- No route, tool, store, migration, runtime flag, specialist dispatch, specialist LLM/tool call, farm write, public output, patch, deploy, Telegram cutover, or physical-control authority changed.
- The Playwright spec stubs API calls and does not touch farm data.
- Local normal tests do not require Playwright to be installed.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 233 tests.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.
- The actual Playwright browser run is expected in GitHub Actions or a local environment after `npm install` and browser install.

Manual/CI check:

1. Confirm `.github/workflows/oom-sakkie-browser-behavior.yml` runs green after push.
2. Optional local run after dependency install: `npm run test:oom-sakkie:browser`.
3. Confirm no hidden startup POSTs, no interval polling, and only owner-clicked dry-run/result/message POSTs.

### 10.9AY Oom Sakkie Dispatch Decision Rail - Local Ready / Migration Pending

Purpose:

- Turn the dispatch-rail blueprint into a first append-only review rail while still keeping live dispatch completely disabled.

What changed:

- Added migration `supabase/migrations/202606090001_create_oom_sakkie_dispatch_decisions.sql`.
- Added `modules/oom_sakkie/dispatch_decision_store.py`.
- Added protected routes:
  - `GET /api/oom-sakkie/dispatch-requests`,
  - `POST /api/oom-sakkie/dispatch-requests`,
  - `POST /api/oom-sakkie/dispatch-requests/<dispatch_request_id>/decisions`.
- Added the migration to `.github/workflows/oom-sakkie-audit-rails.yml`.
- Added tests for:
  - forced false execution/runtime flags,
  - locked-out specialist rejection before DB access,
  - invalid decision types before DB access,
  - migration CHECK/trigger text,
  - protected route success shapes,
  - non-local route denial,
  - live-PG append-only/constraint coverage when the migration exists.

Safety status:

- Append-only audit/review rail only.
- No specialist dispatch happens.
- No specialist LLM or specialist tool execution happens.
- No farm data write, public/customer output, patch, deploy, Telegram cutover, or physical control is created.
- Application code forces `dispatch_enabled`, `runs_specialist_llm`, `runs_specialist_tools`, `writes`, and `applies_runtime_change` false.
- DB constraints also force those flags false and triggers block update/delete.
- Migration was not applied to the local/live database in this turn; CI applies it to disposable Postgres.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 242 tests.

Manual/CI check:

1. Confirm GitHub audit-rail workflow applies `202606090001_create_oom_sakkie_dispatch_decisions.sql` and runs green.
2. Only after review, apply the migration to the intended database with the approved migration script.
3. Confirm `/api/oom-sakkie/dispatch-requests` is loopback/review-gated and returns no-execution flags false.

### 10.9AZ Oom Sakkie Dispatch Decision Status Visibility - Local Ready

Purpose:

- Let Oom Sakkie explain the new dispatch design-review rail without creating any runtime consumer of those decisions.
- Keep the owner-facing `what needs my approval?` answer aligned with the full build/patch/deploy/dispatch-design queue.

What changed:

- Added read-only `dispatch_decision_status`.
- Added deterministic routing for:
  - `dispatch decision status`,
  - `dispatch request status`,
  - `dispatch design review`,
  - `which dispatch requests are waiting for review`.
- `system_work_status` now reads `list_dispatch_requests(limit=5)` as a fourth read-only queue and includes:
  - total dispatch requests loaded,
  - pending dispatch design requests,
  - dispatch store status and outage warnings.
- The LLM answer-composer instruction for `system_work_status` now mentions build/patch/deploy/dispatch-design counts.
- Tests now cover:
  - registry contract includes `dispatch_decision_status`,
  - read-only handler output and false runtime flags,
  - system-work dispatch counts,
  - deterministic routing for dispatch-status wording.

Safety status:

- Status/query-only.
- No new route, migration, event type, runtime flag, or JS action.
- No code consumes `approved_for_design_review` to enable dispatch.
- No specialist dispatch happens.
- No specialist LLM or specialist tool execution happens.
- No farm data write, public/customer output, patch, deploy, Telegram cutover, or physical control is created.
- Dispatch queue failures surface as stale warnings rather than confident "nothing waiting" answers.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 243 tests.
- `node --check static/js/oomSakkie.js` passed.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.
- Browser behavior smoke passed.
- Full local unittest suite passed at 573 tests.

Manual/CI check:

1. Ask `what is the dispatch decision status` in the kiosk.
2. Confirm the answer uses `dispatch_decision_status`.
3. Confirm the answer says no specialist dispatch is enabled.
4. Confirm `what needs my approval?` includes dispatch design review counts when dispatch requests exist.

### 10.9BA Oom Sakkie Dispatch Runtime Review Packet - Local Ready

Purpose:

- Give the owner and Claude one chat-accessible review packet before any future phase designs code that consumes dispatch decisions.
- Keep the packet review-only and separate from the protected pure runtime-review endpoint.

What changed:

- Added read-only `dispatch_runtime_review_packet`.
- The tool combines:
  - pure `get_agent_runtime_review_packet()` output,
  - read-only `dispatch_decision_status_handler({})` output.
- Added deterministic routing for:
  - `dispatch runtime review packet`,
  - `dispatch review packet`,
  - `dispatch execution review`,
  - `claude dispatch review`.
- The packet `next_gate` is `owner_and_claude_review_before_any_code_consumes_dispatch_decisions`.
- Tests assert the tool:
  - is in the read-only registry,
  - keeps dispatch/specialist LLM/specialist tool/write/runtime-change flags false,
  - says it does not enable dispatch,
  - routes correctly from dispatch-review wording.

Safety status:

- Review assembly only.
- No new route, store, migration, event type, runtime flag, JS action, or DB write.
- No code consumes `approved_for_design_review` to enable dispatch.
- No specialist dispatch happens.
- No specialist LLM or specialist tool execution happens.
- No farm data write, public/customer output, patch, deploy, Telegram cutover, or physical control is created.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 244 tests.
- `node --check static/js/oomSakkie.js` passed.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.
- Browser behavior smoke passed.
- Full local unittest suite passed at 574 tests.

Manual check:

1. Ask `prepare the dispatch runtime review packet`.
2. Confirm it uses `dispatch_runtime_review_packet`.
3. Confirm the answer names owner/Claude review as the next gate.
4. Confirm it says dispatch remains disabled.

### 10.9BB Oom Sakkie Jarvis Product Progress - Local Ready

Purpose:

- Give the owner a simple product-progress answer with bars/percentages while keeping the build honest about what is still locked.
- Make Oom Sakkie able to answer `how far are we from Jarvis?` without implying runtime authority.

What changed:

- Added pure `get_jarvis_product_progress()` in `modules/oom_sakkie/agent_runtime.py`.
- Added read-only `jarvis_product_progress`.
- Added deterministic routing for:
  - `jarvis progress`,
  - `oom sakkie progress`,
  - `product progress`,
  - `how far are we from Jarvis`,
  - `progress bar`,
  - `jarvis roadmap status`.
- Progress areas now report:
  - Foundation / safety rails,
  - Local kiosk + voice basics,
  - Read-only farm intelligence,
  - Agent roster + contracts,
  - Agent dry-run / learning rails,
  - Builder / patch / deploy gates,
  - Live specialist execution,
  - Business advisor automation,
  - Customer/public selling tools,
  - True alive Jarvis UI/feel.
- The payload includes `overall_percent`, `overall_bar`, `next_milestone`, and `blocked_until`.
- Tests assert:
  - all authority flags stay false,
  - the progress surface participates in the runtime flag invariant test,
  - live specialist execution remains low/locked,
  - routing hits `jarvis_product_progress`.

Safety status:

- Planning visibility only.
- No new route, store, migration, event type, DB write, runtime flag, JS action, specialist dispatch, specialist LLM/tool execution, farm write, public/customer output, patch, deploy, Telegram cutover, or physical control.
- Percentages are explicit planning status, not unlock criteria.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 246 tests.
- `node --check static/js/oomSakkie.js` passed.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.
- Browser behavior smoke passed.
- Full local unittest suite passed at 576 tests.

Manual check:

1. Ask `show me the Jarvis progress bar`.
2. Confirm it uses `jarvis_product_progress`.
3. Confirm it gives an overall percentage and next milestone.
4. Confirm it says live specialist execution/customer-public selling remain locked.

### 10.9BC Oom Sakkie Agent Command Center - Local Ready

Purpose:

- Give the owner one read-only control-tower answer for the Jarvis team: who would be working, what lanes exist, what queues feed the view, and what remains locked.
- Make Oom Sakkie able to answer `show me the agent command center` without implying that agents are running.

What changed:

- Added pure `get_agent_command_center()` in `modules/oom_sakkie/agent_runtime.py`.
- Added read-only `agent_command_center`.
- Added deterministic routing for:
  - `agent command center`,
  - `jarvis command center`,
  - `oom sakkie command center`,
  - `who is working`,
  - `what are the agents doing`,
  - `team workspace`,
  - `control tower`.
- The command center reports:
  - control-tower lane,
  - safety-review lane,
  - business-growth lane,
  - farm-operations lane,
  - interface lane,
  - builder-gates lane.
- Each lane carries `runs_agent = false`, `dispatch_enabled = false`, `runs_specialist_llm = false`, `runs_specialist_tools = false`, `writes = false`, and `applies_runtime_change = false`.
- The tool includes read-only queue snapshots from:
  - `system_work_status`,
  - `agent_dry_run_status`,
  - `dispatch_decision_status`.
- Tests assert:
  - all authority flags stay false,
  - every lane is non-executing,
  - the command-center surface participates in the runtime flag invariant test,
  - routing hits `agent_command_center`.

Safety status:

- Read-only visibility only.
- No new route, store, migration, event type, DB write, runtime flag, JS action, specialist dispatch, specialist LLM/tool execution, farm write, public/customer output, patch, deploy, Telegram cutover, or physical control.
- Queue snapshots are status-only and cannot consume dispatch decisions or approval records to change behavior.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 248 tests.
- `node --check static/js/oomSakkie.js` passed.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.
- Browser behavior smoke passed.
- Full local unittest suite passed at 578 tests.

Manual check:

1. Ask `show me the agent command center`.
2. Confirm it uses `agent_command_center`.
3. Confirm it says live authority remains locked.
4. Confirm it names the next gate as owner/Claude review before any live runtime authority.

Future research parking lot:

- Financial Agent / capital-allocation assistant idea is parked for later only.
- Hard lock for now: no trading, no broker/exchange/account access, no custody, no funds movement, no payment movement, no model-driven orders, no profit-share automation, and no investment advice or recommendations.
- Any future finance agent must start as read-only research/accounting analysis only, and only after separate owner + Claude review, legal/regulatory/tax/risk review, a dedicated authority matrix entry, append-only decision rails, paper-trading/simulation gates if ever approved, and explicit proof that no live funds can move.

### 10.9BD Oom Sakkie Command Center Quick Action - Local Ready

Purpose:

- Make the read-only command center easier to reach from the kiosk without adding another heavy workbench panel.
- Make the existing agent stage show Gatekeeper/control-tower context when command-center answers are returned.

What changed:

- Added a `Command Center` quick-check button with `data-quick-ask="Show me the agent command center."`.
- Mapped `agent_command_center` to Gatekeeper in the visual agent activity stage.
- Added tests that assert:
  - the quick action exists in the template,
  - command-center activity opens the Gatekeeper workspace,
  - no runtime/dispatch/write flags are enabled.

Safety status:

- UI reachability and visual routing only.
- No new route, store, migration, event type, DB write, background polling, hidden POST, runtime flag, specialist dispatch, specialist LLM/tool execution, farm write, public/customer output, patch, deploy, Telegram cutover, or physical control.

Verification:

- Focused Oom Sakkie service/routes/frontend tests passed at 249 tests.
- `node --check static/js/oomSakkie.js` passed.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.
- Browser behavior smoke passed.
- Full local unittest suite passed at 579 tests.

Manual check:

1. Open `/oom-sakkie`.
2. Click `Command Center`.
3. Confirm the answer uses `agent_command_center`.
4. Confirm the visible agent workspace shows Gatekeeper / control-tower style context and still says dispatch/writes are off.

### 10.9BF Oom Sakkie Playwright CI Startup Hardening - Local Ready

Purpose:

- Address the GitHub Actions browser-behavior failure email by making the Playwright workflow closer to the local development runtime and less dependent on Flask debug-mode behavior.

What changed:

- Browser workflow now uses Python `3.12`, matching the local development venv major/minor version instead of `3.13`.
- Browser workflow now starts Flask through `python -m flask --app app run --host 127.0.0.1 --port 5000`.
- Browser workflow sets `FLASK_ENV = production` and `FLASK_DEBUG = 0`.
- Frontend contract tests assert the workflow does not drift back to `python app.py`.

Safety status:

- CI/test hardening only.
- No app route, store, migration, DB write, runtime flag, specialist dispatch, specialist LLM/tool execution, farm write, public/customer output, patch, deploy, Telegram cutover, or physical control.
- The workflow still runs only against loopback and the Playwright spec still stubs `/api/oom-sakkie/**` with read-only JSON.

Verification:

- Frontend route contracts passed at 27 tests.
- Focused Oom Sakkie service/routes/frontend tests passed at 249 tests.
- `node --check static/js/oomSakkie.js` passed.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.
- Browser behavior smoke passed.

Manual check:

1. Push the branch.
2. Confirm the `Oom Sakkie Browser Behavior` GitHub Actions workflow turns green.
3. If it fails again, inspect the failed step log before changing app code.

### 10.9BG Oom Sakkie Daily Command Brief - Local Ready

Purpose:

- Make the existing `Brief` quick action feel more like a Jarvis-style controller briefing instead of a farm-only status readback.
- Compose the three current read-only owner views into one answer: farm operating brief, business growth brief, and Agent Command Center.
- Keep the answer useful while preserving the current safety line: no live agents, no writes, no public output, and no decision consumption.

What changed:

- Added read-only `jarvis_daily_command_brief`.
- Added deterministic routing for `daily command brief`, `start my day`, `run the command brief`, and related phrases.
- Updated the `Brief` quick action to ask `Give me the daily command brief.`
- Mapped the tool to Gatekeeper in the visible agent activity stage.
- Extracted read-only next actions from existing section context: pending approval/design counts, the Business Advisor owner question, and unavailable sections.
- Updated the LLM answer composer instructions so env-gated composed answers treat this as a multi-section owner command brief across farm, business, and command-center context.
- Added tests for registry coverage, routing, Gatekeeper visual mapping, full read-only composition, partial-section warning behavior, frontend quick-action contract, and composer prompt wording.

Safety status:

- Read-only composition only.
- No new route, store, migration, event type, DB write, runtime flag, specialist dispatch, specialist LLM/tool execution, farm write, customer/public output, patch, deploy, Telegram cutover, or physical control.
- The tool calls existing read-only handlers and reports `partial` plus stale warnings if a section is unavailable.
- All command-brief `llm_context` execution flags remain false.

Verification:

- `python -m unittest tests.test_oom_sakkie_service` -> 149 tests OK, 3 skipped live-DB gates.
- `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 252 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- Browser behavior smoke passed.

Manual check:

1. Open `/oom-sakkie`.
2. Click `Brief`.
3. Confirm the answer uses `jarvis_daily_command_brief`.
4. Confirm the visible agent workspace shows Gatekeeper.
5. Confirm the answer covers farm, business, and command-center context without saying anything was dispatched, written, posted, deployed, or controlled.

### 10.9BH Oom Sakkie Playwright CI Node 24 And Server URL Hardening - Local Ready

Purpose:

- Respond to the GitHub Actions email that still reported the Playwright real-browser behavior gate failing.
- Remove the GitHub hosted-actions Node 20 deprecation warning.
- Make the Playwright web server readiness check target the actual `/oom-sakkie` page instead of relying on the base URL.

What changed:

- Browser behavior workflow now sets `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 = true`.
- Browser behavior workflow now uses `node-version: "24"`.
- Browser behavior workflow now sets `OOM_SAKKIE_PLAYWRIGHT_SERVER_URL = http://127.0.0.1:5000/oom-sakkie`.
- `playwright.config.js` now separates:
  - `baseURL` for page/test navigation, and
  - `serverURL` for webServer readiness.
- Frontend contract tests assert the workflow/config do not drift back to Node 20 or the wrong readiness URL.

Safety status:

- CI/test hardening only.
- No app route, store, migration, DB write, runtime flag, specialist dispatch, specialist LLM/tool execution, farm write, public/customer output, patch, deploy, Telegram cutover, or physical control.
- Playwright still targets loopback and the spec still stubs all `/api/oom-sakkie/**` calls with read-only JSON.

Verification:

- `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
- `node --check playwright.config.js` passed.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.

Manual check:

1. Push the branch.
2. Confirm the `Oom Sakkie Browser Behavior` GitHub Actions workflow turns green.
3. If it still fails, copy the failing step log, not only the annotation summary.

### 10.9BI Oom Sakkie Playwright Workbench Visibility Fix - Local Ready

Purpose:

- Address the likely real-browser failure hidden behind the GitHub email summary.
- The dry-run controls are inside the collapsed `System Workbench` `<details>` element, so Chromium must open that section before it can click the owner-action controls.
- Keep the real-browser gate strict about owner-click-only POSTs while making it match the actual UI.

What changed:

- `tests/oom_sakkie_playwright_behavior.spec.js` now opens `.oom-system-workbench` before the dry-run/result owner-click sequence.
- The spec asserts `#oom_request_sentinel_dry_run` is visible before clicking it.
- Frontend contract tests pin this behavior so the real-browser smoke does not drift back to hidden-control clicks.

Safety status:

- Test-only hardening.
- No app route, store, migration, DB write, runtime flag, specialist dispatch, specialist LLM/tool execution, farm write, public/customer output, patch, deploy, Telegram cutover, or physical control.
- The Playwright spec still stubs all `/api/oom-sakkie/**` calls with read-only JSON and only verifies explicit owner-click POST behavior.

Verification:

- `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.

Manual check:

1. Push the branch.
2. Confirm the `Oom Sakkie Browser Behavior` GitHub Actions workflow turns green.
3. If it still fails, expand the failed `Run Oom Sakkie Playwright behavior gate` step and copy the first Playwright error block.

### 10.9BJ Oom Sakkie Audit Rail CI Node 24 Warning Cleanup - Local Ready

Purpose:

- Clean up the remaining GitHub Actions warning on the disposable-Postgres audit-rail workflow.
- The workflow was already green; this is warning cleanup only.

What changed:

- Added `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 = true` to `.github/workflows/oom-sakkie-audit-rails.yml`.
- Frontend contract tests now assert the audit workflow keeps that opt-in.

Safety status:

- CI/test hardening only.
- No app route, store, migration, DB write, runtime flag, specialist dispatch, specialist LLM/tool execution, farm write, public/customer output, patch, deploy, Telegram cutover, or physical control.
- The workflow still uses disposable Postgres with throwaway credentials and applies only Oom Sakkie audit migrations.

Verification:

- `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.

Manual check:

1. Push the branch.
2. Confirm `Oom Sakkie Audit Rails` remains green.
3. Confirm the Node 20 actions warning no longer appears for that workflow.

### 10.9BK Oom Sakkie Safety Gate Board - Local Ready

Purpose:

- Give the owner one read-only answer for "are the gates green?", "what is the CI status?", and "show me the safety gates".
- Keep the runtime honest: Oom Sakkie can report configured/locked/manual safety gates, but it does not call GitHub or trust CI automatically.

What changed:

- Added `get_jarvis_safety_gate_board()` in `modules/oom_sakkie/agent_runtime.py`.
- Added the read-only `jarvis_safety_gate_board` tool.
- Added deterministic routing for safety-gate / CI-status / GitHub Actions status wording.
- Mapped the tool to Sentinel in the visible agent activity stage.
- Added the safety-gate board as a Command Center panel, queue source, and queue snapshot.
- Added tests for:
  - read-only board payload and false execution flags
  - read-only tool handler
  - routing phrases
  - Sentinel visual mapping
  - Command Center inclusion
  - inspection-surface authority flags

Safety envelope:

- No GitHub API call.
- No network call.
- No route.
- No store or migration.
- No DB write.
- No runtime flag change.
- No specialist dispatch.
- No specialist LLM/tool execution.
- No farm-data write.
- No public/customer output.
- No patch/deploy/Telegram/physical-control action.
- GitHub green status remains owner-confirmed outside the runtime; Oom Sakkie reports that limitation as a stale warning.

Verification:

- `python -m unittest tests.test_oom_sakkie_service` -> 152 tests OK, 3 expected live-DB skips.
- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 255 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.

Manual check:

1. Ask `are the gates green?`.
2. Confirm it uses `jarvis_safety_gate_board`.
3. Confirm it says Oom Sakkie does not call GitHub.
4. Confirm it says live authority remains locked and no specialist/write/public/deploy/control action occurred.

### 10.9BL Oom Sakkie Owner Review Packet - Local Ready

Purpose:

- Give the owner one read-only packet for "prepare Claude review", "handoff to Claude", and "show me the owner review packet".
- Reduce Claude spend by batching the current review context into one local Oom Sakkie answer before the owner decides to ask Claude.

What changed:

- Added `get_jarvis_owner_review_packet()` in `modules/oom_sakkie/agent_runtime.py`.
- Added the read-only `jarvis_owner_review_packet` tool.
- Added deterministic routing for owner-review / Claude-handoff wording.
- Mapped the tool visually to Gatekeeper.
- Added answer-composer guidance for the packet when the env-gated composer is enabled.
- The packet composes existing locked/read-only surfaces:
  - `jarvis_product_progress`
  - `agent_command_center`
  - `jarvis_safety_gate_board`
  - `agent_runtime_review_packet`
- Added tests for:
  - read-only packet payload and false execution flags
  - read-only tool handler
  - routing phrases
  - Gatekeeper visual mapping
  - inspection-surface authority flags
  - composer prompt wording

Safety envelope:

- No Claude API call.
- No GitHub API call.
- No network call.
- No route.
- No store or migration.
- No DB write.
- No runtime flag change.
- No specialist dispatch.
- No specialist LLM/tool execution.
- No farm-data write.
- No public/customer output.
- No patch/deploy/Telegram/physical-control action.
- The packet explicitly says it is not approval to unlock runtime authority.

Verification:

- `python -m unittest tests.test_oom_sakkie_service` -> 155 tests OK, 3 expected live-DB skips.
- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 258 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- `python -m unittest` -> 588 tests OK.
- `python -m unittest` -> 588 tests OK.
- `python -m unittest` -> 588 tests OK.

Manual check:

1. Ask `prepare Claude review`.
2. Confirm it uses `jarvis_owner_review_packet`.
3. Confirm it names `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md`.
4. Confirm it says the packet does not call Claude/GitHub and does not approve runtime authority.

### 10.9BM Oom Sakkie Review Shortcuts - Local Ready

Purpose:

- Make the new read-only review surfaces visible in the kiosk without requiring the owner to remember exact phrases.
- Keep the interaction explicit-click only through the existing quick-ask mechanism.

What changed:

- Added `Safety Gates` quick action with `data-quick-ask="Show me the safety gates."`.
- Added `Review Packet` quick action with `data-quick-ask="Prepare Claude review."`.
- Added frontend route contract assertions for both buttons and prompt strings.

Safety envelope:

- UI-only.
- Uses existing owner-clicked quick-ask POST path.
- No background polling.
- No hidden POST.
- No route.
- No store or migration.
- No DB write.
- No runtime flag change.
- No specialist dispatch.
- No specialist LLM/tool execution.
- No farm-data write.
- No public/customer output.
- No patch/deploy/Telegram/physical-control action.

Verification:

- `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 258 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.

Manual check:

1. Open `/oom-sakkie`.
2. Click `Safety Gates`; confirm it asks `Show me the safety gates.` and routes to `jarvis_safety_gate_board`.
3. Click `Review Packet`; confirm it asks `Prepare Claude review.` and routes to `jarvis_owner_review_packet`.
4. Confirm no action happens without clicking.

### 10.9BN Oom Sakkie Quick Checks Grouping - Local Ready

Purpose:

- Reduce visual clutter in the growing quick-check row without changing any quick-check behavior.
- Make the kiosk easier to scan by grouping existing owner-clicked checks into Farm, Business, and Agent Review clusters.

What changed:

- Grouped existing quick-action buttons in `templates/oom-sakkie.html`:
  - `Farm`
  - `Business`
  - `Agent Review`
- Added `.oom-quick-group` and `.oom-quick-group-label` CSS.
- Desktop layout uses three quick-check columns; smaller screens collapse to one column.
- Added frontend route contract assertions for the grouping and CSS.

Safety envelope:

- UI-only.
- No JavaScript behavior change.
- Same `data-quick-ask` prompts as before.
- Same explicit owner-click quick-ask POST path.
- No background polling.
- No hidden POST.
- No route.
- No store or migration.
- No DB write.
- No runtime flag change.
- No specialist dispatch.
- No specialist LLM/tool execution.
- No farm-data write.
- No public/customer output.
- No patch/deploy/Telegram/physical-control action.

Verification:

- `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 258 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.

Manual check:

1. Open `/oom-sakkie`.
2. Confirm quick checks are grouped into `Farm`, `Business`, and `Agent Review`.
3. Click one button in each group and confirm it still sends the same read-only quick ask.
4. Confirm no action happens without clicking.

### 10.9BO Oom Sakkie CI Green Evidence - Local Ready

Purpose:

- Close the carried-forward operational check that the two Oom Sakkie GitHub Actions gates are actually green on the branch.
- Give the Safety Gate Board concrete owner-verified evidence rather than only "configured" status.

What changed:

- Installed portable GitHub CLI under `.tools/gh/bin/gh.exe`.
- Added `/.tools/` to `.gitignore` so the downloaded CLI binary is not committed.
- Authenticated GitHub CLI as owner account `Crewless9086`.
- Verified active workflows:
  - `Oom Sakkie Audit Rails`
  - `Oom Sakkie Browser Behavior`
- Verified latest runs on `main`:
  - `Oom Sakkie Browser Behavior` run `27225474174` completed with `conclusion = success`, updated `2026-06-09T17:58:15Z`.
  - `Oom Sakkie Audit Rails` run `27225474133` completed with `conclusion = success`, updated `2026-06-09T17:58:02Z`.
- Verified successful jobs:
  - `Playwright real-browser behavior gate`
  - `Unit tests with disposable Postgres audit rails`

Safety envelope:

- Operational verification only.
- No app code change.
- No Oom Sakkie route/tool/store/migration change.
- No DB write.
- No runtime flag change.
- No specialist dispatch.
- No specialist LLM/tool execution.
- No farm-data write.
- No public/customer output.
- No patch/deploy/Telegram/physical-control action.
- GitHub Actions status is still external evidence; Oom Sakkie runtime itself still does not call GitHub.

Verification:

- `.\.tools\gh\bin\gh.exe auth status` confirmed login to `github.com` as `Crewless9086`.
- `.\.tools\gh\bin\gh.exe workflow list` showed both Oom Sakkie workflows active.
- `.\.tools\gh\bin\gh.exe run list --limit 12` showed the latest `Oom Sakkie Audit Rails` and `Oom Sakkie Browser Behavior` runs completed successfully.
- `.\.tools\gh\bin\gh.exe run view 27225474174 --json name,status,conclusion,createdAt,updatedAt,headBranch,event,jobs` confirmed the browser behavior job succeeded.
- `.\.tools\gh\bin\gh.exe run view 27225474133 --json name,status,conclusion,createdAt,updatedAt,headBranch,event,jobs` confirmed the audit-rail job succeeded.

Manual check:

1. Open GitHub Actions in the browser.
2. Confirm the same two latest runs are green.
3. Keep `.tools/` untracked.

### 10.9BP Oom Sakkie Dispatch Execution Approval Rail - Local Ready

Purpose:

- Implement the first dedicated gate Claude approved designing: a Sentinel-only single-shot advisory dry-run execution approval rail.
- Keep this phase as an approval/audit rail only. It does not run Sentinel, call an LLM, execute tools, or consume the approval to change runtime behavior.

What changed:

- Added migration `supabase/migrations/202606090002_create_oom_sakkie_dispatch_execution_approvals.sql`.
- Added `modules/oom_sakkie/dispatch_execution_approval_store.py`.
- Added protected review-gated routes:
  - `POST /api/oom-sakkie/dispatch-requests/<dispatch_request_id>/execution-approvals`
  - `GET /api/oom-sakkie/dispatch-execution-approvals`
  - `POST /api/oom-sakkie/dispatch-execution-approvals/<approval_id>/events`
- Wired the new migration into `.github/workflows/oom-sakkie-audit-rails.yml`.
- Extended the live-PG audit smoke to include the new approval and approval-event tables when migrated.

Safety envelope:

- Approval rail only.
- Requires the parent dispatch request to be `sentinel`.
- `approved_for_single_dry_run_execution` requires the existing dispatch decision rail's latest decision to be `approved_for_design_review`.
- DB CHECK constraints force:
  - `executes_now = false`
  - `dispatch_enabled = false`
  - `runs_specialist_llm = false`
  - `runs_specialist_tools = false`
  - `writes = false`
  - `applies_runtime_change = false`
  - `dispatches_further = false`
- Application responses force the same flags false.
- UPDATE/DELETE triggers make both approval tables append-only.
- No runner or consumer was added.
- No specialist LLM call was added.
- No specialist tool execution was added.
- No farm-data write, public/customer output, deploy, Telegram cutover, physical-control path, or Financial-Agent path was added.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 267 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- `python -m unittest` -> 597 tests OK.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.

Manual check:

1. Push to GitHub.
2. Confirm `Oom Sakkie Audit Rails` applies `202606090002_create_oom_sakkie_dispatch_execution_approvals.sql` and runs green.
3. Ask Claude to verify this is still an approval rail only and not an execution consumer.

Next gate:

- The Sentinel LLM runner was built separately in 10.9BQ.
- Keep `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED` off until Claude reviews 10.9BQ and the owner explicitly decides to run a local smoke.

### 10.9BQ Oom Sakkie Sentinel Single-Shot Advisory Runner - Local Ready

Purpose:

- Implement the first tightly bounded specialist LLM execution path Claude approved: Sentinel-only, single-shot, advisory-only, default-off, and owner/audit gated.
- Keep specialist tool execution, farm writes, public/customer output, Telegram, physical controls, deploys, autonomous loops, and further dispatch locked.

What changed:

- Added `modules/oom_sakkie/sentinel_single_shot_runner.py`.
- Added protected review-gated route:
  - `POST /api/oom-sakkie/dispatch-execution-approvals/<approval_id>/run-sentinel-dry-run`
- Added `specialist_dry_run_policy()` to expose:
  - `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED`
  - outbound endpoint
  - capped read-only context disclosure
  - Sentinel-only single-shot advisory mode
  - no tools / no writes / no further dispatch
- Added Safety Gate Board visibility for the Sentinel single-shot env gate.
- Added `record_sentinel_single_shot_result()` to the existing dry-run result store.
- Added migration `202606090003_allow_single_shot_sentinel_dry_run_results.sql`:
  - preserves old `dry_run_result_review_only` no-execution rows,
  - adds narrow `single_shot_sentinel_advisory_result` mode,
  - allows `runs_specialist = true` and `runs_specialist_llm = true` only for Sentinel's single-shot advisory result,
  - still forces `dispatch_enabled = false`, `runs_specialist_tools = false`, `writes = false`, and `applies_runtime_change = false`.
- Wired the migration into audit-rail CI.

Execution gates:

The runner refuses unless all are true:

1. `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED` is explicitly on.
2. OpenAI-compatible model and API key are configured.
3. The approval exists.
4. The approval is `approved_for_single_dry_run_execution`.
5. The approval specialist is `sentinel`.
6. The parent dispatch request still has latest decision `approved_for_design_review`.
7. The approval has no prior `consumed_by_single_dry_run_result` event.
8. `one_shot_scope.dry_run_request_id` is present.
9. The referenced dry-run request exists and is Sentinel.

One-shot behavior:

- The runner writes `consumed_by_single_dry_run_result` before the outbound LLM call.
- The approval event table has a unique partial index so one approval can only have one consumed event.
- The consumed event is runner-only; the generic approval-event route rejects manual `consumed_by_single_dry_run_result` writes.
- A consumed approval refuses replay.
- If the outbound LLM call fails after consumption, the approval remains consumed. This favors no replay/cost control over automatic retry.

Safety envelope:

- Sends only capped read-only context.
- Calls the configured OpenAI-compatible endpoint once.
- Does not call specialist tools.
- Does not call Oom Sakkie tools.
- Does not write farm data.
- Does not create public/customer output.
- Does not deploy, patch, cut over Telegram, or control hardware.
- Does not dispatch another agent.
- Rejects unsafe action-claiming output through `_looks_unsafe`.
- Writes result text/findings only to the append-only dry-run result rail.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 278 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- `python -m unittest` -> 608 tests OK.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.

Manual check:

1. Keep `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED` off until Claude reviews the implementation diff.
2. Push to GitHub and confirm audit-rail CI applies migrations `202606090002` and `202606090003`.
3. Ask Claude to review the runner before turning the env flag on.

Claude review focus:

- Confirm the runner is Sentinel-only, one-shot, env-gated, approval-gated, and no-tool/no-write.
- Confirm recording the consumed event before the LLM call is the right idempotency tradeoff.
- Confirm the new result constraint honestly records `runs_specialist_llm = true` only in the narrow Sentinel mode.
- Confirm no route/UI path can run the specialist without explicit local owner POST plus env flag.

### 10.9BR Oom Sakkie Sentinel Runner Review Hardening - Local Ready

Purpose:

- Close Claude's post-10.9BQ nits before any live smoke.
- Make the authority matrix honest that the specialist LLM authority is no longer purely `locked`, while still not generally enabled.
- Prove the default-off Sentinel runner path makes zero outbound HTTP calls.

What changed:

- `specialist_llm_loop` in the authority matrix now reports:
  - `enabled = false`
  - `current_state = single_shot_advisory_only`
  - one-shot Sentinel-only wording in `why_locked`
  - required gates tied to per-request execution approval, consumed-event idempotency, cost/privacy display, and Claude/Codex review before widening.
- `locked_count` now counts only authorities whose `current_state` is `locked`.
- Route/service tests now assert:
  - `specialist_llm_loop` is not enabled,
  - `specialist_llm_loop` is `single_shot_advisory_only`,
  - all other authority areas remain locked,
  - top-level `specialist_llm_enabled` remains false.
- The default-off Sentinel runner test now mocks `urllib_request.urlopen` and asserts it is not called when `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED` is off.

Safety envelope:

- No new route.
- No new UI button.
- No new store/migration.
- No specialist tool execution.
- No farm-data write.
- No public/customer output.
- No deploy, Telegram cutover, or physical-control path.
- No widening beyond Sentinel single-shot advisory mode.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 278 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- `python -m unittest` -> 608 tests OK.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.

Next gate:

1. Commit and push 10.9BP-BR.
2. Confirm audit-rail and browser-behavior GitHub Actions are green for the pushed commit.
3. Keep `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED` off until the owner deliberately runs the first local Sentinel smoke.

### 10.9BS Oom Sakkie Effective Single-Shot Visibility - Local Ready

Purpose:

- Close Claude's honesty nuance after 10.9BQ/BR.
- Make the authority matrix show whether the narrow Sentinel single-shot env gate is effectively on/configured, while keeping general specialist LLM authority disabled.

What changed:

- The `specialist_llm_loop` area in `get_agent_authority_matrix()` now includes:
  - `effective_single_shot_enabled`
  - `effective_single_shot_configured`
  - `effective_single_shot_mode`
  - `effective_single_shot_specialist`
  - `effective_single_shot_note`
- These fields are derived from the existing Sentinel dry-run policy snapshot.
- The matrix still reports:
  - `enabled = false` for `specialist_llm_loop`,
  - `enabled_count = 0`,
  - top-level `specialist_llm_enabled = false`.
- Tests cover:
  - default-off reporting,
  - env-on/configured reporting,
  - the fact that even when the narrow env gate is on, general specialist LLM authority remains disabled.

Safety envelope:

- No new route.
- No new UI execution button.
- No new store or migration.
- No LLM call.
- No specialist tool execution.
- No farm-data write.
- No public/customer output.
- No deploy, Telegram cutover, physical-control path, or financial action.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 279 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- `python -m unittest` -> 609 tests OK.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.

Next gate:

1. Commit and push 10.9BS.
2. Confirm audit-rail and browser-behavior GitHub Actions are green.
3. Ask Claude to review the full 10.9BP-BS batch before turning on `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED`.

### 10.9BT Oom Sakkie Sentinel Single-Shot Runbook - Local Ready

Purpose:

- Turn the first live Sentinel smoke from an improvised action into an explicit supervised procedure.
- Keep the actual env-on run as an owner-approved operational step, not a background automation.

What changed:

- Added `docs/06-operations/OOM_SAKKIE_SENTINEL_SINGLE_SHOT_RUNBOOK.md`.
- The runbook covers:
  - preconditions,
  - required dry-run request / dispatch request / design approval / execution approval chain,
  - short `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED=1` smoke window,
  - policy checks before running,
  - the exact local endpoint to call once,
  - expected success and failure shapes,
  - append-only result verification,
  - replay-block verification,
  - immediate flag-off confirmation,
  - outcome fields to log after the smoke.

Safety envelope:

- Docs-only.
- Does not enable the env flag.
- Does not call an LLM.
- Does not add routes, stores, migrations, UI buttons, or tools.
- Does not write farm data.
- Does not create public/customer output.
- Does not deploy, cut over Telegram, control hardware, or touch financial actions.

Verification:

- Documentation reviewed locally.

Next gate:

1. Commit and push 10.9BT.
2. Confirm GitHub Actions are green.
3. Run the first Sentinel smoke only after owner approval, with the env flag off again immediately afterward.

### 10.9BU Oom Sakkie First Sentinel Smoke And Review Packet Fix - Local Ready

Purpose:

- Execute the first owner-approved Sentinel single-shot smoke.
- Verify replay blocking and flag-off recovery.
- Fix the review-packet reader so the owner can inspect the honest single-shot result.

Smoke outcome:

- Owner approved the smoke explicitly.
- Temporary local server ran with `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED=1`.
- Normal kiosk policy was verified afterward with `specialist_dry_run.enabled = false`.
- Smoke chain:
  - dry-run request `OSK-AGENT-DRYRUN-499E983FAF`
  - dispatch request `OSK-DISPATCH-REQ-3234DBAB07`
  - execution approval `OSK-DISPATCH-EXEC-APPROVAL-SMOKE-20260609-CODEX1`
  - consumed event `OSK-DISPATCH-EXEC-EVENT-6D892274A9`
  - result `OSK-AGENT-DRYRUN-RESULT-C63AF980E948`
- Result was advisory-only Sentinel text.
- Replay against the same approval returned `409 dispatch_execution_approval_already_consumed`.

Integration fix:

- `build_agent_dry_run_result_review_packet()` now accepts the narrow single-shot result shape:
  - `mode = single_shot_sentinel_advisory_result`
  - `status = recorded_from_single_shot_sentinel_llm`
  - `specialist_slug = sentinel`
  - `runs_specialist = true`
  - `runs_specialist_llm = true`
  - `dispatch_enabled = false`
  - `runs_specialist_tools = false`
  - `writes = false`
  - `applies_runtime_change = false`
- The same function still rejects unsafe flags for normal dry-run results and single-shot results.

Safety envelope:

- No general specialist LLM loop.
- No specialist tool execution.
- No farm-data write.
- No public/customer output.
- No deploy, Telegram cutover, physical-control path, or financial action.
- No replay of the consumed approval.

Verification:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 281 tests OK.
- `node --check static/js/oomSakkie.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- `python -m unittest` -> 611 tests OK.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node --check playwright.config.js` passed.
- Existing smoke result review packet returned `200`.
- Replay returned `409 dispatch_execution_approval_already_consumed`.
- Normal kiosk policy returned `specialist_dry_run.enabled = false` after the smoke.

Next gate:

1. Owner reviews result `OSK-AGENT-DRYRUN-RESULT-C63AF980E948`.
2. Record accepted/rejected/review-note event only after owner review.
3. Do not design accept-result-into-learning automation or any widening beyond Sentinel until this smoke is reviewed.

### 10.9BV Oom Sakkie Owner Approval Console - Local Ready

Purpose:

- Reduce the confusing Workbench clutter by giving the owner one first-screen approval queue.
- Keep the long System Workbench as the traceability/audit area, not the primary daily decision surface.

What changed:

- Added `Needs Your Approval` above the System Workbench.
- The console summarizes current owner decisions from existing in-memory queues:
  - agent result reviews,
  - agent dry-run handoffs that do not already have a result,
  - build handoffs,
  - patch reviews,
  - deploy decision records.
- Each console card opens the existing Workbench section or existing review action on explicit owner click.
- No new endpoint, route, store, migration, or decision type was added.

Safety envelope:

- UI-only clarity layer over existing append-only gates.
- No background polling.
- No hidden POSTs.
- No auto-accept, auto-reject, auto-build, auto-patch, or auto-deploy.
- No specialist dispatch, specialist tool execution, farm-data write, public/customer output, Telegram cutover, physical control, or financial action.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes` -> 254 tests OK.

Next gate:

1. Owner checks the kiosk visually and confirms the approval console is clearer than the Workbench.
2. If it is still too busy, the next UI-only Prism slice should collapse old Workbench detail further behind audit tabs, without changing authority.
3. Do not design the next automation step until the accepted Sentinel smoke result has been reviewed as evidence.

### 10.9BW Oom Sakkie Controller Board - Local Ready

Purpose:

- Make the agent stage feel more like a Jarvis-style controller view.
- Show the owner what Oom Sakkie is coordinating without adding any execution path.

What changed:

- Added a compact `Controller / Specialist / Owner Gate` board inside the agent stage.
- `renderControllerBoard()` populates it from the existing `agent_activity` object already returned by `/message`.
- Idle state stays explicit: no workspace open, no approval waiting, read-only routing pending.
- Active state names the selected specialist, tool/workspace, selection reason, and owner gate status.

Safety envelope:

- Frontend display only.
- No new endpoint, fetch, route, store, migration, or POST.
- No in-console approval, runner, deploy, send, sell, trade, or control button.
- No specialist dispatch, specialist tool execution, farm-data write, public/customer output, Telegram cutover, physical control, deploy automation, or financial action.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.

### 10.9BX Oom Sakkie Primary Command Deck - Local Ready

Purpose:

- Put the daily owner commands in the first screen instead of forcing the owner into the large quick-action grid.
- Keep the commands read-only and explicit-click.

What changed:

- Added a first-screen command deck with:
  - `Start Day` -> daily command brief,
  - `Needs approval` -> approval status,
  - `Agent command center` -> command center,
  - `Gate status` -> safety gates.
- The deck uses the existing `data-quick-ask` event binding.
- No new JavaScript fetch path was introduced.

Safety envelope:

- Explicit owner click only.
- Uses existing `/message` read-only ask path.
- No hidden POST, polling, runner UI, direct approval, direct deploy, direct send, direct sale, direct trade, or physical control.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.

### 10.9BY Oom Sakkie Quick Checks Drawer - Local Ready

Purpose:

- Reduce visual clutter now that the primary command deck exists.
- Keep all read-only quick checks available without making them dominate the kiosk.

What changed:

- Wrapped the larger quick-action grid in a collapsed `More read-only checks` drawer.
- Existing farm/business/agent quick buttons and prompts are unchanged.
- Existing `querySelectorAll("[data-quick-ask]")` binding still handles buttons inside the drawer.

Safety envelope:

- Template/CSS-only presentation change.
- No new endpoint, fetch, route, store, migration, POST, or authority change.
- No background polling or hidden POSTs.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes` -> 254 tests OK.

Next gate:

1. Owner visually checks whether the first screen now feels clearer: presence/orb, agent stage, command deck, answer, approval console, and detailed Workbench below.
2. If still too busy, next safe work is a UI-only Workbench tab/drawer split.
3. Do not add direct `Approve`, `Run`, `Deploy`, `Send`, `Post`, `Sell`, `Trade`, or `Control` buttons to the first-screen console without a separate Claude-reviewed gate.

### 10.9BZ Oom Sakkie Command UI Browser Gate Hardening - Local Ready

Purpose:

- Make the real-browser safety gate aware of the new command deck and quick-check drawer.
- Catch future regressions where opening UI drawers or clicking primary commands causes hidden automation.

What changed:

- `tests/oom_sakkie_playwright_behavior.spec.js` now asserts:
  - `.oom-command-deck` is visible,
  - `.oom-quick-drawer` is visible,
  - opening the quick drawer creates no non-GET `/api/oom-sakkie/` call,
  - opening the quick drawer creates no interval polling,
  - primary command-deck clicks still use the explicit owner-triggered `/message` path.
- Frontend route contracts pin those Playwright assertions.

Safety envelope:

- Test-only.
- No app code, route, store, migration, runtime flag, runner UI, specialist dispatch, specialist tool execution, farm-data write, public/customer output, Telegram cutover, deploy, physical control, or financial action.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.

Next gate:

1. Let GitHub Actions run the real browser behavior gate after push.
2. Owner reviews the visible kiosk in the browser.
3. Claude reviews the 10.9BW-BZ UI/test batch before any further UI action surfaces are added.

### Morning Decision Queue - Owner Gate

This is the single live decision that should be front-and-center before any next authority design:

1. Review Sentinel single-shot smoke result `OSK-AGENT-DRYRUN-RESULT-C63AF980E948`.
2. Confirm whether the accepted learning evidence should remain planning-only evidence.
3. Do not design accept-result-into-learning automation, Sentinel widening, tool execution, public/customer output, Telegram, deploy, physical controls, farm-data writes, or financial/trading paths until this review is complete and separately Claude-reviewed.

Current safe state:

- `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED` stays off outside a supervised run.
- The owner approval console stays read + navigate only.
- First-screen command buttons stay ask-only through `/message`.
- The full audit trail stays available inside System Workbench.

### 10.9CA Oom Sakkie Sentinel Single-Shot Contract Alignment - Local Ready

Purpose:

- Remove drift risk between the Sentinel single-shot runner, result store, review packet, tests, and migration contract.
- Keep the first execution path narrow and unchanged.

What changed:

- Added `modules/oom_sakkie/sentinel_single_shot_contract.py`.
- Centralized the Sentinel single-shot result identity:
  - `mode = single_shot_sentinel_advisory_result`
  - `status = recorded_from_single_shot_sentinel_llm`
  - `specialist_slug = sentinel`
- Centralized the allowed result flags:
  - `runs_specialist = true`
  - `runs_specialist_llm = true`
  - `dispatch_enabled = false`
  - `runs_specialist_tools = false`
  - `writes = false`
  - `applies_runtime_change = false`
- The store, review packet, runner, and tests now use this contract.
- The static migration SQL remains unchanged, and tests now assert it matches the contract constants.

Safety envelope:

- Hardening only.
- No env flag was enabled.
- No UI runner wiring.
- No specialist tool execution, farm-data write, public/customer output, deploy, Telegram cutover, physical control, or financial action.

Verification:

- `python -m unittest tests.test_oom_sakkie_service` -> 174 tests OK, 4 expected skips.
- `node --check static/js/oomSakkie.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.

### 10.9CB Oom Sakkie Dispatch Execution Consumed-Once Live-PG Test - Local Ready

Purpose:

- Prove the database-level one-shot guard for execution approvals, not only the application check.

What changed:

- Added a DATABASE_URL-gated live Postgres test that:
  - inserts a valid Sentinel dispatch request,
  - inserts one execution approval,
  - inserts one `consumed_by_single_dry_run_result` event,
  - verifies a second consumed event for the same approval raises a unique constraint error,
  - verifies a normal `review_note` event can still be appended.

Safety envelope:

- Test-only.
- No app behavior changed.
- No runner execution, no env enablement, no tool execution, no writes outside audit rails, and no public/customer output.

Verification:

- The test skips safely when `DATABASE_URL` is not configured.
- It will run in the existing disposable-Postgres audit-rail GitHub workflow after push.

### 10.9CC Oom Sakkie Consumed-Once Migration Assertion - Local Ready

Purpose:

- Make the consumed-once DB guard visible in the normal non-live service test too.
- Clarify that Claude's last feedback saw the single-shot contract alignment but missed the already-added live-PG consumed-once test.

What changed:

- `test_dispatch_execution_approval_migration_is_append_only_and_no_execution` now asserts the migration contains:
  - `create unique index if not exists idx_oom_sakkie_dispatch_execution_approval_consumed_once`
  - the partial-index filter `where event_type = 'consumed_by_single_dry_run_result'`
- The DATABASE_URL-gated live-PG test remains the stronger proof because it actually inserts one consumed event and verifies the second insert fails.

Safety envelope:

- Test/docs clarification only.
- No app behavior changed.
- No env flag enabled, no Sentinel runner UI, no authority widening, and no farm-data/public/deploy/Telegram/physical/financial path.

### 10.9CD Oom Sakkie Learning Influence Proposal Rail - Local Ready

Purpose:

- Start making accepted Sentinel/agent evidence useful without silently changing the system.
- Convert accepted evidence into proposed learning influence records that the owner can review.
- Keep learning influence as proposal-only until a separate owner + Claude-reviewed gate exists to apply anything.

What changed:

- Added migration `supabase/migrations/202606100001_create_oom_sakkie_learning_influence_proposals.sql`.
- Added `modules/oom_sakkie/learning_influence_store.py`.
- Added protected routes:
  - `GET /api/oom-sakkie/agent-learning/influence-proposals`
  - `POST /api/oom-sakkie/agent-learning/influence-proposals/from-accepted`
  - `POST /api/oom-sakkie/agent-learning/influence-proposals/<proposal_id>/events`
- Proposal rows are generated from accepted dry-run results only.
- One source result can produce one proposal (`idx_oom_sakkie_learning_influence_source_once`).
- Owner events are append-only and limited to:
  - `approved_for_future_planning`
  - `rejected`
  - `review_note`

Safety envelope:

- `applies_learning_now = false`
- `changes_prompt_now = false`
- `changes_runtime_now = false`
- `dispatch_enabled = false`
- `writes = false`
- No prompt rewrite, routing change, runtime flag, specialist dispatch, specialist tool execution, farm-data write, public/customer output, Telegram, deploy, physical control, or financial action.

Verification:

- Migration content test pins mode/status/event types/no-apply flags/append-only triggers.
- DATABASE_URL-gated live-PG test verifies `applies_learning_now = true` is rejected and update/delete triggers reject mutation.
- Route tests verify protected endpoints return false apply/write flags and deny non-local access.

### 10.9CE Oom Sakkie Learning Influence Status Tool - Local Ready

Purpose:

- Let the owner ask Oom Sakkie about self-learning progress and Sentinel suggestions in normal language.
- Explain what is waiting for owner review without applying it.

What changed:

- Added read-only `learning_influence_status`.
- Added deterministic routing for:
  - `learning influence`
  - `learning proposals`
  - `sentinel suggestions`
  - `self-learning`
  - `what learning needs approval`
- The tool reads proposal counts and reports waiting / approved-for-future-planning / rejected status.

Safety envelope:

- Read-only status only.
- Chat cannot generate proposals or apply learning.
- No runtime/prompt/tool/data/public/deploy/Telegram/control/financial authority.

Verification:

- Tool registry contract includes `learning_influence_status` and still asserts every tool is read-only.
- Focused Oom Sakkie service/routes/frontend tests passed locally at 292 tests.
- Browser behavior smoke passed.

Next gate:

1. Push this hardening clarification and confirm both GitHub Actions gates are green.
2. Ask Claude to review 10.9CA-CE together with the already-passed 10.9BW-BZ UI batch.
3. Owner still reviews `OSK-AGENT-DRYRUN-RESULT-C63AF980E948`; after that, the owner can generate learning influence proposals from accepted evidence.
4. Do not build any consumer that applies approved learning proposals until that consumer has its own dedicated owner + Claude-reviewed gate.

### 10.9CF Oom Sakkie Learning Influence Workbench UI - Local Ready

Purpose:

- Make the accepted-evidence -> learning-proposal path visible and usable from the kiosk.
- Keep all proposal generation/review actions explicit, local, append-only, and review-only.
- Surface pending learning proposals in the owner approval queue without adding first-screen approve/apply controls.

What changed:

- Added a `Learning Influence Proposals` panel to the System Workbench.
- Added Workbench buttons:
  - `Prepare Proposals` calls the protected `POST /api/oom-sakkie/agent-learning/influence-proposals/from-accepted` route.
  - `Refresh` calls the protected `GET /api/oom-sakkie/agent-learning/influence-proposals?limit=8` route.
- Proposal rows show source result, specialist, proposal text, proposed planning rules, latest event, and guard flags.
- Proposal review buttons record append-only events only:
  - `approved_for_future_planning`
  - `rejected`
  - `review_note`
- Workbench `Next action` now includes pending learning influence proposals.
- The first-screen owner approval console can list pending learning proposals, but the action is navigation-only: it opens the Workbench panel and does not approve/generate/apply learning.

Safety envelope:

- `approved_for_future_planning` still means future planning evidence only.
- No proposal consumer was added.
- No prompt rewrite, routing change, runtime flag, specialist dispatch, specialist tool execution, farm-data write, public/customer output, Telegram, deploy, physical control, or financial action.
- The Sentinel runner remains unreferenced from the UI and the env flag remains off.

Verification:

- Frontend contract coverage pins the panel, fetch routes, review event types, and approval-console navigation-only behavior.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest tests.test_frontend_route_contracts` passed at 28 tests.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.

Next gate:

1. Run the focused Oom Sakkie suite and full local unittest suite.
2. Push only after tests pass.
3. Confirm both GitHub Actions gates are green.
4. Ask Claude to review 10.9CF with 10.9CD/CE as the context.
5. Do not build a consumer that applies approved learning proposals until that consumer has its own dedicated owner + Claude-reviewed gate.

### 10.9CG Oom Sakkie Learning Influence Browser Gate Hardening - Local Ready

Purpose:

- Prove the new learning influence Workbench actions follow the same owner-click-only browser behavior as the rest of the kiosk.
- Keep the learning proposal path visible and reviewable without adding hidden POSTs, polling, or any apply-learning consumer.

What changed:

- Extended `tests/oom_sakkie_browser_behavior_smoke.js`:
  - stubs learning-influence list/prepare/event responses as no-apply JSON.
  - asserts `Prepare Proposals` only POSTs after an explicit owner click.
  - asserts that click does not start interval polling.
- Extended `tests/oom_sakkie_playwright_behavior.spec.js`:
  - stubs a pending learning-influence proposal.
  - asserts `Prepare Proposals` POSTs only after an explicit owner click.
  - asserts `Approve For Future Planning` records only a proposal event after an explicit owner click.
  - asserts both clicks create no interval polling.
- Frontend route contracts now pin those smoke/Playwright assertions.

Safety envelope:

- Test/CI hardening only.
- No app runtime behavior changed.
- No route, store, migration, prompt, runtime flag, proposal consumer, Sentinel runner UI, specialist dispatch, specialist tool execution, farm-data write, public/customer output, Telegram, deploy, physical control, or financial path.

Verification:

- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- `node --check static/js/oomSakkie.js` passed.
- `python -m unittest tests.test_frontend_route_contracts` passed at 28 tests.

Next gate:

1. Run the focused Oom Sakkie suite and full local unittest suite.
2. Push only after tests pass and confirm both GitHub Actions gates are green.
3. Ask Claude to review 10.9CF-CG together.
4. Do not build any proposal consumer that applies approved learning proposals until that consumer has its own dedicated owner + Claude-reviewed gate.

### 10.9CH Oom Sakkie Owner Cockpit UI - Local Ready

Purpose:

- Replace the busy first-screen approval list with a cleaner owner-facing cockpit.
- Keep the System Workbench as the complete audit/debug surface for Codex, Claude, and traceability.
- Let the owner handle simple evidence/proposal review decisions from the first screen without hunting through the Workbench.

What changed:

- Renamed the first-screen decision area to `Owner Cockpit`.
- Added one primary decision card, a compact `Next in line` queue, and an OSK ID search/jump input.
- Added an `Audit Trail` button that opens the full System Workbench without hiding or removing the detailed audit trail.
- Direct cockpit actions are limited to append-only review records:
  - agent dry-run result: `accepted_for_learning` or `rejected`.
  - learning influence proposal: `approved_for_future_planning` or `rejected`.
- Build handoff, patch review, deploy decision, dry-run handoff, and proposal preparation remain detailed Workbench flows. The cockpit opens those areas but does not approve, run, apply, deploy, send, sell, trade, or control anything.

Safety envelope:

- The Sentinel runner is still not referenced from the UI.
- `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED` remains off outside supervised runs.
- No proposal consumer was added.
- No prompt rewrite, routing change, runtime flag, specialist dispatch, specialist tool execution, farm-data write, public/customer output, Telegram, deploy, physical control, or financial action.
- The new direct cockpit buttons create only append-only evidence/proposal review events and are covered by explicit-click/no-polling browser gates.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- `node --check tests/oom_sakkie_browser_behavior_smoke.js` passed.
- `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- `python -m unittest tests.test_frontend_route_contracts` passed at 28 tests.
- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` passed at 293 tests, 1 live-DB skip.
- `python -m unittest` passed at 623 tests, 1 live-DB skip.

Next gate:

1. Run the focused Oom Sakkie suite and full local unittest suite.
2. Push only after tests pass and confirm both GitHub Actions gates are green.
3. Ask Claude to review 10.9CH specifically as an owner-facing action-surface change.
4. Do not add direct `Approve Patch`, `Run Sentinel`, `Deploy`, `Send`, `Post`, `Sell`, `Trade`, or `Control` buttons to the first-screen cockpit without a dedicated owner + Claude-reviewed gate.

### 10.9CI Oom Sakkie Owner Cockpit Decision Feedback - Local Ready

Purpose:

- Make owner-clicked cockpit decisions visibly confirm what happened.
- Avoid the owner feeling like `Accept For Learning` disappeared or did nothing.

What changed:

- Confirmed `OSK-AGENT-DRYRUN-RESULT-C63AF980E948` now has `latest_event.event_type = accepted_for_learning`.
- Updated cockpit result/proposal event handlers to await the event response, refresh the result/proposal queues, and write a clear status message in the cockpit.
- Status copy explicitly says the record is evidence/planning only and that no runtime change or learning application occurred.

Safety envelope:

- UI feedback/refresh polish only.
- Still no Sentinel runner UI.
- Still no proposal consumer or apply-learning path.
- Still no prompt rewrite, routing change, runtime flag, specialist dispatch, specialist tool execution, farm-data write, public/customer output, Telegram, deploy, physical control, or financial action.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- `python -m unittest tests.test_frontend_route_contracts` passed at 28 tests.

Next gate:

1. Owner visually confirms the cockpit now shows a clear status after append-only review actions.
2. Do not add any first-screen run/apply/deploy/send/sell/control/trade action without a dedicated owner + Claude-reviewed gate.

### 10.9CJ Oom Sakkie Cockpit Accepted-Result Proposal Prep - Local Ready

Purpose:

- Remove the extra Workbench step after the owner accepts one agent result for learning.
- Prepare the learning influence proposal for the exact clicked result only.
- Keep proposal generation review-only and never apply learning automatically.

What changed:

- Added protected route `POST /api/oom-sakkie/agent-learning/influence-proposals/from-result`.
- Added `record_learning_influence_proposal_from_result()` to load one dry-run result and require its latest event to be `accepted_for_learning`.
- After a cockpit `Accept For Learning` click succeeds, the kiosk now prepares the proposal for that same dry-run result ID and refreshes the learning proposal queue.
- The cockpit status tells the owner whether one planning proposal was prepared or already existed.
- Browser behavior tests now assert the proposal-prep POST includes the exact clicked `source_result_id`.

Safety envelope:

- Proposal prep remains append-only/review-only.
- Existing accepted-result bulk prep still exists in the Workbench for deliberate batch use.
- The cockpit does not approve the proposal, apply learning, change prompts, change routes, run a specialist, deploy, send, post, sell, trade, control equipment, or write farm data.
- `applies_learning_now = false`, `changes_prompt_now = false`, `changes_runtime_now = false`, `dispatch_enabled = false`, and `writes = false` stay pinned in responses/tests.

Verification:

- Focused service/route/frontend tests passed.
- Dependency-free browser behavior smoke passed.
- JS syntax checks passed for the kiosk and browser smoke files.

Next gate:

1. Owner visually checks the cockpit flow: click `Accept For Learning`, confirm a planning proposal appears, and confirm the status says no learning/runtime change was applied.
2. Do not build any consumer that applies approved learning proposals until that consumer has its own dedicated owner + Claude-reviewed gate.

### 10.9CK Oom Sakkie Learning/Cockpit Review Packet Refresh - Local Ready

Purpose:

- Keep the one-command Claude review handoff aligned with the current learning influence and cockpit action-surface work.
- Record current CI evidence after the accepted-result proposal-prep checkpoint.

What changed:

- Updated `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md` so the current review packet scope runs through 10.9CJ.
- Added explicit review bullets for:
  - Owner Cockpit UI and decision feedback.
  - Cockpit accepted-result proposal prep.
- Added `modules/oom_sakkie/learning_influence_store.py`, the learning influence migration, and the Playwright browser behavior spec to the inspect list.
- Updated verification evidence with:
  - local focused suite at 297 tests,
  - full local suite at 627 tests,
  - green GitHub Actions runs for commit `613085b`.
- Added a dedicated Claude design-check question for 10.9CJ.

Safety envelope:

- Documentation/review readiness only.
- No app runtime behavior changed.
- No endpoint, store, migration, UI action, prompt/routing/runtime flag, specialist dispatch/tool execution, farm-data write, public/customer output, deploy, Telegram, physical control, financial action, or proposal consumer was added.

Verification:

- `node --check static/js/oomSakkie.js` passed.
- Focused frontend route contracts passed.
- GitHub Actions evidence was read with the local portable `gh.exe`; Oom Sakkie Browser Behavior and Audit Rails are green for the latest pushed checkpoint.

Next gate:

1. Owner can ask Claude Code: `Read docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md and run the current review.`
2. Keep learning influence proposal consumption locked until a separate owner + Claude-reviewed gate exists.

### 10.9CL Oom Sakkie Owner Review Packet Scope Evidence - Local Ready

Purpose:

- Make Oom Sakkie's own read-only `prepare Claude review` answer match the refreshed handoff scope.
- Keep review readiness visible from the kiosk without calling Claude, GitHub, or enabling authority.

What changed:

- Added current review metadata to `get_jarvis_owner_review_packet()`:
  - scope: `Oom Sakkie 10.6 through 10.9CK`,
  - handoff file and exact Claude prompt,
  - focus items for Owner Cockpit, accepted-result proposal prep, learning proposal-only boundaries, and CI gates,
  - latest green CI run evidence from the local `gh` check.
- The `jarvis_owner_review_packet` tool summary now names the current scope and counts the recorded green CI gates.
- Tests pin that the packet still has no learning influence consumer and does not apply learning, change prompts, or change runtime.

Safety envelope:

- Read-only packet content only.
- No Claude call, GitHub call, endpoint, store, migration, UI action, runtime flag, specialist dispatch/tool execution, farm-data write, public/customer output, deploy, Telegram, physical control, financial action, or learning proposal consumer was added.

Verification:

- Targeted owner review packet service tests passed.
- `node --check static/js/oomSakkie.js` passed.

Next gate:

1. Ask Oom Sakkie `prepare Claude review` and confirm it names the 10.9CK scope and says the packet does not approve authority.
2. Keep learning influence proposal consumption locked until a separate owner + Claude-reviewed gate exists.

### 10.9CM Oom Sakkie Owner Review Packet Chat Gate - Local Ready

Purpose:

- Turn the manual `prepare Claude review` browser check into a repeatable service test.
- Prove the routed Oom Sakkie answer names the current review scope and keeps authority locked.

What changed:

- Added a `handle_message()` regression test for `prepare Claude review`.
- The test verifies:
  - the deterministic router selects `jarvis_owner_review_packet`,
  - the answer names `10.9CK`,
  - the answer reports the recorded green CI gate count,
  - the safety note says the packet does not approve runtime authority,
  - Gatekeeper is the visible agent workspace,
  - no agent run, dispatch, or write authority is enabled.

Safety envelope:

- Test-only hardening.
- No app runtime behavior, endpoint, store, migration, UI action, prompt/routing rule, runtime flag, specialist dispatch/tool execution, farm-data write, public/customer output, deploy, Telegram, physical control, financial action, or learning proposal consumer was added.

Verification:

- Targeted `prepare Claude review` service test passed.
- `node --check static/js/oomSakkie.js` passed.

Next gate:

1. Keep this owner review packet as review-readiness only.
2. Do not build learning proposal consumption or runtime unlocks until a separate owner + Claude-reviewed gate exists.

### 10.9CN Oom Sakkie Review Packet Final Scope Sync - Local Ready

Purpose:

- Make the owner/Claude handoff and Oom Sakkie's read-only review packet include the latest 10.9CL/10.9CM review-readiness hardening.
- Stop the unattended build at a clean review gate instead of starting any learning consumer or runtime unlock.

What changed:

- Updated `get_jarvis_owner_review_packet()` metadata scope to `Oom Sakkie 10.6 through 10.9CM`.
- Updated the packet focus list to include owner review packet evidence and the `prepare Claude review` chat gate.
- Updated recorded CI evidence to the latest green commit `5de5d9d`:
  - `Oom Sakkie Browser Behavior` run `27314056906`,
  - `Oom Sakkie Audit Rails` run `27314056931`.
- Updated `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md` so Claude's current review packet names the 10.9CA-CM scope, latest verification, and design checks for 10.9CL/10.9CM.
- Updated service tests to pin the new scope, CI evidence, and no-authority guard behavior.

Safety envelope:

- Review-readiness metadata/docs/test hardening only.
- No endpoint, store, migration, UI action, prompt/routing rule, runtime flag, specialist dispatch/tool execution, farm-data write, public/customer output, deploy, Telegram, physical control, financial action, or learning proposal consumer was added.

Verification:

- Targeted owner review packet service tests passed.
- Focused Oom Sakkie route/service/frontend suite passed.
- Browser behavior smoke passed.
- Full local unittest suite passed.
- GitHub Actions passed for commit `5de5d9d` before this final metadata sync.

Next gate:

1. Owner runs Claude review with: `Read docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md and run the current review.`
2. Keep learning proposal consumption, runtime unlocks, and live specialist authority locked until a separate owner + Claude-reviewed gate exists.

### 10.9CO Oom Sakkie Learning Influence Live-PG Closure - Local Ready

Purpose:

- Act on Claude's review feedback for 10.9CA-CM.
- Close the remaining offline-only gap for the learning-influence `from-result` rail before relying on it in daily kiosk use.

Claude feedback acted on:

- Claude verdict for 10.9CA-CM: `pass`.
- Concrete next step: apply migration `202606100001_create_oom_sakkie_learning_influence_proposals.sql` to live Postgres and add DATABASE_URL-gated coverage for:
  - the `source_result_not_accepted_for_learning` 409 guard,
  - `on conflict do nothing` idempotency returning the existing proposal.

What changed:

- Applied migration `202606100001_create_oom_sakkie_learning_influence_proposals.sql` with the reviewed migration script.
- Added a DATABASE_URL-gated live-PG test proving:
  - a persisted dry-run result with no `accepted_for_learning` latest event is rejected with 409,
  - after recording `accepted_for_learning`, `record_learning_influence_proposal_from_result()` creates exactly one proposal,
  - a repeated call returns the existing proposal with `created_count = 0`,
  - proposal/app response flags remain `applies_learning_now = false`, `changes_prompt_now = false`, `changes_runtime_now = false`, `dispatch_enabled = false`, and `writes = false`.
- Added route-contract coverage for `/api/oom-sakkie/agent-learning/influence-proposals/from-result` to pin:
  - success,
  - 409 not-accepted guard propagation,
  - existing-proposal idempotency response.
- Updated the owner/Claude review packet scope to `Oom Sakkie 10.6 through 10.9CO`.

Safety envelope:

- Migration application plus tests/docs/metadata only.
- No learning proposal consumer, prompt/routing/runtime change, live specialist dispatch, specialist tool execution, farm-data write, public/customer output, deploy, Telegram, physical control, financial action, or broader authority was added.

Verification:

- Migration apply command succeeded.
- New live-PG `from-result` test passed with `.env` loaded.
- Existing plus new learning-influence live-PG tests passed.
- Route contract tests for `from-result` success/409/idempotency passed.

Next gate:

1. Run focused and full local verification, then push and confirm GitHub Actions.
2. Ask Claude to review 10.9CO before any learning proposal consumption or runtime-authority work.

### 10.9CP Oom Sakkie Learning Consumption Threat Model Packet - Local Ready

Purpose:

- Act on Claude's carried-forward CI-evidence drift nit without adding runtime GitHub calls.
- Build the largest safe pre-review slice before the high-risk learning proposal consumer gate: a read-only threat model and readiness packet for future consumption design.

Claude feedback acted on:

- Claude verdict for 10.9CO: `pass`.
- Claude repeated that CI evidence commit pins can drift after every push and suggested generating/dating evidence rather than treating hand-pinned commit IDs as exact current-HEAD proof.
- Claude explicitly did not authorize actual learning proposal consumption or runtime authority.

What changed:

- `CURRENT_CLAUDE_REVIEW_CI_EVIDENCE` now records `recorded_commit` values from the latest green run evidence and includes `ci_evidence_policy`:
  - `mode = recorded_operator_evidence_only`,
  - `runtime_calls_github = false`,
  - `auto_trusts_ci = false`,
  - note says evidence may trail newer commits until intentionally refreshed.
- Added read-only `get_learning_influence_consumption_readiness()`.
- Added read-only Oom Sakkie tool `learning_influence_consumption_readiness` and deterministic routing for learning-consumption / proposal-consumer / learning-threat-model questions.
- Added protected read-only route `GET /api/oom-sakkie/agent-learning/consumption-readiness`.
- The readiness packet lists:
  - allowed future scope for a first consumer design,
  - hard no-go scope,
  - threat scenarios for prompt/route poisoning, authority creep, stale evidence, replay/idempotency, and rollback gaps,
  - required gates before any consumer exists.
- The owner/Claude review packet now embeds the readiness packet and scopes the next bundled review through `10.9CP`.

Safety envelope:

- Read-only metadata, route, tool, and tests only.
- No proposal consumer, no proposal application, no prompt/routing/runtime change, no hidden POST or polling, no specialist dispatch, no specialist LLM/tool execution, no farm-data write, no public/customer output, no deploy, no Telegram, no physical control, and no financial action.

Verification:

- Targeted owner-review packet, learning-consumption readiness, routing, route, and JS syntax checks passed.

Next gate:

1. Run focused and full local verification, push, and confirm CI.
2. Ask Claude to review the combined 10.9CO/10.9CP follow-up before designing any learning proposal consumer.

### 10.9CQ Oom Sakkie Consumption Audit Rail Blueprint - Local Ready

Purpose:

- Act on Claude's 10.9CO/CP pass feedback without implementing a consumer.
- Fold Claude's two extra threat items into the readiness packet before they become expensive to retrofit.
- Prepare one large Claude-reviewable design packet for the first future implementation slice: append-only consumption audit rail with zero apply behavior.

Claude feedback acted on:

- Claude verdict for 10.9CO/CP: `pass`.
- Claude explicitly did not authorize the consumer itself.
- Claude asked to keep two added threat items in scope:
  - evidence provenance / integrity: proposal text may be LLM-produced untrusted input,
  - blast-radius bound: one consumption should touch at most one allowlisted target field and emit a size-capped reviewable diff.
- Claude recommended the first future implementation slice should be the append-only consumption audit rail plus consumed-once live-PG test with zero apply behavior.

What changed:

- Added threat scenario `evidence_provenance_and_integrity`.
- Added threat scenario `oversized_or_multi_target_blast_radius`.
- Added required gates:
  - `untrusted_proposal_text_policy`,
  - `one_target_field_per_consumption`,
  - `size_capped_reviewable_diff`.
- Added read-only `get_learning_influence_consumption_audit_rail_blueprint()`.
- Added read-only Oom Sakkie tool `learning_influence_consumption_audit_rail_blueprint` and deterministic routing for learning-consumption-audit-rail / consumer-blueprint questions.
- Added protected read-only route `GET /api/oom-sakkie/agent-learning/consumption-audit-rail-blueprint`.
- The blueprint proposes:
  - request/event table shape,
  - allowed future target contract,
  - untrusted proposal text policy,
  - size-capped diff contract,
  - consumed-once live-PG tests,
  - route contract tests.
- The owner/Claude review packet now embeds this blueprint and scopes the next bundled review through `10.9CQ`.

Safety envelope:

- Read-only blueprint, route, tool, docs, and tests only.
- No migration, store, event writer, proposal consumer, proposal application, prompt/routing/runtime change, hidden POST or polling, specialist dispatch, specialist LLM/tool execution, farm-data write, public/customer output, deploy, Telegram, physical control, or financial action.

Verification:

- Targeted owner packet, threat model, audit-rail blueprint, route, routing, and JS syntax checks passed.

Next gate:

1. Run focused and full local verification, push, and confirm CI.
2. Ask Claude to review 10.9CQ before implementing the append-only consumption audit rail.

### 10.9CR Oom Sakkie Consumption Audit Rail Implementation - Local Ready

Purpose:

- Act on Claude's 10.9CQ pass without implementing a learning consumer.
- Implement only the append-only consumption audit rail Claude cleared: request records, review events, DB consumed-once proof, and route/live-PG tests.
- Keep the first slice review-note-only with zero prompt/route diff application.

Claude feedback acted on:

- Claude verdict for 10.9CQ: `pass`.
- Claude cleared implementation of the append-only audit rail as the next gate.
- Claude recommended the first rail slice produce only request/event records plus a review-note artifact, with no applyable diff machinery.
- Claude explicitly did not authorize a learning proposal consumer or runtime authority.

What changed:

- Added migration `supabase/migrations/202606110001_create_oom_sakkie_learning_influence_consumption_audit_rail.sql`.
- Added `modules/oom_sakkie/learning_influence_consumption_store.py`.
- Added protected routes:
  - `GET /api/oom-sakkie/agent-learning/consumption-requests`,
  - `POST /api/oom-sakkie/agent-learning/consumption-requests`,
  - `POST /api/oom-sakkie/agent-learning/consumption-requests/<consumption_request_id>/events`.
- A consumption request requires the source learning proposal's latest event to be `approved_for_future_planning`; non-approved proposals return `409 proposal_not_approved_for_future_planning`.
- Each request is limited to one allowlisted target kind/field and stores a `review_note_only` artifact with untrusted proposal-text policy and source provenance.
- The generic event route rejects `consumed_for_patch_proposal` with `403 consumed_event_is_future_consumer_only`; the marker is present only as a later reviewed consumer-path DB guard.
- The migration forces `applies_learning_now = false`, `changes_prompt_now = false`, `changes_runtime_now = false`, `dispatch_enabled = false`, and `writes = false` on both request and event tables, blocks update/delete, and enforces one `consumed_for_patch_proposal` marker per request through a partial unique index.
- The owner/Claude review packet now scopes through `10.9CR` and says the audit rail is implemented but still has no consumer and no apply path.

Safety envelope:

- Records only.
- No learning proposal consumer, no prompt/route diff application, no prompt/routing/runtime change, no hidden POST or polling, no specialist dispatch, no specialist LLM/tool execution, no farm-data write, no public/customer output, no deploy, no Telegram, no physical control, and no financial action.

Verification:

- Applied migration `202606110001_create_oom_sakkie_learning_influence_consumption_audit_rail.sql`.
- Focused audit suite without dotenv: `318 OK`, with the DATABASE_URL-gated live test skipped as expected.
- Focused audit suite with `.env` loaded: `318 OK`, including the new live-PG consumption audit rail test.
- The live-PG test proves:
  - non-approved proposal rejects with 409 before request insert,
  - approved proposal creates one request,
  - repeated same target returns the existing request with `created_count = 0`,
  - review-note events remain evidence and do not consume,
  - second `consumed_for_patch_proposal` marker fails through the partial unique index,
  - update/delete on both new tables raises append-only errors.
- `node --check static/js/oomSakkie.js` passed.

Next gate:

1. Run browser smoke/full local verification, push, and confirm GitHub Actions.
2. Ask Claude to review 10.9CR before any learning proposal consumer or applyable prompt/route diff design.

### 10.9CS Oom Sakkie Learning Consumer Design Static Guard - Local Ready

Purpose:

- Act on Claude's 10.9CR pass without implementing a consumer.
- Guard the one dangerous hinge Claude identified: `allow_consumed=True`.
- Package the next consumer-design questions into a read-only packet for owner + Claude review.

Claude feedback acted on:

- Claude verdict for 10.9CR: `pass`.
- Claude called `allow_consumed` the single hinge to guard hardest.
- Claude recommended a regression test now that asserts no production module calls `record_learning_influence_consumption_event(..., allow_consumed=True)`.
- Claude recommended the next consumer slice stay review-note-only, owner-gated, and covered by no-authority/static guards.

What changed:

- Added a static AST regression test over `modules/**/*.py` that fails if any production caller passes `allow_consumed=True` to the learning-consumption event writer.
- Added read-only `get_learning_influence_consumer_design_packet()`.
- Added read-only Oom Sakkie tool `learning_influence_consumer_design_packet`.
- Added deterministic routing for learning-consumer-design and `allow_consumed` guard questions.
- Added protected read-only route `GET /api/oom-sakkie/agent-learning/consumer-design-packet`.
- The design packet states:
  - `allow_consumed_production_callers = []`,
  - `learning_influence_consumer_enabled = false`,
  - first future output must be `review_note_artifact_only`,
  - proposal text is untrusted,
  - one target field per consumption,
  - owner approval event required before any future consumed marker,
  - rollback/manual-application artifact required,
  - manual application remains outside the kiosk.

Safety envelope:

- Static guard, read-only packet, tool, route, docs, and tests only.
- No consumer, no production `allow_consumed=True` caller, no prompt/route diff application, no prompt/routing/runtime change, no hidden POST or polling, no specialist dispatch, no specialist LLM/tool execution, no farm-data write, no public/customer output, no deploy, no Telegram, no physical control, and no financial action.

Verification:

- Focused audit suite: `323 OK`.
- `node --check static/js/oomSakkie.js` passed.
- Live-gated focused audit suite with `.env` loaded: `323 OK`.
- Browser behavior smoke passed.
- Full local unittest suite: `653 OK`.

Next gate:

1. Run browser smoke/full local verification, push, and confirm GitHub Actions.
2. Ask Claude to review 10.9CS before any learning proposal consumer implementation.

### 10.9CT Oom Sakkie Allow-Consumed Static Guard Hardening - Local Ready

Purpose:

- Act on Claude's 10.9CS pass feedback without implementing a consumer.
- Close Claude's low-priority static-guard nit before any future consumer code exists.
- Make the automated guard harder to evade accidentally.

Claude feedback acted on:

- Claude verdict for 10.9CS: `pass`.
- Claude noted the AST guard caught only keyword `allow_consumed=True` with literal `True`.
- Claude suggested hardening the guard to also catch aliased calls, positional fourth-argument use, and non-literal truthy values.

What changed:

- The static AST test now tracks:
  - direct imports,
  - aliased function imports,
  - module imports,
  - module-attribute calls.
- The guard now flags:
  - positional fourth arguments to `record_learning_influence_consumption_event`,
  - `**kwargs`,
  - any `allow_consumed` keyword value that is not literal `False`.
- The consumer-design packet wording now documents this stronger trip-wire.
- Scope metadata moved to `10.9CT`.

Safety envelope:

- Test/packet/docs hardening only.
- No consumer, no production `allow_consumed` caller, no prompt/route diff application, no prompt/routing/runtime change, no hidden POST or polling, no specialist dispatch, no specialist LLM/tool execution, no farm-data write, no public/customer output, no deploy, no Telegram, no physical control, and no financial action.

Verification:

- Focused audit suite: `323 OK`.
- `node --check static/js/oomSakkie.js` passed.

Next gate:

1. Run focused/full local verification, push, and confirm GitHub Actions.
2. Ask Claude to review 10.9CT before any learning proposal consumer implementation.

### 10.9CU Oom Sakkie Source-Backed Allow-Consumed Caller Evidence - Local Ready

Purpose:

- Act on Claude's carried-forward note that `allow_consumed_production_callers = []` was documentation backed by a separate static test.
- Make the consumer-design packet's no-production-caller claim source-backed without implementing a consumer.
- Reuse one scanner for both the packet evidence and the regression guard.

Claude feedback acted on:

- Claude verdict for 10.9CT: `pass`.
- Claude noted the remaining hardcoded `allow_consumed_production_callers: []` field was acceptable, but depended on the separate AST test for honesty.
- This slice folds that fact into live packet evidence before any future consumer gate.

What changed:

- `agent_runtime.py` now exposes `find_learning_influence_allow_consumed_callers()`.
- `get_learning_influence_consumer_design_packet()` now derives `allow_consumed_production_callers` from that scanner instead of returning a hardcoded empty list.
- The static regression test uses the shared scanner.
- A synthetic scanner test proves detection for alias calls, module calls, positional fourth-argument overrides, `**kwargs`, and non-literal-false `allow_consumed` values while allowing literal `False`.
- Scope metadata moved to `10.9CU`.

Safety envelope:

- Evidence/test/packet hardening only.
- No consumer, no production `allow_consumed` caller, no prompt/route diff application, no prompt/routing/runtime change, no hidden POST or polling, no specialist dispatch, no specialist LLM/tool execution, no farm-data write, no public/customer output, no deploy, no Telegram, no physical control, and no financial action.

Verification:

- Focused audit suite: `324 OK`.
- `node --check static/js/oomSakkie.js` passed.
- Live-gated focused audit suite with `.env` loaded: `324 OK`.
- Browser behavior smoke passed.
- Full local unittest suite: `654 OK`.
- GitHub Actions after commit `d6ca87b`: `Oom Sakkie Browser Behavior` run `27340979776` success; `Oom Sakkie Audit Rails` run `27340979805` success.

Next gate:

1. Run focused/full local verification, push, and confirm GitHub Actions.
2. Ask Claude to review 10.9CU before any learning proposal consumer implementation.

### 10.9CV Oom Sakkie Allow-Consumed Scanner Resilience - Local Ready

Purpose:

- Act on Claude's two low-priority 10.9CU scanner robustness nits.
- Keep the source-backed `allow_consumed_production_callers` packet field honest even if the process CWD is not the repo root.
- Make syntax failures explicit scanner evidence instead of route exceptions.

Claude feedback acted on:

- Claude verdict for 10.9CU: `pass`.
- Claude noted `ast.parse` was not guarded and could raise from the packet route.
- Claude noted the default `root="modules"` was CWD-relative and could soft-fail to `[]` if called outside the repo root.

What changed:

- `find_learning_influence_allow_consumed_callers()` now resolves relative scan roots from `agent_runtime.py`'s repo location.
- `_learning_influence_allow_consumed_callers_from_source()` now catches `SyntaxError` and returns a `:parse_error` marker.
- Tests prove the scanner remains clean after changing CWD to a temporary directory.
- Tests prove a syntactically invalid scanned file returns explicit parse-error evidence.
- Scope metadata moved to `10.9CV`.

Safety envelope:

- Scanner/test/packet hardening only.
- No consumer, no production `allow_consumed` caller, no prompt/route diff application, no prompt/routing/runtime change, no hidden POST or polling, no specialist dispatch, no specialist LLM/tool execution, no farm-data write, no public/customer output, no deploy, no Telegram, no physical control, and no financial action.

Verification:

- Focused audit suite: `326 OK`.
- `node --check static/js/oomSakkie.js` passed.
- Live-gated focused audit suite with `.env` loaded: `326 OK`.
- Browser behavior smoke passed.
- Full local unittest suite: `656 OK`.
- Live-gated focused audit suite with `.env` loaded: `326 OK`.
- Browser behavior smoke passed.
- Full local unittest suite: `656 OK`.
- GitHub Actions after commit `aaaa4a4`: `Oom Sakkie Browser Behavior` run `27345986022` success; `Oom Sakkie Audit Rails` run `27345985975` success.
- Live-gated focused audit suite with `.env` loaded: `326 OK`.
- Browser behavior smoke passed.
- Full local unittest suite: `656 OK`.
- GitHub Actions after commit `0db102a`: `Oom Sakkie Browser Behavior` run `27341856836` success; `Oom Sakkie Audit Rails` run `27341856819` success.

Next gate:

1. Run focused/full local verification, push, and confirm GitHub Actions.
2. Ask Claude to review 10.9CV before any learning proposal consumer implementation.

### 10.9CW Oom Sakkie Read-Only Consumer Design Agreement - Local Ready

Purpose:

- Act on Claude's 10.9CV pass feedback that the scanner thread is closed and the next useful checkpoint is consumer design review, not consumer implementation.
- Make the design-review agenda concrete in the existing read-only consumer design packet.
- Preserve the pre-consumer gate: no production `allow_consumed=True`, no consumer, no applyable diff.

Claude feedback acted on:

- Claude verdict for 10.9CV: `pass`.
- Claude said the substantive next step is owner + Claude consumer-design review: agree review-note artifact shape, `must_recheck_before_marker` enforcement, and rollback artifact contract.
- Claude explicitly said this is design, not code that consumes proposals.

What changed:

- `get_learning_influence_consumer_design_packet()` now includes `consumer_design_review_agreement`.
- The agreement sets `implementation_authorized_now = false` and `allow_consumed_true_authorized_now = false`.
- The agreement pins:
  - review-note artifact shape,
  - required source provenance,
  - forbidden patch/write/public-output fields,
  - ordered `must_recheck_before_marker` sequence,
  - failure behavior that writes no consumed marker,
  - rollback artifact contract,
  - future static-guard update requirement.
- Service and route tests pin the agreement and the no-authority posture.
- Scope metadata moved to `10.9CW`.

Safety envelope:

- Design/test/packet hardening only.
- No consumer, no production `allow_consumed` caller, no prompt/route diff application, no prompt/routing/runtime change, no hidden POST or polling, no specialist dispatch, no specialist LLM/tool execution, no farm-data write, no public/customer output, no deploy, no Telegram, no physical control, and no financial action.

Verification:

- Focused audit suite: `326 OK`.
- `node --check static/js/oomSakkie.js` passed.

Next gate:

1. Run focused/full local verification, push, and confirm GitHub Actions.
2. Ask Claude to review 10.9CW before any learning proposal consumer implementation.

### 10.9CX Oom Sakkie Consumed-Once Atomicity Wording - Local Ready

Purpose:

- Act on Claude's 10.9CW spec refinement before any consumer implementation.
- Make the future consumer contract explicit that the DB consumed-once partial unique index, not the step-5 read, is the atomic race guard.
- Preserve the pre-consumer gate: no production `allow_consumed=True`, no consumer, no applyable diff.

Claude feedback acted on:

- Claude verdict for 10.9CW: `pass`.
- Claude noted the TOCTOU window between verifying no prior `consumed_for_patch_proposal` marker and writing that marker.
- Claude recommended the agreement state that the DB consumed-once constraint is authoritative and unique-violation must return safely with no second artifact.

What changed:

- `consumer_design_review_agreement.must_recheck_before_marker_enforcement.atomicity_guard` now names `idx_oom_sakkie_learning_consumption_consumed_once`.
- `unique_violation_behavior` now requires returning `already_consumed` and producing no second review-note artifact.
- Service and route tests pin both fields.
- Scope metadata moved to `10.9CX`.

Safety envelope:

- Design/test/packet wording only.
- No consumer, no production `allow_consumed` caller, no prompt/route diff application, no prompt/routing/runtime change, no hidden POST or polling, no specialist dispatch, no specialist LLM/tool execution, no farm-data write, no public/customer output, no deploy, no Telegram, no physical control, and no financial action.

Verification:

- Focused audit suite: `326 OK`.
- `node --check static/js/oomSakkie.js` passed.

Next gate:

1. Run focused/full local verification, push, and confirm GitHub Actions.
2. Ask Claude to review 10.9CX before any learning proposal consumer implementation.

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
