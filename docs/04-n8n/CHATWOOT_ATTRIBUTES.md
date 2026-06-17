# Chatwoot Attributes And Labels

## Purpose

This file is the canonical register for Chatwoot labels and custom attributes used by the n8n workflow suite and backend-native Chatwoot integrations.

Chatwoot conversation custom attributes are high risk because the Chatwoot API replaces the full `custom_attributes` object on write. Any workflow node that writes conversation attributes must send the complete required snapshot, not only the field it is changing.

## Standing Rules

- Every Chatwoot conversation attribute write must preserve the active context fields listed below.
- Do not add a new Chatwoot attribute write node without updating this file and `DO_NOT_CHANGE.md`.
- Do not enable `1.3 - SAM - Sales Agent - Media Tool` until its media attribute write preserves order context.
- Contact attributes are currently defined in Chatwoot for future memory use, but n8n does not yet read or write them.
- Label writes must be tested carefully. If the Chatwoot label endpoint replaces labels instead of appending, every label write must preserve the existing label set.
- Backend-native Sam Meat label/attribute writes must follow the same preservation rule as n8n writes.

## Conversation Attributes

| Attribute | Type in Chatwoot | Owner / writer | Current workflow use | Required on every conversation attribute write |
| --- | --- | --- | --- | --- |
| `order_id` | text | `1.0`, `1.1` | Active order context for later customer turns. | Yes |
| `order_status` | text | `1.0`, `1.1` | Active order lifecycle status context. | Yes |
| `conversation_mode` | text | `1.0`, `1.1` | `AUTO` or `HUMAN` mode gate. | Yes |
| `pending_action` | text | `1.0`, `1.1` | Guarded customer action state, currently `cancel_order`, `send_quote`, or blank. | Yes |
| `escalation_ticket_id` | text | `1.0`, `1.1` | Links Chatwoot conversation to Telegram escalation ticket. | Escalation writes only |
| `last_escalated_at` | date | `1.0`, `1.1` | Date the conversation was moved to human handling. | Escalation writes only |
| `last_human_replay` | date | `1.0`, `1.1` | Human reply tracking field. Name is currently spelled `replay` in workflow exports. | Escalation writes only |
| `payment_method` | text | `1.0` | Payment method mirror for conversation continuity. Values: `Cash` or `EFT`. Written after every Chatwoot attribute write to preserve context across turns. | Yes |
| `last_images_sent_at` | date | `1.3` | Media tool send tracking. Disabled workflow. | Media writes only |
| `last_images_sent_category` | text | `1.3` | Last media category sent. Disabled workflow. | Media writes only |
| `last_images_sent_count` | number | `1.3` | Count of images sent. Disabled workflow. | Media writes only |
| `images_sent_offset_map` | text | `1.3` | JSON map for repeat-send offsets. Disabled workflow. | Media writes only |
| `sales_lane` | text | Backend Sam Meat | Sales lane marker, for example `meat_preorder`, `live_pig`, or `slaughter_abattoir`. | Meat writes only |
| `meat_product_type` | text | Backend Sam Meat | Current meat product category such as `half_carcass`, `full_carcass`, `custom_cut`, or blank. | Meat writes only |
| `meat_cut_set` | text | Backend Sam Meat | Cut set such as `Set A`, `Set B`, or blank. | Meat writes only |
| `meat_delivery_mode` | text | Backend Sam Meat | `delivery`, `collection`, or blank. | Meat writes only |
| `meat_delivery_town` | text | Backend Sam Meat | Delivery/collection town or area. | Meat writes only |
| `meat_lead_id` | text | Backend Sam Meat | Backend sales lead ID linked to the conversation. | Meat writes only |
| `meat_order_id` | text | Backend/Farm App later | Draft/final meat order ID when created. | Meat writes only |
| `meat_payment_state` | text | Backend Sam Meat/Farm App later | `not_requested`, `deposit_pending`, `pop_received_unverified`, `deposit_confirmed`, `balance_due`, `paid`, or blank. | Meat writes only |
| `meat_next_gate` | text | Backend Sam Meat/Farm App later | Current gate such as `collect_missing_facts`, `owner_price_review`, `await_customer_yes`, `confirm_deposit`, `find_second_half_buyer`, `confirm_final_balance`, or `schedule_delivery`. | Meat writes only |
| `meat_followup_due_at` | date | Backend Sam Meat/Farm App later | Future follow-up target time/date. | Meat writes only |
| `meat_last_customer_intent` | text | Backend Sam Meat | Short latest intent summary such as `asks_options`, `asks_price`, `confirms_booking`, or `sends_pop`. | Meat writes only |

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

### Backend Sam Meat Writes

Current status: implemented in backend Phase 11L.

Runtime gate:

- `SAM_MEAT_CHATWOOT_HYGIENE_ENABLED=1`

Required Chatwoot envs:

- `CHATWOOT_BASE_URL`
- `CHATWOOT_ACCOUNT_ID`
- `CHATWOOT_API_ACCESS_TOKEN`

The backend first fetches the Chatwoot conversation, merges the meat fields into the existing `custom_attributes`, and writes the full merged snapshot back to Chatwoot. It also reads the existing labels and writes the union of current labels plus meat labels, so existing order/sales labels are preserved even if Chatwoot treats label writes as replacement writes.

Backend Sam Meat must preserve existing conversation attributes where possible and add/update only its meat-sales fields.

Required meat snapshot fields:

- `sales_lane`
- `meat_product_type`
- `meat_cut_set`
- `meat_delivery_mode`
- `meat_delivery_town`
- `meat_lead_id`
- `meat_order_id`
- `meat_payment_state`
- `meat_next_gate`
- `meat_followup_due_at`
- `meat_last_customer_intent`

If the conversation also contains normal order fields, backend meat writes must preserve:

- `order_id`
- `order_status`
- `conversation_mode`
- `pending_action`
- `payment_method`
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

These labels exist or are planned in Chatwoot.

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
| `meat_lead` | Backend Sam Meat write. | Meat preorder lane. |
| `half_carcass` | Backend Sam Meat write. | Product marker. |
| `full_carcass` | Backend Sam Meat write. | Product marker. |
| `set_a` | Backend Sam Meat write. | Cut-set marker. |
| `delivery` | Backend Sam Meat write. | Delivery marker. |
| `collection` | Backend Sam Meat write. | Collection marker. |
| `deposit_pending` | Backend Sam Meat/Farm App write. | Payment gate marker. |
| `pop_received_unverified` | Backend Sam Meat/Farm App write. | POP evidence only; does not unlock operations. |
| `deposit_confirmed` | Planned Farm App/backend write. | Bank-confirmed deposit marker. |
| `balance_due` | Planned Farm App/backend write. | Final balance pending. |
| `ready_for_delivery` | Planned Farm App/backend write. | Delivery release gate ready. |
| `needs_followup` | Backend/Farm App write. | Human/system follow-up needed. |
| `lost_lead` | Planned backend/Farm App write. | Buyer dropped or not moving forward. |
| `test_flow` | Backend/Farm App write. | Test data marker for easy cleanup. |

## Label Write Risk

`1.0` currently sends:

- `{"labels": ["warm_lead"]}`
- `{"labels": ["hot_lead"]}`

Before adding more label behavior, live-test whether the Chatwoot labels endpoint appends labels or replaces the complete label set. If it replaces, label writes must preserve all existing labels.

## Current Outstanding Items

- `1.1 Release Conversation to Auto` was live-verified on 2026-04-29 and now writes evaluated values back to Chatwoot.
- Phase 1.3 payment-method preservation was live-verified on 2026-04-29 across normal update, next-turn readback, cancel pending, and escalation release.
- Confirm the Chatwoot label endpoint behavior before expanding labels.
- Phase 11L is implemented: backend-native Sam Meat label/attribute writes preserve existing labels and attributes by fetching the current conversation first.
- Fix `1.3 Patch Conversation Attributes` before enabling media.
- Decide whether contact attributes should become a real memory layer after order lifecycle stabilization.
