# HERDMASTER litter weaning recovery: LIT-2026-322B

Status: production record recovered; permanent workflow correction pending integration
Opened: 2026-07-28 SAST
Owner intent: finish the already-started weaning record once, preserve the submitted facts, and prevent duplicate treatment, weight, movement, and lifecycle records.

## Incident

The owner previewed and submitted the full Weaning Day form for `LIT-2026-322B`. The production request exceeded the worker timeout while medical-event rows were being inserted sequentially through separate database connections. The server returned an HTML 500 response and the browser attempted to parse it as JSON, displaying:

`Unexpected token '<', "<html> <"... is not valid JSON`

This was an application defect, not an owner input error.

## Authoritative production state after the stopped request

- Litter status: `Active`
- Wean date: not recorded
- Active on-farm piglets: 10
- Sex count: 8 male, 2 female
- Tag numbers: 131 through 140 recorded
- Current pen: `PEN-009` for all ten piglets
- Wean weights: not recorded
- Weight-log rows from this operation: none established
- Movement rows from this operation: none established
- Mark-weaned lifecycle update: not performed
- Treatment date represented by the committed rows: `2026-07-27`

Seventeen treatment rows committed before the timeout:

- Tags 131 through 138: `PRD-001` Antiparasitic and `PRD-002` Deworming present
- Tag 139: `PRD-001` present; `PRD-002` missing
- Tag 140: both `PRD-001` and `PRD-002` missing

The three missing treatment facts must be reconciled without duplicating the seventeen committed rows.

## Owner-confirmed recovery facts

Confirmed by Charl on 2026-07-28:

| Tag | Wean weight |
| --- | ---: |
| 131 | 6.6 kg |
| 132 | 5.2 kg |
| 133 | 7.8 kg |
| 134 | 7.2 kg |
| 135 | 6.2 kg |
| 136 | 6.8 kg |
| 137 | 7.2 kg |
| 138 | 6.6 kg |
| 139 | 7.4 kg |
| 140 | 5.8 kg |

- Target pen: `PEN-012` (`Skeer 2`)
- Wean date: `2026-07-27`
- Antiparasitic product: `PRD-001`
- Deworming product: `PRD-002`
- Vaccination: none
- All other submitted data: confirmed correct

## Required correction

1. Replace per-treatment connection acquisition with a bounded transactional write path.
2. Give the full weaning packet a stable operation identity and idempotent replay behavior.
3. Detect the existing partial state and insert only missing treatment facts.
4. Apply weights, movements, pig/litter weaning fields, and treatment reconciliation atomically wherever the production datastore permits.
5. Return structured JSON for server failures and make the browser tolerate non-JSON error responses.
6. Verify exact replay creates no additional rows.

## Completion evidence

This incident is complete only when:

- all ten intended weights are recorded exactly once;
- the intended treatments exist exactly once per piglet;
- intended pen movements exist exactly once, or are explicitly not required;
- the litter and its ten active piglets carry the correct wean date and weaned state;
- replay creates zero additional rows;
- the owner page reloads successfully and displays the completed locked history.

Until then, do not resubmit the original form.

## Production recovery result

Completed on 2026-07-28 through one bounded database transaction after an exact read-only preflight.

- Piglets verified: 10
- Treatment facts: 20 exactly; the 17 committed rows were preserved and only the 3 missing facts were inserted
- Weaning weight events: 10 exactly, matching the owner-confirmed values
- Movement events from `PEN-009` to `PEN-012`: 10 exactly
- Piglets classified as `Weaner`: 10
- Piglets currently projected in `PEN-012`: 10
- Piglets carrying the correct wean date and weight: 10
- Litter wean date: `2026-07-27`
- Litter weaned count: 10
- Litter status: `Weaned`
- Conflicting facts encountered: none

The owner does not need to resubmit this litter.

## HERDMASTER follow-up

The production record is complete, but the original application defect remains a P0 workflow-reliability item until the reviewed correction is integrated and deployed:

- make the full Supabase weaning-day packet transactional and replay-safe;
- remove per-row connection acquisition from treatment, weight, and movement writes;
- return JSON-safe failure information to the browser;
- retain a recoverable operation identity and explicit partial-state reconciliation.
