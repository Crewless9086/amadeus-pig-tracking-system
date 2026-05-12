# Sheet Changelog

## Purpose

Records approved changes to Google Sheets columns, formulas, sheet names, ownership rules, and documentation structure.

## Current Entries

### 2026-05-12 - Phase 5.5 order intake state sheets

Sheet: `ORDER_INTAKE_STATE`, `ORDER_INTAKE_ITEMS`

Change: Added backend-ready setup utility and documented headers for persistent sales intake state. The setup script is `scripts/setup_order_intake_infrastructure.py`; without `--apply` it is dry-run only. Dry-run on 2026-05-12 confirmed both sheets were missing and would be created with the documented headers. Apply on 2026-05-12 created both sheets and verified headers.

Reason: Sam's natural sales conversations need persistent backend-owned structured state so customer-confirmed order facts do not disappear in long conversations.

Backend impact: Backend will read/write these sheets through `/api/order-intake/*` endpoints. Backend validates and merges proposed patches; n8n and Sam must not write these sheets directly.

n8n impact: Phase 5.6 should call backend intake endpoints in shadow mode before any live routing depends on intake state.

Formula impact: None planned. These are operational backend-owned sheets, not formula sheets.

Approved by: project owner


### 2026-05-09 - Phase 2.2 document infrastructure sheet design

Sheet: `SYSTEM_SETTINGS`, `ORDER_DOCUMENTS`

Change: Added documented schemas for backend-readable document settings and quote/invoice document tracking. Live setup utility created `SYSTEM_SETTINGS` and `ORDER_DOCUMENTS` on 2026-05-09, seeded 18 settings, and verified headers. Shared Drive folder IDs were written to `SYSTEM_SETTINGS` and backend upload was live-verified on 2026-05-10.

Reason: Phase 2 quote/invoice generation needs configurable business values, Drive folder IDs, locked VAT/totals, file metadata, and delivery tracking before endpoint implementation.

Backend impact: Backend should create/read `SYSTEM_SETTINGS`, write `ORDER_DOCUMENTS`, and treat `ORDER_DOCUMENTS` as the source of truth for generated document metadata.

n8n impact: n8n should download generated PDFs using authenticated Google Drive access and call backend endpoints for sent-state updates instead of writing `ORDER_DOCUMENTS` directly.

Formula impact: None planned.

Approved by: project owner


### 2026-04-25 - Google Sheets Documentation Baseline

Sheet: all documented sheets

Change: Created the first complete `docs/03-google-sheets/` structure with one documentation file per known Google Sheet and aligned folder-level schema, ownership, formula, field, and business rule docs.

Reason: Establish a clean source of truth before further backend, n8n, or AI changes.

Backend impact: Backend should use these docs before changing sheet reads/writes.

n8n impact: n8n should use these docs before reading sales stock or requesting order actions.

Formula impact: Formula-driven sheets are documented as read-only outputs.

Approved by: project owner

### 2026-04-25 - Standardized Sales And Status Labels

Sheet: Google Sheets documentation

Change: Standardized pig slaughter status to `Slaughtered`, Ready for Slaughter category code to `RFS`, and sales display weight field naming to `Weight_Band`.

Reason: Remove ambiguity before backend and n8n logic use these fields.

Backend impact: Future code should use these standardized values when reading or writing related fields.

n8n impact: Workflow logic should use `RFS` and `Weight_Band` where these sales fields are referenced.

Formula impact: Documentation now reflects the approved naming standard.

Approved by: project owner

## Entry Template

```text
Date:
Sheet:
Change:
Reason:
Backend impact:
n8n impact:
Formula impact:
Approved by:
```
