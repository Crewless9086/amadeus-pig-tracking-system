# 1.5 - Outbound Document Delivery

## Role

Backend-triggered workflow that sends generated quote/invoice PDFs to a Chatwoot conversation as attachments.

This workflow is separate from `1.0 - SAM - Sales Agent - Chatwoot`. The backend owns document generation, totals, VAT, references, and `ORDER_DOCUMENTS`. n8n only downloads the already-generated PDF and sends it to Chatwoot.

## Trigger

Webhook called by Flask through `DOCUMENT_DELIVERY_WEBHOOK_URL`.

Suggested production path:

```text
https://charln.app.n8n.cloud/webhook/order-document-delivery
```

Expected payload:

```json
{
  "event_type": "order_document_delivery",
  "account_id": "147387",
  "conversation_id": "1742",
  "document_id": "DOC-2026-45F259",
  "order_id": "ORD-2026-01E18A",
  "document_type": "Quote",
  "document_ref": "Q-2026-01E18A-V3",
  "payment_ref": "01E18A",
  "file_name": "QUO_2026_05_10_01E18A_V3_(R3,680.00)_EFT.pdf",
  "google_drive_file_id": "1V7jW5vu4nbB-JEo2h3_a-gGpYkgIsGZ1",
  "google_drive_url": "https://drive.google.com/file/d/...",
  "message_text": "Please find your quote attached: Q-2026-01E18A-V3",
  "changed_by": "App",
  "trigger_source": "Flask App"
}
```

## Required Behavior

1. Validate `event_type`, `conversation_id`, `google_drive_file_id`, `file_name`, and `message_text`.
2. Download the PDF from Google Drive using authenticated Google Drive access.
3. Send the file to Chatwoot as `attachments[]` with `message_type = outgoing` and `private = false`.
4. Return `{ success: true, sent: true, document_id, conversation_id }` only after Chatwoot send succeeds.

## Safety Rule

For tests, use `conversation_id = 1742` only. Do not use the order's customer conversation for `ORD-2026-01E18A`; it is being used as a test document source.

## Backend Contract

Backend endpoint:

```text
POST /api/order-documents/<document_id>/send
```

Backend requires a `conversation_id` in the request body. It does not fall back to the customer conversation. This prevents accidental customer sends during testing.

Example:

```json
{
  "conversation_id": "1742",
  "sent_by": "Codex Phase 2.5 Test"
}
```

When n8n returns success, backend marks the document as `Sent` in `ORDER_DOCUMENTS`.

## n8n Configuration Notes

- Configure the Google Drive node with an OAuth credential that can read the Amadeus Shared Drive.
- Configure the Chatwoot HTTP node with the Chatwoot API token as a credential or protected value.
- Do not commit real Chatwoot tokens to this repo.
