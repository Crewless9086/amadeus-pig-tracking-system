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

- quote: `QUO_YYYY_MM_DD_XXXXXX_VN_(R10,580.00)_EFT.pdf`
- invoice: `INV_YYYY_MM_DD_XXXXXX_VN_(R10,580.00)_EFT.pdf`

Examples:

- `QUO_2026_04_15_A99273_V1_(R10,580.00)_EFT.pdf`
- `INV_2026_04_15_A99273_V1_(R10,580.00)_EFT.pdf`

Where:

- `QUO` / `INV` identifies the document type.
- `YYYY_MM_DD` is the document generation date.
- `XXXXXX` is the short order/payment reference.
- `VN` is the document version, for example `V1`.
- `(R10,580.00)` is the final total shown on the document.
- `EFT` / `Cash` is the payment method.

Filename rule: the filename is for human scanning in Google Drive only. Backend must not parse accounting truth from the filename; `ORDER_DOCUMENTS` remains the source for document type, version, totals, payment method, and file IDs.

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

## PDF Generation Approach

Recommended approach for Phase 2.3:

- use ReportLab for backend PDF generation
- build the quote/invoice layout directly in Python using the approved document schema
- keep document data assembly separate from PDF rendering so totals can be tested without parsing PDFs
- add the dependency only when Phase 2.3 implementation begins

Reason:

- no PDF library is currently installed in the project environment
- ReportLab avoids browser/native rendering dependencies
- deterministic table/text layout is a good fit for quote and invoice documents
- invoices need stable totals, not marketing-style HTML rendering

## Google Drive Helper

Backend Drive upload/download support lives in:

- `services/google_drive_service.py`

The helper uses the existing service-account credentials and Drive scope already configured for Google Sheets. It supports:

- upload by local file path and target folder ID
- download by file ID for authenticated attachment workflows
- metadata lookup by file ID

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

## Confirmed Decisions

1. `SYSTEM_SETTINGS` should be created by an admin setup script or backend setup utility, not manually typed row by row.
2. `ORDER_DOCUMENTS` should be created by an admin setup script or backend setup utility, not manually typed row by row.
3. Google Drive folder IDs:
   - quote Shared Drive folder: `1r7oqIDMwZZi5T7BxC31y7UGNzn8Ud9ys`
   - invoice Shared Drive folder: `1_kbfX69s6yeb-Zfdcpu5jse8H30HvLGr`
4. Customer delivery should send the generated PDF as a Chatwoot attachment through n8n, not only a public link.
5. Quote versioning should be included in the first implementation.
6. Invoice generation should require an existing generated quote first. The customer should see the quote before an invoice is generated.
7. Invoice generation should use the latest non-voided quote version for the order.
8. Quote generation is allowed while an order is still `Draft`.
9. n8n can be given authenticated Google Drive access to download generated PDFs by file ID.
10. Draft quotes should show a visible note: `Draft quote - subject to availability and approval`.

## Google Drive Permission Strategy

Recommended first implementation:

- uploaded PDFs stay restricted in Google Drive
- backend stores `Google_Drive_File_ID` and `Google_Drive_URL` in `ORDER_DOCUMENTS`
- n8n uses authenticated Google Drive access to download the generated PDF by file ID
- n8n sends the downloaded PDF as a Chatwoot attachment
- do not make quote/invoice PDFs public by default

Reason:

- customers receive the PDF directly as an attachment
- old quotes/invoices remain retrievable by the business
- sensitive customer/order documents are not exposed through public links
- `ORDER_DOCUMENTS` remains the lookup source if a customer asks for an old document

Phase 2.2 live upload finding:

- Sharing the quote folder with the service account fixed the folder access issue.
- Uploading from the backend service account to a normal My Drive folder then failed with Google Drive `403`: service accounts do not have storage quota.
- Resolution selected: use Google Shared Drive folders created from the Amadeus Workspace account, with the service account added as content manager.
- Live Shared Drive upload test passed on 2026-05-10. Test file: `PHASE_2_2_SHARED_DRIVE_UPLOAD_TEST.txt`; file ID: `17HtPAumE9XJf2e8xtvQsTb0YpwCtEncI`.

Backend Drive API calls must include Shared Drive support (`supportsAllDrives=true`) for upload, download, and metadata lookup.

## Remaining Open Questions Before Implementation

None for Phase 2.1 design. Implementation can proceed to sheet setup planning and backend endpoint planning.

## Proposed Rollout

1. Phase 2.2: document and create `SYSTEM_SETTINGS` and `ORDER_DOCUMENTS` through `scripts/setup_document_infrastructure.py`. - Done 2026-05-09
2. Phase 2.2: move/copy canonical logo asset to `static/document-assets/amadeus-logo.png`. - Done
3. Phase 2.2: implement backend settings/document-register helpers in `modules/documents/document_service.py`. - Done
4. Phase 2.3: implement quote generation endpoint with `V1`, `V2`, etc. - Done
5. Phase 2.3: live-test quote generation on one safe order. - Done; Cash, V2, and EFT/VAT paths verified
6. Phase 2.4: implement invoice generation endpoint, requiring an existing non-voided quote. - Done
7. Phase 2.4: live-test invoice generation on one approved safe order. - Done
8. Phase 2.5: add n8n attachment delivery only after document generation is stable.
