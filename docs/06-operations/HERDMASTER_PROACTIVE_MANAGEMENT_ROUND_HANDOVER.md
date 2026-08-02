# HERDMASTER proactive management round handover

Status: Prepared (20%), source-only

`modules/pig_weights/herdmaster_management_round.py` converts the existing read-only canonical HERDMASTER worklist, attributable owner observations and active specialist-owned cases into one deterministic maximum-three internal Oom Sakkie publication packet.

It does not send Telegram, message Charl directly, persist a notification, write farm data, create a mating or change lifecycle/availability. The packet targets `oom_sakkie_internal_owner_attention`, has a deterministic publication ID and deduplication key, and rebuilds only when bound canonical or specialist-case evidence changes.

## Current management-round behavior

- Active welfare cases outrank routine herd work, but their already-issued Oom Sakkie questions are suppressed.
- Attributable `Assumed Pregnant` observations remain explicitly separate from clinically confirmed pregnancy.
- Near-term assumed-pregnant cycles may outrank inconclusive or no-result cycles, without creating pregnancy facts.
- Completed tasks, lower-ranked work and contained data-quality cases are suppressed.
- Zigay can remain explicitly contained without altering litter history.

## Later shared integration

After a serialized integration window, the existing scheduled HERDMASTER worklist producer should call `build_management_round` and append the returned packet to Oom Sakkie's existing internal owner-attention/task store using `publication_id`/`deduplication_key`. The existing Oom Sakkie coordinator, not HERDMASTER, owns any later owner delivery. Registration must preserve exactly one Telegram trigger and must not introduce a specialist router or direct bot send.

Operational proof requires one scheduled canonical round to create one internal Oom Sakkie item, exact replay to create zero additional items, no direct Telegram send from HERDMASTER, and zero farm/protected writes. Oom Sakkie must suppress a Pig 11 duplicate while its active lifecycle remains waiting for input.
