# Changelog

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
