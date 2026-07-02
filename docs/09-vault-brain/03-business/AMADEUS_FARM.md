# Amadeus Farm

The farm operating system covers pigs, litters, breeding, weights, medical events, purpose review, sales, slaughter/abattoir fallback, weather, power, irrigation, and operational dashboards.

Core rule: one pig should have one operational truth.

## Operating Principles

- Backend APIs own business rules and operational writes.
- AI agents interpret, summarize, draft, and route. They do not own hidden data truth.
- n8n orchestrates workflows and I/O, but should not become the permanent data layer.
- Supabase/Postgres is the target durable transactional and telemetry store where history, scale, audit, and querying matter.
- Google Sheets may remain useful during migration for visibility, manual review, and temporary formula views.
- Sheets must be retired table by table only after replacement web app views are accepted.
- Hardware-control secrets must live in protected credentials or environment variables, not sheet cells or workflow expressions.

## Command Structure

- CEO / farm commander: Oom Sakkie.
- Farm Operations: Herdmaster, Rootline, Gatekeeper, Quartermaster.
- Farm Sales CEO: SAM.
- Farm Sales lanes: meat sales, live pig sales, slaughter/abattoir sales, butcher/custom-cut sales.

Oom Sakkie owns farm command and operational truth. SAM owns farm sales/client interaction. Farm Sales agents must draw from the same farm truth and must not create separate shadow truth.

## Major Modules

- Sales and orders.
- Pig records.
- Weights and reports.
- Breeding and litters.
- Pork/meat business module.
- Weather.
- Sunsynk/power.
- Irrigation.
- Farm dashboard/home.

## Migration Direction

Use this sequence:

1. Map operating system and data ownership.
2. Set up Supabase foundations.
3. Migrate one bounded data area at a time.
4. Update n8n and assistant workflows to call backend APIs rather than direct sheet reads/writes.

Do not start a full Supabase migration before the module map is clear. Do not build new integrations directly on raw Google Sheets when those integrations are likely to move.

## Source References

- `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md`
- `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md`
