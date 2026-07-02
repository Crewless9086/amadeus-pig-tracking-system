# Google Sheets Legacy

Google Sheets is legacy/reference/export/fallback unless a route explicitly still uses it.

Formula-driven sheets and sales stock sheets must be treated carefully and should not become hidden write targets.

## Current Role

Google Sheets still contains important operational history and formula views. It is not garbage. It is a legacy/runtime reference layer while Supabase and backend read models finish replacing it.

## Sheet Classes

| Class | Examples | Rule |
| --- | --- | --- |
| Master/source sheets | `PIG_MASTER`, `ORDER_MASTER`, `ORDER_LINES`, `LITTERS` | Backend/admin tooling only; no n8n/agent direct writes. |
| Log/history sheets | `WEIGHT_LOG`, `MEDICAL_LOG`, `MATING_LOG`, `ORDER_STATUS_LOG`, `ORDER_DOCUMENTS`, `LOCATION_HISTORY` | Append/audit-friendly; no casual overwrite. |
| Register/reference sheets | `PEN_REGISTER`, `PRODUCT_REGISTER`, `USERS`, `SALES_PRICING`, `SYSTEM_SETTINGS` | Controlled admin/manual or backend setup. |
| Intake state sheets | `ORDER_INTAKE_STATE`, `ORDER_INTAKE_ITEMS` | Backend-owned until migrated. |
| Formula overview sheets | `PIG_OVERVIEW`, `ORDER_OVERVIEW`, `LITTER_OVERVIEW`, `MATING_OVERVIEW`, `SALES_AVAILABILITY` | Read-only calculated outputs. |
| Sales display sheets | `SALES_STOCK_DETAIL`, `SALES_STOCK_SUMMARY`, `SALES_STOCK_TOTALS` | Read-only display/context; do not treat info rows as sale-ready stock. |

## Hard Rules

- If a formula sheet is wrong, fix the source data or formula, not the displayed output cell.
- `SALES_AVAILABILITY` is the sale gate for live pig availability.
- `SALES_PRICING` is the price source for legacy live-pig orders; AI/n8n must not invent prices.
- Formula/display totals can include information-only rows. Agents must not turn those rows into sale-ready stock.
- n8n must call backend endpoints for order changes rather than writing sheets.
- Backend must validate state and availability before reservations, releases, approvals, rejections, cancellations, and completions.

## Cleanup Direction

- Do not delete legacy sheets or sheet docs until the matching Supabase/backend route is accepted and verified.
- Once a route is fully migrated, keep the sheet docs as archive/reference until owner approves deletion.
- When a sheet becomes read-only/archive, mark that in the source map and migration inventory.

## Source References

- `docs/03-google-sheets/WRITE_OWNERSHIP.md`
- `docs/03-google-sheets/BUSINESS_RULES.md`
- `docs/03-google-sheets/SHEET_SCHEMA.md`
- `docs/03-google-sheets/FORMULA_LOGIC.md`
