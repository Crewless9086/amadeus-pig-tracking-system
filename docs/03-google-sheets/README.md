# Google Sheets Documentation

## Purpose

This folder is the source of truth for the Google Sheets layer of the Amadeus Pig Tracking and Sales System.

It explains:

- which sheets exist
- which sheets are writable
- which sheets are formula-driven read views
- which sheets are used by the backend, n8n, AI agents, and the web app
- where columns, formulas, and ownership rules are documented

## Folder Map

| File or folder | Purpose |
| --- | --- |
| `SHEET_SCHEMA.md` | System-level list of sheets, roles, and relationships. |
| `WRITE_OWNERSHIP.md` | Defines which layer may write to each sheet. |
| `FORMULA_LOGIC.md` | Explains formula chains and derived sheet behavior. |
| `FIELD_DEFINITIONS.md` | Defines important shared fields and allowed values. |
| `BUSINESS_RULES.md` | Business rules that protect sales, orders, stock, and sheet integrity. |
| `SHEET_CHANGELOG.md` | Tracks approved sheet changes. |
| `sheets/` | One file per Google Sheet, including columns, formulas, and notes. |

## Sheet Files

The current documented Google Sheets are:

| Sheet | Type | File |
| --- | --- | --- |
| `PIG_MASTER` | Master/source-of-truth | `sheets/PIG_MASTER.md` |
| `ORDER_MASTER` | Master/source-of-truth | `sheets/ORDER_MASTER.md` |
| `ORDER_LINES` | Master/source-of-truth | `sheets/ORDER_LINES.md` |
| `LITTERS` | Master/source-of-truth | `sheets/LITTERS.md` |
| `WEIGHT_LOG` | Log/history | `sheets/WEIGHT_LOG.md` |
| `MEDICAL_LOG` | Log/history | `sheets/MEDICAL_LOG.md` |
| `MATING_LOG` | Transaction/breeding source | `sheets/MATING_LOG.md` |
| `ORDER_STATUS_LOG` | Audit log | `sheets/ORDER_STATUS_LOG.md` |
| `LOCATION_HISTORY` | Log/history | `sheets/LOCATION_HISTORY.md` |
| `PEN_REGISTER` | Register/reference | `sheets/PEN_REGISTER.md` |
| `PRODUCT_REGISTER` | Register/reference | `sheets/PRODUCT_REGISTER.md` |
| `USERS` | User/admin register | `sheets/USERS.md` |
| `SALES_PRICING` | Manual pricing table | `sheets/SALES_PRICING.md` |
| `SYSTEM_SETTINGS` | Register/reference | `sheets/SYSTEM_SETTINGS.md` |
| `ORDER_DOCUMENTS` | Document register | `sheets/ORDER_DOCUMENTS.md` |
| `PIG_OVERVIEW` | Formula overview | `sheets/PIG_OVERVIEW.md` |
| `MATING_OVERVIEW` | Formula overview | `sheets/MATING_OVERVIEW.md` |
| `LITTER_OVERVIEW` | Formula overview | `sheets/LITTER_OVERVIEW.md` |
| `ORDER_OVERVIEW` | Formula overview | `sheets/ORDER_OVERVIEW.md` |
| `SALES_AVAILABILITY` | Formula sales gate | `sheets/SALES_AVAILABILITY.md` |
| `SALES_STOCK_DETAIL` | Formula sales display | `sheets/SALES_STOCK_DETAIL.md` |
| `SALES_STOCK_SUMMARY` | Formula sales display | `sheets/SALES_STOCK_SUMMARY.md` |
| `SALES_STOCK_TOTALS` | Formula sales display | `sheets/SALES_STOCK_TOTALS.md` |

## Planned Sheet Files

These sheets are documented for upcoming phases but are not live until the matching implementation/setup phase is approved and run.

| Sheet | Planned Phase | File |
| --- | --- | --- |
| `ORDER_INTAKE_STATE` | Phase 5.5 backend-owned intake state | `sheets/ORDER_INTAKE_STATE.md` |
| `ORDER_INTAKE_ITEMS` | Phase 5.5 backend-owned intake item rows | `sheets/ORDER_INTAKE_ITEMS.md` |

## Core Rules

- Master, log, register, pricing, and user/admin sheets are the only write targets.
- Formula overview sheets and sales stock display sheets are read-only.
- If a formula sheet looks wrong, fix the source data or the formula, not the calculated output cell.
- AI agents and n8n workflows must not invent availability, pricing, or reservation state.
- Backend logic is responsible for safe operational writes and data integrity checks.

## Maintenance Rule

When a Google Sheet changes, update the matching file under `sheets/`, then update any affected folder-level docs and add an entry to `SHEET_CHANGELOG.md`.
