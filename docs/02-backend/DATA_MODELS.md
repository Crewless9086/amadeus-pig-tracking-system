# Backend Data Models

## Purpose

Defines the backend-facing order fields and how they relate to Google Sheets and n8n payloads.

## `ORDER_MASTER`

Primary order header sheet.

Important fields:

| Field | Backend meaning |
| --- | --- |
| `Order_ID` | Stable order identifier. |
| `Order_Date` | Date order was created. |
| `Customer_Name` | Customer name. |
| `Customer_Phone` | Customer phone/contact value. |
| `Customer_Channel` | Source channel such as Chatwoot/WhatsApp. |
| `Customer_Language` | Customer language. |
| `Order_Source` | Source actor/system, for example `Sam` or `App`. |
| `Requested_Category` | Header-level requested sale category. |
| `Requested_Weight_Range` | Header-level requested weight band/range. |
| `Requested_Sex` | Header-level sex preference. Use `Any` for mixed split requests; exact sex quantities belong on `ORDER_LINES` via `requested_items[]`. |
| `Requested_Quantity` | Header-level requested quantity. |
| `Quoted_Total` | Quoted amount if known. |
| `Final_Total` | Final amount if known. |
| `Order_Status` | Draft, pending, approved, cancelled, completed-style lifecycle state. |
| `Approval_Status` | Approval state. Use `Rejected` for human/admin rejection and `Not_Required` for customer cancellation. |
| `Collection_Method` | Collection mode. No delivery promise unless business rules change. |
| `Collection_Location` | Approved collection location. |
| `Collection_Date` | Planned collection date. |
| `Payment_Status` | Payment state. |
| `Reserved_Pig_Count` | Count of reserved pigs/lines for the order. |
| `Notes` | Human/system notes. |
| `Created_By` | Creator. |
| `Created_At` | Created timestamp. |
| `Updated_At` | Updated timestamp. |
| `Payment_Method` | Cash/EFT value used for approval validation and VAT treatment. |
| `ConversationId` | Chatwoot conversation ID stored from incoming `conversation_id` for outbound approval/rejection notifications. This is written during draft creation, including first-turn `create_order_with_lines`. |

## `ORDER_LINES`

Line-level order sheet.

Important fields:

| Field | Backend meaning |
| --- | --- |
| `Order_Line_ID` | Stable order line identifier. |
| `Order_ID` | Parent order ID. |
| `Pig_ID` | Reserved/matched pig ID. |
| `Tag_Number` | Pig tag display value. |
| `Sale_Category` | Customer-facing sale category. |
| `Weight_Band` | Standard weight band. |
| `Sex` | Pig sex. |
| `Current_Weight_Kg` | Current matched pig weight. |
| `Unit_Price` | Unit price from pricing/matching logic. |
| `Line_Status` | Draft/reserved/cancelled/collected-style line state. |
| `Reserved_Status` | Reservation state. |
| `Notes` | Notes. |
| `Created_At` | Created timestamp. |
| `Updated_At` | Updated timestamp. |
| `Request_Item_Key` | Stable key linking line rows to requested item splits. |

## `ORDER_STATUS_LOG`

Audit sheet for order lifecycle events.

Important fields:

- order ID
- previous status
- new status
- changed by
- changed at
- notes/reason where available

Required direction:

- reject and cancel must log status changes
- future release/cancel actions should log enough detail to debug reservation changes

## n8n `requested_items[]`

`requested_items[]` is the structured payload from `1.0` through `1.2` to backend sync.

Fields:

| Field | Meaning |
| --- | --- |
| `request_item_key` | Stable item key such as `primary_1` or `primary_2`. |
| `category` | Requested sale category. |
| `weight_range` | Requested `Weight_Band`. |
| `sex` | Requested sex split. |
| `quantity` | Quantity for that requested item. |
| `intent_type` | Optional n8n source label. Allowed values: `primary`, `addon`, `nearby_addon`, `extractor_slot`. It is validated for payload hygiene but does not change matching behavior. |
| `status` | Optional item status. Defaults to `active`; backend sync only accepts `active`. Inactive requested items are not supported and must be omitted by the caller. |
| `notes` | Notes for the requested split. |

## Status Model Notes

Current code expresses rejection as:

- `Order_Status = Cancelled`
- `Approval_Status = Rejected`

Customer cancellation standard: `Order_Status = Cancelled`, `Approval_Status = Not_Required`, and `Payment_Status = Cancelled`.

## Known Model Risks

- `Request_Item_Key` must be stable or split-item sync can fail.
- `Reserved_Status` and `Line_Status` can drift if reservation/release/cancel logic is not handled together.
- `intent_type` is metadata only and must not be used as a substitute for `request_item_key`.
- `status` is deliberately restricted to `active`; callers must omit inactive/cancelled requested items instead of sending them to backend sync.
