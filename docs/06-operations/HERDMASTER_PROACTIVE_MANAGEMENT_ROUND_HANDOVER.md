# HERDMASTER proactive management round handover

Status: Prepared (20%), source-only

`modules/pig_weights/herdmaster_management_round.py` converts the existing read-only canonical HERDMASTER worklist, attributable owner observations and active specialist-owned cases into one deterministic maximum-three internal Oom Sakkie publication packet.

It does not send Telegram, message Charl directly, persist a notification, write farm data, create a mating or change lifecycle/availability. The packet targets `oom_sakkie_internal_owner_attention`, has a deterministic publication ID and deduplication key, and rebuilds only when bound canonical or specialist-case evidence changes.

## Current management-round behavior

- Active welfare cases outrank routine herd work, but their already-issued Oom Sakkie questions are suppressed.
- Attributable `Assumed Pregnant` observations remain explicitly separate from clinically confirmed pregnancy.
- The farm's governed operating sequence is post-mating monitoring, then attributable visual `Assumed Pregnant` when supported. Visual signs such as belly development/drop and teat or milk-line development are sufficient for proportional farrowing preparation and monitoring; routine clinical scanning is not required.
- Clinical confirmation remains a separate optional higher-confidence fact and is never implied by `Assumed Pregnant`.
- `Assumed Pregnant` requires non-empty attributable visual signs and an exact match between the observation's mating identity/date and the canonical task's current mating identity/date; mismatches and future chronology fail closed.
- The governed current-cycle boundary is 125 days after mating. Older evidence cannot drive current farrowing preparation and is reduced to an unresolved reproductive-status review requesting only current farrowing/heat/status evidence.
- For assumed-pregnant cycles the contract exposes mating identity/date, a 114-day planning projection with a +/-2-day uncertainty range, monitoring phase, a preparation window beginning 14 days before the earliest projected date and completing seven days before it, one next visual observation, change triggers and still-prohibited actions.
- Near-term assumed-pregnant cycles may outrank inconclusive or no-result cycles, without creating pregnancy facts or protected pen/movement actions.
- Completed tasks, lower-ranked work and contained data-quality cases are suppressed.
- Zigay can remain explicitly contained without altering litter history.

## Later shared integration

After a serialized integration window, the existing scheduled HERDMASTER worklist producer should call `build_management_round` and append the returned packet to Oom Sakkie's existing internal owner-attention/task store using `publication_id`/`deduplication_key`. The existing Oom Sakkie coordinator, not HERDMASTER, owns any later owner delivery. Registration must preserve exactly one Telegram trigger and must not introduce a specialist router or direct bot send.

Operational proof requires one scheduled canonical round to create one internal Oom Sakkie item, exact replay to create zero additional items, no direct Telegram send from HERDMASTER, and zero farm/protected writes. Oom Sakkie must suppress a Pig 11 duplicate while its active lifecycle remains waiting for input.
