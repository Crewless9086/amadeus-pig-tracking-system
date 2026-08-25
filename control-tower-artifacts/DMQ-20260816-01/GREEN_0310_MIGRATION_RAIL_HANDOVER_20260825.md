# DMQ-20260816-01 — GREEN 0.3.10 migration-rail handover

Status: `DURABLY LOGGED — NOT YET AN OUTCOME` in the reviewable commit carrying
this handover.

Governed Render run `32860700895` succeeded, but the closed allowlist ended
before existing migration `202608250001_fence_green_print_lease_device_binding`.
This is an existing-mission defect/addendum in `DMQ-20260816-01`; no new
mission, migration, queue, worker or print job is created.

The bounded repair appends the unchanged migration with LF SHA-256
`7607ddc4f7fb3c6cd77d638525854929545026af0e9160eb751633b29f51459b`.
It verifies exact predecessor/target function bodies, signatures, owner,
security-definer posture, search path, volatility and EXECUTE ACLs, inventories
the three functions in the existing catalog checkpoint, and proves apply,
replay, drift rejection and rollback in disposable PostgreSQL.

Existing job `GREEN-WWS-WWS-20260825.r1.a79d4a6effa6` remains the only job and
had no attempt ID, CUPS job, provider receipt or physical outcome at inspection.
This repair does not authorize/run a migration, recover a lease, replay the
request, submit to CUPS or print. After reviewed merge, the governed Render rail
must prove receipt and exact readback before that same job can be recovered
once against its freshly active device binding.

OWNER ACTION: NONE.
