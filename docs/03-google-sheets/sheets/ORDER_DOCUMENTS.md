# ORDER_DOCUMENTS.md

## Role

Document register for generated quote and invoice PDFs.

This sheet tracks generated document metadata, Google Drive file references, totals, status, version, and delivery state. It is the source of truth for finding old quotes/invoices.

## Write Ownership

Backend.

n8n must not write this sheet directly. n8n should call backend endpoints to mark delivery/sent state after sending documents.

## Columns

Document_ID	Order_ID	Document_Type	Document_Ref	Payment_Ref	Version	Document_Status	Payment_Method	VAT_Rate	Subtotal_Ex_VAT	VAT_Amount	Total	Valid_Until	Google_Drive_File_ID	Google_Drive_URL	File_Name	Created_At	Created_By	Sent_At	Sent_By	Notes

## Column Style And Values

Document_ID	DOC-YYYY-######
Order_ID	ORD-YYYY-######
Document_Type	Quote or Invoice
Document_Ref	full document reference, e.g. Q-2026-36CDE4 or INV-2026-36CDE4
Payment_Ref	short customer EFT reference, e.g. 36CDE4
Version	integer version number
Document_Status	Generated, Sent, Voided, or Superseded
Payment_Method	Cash or EFT
VAT_Rate	locked VAT rate used at generation time
Subtotal_Ex_VAT	number
VAT_Amount	number
Total	number
Valid_Until	date for quotes; blank for invoices unless later required
Google_Drive_File_ID	Drive file ID returned by upload
Google_Drive_URL	Drive URL returned/stored for internal lookup
File_Name	generated PDF filename
Created_At	date/time generated
Created_By	admin/system actor
Sent_At	date/time sent to customer, blank until sent
Sent_By	actor/workflow that sent it, blank until sent
Notes	system/admin notes

## Business Rules

- Quote versions increment per order: V1, V2, V3.
- Invoice generation requires an existing non-voided quote.
- Invoice generation uses the latest non-voided quote version.
- Generated PDFs stay restricted in Google Drive by default.
- n8n downloads PDFs through authenticated Google Drive access and sends them as Chatwoot attachments.
- `ORDER_DOCUMENTS` remains the truth even though filenames include human-readable summary details.

## Notes

- Backend should not parse totals, payment method, or status from `File_Name`.
- Backend should fail clearly if required Drive upload details are missing.
- Delivery updates should preserve the original generated document totals and file IDs.
