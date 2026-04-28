# Do Not Change

## Purpose

Defines workflow behavior, fields, and integration contracts that must not be changed without explicit review.

## Protected Workflow Roles

| Workflow | Protected role |
| --- | --- |
| `1.0 - SAM - Sales Agent - Chatwoot` | Customer-facing conversation hub. |
| `1.1 - SAM - Sales Agent - Escalation Telegram` | Human reply bridge from Telegram to Chatwoot. |
| `1.2 - Amadeus Order Steward` | Backend order action worker. |
| `1.3 - SAM - Sales Agent - Media Tool` | Disabled media tool until fixed and tested. |

## Protected Field Ownership

Do not rename or repurpose these fields casually:

| Field | Owner / purpose |
| --- | --- |
| `decision_mode` | Authoritative branch mode in `1.0`. |
| `escalation_raw_output` | Preserved classifier output. |
| `ai_reply_output` | Preserved AI Sales Agent reply. |
| `cleaned_reply` | Final customer-safe reply from `1.0`. |
| `order_state` | Structured order intent extracted by `1.0`. |
| `requested_items[]` | Structured line request data for sync. |
| `conversation_mode` | Chatwoot mode gate: `AUTO` or `HUMAN`. |
| `pending_action` | Chatwoot confirmation state for guarded actions such as `cancel_order`. |
| `order_id` | Backend order identifier. |
| `order_status` | Backend/order state context. |
| `TicketID` | Human escalation ticket key. |
| `images_sent_offset_map` | Media tool repeat-send control. |

## High-Risk Field: `output`

`output` is temporary and stage-dependent. It is used by multiple AI/tool nodes and must not be treated as globally safe after merge points.

Important content must be copied into a dedicated field before it crosses a merge, switch, or external call.

## Protected `1.0` Behavior

Do not change without review:

- customer-message loop guard
- HUMAN mode gate
- voice-note transcription path
- classifier decision parse path
- CLARIFY path protection
- final reply cleaning/sending path
- order route switch, including `CANCEL_PENDING`, `CANCEL_ORDER`, and `CLEAR_PENDING`
- Chatwoot `pending_action` set/clear calls
- `1.2` execute workflow calls
- escalation handoff creation

## Protected `1.2` Behavior

Do not change without review:

- `action` discriminator field
- backend base URL and endpoint paths
- payload normalization
- `create_order`, `update_order`, `sync_order_lines_from_request`, and `cancel_order` contracts used by `1.0`
- backend error propagation

`1.2` must not directly write order Google Sheets.

## Protected Escalation Behavior

Do not change without review:

- Ticket ID format and lookup behavior
- handoff sheet columns used by `1.0` and `1.1`
- approved Telegram chat restriction
- Chatwoot account/conversation ID mapping
- returning `conversation_mode` to `AUTO` after human reply

Desired improvement:

- Delete/clean up relevant Telegram messages after human reply, without deleting unrelated messages.

## Protected Media Behavior

`1.3` is disabled until fixed and tested.

Do not enable without review:

- `Send_Pictures` tool in `1.0`
- Google Drive folder mappings
- Chatwoot media attachment behavior
- `images_sent_offset_map` updates

## Protected External Systems

- Chatwoot API calls must use the correct account and conversation IDs.
- Backend order actions must go through the Flask API.
- Sales stock sheets are read-only.
- Formula-driven Google Sheets are read-only.
- Google Drive media folders must not expose unapproved files.
- Telegram escalation must stay restricted to approved human users/chats.

## Review Rule

If a change affects a protected field, route, workflow number, sheet, backend endpoint, or Chatwoot custom attribute, update this file and test the affected path before treating the change as stable.
