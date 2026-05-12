# ORDER_INTAKE_ITEMS

## Status

Planned for Phase 5.4 / 5.5. This sheet is not live yet.

Do not create or edit this sheet manually until the design is approved and the setup path is implemented.

## Purpose

Backend-owned item rows for persistent order intake.

This sheet allows one conversation intake to contain multiple requested products, such as:

- 1 female grower in `35_to_39_Kg`
- 2 piglets in `5_to_6_Kg`
- split male/female requests
- add-ons
- nearby-band alternatives
- removed/replaced item history

Only active rows should be sent to the existing order-line sync endpoint.

## Write Ownership

Backend only.

n8n and Sam must call backend endpoints. They must not write this sheet directly.

## Proposed Columns

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `Intake_Item_ID` | string | yes | Stable row ID, e.g. `INTAKEITEM-2026-XXXXXX`. |
| `Intake_ID` | string | yes | Links to `ORDER_INTAKE_STATE.Intake_ID`. |
| `ConversationId` | string | yes | Duplicated for easier lookup/debugging. |
| `Item_Key` | string | yes | Stable key used for sync, e.g. `item_1`, `item_2`. |
| `Quantity` | number | yes for active | Whole number requested quantity. |
| `Category` | enum | yes for active | `Piglet`, `Weaner`, `Grower`, `Finisher`, `Slaughter`. |
| `Weight_Range` | enum | yes for active | Stored value such as `35_to_39_Kg`. |
| `Sex` | enum | no | `Male`, `Female`, or `Any`. |
| `Intent_Type` | enum | yes | Aligns with existing sync metadata. |
| `Status` | enum | yes | `active`, `removed`, or `replaced`. |
| `Linked_Order_Line_IDs` | string/list | no | Order line IDs created from this item after sync. |
| `Last_Match_Status` | string | no | Latest sync result: `exact_match`, `partial_match`, `no_match`, etc. |
| `Matched_Quantity` | number | no | Latest quantity matched into order lines. |
| `Replaced_By_Item_Key` | string | no | Set when this row is replaced by a newer item. |
| `Removal_Reason` | string | no | Short reason when customer removes/replaces the item. |
| `Notes` | string | no | Backend/admin notes. |
| `Created_At` | datetime | yes | Backend timestamp. |
| `Updated_At` | datetime | yes | Backend timestamp. |
| `Removed_At` | datetime | no | Set when status becomes `removed` or `replaced`. |

## Proposed Intent Type Values

- `primary`
- `addon`
- `nearby_addon`
- `extractor_slot`

These align with the existing `sync_order_lines_from_request` metadata.

## Proposed Status Values

- `active`
- `removed`
- `replaced`

## Rules

- `Item_Key` must remain stable once created.
- Removed or replaced rows should not be deleted; keep them for conversation history.
- Removed/replaced rows should carry `Removed_At` and, where possible, `Removal_Reason` or `Replaced_By_Item_Key`.
- Only `active` rows should be transformed into `requested_items[]` for backend order-line sync.
- If an edit is ambiguous, backend should not guess. It should return `Next_Action = ask_disambiguation`.
- Existing Draft orders can be updated from active intake items.
- Approved, reserved, completed, or cancelled orders should not be automatically changed from intake items.
