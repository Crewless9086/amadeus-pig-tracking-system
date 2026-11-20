# Forecast Logger Delivery

Classification: technical runtime reference; not agent doctrine.

Canonical code: `modules/telemetry/forecast_logger.py`; entrypoint:
`python scripts/run_forecast_logger.py`. Install the cron dependencies with
`pip install -r deploy/forecast-logger/requirements.txt` from the repository root.
The historical `external_sources/` copy is not the publication path.


One existing Render cron retrieves a three-day forecast and sends it to the
existing telemetry ingest endpoint. Consumers reuse stored forecasts; they do
not poll providers. Google Sheets is an optional mirror. The legacy n8n forecast
workflow remains inactive.

## Providers and source identity

`FORECAST_PROVIDERS=visual_crossing,weatherapi` is the default order. Every
scheduled refresh tries the first eligible provider, so recovery automatically
returns to the configured primary. A persisted provider cooldown or an active
probe lease skips that provider independently of the backup.

- Visual Crossing's commercial no-key endpoint is the default. The request uses
  metric units, only required fields, and the exact local today-through-day-2
  range. Its source is `visual-crossing-forecast-main` / `visual_crossing`.
- WeatherAPI is the optional commercial free backup. Set `WEATHERAPI_API_KEY`
  in service secrets; requests always use three days, including during any
  higher-tier signup trial. Without a key it is explicitly `not_configured`;
  a working primary alone does not prove backup availability. Its source is
  `weatherapi-forecast-main` / `weatherapi`.
- Open-Meteo is retained only when explicitly included in `FORECAST_PROVIDERS`
  with an appropriately licensed endpoint/account. It is not a default free
  commercial fallback. Existing `OPEN_METEO_API_URL`, `OPEN_METEO_API_KEY` and
  `OPEN_METEO_MAX_RETRIES` remain supported; retry count is capped at two.

Provider source rows must already be registered and active with matching
provider identity. The logger cannot register sources or change credentials.
Each day preserves source identity, actual coverage, attribution, request hash,
and aware UTC retrieval time. Retrieval time is not a model issuance timestamp.
WeatherAPI and Visual Crossing daily rain probability is the maximum of all 24
hourly probabilities, not a fabricated zero. WeatherAPI's distinct daily chance
is retained separately. Visual Crossing's combined/forecast source provenance
is retained; remote observations never become local rain or delivered-water
credit. User-facing consumers must display the provider attribution.

## Cadence and limits

Recommended existing-cron setting: `0 */4 * * *` UTC, with `DAYS=3`. This fits
inside the existing six-hour freshness policy; this documentation does not
change a live schedule. Do not weaken freshness to accommodate the old 12-hour
schedule. Longer Open-Meteo horizons are only used when explicitly configured.

Provider attempts use bounded retries and request inactivity timeouts. A
`Retry-After` that exceeds the short same-run retry budget ends that provider's
attempt without shortening its instruction. Network, quota, 5xx and invalid
required forecast data can select an independent configured backup.

## Durable provider health

The authenticated `/api/telemetry/weather/forecast/provider-health` action uses
the existing `telemetry_sources.metadata.forecast_provider_health` object.
Atomic claims fence concurrent jobs by generation and attempt identity. Snapshot
ingestion locks and checks that same live claim in its own write transaction,
so an expired or superseded worker cannot insert a newly stamped forecast.
Results are replayable only when every result field matches. Stored `retry_not_before`
never moves earlier, even across process restarts or both-provider failure.

An unresolved probe lease lasts 15 minutes. Its later automatic recovery is a
local unknown-outcome policy, not a claimed provider reset time. A response lost
before its Retry-After reaches the backend cannot preserve an unseen bound;
that limitation is explicit. Unavailable health admission prevents contacting
that provider. No new scheduler, database table or provider state file is used.

Provider health becomes `ingested` only after valid forecast acquisition and a
successful required backend ingest acknowledgement. Failed required ingest or
unconfirmed health persistence exits nonzero even if the Sheets mirror worked.
Both-provider failure preserves existing forecast snapshots and exits nonzero.

## Official contracts

- https://www.visualcrossing.com/resources/documentation/weather-api/free-weather-api-no-key/
- https://www.visualcrossing.com/resources/documentation/weather-api/timeline-weather-api/
- https://www.weatherapi.com/docs/forecast-api/
- https://www.weatherapi.com/pricing

No API key, paid subscription, account action or live configuration is created
by this source change.
