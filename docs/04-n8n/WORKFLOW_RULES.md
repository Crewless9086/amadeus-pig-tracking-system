# Workflow Rules

## Purpose

Defines the operating rules for the n8n workflow suite.

## Suite Rules

- `1.0 - SAM - Sales Agent - Chatwoot` is the customer-facing hub.
- `1.1 - SAM - Sales Agent - Escalation Telegram` handles human replies after escalation.
- `1.2 - Amadeus Order Steward` handles backend order actions for `1.0`.
- `1.3 - SAM - Sales Agent - Media Tool` is the official media workflow, but remains disabled until fixed and tested.

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
- Telegram cleanup after reply is desired and should be implemented/tested before marked complete

## Order Steward Rules

For `1.0`, only these `1.2` actions are currently treated as live:

- `create_order`
- `update_order`
- `sync_order_lines_from_request`

Other actions present in `1.2` are not automatically considered live for Sam until wired, tested, and documented.

Sam should not directly write order sheets. Future order review should preferably go through `1.2` and backend order lookup/review endpoints rather than direct `ORDER_OVERVIEW` sheet access.

## Media Tool Rules

- `1.3` is the official media workflow number.
- The media tool remains disabled until fixed and tested.
- Do not enable `Send_Pictures` in `1.0` until `1.3` input/output behavior is verified.
- Media categories and Google Drive folders must be reviewed before customer use.

## Google Sheets Rules

- Sales stock and availability sheets are read-only.
- n8n must not directly write operational order sheets.
- n8n should call backend endpoints through `1.2` for order changes.
- Sheet rules must align with `docs/03-google-sheets/`.

## Secrets And Export Detail

The repository is private, so workflow exports may retain full local build detail. If this repository becomes shared or public, credentials, tokens, webhook URLs, and IDs must be redacted or rotated.
