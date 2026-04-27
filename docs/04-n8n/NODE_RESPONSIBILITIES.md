# Node Responsibilities

## Purpose

Defines the responsibilities and boundaries for the n8n workflow suite.

## Global Rules

- Each node should do one clear job.
- Normalize, parse, clean, and prepare nodes must not invent business meaning.
- AI agent nodes may reason, but their important outputs must be preserved into dedicated fields before merge points.
- Backend/order actions should go through `1.2 - Amadeus Order Steward` and backend APIs.
- Formula-driven Google Sheets are read surfaces only.

## `1.0 - SAM - Sales Agent - Chatwoot`

### Inbound And Guard Nodes

| Node / group | Responsibility | Must not do |
| --- | --- | --- |
| `Webhook - Chatwoot Trigger` | Receive raw Chatwoot inbound event. | Classify, rewrite, or create order state. |
| `IF - Only Incoming Customer Messages` | Stop outgoing/private/system loops. | Allow non-customer messages into Sam. |
| `Code - Normalize Incoming Message` | Create stable customer, message, account, conversation, contact, and custom attribute fields. | Infer intent or change customer wording. |
| `If - Has Audio Attachment?` + audio nodes | Download/transcribe voice notes and apply transcript. | Lose original Chatwoot IDs or send replies directly. |
| `IF - Has Final Text` | Continue only when there is usable text. | Route empty messages into AI. |
| `Edit - Keep Chatwoot ID's` | Preserve Chatwoot identifiers for downstream calls. | Drop transcript/customer message fields needed later. |
| `Code - Mode Gate` + human lock check | Respect `conversation_mode`. | Let Sam respond while HUMAN lock is active. |

### Context And Classification Nodes

| Node / group | Responsibility | Must not do |
| --- | --- | --- |
| `HTTP - Get Conversation Messages` | Fetch Chatwoot message history. | Become the source of order truth. |
| `Code - Format Chat History` | Format conversation history for AI context. | Change customer intent. |
| Escalation classifier agent | Decide AUTO, CLARIFY, or ESCALATE. | Send customer replies or mutate order data. |
| classifier parse/normalize nodes | Preserve classifier output and create `decision_mode`. | Rewrite classifier meaning without explicit rule. |

### Sales And Reply Nodes

| Node / group | Responsibility | Must not do |
| --- | --- | --- |
| AI Sales Agent | Answer customer using tools and context. | Promise availability, price, or reservation without data/tool support. |
| Sales stock tools | Read sales availability/pricing display sheets. | Write to Google Sheets. |
| Farm info doc tool | Provide farm/business context. | Override sales/order rules. |
| Clean final reply node | Remove tool/debug noise and produce `cleaned_reply`. | Change meaning or weaken the reply. |
| HTTP send reply node | Send `cleaned_reply` to Chatwoot. | Send raw `output` or debug fields. |

### Order Nodes

| Node / group | Responsibility | Must not do |
| --- | --- | --- |
| `Code - Build Order State` | Extract structured order state from the conversation. | Write to sheets or assume backend success. |
| `Switch - Route Order Action` | Route to current supported order actions. | Route unapproved actions from `1.0`. |
| `Set - Draft Order Payload` | Build `create_order` payload. | Include unsupported fields. |
| `Code - Build Enrich Existing Draft Payload` | Build safe `update_order` payload. | Update without `existing_order_id`. |
| `Code - Build Sync Existing Draft Payload` | Build `sync_order_lines_from_request` payload. | Sync without `requested_items[]`. |
| `Call 1.2 - ...` nodes | Execute Order Steward. | Directly write order sheets. |

### Escalation Nodes

| Node / group | Responsibility | Must not do |
| --- | --- | --- |
| escalation handoff sheet append | Store human handoff ticket/context. | Store incomplete Chatwoot account/conversation IDs. |
| Telegram alert node | Notify human of escalation. | Resolve the customer conversation directly. |
| Chatwoot private note/attributes nodes | Record context and lock mode if needed. | Leave HUMAN mode stuck after human reply. |

## `1.1 - SAM - Sales Agent - Escalation Telegram`

| Node / group | Responsibility | Must not do |
| --- | --- | --- |
| Telegram trigger | Receive approved human reply. | Accept unauthorized chats. |
| Parse human reply | Extract ticket ID and human reply text. | Change the human's intended meaning. |
| Get ticket detail | Find matching escalation row. | Guess account/conversation IDs. |
| Polish human reply agent | Clean tone while preserving meaning. | Add promises or facts not provided by human. |
| Chatwoot send reply | Send final human answer to customer. | Send to wrong conversation. |
| Sheet update node | Mark ticket answered/processed. | Lose audit trail. |
| Conversation attributes update | Return conversation to `AUTO`. | Leave customer locked in HUMAN accidentally. |
| Telegram delete node | Clean up Telegram messages when implemented. | Delete unrelated messages. |

## `1.2 - Amadeus Order Steward`

| Node / group | Responsibility | Must not do |
| --- | --- | --- |
| Execute workflow trigger | Accept payload from `1.0`. | Accept ambiguous action payloads without normalization. |
| Normalize payload | Standardize input fields. | Invent order data. |
| Route by action | Select backend operation. | Treat unsupported actions as live for `1.0`. |
| Backend HTTP nodes | Call Flask API endpoints. | Directly edit Google Sheets. |
| Response shaping nodes | Return useful success/error payload. | Hide backend failures. |

Current `1.0` live actions only:

- `create_order`
- `update_order`
- `sync_order_lines_from_request`

## `1.3 - SAM - Sales Agent - Media Tool`

Current status: disabled until fixed and tested.

| Node / group | Responsibility | Must not do |
| --- | --- | --- |
| Execute workflow trigger | Accept media request from Sam. | Run from customer path while disabled. |
| Category/folder mapping | Map `category_key` to Google Drive folder. | Use unknown folders without review. |
| Chatwoot conversation lookup | Read media offset custom attributes. | Overwrite unrelated custom attributes. |
| Google Drive list/download nodes | Select image files. | Expose private/unapproved media. |
| Chatwoot attachment node | Send media to customer. | Send duplicates unintentionally. |
| Offset update node | Update `images_sent_offset_map`. | Reset offsets without reason. |
