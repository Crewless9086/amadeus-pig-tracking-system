# Telemetry Data Model

Telemetry covers weather, forecast, Sunsynk/power, irrigation, alerts, and rollups.

## Operating Direction

- Keep working weather behavior stable while migrating the slow/high-volume paths.
- Sunsynk/power is the urgent migration candidate because Google Sheets reads can be slow or time out.
- Agents must receive small prepared backend payloads, not raw high-volume sheets/tables.
- n8n remains useful for schedules and delivery, but backend/Supabase should own state, rollups, cooldowns, duplicate prevention, and business/safety rules.
- Human notifications and automation triggers are different things and must not be mixed into one vague alert bucket.

## Read Models Agents Should Use

| Read model | Purpose |
| --- | --- |
| Current power status | Battery/grid/load/solar state, data age, warning flags. |
| Power daily summary | Today/yesterday/week/month power answers and comparisons. |
| Power hourly rollup | Last-24h trend without scanning raw intervals. |
| Current weather | Latest station reading, data age, rain/wind/temp/humidity flags. |
| Forecast summary | Compact forecast periods and risk flags. |
| Recent alerts | What happened recently, severity, cooldown/audit context. |
| Irrigation status | Current plan, zone state, pauses/skips, no hardware control. |

## Rollup Rules

- Daily rollups are the trusted reporting layer.
- Monthly rollups are built from daily rollups.
- Yearly rollups are built from monthly rollups.
- Store sample count, expected sample count, coverage percentage, calculation version, and limitations.
- Power raw/weather raw retention default is `90 days` initially, then review storage/cost.
- Irrigation events/plans should be long-term/permanent unless volume becomes a problem.

## Hardware-Control Rules

- Irrigation and pump actions must be backend-owned with explicit audit rows before automatic control expansion.
- n8n can call/deliver actions, but must not invent safety rules.
- Telegram should not receive every automation event; use severity, grouping, quiet hours, and summaries.

## Source References

- `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`

Agents should read prepared telemetry payloads rather than raw high-volume tables:

- latest state;
- daily summaries;
- hourly rollups;
- weekly/monthly rollups;
- alert logs;
- small owner-ready JSON.
