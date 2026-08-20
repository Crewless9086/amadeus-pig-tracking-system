# Green Print Bridge physical commissioning guide

Lifecycle classification: transitional commissioning guide; not commissioned. Pilot: `farm.weekly_weight_sheet.v1` only. It becomes active only after canonical PDF/request/confirmation source, a reviewed crash-safe adapter, deployment, and fresh physical acceptance succeed.

This guide is for Charl's later, explicitly authorized on-site commissioning. It does not authorize a print, configuration change, credential change, deployment, public exposure, or farm-data write. Stop whenever an observation differs; record it as Unknown and return it to the technical maintainer. Do not improvise.

## Before the appointment

1. Confirm the Documents backend version containing the reviewed Green adapter contract is merged and deployed. If not, stop.
2. Confirm Oom Sakkie's existing authenticated owner/family path can resolve the canonical current weekly weighing sheet. Do not use a file path, old download, or manually created PDF.
3. Ask the technical maintainer for a one-use commissioning window and the protected identity-registration procedure. Charl must not invent IDs, URLs, tokens, certificates, queue names, or passwords.
4. Keep Home Assistant, Green, CUPS, and the printer on the private farm network. No router port-forward, public DNS, public tunnel, cloud webhook, or Internet-exposed CUPS/Home Assistant endpoint is allowed.
5. Have A4 paper available. Do not load confidential discarded sheets for reuse.

## Observe without changing anything

1. Read the label on the Home Assistant Green and record its serial/model privately; do not place it in chat, logs, screenshots, or this repository.
2. Read the printer label and confirm it says HP OfficeJet Pro 8123. Record serial and network facts privately.
3. On the printer screen, note ink/paper/error state. Do not print a diagnostic page.
4. In the router's private admin view, confirm both devices appear on the intended private LAN. Do not create forwarding rules or expose services.
5. If the model, network membership, or security state is uncertain, stop. The exact blocker is “registered physical identity/private-network fact unavailable.”

## Technical maintainer's protected setup (Charl observes)

1. The maintainer registers one Green identity and one printer identity in the canonical protected registry, binding observed serials without logging secrets.
2. The maintainer configures CUPS locally for that printer and verifies the queue is reachable only from the private adapter host. The queue name is treated as configuration, never shell input from a request.
3. The maintainer installs a least-privilege adapter credential that can claim one authorized job and retrieve only its digest-bound PDF over the allowlisted private HTTPS origin.
4. The maintainer configures a private trust chain/certificate. Disabling TLS verification is not permitted.
5. The maintainer configures the durable local SQLite ledger and private spool with restricted permissions, disk monitoring, restart supervision, and no document-content logging.
6. The maintainer sets the only allowed options: A4, one copy, monochrome, one-sided. No request can override them.
7. The maintainer verifies restart recovery, expired-lease recovery, storage-exhaustion fail-safe, 48-hour retry-to-held transition, Continue/Cancel handling, and deletion of temporary PDFs after completion, cancellation, or held resolution using synthetic non-farm fixtures only.
8. The maintainer proves that Green/CUPS is only a local execution adapter: the canonical Documents service owns request/job identity and Oom Sakkie delegates exactly one job. No Home Assistant automation, CUPS queue, spreadsheet, or local database becomes an authoritative document queue.

## Authorized pilot acceptance (separate future window)

1. Charl naturally asks Oom Sakkie for the current weekly weighing sheet through the existing authenticated channel. This resolves the canonical action; it does not itself authorize physical submission while print standing authority remains Unknown.
2. Confirm Oom Sakkie resolves the canonical current sheet and creates exactly one canonical job identity. If two jobs appear, stop and Cancel; do not retry manually.
3. Use the existing protected confirmation rail to authorize that exact job, version, digest, registered device pair, defaults, and expiry. Confirm the adapter claims it with a fenced lease, persists a unique pre-submission attempt, retrieves only from the allowlisted private HTTPS origin, and matches its SHA-256 before submission.
4. Confirm CUPS reports the exact provider job ID, provider state, and observation time. Application logs must contain identities, states, digests, and timestamps only—never secrets or PDF content.
5. Physically inspect that exactly one A4, monochrome, one-sided weekly weighing sheet emerged. This human observation is physical evidence; CUPS “completed” alone is not.
6. Confirm the owner receives only completion, or one exception that says what action is needed. Do not send duplicate Telegram updates.
7. Confirm the temporary PDF is gone while durable metadata, digest, lease chronology, exact CUPS evidence, and protected confirmation remain.
8. Record canonical, provider, and physical evidence separately. Never manufacture a missing layer.

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
