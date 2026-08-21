# Amadeus Green Print Bridge

This private app hosts a local CUPS daemon and the bounded Documents adapter on Home Assistant Green. It is source-only and uncommissioned until the separate physical acceptance journey succeeds.

## Security and configuration

Keep Home Assistant, the printer and the canonical Documents endpoint on the private farm network. Do not publish ports or use a tunnel. Install the private CA certificate at the fixed `/config/private-ca.crt` path through this app's Home Assistant `addon_config` directory; the app refuses missing certificate trust and never disables TLS verification. The canonical intake path is fixed in source and cannot be changed through options. Enter the remaining runtime values only in the Home Assistant app options UI. Do not place them in Git, examples, screenshots, support bundles or shell history.

The configured `cups_queue_id` and `printer_uri` are commissioning-time registry values, never request fields. The app accepts only `farm.weekly_weight_sheet.v1`, generator `web.print_sheets.v1`, A4, one copy, monochrome and one-sided. The canonical bearer credential must have only claim/read/event permissions for the print-job API and digest-bound PDFs.

## Runtime, recovery and health

Supervisor starts the app automatically and restarts it after failure. `/data/green-print-ledger.sqlite3` is crash-recovery state only; Supabase/Documents remains canonical. PDFs exist only under the tmpfs spool and are deleted after each attempt. `/data/health.json` reports worker identity, heartbeat, last/next poll and the last bounded result without secrets or document content. A cold backup stops the app before copying `/data`; temporary spool is excluded.

On restart, persisted submission attempts are reconciled before the app polls new canonical intake. An attempt with a known CUPS job is observed before any retry. A persisted attempt without a provider job identity becomes ambiguous and cannot auto-retry. Provider completion is not physical completion. HTTPS redirects are refused; the canonical and printer hostnames must resolve only to private or link-local addresses.

## Install and commissioning

1. Review the exact commit and build the aarch64 artifact from its pinned Dockerfile or add this private repository for a local Supervisor build. `build.yaml` remains only as a backward-compatible Supervisor hint; current builds take their base image and labels from `Dockerfile`.
2. Add the repository in the Home Assistant app store; install but do not start until the canonical endpoint, least-privilege token, registry identities, printer URI and private CA are commissioned.
3. Validate options and start the app. Confirm health is `event_waiting`, the local queue exists, logs contain no option values, and no job is eligible.
4. Follow `docs/06-operations/GREEN_PRINT_BRIDGE_PHYSICAL_COMMISSIONING_GUIDE.md`. The development terminal must never manufacture the genuine request or operate the printer.

## Restore, rollback and uninstall

Restore only a cold backup paired with current canonical Supabase truth. Before enabling the restored worker, reconcile every non-terminal local job against canonical job state and CUPS; never submit from backup state alone.

Rollback by stopping the app, revoking its canonical credential, and retaining the prior manual print path. Preserve `/data` evidence until canonical reconciliation is complete. Uninstall only after the credential is revoked, every known CUPS job and canonical job is reconciled, and required audit metadata is exported through the protected process. Supervisor removal deletes local recovery state; it does not cancel a provider job or change canonical truth.
