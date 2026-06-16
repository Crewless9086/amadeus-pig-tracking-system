# Sam Meat Intake Live Smoke Checklist

## Status

Phase 11C operational setup. The workflow branch exists, but live activation is not complete until this checklist passes.

## Backend Env

Configure in the backend environment:

- `OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_ENABLED=1`
- `OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_TOKEN=<long random token, 32+ chars>`

Do not commit the token.

## n8n Variables

Configure in n8n:

- `SAM_MEAT_INTAKE_HANDOFF_ENABLED=1`
- `SAM_MEAT_INTAKE_REMOTE_TOKEN=<same token as backend>`
- optional `SAM_MEAT_INTAKE_BASE_URL=https://amadeus-pig-tracking-system.onrender.com`

Do not paste the token into workflow JSON.

## Import

Import the repo export:

```text
docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/workflow.json
```

Confirm these nodes exist:

- `Code - Build Sam Meat Intake Payload`
- `IF - Sam Meat Intake Ready`
- `HTTP - Sam Meat Intake Lead`
- `Code - Attach Sam Meat Intake Result`

## Remote Route Smoke

Run the route smoke after backend env is deployed:

```powershell
$env:SAM_MEAT_INTAKE_SMOKE_BASE_URL="https://amadeus-pig-tracking-system.onrender.com"
$env:SAM_MEAT_INTAKE_REMOTE_TOKEN="<token>"
$env:SAM_MEAT_INTAKE_SMOKE_CREATE="1"
.\venv\Scripts\python.exe scripts\sam_meat_intake_remote_smoke.py
```

Expected:

- bad-token check returns `403`
- create returns `success = true`
- lead ID starts with `OSK-SALES-LEAD-`
- `remote_ingest.records_tracking_lead = true`
- `sends_customer_message = false`
- `calls_chatwoot = false`
- `calls_n8n = false`
- `creates_order = false`
- `changes_stock = false`
- `financial_action = false`

## Chatwoot Controlled Smoke

Use one controlled inbound customer-style message, for example:

```text
Hi, I am interested in a half carcass, Set A, Riversdale, next available week. EFT is fine.
```

Expected:

- Sam continues the normal conversation.
- Backend records one tracking-only meat lead.
- Sam does not quote price/kg.
- Sam does not promise an available week.
- Sam does not ask for deposit.
- Sam does not create a preorder/order.
- Sam does not reserve or allocate stock.

## Readback

After the smoke, confirm through the local owner rail:

```text
GET /api/oom-sakkie/sales-leads?status=launch_test
```

or use the Oom Sakkie Ledger Sales Workbench.

The smoke lead should show as owner/Ledger follow-up. If it is only smoke evidence, close it with an append-only lead event after review.

## Stop Conditions

Stop immediately if any of these happen:

- Sam quotes a price/kg without owner confirmation.
- Sam promises timing or availability.
- Sam asks for payment or deposit.
- Any order/preorder is created.
- Any stock is reserved or allocated.
- Chatwoot custom attributes lose existing `order_id`, `order_status`, `conversation_mode`, `pending_action`, or `payment_method`.
