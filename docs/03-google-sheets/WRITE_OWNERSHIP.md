# Write Ownership

## Purpose

This document defines which system component may write to each Google Sheet.

## Hard Rule

Formula-driven sheets must not be written to by n8n, AI agents, or backend code. They may be read by the web app, backend, n8n, and AI agents.

## Ownership Table

| Sheet | Write owner | Read owner | Notes |
| --- | --- | --- | --- |
| `PIG_MASTER` | Backend/admin tooling | Backend, web app, formula sheets | Main pig data. Backend should own operational updates such as status, on-farm state, sale purpose, and order completion effects. |
| `ORDER_MASTER` | Backend | Backend, n8n, web app, formula sheets | Order headers. n8n should call backend endpoints, not write directly. |
| `ORDER_LINES` | Backend | Backend, n8n, web app, formula sheets | Order line and reservation state. Reservation/release must be backend-controlled. |
| `LITTERS` | Backend/admin tooling | Backend, web app, formula sheets | Litter source records. |
| `WEIGHT_LOG` | Backend/admin tooling | Backend, web app, formula sheets | Append weight entries; do not overwrite historical entries casually. |
| `MEDICAL_LOG` | Backend/admin tooling | Backend, web app, formula sheets | Append treatment entries and withdrawal information. |
| `MATING_LOG` | Backend/admin tooling | Backend, web app, formula sheets | Breeding transaction records. |
| `ORDER_STATUS_LOG` | Backend | Backend, web app, formula sheets | Append-only audit trail for order status changes. |
| `ORDER_DOCUMENTS` | Backend | Backend, web app, n8n | Quote/invoice document register. n8n should call backend endpoints to update sent state, not write directly. |
| `LOCATION_HISTORY` | Backend/admin tooling | Backend, web app, formula sheets | Pig movement history. |
| `PEN_REGISTER` | Admin tooling/manual | Backend, web app | Reference list of pens. |
| `PRODUCT_REGISTER` | Admin tooling/manual | Backend, web app | Product and withdrawal defaults. |
| `USERS` | Controlled admin/manual | Backend, web app | User/access data. Not fully automated unless later approved. |
| `SALES_PRICING` | Admin/manual pricing owner | Backend, n8n, AI, web app | Pricing source. AI must never invent prices. |
| `SYSTEM_SETTINGS` | Backend setup utility/admin tooling | Backend, web app | Configurable settings for document generation. Stable setting keys must not be renamed casually. |
| `PIG_OVERVIEW` | Formula only | Backend, web app, n8n, AI | Read-only calculated pig state. |
| `MATING_OVERVIEW` | Formula only | Backend, web app | Read-only calculated breeding state. |
| `LITTER_OVERVIEW` | Formula only | Backend, web app | Read-only calculated litter state. |
| `ORDER_OVERVIEW` | Formula only | Backend, web app, n8n | Read-only calculated order display. |
| `SALES_AVAILABILITY` | Formula only | Backend, n8n, AI, web app | Read-only sales eligibility gate. |
| `SALES_STOCK_DETAIL` | Formula only | n8n, AI, web app | Read-only sales display. |
| `SALES_STOCK_SUMMARY` | Formula only | n8n, AI, web app | Read-only sales display. |
| `SALES_STOCK_TOTALS` | Formula only | n8n, AI, web app | Read-only sales display. |

## Direct n8n Write Rule

n8n should not directly edit operational Google Sheets. It should call backend endpoints for order creation, update, reservation, release, cancellation, approval, rejection, and completion.

## Manual Edit Rule

Manual edits should be limited to admin/register/pricing corrections or controlled data fixes. Formula outputs should not be manually edited.
