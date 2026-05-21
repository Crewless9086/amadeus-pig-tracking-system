# External Sources

This folder stores source evidence copied from related Amadeus projects.

These files are not part of the live Flask app unless they are deliberately migrated into app modules later.

## Structure

- `telemetry/sunsynk/` - Sunsynk logger source evidence.
- `telemetry/weather/` - local weather station logger source evidence.
- `telemetry/forecast/` - forecast logger source evidence.
- `web/` - related non-telemetry website/landing assets.

## Secret Handling

Do not commit local secrets from this folder.

The repo `.gitignore` excludes nested `.env` files and common secret-looking files under `external_sources/`.

If a source folder contains real API keys, passwords, service account JSON, webhook URLs, or device credentials, keep them in ignored local files only and move production values into Render/n8n/Supabase/backend environment variables during implementation.
