# Backend Module Structure

## Purpose

Documents the current backend order module layout and the intended ownership boundaries.

## Current Runtime Structure

```text
app.py
  registers orders_bp under /api

modules/orders/
  order_routes.py
  order_service.py
  order_validation.py

services/
  google_sheets_service.py
```

## Current File Responsibilities

| File | Current responsibility |
| --- | --- |
| `app.py` | Flask app setup, blueprint registration, and HTML page routes. |
| `modules/orders/order_routes.py` | Flask JSON routes for orders and order lines. |
| `modules/orders/order_validation.py` | Payload validation and cleanup for create/update/sync/order-line requests. |
| `modules/orders/order_service.py` | Large service containing sheet constants, order reads, writes, matching, sync, reservation, lifecycle, completion, logging, and n8n webhook notification. |
| `services/google_sheets_service.py` | Shared low-level Google Sheets reads/writes. |

## Current Concern

`order_service.py` is too broad. It mixes:

- sheet access
- order CRUD
- requested item matching
- order line sync
- reservation/release
- approval/rejection/completion
- status logging
- n8n notification

This makes bugs like split-item sync or reject-without-release harder to isolate.

## Intended Future Structure

Future refactor should preserve routes and behavior while splitting by concern:

```text
modules/orders/
  order_routes.py
  order_validation.py
  order_service.py              # thin compatibility facade
  order_read.py
  order_write.py
  order_matching.py
  order_line_sync.py
  order_reservation.py
  order_lifecycle.py
  order_status_log.py
  integrations/
    n8n_orders.py
```

## Ownership Boundaries

| Area | Owner file after refactor |
| --- | --- |
| list/detail/available pigs reads | `order_read.py` |
| create/update order headers | `order_write.py` |
| pricing/category/pig matching | `order_matching.py` |
| requested item to line sync | `order_line_sync.py` |
| reserve/release | `order_reservation.py` |
| approve/reject/cancel/complete | `order_lifecycle.py` |
| status audit logging | `order_status_log.py` |
| n8n webhook notification | `integrations/n8n_orders.py` |

## Refactor Rule

Do not split code until the current behavior is documented and a focused test/manual verification checklist exists for the affected path.
