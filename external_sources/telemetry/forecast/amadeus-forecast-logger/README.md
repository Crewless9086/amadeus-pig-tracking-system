# Amadeus Forecast Logger

The Render cron fetches a 10-day Open-Meteo forecast and writes it to the
Amadeus telemetry ingest endpoint. Google Sheets can remain enabled as a
temporary mirror.

## Production schedule

Run twice daily at `0 4,16 * * *` UTC, which is 06:00 and 18:00 in
`Africa/Johannesburg`. Forecast consumers, including irrigation planning,
must read the backend/Supabase forecast instead of polling Open-Meteo again.

The legacy n8n workflow `2.1.1 - Amadeus Forecast Tool` should remain inactive.

## Provider limits

The free Open-Meteo endpoint can return HTTP 429 when its shared daily quota is
exhausted. A daily-limit response preserves the existing forecast, emits a
`provider_rate_limited` result, and exits without a traceback. Short-lived 429
and 5xx responses are retried with bounded backoff.

Optional paid Open-Meteo configuration:

- `OPEN_METEO_API_URL=https://customer-api.open-meteo.com/v1/forecast`
- `OPEN_METEO_API_KEY=<configured in Render only>`
- `OPEN_METEO_MAX_RETRIES=2`

Never commit the API key or print it in logs.
