# Workflow Rules

## Purpose

Defines the operating rules for the n8n workflow suite.

## Suite Rules

- `1.0 - SAM - Sales Agent - Chatwoot` is the customer-facing hub.
- `1.1 - SAM - Sales Agent - Escalation Telegram` handles human replies after escalation.
- `1.2 - Amadeus Order Steward` handles backend order actions for `1.0`.
- `1.3 - SAM - Sales Agent - Media Tool` is the official media workflow, but remains disabled until fixed and tested.
- `1.4 - Outbound Order Notification` handles backend-confirmed approval/rejection customer messages.
- `1.5 - Outbound Document Delivery` handles backend-generated quote/invoice attachment delivery.
- `1.6 - Daily Order Summary` handles scheduled backend summary reporting to Telegram.
- Chatwoot labels and custom attributes must follow `CHATWOOT_ATTRIBUTES.md`.

## Decision Modes In `1.0`

| Mode | Meaning | Rule |
| --- | --- | --- |
| `AUTO` | Continue with system logic and order processing when appropriate. | May call `1.2` for currently supported actions. |
| `CLARIFY` | Ask one useful follow-up question or answer without backend processing. | Must not create/update/sync orders. |
| `ESCALATE` | Hand to human. | Must create handoff context and stop automated customer reply where human action is required. |

## CLARIFY Rules

When `decision_mode = CLARIFY`:

- do not create or update orders
- do not sync order lines
- use the AI Sales Agent reply directly where possible
- do not weaken a useful answer by routing it through a composer that changes meaning
- ask only one clear follow-up question when a question is needed

## AUTO Rules

When `decision_mode = AUTO`:

- build or update `order_state` only when the customer gave enough useful order information
- call `1.2` only for currently approved live actions
- do not promise reservation or availability until backend/tool data supports it
- preserve useful AI reply context through merge points
- final customer reply must come from the approved cleaned reply path

## ESCALATE Rules

When `decision_mode = ESCALATE`:

- create a handoff record with enough context for the human
- notify the human via Telegram
- protect the customer conversation from duplicate automated replies
- use `1.1` to send the human response back to Chatwoot
- return the conversation to `AUTO` only after the human reply is sent
- preserve Chatwoot order context fields when setting or clearing human mode
- Telegram cleanup after reply is desired and should be implemented/tested before marked complete

## Order Steward Rules

For `1.0`, these `1.2` actions are currently treated as live (aligned with `docs/02-backend/API_STRUCTURE.md`):

- `create_order`
- `create_order_with_lines` (atomic create + sync in `1.2`)
- `update_order`
- `sync_order_lines_from_request`
- `get_order_context` (read-only; called by `1.0` before AUTO order-state build when a draft id exists)
- `cancel_order`
- `send_for_approval`
- `generate_quote`
- `send_latest_quote`

Other actions present in `1.2` (for example `view_order`, `reserve_order`) are not automatically considered live for Sam until wired, tested, and documented.

Customer cancellation requires two-turn confirmation. `1.0` must set `pending_action = cancel_order` on first cancel intent, call `cancel_order` only after a clear confirmation, and clear stale pending state when the next customer message does not confirm cancellation.

Quote delivery may also use pending confirmation. When a quote is generated/current but not yet sent, `1.0` may set `pending_action = send_quote`. A later clear confirmation routes to `send_latest_quote`; Sam may only say the quote was sent after the backend/steward response confirms delivery.

Sam should not directly write order sheets. Future order review should preferably go through `1.2` and backend order lookup/review endpoints rather than direct `ORDER_OVERVIEW` sheet access.

## Outbound Notification Rules

- `1.4` is triggered by backend only through `ORDER_NOTIFICATION_WEBHOOK_URL`.
- `1.4` must send only the backend-provided `message_text`; do not rewrite approval/rejection messages with AI.
- `1.4` must use `conversation_id` from `ORDER_MASTER.ConversationId` and must fail clearly if it is missing.
- `1.0` must not send approval/rejection outcome messages independently.
- Backend notification failure must not roll back approval or rejection.

## Document Delivery Rules

- `1.5` is triggered by backend only through `DOCUMENT_DELIVERY_WEBHOOK_URL`.
- `1.5` must send only backend-generated PDFs referenced by `ORDER_DOCUMENTS`.
- `1.5` must not calculate VAT, totals, document references, or invoice eligibility.
- `1.5` must require `conversation_id`; backend test sends must explicitly target the approved test conversation.
- For Phase 2.5 tests, use Chatwoot `conversation_id = 1742` only.

## Daily Summary Rules

- `1.6` must call `GET /api/reports/daily-summary`.
- `1.6` must not read order sheets directly.
- `1.6` is read-only and must not call order mutation endpoints.
- Manual trigger testing should happen before activating the schedule.
- Telegram delivery should target only the approved admin chat until user/notification preferences are designed.

## Media Tool Rules

- `1.3` is the official media workflow number.
- The media tool remains disabled until fixed and tested.
- Do not enable `Send_Pictures` in `1.0` until `1.3` input/output behavior is verified.
- Do not enable `1.3` until its `Patch Conversation Attributes` node preserves the full Chatwoot conversation attribute snapshot.
- Media categories and Google Drive folders must be reviewed before customer use.

## Google Sheets Rules

- Sales stock and availability sheets are read-only.
- n8n must not directly write operational order sheets.
- n8n should call backend endpoints through `1.2` for order changes.
- Sheet rules must align with `docs/03-google-sheets/`.

## Secrets And Export Detail

The repository is private, so workflow exports may retain full local build detail. If this repository becomes shared or public, credentials, tokens, webhook URLs, and IDs must be redacted or rotated.
