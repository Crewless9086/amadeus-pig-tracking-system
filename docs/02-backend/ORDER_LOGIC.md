# Order Logic

## Purpose

Defines the intended and current backend order behavior.

## Layer Ownership

| Layer | Responsibility |
| --- | --- |
| Sam / `1.0` | Conversation, extracting customer intent, asking questions, and calling tools. |
| `1.2 - Order Steward` | Routes order actions from n8n to backend API. |
| Flask backend | Validates and executes order changes safely. |
| Google Sheets | Stores order, line, status, pig, and formula-derived views. |
| Web app / human | Approval, rejection, cancellation, overrides, completion, and manual fixes. |

## Draft Creation

A draft order should be created when the customer has provided enough useful order information.

Rules:

- Do not create duplicate active drafts for the same customer when an existing draft should be updated.
- Sam may help build the draft, but backend must generate and save the order.
- Draft creation should not imply approval, reservation, or guaranteed availability.

Current backend endpoint:

- `POST /api/master/orders`

## Draft Update / Enrichment

Draft updates may change allowed request fields such as quantity, category, weight band, sex, collection location, and notes.

Rules:

- Updates must identify the correct existing order.
- Empty or unsupported fields must not overwrite useful existing data.
- Sam should only tell the customer the draft was updated after backend success.

Current backend endpoint:

- `PATCH /api/master/orders/<order_id>`

## Requested Items And Split Lines

`requested_items[]` is the structured order-line request sent by n8n to backend sync.

Each item must have a stable `request_item_key`.

Example split request:

| Key | Meaning |
| --- | --- |
| `primary_1` | male pig request |
| `primary_2` | female pig request |

Rules:

- `primary_1` and `primary_2` must both be preserved.
- repeated syncs must not create duplicate active rows
- old lines must be released/cancelled before replacement when the request changes
- line totals should reflect what stock could actually be matched — see **Partial match sync** below
- mixed-sex customer requests should store `ORDER_MASTER.Requested_Sex = Any`; the exact split belongs on `ORDER_LINES` through `requested_items[]` (`primary_1`, `primary_2`, etc.)
- `intent_type` is only a validated caller/source label (`primary`, `addon`, `nearby_addon`, `extractor_slot`) and does not affect stock matching.
- `status` is only accepted as `active`; inactive requested items are not a backend sync feature and should be omitted by the caller.

## Partial/no-match sync

When available stock for a requested item is **greater than zero** but **less than** `requested_quantity`, the sync still creates one `ORDER_LINES` row per matched pig (up to availability). The response item includes:

| Field | Meaning |
| --- | --- |
| `match_status` | `partial_match` |
| `matched_quantity` | Count of pigs actually written to lines (fulfilled). |
| `available_quantity` | Count of candidate pigs matching category/weight/sex filters before allocation. |
| `created_line_count` | Lines created for that item. |
| `alternatives` | Same-category alternates for messaging. |

When a requested item has no matching sale-ready pigs, the response item uses `match_status: no_match`, `matched_quantity: 0`, and still returns same-category `alternatives` where available.

The aggregate API response separates technical success from business completeness:

| Field | Meaning |
| --- | --- |
| `success` | Backend sync call completed without processing errors. This can still be `true` for partial/no-match stock outcomes. |
| `complete_fulfillment` | `true` only when total matched quantity equals total requested quantity and no item is partial/no-match/error. |
| `partial_fulfillment` | `true` whenever the request is not completely fulfilled, including `partial_match` and `no_match`. |
| `fulfillment_status` | `complete`, `partial`, `no_match`, or `error`. |
| `requested_total`, `matched_total`, `unmatched_total` | Aggregate quantity counts across all requested items. |
| `incomplete_items` | Compact list of rows where matched quantity is below requested quantity, including alternatives. |

n8n/Sam must treat `complete_fulfillment`, not raw `success`, as the signal that the requested order lines are fully satisfied.

Other rules:

- `primary_1` and `primary_2` must both be preserved when used.
- repeated syncs must not create duplicate active rows
- old lines must be released/cancelled before replacement when the request changes

Known residual risk:

- split requested items have previously failed where `primary_2` rows were missing or not updated correctly.
- the issue appears to be backend sync/write logic rather than the n8n payload.

Current backend endpoint:

- `POST /api/master/orders/<order_id>/sync-lines`

## Reservation

Reservation should hold specific pigs for a valid active order.

Rules:

- only active valid order lines should be reserved
- cancelled, collected, or invalid lines should not become reserved
- reserved count on `ORDER_MASTER` must match reserved lines
- Sam must not promise reservation until backend confirms

**Eligible line criteria (Phase 1.6):**

| Condition | Result |
| --- | --- |
| `Line_Status` is `Cancelled` or `Collected` | skipped — terminal state, never modified |
| `Pig_ID` is empty | skipped — placeholder line, cannot hold inventory |
| `Reserved_Status = Reserved` AND `Line_Status = Reserved` | noop — already correct, idempotent |
| All other active lines with a `Pig_ID` | reserved — `Line_Status` and `Reserved_Status` both set to `Reserved` |

**Line_Status values:**
- `Draft` — default after creation
- `Reserved` — line is reserved
- `Collected` — terminal, line has been collected (set by `complete_order`)
- `Cancelled` — terminal, line has been soft-cancelled

**Reserved_Status values:**
- `Not_Reserved` — default
- `Reserved` — currently reserved
- `Collected` — set by `complete_order` alongside `Line_Status = Collected`

**Response semantics:**
- `success = true` when at least one line is or was already reserved
- `success = false` when nothing could be reserved (all skipped — 422 HTTP status)
- `warning` is present when `success = true` but some lines were skipped
- `line_results` lists every line belonging to the order with its outcome (`reserved`, `noop`, `skipped`)
- `changed_count` = rows written to `ORDER_LINES` in the batch call

All `ORDER_LINES` updates are applied in a single `batch_update_rows_by_id` call — no partial silent failure on multi-line orders.

Current backend behavior:

- `POST /api/orders/<order_id>/reserve` marks matching `ORDER_LINES` as reserved and updates `ORDER_MASTER.Reserved_Pig_Count`.
- It does not directly write formula sheets.

## Release

Release frees reserved order lines and makes pigs available again through the sheet/formula chain.

Release must happen when:

- an order is rejected
- a customer cancels
- an order line is removed
- requested items change and old lines no longer match
- an order expires or is abandoned
- payment fails or is not received in the agreed window
- a human manually releases the order
- an order is changed back from reserved/approved to draft

Hard rule:

A pig must never stay reserved if the order is no longer active or valid.

**Release rules (Phase 1.6):**

| Line state | Result |
| --- | --- |
| `Line_Status = Collected` | skipped — terminal state, never modified |
| `Reserved_Status != Reserved` AND `Line_Status != Reserved` | noop — nothing to release |
| `Reserved_Status = Reserved` | cleared to `Not_Reserved` |
| `Line_Status = Reserved` (active non-cancelled line) | reverted to `Draft` |
| `Line_Status = Cancelled` with `Reserved_Status = Reserved` | `Reserved_Status` cleared; `Line_Status` kept as `Cancelled` |

**Idempotent:** calling release twice is safe. Second call returns all noops with `success = true` and `changed_count = 0`.

`ORDER_MASTER.Reserved_Pig_Count` is set to the actual post-release count (not a blind `0`).

All `ORDER_LINES` updates are applied in a single `batch_update_rows_by_id` call.

Current backend behavior:

- `POST /api/orders/<order_id>/release` sets reserved lines back to not reserved and resets `ORDER_MASTER.Reserved_Pig_Count`.
- `reject_order()` now performs rejection-specific cleanup by cancelling linked non-cancelled/non-collected lines, setting their `Reserved_Status` to `Not_Reserved`, and resetting `ORDER_MASTER.Reserved_Pig_Count` to `0`.

## Rejection

Approved intended behavior:

- `ORDER_MASTER.Order_Status` should change to `Cancelled` or `Rejected`.
- Current preferred backend-compatible expression is `Order_Status = Cancelled` and `Approval_Status = Rejected`.
- All reserved `ORDER_LINES` linked to the order must be released.
- `ORDER_LINES.Reserved_Status` should change back to `Not_Reserved` / available equivalent.
- Lines that should no longer continue should be marked `Cancelled`.
- `ORDER_STATUS_LOG` must record the change.
- Sam must not say the order is approved or reserved.
- Sam should send a polite message explaining that the order cannot proceed, ideally with a human-approved reason if needed.

Current backend behavior:

- `reject_order()` blocks completed orders from being rejected.
- It cancels linked non-cancelled/non-collected order lines.
- It sets linked line `Reserved_Status` values to `Not_Reserved`.
- It resets `ORDER_MASTER.Reserved_Pig_Count` to `0`.
- It writes `ORDER_STATUS_LOG` when rejection or cleanup changes state.

## Customer Cancellation

Approved intended behavior:

- order should be marked `Cancelled`
- linked order lines should be cancelled or released
- reserved pigs must become available again
- `ORDER_STATUS_LOG` must record customer cancellation
- Sam should confirm cancellation politely
- no further follow-up should happen unless the customer asks again later

Suggested statuses:

- `Order_Status = Cancelled`
- `Approval_Status = Not_Required`
- `Payment_Status = Cancelled`

Current backend behavior:

- `cancel_order()` provides a dedicated customer cancellation action.
- It blocks completed orders from being cancelled.
- It does not convert already rejected orders into customer-cancelled orders.
- It sets `Order_Status = Cancelled` and `Approval_Status = Not_Required`.
- It sets `Payment_Status = Cancelled`.
- It cancels linked non-cancelled/non-collected order lines.
- It sets linked line `Reserved_Status` values to `Not_Reserved`.
- It resets `ORDER_MASTER.Reserved_Pig_Count` to `0`.
- It writes `ORDER_STATUS_LOG` when cancellation or cleanup changes state.

## Approval

Approval is a human/web-app controlled action.

Rules:

- Sam should not directly approve risky or unclear orders without backend/human confirmation.
- Approval should only happen after order lines, quantities, pricing, and reservation state are valid.

Current backend endpoint:

- `POST /api/orders/<order_id>/approve`

Current backend behavior:

- `approve_order()` only allows approval when `Order_Status = Pending_Approval`.
- Draft, Approved, Cancelled, and Completed orders are rejected by the approval endpoint.
- Approval updates `ORDER_MASTER` to `Order_Status = Approved` and `Approval_Status = Approved` first.
- After approval is written, backend attempts to reserve eligible active order lines using the same hardened reservation rules as `POST /api/orders/<order_id>/reserve`.
- If reservation fails or partially fails, approval is not rolled back. Backend returns `reserve_warning`, keeps any `auto_reserve.line_results`, and writes an `ORDER_STATUS_LOG` follow-up warning for manual admin action.
- After the approval and reservation attempt, backend calls `ORDER_NOTIFICATION_WEBHOOK_URL` with `event_type = order_approved`, `ConversationId`, and the agreed customer message text. Notification failure does not roll back approval.

Rejection notification:

- `reject_order()` cancels/release linked active lines, updates the order to `Cancelled | Rejected`, then calls `ORDER_NOTIFICATION_WEBHOOK_URL` with `event_type = order_rejected`, `ConversationId`, and the agreed rejection message text.
- Notification failure is returned as `notification_warning` and written to `ORDER_STATUS_LOG` for manual follow-up.

## Completion / Collection

Completion should represent final collection/sale outcome.

Rules:

- collected lines should be marked final
- pigs should be updated as sold/exited where appropriate
- status log should record completion

Current backend endpoint:

- `POST /api/orders/<order_id>/complete`

## Sam vs Web App Responsibilities

Sam may:

- create draft orders
- update/enrich draft orders
- sync requested order lines
- ask missing details
- request order review
- ask Order Steward/backend to review, approve, reject, or cancel when supported
- confirm customer cancellation intent
- send customer-facing updates only after backend truth is confirmed

Web app/humans may:

- view all orders
- view full order detail
- manually add/remove/edit order lines
- reserve and release pigs
- approve, reject, and cancel orders
- mark payment status
- mark collection/completion
- edit collection details
- override or fix data manually
- view logs and history

Simple rule:

Sam handles conversation and draft-building. The web app handles human control, approval, overrides, and final operational actions.
