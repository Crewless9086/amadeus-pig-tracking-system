# Vault Cutover Batch 8 Reconciliation

Status: remaining external archive candidates resolved as current technical references; no deletion or move performed.

Date: 2026-08-18

## Reviewed documents

| Source | Binding disposition | Reason |
| --- | --- | --- |
| `external_sources/AMADEUS_HALF_CARCASS_CUTTING_STANDARD_v1.0.md` | Keep technical/business reference. | Still consumed by current Vault business authority, meat UI, tests and operational sales material. It cannot independently govern agents. |
| `external_sources/README.md` | Keep technical. | Current external-source boundary and secret-handling instructions. |
| `external_sources/telemetry/forecast/amadeus-forecast-logger/README.md` | Keep technical. | Current Render schedule, provider-limit and backend-ingest contract. |
| `external_sources/telemetry/sunsynk/amadeus-sunsynk-logger/README.md` | Keep technical. | Current backend-ingest and transitional Sheets-mirror contract. |

## Safety result

- No document passed the strict deletion or archive test.
- The manifest now has zero unresolved `ARCHIVE_CANDIDATE` entries.
- Vault doctrine remains authoritative; these files provide implementation or source evidence only.
- No move, deletion, doctrine expansion, runtime, provider, production-data or authority change occurred.

## Next boundary

Continue with a fresh owner-approved family from the regenerated manifest. Any
later retirement of these files requires exact replacement, reference migration
and current runtime/provider proof.
