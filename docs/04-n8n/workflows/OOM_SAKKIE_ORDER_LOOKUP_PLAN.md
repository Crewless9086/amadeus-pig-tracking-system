# Oom Sakkie Order And Document Lookup Plan

## Purpose

Phase 7.3 planning for letting Oom Sakkie answer internal operator questions about orders and documents without opening the web app or Google Sheets.

Status: 7.3A and 7.3B complete; 7.3C read-only Oom Sakkie lookup is implemented and live-verified. Future document-send behavior remains planning-only until explicitly approved.

## Live Workflow Baseline

Imported from n8n on 2026-05-18:

| Workflow | ID | Status | Current role |
| --- | --- | --- | --- |
| `2 - The GateKeeper` | `yt4qc1kP5riAfLfL` | Active | Single Telegram entry point for Oom Sakkie messages and button callbacks. |
| `2.0 - OOM SAKKIE - Amadeus Assistant Agent` | `6UscGE44eTfdLp1A` | Active | Main Oom Sakkie Telegram assistant. |
| `2.1 - Amadeus Weather Sub-Agent` | `L4c34rFmN0kUJvWc` | Active | Weather sub-agent tool. |
| `2.1.1 - Amadeus Forecast Tool` | `vx1lV8aFCG28KSIN` | Active | Forecast utility workflow. |
| `2.2 - Amadeus Sunsynk Sub-Agent` | `tKVKoCcxhT7CAydT` | Active | Solar/power sub-agent tool. |
| `2.3.1 - Build Daily Irrigation Plan` | `UNwNmx0TwtFf8mjo` | Active | Scheduled irrigation planning. |
| `2.3.2 - Run Irrigation Controller` | `f6oPLsaolGH4pMKC` | Inactive | Scheduled irrigation valve controller. |
| `2.4 - Amadeus Orders Sub Agent` | `T8LLCAtYDLNRPoRx` | Active | Internal order approval sub-agent. |
| `2.4.1 - Test Caller` | `GwWZueB0iyonpscl` | Inactive | Manual orders sub-agent test caller. |
| `2.4.2 - Orders Approval Callback Handler` | `wmsgzHNywC6okTuI` | Inactive | Legacy callback handler; callback routing moved into GateKeeper to avoid Telegram webhook conflicts. |
| `2.4.3 - Order Approval Request Webhook` | `k4XVMoJ1hK09PIvT` | Active | Approval request webhook. |
| `ALERT - Local Weather Station` | `g0ajlm9gBp7J72Jn` | Removed | Historical scheduled weather station alerts; replaced by backend-driven `ALERT - Weather Backend Delivery`. |
| `ALERT - Sunsynk` | `2LETWzde7lMDlMnl` | Removed | Historical scheduled solar/power alerts; replaced by backend-driven `ALERT - Power Backend Delivery`. |
| `ALERT - Weather Forecast` | `I4D76Gb9ddGFhSP5` | Removed | Historical scheduled forecast alerts; replaced by backend-driven `ALERT - Weather Backend Delivery`. |

Planning correction:

- Oom Sakkie is already live and in use.
- Phase 7.3 must build around the existing `2.#` workflow suite, especially `2 - The GateKeeper`, `2.0`, and `2.4`.
- Do not introduce a replacement Oom Sakkie workflow unless the owner explicitly approves that later.

## Current Decision

- Oom Sakkie is an internal operator assistant, not a customer-facing sales agent.
- Oom Sakkie should use backend APIs and/or the Order Steward workflow for order truth.
- Oom Sakkie must not read Google Sheets directly.
- Read-only lookup comes first.
- Sending customer documents is allowed only through existing backend document-send endpoints and only after an explicit operator instruction.
- Oom Sakkie should not mutate order lifecycle state in this phase.
- Existing approval behavior in `2.4` must remain intact while lookup is added.
- The first likely integration point is adding a read-only order lookup tool/sub-action around `2.4`, then exposing it to `2.0` only after it is tested.

## Scope

### In Scope For 7.3

- Look up orders by:
  - exact `order_id`
  - customer phone number
  - customer name
  - current/known Chatwoot conversation ID if available
- Summarize one order for an operator:
  - order status
  - approval status
  - payment status
  - payment method
  - customer name and phone
  - collection location/date
  - active line summary
  - cancelled line count where relevant
  - totals
  - notes
  - outstanding actions
- Show quote/invoice document records for an order:
  - document type
  - document reference
  - document status
  - version
  - total
  - created/sent timestamps
  - sent by
  - Google Drive URL for internal lookup when safe
- Ask one disambiguation question when multiple orders match.
- Provide internal operator-safe wording.

### Out Of Scope For 7.3

- Creating orders.
- Updating orders.
- Cancelling, approving, rejecting, reserving, releasing, or completing orders.
- Generating new quotes/invoices unless a later 7.3 sub-slice explicitly adds it.
- Sending documents to a customer without a clear operator confirmation.
- Replacing the web app order page.
- Database/Postgres migration work.

## Existing Backend Surface

Use what already exists before adding new endpoints.

| Need | Existing support | Notes |
| --- | --- | --- |
| Exact order lookup | `GET /api/orders/<order_id>` | Returns `order`, `lines`, and serialized `documents`. Good first implementation target. |
| Active order lookup | `GET /api/orders/active-customer-context` | Supports `order_id`, `conversation_id`, and `customer_phone`; only returns active review orders. |
| Order list/search base | `GET /api/orders` | Returns all order summaries. Could support name/phone search initially, but a narrower backend search endpoint may be cleaner later. |
| Send latest quote | `POST /api/orders/<order_id>/quote/send-latest` | Existing customer-facing delivery path. Must require explicit operator instruction and destination conversation ID. |
| Send specific document | `POST /api/order-documents/<document_id>/send` | Existing backend-owned delivery path through workflow `1.5`. Must not be called from vague lookup requests. |

## Recommended Backend Additions

7.3 can start without new backend endpoints if Oom Sakkie only does exact `order_id` lookups.

Recommended before broader operator use:

### `GET /api/orders/search`

Purpose:

- Provide a controlled search endpoint for Oom Sakkie and future web app search.

Detailed backend contract:

- `docs/02-backend/API_STRUCTURE.md` section `Planned Oom Sakkie Order Search Contract (Phase 7.3)`.

Suggested query parameters:

- `order_id`
- `customer_phone`
- `customer_name`
- `conversation_id`
- `status_scope = active | history | all`
- `limit`

Suggested behavior:

- Exact `order_id` wins when present.
- Phone lookup should normalize digits.
- Name lookup should be partial but conservative.
- Default `status_scope` should be `active`.
- Return compact matches only, not full raw rows.
- If one exact match exists, include a compact detail summary or a `detail_url`/`order_id` for follow-up detail fetch.

### `GET /api/orders/<order_id>/operator-summary`

Purpose:

- Return a compact, internal-safe order summary for Oom Sakkie.

Reason:

- `GET /api/orders/<order_id>` is useful, but it returns enough raw detail that each workflow would need its own formatter. A backend-owned summary keeps Oom Sakkie stable and reduces prompt/workflow drift.

Suggested output:

- `success`
- `lookup_status`
- `order_summary`
- `line_summary`
- `document_summary`
- `outstanding_actions`
- `safe_document_actions`

Detailed backend contract:

- `docs/02-backend/API_STRUCTURE.md` section `Planned Oom Sakkie Operator Summary Contract (Phase 7.3)`.

## Oom Sakkie Actions

Recommended action set:

| Action | Type | Input | Output | Safety |
| --- | --- | --- | --- | --- |
| `find_order` | read-only | `order_id`, `customer_phone`, `customer_name`, `conversation_id`, `status_scope` | match list or one match | Multiple matches must ask one disambiguation question. |
| `get_order_summary` | read-only | `order_id` | compact order/operator summary | Must use backend-confirmed data. |
| `get_order_documents` | read-only | `order_id` | quote/invoice document list | Internal links allowed only for operators. |
| `prepare_document_send` | confirmation step | `document_id` or latest quote + target conversation | confirmation wording | Does not send. Asks operator to confirm. |
| `send_document` | explicit action | `document_id`, `conversation_id`, `sent_by` | backend send result | Only after explicit confirmation. |

Do not add write actions like `cancel_order`, `approve_order`, or `reserve_order` in 7.3. Those remain web app / existing controlled workflow actions.

## Disambiguation Rules

When multiple orders match:

- Show up to five compact matches.
- Include:
  - order ID
  - customer name
  - order date
  - order status
  - payment status
  - active line count
  - collection location/date
- Ask one clear question, for example:
  - "I found three orders for that customer. Which one should I open: ORD-..., ORD-..., or ORD-...?"
- Do not guess based on newest order if the operator asked by name/phone and multiple active orders exist.

When no order matches:

- Say no matching order was found.
- Ask for one better identifier:
  - order ID
  - phone number
  - customer name

## Document Safety Rules

- Lookup requests may show document records.
- Lookup requests must not send a document.
- Sending requires a clear operator action such as:
  - "Send quote Q-... to conversation 1774"
  - "Send the latest quote for ORD-... to the customer"
- If the destination conversation is missing, ask for it or use only a backend-confirmed active customer conversation.
- Never send a document to a test conversation unless the operator explicitly says it is a test.
- Never expose raw webhook payloads, Drive internals, or backend debug details in the operator reply.
- If a document is `Voided`, do not send it.
- If several generated documents exist, prefer the latest non-voided quote/invoice only when the operator asked for "latest"; otherwise ask which document.

## Operator Reply Shape

Oom Sakkie should answer with compact operational wording.

Example order summary:

```text
Order ORD-2026-123456 is Draft / Not Required.
Customer: Charl N, 084...
Items: 1 x Female Grower 35_to_39_Kg at R1,400
Total: R1,400
Payment: Cash, status Pending
Collection: Riversdale, date not set
Documents: Quote Q-2026-123456 generated, not sent
Outstanding: send for approval once details are confirmed.
```

Avoid:

- raw JSON
- sheet names unless diagnosing with the operator
- long line-by-line dumps
- customer-facing sales wording

## Suggested 7.3 Work Slices

### 7.3A Planning And Contract

- Accept this plan or revise it. - In progress.
- Review the imported live `2.#` workflow READMEs. - Done.
- Confirm whether `2.4` should own both approval and read-only lookup, or whether lookup should become a new `2.4.x` helper workflow. - Owner decision after safety review: create separate `2.4.4 - Order Lookup Tool`.
- Decide whether the first implementation uses existing endpoints only or adds `GET /api/orders/search` first. - Recommended: add backend search/summary first so matching stays backend-owned.
- Decide whether document links are shown to operators or only document refs/statuses are shown. - Recommended: show refs/statuses first; add links only after operator access rules are clearer.

## Recommended 7.3A Direction

Use a new `2.4.4 - Order Lookup Tool` as the read-only order lookup tool for Oom Sakkie.

Recommended decisions before implementation:

- Add backend-owned search/summary support before workflow changes:
  - `GET /api/orders/search`
  - `GET /api/orders/<order_id>/operator-summary`
- Keep name/phone matching in the backend, not in n8n Code nodes.
- Expose order lookup through the existing Telegram Oom Sakkie route:
  - `2 - The GateKeeper`
  - `2.0 - OOM SAKKIE - Amadeus Assistant Agent`
  - `2.4.4 - Order Lookup Tool`
- Keep `2.4` approval behavior untouched. It remains the approval/request/callback workflow.
- In the first live version, show document refs, document status, versions, totals, and sent state. Do not show raw Google Drive URLs by default.
- Keep invoice sending future-only until quote lookup/send behavior is proven.
- Keep document sending out of the first read-only lookup slice.

Recommended first action set inside `2.4.4`:

| Action | Backend path | Purpose |
| --- | --- | --- |
| `find_order` | `GET /api/orders/search` | Find compact matches by order ID, phone, name, or conversation ID. |
| `get_order_summary` | `GET /api/orders/<order_id>/operator-summary` | Return one compact internal order summary. |
| `get_order_documents` | `GET /api/orders/<order_id>/operator-summary` document section | Return quote/invoice records for the order. |

Do not add these actions to approval callback paths. They should be callable from the Oom Sakkie assistant path, not from arbitrary Telegram callback commands.

### 7.3B Backend Search/Summary

- Add backend search/summary endpoint first unless owner redirects. - Done locally.
- Add tests for exact order, phone, name, multiple matches, no match, and document summary. - Done locally.
- Keep existing `/api/orders/<order_id>` unchanged unless a bug is found.

Implemented locally:

- `GET /api/orders/search`
- `GET /api/orders/<order_id>/operator-summary`
- Search and summary logic live in `modules/orders/order_read.py`.
- Routes are exposed from `modules/orders/order_routes.py`.
- Existing `/api/orders/<order_id>` behavior is unchanged.
- First slice does not return Google Drive URLs and does not send documents.
- Full local test suite passed with 82 tests.

Production smoke:

- Backend deployed and ready on 2026-05-18.
- `GET /api/orders/search` without an identifier returned expected `400`.
- `GET /api/orders/search?customer_name=Charl%20N&status_scope=all&limit=3` returned compact multiple matches.
- `GET /api/orders/ORD-2026-3E46B8/operator-summary` returned compact order/document/outstanding-action data.
- Operator summary did not return Google Drive URLs.

### 7.3C Oom Sakkie Workflow - Complete And Live-Verified

- Create the new `2.4.4 - Order Lookup Tool` workflow export and import it to n8n. - Done.
- Update the existing Oom Sakkie workflow docs/export. Do not replace the live `2.0` workflow.
- Add read-only actions first:
  - `find_order`
  - `get_order_summary`
  - `get_order_documents`
- Do not add send actions until read-only lookup is verified.

Implemented 2026-05-18:

- New n8n workflow created: `2.4.4 - Order Lookup Tool`.
- n8n workflow ID: `1VNdetSbgP0ffNyH`.
- Local export: `docs/04-n8n/workflows/2.4.4 - Order Lookup Tool/workflow.json`.
- Current n8n status: active and wired into `2.0`.
- `2.4 - Amadeus Orders Sub Agent` was not changed.
- Read-only branches added:
  - `find_order`
  - `get_order_summary`
  - `get_order_documents`
- No Telegram, Chatwoot, approval, cancellation, reservation, release, completion, generation, or document-send nodes were added.

Planned workflow wiring:

1. Add a third tool to `2.0 - OOM SAKKIE - Amadeus Assistant Agent`:
   - Tool name: `Orders_Info_Tool`
   - Target workflow: `2.4.4 - Order Lookup Tool`
   - Tool input: the operator's raw message in `input`.
2. Update the `2.0` assistant prompt so it routes order/document lookup questions to `Orders_Info_Tool`.
3. Keep `2 - The GateKeeper` unchanged.
4. Keep `2.4` approval branches unchanged:
   - `request_order_approval`
   - `process_order_approval_reply`
   - `invalid_callback`
5. Add separate read-only action routes in new `2.4.4`:
   - `find_order`
   - `get_order_summary`
   - `get_order_documents`
6. Do not connect lookup actions to Telegram approval callback parsing.
7. Do not add document-send actions in this slice.

Local 7.3C wiring update:

- `2.0` now has an `Orders_Info_Tool` node pointing to `1VNdetSbgP0ffNyH`.
- `2.0` assistant prompt now lists three tools: weather, Sunsynk, and read-only order lookup.
- `2.4.4` normalize logic now accepts either structured fields or raw `input` from Oom Sakkie.
- `2.4.4` can infer simple order IDs, phone numbers, conversation IDs, customer names, and lookup intent from raw text.

n8n upload status:

- `2.4.4 - Order Lookup Tool` uploaded and read back from n8n on 2026-05-18.
- Live `2.0` was updated through the n8n UI and read back on 2026-05-18.
- The same `500` occurred when attempting to PUT the unchanged live `2.0` export, so this is not caused by the new order tool node.
- `2.4.4` was activated after adding required workflow input declarations to the trigger.
- Telegram routing issue found and fixed on 2026-05-18:
  - General Oom Sakkie Telegram messages were being captured by `2.4 - Amadeus Orders Sub Agent`.
  - `2.4` then dropped them because they were not manual `approve ...` or `reject ...` commands.
  - Disabled `2.4`'s normal-message Telegram trigger.
  - Refreshed `2 - The GateKeeper` activation so it owns normal Telegram `message` updates.
  - Superseded by the 2026-05-19 Path A recovery: GateKeeper now owns both normal messages and button callbacks; `2.4.2 - Orders Approval Callback Handler` is retired from the live path.
- Exact order lookup live smoke passed on 2026-05-18:
  - Operator sent `Hi`; Oom Sakkie replied through the GateKeeper -> `2.0` path.
  - Operator sent `Show me order ORD-2026-3E46B8`.
  - Oom Sakkie returned the cancelled order summary, no active items, payment status, collection location, quote reference, and closed-order status.
- Document lookup live smoke passed:
  - Operator sent `What documents are on order ORD-2026-3E46B8?`.
  - Oom Sakkie returned quote `Q-2026-3E46B8`, generated status, total `R1400`, and valid-until date.
- Name search/disambiguation live smoke passed:
  - Operator sent `Find order for Charl N`.
  - Oom Sakkie returned multiple matching active/draft orders and asked the operator to choose one order ID.
- Phone search no-match live smoke passed:
  - Operator sent `Find orders for 0645087806`.
  - Oom Sakkie returned no matching active orders.
- Follow-up note:
  - Current phone/name search defaults to `status_scope=active`.
  - This is correct for first-pass operator lookup, but later Oom Sakkie should support explicit historical/all-status wording such as `search all orders for 064...` or `find old/cancelled/completed orders for this phone`.
  - Keep this as a later narrow enhancement; do not expand the current read-only slice unless operator use shows it is needed immediately.
- 7.3C status: complete and live-verified.
- Next action: plan 7.3D document-send guard before adding any send behavior.

Planned `2.4.4` branch shape:

| Action | Route | Backend endpoint | Formatter |
| --- | --- | --- | --- |
| `find_order` | Switch output `Find Order` | `GET /api/orders/search` | Compact match list / disambiguation result. |
| `get_order_summary` | Switch output `Get Order Summary` | `GET /api/orders/<order_id>/operator-summary` | Compact order + line + action summary. |
| `get_order_documents` | Switch output `Get Order Documents` | `GET /api/orders/<order_id>/operator-summary` | Compact document list only. |

Planned `2.4.4` input fields:

| Field | Required | Used by |
| --- | --- | --- |
| `action` | yes | All branches. |
| `order_id` | no | Exact lookup, summary, documents. |
| `customer_phone` | no | Search. |
| `customer_name` | no | Search. |
| `conversation_id` | no | Search. |
| `status_scope` | no | Search; default `active`. |
| `limit` | no | Search; default `5`. |
| `changed_by` | no | Trace field only; no write action in this slice. |

Planned response fields back to `2.0`:

| Field | Notes |
| --- | --- |
| `success` | Boolean success of lookup call. |
| `action` | Echoes lookup action. |
| `lookup_status` | `single_match`, `multiple_matches`, `no_match`, `terminal_order`, or `error`. |
| `message` | Operator-safe summary/disambiguation text. |
| `matches` | Compact matches for `find_order`. |
| `order_summary` | Compact order facts for summary/doc lookup. |
| `line_summary` | Grouped active line data. |
| `document_summary` | Quote/invoice records without Drive URLs. |
| `outstanding_actions` | Backend-owned action hints. |

### 7.3D Document Send Guard - Planning Next

- Add explicit confirmation path for document send.
- Verify it calls backend send endpoints, not workflow-to-Chatwoot directly.
- Test only with a safe test conversation.
- Use Telegram buttons where they reduce operator effort, similar to the approval workflow.

Planning rule:

- Do not implement document sending until the confirmation wording, destination checks, document eligibility checks, and backend endpoint path are reviewed.
- Keep `2.4.4` read-only unless 7.3D explicitly approves a new action.

Current backend facts:

- Existing endpoint `POST /api/order-documents/<document_id>/send` sends a specific existing document.
- Existing endpoint `POST /api/orders/<order_id>/quote/send-latest` finds or creates the latest quote if quote-ready, then sends it.
- Both send paths require explicit `conversation_id`; the backend intentionally does not silently fall back to the customer conversation.
- Existing delivery path goes through backend -> `DOCUMENT_DELIVERY_WEBHOOK_URL` -> `1.5 - Outbound Document Delivery` -> Chatwoot attachment.
- Existing backend blocks voided documents and recently-sent duplicate sends.

Recommended 7.3D backend additions before workflow send buttons:

### `POST /api/orders/<order_id>/quote/prepare-send`

Purpose:

- Return a safe Telegram-button payload for sending the latest quote.
- Do not send anything.
- Do not generate a new quote unless explicitly approved during implementation; first recommendation is prepare existing latest non-voided quote only.

Suggested request:

```json
{
  "conversation_id": "1774",
  "requested_by": "Oom Sakkie"
}
```

Suggested response:

```json
{
  "success": true,
  "action": "prepare_latest_quote_send",
  "order_id": "ORD-2026-3E46B8",
  "customer_name": "Charl N",
  "destination": {
    "conversation_id": "1774",
    "source": "operator_input_or_order_record",
    "confirmed": true
  },
  "document": {
    "document_id": "DOC-...",
    "document_type": "Quote",
    "document_ref": "Q-2026-3E46B8",
    "document_status": "Generated",
    "total": 1400,
    "valid_until": "2026-05-20"
  },
  "button_context": {
    "send_label": "Send quote to customer",
    "cancel_label": "Cancel",
    "callback_action": "send_latest_quote_confirmed"
  },
  "message": "Quote Q-... is ready for Charl N. Total R1400. Send it to the customer?"
}
```

Suggested backend guard checks:

- Order exists.
- Customer/destination conversation is present and confirmed.
- Latest quote exists and is not voided.
- Quote belongs to the order.
- Quote is not stale/replaced by a newer generated quote.
- Document type is `Quote`; invoice sending remains future-only unless explicitly approved.
- Return an unsafe result instead of guessing if multiple destinations or missing destination data exist.

Implementation status:

- Implemented locally in `modules/orders/order_routes.py`.
- Tests added in `tests/test_order_routes.py`.
- Focused route test suite passed.
- The endpoint does not call `send_order_document`, n8n, or Chatwoot.
- It returns explicit `button_context` for the later Telegram callback slice.

### `POST /api/orders/<order_id>/quote/send-latest-confirmed`

Purpose:

- Backend-owned final send endpoint for the Telegram button callback.
- Re-check all prepare-send safety rules at click time.
- Then call the existing send path only if still safe.

Suggested request:

```json
{
  "document_id": "DOC-...",
  "conversation_id": "1774",
  "sent_by": "Oom Sakkie",
  "confirmation_source": "telegram_button",
  "telegram_user_id": "..."
}
```

Suggested behavior:

- Re-fetch order and latest non-voided quote.
- Refuse if `document_id` is no longer the latest sendable quote.
- Refuse if conversation ID is missing or no longer trusted.
- Call `send_order_document(...)` only after all checks pass.
- Return compact success/failure for Telegram.

Implementation status:

- Implemented locally in `modules/orders/order_routes.py`.
- Tests added in `tests/test_order_routes.py`.
- Focused route test suite passed.
- Re-checks order existence, required `document_id`, required `conversation_id`, latest quote existence, selected document ID, document type, and voided/superseded status before calling `send_order_document`.
- Returns `502` if the delivery workflow does not confirm a send.
- Existing `send_order_document` still owns n8n/Chatwoot delivery and sent-status marking.

Recommended Telegram button pattern:

- Oom Sakkie can present operator buttons after a document lookup or prepare-send step.
- Buttons should be used for clear, bounded decisions such as:
  - `Send latest quote`
  - `Choose quote Q-...`
  - `Cancel`
  - `Open order summary`
- Buttons must carry enough callback data to identify:
  - action
  - order ID
  - document ID or document ref
  - destination conversation/customer context when available
- Buttons must route through a dedicated callback handler, not through the general lookup prompt.
- Button callbacks must still call backend-owned send endpoints and must not send directly to Chatwoot.
- Button clicks must re-check document eligibility and destination safety at execution time.
- If the callback data is stale, missing, or ambiguous, Oom Sakkie should ask the operator to prepare the send again instead of guessing.
- Approval buttons remain separate from document-send buttons.

Recommended first button flow:

1. Operator asks: `What documents are on order ORD-... ?`
2. Oom Sakkie lists documents and shows buttons:
   - `Send latest quote`
   - `Cancel`
3. Operator clicks `Send latest quote`.
4. Oom Sakkie/backend verifies:
   - order exists
   - latest quote is non-voided
   - destination conversation/customer is backend-confirmed
   - send is allowed for this document type/status
5. Oom Sakkie asks one final confirmation or sends only if the clicked button wording is explicitly final enough.
6. Backend sends through existing document delivery endpoint/workflow.

Recommended workflow shape:

| Workflow | Change | Purpose |
| --- | --- | --- |
| `2.0 - OOM SAKKIE - Amadeus Assistant Agent` | No direct send action. It can ask `2.4.4` to prepare document send. | Keep the assistant conversational and avoid direct delivery logic. |
| `2.4.4 - Order Lookup Tool` | Add `prepare_latest_quote_send` only after backend prepare endpoint exists. | Return Telegram-ready context/buttons, but do not send. |
| New `2.4.5 - Document Send Callback Handler` or similar | Execute-workflow worker for document-send button callbacks. | Keep document-send logic separate from approval decisions without creating a second active Telegram callback trigger. |
| `1.5 - Outbound Document Delivery` | No change expected. | Existing backend-triggered Chatwoot attachment delivery remains the delivery path. |

Recommended callback data:

```text
quote_send|ORD-2026-3E46B8|DOC-...|1774
quote_cancel|ORD-2026-3E46B8|DOC-...
```

Callback rules:

- Keep callback data short enough for Telegram limits.
- If callback data cannot include all fields safely, store a short pending-send token in backend state instead of overloading callback data.
- Do not reuse approval callback prefixes like `approve_` or `reject_`.
- Do not add a second active Telegram `callback_query` trigger for the same Oom Sakkie bot.
- Route document-send callbacks from the existing callback entry point into `2.4.5` so Telegram callback ownership remains single-entry.

Workflow implementation status:

- Local `2.0` export now passes Telegram chat/user context into `Orders_Info_Tool`.
- `2.4.4` is active in n8n and supports `prepare_latest_quote_send`, calling the backend prepare endpoint and sending operator-only Telegram confirmation buttons.
- `2.4.5 - Document Send Callback Handler` is active in n8n as workflow `8b14lAqmyrD0LYZz`.
- `2.4.2` is retired from the live path. GateKeeper now owns `callback_query` updates and routes `quote_send|...` and `quote_cancel|...` callbacks to `2.4.5`.
- `2.0` was manually imported/updated through the n8n UI by the owner on 2026-05-18.
- n8n API verification confirms live `2.0` now passes `telegram_chat_id` and `telegram_user_id` into `Orders_Info_Tool`.
- n8n API verification confirms `2.4.5 - Document Send Callback Handler` exists as workflow `8b14lAqmyrD0LYZz` and is active.
- Claude review accepted Path A: keep GateKeeper as the single Oom Sakkie Telegram router, do not build Router V2, do not move callbacks into `2.0`, and retire `2.4.2` from the live path. Detailed plan: `docs/04-n8n/OOM_SAKKIE_ROUTING_ARCHITECTURE_PLAN.md`.
- 2026-05-19 live recovery completed: owner manually uploaded the cleaned GateKeeper workflow and replaced the Telegram Trigger node; `Hi` routed through GateKeeper to `2.0`, and Oom Sakkie replied.
- Repo export refreshed from live n8n GateKeeper workflow `s8QaxmqT69Z5mhvE`, so the current trigger node is preserved in `docs/04-n8n/workflows/2 - The GateKeeper/workflow.json`.
- Recovery checklist retained for future incidents: `docs/04-n8n/OOM_SAKKIE_MANUAL_RECOVERY_CHECKLIST.md`.

Open planning question:

- Decision: use a one-button send flow after Oom Sakkie has shown enough context.
- The send button must be explicit, for example `Send quote to customer`, not a vague `Send`.
- Always include a nearby `Cancel` button.
- The button message should show:
  - order ID
  - document ref
  - document type
  - customer/destination
  - total
- The button callback must re-check backend safety at click time:
  - latest/non-voided quote
  - correct order
  - backend-confirmed customer conversation
  - document has not been voided or replaced
- If anything changed, refuse to send and ask the operator to refresh the order/document lookup.

### 7.3E Live Verification

- `2.0 - OOM SAKKIE - Amadeus Assistant Agent` has been imported/updated through the n8n UI.
- GateKeeper first live message test passed on 2026-05-19: `Hi` routed through GateKeeper to `2.0`, and Oom Sakkie replied.
- If routing fails again, Test 0 is Telegram `getWebhookInfo`; it must show GateKeeper's webhook URL, not an empty URL and not the old `2.4.2` webhook ID.
- Quote-send preparation test on 2026-05-19 reached `2.4.4`, called the backend prepare endpoint, and displayed Telegram confirmation buttons.
- `Cancel` button test passed on 2026-05-19: GateKeeper routed the callback to `2.4.5`, which returned `Quote send cancelled`; backend document status remained `Generated` with blank sent fields.
- Duplicate prepare acknowledgement fixed in live `2.0`: `2.4.4` sends the direct button message, then `2.0` suppresses the follow-up AI acknowledgement when output contains the quote-send preparation pattern.
- Safety issue found during the cancelled-order test: backend prepare allowed a quote-send button for terminal order `ORD-2026-3E46B8`. Backend guard is now deployed and blocks terminal orders for both prepare and confirmed-send.
- Tool-skip issue found on repeated prepare requests: `2.0` answered from `Simple Memory` without calling `2.4.4`, so it claimed buttons were prepared when none were created. Decision implemented: disconnect/remove `Simple Memory` from `2.0`; Oom Sakkie operational commands should be stateless and tool-backed.
- Real send button test passed on 2026-05-19 using `ORD-2026-71609C`: GateKeeper routed `quote_send|...` to `2.4.5`, backend sent quote `Q-2026-71609C` / `DOC-2026-AD8111` to Chatwoot conversation `1774`, WhatsApp received the PDF message, and backend document status became `Sent` with `sent_by = Charl`.
- n8n verification passed for the send click: GateKeeper execution `45071` and `2.4.5` execution `45072` both succeeded.
- Test order cleanup passed: `ORD-2026-71609C` was cancelled after the send test; one line was cancelled and reserved count returned to zero.
- Cleanup implemented:
  - `2.0` export disconnects `Simple Memory`.
  - `2.0` export adds `Switch - Suppress Direct Tool Reply` between `AI Assistant Agent` and `AI Replay Agent`; output `__NO_TELEGRAM_REPLY__` and quote-send preparation acknowledgements are suppressed.
  - `2.4.4` export returns `__NO_TELEGRAM_REPLY__` after it has already sent the direct Telegram button message.
  - Shared date parser now accepts sheet datetime strings such as `19 May 2026 04:20`, so operator summaries can show `sent_at` instead of blanking it.
- Final 7.3D smoke passed on 2026-05-19 with `ORD-2026-46D437`: prepare produced only one Telegram button message, `Cancel` left quote `Q-2026-46D437` / `DOC-2026-67813E` as `Generated`, prepare again produced one message, `Send quote to customer` sent the PDF to Chatwoot conversation `1774`, WhatsApp received the quote, and backend recorded `Document_Status = Sent`, `Sent_By = Charl`, `Sent_At = 2026-05-19`.
- Final test order cleanup passed: `ORD-2026-46D437` was cancelled after the successful send test; one line was cancelled, payment status became `Cancelled`, and reserved pig count is zero.
- Phase 7.3D is complete and live-verified.
- Test exact `order_id` lookup.
- Test phone/name multiple-match handling.
- Test document list lookup.
- Test no-match handling.
- Test quote-send preparation and the `Cancel` button.
- Test `Send quote to customer` only after the destination conversation/customer is confirmed safe.

## Open Questions

- Confirm whether document links should stay hidden in the first live version.
- Confirm whether quote send should be planned as a later 7.3D slice and invoice send left future-only.
