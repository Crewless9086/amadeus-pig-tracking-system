# Google Sheets Legacy

Google Sheets is legacy/reference/export/fallback unless a route explicitly still uses it.

Formula-driven sheets and sales stock sheets must be treated carefully and should not become hidden write targets.

## Current Role

Google Sheets still contains important operational history and formula views. It is not garbage. It is a legacy/runtime reference layer while Supabase and backend read models finish replacing it.

Normal application routes must be Supabase-first wherever their domain is
listed as migrated in `SUPABASE_CONTRACTS.md`. A Sheets path in those domains
is compatibility fallback, import/export or administrator tooling; it is not a
second operational authority. A dated migration report cannot prove that a
fallback is still needed or that a historic conflict is still unresolved.

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

Retirement test: `GS-LEGACY-RETIREMENT-V1`, defined in
`10-source-map/TRANSITIONAL_EXIT_TEST_REGISTER.md`. Current status is
`BLOCKED_CURRENT_RUNTIME_DEPENDENCY`; this is a bounded technical exception,
not permission for new Sheets authority.

- Do not delete legacy sheets or sheet docs until the matching Supabase/backend route is accepted and verified.
- Once a route is fully migrated, keep the sheet docs as archive/reference until owner approves deletion.
- When a sheet becomes read-only/archive, mark that in the source map and migration inventory.
- Retire a fallback only after fresh route inventory, exact Supabase read/write
  ownership, shadow equivalence, failure-path coverage, rollback proof and an
  owner-approved stability window. Existing fallback code is not permission to
  route new work through Sheets.

## Source References

- `docs/03-google-sheets/WRITE_OWNERSHIP.md`
- `docs/03-google-sheets/BUSINESS_RULES.md`
- `docs/03-google-sheets/SHEET_SCHEMA.md`
- `docs/03-google-sheets/FORMULA_LOGIC.md`
