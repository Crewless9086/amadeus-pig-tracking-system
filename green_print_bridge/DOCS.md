# Amadeus Green Print Bridge

Version 0.3.0 uses the Home Assistant supported prebuilt image reference
`ghcr.io/crewless9086/amadeus-green-print-bridge`. Its tag may be published only
once by the guarded manual workflow. The release receipt must bind the exact source
commit, aarch64 digest, Cosign signature, SBOM and GitHub provenance attestations.
The displayed app version or repository description alone is never provenance.
Before starting, a technical maintainer must verify the Supervisor-resolved image
digest equals the approved receipt. Publishing, updating the dormant installation,
starting and commissioning are separate protected actions.

This private app hosts a local CUPS daemon and the bounded Documents adapter on Home Assistant Green. It is source-only and uncommissioned until the separate physical acceptance journey succeeds.

## Security and configuration

Keep every endpoint on the private farm network; publish no ports or tunnels. Install the private CA at fixed `/config/private-ca.crt`. The canonical claim and protected-command paths are source-fixed. Commission `canonical_endpoint_ip` from the private DNS answer set: HTTPS connects only to that address while TLS verifies the configured hostname. The IPPS URI must use a private IP literal whose certificate contains that IP identity, avoiding later CUPS DNS resolution. Enter values only in the Home Assistant app options UI.

The configured queue and printer URI are commissioning registry values, never request fields. The app accepts only the fixed pilot document/options. The credential has only atomic-claim, fenced reconcile/transition, protected-command and digest-bound-PDF permissions. No plain claimable-job GET exists. Lease token, version, digest and authorization receipt bind every transition; stable event IDs make replay idempotent. Continue/Cancel additionally bind and atomically consume one fresh command receipt, clear the command fields, and return the prior canonical result on replay without a provider action.

## Runtime, recovery and health

Supervisor starts the app automatically and restarts it after failure. `/data/green-print-ledger.sqlite3` is crash-recovery state only; Supabase/Documents remains canonical. PDFs exist only under the tmpfs spool and are deleted after each attempt. `/data/health.json` reports worker identity, heartbeat, last/next poll and the last bounded result without secrets or document content. A cold backup stops the app before copying `/data`; temporary spool is excluded.

On restart, persisted attempts renew a live lease or recover an expired nonterminal lease before CUPS observation or intake, preserving attempt and provider identity. Corrupt/partial local state fails closed. Missing provider identity becomes canonically ambiguous. Free-space thresholds run before claim/download. Protected fresh Continue retains the job and moves canonically to the sole retry state. Cancel requests cancellation only for the exact known queue job, performs bounded exact readback, and closes only on confirmed absence; pending, completed, unavailable or contradictory evidence becomes canonical ambiguous/Hold and remains in recovery. Local recovery is deleted only after durable canonical closure acknowledgement. Provider completion is not physical completion. Health separates liveness from business Hold.

The root entrypoint only prepares owned directories, validates/writes the commissioned queue file and launches processes. CUPS runs as `cupsd`; the Documents worker runs as `greenprint`. The long-lived worker cannot administer queues or write CUPS configuration.

## Install and commissioning

1. Review the exact commit and build the aarch64 artifact from its pinned Dockerfile or add this private repository for a local Supervisor build. `build.yaml` remains only as a backward-compatible Supervisor hint; current builds take their base image and labels from `Dockerfile`.
2. Add the repository in the Home Assistant app store; install but do not start until the canonical endpoint, least-privilege token, registry identities, printer URI and private CA are commissioned.
3. Validate options and start the app. Confirm health is `event_waiting`, the local queue exists, logs contain no option values, and no job is eligible.
4. Follow `docs/06-operations/GREEN_PRINT_BRIDGE_PHYSICAL_COMMISSIONING_GUIDE.md`. The development terminal must never manufacture the genuine request or operate the printer.

## Restore, rollback and uninstall

Restore only a cold backup paired with current canonical Supabase truth. Before enabling the restored worker, reconcile every non-terminal local job against canonical job state and CUPS; never submit from backup state alone.

Rollback by stopping the app, revoking its canonical credential, and retaining the prior manual print path. Preserve `/data` evidence until canonical reconciliation is complete. Uninstall only after the credential is revoked, every known CUPS job and canonical job is reconciled, and required audit metadata is exported through the protected process. Supervisor removal deletes local recovery state; it does not cancel a provider job or change canonical truth.
