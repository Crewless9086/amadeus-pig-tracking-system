# Quote And Invoice Design

## Purpose

Defines the Phase 2 document-generation design before implementation.

This is a planning document. It does not mean the sheets, endpoints, Google Drive folders, or logo assets have been changed yet.

## Source Samples

The current visual samples are in Google Sheets:

- `QUOTE GENERATE`
- `INVOICE GENERATE`

Observed shared layout:

- Amadeus Farm header and contact details
- document type block (`QUOTE` or `INVOICE`)
- document reference and date
- bill-to block
- order details block
- grouped line descriptions and amounts
- subtotal, VAT, and total
- bank details
- collection notes: location, date, time
- short payment reference based on the order suffix

## Ownership

Backend should generate quote and invoice documents.

Rationale:

- backend owns order truth, payment method, line prices, status guards, and audit writes
- totals and VAT must be deterministic and testable
- n8n should not calculate accounting values
- n8n should only deliver documents after backend generation succeeds

## Document Types

### Quote

Allowed from:

- `Pending_Approval`
- `Approved`

Preferred use:

- customer-facing commercial summary before or around approval
- can be regenerated as a new version if order details change while still allowed

### Invoice

Allowed from:

- `Approved`
- later states after approval, unless a future rule blocks it

Preferred use:

- customer-facing payment/sale document once the order is accepted

## References

Use two separate references.

### Document Reference

Purpose: admin, accounting, document lookup, Google Drive filename, and `ORDER_DOCUMENTS` metadata.

Format:

- quote: `Q-YYYY-XXXXXX`
- invoice: `INV-YYYY-XXXXXX`

Where:

- `YYYY` is the order year
- `XXXXXX` is the suffix of `Order_ID`

Example:

- `Q-2026-36CDE4`
- `INV-2026-36CDE4`

If multiple versions are needed:

- `Q-2026-36CDE4-V1`
- `Q-2026-36CDE4-V2`

### Payment Reference

Purpose: customer EFT/banking app reference.

Format:

- `XXXXXX`

Example:

- `36CDE4`

Document wording:

- `Use Reference: 36CDE4`

Reason: the payment reference should stay short and easy to enter in banking apps, while the document reference remains unique and searchable.

## Configurable Settings

Create a future register/reference sheet:

- `SYSTEM_SETTINGS`

Suggested columns:

| Column | Purpose |
| --- | --- |
| `Setting_Key` | Stable setting key used by backend. |
| `Setting_Value` | Current value. |
| `Description` | Human explanation. |
| `Updated_At` | Last update date/time. |
| `Updated_By` | Actor/admin who changed it. |

Initial settings:

| Setting_Key | Example Value | Purpose |
| --- | --- | --- |
| `quote_valid_days` | `3` | Quote expiry offset. |
| `vat_rate` | `0.15` | VAT rate used for EFT documents. |
| `business_name` | `AMADEUS FARM` | Document header. |
| `business_address_line_1` | `Swartklip Road` | Document header. |
| `business_address_line_2` | `Riversdale, 6670` | Document header. |
| `business_address_line_3` | `Western Cape` | Document header. |
| `business_phone` | `084-567-9327` | Document header. |
| `business_email` | `amadeusfarm572@gmail.com` | Document header. |
| `business_vat_number` | `4510286224` | Document header. |
| `bank_name` | `First National Bank (FNB)` | Bank details. |
| `bank_account_name` | `Charl Nieuwendyk` | Bank details. |
| `bank_account_type` | `Cheque Account` | Bank details. |
| `bank_account_number` | `62315222711` | Bank details. |
| `bank_branch_code` | `250655` | Bank details. |
| `document_drive_root_folder_id` | blank until configured | Google Drive root folder. |
| `quote_drive_folder_id` | blank until configured | Optional quote folder override. |
| `invoice_drive_folder_id` | blank until configured | Optional invoice folder override. |

Backend should apply safe defaults only for non-sensitive formatting values. Folder IDs and bank details should be treated as required configuration before production document generation.

## Document Register

Create a future log/register sheet:

- `ORDER_DOCUMENTS`

Suggested columns:

| Column | Purpose |
| --- | --- |
| `Document_ID` | Stable generated ID, for example `DOC-2026-XXXXXX`. |
| `Order_ID` | Linked order. |
| `Document_Type` | `Quote` or `Invoice`. |
| `Document_Ref` | Full document reference. |
| `Payment_Ref` | Short EFT reference. |
| `Version` | Version number. |
| `Document_Status` | `Generated`, `Sent`, `Voided`, `Superseded`. |
| `Payment_Method` | `Cash` or `EFT` at generation time. |
| `VAT_Rate` | Locked VAT rate used. |
| `Subtotal_Ex_VAT` | Line subtotal before VAT. |
| `VAT_Amount` | VAT amount. |
| `Total` | Final total shown. |
| `Valid_Until` | Quote expiry date; blank for invoice unless needed. |
| `Google_Drive_File_ID` | Stored file ID. |
| `Google_Drive_URL` | Share/link URL. |
| `Created_At` | Generation timestamp. |
| `Created_By` | Actor/admin/system. |
| `Sent_At` | Delivery timestamp, if sent. |
| `Sent_By` | Actor/workflow that sent it. |
| `Notes` | Manual/system notes. |

## VAT And Totals

Line prices are treated as ex-VAT unit prices.

Rules:

- `Cash`: VAT amount is `0`; total equals subtotal.
- `EFT`: VAT amount is `subtotal * vat_rate`; total equals subtotal plus VAT.
- VAT rate must be locked on the document record at generation time.
- Invoice should use the VAT rate/totals locked on the corresponding quote when generated from an existing quote. If no quote exists, invoice locks its own values at invoice generation time.

## Line Grouping

Document lines should group active order lines by:

- sale category
- weight band
- sex
- unit price

Description format:

- `1x Grower Pigs (20-24kg) @ R800 each (Male)`
- `2x Grower Pigs (30-34kg) @ R1200 each (Female)`

Only non-cancelled lines should appear on generated documents.

Open implementation check:

- confirm `ORDER_LINES.Unit_Price` is populated for all lines that can be quoted/invoiced
- if a line has missing unit price, document generation must fail clearly instead of creating a misleading total

## Google Drive Storage

Generated PDFs should be uploaded to Google Drive.

Preferred folder shape:

- `Amadeus Documents/Quotes/YYYY/`
- `Amadeus Documents/Invoices/YYYY/`

Backend should store the returned file ID and URL in `ORDER_DOCUMENTS`.

File naming:

- quote: `Q-2026-36CDE4 - ORD-2026-36CDE4.pdf`
- invoice: `INV-2026-36CDE4 - ORD-2026-36CDE4.pdf`

## Logo And Assets

Uploaded logo files currently exist in the repo root:

- `Amadeus_Logo.png`
- `Amadeus_Logo.jpg`
- `Amadeus_Logo.pdf`

Recommended canonical runtime asset:

- `static/document-assets/amadeus-logo.png`

The PNG should be used for generated PDFs. The JPG/PDF can remain source/reference assets unless a later rendering tool needs a different format.

No logo files have been moved yet.

## Backend Endpoints

Planned endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/orders/<order_id>/quote` | Generate quote PDF, upload to Drive, record metadata. |
| `POST` | `/api/orders/<order_id>/invoice` | Generate invoice PDF, upload to Drive, record metadata. |
| `GET` | `/api/orders/<order_id>/documents` | List generated quote/invoice records for an order. |

Potential later endpoint:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/order-documents/<document_id>/send` | Ask n8n to deliver an existing generated document. |

## n8n Role

n8n should deliver documents only after backend generation succeeds.

Allowed responsibilities:

- receive document URL/file reference from backend
- send document/link to Chatwoot
- update `ORDER_DOCUMENTS.Sent_At` through backend endpoint, not by writing sheets directly

Not allowed:

- calculate VAT
- calculate totals
- decide invoice eligibility
- create document references independently

## Open Questions Before Implementation

1. Confirm whether `SYSTEM_SETTINGS` should be created manually first or created by an admin setup script. - Yes, If you think this is quicker and easier then me doing it manually. 
2. Confirm whether `ORDER_DOCUMENTS` should be created manually first or created by an admin setup script. - Yes
3. Confirm Google Drive folder IDs for the document root/quote/invoice folders. - I have created this files in drive
QUOTE - https://drive.google.com/drive/folders/1gbQuDtvkRo1SnpZTeI587nhRnkZPx7cp
INVOICE - https://drive.google.com/drive/folders/1h2uyOndhAgngzFDVQYqBhrqfxL0zw5TI
4. Confirm whether generated PDFs should be publicly link-accessible, restricted to account users, or sent as attachments by n8n. - Send as an attachement by n8n
5. Confirm whether quote versioning should be enabled in the first implementation or reserved for a later phase. - Can implement it now, why not.
6. Confirm whether invoice generation should require an existing quote or allow direct invoice generation from an approved order. - I think a quote needs to be generated 1st so the client can see this and approve it once they view it.

## Proposed Rollout

1. Finalize this design document.
2. Create/document `SYSTEM_SETTINGS` and `ORDER_DOCUMENTS` sheets.
3. Move/copy canonical logo asset to `static/document-assets/amadeus-logo.png`.
4. Implement backend settings/document-register helpers.
5. Implement quote generation endpoint.
6. Live-test quote generation on one safe order.
7. Implement invoice generation endpoint.
8. Live-test invoice generation on one approved safe order.
9. Add n8n delivery only after document generation is stable.
