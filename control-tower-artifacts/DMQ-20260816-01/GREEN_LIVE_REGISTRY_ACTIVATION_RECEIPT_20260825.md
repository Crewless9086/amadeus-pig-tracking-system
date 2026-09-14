# GREEN live registry activation receipt

Mission: `DMQ-20260816-01`  
Live source revision: `76a8dac7640bc431522b0198b4c059947441a1d3`

The genuine owner request was Telegram message `4031`, update `549158359`,
received through n8n executions `66641` and `66642`. The backend returned 503
with `documents_green_preview_contained` / `RaiseException`, delivered hold
message `4032`, and atomically rolled back the standing receipt. Canonical
readback proved zero claims, jobs and events. This was not a PR #1256
authorization-lookup failure: ingress authentication succeeded.

The exact cause was the sole matching canonical device registry row remaining
`active=false`, `commissioned_at=NULL` after real GREEN 0.3.8 commissioning.
Bounded transaction `332093` compare-and-set that existing row only:

- farm: `farm-amadeus`
- GREEN: `green-amadeus-ha-01`
- printer: `printer-amadeus-kantoor-hp8120-01`
- queue: `weekly-a4`
- registry version: `green-0.3.2-20260822`
- canonical origin: Render HTTPS origin already stored in the row
- active: `true`
- commissioned at: `2026-08-25T07:56:14.650507Z`
- evidence SHA-256: `175460ec3d3f710c49299c33fbbd0af0d6f12635c236fc847511a28f7658f6eb`

The evidence digest binds the merged GREEN 0.3.8 device commissioning receipt.
Precondition and post-readback remained zero print claims, zero jobs and zero
events. No Telegram replay/send, document generation, GREEN claim, PDF fetch,
CUPS attempt, provider call, printer call, page or physical follow-up occurred.

The failed request is not reinterpreted as acceptance and must not be replayed.
A later genuine request may enter the now-active existing rail exactly once.

