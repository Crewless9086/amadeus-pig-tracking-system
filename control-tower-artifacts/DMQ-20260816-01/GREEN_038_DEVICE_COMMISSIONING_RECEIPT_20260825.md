# GREEN 0.3.8 device commissioning receipt

Mission: `DMQ-20260816-01` / existing GREEN-DOCUMENTS weekly print lineage.

Lifecycle: `WORKING / BRIDGE_ACTIVE / GENUINE_PRINT_ACCEPTANCE_WAITING`.

## Verified release and device evidence

- Merged source: `844d3a10944e07a5341602ea18b337fca16b0dbd`.
- Publication workflow: `32810759240`, successful.
- Package: `ghcr.io/crewless9086/amadeus-green-print-bridge:0.3.8`.
- Immutable arm64 index digest:
  `sha256:587e0a21237d5706d42122161a5ec71ae75be54f4cf5db283ee26e5d922ee9bd`.
- Supply chain: Cosign, provenance, SPDX SBOM, source/version/platform labels
  and tag-to-digest equality verified by the guarded workflow.
- Charl installed 0.3.8 through Home Assistant.
- Saved printer profile: `local_ipp_fixed`.
- Saved exact queue URI:
  `ipp://192.168.0.118:631/printers/weekly-a4`.
- Home Assistant after stability wait: `Current version 0.3.8`, `Running`.

No print job, provider submission or physical page was created during this
commissioning step. The bridge is active; a printed owner outcome remains
unproven.

## Reused acceptance journey

Reuse `modules/oom_sakkie/documents_green_request_runtime.py`,
`modules/documents/weekly_weight_sheet.py`, the `documents_green_print`
protected claim in `modules/oom_sakkie/protected_action_runtime.py`, the
canonical Green print-job API and the installed worker. The only pilot document
is `farm.weekly_weight_sheet.v1`; the exact queue/options are registry-bound.

The next automatic action is an idle polling/heartbeat cycle with zero eligible
jobs. When a genuine farm need naturally produces the existing private weekly
weighing-sheet request, Oom Sakkie creates one preview. The requesting actor
confirms it; Green handles the resulting immutable canonical job exactly once.
The existing separate protected page follow-up records physical truth and never
auto-reprints. No terminal may synthesize the request, confirmation, document,
job or physical acceptance.

OWNER ACTION: NONE.
