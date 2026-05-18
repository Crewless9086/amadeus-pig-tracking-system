# Oom Sakkie Order And Document Lookup Plan

## Purpose

Phase 7.3 planning for letting Oom Sakkie answer internal operator questions about orders and documents without opening the web app or Google Sheets.

Status: planning only. Do not update workflow JSON or backend code from this document until the 7.3 plan is reviewed and accepted.

## Live Workflow Baseline

Imported from n8n on 2026-05-18:

| Workflow | ID | Status | Current role |
| --- | --- | --- | --- |
| `2 - The GateKeeper` | `yt4qc1kP5riAfLfL` | Active | Telegram access gate for Oom Sakkie. |
| `2.0 - OOM SAKKIE - Amadeus Assistant Agent` | `6UscGE44eTfdLp1A` | Active | Main Oom Sakkie Telegram assistant. |
| `2.1 - Amadeus Weather Sub-Agent` | `L4c34rFmN0kUJvWc` | Active | Weather sub-agent tool. |
| `2.1.1 - Amadeus Forecast Tool` | `vx1lV8aFCG28KSIN` | Active | Forecast utility workflow. |
| `2.2 - Amadeus Sunsynk Sub-Agent` | `tKVKoCcxhT7CAydT` | Active | Solar/power sub-agent tool. |
| `2.3.1 - Build Daily Irrigation Plan` | `UNwNmx0TwtFf8mjo` | Active | Scheduled irrigation planning. |
| `2.3.2 - Run Irrigation Controller` | `f6oPLsaolGH4pMKC` | Inactive | Scheduled irrigation valve controller. |
| `2.4 - Amadeus Orders Sub Agent` | `T8LLCAtYDLNRPoRx` | Active | Internal order approval sub-agent. |
| `2.4.1 - Test Caller` | `GwWZueB0iyonpscl` | Inactive | Manual orders sub-agent test caller. |
| `2.4.2 - Orders Approval Callback Handler` | `wmsgzHNywC6okTuI` | Active | Telegram approval callback handler. |
| `2.4.3 - Order Approval Request Webhook` | `k4XVMoJ1hK09PIvT` | Active | Approval request webhook. |
| `ALERT - Local Weather Station` | `g0ajlm9gBp7J72Jn` | Inactive | Scheduled weather station alerts. |
| `ALERT - Sunsynk` | `2LETWzde7lMDlMnl` | Inactive | Scheduled solar/power alerts. |
| `ALERT - Weather Forecast` | `I4D76Gb9ddGFhSP5` | Inactive | Scheduled forecast alerts. |

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
- Confirm whether `2.4` should own both approval and read-only lookup, or whether lookup should become a new `2.4.x` helper workflow. - Owner decision: build lookup into existing `2.4`.
- Decide whether the first implementation uses existing endpoints only or adds `GET /api/orders/search` first. - Recommended: add backend search/summary first so matching stays backend-owned.
- Decide whether document links are shown to operators or only document refs/statuses are shown. - Recommended: show refs/statuses first; add links only after operator access rules are clearer.

## Recommended 7.3A Direction

Use the existing `2.4 - Amadeus Orders Sub Agent` as the order tool for Oom Sakkie.

Recommended decisions before implementation:

- Add backend-owned search/summary support before workflow changes:
  - `GET /api/orders/search`
  - `GET /api/orders/<order_id>/operator-summary`
- Keep name/phone matching in the backend, not in n8n Code nodes.
- Expose order lookup through the existing Telegram Oom Sakkie route:
  - `2 - The GateKeeper`
  - `2.0 - OOM SAKKIE - Amadeus Assistant Agent`
  - `2.4 - Amadeus Orders Sub Agent`
- Keep `2.4` approval behavior intact and add lookup as separate read-only actions.
- In the first live version, show document refs, document status, versions, totals, and sent state. Do not show raw Google Drive URLs by default.
- Keep invoice sending future-only until quote lookup/send behavior is proven.
- Keep document sending out of the first read-only lookup slice.

Recommended first action set inside `2.4`:

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

### 7.3C Oom Sakkie Workflow

- Update the existing Oom Sakkie workflow docs/export. Do not replace the live `2.0` workflow.
- Add read-only actions first:
  - `find_order`
  - `get_order_summary`
  - `get_order_documents`
- Do not add send actions until read-only lookup is verified.

### 7.3D Document Send Guard

- Add explicit confirmation path for document send.
- Verify it calls backend send endpoints, not workflow-to-Chatwoot directly.
- Test only with a safe test conversation.

### 7.3E Live Verification

- Test exact `order_id` lookup.
- Test phone/name multiple-match handling.
- Test document list lookup.
- Test no-match handling.
- Test document send only if 7.3D is in scope and the destination is confirmed safe.

## Open Questions

- Confirm whether document links should stay hidden in the first live version.
- Confirm whether quote send should be planned as a later 7.3D slice and invoice send left future-only.
