# HERDMASTER exposure-to-cycle transition handover — 2026-08-12

## Status

Prepared only. No production deployment or farm write is part of this source handover. Business completion remains bound to a genuine removal journey for the current exposure group.

## Authoritative distinction

- An exposure start records physical placement with a boar.
- An exposure removal records the attributable actual removal date.
- A completed exposure creates one open canonical breeding cycle whose possible service interval is the exposure start through removal date.
- The interval does not assert an exact service, conception, fertility, or pregnancy fact.
- The expected farrowing interval is calculated by adding 114 days to both ends of the supported service interval.
- A later attributable exact service or clinical/owner observation remains a distinct fact.

The existing `pig_breeding_exposure_events` and `mating_events` stores remain authoritative. No parallel exposure, mating, or observation ledger is introduced.

## Current runtime-loaded evidence (read-only cutoff 2026-08-12)

Group `HERD-EXPOSURE-GROUP-9C64CC59960730C2819CF78854A72891` contains five canonical starts dated 2026-08-12 and no removals:

- Sophie with Bola
- Olive with Tyson
- Shupe with Tyson
- Lucy with Tyson
- Lolly with Prince

The planned removal date is 2026-08-28. The five starts must not be recreated. Ms Piggy remains under an attributable body-condition recovery hold (score 2). Linda remains near farrowing with historical mating date and father Unknown.

## Owner-visible sample before deployment

> Sophie was physically removed from Bola on 28 August. Possible service window: 12–28 August. Expected farrowing window: 4–20 December. Exact service and conception dates remain Unknown. This preview creates no mating observation, pregnancy, or movement record until protected confirmation.

The same protected grouped action is consumed by the Breeding Attention application and by authenticated Oom Sakkie text. Voice transcription enters that same text contract; it has no separate writer.

## Transaction and replay contract

One confirmed grouped removal operation:

1. locks and revalidates every matching canonical start;
2. inserts every removal and its exposure-linked cycle in one database transaction;
3. records `mating_date` and `expected_farrowing_date` as `NULL`;
4. preserves the service and farrowing windows with `exposure_window_estimate` provenance;
5. fails the whole group on a missing, conflicting, duplicated, or partially transitioned row;
6. uses the canonical exposure identity as a unique cycle source;
7. makes exact replay a zero-row no-op;
8. creates no movement, pregnancy, medical, recovery-clearance, or availability effect.

## Later serialized integration and real-world proof

After the serialized lane is explicitly free: reconcile the exact reviewed source head with current main, run exact-head and exact-merge CI, deploy the exact merge lineage, and verify health. On the genuine removal date, recover the canonical active group through the existing authenticated boundary, present one five-row protected preview, and wait for exact owner confirmation. Execute once only after confirmation.

Business proof must show five removals and five exposure-linked open cycles, the 2026-08-12 through actual-removal service windows, the corresponding 114-day farrowing windows in Breeding Attention, no exact service/conception/pregnancy claims, no duplicate starts or cycles, zero unrelated farm writes, and a zero-effect replay. If the actual removals differ by sow or date, rebuild the preview from that fresh attributable evidence instead of applying the planned date.

## Evidence classes

- Documented: the governance standard, breeding-exposure recovery plan, unified capture plan, and channel-invariant canonical-action doctrine.
- Runtime-loaded: the five current canonical starts, absence of removals/cycles at the cutoff, Ms Piggy's recovery hold, and Linda's near-farrowing Unknowns.
- Provider-verified: none for removal yet. A future authenticated owner report and exact confirmation must be retained separately and bound to the preview hash.
