# Changelog

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
