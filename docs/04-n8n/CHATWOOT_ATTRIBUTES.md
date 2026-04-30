# Chatwoot Attributes And Labels

## Purpose

This file is the canonical register for Chatwoot labels and custom attributes used by the n8n workflow suite.

Chatwoot conversation custom attributes are high risk because the Chatwoot API replaces the full `custom_attributes` object on write. Any workflow node that writes conversation attributes must send the complete required snapshot, not only the field it is changing.

## Standing Rules

- Every Chatwoot conversation attribute write must preserve the active context fields listed below.
- Do not add a new Chatwoot attribute write node without updating this file and `DO_NOT_CHANGE.md`.
- Do not enable `1.3 - SAM - Sales Agent - Media Tool` until its media attribute write preserves order context.
- Contact attributes are currently defined in Chatwoot for future memory use, but n8n does not yet read or write them.
- Label writes must be tested carefully. If the Chatwoot label endpoint replaces labels instead of appending, every label write must preserve the existing label set.

## Conversation Attributes

| Attribute | Type in Chatwoot | Owner / writer | Current workflow use | Required on every conversation attribute write |
| --- | --- | --- | --- | --- |
| `order_id` | text | `1.0`, `1.1` | Active order context for later customer turns. | Yes |
| `order_status` | text | `1.0`, `1.1` | Active order lifecycle status context. | Yes |
| `conversation_mode` | text | `1.0`, `1.1` | `AUTO` or `HUMAN` mode gate. | Yes |
| `pending_action` | text | `1.0`, `1.1` | Guarded customer action state, currently `cancel_order` or blank. | Yes |
| `escalation_ticket_id` | text | `1.0`, `1.1` | Links Chatwoot conversation to Telegram escalation ticket. | Escalation writes only |
| `last_escalated_at` | date | `1.0`, `1.1` | Date the conversation was moved to human handling. | Escalation writes only |
| `last_human_replay` | date | `1.0`, `1.1` | Human reply tracking field. Name is currently spelled `replay` in workflow exports. | Escalation writes only |
| `payment_method` | text | `1.0` | Payment method mirror for conversation continuity. Values: `Cash` or `EFT`. Written after every Chatwoot attribute write to preserve context across turns. | Yes |
| `last_images_sent_at` | date | `1.3` | Media tool send tracking. Disabled workflow. | Media writes only |
| `last_images_sent_category` | text | `1.3` | Last media category sent. Disabled workflow. | Media writes only |
| `last_images_sent_count` | number | `1.3` | Count of images sent. Disabled workflow. | Media writes only |
| `images_sent_offset_map` | text | `1.3` | JSON map for repeat-send offsets. Disabled workflow. | Media writes only |

## Required Conversation Attribute Snapshots

### `1.0` Order And Cancel Writes

These nodes must always write:

- `order_id`
- `order_status`
- `conversation_mode`
- `pending_action`
- `payment_method`

Nodes:

- `HTTP - Set Conversation Order Context`
- `HTTP - Set Conversation Context After Update`
- `HTTP - Set Pending Cancel Action`
- `HTTP - Clear Pending Action`
- `HTTP - Clear Pending After Cancel`
- `HTTP - Set Chatwoot After Send Approval`

### `1.0` Escalation Write

`HTTP - Set Conversation Human Mode` must always write:

- `order_id`
- `order_status`
- `conversation_mode = HUMAN`
- `pending_action`
- `payment_method`
- `escalation_ticket_id`
- `last_escalated_at`
- `last_human_replay`

### `1.1` Human Reply Release Write

`Release Conversation to Auto` must always write:

- `order_id`
- `order_status`
- `conversation_mode = AUTO`
- `pending_action`
- `payment_method` — read from `Sales_HumanEscalations.WebPaymentMethod`
- `escalation_ticket_id = ""`
- `last_human_replay = ""`
- `last_escalated_at = ""`

The order fields come from the `Sales_HumanEscalations` row fields:

- `WebOrderId`
- `WebOrderStatus`
- `WebPendingAction`
- `WebPaymentMethod`

### `1.3` Media Write

Current status: disabled and not safe to enable until fixed.

`Patch Conversation Attributes` currently writes only media fields:

- `last_images_sent_at`
- `last_images_sent_category`
- `last_images_sent_count`
- `images_sent_offset_map`

Before enabling `1.3`, update this node so media writes also preserve:

- `order_id`
- `order_status`
- `conversation_mode`
- `pending_action`
- escalation fields if present

## Contact Attributes

These are defined in Chatwoot but are not currently read or written by n8n.

| Attribute | Type in Chatwoot | Intended use | Current workflow status |
| --- | --- | --- | --- |
| `buying_intent` | list | Let Sam adjust tone and detail level automatically. | Defined only |
| `requested_quantity` | number | Remember requested quantity across conversations. | Defined only |
| `preferred_weight_range` | text | Remember common preferred weight range. | Defined only |
| `preferred_sex` | list | Remember customer sex preference. | Defined only |
| `contact_stage` | list | Future customer lifecycle branching. | Defined only |

Do not rely on these fields until a deliberate contact-attribute read/write design is added.

## Labels

These labels exist in Chatwoot.

| Label | Current n8n use | Notes |
| --- | --- | --- |
| `warm_lead` | Written by `1.0` lead classification. | Active |
| `hot_lead` | Written by `1.0` lead classification. | Active |
| `error_fix` | Not currently written by n8n. | Defined only |
| `human_followup` | Not currently written by n8n. | Defined only |
| `lead` | Not currently written by n8n. | Defined only |
| `pricing_requested` | Not currently written by n8n. | Defined only |
| `ready_to_buy` | Not currently written by n8n. | Defined only |
| `reserved` | Not currently written by n8n. | Defined only |
| `sold` | Not currently written by n8n. | Defined only |
| `waiting_list` | Not currently written by n8n. | Defined only |

## Label Write Risk

`1.0` currently sends:

- `{"labels": ["warm_lead"]}`
- `{"labels": ["hot_lead"]}`

Before adding more label behavior, live-test whether the Chatwoot labels endpoint appends labels or replaces the complete label set. If it replaces, label writes must preserve all existing labels.

## Current Outstanding Items

- `1.1 Release Conversation to Auto` was live-verified on 2026-04-29 and now writes evaluated values back to Chatwoot.
- Phase 1.3 payment-method preservation was live-verified on 2026-04-29 across normal update, next-turn readback, cancel pending, and escalation release.
- Confirm the Chatwoot label endpoint behavior before expanding labels.
- Fix `1.3 Patch Conversation Attributes` before enabling media.
- Decide whether contact attributes should become a real memory layer after order lifecycle stabilization.
