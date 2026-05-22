# Supabase Telemetry Plan

## Purpose

Phase 10.3 planning document.

This document defines how Amadeus Farm should handle weather, Sunsynk power, irrigation, and alert data before rebuilding Oom Sakkie telemetry answers or moving high-volume logs into Supabase.

The immediate reason for this phase is the slow `2.2 - Amadeus Sunsynk Sub-Agent` path. It currently reads Google Sheets through n8n tools and can run for minutes without returning an answer. Quick workflow hardening was not enough, so the correct next step is to design the data path properly.

## Current Recommendation

Use one shared telemetry direction:

1. Inventory the existing telemetry sources first.
2. Keep working weather behavior stable while designing the new path.
3. Move high-volume/current-state telemetry behind backend APIs before asking Oom Sakkie to answer from it.
4. Store durable telemetry history in Supabase/Postgres where volume, history, and querying matter.
5. Give agents small prepared read models, not raw high-volume tables or large sheets.
6. Keep hardware-control actions, especially irrigation, behind explicit backend/audit boundaries before expanding commands.

Do not rebuild `2.2` as another larger agent workflow over Google Sheets.

Do not migrate telemetry blindly before the current sheets, cron jobs, n8n workflows, and data volume are documented.

## Current Telemetry Inventory

Known from current workflow docs and Phase 7.3E notes:

| Area | Current Workflows | Current Sheets / Data Views | Current Problem | Target Direction |
| --- | --- | --- | --- | --- |
| Weather station | `2.1 - Amadeus Weather Sub-Agent`, `ALERT - Local Weather Station` | `Amadeus_Weather_Logs`, `Weather_Alert_Log` | Weather is currently working after prompt/tool hardening. | Keep stable; later move logs/read models if useful. |
| Weather forecast | `2.1.1 - Amadeus Forecast Tool`, `ALERT - Weather Forecast` | `Forecast_10Day_Current`, `Weather_Alert_Log` | `2.1.1` has no recent executions; current `2.1` appears to read forecast data directly. | Decide whether forecast tool remains standalone or becomes the forecast worker again. |
| Sunsynk power | `2.2 - Amadeus Sunsynk Sub-Agent`, `ALERT - Sunsynk` | `Amadeus_Sunsynk_Log`, `Sunsynk_Current_Overview`, `Sunsynk_Daily_Summary`, `Sunsynk_Last24h_Hourly`, `Sunsynk_5min_Intervals`, `Sunsynk_Alert_Log` | Oom Sakkie power questions can hang for minutes; agent reaches a sheet tool but does not reliably answer. | Move toward backend/Supabase read models and deterministic summaries. |
| Irrigation planning | `2.3.1 - Build Daily Irrigation Plan` | `Amadeus_Irrigation_Logs`, weather logs | Depends on weather and irrigation state; not yet a backend-owned data path. | Inventory before changing. |
| Irrigation control | `2.3.2 - Run Irrigation Controller` | `Amadeus_Irrigation_Logs`, IFTTT/device actions | Hardware-control keys and actions need strict credential/audit boundaries. | Backend-owned command endpoint later; no expansion until secrets/audit are cleaned. |

Local repo scan on 2026-05-21:

- No backend telemetry modules exist yet under `modules/`; current backend domain modules are `documents`, `orders`, `pig_weights`, `reports`, and `sales`.
- No local Python/JS telemetry ingestion scripts were found in this repo by filename search.
- Telemetry knowledge currently lives mainly in n8n workflow exports and README files under `docs/04-n8n/workflows/`.
- Existing docs confirm that Sunsynk, weather, forecast, and irrigation are still workflow/sheet driven, not backend-owned.
- This means 10.3A still needs owner input about any external logger, laptop folder, Render cron/service, or device-cloud process that is outside this repo.

External source import on 2026-05-21:

- Owner added source folders under `external_sources-telemetry`; they were reorganized into `external_sources/`.
- `external_sources/telemetry/sunsynk/amadeus-sunsynk-logger/`
  - Python logger for Sunsynk.
  - Uses Sunsynk OpenAPI OAuth/login flow with `SUNSYNK_APP_KEY`, `SUNSYNK_APP_SECRET`, `SUNSYNK_USERNAME`, `SUNSYNK_PASSWORD`, and `SUNSYNK_INVERTER_SN`.
  - Reads `/api/v1/inverter/<serial>/flow` and `/api/v1/inverter/<serial>/realtime/output`.
  - Writes rows to Google Sheets using `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SHEET_NAME`, and `GOOGLE_SHEET_TAB`.
  - Captures timestamp, battery SOC, battery power, PV power, load, grid, generator, inverter output, derived grid/generator/battery flags, and raw JSON.
- `external_sources/telemetry/weather/amadeus-local-weatherstation-logger/`
  - Python logger for Weather.com PWS current conditions.
  - Uses `GOOGLE_SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_FILE`, `WCOM_API_KEY`, `STATION_ID`, `TIMEZONE`, and `DUP_WINDOW_SEC`.
  - Writes to `Current_Conditions`.
  - Captures timestamp, temperature, wind speed/gust/direction, rain rate/total, pressure, and humidity.
  - Includes duplicate/too-soon protection based on the last logged timestamp.
- `external_sources/telemetry/forecast/amadeus-forecast-logger/`
  - Python logger for Open-Meteo daily forecast.
  - Uses `GOOGLE_SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_FILE` or `GOOGLE_SERVICE_ACCOUNT_JSON`, `LAT`, `LON`, `TIMEZONE`, and `DAYS`.
  - Writes current forecast to `Forecast_10Day_Current` and appends history to `Forecast_10Day_History`.
  - Captures run timestamp, timezone, forecast date, offset, max/min temperature, rain sum/probability, wind/gust, source, lat, and lon.
- `external_sources/web/amadeus-landing/`
  - Related website/landing-page source, not telemetry.
  - Kept outside `external_sources/telemetry/`.
- Secret check:
  - One `.env` file exists in the forecast logger folder and is ignored by git.
  - Logger code references secrets via environment variable names; no secret values were copied into this document.
  - A landing page contains a website widget token-like value; it is treated as non-telemetry source evidence and should be reviewed before any public repo/share.

10.3A inventory status from imported sources:

| Source | In Repo? | Runtime Likely Needed | Current Write Target | Notes |
| --- | --- | --- | --- | --- |
| Sunsynk logger | Yes | Render cron | `Amadeus_Sunsynk_Log` spreadsheet | Screenshot confirms Render service `amadeus-sunsynk-logger` has successful runs. Need tab/column inventory after sheet access is granted. |
| Weather station logger | Yes | Render cron | `Amadeus_Weather_Log` spreadsheet | Screenshot confirms Render service `amadeus-localweatherstation-logger` has successful runs. Need tab/column inventory after sheet access is granted. |
| Forecast logger | Yes | Render cron | Forecast spreadsheet/tabs from logger env | Screenshot confirms Render service `amadeus-forecast-logger` has successful runs. Contains local `.env`; ignored. Need confirm production spreadsheet and tabs. |
| Irrigation | n8n workflow docs only | n8n | `Amadeus_Irrigation_Logs` spreadsheet | Owner believes irrigation is n8n-run only. Need tab/column inventory after sheet access is granted. |
| Landing page | Yes | Static/web hosting | None for telemetry | Filed separately under `external_sources/web/`. |

Owner-confirmed production sheets on 2026-05-21:

| Area | Spreadsheet |
| --- | --- |
| Sunsynk | `https://docs.google.com/spreadsheets/d/1y0lV78bIH0Cx3BS7IbM3H-iwLjP8tXT2hwp-IZAkKCg/edit` |
| Weather | `https://docs.google.com/spreadsheets/d/1nbxVchuN_cJyx6JRuANHxTISCjVXqUw3JJ4rN1w74e8/edit` |
| Irrigation | `https://docs.google.com/spreadsheets/d/1Wsje-g76mecOPWwQRvFR_TEdvfoUf9Vf1gL2pxmGX4E/edit` |

Access note:

- Local service account attempted read-only inventory on 2026-05-21 and received Google Sheets `403` permission denied.
- Share the three production sheets with `amadeuspigtrackersystem@amadeus-farm-weather-bot.iam.gserviceaccount.com` as Viewer before running tab/header/formula inventory.

Access update:

- Owner granted Viewer access to all three telemetry spreadsheets on 2026-05-21.
- Weather and irrigation tab/header/formula inventory succeeded.
- Sunsynk metadata inventory succeeded, but Google Sheets values reads timed out even for tiny ranges such as `Sunsynk_Current_Overview!A1:AB5`.
- After access was fixed, a repeat tiny Sunsynk values read on 2026-05-21 reached the spreadsheet but returned Google Sheets `503 service unavailable`.
- This timeout is a useful design signal: Oom Sakkie should not depend on live Google Sheets value reads for Sunsynk answers.

Sunsynk spreadsheet inventory:

Spreadsheet: `Amadeus_Sunsynk_Log`

| Tab | Grid Size | Current Role | Inventory Result |
| --- | ---: | --- | --- |
| `Sunsynk_Log` | 35,889 rows x 26 cols | Raw/current logger output from Sunsynk logger | Metadata only; values API timed out. Logger source shows timestamp, SOC, battery/PV/load/grid/generator/inverter fields and raw JSON. |
| `Sunsynk_Alert_Log` | 1,055 rows x 28 cols | Sunsynk alert history | Metadata only; values API timed out during Sunsynk reads. |
| `Sunsynk_Current_Overview` | 1,000 rows x 26 cols | Current-state / LLM-friendly overview | Metadata only; values API timed out. This should become the first backend read model. |
| `Sunsynk_5min_Intervals` | 36,096 rows x 28 cols | High-frequency interval data | Metadata only; likely bulk source for rollups. |
| `Sunsynk_Daily_Summary` | 1,000 rows x 26 cols | Daily power rollup | Metadata only; target for permanent daily rollup model. |
| `Sunsynk_Last24h_Hourly` | 9,392 rows x 26 cols | Hourly recent trend/read model | Metadata only; target for last-24h backend payload. |
| `Sunsynk_Cost_Data` | 1,000 rows x 26 cols | Cost/tariff/value calculations | Metadata only; should be reviewed before dashboard Rand/cost widgets. |
| `Sunsynk_Info` | 1,000 rows x 26 cols | Info/settings/reference | Metadata only; likely reference/config. |

Weather spreadsheet inventory:

Spreadsheet: `Amadeus_Weather_Logs`

| Tab | Grid Size | Headers / Role | Formula Notes |
| --- | ---: | --- | --- |
| `Current_Conditions` | 101,682 rows x 31 cols | `Timestamp`, `Temperature`, `Wind Speed`, `Wind Gust`, `Wind Direction`, `Rain Rate`, `Total Rain`, `Pressure`, `Humidity`, `DateOnly` | `DateOnly` is generated with an `ARRAYFORMULA` over timestamp. |
| `LLM_Latest_Reading` | 1,000 rows x 26 cols | Latest weather row for LLM use | Formula indexes latest sorted `Current_Conditions` row. |
| `LLM_Today_Readings` | 1,000 rows x 26 cols | Today's weather rows for LLM use | Formula filters `Current_Conditions` to today. |
| `Daily_Pivot` | 1,000 rows x 26 cols | Daily max/min/temp/wind/rain summary | No formulas found in first 50 rows; likely values/pivot output. |
| `Weather_Alert_Log` | 1,255 rows x 26 cols | `timestamp_za`, `alert_type`, `alert_key`, `severity`, `cooldown_min`, `message`, `last_timestamp_za`, `extra_json` | No formulas found in first 50 rows. |
| `Weather_Settings` | 1,000 rows x 26 cols | Empty/no values in sampled range | No formulas found in first 50 rows. |
| `Forecast_10Day_Current` | 1,000 rows x 26 cols | Open-Meteo 10-day current forecast | Written by forecast logger; no formulas found in first 50 rows. |
| `Forecast_24hr_Current` | 1,000 rows x 26 cols | Next-24h compact forecast summary | Formula-based summary over `Forecast_10Day_Current`. |
| `Forecast_10Day_History` | 32,471 rows x 26 cols | Open-Meteo forecast history | No formulas found in first 50 rows. |

Irrigation spreadsheet inventory:

Spreadsheet: `Amadeus_Irrigation_Logs`

| Tab | Grid Size | Headers / Role | Formula Notes |
| --- | ---: | --- | --- |
| `ZONES` | 998 rows x 26 cols | `zone_id`, `name`, `ha_entity`, `priority`, `summer_minutes`, `winter_minutes`, `allowed_start`, `allowed_end`, `days_allowed`, `soil_type`, `notes`, `ifttt_on_event`, `ifttt_off_event` | No formulas found in first 50 rows. Contains IFTTT event names, not the Maker key. |
| `RULES` | 1,001 rows x 26 cols | `rule_key`, `rule_value` | No formulas found in first 50 rows. Examples include `wind_pause_kmh`, `live_rain_skip_mm`. |
| `DAILY_PLAN` | 1,132 rows x 27 cols | `plan_id`, `date`, `zone_id`, `planned_start`, `planned_minutes`, `status`, `reason`, `actual_start`, `actual_end`, `water_score` | No formulas found in first 50 rows. |
| `STATE` | 1,000 rows x 27 cols | `state_id`, `current_zone_id`, `current_status`, `remaining_minutes`, `pause_reason`, `last_update`, `last_zone_completed`, `next_zone_id` | No formulas found in first 50 rows. |
| `LOG` | 1,135 rows x 26 cols | `timestamp`, `zone_id`, `event`, `reason`, `weather_snapshot`, `run_minutes_planned`, `run_minutes_actual`, `actor`, `plan_id` | No formulas found in first 50 rows. |
| `TANK_COLUMNS` | 1,000 rows x 26 cols | `column_id`, `status`, `active` | No formulas found in first 50 rows. |

10.3A inventory conclusion:

- Weather currently already has small LLM-facing sheet views (`LLM_Latest_Reading`, `LLM_Today_Readings`, `Forecast_24hr_Current`), so it can stay stable while we design telemetry migration.
- Irrigation sheets are small and structured enough to model later, but they include hardware-control event references, so command/audit design must come before control expansion.
- Sunsynk is the urgent telemetry candidate: the raw and interval tabs are large, and even small values reads are timing out through the Sheets API. The first implementation should replace Oom Sakkie Sunsynk sheet reads with a backend/Supabase current-state endpoint.

## 10.3 Required Outcome

This phase is complete when we have:

- a documented inventory of all telemetry sheets, workflows, scripts, cron jobs, and external APIs
- a decision on which telemetry data should move to Supabase first
- a proposed Supabase telemetry schema with raw readings, latest-state snapshots, rollups, and alert logs
- backend API contracts for Oom Sakkie and dashboard use
- n8n rules for reading telemetry through backend APIs instead of scanning sheets
- a safe plan for irrigation command secrets and action audit
- a staged implementation plan that can be built and tested without breaking current weather or live irrigation behavior

## Data Ownership Direction

| Data Type | Current Owner | Target Owner | Notes |
| --- | --- | --- | --- |
| Raw weather readings | Google Sheets / n8n | Supabase telemetry tables later | Weather works now; do not move first unless needed for dashboard/read models. |
| Raw Sunsynk readings | Google Sheets / cron or n8n path to confirm | Supabase telemetry tables | Likely first telemetry migration because the current answer path is slow. |
| Current power state | `Sunsynk_Current_Overview` sheet | Backend read model over Supabase/latest state | This should be the first Oom Sakkie power answer source. |
| Daily power summary | `Sunsynk_Daily_Summary` sheet | Supabase rollup table or backend-calculated view | Needed for "today", "yesterday", and daily comparisons. |
| Last 24h power profile | `Sunsynk_Last24h_Hourly` sheet | Hourly rollup table/view | Needed for simple trend answers. |
| 5-minute power intervals | `Sunsynk_5min_Intervals` sheet | Raw/high-frequency table or retained sheet until volume is understood | Do not expose raw interval scans to the LLM. |
| Alert logs | Weather/Sunsynk alert log sheets | Supabase alert log table | Needed for audit and "what happened" questions. |
| Irrigation plans/actions | n8n/sheets/IFTTT | Backend command and audit tables later | Hardware control must be explicit, auditable, and credential-safe. |

## LLM Read Model Direction

Oom Sakkie should receive small JSON payloads from backend endpoints, for example:

| Endpoint Idea | Purpose | Payload Shape |
| --- | --- | --- |
| `GET /api/telemetry/power/current` | Answer "what is the power like now?" | latest inverter/battery/grid/load/solar state, timestamp, data age, warning flags |
| `GET /api/telemetry/power/summary?period=today` | Answer today/yesterday/week/month power questions | production, consumption, grid import/export, battery min/max, notable events |
| `GET /api/telemetry/power/hourly?hours=24` | Answer last-24h trend questions | 24 hourly rollup rows, not raw 5-minute data |
| `GET /api/telemetry/weather/current` | Answer current weather questions | latest station reading, data age, rain/wind/temp/humidity flags |
| `GET /api/telemetry/weather/forecast` | Answer forecast questions | compact forecast periods with risk flags |
| `GET /api/telemetry/alerts/recent?area=sunsynk` | Answer "any alerts?" questions | recent alert entries and severity |

Agents should not query raw telemetry tables directly.

Agents should not decide whether telemetry is stale; backend endpoints should include data-age and stale flags.

## 10.3B Sunsynk Current-State Read Model

Goal:

- Replace the slow `2.2 - Amadeus Sunsynk Sub-Agent` Google Sheets read path with one small backend-prepared payload.
- Answer current operational power questions such as "what is the power like now?", "are we on solar?", "is the battery charging?", "are we using grid?", and "is the data fresh?"
- Do not solve full daily/monthly cost reporting in this slice.

Recommended first endpoint:

`GET /api/telemetry/power/current`

Recommended response shape:

```json
{
  "success": true,
  "source": {
    "source_id": "sunsynk-main-inverter",
    "source_name": "Amadeus Sunsynk Inverter",
    "provider": "sunsynk",
    "last_reading_at": "2026-05-21T19:05:00+02:00",
    "data_age_minutes": 4,
    "is_stale": false,
    "stale_after_minutes": 15
  },
  "current": {
    "battery_soc_pct": 82,
    "battery_power_w": -640,
    "battery_state": "charging",
    "solar_power_w": 3120,
    "pv1_power_w": 1580,
    "pv2_power_w": 1540,
    "load_power_w": 1240,
    "grid_power_w": 0,
    "grid_state": "not_using_grid",
    "generator_power_w": 0,
    "generator_state": "off",
    "inverter_output_w": 1240
  },
  "flags": {
    "solar_active": true,
    "battery_charging": true,
    "battery_discharging": false,
    "grid_active": false,
    "generator_active": false,
    "low_battery": false,
    "high_load": false,
    "no_solar": false
  },
  "summary": {
    "status": "ok",
    "headline": "Solar is carrying the farm load and charging the battery.",
    "operator_notes": [
      "Battery is at 82%.",
      "Solar production is 3.1 kW.",
      "Current load is 1.2 kW.",
      "No grid or generator use is showing."
    ]
  },
  "units": {
    "power": "W",
    "battery_soc": "%"
  }
}
```

Required field groups:

| Group | Required? | Purpose |
| --- | --- | --- |
| `source` | Yes | Lets Oom Sakkie know whether the answer is fresh and where it came from. |
| `current` | Yes | Numeric state for solar, load, battery, grid, generator, and inverter output. |
| `flags` | Yes | Deterministic booleans for Oom Sakkie wording and alert-style answers. |
| `summary` | Yes | Backend-prepared short wording so the LLM does not invent technical meaning. |
| `units` | Yes | Prevents confusion between watts, kilowatts, percentages, and money. |

Stale-data rules:

| Condition | Backend Response |
| --- | --- |
| Latest reading age is `<= 15` minutes | `is_stale = false`, `summary.status = ok` unless another warning applies. |
| Latest reading age is `> 15` and `<= 60` minutes | `is_stale = true`, `summary.status = stale`, answer may include the last known state but must say it is old. |
| Latest reading age is `> 60` minutes or no reading exists | `is_stale = true`, `summary.status = unavailable`, Oom Sakkie should not describe it as current. |

Initial threshold recommendations:

| Flag | Rule | Notes |
| --- | --- | --- |
| `solar_active` | `solar_power_w > 100` | Avoid saying solar is active for tiny noise values. |
| `grid_active` | absolute `grid_power_w > 50` | Existing logger treats any non-zero as active; backend should use a small threshold. |
| `generator_active` | `generator_power_w > 50` or logger `gen_active = true` | Preserve logger flag if available. |
| `battery_charging` | logger `battery_charging = true` or `battery_power_w < -50` | Current logger notes Sunsynk sign direction carefully; backend should preserve that interpretation. |
| `battery_discharging` | logger `battery_discharging = true` or `battery_power_w > 50` | Use the logger-derived flag first. |
| `low_battery` | `battery_soc_pct < 30` | Planning default; owner can adjust later. |
| `high_load` | `load_power_w >= 6000` | Planning default until inverter/load expectations are confirmed. |
| `no_solar` | `solar_power_w <= 100` during daylight only | Daylight check can be added later; avoid false night alerts. |

Recommended backend behavior:

- Backend should return `200` with `success = true` when it has a latest reading, even if stale.
- Backend should return `200` with `success = false`, `summary.status = unavailable`, and a clear message if no reading exists yet.
- Backend should never expose raw Sunsynk API JSON to Oom Sakkie.
- Backend should include `data_age_minutes` and `is_stale` in every successful response.
- Backend should convert missing numeric values to `null`, not empty strings.
- Backend should generate the human summary from deterministic rules, not from an LLM.

First-version data source:

- The existing Render cron Sunsynk logger already extracts the required fields from Sunsynk.
- Preferred next architecture: the logger sends the same normalized reading to the backend, and the backend writes Supabase/latest-state.
- Acceptable transition architecture: the logger writes Supabase directly for the first version if that is materially faster, but backend endpoints still remain the only read path for Oom Sakkie.
- Avoid using Google Sheets as the endpoint source because value reads are timing out/returning `503` even after access was granted.

Fields required from the logger:

| Logger Field | Endpoint Field |
| --- | --- |
| `timestamp_za` | `source.last_reading_at` |
| `soc` | `current.battery_soc_pct` |
| `batt_power` | `current.battery_power_w` |
| `pv_total` | `current.solar_power_w` |
| `pv1` | `current.pv1_power_w` |
| `pv2` | `current.pv2_power_w` |
| `load_power` | `current.load_power_w` |
| `grid_power` | `current.grid_power_w` |
| `gen_power` | `current.generator_power_w` |
| `inv_pac` | `current.inverter_output_w` |
| `grid_active` | `flags.grid_active` plus `current.grid_state` |
| `gen_active` | `flags.generator_active` plus `current.generator_state` |
| `battery_charging` | `flags.battery_charging` plus `current.battery_state` |
| `battery_discharging` | `flags.battery_discharging` plus `current.battery_state` |

Oom Sakkie wording rules for `2.2` later:

- If `summary.status = unavailable`, say the power data is unavailable and do not guess.
- If `is_stale = true`, say "last known" and include the reading age.
- Prefer `summary.headline` as the first sentence.
- Use only the prepared fields from the backend response.
- Do not ask the agent to calculate battery direction, grid state, or freshness from raw values.
- Do not call Google Sheets from `2.2` for current power answers after this endpoint is live.

Not included in 10.3B:

- Daily/monthly/yearly power totals.
- Rand/cost calculations from `Sunsynk_Cost_Data`.
- Alert history.
- Dashboard charts.
- Irrigation control.
- Weather migration.

10.3B implementation gate:

- Owner agrees this payload is useful for the first Oom Sakkie power answers.
- Decide stale threshold, currently recommended at 15 minutes.
- Decide initial low-battery threshold, currently recommended at 30%.
- Decide ingestion path in 10.3D before building SQL or endpoint writes.

## 10.3C Telemetry Schema Proposal

Status:

- Planning only.
- No SQL migration is approved yet.
- Owner agreed the 10.3B current-state payload on 2026-05-21.

Schema principle:

- Separate latest operational state from raw history.
- Keep Oom Sakkie and dashboard reads on compact latest/rollup tables.
- Keep raw data only as a short-term source for debugging and rollup rebuilds.
- Do not model irrigation command execution in the same first migration as Sunsynk reads.

Recommended first migration scope:

| Table | Include In First Telemetry Migration? | Purpose |
| --- | --- | --- |
| `telemetry_sources` | Yes | Registry for Sunsynk inverter, weather station, forecast provider, irrigation controller, and future telemetry devices. |
| `power_readings_5min` | Yes | Recent raw Sunsynk readings used for debugging and future rollups. Short retention. |
| `power_latest_state` | Yes | One latest row per Sunsynk source for fast Oom Sakkie current-state answers. |
| `telemetry_alerts` | Yes | Shared alert/audit table for power/weather/irrigation events. Initially usable for Sunsynk. |
| `power_hourly_rollups` | Plan now, optional first migration | Last-24h and trend answers. Can be added in first migration if low risk, but not required for `/power/current`. |
| `power_daily_rollups` | Plan now, optional first migration | Daily totals/comparisons. Can wait until rollup calculations are defined. |
| `power_monthly_rollups` | Later | Permanent monthly summaries after daily rollups are proven. |
| `power_yearly_rollups` | Later | Permanent yearly summaries after monthly rollups are proven. |
| `weather_latest_state` | Later | Weather works now; do not move in the first Sunsynk fix unless needed. |
| `weather_forecast_snapshots` | Later | Forecast works well enough from current sheet views; migrate later. |
| `irrigation_actions` | Later | Hardware-control audit/command design must be handled separately. |

Recommended first tables:

### `telemetry_sources`

Purpose:

- One row per telemetry source/device/provider.
- Lets backend endpoints find source metadata and stale thresholds without hardcoding everything.

Recommended columns:

| Column | Type | Notes |
| --- | --- | --- |
| `source_id` | `text primary key` | Example: `sunsynk-main-inverter`. |
| `source_type` | `text not null` | Check: `power`, `weather`, `forecast`, `irrigation`. |
| `provider` | `text not null` | Example: `sunsynk`, `weather_com`, `open_meteo`, `ifttt`. |
| `display_name` | `text not null` | Human-readable name. |
| `external_ref` | `text` | Inverter serial/station ID/etc. Avoid secrets. |
| `timezone` | `text not null default 'Africa/Johannesburg'` | Source timezone. |
| `stale_after_minutes` | `integer not null default 15` | Current-state freshness threshold. |
| `active` | `boolean not null default true` | Soft-disable source without deleting history. |
| `metadata` | `jsonb not null default '{}'::jsonb` | Non-secret source config. |
| `created_at` / `updated_at` | `timestamptz` | Standard audit timestamps. |

### `power_readings_5min`

Purpose:

- Recent raw normalized Sunsynk readings.
- Source for debugging and later hourly/daily rollups.
- Not used directly by Oom Sakkie.

Recommended columns:

| Column | Type | Notes |
| --- | --- | --- |
| `reading_id` | `text primary key` | Deterministic or generated ID. |
| `source_id` | `text references telemetry_sources(source_id)` | Should be `sunsynk-main-inverter` first. |
| `reading_at` | `timestamptz not null` | Timestamp from logger/API. |
| `battery_soc_pct` | `numeric(5,2)` | Battery state of charge. |
| `battery_power_w` | `numeric(12,3)` | Preserve sign from logger interpretation. |
| `solar_power_w` | `numeric(12,3)` | Total PV power. |
| `pv1_power_w` / `pv2_power_w` | `numeric(12,3)` | Optional string-specific values. |
| `load_power_w` | `numeric(12,3)` | Farm load. |
| `grid_power_w` | `numeric(12,3)` | Grid import/export/current flow as provided by source. |
| `generator_power_w` | `numeric(12,3)` | Generator power. |
| `inverter_output_w` | `numeric(12,3)` | Inverter output. |
| `grid_active` / `generator_active` | `boolean` | Logger/backend-derived flags. |
| `battery_charging` / `battery_discharging` | `boolean` | Preserve logger-derived direction. |
| `raw_payload` | `jsonb` | Optional raw Sunsynk payload for short retention/debug only. |
| `ingested_at` | `timestamptz not null default now()` | When backend/Supabase received it. |
| `import_batch_id` | `text` | Optional import/debug trace. |

Recommended constraints/indexes:

- Unique `(source_id, reading_at)` so repeated cron retries upsert instead of duplicate.
- Index `(source_id, reading_at desc)` for latest/recent reads.
- Check percentages between `0` and `100` when not null.

### `power_latest_state`

Purpose:

- Fast current state table used by `GET /api/telemetry/power/current`.
- One row per power source.

Recommended columns:

| Column | Type | Notes |
| --- | --- | --- |
| `source_id` | `text primary key references telemetry_sources(source_id)` | One latest state per source. |
| `reading_at` | `timestamptz not null` | Latest source reading timestamp. |
| `data_age_minutes` | `integer` | May be calculated by backend instead of stored; storing is optional. |
| `battery_soc_pct` | `numeric(5,2)` | Same normalized fields as raw table. |
| `battery_power_w` | `numeric(12,3)` | Same normalized fields as raw table. |
| `solar_power_w` | `numeric(12,3)` | Same normalized fields as raw table. |
| `pv1_power_w` / `pv2_power_w` | `numeric(12,3)` | Optional. |
| `load_power_w` | `numeric(12,3)` | Same normalized fields as raw table. |
| `grid_power_w` | `numeric(12,3)` | Same normalized fields as raw table. |
| `generator_power_w` | `numeric(12,3)` | Same normalized fields as raw table. |
| `inverter_output_w` | `numeric(12,3)` | Same normalized fields as raw table. |
| `battery_state` | `text` | Check: `charging`, `discharging`, `idle`, `unknown`. |
| `grid_state` | `text` | Check: `using_grid`, `not_using_grid`, `exporting`, `unknown`. |
| `generator_state` | `text` | Check: `on`, `off`, `unknown`. |
| `flags` | `jsonb not null default '{}'::jsonb` | Deterministic flags from 10.3B. |
| `summary_status` | `text not null default 'ok'` | Check: `ok`, `warning`, `stale`, `unavailable`. |
| `summary_headline` | `text` | Backend-prepared headline. |
| `summary_notes` | `jsonb not null default '[]'::jsonb` | Backend-prepared bullet list. |
| `updated_at` | `timestamptz not null default now()` | Latest DB update time. |

Recommended constraints/indexes:

- Primary key `source_id`.
- Index `reading_at desc`.
- Backend should compute `is_stale` at read time using `reading_at` and `telemetry_sources.stale_after_minutes`, so stale status does not go stale itself.

### `telemetry_alerts`

Purpose:

- Shared event/alert history for Sunsynk, weather, forecast, and irrigation.
- Useful for "what happened?" questions and operational audit.

Recommended columns:

| Column | Type | Notes |
| --- | --- | --- |
| `alert_id` | `text primary key` | Generated ID. |
| `source_id` | `text references telemetry_sources(source_id)` | May be null for system-wide alerts. |
| `area` | `text not null` | Check: `power`, `weather`, `forecast`, `irrigation`, `system`. |
| `alert_type` | `text not null` | Example: `low_battery`, `grid_active`, `logger_stale`. |
| `severity` | `text not null` | Check: `info`, `warning`, `critical`. |
| `message` | `text not null` | Human-readable event. |
| `event_at` | `timestamptz not null` | When the event happened. |
| `resolved_at` | `timestamptz` | Optional. |
| `status` | `text not null default 'Open'` | Check: `Open`, `Resolved`, `Ignored`. |
| `details` | `jsonb not null default '{}'::jsonb` | Extra non-secret data. |
| `created_at` | `timestamptz not null default now()` | Audit. |

Recommended constraints/indexes:

- Index `(area, event_at desc)`.
- Index `(source_id, event_at desc)`.
- Index `(status, severity)`.

Optional rollup tables for same or later migration:

### `power_hourly_rollups`

Purpose:

- Support "last 24 hours" trend answers without scanning raw 5-minute data.

Minimum columns:

- `source_id`
- `period_start`
- `period_end`
- average/min/max battery SOC
- average/max load power
- total/average solar power proxy, until proper energy kWh is confirmed
- grid active minutes
- generator active minutes
- sample_count
- calculation_version
- generated_at

### `power_daily_rollups`

Purpose:

- Support "today", "yesterday", and date comparison answers.

Minimum columns:

- `source_id`
- `rollup_date`
- min/max battery SOC
- max load power
- max solar power
- grid active minutes
- generator active minutes
- sample_count
- data_coverage_pct
- calculation_version
- generated_at

Open technical point:

- The current logger captures instantaneous power readings, not guaranteed energy counters. Daily/monthly kWh totals should not be invented from these until we confirm whether Sunsynk API exposes reliable energy-total fields or whether approximated interval integration is acceptable.

Recommended first migration decision:

- Create only `telemetry_sources`, `power_readings_5min`, `power_latest_state`, and `telemetry_alerts` first.
- Leave hourly/daily/monthly/yearly rollup tables for the next slice unless we confirm energy calculation rules.
- Seed one source row for `sunsynk-main-inverter` with provider `sunsynk`, source type `power`, timezone `Africa/Johannesburg`, and stale threshold `15`.

10.3C implementation gate:

- Owner agrees first schema should be power-first, not all telemetry at once.
- Owner accepts raw 5-minute readings as short-retention/debug data, not Oom Sakkie answer data.
- Owner accepts that kWh/cost rollups wait until energy counters/calculation rules are confirmed.
- Then create migration `202605210005_create_telemetry_power_tables.sql` and a verifier endpoint in the next implementation slice.

10.3C local implementation result:

- Owner agreed to implement the first power schema slice on 2026-05-21.
- Migration created locally: `supabase/migrations/202605210005_create_telemetry_power_tables.sql`.
- Backend verifier created locally: `GET /health/database/telemetry-power-schema`.
- Migration creates `telemetry_sources`, `power_readings_5min`, `power_latest_state`, and `telemetry_alerts`.
- Migration seeds `sunsynk-main-inverter` as the first `telemetry_sources` row.
- No telemetry readings are imported.
- No Render logger changes are included.
- No n8n workflow changes are included.
- Local verification passed on 2026-05-21: focused database tests passed at 18 tests, local missing-config verifier smoke returned safe `503`, and full local unittest suite passed at 211 tests.

Deploy/apply gate:

- Deploy the backend containing `/health/database/telemetry-power-schema`.
- Run `supabase/migrations/202605210005_create_telemetry_power_tables.sql` in Supabase SQL Editor.
- Confirm `/health/database/telemetry-power-schema` returns `success = true`, `status = ok`, migration ID `202605210005_create_telemetry_power_tables`, `missing_tables = []`, and `sunsynk_source.source_id = sunsynk-main-inverter`.

10.3C deployed verification result:

- Passed on 2026-05-21.
- `/health/database/telemetry-power-schema` returned `success = true`, `status = ok`, migration ID `202605210005_create_telemetry_power_tables`, all four expected tables found, and `missing_tables = []`.
- Seed source confirmed: `sunsynk_source.source_id = sunsynk-main-inverter`, `provider = sunsynk`, `source_type = power`, `stale_after_minutes = 15`.
- Direct-run note for future migrations: Codex can apply SQL directly to Supabase from the local workspace when `DATABASE_URL` is available locally and network/database command approval is granted. The safe rule is to inspect the SQL first, run exactly one reviewed migration file, then verify through the matching backend health endpoint.

## Implementation Sequence

1. **10.3A telemetry inventory** - document current sheets, workflow IDs, cron jobs, backend/laptop scripts, external APIs, row counts, update frequency, and direct writes.
2. **10.3B Sunsynk current-state read model plan** - design the minimum backend payload for Oom Sakkie power questions.
3. **10.3C telemetry schema proposal** - prepare SQL planning for source registry, latest-state, rollups, raw readings, and alerts.
4. **10.3D ingestion decision** - decide whether n8n, backend cron, laptop script, or existing logger should write to Supabase first.
5. **10.3E read-only backend endpoint first** - build one safe read-only endpoint for current Sunsynk state before changing Oom Sakkie.
6. **10.3F Oom Sakkie power tool update** - update `2.2` to call the backend read model instead of reading multiple sheets through an agent loop.
7. **10.3G weather/forecast alignment** - decide whether weather stays sheet-backed for now or gets the same backend read-model treatment.
8. **10.3H irrigation command boundary** - plan backend-owned command/audit endpoints before any new Telegram irrigation controls.

## 10.3D Ingestion Decision

Decision:

- The existing Render Sunsynk logger should call the Flask backend.
- The backend should validate the reading, normalize fields, write `power_readings_5min`, update `power_latest_state`, and later serve Oom Sakkie from `GET /api/telemetry/power/current`.
- The logger should not write directly to Supabase for the preferred path.
- The logger may continue writing to Google Sheets temporarily as a visible mirror during transition, but Google Sheets must not be Oom Sakkie's current-state source.

Reasoning:

- Backend-owned ingest keeps validation, stale/read-model rules, and future audit behavior in one place.
- It prevents the logger from needing database credentials.
- It lets Render cron fail safely through one controlled API contract.
- It avoids putting direct Supabase write credentials into n8n or logger code if not needed.

Required secret:

- Backend and logger need a shared secret called `TELEMETRY_INGEST_API_KEY`.
- The logger sends it as `X-Amadeus-Telemetry-Key`.
- The backend rejects missing/invalid keys before touching Supabase.
- Do not store this key in docs, workflow JSON, or source files.

10.3D local implementation result:

- `POST /api/telemetry/power/ingest` is implemented locally.
- It accepts the current Sunsynk logger fields such as `timestamp_za`, `soc`, `batt_power`, `pv_total`, `pv1`, `pv2`, `load_power`, `grid_power`, `gen_power`, `inv_pac`, `grid_active`, `gen_active`, `battery_charging`, and `battery_discharging`.
- It derives battery/grid/generator states, deterministic flags, and backend summary wording.
- It writes/upserts one raw 5-minute row and one latest-state row.
- It is protected by `TELEMETRY_INGEST_API_KEY`.

## 10.3E Current Power Backend Endpoint

Endpoint:

- `GET /api/telemetry/power/current`

Purpose:

- Return the 10.3B agreed current-state payload from Supabase `power_latest_state`.
- Include source freshness, stale flag, deterministic current state, flags, backend-prepared summary, and units.
- Return `success = false`, `status = unavailable` with HTTP `200` if the schema exists but no latest reading has been ingested yet.

Local implementation result:

- `GET /api/telemetry/power/current` is implemented locally.
- `POST /api/telemetry/power/ingest` is implemented locally because the selected ingestion path requires it.
- Local route smoke without required env/config returned safe failures:
  - current endpoint: `503`, `status = not_configured` when `DATABASE_URL` is missing
  - ingest endpoint: `503`, `status = ingest_key_not_configured` when `TELEMETRY_INGEST_API_KEY` is missing
- Focused telemetry tests passed locally at 8 tests.
- Full local unittest suite passed at 219 tests.

Deploy/test gate:

- Add `TELEMETRY_INGEST_API_KEY` to Render backend environment.
- Deploy the backend.
- Confirm `GET /api/telemetry/power/current` returns either current data or `status = unavailable` before the first ingest.
- Send one safe synthetic/test Sunsynk payload to `POST /api/telemetry/power/ingest` with `X-Amadeus-Telemetry-Key`.
- Confirm the ingest returns `success = true`, `writes_to_supabase = true`.
- Confirm `GET /api/telemetry/power/current` returns that latest state.
- Only after this test should the Render Sunsynk logger be updated.

10.3D/10.3E deployed verification result:

- Passed on 2026-05-21.
- Synthetic ingest to `POST /api/telemetry/power/ingest` returned `success = true`, `status = ok`, `source_id = sunsynk-main-inverter`, `reading_id = PWR-FEC6256BECB7`, and `source.writes_to_supabase = true`.
- Readback from `GET /api/telemetry/power/current` returned the synthetic state from Supabase:
  - battery SOC `82%`
  - battery state `charging`
  - solar `3120 W`
  - load `1240 W`
  - grid state `not_using_grid`
  - generator state `off`
  - deterministic flags present
  - summary status `stale`, because the synthetic test timestamp was intentionally older than the 15-minute stale threshold
- Security note: rotate `TELEMETRY_INGEST_API_KEY` before wiring the real Render Sunsynk logger if the current test key was pasted into chat or logs.

## 10.3F Sunsynk Logger Update

Goal:

- Update the Render Sunsynk cron logger to feed the new backend ingest endpoint.
- Keep Google Sheets as a temporary mirror while the Supabase path is proven.
- Do not update Oom Sakkie `2.2` until the real logger has produced a fresh Supabase reading.

Local implementation result:

- Updated `external_sources/telemetry/sunsynk/amadeus-sunsynk-logger/main.py`.
- Added logger README at `external_sources/telemetry/sunsynk/amadeus-sunsynk-logger/README.md`.
- Logger now posts the same normalized Sunsynk reading to `POST /api/telemetry/power/ingest` when both env vars are present:
  - `AMADEUS_BACKEND_URL`
  - `TELEMETRY_INGEST_API_KEY`
- Logger still writes to Google Sheets by default while `GOOGLE_SHEETS_ENABLED` is not `false`.
- Logger can later disable the sheet mirror with `GOOGLE_SHEETS_ENABLED=false`, but only after Supabase ingest has been stable.
- Render cron test on 2026-05-21 failed in the Google Sheets mirror path with `gspread.exceptions.APIError: APIError: [404]: Requested entity was not found.` The deployed `/api/telemetry/power/current` readback still showed the old synthetic reading, so a fresh real Sunsynk reading had not yet landed in Supabase.
- Logger was hardened locally after that test: if backend ingest succeeds but the Google Sheets mirror fails, the cron records `google_sheets_error` and exits successfully instead of losing the run. If the backend ingest does not succeed, a Google Sheets failure still fails the cron.
- Render cron source was changed from the separate `amadeus-sunsynk-logger` repo to the main `amadeus-pig-tracking-system` repo, with root directory `external_sources/telemetry/sunsynk/amadeus-sunsynk-logger`.
- A trailing-space typo in the Render root directory caused path confusion during setup; remove any trailing spaces from the root directory field.
- Deployed verification passed on 2026-05-22: Render cron printed `backend_ingest_enabled = true`, `backend_ingest_success = true`, reading ID `PWR-49F0F62E4F21`, `google_sheets_written = true`, `google_sheets_error = null`, and timestamp `2026-05-22T00:28:20+02:00`.
- Backend readback from `/api/telemetry/power/current` returned a real fresh state with `data_age_minutes = 0`, `is_stale = false`, battery `47%`, battery state `discharging`, load `872 W`, solar `0 W`, grid `0 W`, and generator `0 W`.
- Local syntax verification passed with `python -m py_compile`.

Render cron env vars to add:

| Env Var | Value |
| --- | --- |
| `AMADEUS_BACKEND_URL` | `https://amadeus-pig-tracking-system.onrender.com` |
| `TELEMETRY_INGEST_API_KEY` | Same rotated value configured on the backend. |
| `GOOGLE_SHEETS_ENABLED` | Currently allowed as `true` because the verified cron run wrote both backend and Google Sheets successfully. Set to `false` later when the mirror is no longer needed. |

Deploy/test gate:

- Deploy the updated Sunsynk logger code to the Render cron service.
- Run/wait for one cron execution.
- Confirm Render cron logs show:
  - `backend_ingest_enabled = true`
  - `backend_ingest_success = true`
  - `google_sheets_written = false` and `google_sheets_enabled = false` if the mirror is disabled for recovery, or `google_sheets_written = true` if the sheet mirror is fixed and enabled
- Confirm `GET /api/telemetry/power/current` returns a fresh reading with `is_stale = false` or a small `data_age_minutes`.
- Only then move to updating Oom Sakkie `2.2`.

Status:

- Complete and deployed-verified on 2026-05-22.
- Next implementation slice: update Oom Sakkie `2.2` so power questions call `/api/telemetry/power/current` instead of reading Sunsynk Google Sheets.

## 10.3G Oom Sakkie Power Tool Update

Goal:

- Replace the slow `2.2` Google Sheets/LangChain agent path with a deterministic backend current-power worker.
- Keep this slice limited to current/live power status.
- Do not re-enable daily totals, kWh, last-24h trends, or interval analysis until backend read models exist for those shapes.

Local implementation result:

- Updated `docs/04-n8n/workflows/2.2 - Amadeus Sunsynk Sub-Agent/workflow.json`.
- `2.2` now has only:
  - `When Executed by Another Workflow`
  - `HTTP - Get Current Power State`
  - `Code - Format Current Power Answer`
  - a sticky note
- Removed the `AI Sunsynk Agent`, `OpenAI Chat Model`, and all Sunsynk Google Sheets tool nodes from the `2.2` export.
- Updated `2.0 - OOM SAKKIE` `Sunsynk_Info_Tool` description so the main assistant treats this as a backend/Supabase current-power tool.
- Updated n8n workflow docs and workflow map.

Local verification:

- Both updated workflow JSON files parse successfully.
- Backend endpoint readback before import returned fresh data with `is_stale = false` and low `data_age_minutes`.

Import/test gate:

- Import `docs/04-n8n/workflows/2.2 - Amadeus Sunsynk Sub-Agent/workflow.json` into n8n.
- Import `docs/04-n8n/workflows/2.0 - OOM SAKKIE - Amadeus Assistant Agent/workflow.json` into n8n so the tool description matches the new behavior.
- Ask Oom Sakkie: `What's the power like now?`
- Expected result: one timely Telegram answer with battery, solar, load, grid, generator, latest reading time, and no Google Sheets delay.
- Ask Oom Sakkie a daily/last-24h power question.
- Expected result for now: the answer should state that this tool currently supports current/live power state only and that daily/kWh/trend read models are planned later.

Live verification:

- Passed on 2026-05-22 after importing `2.2` and `2.0` into n8n.
- Telegram test `What's the power like now?` returned quickly with current backend/Supabase data:
  - battery `46%`, `discharging`
  - solar `0.0 kW`, PV1 `0 W`, PV2 `0 W`
  - load `1.0 kW`
  - grid `not using grid`, `0 W`
  - generator `off`, `0 W`
  - latest reading `22 May 2026, 00:40`, `4 minutes old`
- Result confirms current power answers no longer depend on slow Sunsynk Google Sheets reads.

## 10.3H Recent Power Profile Endpoint

Goal:

- Add a read-only backend endpoint for recent power profile questions such as "what happened in the last 24 hours?"
- Keep the first version sample-based and honest.
- Do not claim kWh, cost, import, or export totals until reliable Sunsynk energy counters or approved interval-integration rules exist.

Endpoint:

`GET /api/telemetry/power/recent?hours=24`

Local implementation result:

- Added `get_recent_power_profile()` in `modules/telemetry/power_service.py`.
- Added route `GET /api/telemetry/power/recent` in `modules/telemetry/telemetry_routes.py`.
- The endpoint reads recent rows from `power_readings_5min`.
- The endpoint returns:
  - requested window and data coverage
  - first and last reading timestamps
  - battery latest/min/max/average SOC
  - charging/discharging approximate minutes
  - average/max solar and load power
  - grid/generator active sample counts and approximate minutes
  - hourly buckets for trend display
  - explicit limitations that these are sample-based power readings, not kWh totals

Local verification:

- Focused telemetry/workflow tests pass at 11 tests.
- Full local test suite passes at 221 tests.

Deploy/test gate:

- Deploy backend.
- Open `/api/telemetry/power/recent?hours=24`.
- Confirm it returns `success = true`, a non-zero `row_count`, `coverage_pct`, battery/power/activity sections, and explicit limitations.
- Only after that should `2.2` be expanded to answer last-24h trend questions from this endpoint.

First deployed check:

- Endpoint returned `success = true`, 24 rows, coverage, battery/power/activity/hourly sections, and limitations.
- The response still included the old synthetic ingest row (`82%`, `3120 W`) because it was inside the 24-hour window and had no real cron raw payload.
- Follow-up local patch now filters `raw_payload is not null`, so synthetic/manual test rows are excluded from recent profile summaries.
- Focused telemetry/workflow tests still pass at 11 tests after the filter patch.
- Redeploy backend and recheck before wiring Oom Sakkie last-24h questions.

## Must Not Do In 10.3 Planning

- Do not change live n8n workflows yet.
- Do not create telemetry SQL migrations before the inventory is complete.
- Do not move irrigation command execution until secrets and audit are designed.
- Do not break the currently working weather flow.
- Do not let Oom Sakkie scan raw high-volume telemetry tables.
- Do not build dashboard widgets until the read models are defined.

## 10.3A Inventory Owner Inputs

Confirmed on 2026-05-21:

- Sunsynk, weather station, and forecast loggers run as Render cron services.
- Irrigation appears to be n8n-run.
- External logger source folders are filed under `external_sources/`.
- Production Google Sheet IDs for Sunsynk, weather, and irrigation are documented above.
- Service-account access now works for spreadsheet metadata and for weather/irrigation value inventory.
- Sunsynk values reads are still unreliable/too slow, even after access was granted.

Still needed before build decisions:

- Exact raw-retention window for 5-minute Sunsynk data.
- Whether Google Sheets should remain as a temporary visible mirror after Supabase writes begin.
- Whether `Sunsynk_Cost_Data` is required in the first power endpoint or can wait for a dashboard/cost phase.
- Whether the Render cron logger should write directly to Supabase or call a backend endpoint. Current recommendation: call a backend endpoint where practical, so validation and read-model ownership stay in the app.

## Recommended First Build After Planning

The first implementation should be read-only:

- import or mirror only enough Sunsynk data to answer "what is the power like now?"
- expose one backend endpoint with a compact response
- test that endpoint directly
- then update `2.2` to call that endpoint

This should fix the slow Oom Sakkie power path without changing live hardware control or forcing a full telemetry migration in one step.

## Data Retention And Rollup Direction

Owner proposal on 2026-05-21:

- Do not keep every 5-minute reading forever if it is not useful.
- Keep current-state data for immediate questions.
- Roll 5-minute readings into daily totals/summaries.
- Roll daily summaries into monthly summaries.
- Roll monthly summaries into yearly summaries.
- Delete or archive lower-level detail once the summary level is trusted, so data stays useful and compact.

Recommended approach:

- Keep raw 5-minute Sunsynk data for a short retention window first, for example 7 to 31 days. This protects debugging and lets us rebuild rollups if a formula is wrong.
- Keep daily rollups permanently or long-term.
- Keep monthly and yearly rollups permanently.
- Keep latest/current-state snapshots permanently as overwritten rows or small latest-state tables.
- Do not physically delete raw data until rollup jobs are tested and a backup/export rule exists.
- Mark rollups with source window, row count, generated timestamp, and calculation version so we can trust where totals came from.
- For Oom Sakkie, use current-state, daily, hourly, monthly, yearly, and alert read models. Do not let it scan raw 5-minute history.

Likely Sunsynk retention model:

| Layer | Purpose | Retention |
| --- | --- | --- |
| `power_latest_state` | "What is happening now?" | Keep one latest row per source/inverter. |
| `power_readings_5min` | Debug, recent charts, rollup source | Short window first, likely 7-31 days unless storage/cost says otherwise. |
| `power_hourly_rollups` | Last 24h and trend answers | Medium-term, for example 90 days. |
| `power_daily_rollups` | Daily totals and comparisons | Long-term/permanent. |
| `power_monthly_rollups` | Monthly totals and reporting | Permanent. |
| `power_yearly_rollups` | Yearly totals and long-term trend | Permanent. |
| `telemetry_alerts` | Audit of warnings and notable events | Long-term/permanent. |

Decision still needed:

- Exact raw-retention window for 5-minute Sunsynk data.
- Whether raw weather data should also be rolled up/deleted or kept longer because it is lower volume.
- Whether Google Sheets should be cleaned after Supabase rollups are proven, or left as legacy history.
