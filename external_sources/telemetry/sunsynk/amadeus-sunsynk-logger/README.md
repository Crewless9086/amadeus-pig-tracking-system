# Amadeus Sunsynk Logger

Render cron logger for the Sunsynk inverter.

## Phase 10.3F Direction

The logger now supports the preferred backend ingest path:

- `AMADEUS_BACKEND_URL=https://amadeus-pig-tracking-system.onrender.com`
- `TELEMETRY_INGEST_API_KEY=<same key configured on backend>`

When both values are present, the logger posts the normalized reading to:

`POST /api/telemetry/power/ingest`

The logger can still keep Google Sheets as a temporary mirror while we validate Supabase:

- `GOOGLE_SHEETS_ENABLED=true` by default
- set `GOOGLE_SHEETS_ENABLED=false` only after the backend/Supabase path has been proven stable
- if backend ingest succeeds but the Google Sheets mirror fails, the cron logs
  `google_sheets_error` and still exits successfully

Do not store secret values in this repo.
