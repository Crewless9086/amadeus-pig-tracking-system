# Order Intake State Design

## Purpose

Phase 5.4 defines the persistent intake layer for natural Sam sales conversations.

The goal is to stop order facts from being lost when a conversation becomes long, repetitive, or indirect. Sam may speak naturally, but operational decisions must come from backend-confirmed structured state.

This is a design document only. It does not create sheets, endpoints, workflow nodes, or runtime behavior.

## Core Principle

Conversation is human. State is structured. Backend is truth. n8n is orchestration. Sam is language.

## Problem

The current `1.0 - Sam-sales-agent-chatwoot` flow can hold a natural conversation, but draft creation depends on structured `order_state` being complete on the current turn.

That breaks when:

- the customer's original product details fall outside the recent Chatwoot history window
- Sam repeats the correct order details in prose, but deterministic route code does not trust Sam's prose as source data
- the customer says short replies such as "Yes", "I told you what I want", or "I need a quote"
- quote-stage wording blocks draft creation even when the customer has provided all required details

The fix is not to make Sam guess harder. The fix is to persist intake facts turn by turn.

## Ownership

| Layer | Owns | Must Not Own |
| --- | --- | --- |
| Backend | Intake state, item state, merge rules, missing-field calculation, next action, draft/update/quote eligibility | Natural customer wording |
| Google Sheets | Persistent intake rows until a stronger database exists | Formula-driven decisions for intake state |
| n8n | Message orchestration, backend calls, passing compact context, sending replies/documents | Intake truth or direct sheet writes |
| Chatwoot attributes | Lightweight routing hints | Full order intake truth |
| Sam | Natural reply, one clear next question, friendly explanation | Operational truth, sheet writes, final action decisions |

## Planned Sheets

### `ORDER_INTAKE_STATE`

One active intake header per sales conversation.

This sheet tracks customer/conversation identity, lifecycle state, known non-item facts, missing fields, next action, and linked draft/document state.

### `ORDER_INTAKE_ITEMS`

One row per requested item.

This supports:

- one category
- multiple categories
- split male/female requests
- add-ons
- nearby-band add-ons
- edits
- removals
- links to synced `ORDER_LINES`

## Intake Lifecycle

| Status | Meaning |
| --- | --- |
| `Open` | Intake is active and collecting details. |
| `Ready_For_Draft` | Required draft fields are present and customer intent is strong enough to create/update a draft. |
| `Draft_Created` | Intake is linked to a Draft order. |
| `Quote_Requested` | Customer asked for a formal quote. |
| `Quote_Generated` | Backend generated a quote PDF and recorded it in `ORDER_DOCUMENTS`. |
| `Sent_For_Approval` | Linked order was sent for approval. |
| `Closed` | Intake is no longer active because the order was cancelled, completed, or explicitly abandoned. |
| `Needs_Admin` | The customer asked for something that should not be auto-applied, such as changing an approved order. |

## Required Fields

### Required To Create A Draft

- at least one active intake item with:
  - `Quantity`
  - `Category`
  - `Weight_Range`
- `Collection_Location`
- a customer identity/contact route
- customer commitment signal, such as:
  - "I want to proceed"
  - "yes create it"
  - "please order"
  - confirmed quote/order details after Sam asks a direct draft question

Do not create a Draft order just because two or more fields are known. A Draft order is allowed only when the minimum operational fields above are present and the customer has clearly committed to creating/proceeding with an order.

`Payment_Method` is not required for the first Draft order, but it is required before formal quote generation and before sending the order for approval.

### Required To Generate A Formal Quote

- all draft requirements
- `Payment_Method` (`Cash` or `EFT`)
- linked Draft order
- synced active order lines
- active lines have valid unit prices

Formal quote generation must use the existing backend quote endpoint and `ORDER_DOCUMENTS`.

## Draft Order Versus Quote

A Draft order is the operational record.

A formal quote is a backend-generated PDF document based on the order and order lines.

If the customer asks for a formal quote and no draft exists, the agreed flow is:

1. complete intake
2. create Draft order
3. sync order lines
4. generate quote PDF
5. offer/send the quote through the document path

Sam must not treat a chat price summary as a generated quote.

If the customer clearly wants to proceed but has not asked for a formal quote, the system may create/update the Draft when the draft requirements are met, then Sam should ask whether the customer wants a formal quote PDF or wants to continue toward approval. The system should not generate a formal quote silently unless the customer requested or confirmed it.

## Intake Merge Rules

Each customer message can produce an intake update patch.

AI-assisted extraction may propose an intake update patch, but the backend must validate and merge the patch safely. n8n and Sam must not write intake rows directly.

- non-empty new values may update empty fields
- non-empty new values may update existing fields when the customer clearly changes them
- blank values must not erase known fields
- ambiguous changes must set `Next_Action = ask_disambiguation`
- removed items must be marked inactive/removed, not deleted from history
- item keys must remain stable once assigned

Examples:

| Customer Says | Expected Merge |
| --- | --- |
| "Riversdale works for me" | Set `Collection_Location = Riversdale`. |
| "Cash please" | Set `Payment_Method = Cash`. |
| "Add 2 piglets as well" | Add a new active intake item. |
| "Change the grower to 40-44kg" | Update one matching grower item, or ask disambiguation if multiple match. |
| "Remove the piglets" | Mark matching piglet item `Removed`. |
| "I told you what I want" | Do not erase fields. Use existing state and ask only if a required field is still missing. |

The backend should reject or ignore proposed values outside known allowed values, such as invalid categories, invalid payment methods, non-positive quantities, or unsupported item statuses.

## Item Model

Each active item maps toward one or more eventual `ORDER_LINES`.

Required item fields:

- `Item_Key`
- `Quantity`
- `Category`
- `Weight_Range`
- `Sex`
- `Intent_Type`
- `Status`

Allowed `Intent_Type` values should align with existing sync metadata:

- `primary`
- `addon`
- `nearby_addon`
- `extractor_slot`

Allowed `Status` values:

- `active`
- `removed`
- `replaced`

Only active items should be sent to the existing backend line sync endpoint, because current sync rejects inactive rows.

## Next Action Contract

Backend should return a compact command object to n8n.

Candidate `next_action` values:

| Value | Meaning |
| --- | --- |
| `ask_missing_field` | Sam should ask one specific missing field. |
| `ask_disambiguation` | Sam should clarify which item/order the customer means. |
| `reply_only` | No operational action needed. |
| `create_draft` | Intake is ready and customer wants to proceed. |
| `update_draft` | Linked Draft exists and intake changed. |
| `sync_lines` | Linked Draft exists and active intake items need line sync. |
| `create_draft_then_quote` | Formal quote requested, no draft exists, intake complete. |
| `update_draft_then_quote` | Formal quote requested, Draft exists, intake needs update/sync first. |
| `generate_quote` | Draft and synced lines are ready for quote generation. |
| `block_requires_admin` | Customer asked for an unsafe automatic change. |

## Backend Response Shape

Candidate response:

```json
{
  "success": true,
  "conversation_id": "1774",
  "intake_id": "INTAKE-2026-ABC123",
  "intake_status": "Open",
  "draft_order_id": "",
  "known_fields": {
    "collection_location": "Riversdale",
    "collection_time_text": "Friday at 14:00",
    "payment_method": "Cash"
  },
  "items": [
    {
      "item_key": "item_1",
      "quantity": 1,
      "category": "Grower",
      "weight_range": "35_to_39_Kg",
      "sex": "Female",
      "intent_type": "primary",
      "status": "active"
    }
  ],
  "missing_fields": [],
  "ready_for_draft": true,
  "ready_for_quote": true,
  "next_action": "create_draft_then_quote",
  "safe_reply_facts": [
    "1 female grower pig",
    "35-39 kg",
    "Riversdale",
    "Friday at 14:00",
    "Cash"
  ]
}
```

## Collection Date And Time

Customer wording such as "Friday at 14:00" must be preserved exactly in `Collection_Time_Text`.

The backend may also store parsed fields when they are safe:

- `Collection_Date`
- `Collection_Time`

If the date is relative or ambiguous, Sam should confirm the exact date before relying on the parsed date for operational action. The raw text remains available even when parsing is uncertain.

## Existing Draft Changes

If linked order status is `Draft`, the intake system may update:

- requested items
- collection location
- payment method
- timing text/notes

After an intake edit:

1. update intake state
2. update `ORDER_MASTER` header if needed
3. sync active intake items to `ORDER_LINES`
4. report exact, partial, or no-match results

If linked order is `Pending_Approval`, `Approved`, `Completed`, or `Cancelled`, automatic edits should be blocked unless later explicitly designed.

## Multi-Category Flow

Customer:

```text
I want 1 female grower 35-39kg and 2 piglets 5-6kg.
```

Intake items:

```json
[
  {
    "item_key": "item_1",
    "quantity": 1,
    "category": "Grower",
    "weight_range": "35_to_39_Kg",
    "sex": "Female"
  },
  {
    "item_key": "item_2",
    "quantity": 2,
    "category": "Piglet",
    "weight_range": "5_to_6_Kg",
    "sex": "Any"
  }
]
```

The system must not collapse this into one header-only product field.

## Shadow Mode

Before intake drives live actions, it should run in shadow mode:

- update/read intake on every customer turn
- keep existing routing behavior unchanged
- compare intake state to current `order_state`
- log differences for known problem transcripts
- prove state survives long conversations and repeated questions

Shadow mode must pass before payload cleanup.

## Cleanup Sequence

Do not clean payloads first.

Correct sequence:

1. design intake state
2. create sheet/endpoints
3. shadow-mode compare
4. use intake for draft/quote decisions
5. live-test the known failing transcript
6. reduce duplicated n8n fields and Chatwoot attributes

## Settled Decisions

Phase 5.4 owner decisions are settled:

- Use the proposed explicit column names documented in `docs/03-google-sheets/sheets/ORDER_INTAKE_STATE.md` and `docs/03-google-sheets/sheets/ORDER_INTAKE_ITEMS.md` as the Phase 5.5 implementation baseline.
- AI-assisted extraction may propose patches, but the backend validates and merges them. n8n and Sam do not write intake state directly.
- A formal quote request must create/update a backend Draft order first when no suitable Draft exists.
- Store relative collection wording in `Collection_Time_Text`; store parsed `Collection_Date` / `Collection_Time` only when safe or confirmed.
- Keep closed intake rows for audit/history. Do not delete them as part of normal operation.
- Abandoned open intake rows may be marked `Closed` with an abandoned reason after an agreed inactivity window. Do not delete them. Draft-linked abandoned cases should be reviewed or handled by a separately approved rule.
