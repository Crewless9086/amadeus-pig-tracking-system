# SYSTEM_SETTINGS.md

## Role

Register/reference sheet for backend-readable system settings.

This sheet lets business rules such as quote validity, VAT rate, business details, bank details, and document Drive folders be changed without code changes.

## Write Ownership

Backend setup utility or controlled admin tooling.

Manual edits are acceptable for approved setting changes, but setting keys must not be renamed casually because backend code reads by `Setting_Key`.

## Columns

Setting_Key	Setting_Value	Description	Updated_At	Updated_By

## Column Style And Values

Setting_Key	stable lowercase key
Setting_Value	string value read by backend
Description	human explanation of the setting
Updated_At	date/time of last setting update
Updated_By	admin/system actor that last changed it

## Required Initial Settings

| Setting_Key | Setting_Value | Description |
| --- | --- | --- |
| `quote_valid_days` | `3` | Number of days a generated quote remains valid. |
| `vat_rate` | `0.15` | VAT rate used for EFT quote/invoice calculations. |
| `business_name` | `AMADEUS FARM` | Business name shown on quote/invoice PDFs. |
| `business_address_line_1` | `Swartklip Road` | Business address line 1. |
| `business_address_line_2` | `Riversdale, 6670` | Business address line 2. |
| `business_address_line_3` | `Western Cape` | Business address line 3. |
| `business_phone` | `084-567-9327` | Business phone shown on documents. |
| `business_email` | `amadeusfarm572@gmail.com` | Business email shown on documents. |
| `business_vat_number` | `4510286224` | Business VAT number shown on documents. |
| `bank_name` | `First National Bank (FNB)` | Bank name shown on documents. |
| `bank_account_name` | `Charl Nieuwendyk` | Bank account holder shown on documents. |
| `bank_account_type` | `Cheque Account` | Bank account type shown on documents. |
| `bank_account_number` | `62315222711` | Bank account number shown on documents. |
| `bank_branch_code` | `250655` | Bank branch code shown on documents. |
| `quote_drive_folder_id` | `1r7oqIDMwZZi5T7BxC31y7UGNzn8Ud9ys` | Google Drive Shared Drive folder ID for quote PDFs. |
| `invoice_drive_folder_id` | `1_kbfX69s6yeb-Zfdcpu5jse8H30HvLGr` | Google Drive Shared Drive folder ID for invoice PDFs. |
| `document_logo_path` | `static/document-assets/amadeus-logo.png` | Runtime logo asset path for PDF generation. |
| `draft_quote_note` | `Draft quote - subject to availability and approval` | Visible note on quotes generated while order status is Draft. |

## Notes

- Backend should fail clearly if required document settings are missing.
- Backend may cache settings per request, but should not hard-code business values that belong here.
- Sensitive credentials do not belong in this sheet.
