# ORDER_INTAKE_STATE

## Status

Planned for Phase 5.4 / 5.5. This sheet is not live yet.

Do not create or edit this sheet manually until the design is approved and the setup path is implemented.

## Purpose

Backend-owned persistent intake header for natural Sam sales conversations.

One active row should represent one in-progress sales/order intake for a Chatwoot conversation. The row stores confirmed non-item facts, lifecycle state, missing fields, next action, and links to a Draft order and generated quote state.

## Write Ownership

Backend only.

n8n and Sam must call backend endpoints. They must not write this sheet directly.

## Proposed Columns

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `Intake_ID` | string | yes | Stable ID, e.g. `INTAKE-2026-XXXXXX`. |
| `ConversationId` | string | yes | Chatwoot conversation ID. |
| `Account_ID` | string | no | Chatwoot account ID, useful for routing. |
| `Contact_ID` | string | no | Chatwoot contact ID if available. |
| `Customer_Name` | string | yes | Latest known customer name. |
| `Customer_Phone` | string | no | Normalized customer phone when available. |
| `Customer_Channel` | string | no | Example: `Sam - WhatsApp`. |
| `Customer_Language` | string | no | Latest known language. |
| `Draft_Order_ID` | string | no | Linked `ORDER_MASTER.Order_ID` once created. |
| `Intake_Status` | enum | yes | `Open`, `Ready_For_Draft`, `Draft_Created`, `Quote_Requested`, `Quote_Generated`, `Sent_For_Approval`, `Closed`, `Needs_Admin`. |
| `Collection_Location` | enum/string | no | `Riversdale`, `Albertinia`, or `Any` where applicable. |
| `Collection_Time_Text` | string | no | Human text such as `Friday at 14:00`. |
| `Collection_Date` | date | no | Optional parsed date once available. |
| `Collection_Time` | time | no | Optional parsed time once available. |
| `Payment_Method` | enum | no | `Cash` or `EFT`. Required for formal quote generation. |
| `Quote_Requested` | boolean | yes | Whether customer asked for a formal quote. |
| `Order_Commitment` | boolean | yes | Whether customer clearly wants to proceed/order. |
| `Missing_Fields` | string/list | no | Backend-computed missing fields. |
| `Next_Action` | enum | no | Backend-computed command for n8n/Sam. |
| `Ready_For_Draft` | boolean | yes | Backend-computed readiness. |
| `Ready_For_Quote` | boolean | yes | Backend-computed readiness. |
| `Last_Customer_Message` | string | no | Last message used for intake update. |
| `Last_Updated_By` | string | no | Example: `Sam`, `App`, `Admin`. |
| `Created_At` | datetime | yes | Backend timestamp. |
| `Updated_At` | datetime | yes | Backend timestamp. |
| `Closed_At` | datetime | no | Set when status becomes `Closed`. |
| `Closed_Reason` | string | no | Example: `completed`, `cancelled`, `abandoned`, `admin_reset`. |
| `Notes` | string | no | Backend/admin diagnostic notes. |

## Proposed Status Values

- `Open`
- `Ready_For_Draft`
- `Draft_Created`
- `Quote_Requested`
- `Quote_Generated`
- `Sent_For_Approval`
- `Closed`
- `Needs_Admin`

## Proposed Next Action Values

- `ask_missing_field`
- `ask_disambiguation`
- `reply_only`
- `create_draft`
- `update_draft`
- `sync_lines`
- `create_draft_then_quote`
- `update_draft_then_quote`
- `generate_quote`
- `block_requires_admin`

## Rules

- Blank incoming values must not erase known facts.
- Backend computes `Missing_Fields`, `Ready_For_Draft`, `Ready_For_Quote`, and `Next_Action`.
- Chatwoot attributes are not the source of truth for this row.
- Closed rows should remain for audit/history; do not delete them casually.
- Relative collection wording should remain in `Collection_Time_Text`; parsed date/time fields are optional and should be written only when safe or confirmed.
- Abandoned intakes should be closed with `Closed_Reason = abandoned`, not deleted.
