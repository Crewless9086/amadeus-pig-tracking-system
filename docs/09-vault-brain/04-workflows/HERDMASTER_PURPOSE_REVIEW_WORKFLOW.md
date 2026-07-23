# Herdmaster Purpose Review Workflow

Purpose review starts after weaning and post-wean weight timing rules.

Herdmaster prepares recommendations using wean weight, latest weight, ADG, litter quality, sow/boar, sex, pen, stored purpose, and missing data.

Owner approves, overrides, defers, or requests recheck. A correction write requires a persisted owner-approved correction batch, execution-time canonical fresh-weight validation, and an atomic operational audit event for every corrected pig. The legacy apply route is preview-only and correction execution has no Google Sheets fallback.

Source reference: `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md`.
