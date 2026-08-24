# Green Print Bridge physical commissioning guide

Lifecycle classification: transitional commissioning guide; not commissioned. Pilot: `farm.weekly_weight_sheet.v1` only. It becomes active only after canonical PDF/request/confirmation source, a reviewed crash-safe adapter, deployment, and fresh physical acceptance succeed.

## Reviewed Home Assistant OS architecture decision

The smallest supported target is the private aarch64 Home Assistant app in
`green_print_bridge/`, not a privileged host modification and not a separate
computer. Official Home Assistant app constraints provide an isolated container,
persistent `/data`, tmpfs, automatic boot, cold backup, option schemas, read-only
`addon_config` certificate injection and AppArmor. The candidate maps no Home
Assistant configuration, Docker socket, hardware bus or host network; publishes
no port; and requests no privileged capability. Local CUPS and the adapter can
therefore run inside protection mode. A separate private host becomes necessary
only if commissioning proves the printer cannot be reached through ordinary
private container networking or its driver cannot run on aarch64 without
privileged device/host access. That blocker is not currently demonstrated.

Architecture sources reviewed on 2026-08-21:

- https://developers.home-assistant.io/docs/apps/
- https://developers.home-assistant.io/docs/apps/configuration/
- https://developers.home-assistant.io/docs/apps/repository/
- https://developers.home-assistant.io/docs/apps/security/
- https://developers.home-assistant.io/docs/apps/publishing/

Current Home Assistant documentation deprecates `build.yaml` for current build
pipelines. The app's pinned base image and OCI/Home Assistant labels therefore
live in `Dockerfile`; the retained `build.yaml` is compatibility-only and may be
removed in a later separately reviewed cleanup after supported Supervisor
versions no longer consume it.

This guide is for Charl's later, explicitly authorized on-site commissioning. It does not authorize a print, configuration change, credential change, deployment, public exposure, or farm-data write. Stop whenever an observation differs; record it as Unknown and return it to the technical maintainer. Do not improvise.

For the current 0.3.1 dormant state and the exact zero-actuation facts required
before this guide may be used, first complete
`GREEN_PRINT_031_NON_ACTUATING_COMMISSIONING_PREFLIGHT_20260822.md`. That packet
does not authorize starting or configuring the app, accessing the printer,
creating a queue/job or printing.

## Before the appointment

1. Confirm the Documents backend version containing the reviewed Green adapter contract is merged and deployed. If not, stop.
2. Confirm Oom Sakkie's existing authenticated owner/family path can resolve the canonical current weekly weighing sheet. Do not use a file path, old download, or manually created PDF.
3. Ask the technical maintainer for a one-use commissioning window and the protected identity-registration procedure. Charl must not invent IDs, URLs, tokens, certificates, queue names, or passwords.
4. The 2026-08-24 owner decision accepts the farm-house printer's confidentiality and local-network risk for practical farm-team-only use. Private PKI, TLS/IPPS and certificate setup are not commissioning gates. Keep the adapter bound to the fixed approved printer and queue; do not expose a public arbitrary-print endpoint.
5. Have A4 paper available. Do not load confidential discarded sheets for reuse.
6. Review the exact app commit and `green_print_bridge/DOCS.md`. Preserve the
   prior manual print path; installation does not retire it.

## Observe without changing anything

1. Read the label on the Home Assistant Green and record its serial/model privately; do not place it in chat, logs, screenshots, or this repository.
2. Read the printer label and confirm it says HP OfficeJet Pro 8123. Record serial and network facts privately.
3. On the printer screen, note ink/paper/error state. Do not print a diagnostic page.
4. In the router's private admin view, confirm both devices appear on the intended private LAN. Do not create forwarding rules or expose services.
5. If the model, network membership, or security state is uncertain, stop. The exact blocker is “registered physical identity/private-network fact unavailable.”

## Technical maintainer's protected setup (Charl observes)

1. The maintainer registers one Green identity and one printer identity in the canonical protected registry, binding observed serials without logging secrets.
2. The maintainer configures CUPS locally for that printer and verifies the queue is reachable only from the private adapter host. The queue name is treated as configuration, never shell input from a request.
3. The maintainer installs a bounded adapter credential that can claim one authorized job and retrieve only its digest-bound PDF from the configured origin.
4. Private PKI/TLS/IPPS is not required for this farm-house deployment. The fixed approved printer, fixed queue, exact canonical job identity and digest remain mandatory; no caller may choose an arbitrary printer, queue, URL or print payload.

Current runtime gap: `green_print_bridge/DOCS.md` and the existing app still
require `private_ipps`, a private CA and TLS validation. Open PR #1194 further
hardens that superseded policy and must not merge. This owner decision is not
operative until a bounded reviewed source correction replaces those gates while
preserving the minimum integrity contract above.
5. The maintainer configures the durable local SQLite ledger and private spool with restricted permissions, disk monitoring, restart supervision, and no document-content logging.
6. The maintainer sets the only allowed options: A4, one copy, monochrome, one-sided. No request can override them.
7. The maintainer verifies restart recovery, expired-lease recovery, storage-exhaustion fail-safe, 48-hour retry-to-held transition, Continue/Cancel handling, and deletion of temporary PDFs after completion, cancellation, or held resolution using synthetic non-farm fixtures only.
8. The maintainer proves that Green/CUPS is only a local execution adapter: the canonical Documents service owns request/job identity and Oom Sakkie delegates exactly one job. No Home Assistant automation, CUPS queue, spreadsheet, or local database becomes an authoritative document queue.
9. Add the private repository and configure the app through Home Assistant only
   after the exact artifact passes review. Never paste credentials or options
   into a shell or log.
10. Confirm the app starts in protection mode with no published ports, host
    network, Docker socket, Home Assistant config map, USB or privileged access.
    Confirm `/data/health.json` reports a fresh `event_waiting` heartbeat and no
    eligible job before the genuine acceptance window.

## Authorized pilot acceptance (separate future window)

1. Charl naturally asks Oom Sakkie for the current weekly weighing sheet through the existing authenticated channel. This resolves the canonical action; it does not itself authorize physical submission while print standing authority remains Unknown.
2. Confirm Oom Sakkie resolves the canonical current sheet and creates exactly one canonical job identity. If two jobs appear, stop and Cancel; do not retry manually.
3. Use the existing protected confirmation rail to authorize that exact job, version, digest, registered device pair, defaults, and expiry. Confirm the adapter claims it with a fenced lease, persists a unique pre-submission attempt, retrieves only from the allowlisted private HTTPS origin, and matches its SHA-256 before submission.
4. Confirm CUPS reports the exact provider job ID, provider state, and observation time. Application logs must contain identities, states, digests, and timestamps only—never secrets or PDF content.
5. Require truthful CUPS/provider and canonical printed-or-failed readback for the exact job. The farm team reports a missing, duplicate, wrong or damaged page as an exception; routine human observation is not a commissioning gate.
6. Confirm the owner receives only completion, or one exception that says what action is needed. Do not send duplicate Telegram updates.
7. Confirm the temporary PDF is gone while durable metadata, digest, lease chronology, exact CUPS evidence, and protected confirmation remain.
8. Record canonical/provider result and any volunteered physical exception separately. Never manufacture a missing layer.

## Exception paths

1. Offline/unreachable: leave automatic bounded retries active. After 48 hours the job must become Held and present only Continue or Cancel. Repeated owner retry requests are a defect.
2. Continue: only the protected owner action may release the same canonical job to retry; it must not create a second job. The PDF must be freshly retrieved and digest-checked.
3. Cancel: require the protected owner action, cancel any known CUPS job if safe, close the canonical job, and delete the temporary PDF.
4. Paper jam, wrong output, duplicate page, or uncertain physical result: do not claim completion and do not auto-reprint. Hold with one actionable exception because CUPS evidence cannot prove the physical page.
5. Low disk, digest mismatch, unsafe URL, identity mismatch, lease conflict, restart ambiguity, or missing evidence: fail closed before submission and escalate one exception without secrets/content.

## Rollback

1. Disable only the bounded Green adapter worker through its private supervisor; do not disable the canonical Documents lifecycle or Oom Sakkie.
2. Revoke the adapter credential and registration using the protected procedure.
3. Preserve durable non-content metadata/evidence for audit; remove temporary PDFs through the adapter cleanup path.
4. Remove the local CUPS queue only if the maintainer confirms it has no unrelated owner. Do not alter printer/network/Home Assistant configuration merely to roll back source.
5. The prior manual weekly-sheet journey remains available until the operational pilot is proven and explicitly retired.
6. Before restore or uninstall, stop the app and reconcile every local
   non-terminal job against canonical Supabase and CUPS. Restoring SQLite never
   authorizes submission. Revoke the credential before uninstall; retain required
   content-free audit evidence because Supervisor removal deletes `/data`.
