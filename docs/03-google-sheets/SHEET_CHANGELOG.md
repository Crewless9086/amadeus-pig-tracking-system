# Sheet Changelog

## Purpose

Records approved changes to Google Sheets columns, formulas, sheet names, ownership rules, and documentation structure.

## Current Entries

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
