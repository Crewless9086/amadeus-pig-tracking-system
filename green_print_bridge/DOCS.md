# Amadeus Green Print Bridge

Version 0.3.6 uses the Home Assistant supported prebuilt image reference
`ghcr.io/crewless9086/amadeus-green-print-bridge`. Its tag may be published only
once through the guarded manual workflow. GHCR does not provide a registry-level
immutability guarantee for this private tag: the workflow refuses reuse, verifies
the tag-to-digest mapping twice, and every release and installation decision must
bind the immutable digest. The verified release packet binds the exact source
commit, linux/arm64 index descriptor and config, OCI labels, Cosign identity, SBOM digest, and GitHub build
and SBOM attestations.
The displayed app version or repository description alone is never provenance.
Before starting, a technical maintainer must verify the Supervisor-resolved image
digest equals the approved receipt. Publishing, updating the dormant installation,
starting and commissioning are separate protected actions.

This private app hosts a local CUPS daemon and the bounded Documents adapter on Home Assistant Green. It is source-only and uncommissioned until the separate physical acceptance journey succeeds.

## Security and configuration

Publish no inbound ports or tunnels. Choose exactly one canonical transport profile. `private_pinned` preserves the private-network design: install the private CA at fixed Home Assistant host path `/config/private-ca.crt`; the read-only `homeassistant_config` mount exposes only that exact file to the app as `/homeassistant/private-ca.crt`. Commission a non-empty `canonical_endpoint_ip` from the complete private DNS answer set; HTTPS connects only to that address while TLS verifies the configured hostname. For `public_pki_exact_origin`, leave `canonical_endpoint_ip` blank. Home Assistant saves that explicit blank and the worker normalizes it to no runtime pin. This public profile accepts only `https://amadeus-pig-tracking-system.onrender.com`, uses the system public trust store with hostname verification, follows no redirects, and forbids a non-empty endpoint pin, alternate port, path, credentials, query, or fragment. Canonical claim, command, transition, and PDF paths remain source-fixed; every request retains bearer, farm, and Green identity bindings.

The printer transport is always `private_ipps`; plain IPP and disabled TLS are unsupported. The protected private CA is installed as CUPS' site CA, while `AllowAnyRoot`, expired certificates, and trust-on-first-use are disabled and certificate-name validation plus encryption are required. Set `printer_endpoint_ip` to the commissioned private address. An IP-literal `printer_uri` requires that same address and a certificate with the IP SAN. For a hostname `printer_uri`, startup connects directly to the commissioned private IP while verifying that hostname as the certificate SAN; it does not trust or require ambient DNS. Only after that identity check succeeds is the hostname bound locally to the commissioned address for CUPS, and the binding is read back exactly. Conflicting, invalid, unwritable or mismatched bindings hold before CUPS starts. Enter values only in the Home Assistant app options UI.

The configured queue and printer URI are commissioning registry values, never request fields. The app accepts only the fixed pilot document/options. The credential has only atomic-claim, fenced reconcile/transition, protected-command and digest-bound-PDF permissions. No plain claimable-job GET exists. Lease token, version, digest and authorization receipt bind every transition; stable event IDs make replay idempotent. Continue/Cancel additionally bind and atomically consume one fresh command receipt, clear the command fields, and return the prior canonical result on replay without a provider action.

## Runtime, recovery and health

Supervisor starts the app automatically and restarts it after failure. The root-owned Supervisor options remain at `/data/options.json`; bootstrap copies them to a mode-0600 Green-owned file under `/data/green-runtime` without changing ownership of the mount root. `/data/green-runtime/green-print-ledger.sqlite3` is crash-recovery state only; Supabase/Documents remains canonical. PDFs exist only under the tmpfs spool and are deleted after each attempt. `/data/green-runtime/health.json` reports worker identity, heartbeat, last/next poll and the last bounded result without secrets or document content. A cold backup stops the app before copying `/data`; temporary spool is excluded.

On restart, persisted attempts renew a live lease or recover an expired nonterminal lease before CUPS observation or intake, preserving attempt and provider identity. Corrupt/partial local state fails closed. Missing provider identity becomes canonically ambiguous. Free-space thresholds run before claim/download. Protected fresh Continue retains the job and moves canonically to the sole retry state. Cancel requests cancellation only for the exact known queue job, performs bounded exact readback, and closes only on confirmed absence; pending, completed, unavailable or contradictory evidence becomes canonical ambiguous/Hold and remains in recovery. Local recovery is deleted only after durable canonical closure acknowledgement. Provider completion is not physical completion. Health separates liveness from business Hold.

The inherited Home Assistant S6 `/init` remains PID 1 and is explicitly allowed by the custom AppArmor profile. Its bounded command invokes shell-only Green entry scripts, which prepare owned directories, validate/write the commissioned queue file and launch processes through Alpine's packaged `/sbin/su-exec`. CUPS runs as `cupsd`; the Documents worker runs as `greenprint`. The long-lived worker cannot administer queues or write CUPS configuration.

The partial 0.3.0 publication is permanently quarantined. Index digest
`sha256:48d8d871740be4e315a1f108897da6617ce5c08cc5d20715398094140a8068f3`
labels runnable manifest
`sha256:4b738c69245a6b4721a7f4b58135acf3d2308f355b7c8c4008c4149763e11b32`
as `linux/amd64` while its image config and layers are arm64.
It must never be installed, attested further, overwritten, deleted, or reused.

If a unique-version publication creates its index but stops before signing or
attestation, do not rebuild, retag, delete or push the package again. The
partial-publication recovery lane requires the reviewed source commit, index
digest and sole arm64 manifest digest; rereads the stable tag and OCI labels
with bounded registry-consistency retries; refuses foreign, duplicate or
malformed signatures and attestations; and may complete only missing signature,
SBOM and attestation evidence for that exact existing artifact. Recovery is a
separately protected dispatch and never grants installation or print authority.

## Install and commissioning

1. Review the exact commit, approve one guarded publication, and verify the complete non-secret 0.3.6 release packet against the published immutable digest. There is no current local Supervisor-build fallback.
2. Add the private repository in the Home Assistant app store and install or update only when Supervisor resolves the exact approved digest. Do not start until the canonical endpoint, least-privilege token, registry identities, printer URI and private CA are commissioned.
3. Validate options and start the app. Confirm health is `event_waiting`, the local queue exists, logs contain no option values, and no job is eligible.
4. Follow `docs/06-operations/GREEN_PRINT_BRIDGE_PHYSICAL_COMMISSIONING_GUIDE.md`. The development terminal must never manufacture the genuine request or operate the printer.

## Restore, rollback and uninstall

Restore only a cold backup paired with current canonical Supabase truth. Before enabling the restored worker, reconcile every non-terminal local job against canonical job state and CUPS; never submit from backup state alone.

Rollback by stopping the app, revoking its canonical credential, and retaining the prior manual print path. Preserve `/data` evidence until canonical reconciliation is complete. Uninstall only after the credential is revoked, every known CUPS job and canonical job is reconciled, and required audit metadata is exported through the protected process. Supervisor removal deletes local recovery state; it does not cancel a provider job or change canonical truth.
