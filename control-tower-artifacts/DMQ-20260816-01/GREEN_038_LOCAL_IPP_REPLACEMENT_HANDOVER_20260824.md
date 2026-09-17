# GREEN 0.3.8 local IPP replacement handover

Mission lineage: `DMQ-20260816-01` / existing GREEN print commissioning.

Lifecycle: `WORKING / SOURCE_REPAIR / AUTHORITY_AND_RELEASE_HOLD`.

## Intake and consolidation

The owner accepted the farm-house confidentiality and local-network risk of a
fixed unencrypted IPP hop. This bounded source repair supersedes PR #1194's
private-IPPS/private-CA transport design; it does not create another printer
mission, queue, ledger, or delivery system. PR #1194 must remain preserved until
this replacement is independently accepted, then be closed as superseded.

The durable provider-readback authority update is PR #1249. At source intake it
remains open and has a failing `charlie-core` gate. Therefore this replacement
must not be merged, released, installed, commissioned, or used to create a job
until that authority is independently reviewed and integrated.

## Bounded design

- Canonical API transport remains HTTPS with the existing exact-origin and
  private-pin/public-PKI controls.
- Printer transport accepts only `local_ipp_fixed`.
- The configured URI must be an IP literal equal to the commissioned
  `printer_endpoint_ip`, use `ipp`, port 631, and the exact
  `/printers/<cups_queue_id>` path. Hostnames, credentials, query strings,
  fragments, alternate ports, public IPs, and queue drift fail closed.
- Existing immutable job/document/PDF/authorization identities, lease and
  replay controls, bounded retry, CUPS receipt validation, and truthful
  `printed`/`failed` transitions remain authoritative.
- This source branch creates no print job and performs no provider, printer,
  database, or farm mutation.

## Verification and release boundary

Focused source suite: `tests/test_green_print_home_assistant_app.py`.

Commissioning sequence after authority, review, merge, image publication, and
exact installed-version proof: first prove a zero-job idle cycle against the
fixed queue. Only then may the existing governed immutable-job journey create a
single authorized print attempt. A source build or idle queue is not a printed
owner outcome.

OWNER ACTION: NONE. Control Tower retains the release hold automatically.
