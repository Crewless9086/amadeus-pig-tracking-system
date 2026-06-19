# Meat Sales WhatsApp Templates

Pilot status: not yet created in Meta/WhatsApp Manager.

Purpose: approved templates are needed when the 24-hour WhatsApp customer-service window is closed. Sam must not assume a normal PDF/message was delivered if WhatsApp blocks it. The backend now blocks stale-window document sends and waits for template recovery first.

## Pilot Templates To Create

| Priority | Template key | Category | When Sam uses it | Suggested body | Variables |
|---|---|---|---|---|---|
| 1 | `amadeus_meat_quote_ready` | Utility | Estimated quote PDF is ready, but the 24-hour window is closed. | `Hi {{1}}, your Amadeus Farm pork estimate is ready. Please reply YES and I will send the quote details.` | `{{1}}` customer first name |
| 2 | `amadeus_meat_deposit_followup` | Utility | Deposit/pro-forma was sent earlier and no bank-confirmed payment is logged yet. | `Hi {{1}}, we are holding your Amadeus Farm pork preorder under reference {{2}}. Please reply here if you have made payment or need help.` | `{{1}}` customer first name, `{{2}}` payment reference |
| 3 | `amadeus_meat_booking_update` | Utility | Abattoir/butcher timing is confirmed after the window closes. | `Hi {{1}}, we have an update on your Amadeus Farm pork booking {{2}}. Please reply YES and I will send the details.` | `{{1}}` customer first name, `{{2}}` payment reference |
| 4 | `amadeus_meat_delivery_update` | Utility | Delivery route/date update must be sent after the window closes. | `Hi {{1}}, your Amadeus Farm pork delivery update for reference {{2}} is ready. Please reply YES and I will send the latest details.` | `{{1}}` customer first name, `{{2}}` payment reference |
| 5 | `amadeus_meat_final_invoice_ready` | Utility | Final packed weight/final invoice is ready and the window is closed. | `Hi {{1}}, your final Amadeus Farm pork invoice for reference {{2}} is ready. Please reply YES and I will send it through.` | `{{1}}` customer first name, `{{2}}` payment reference |

## Later Setup Checklist

- Create the templates in Meta/WhatsApp Manager under the Amadeus WhatsApp account.
- Keep the exact template names above unless the backend envs are updated to match.
- Set `MEAT_SALES_QUOTE_READY_TEMPLATE_NAME=amadeus_meat_quote_ready` once approved.
- Set `MEAT_SALES_DEPOSIT_FOLLOWUP_TEMPLATE_NAME=amadeus_meat_deposit_followup` once approved.
- Set `MEAT_SALES_BOOKING_UPDATE_TEMPLATE_NAME=amadeus_meat_booking_update` once approved.
- Set `MEAT_SALES_DELIVERY_UPDATE_TEMPLATE_NAME=amadeus_meat_delivery_update` once approved.
- Set `MEAT_SALES_FINAL_INVOICE_TEMPLATE_NAME=amadeus_meat_final_invoice_ready` once approved.
- Keep `MEAT_SALES_QUOTE_READY_TEMPLATE_LANGUAGE=en` unless Meta approves a different language code.
- Test each template against Charl's own WhatsApp first before using it for live buyers.

## Current Backend Behavior

- `GET /api/sales/meat-whatsapp-templates` returns the machine-readable pilot template pack, configured env names, missing envs, and exact suggested bodies.
- If the quote PDF send is inside the 24-hour service window, Chatwoot may accept the send.
- Chatwoot acceptance is recorded as unverified until a delivery-status webhook confirms `delivered` or `read`.
- If the window is closed or unknown, the backend returns `estimated_quote_template_required` and does not send the PDF.
- If a later delivery webhook reports `failed`, `undelivered`, or `bounced`, the lead receives a failure event for owner/system recovery.
