# Changelog

## 0.3.10

- Persist bounded PDF retrieval and digest-validation failures before any
  provider attempt, then recover only the same fenced canonical claim.
- Revalidate immutable job and device bindings before one later attempt, while
  preserving the existing ambiguity barrier against automatic reprints.

## 0.3.9

- Normalize an idle protected-command envelope so the worker continues to the
  ordinary authorized-job claim in the same poll cycle.
- Preserve the commissioned fixed queue, printer, registry and one-copy policy.

## 0.3.8

- Adds the owner-authorized `local_ipp_fixed` printer transport for one exact
  private IP literal, port 631, `/printers/<registered queue>` path, and fixed
  CUPS queue. It does not enable DNS targets, credentials, query parameters,
  arbitrary ports/paths, host networking, or general print submission.
- Preserves canonical HTTPS, immutable job/document/PDF and authorization
  bindings, leases, deterministic transitions, bounded recovery, replay
  protection, and truthful provider completion/failure states.

## 0.3.6

- Read the verified private CA from Home Assistant's distinct read-only `homeassistant_config` mount at `/homeassistant/private-ca.crt` while leaving the add-on private config and Supervisor options contract unchanged.
- Restrict AppArmor to that exact certificate path; no other Home Assistant configuration file is readable.

## 0.3.5

- Preserves Supervisor ownership of the `/data` mount and creates one bounded
  Green-owned runtime subdirectory instead of changing the mount root.
- Copies the Supervisor-populated root-readable options into a mode-0600
  Green-owned runtime file before privilege drop.
- Adds fixed non-secret stage/reason failure evidence from S6 command entry
  through mount validation, bootstrap, queue readiness and service exec.

## 0.3.4

- Connects the initial printer TLS check directly to the commissioned private
  endpoint pin while retaining the configured hostname as the certificate SAN
  identity, removing the circular dependency on ambient printer DNS.
- Establishes and verifies the fixed local hostname binding only after trusted
  TLS identity succeeds, and fails closed on conflicts or write/readback errors.
- Emits bounded startup stage/reason diagnostics without configuration values,
  credentials or certificate contents.

## 0.3.3

- Repairs Home Assistant startup under the custom AppArmor profile by allowing
  the pinned base image's inherited S6 entrypoint and bounded runtime paths.
- Uses Alpine's actual `/sbin/su-exec` location and shell-only entry scripts,
  removing the invalid `/usr/bin/su-exec` and unnecessary Bashio interpreter
  assumptions.
- Makes the public-PKI canonical endpoint pin blank by default and normalizes
  that blank to no runtime pin, while `private_pinned` still requires and
  verifies an exact private address.

## 0.3.2

- Adds an explicit `public_pki_exact_origin` canonical transport for the exact approved Render HTTPS origin. It uses the system public trust store and hostname verification, follows no redirects, accepts no endpoint IP pin, and cannot change origin, port, or base path.
- Retains the existing `private_pinned` canonical transport with private DNS-set validation, commissioned IP binding, and the private CA.
- Adds an explicit `private_ipps` printer transport. IP-literal SAN identities remain supported; hostname SAN identities require a single complete private DNS answer exactly matching the commissioned endpoint pin, then bind that hostname to the pin inside the container. CUPS requires encryption, validates the certificate name against its protected site CA, and disables arbitrary roots, expired certificates, and trust-on-first-use.
- Keeps the app outbound-only with no published listener and retains bearer, farm, Green, printer, queue, and registry bindings.

## 0.3.1

- Quarantine the invalid partial 0.3.0 artifact without overwriting it.
- Export the unique replacement with an explicit `linux/arm64` platform.
- Verify raw OCI index descriptor and image config architecture before signing.
- Generate the SPDX SBOM with an explicit arm64 Syft scan.

## 0.3.0

- Prepare a uniquely versioned, signed prebuilt aarch64 GHCR image with exact source
  revision, immutable digest receipt, SBOM and build provenance attestations.
- Refuse publication when the version tag already exists; publication remains a
  separate explicitly triggered protected action.
- Keep the installed 0.2.0 app stopped until a separately authorized dormant update.

## 0.2.0

- Consume protected command receipts atomically, renew/recover nonterminal leases, and require exact post-cancel CUPS readback before durable cleanup.
- Add atomic canonical leases, fenced replay-safe transitions and protected Continue/Cancel.
- Pin canonical transport and require private IP-literal IPPS commissioning.
- Split bounded root initialization from non-root worker/CUPS identities.
- Add restore, corrupt-ledger, disk and business-Hold fail-safe behavior.

## 0.1.0

- Initial source-only private aarch64 packaging for the bounded weekly weighing-sheet pilot.
