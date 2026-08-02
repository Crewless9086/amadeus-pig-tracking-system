# ROOTLINE Operating Knowledge Register

## Owner-approved Water & Energy baseline — 2026-07-28

The authoritative Phase 1 contract is
[ROOTLINE Water & Energy Manager Phase 1](ROOTLINE_WATER_ENERGY_MANAGER_PHASE1.md).
It records the 40% absolute floor, provisional 50% working reserve, learned
63/67/70% reserve comparison, provisional approximately R9/kWh tariff, the
five-storage/twelve-reservoir topology, manual count observations, unresolved
SmartLife/transfer bindings and the SONOFF fertilizer controller contract.

These facts authorize advice and immutable evidence only. They do not authorize
a plan consumer, command, schedule, workflow, SmartLife/SONOFF/IFTTT/n8n call,
retry or hardware action.

Status: owner-approved initial governance baseline; command-inert.

This register supplies the owner-only Daily Advisor with reviewed facts and
explicit Unknowns. It is not a schedule, irrigation plan, command queue,
transport adapter, or hardware-control authorization.

## Known zones

| Zone | Owner name | Use | Supply | Pump | Priority | Physical proof |
|---|---|---|---|---|---|---|
| `B12345` | B - Kamp | Lucerne drip irrigation | Gravity-fed downhill | No | Equal | Logical mapping owner-confirmed; supervised physical canary not run |
| `C12345` | C - Kamp | Vegetable drip irrigation | Gravity-fed downhill | No | Equal | Channel 2 identity/open/flow/OFF/closure proven once under supervision |

When both zones are otherwise eligible and capacity conflicts, ROOTLINE must
request owner selection. It may not invent a priority.

## Approved initial operating policy

| Policy | Approved value |
|---|---|
| Eligibility | Manual-advisory only |
| Seasonal boundaries | **Unknown** |
| Runtime meaning | Planned valve-open minutes |
| Runtime evidence | Planned minutes, observed runtime, and measured delivery are separate |
| Operating period | Daylight only; exact windows **Unknown** |
| Minimum runtime | **Unknown** |
| Maximum runtime | **Unknown** |
| Repeat run | No repeat on the same operating day without fresh owner review |
| Simultaneous zones | Never; one zone at a time |
| Forecast-rain thresholds | **Unknown** |
| Live rain | Hold until rain stops, evidence refreshes, and owner reviews |
| Temperature | Informational until limits are approved |
| Wind | Informational for these drip zones unless a physical safety concern exists |
| Crop-need bands | **Unknown** |
| Successful watering | Credible opening, new physical flow, observed runtime, OFF/closure, and no unresolved failure |
| Measured volume | **Unavailable** |
| Carry-forward | At most one missed opportunity as explanation/priority signal; never accumulated minutes |
| Owner hold | No automatic expiry; explicit owner release required |
| Controller power-loss behavior | **Unknown** |

Unknown numeric policy must remain visible. When it is material to eligibility
or runtime, the Daily Advisor returns `Needs Data` or `Hold`, never an invented
`Irrigate`, `Do Not Irrigate`, eligibility conclusion, or runtime.

## Historical evidence boundary

Legacy Google Sheet plan rows and imported plan/event history remain
provisional historical evidence. They must not appear as additional current
schedules and do not prove watering.

- planned minutes describe intent;
- observed runtime requires runtime evidence;
- measured water requires a volume sensor or other authoritative measurement;
- an HTTP response does not prove valve movement;
- valve movement does not prove water flow;
- water flow does not prove delivered volume.

The successful C12345 identity pulse is not counted as verified crop watering.

## C12345 supervised identity-and-shutdown proof

- Packet:
  `ROOTLINE-CANARY-C12345-CH2-20260727-32B0D177-G1`
- Evidence SHA-256:
  `ef388830f14056bf7baea2915950a655ae77c8f7c058b8e1f9f1c92638d028ab`
- Logical events:
  `irrigation_1_ch2_on` / `irrigation_1_ch2_off`
- ON and OFF transport responses: HTTP 200 accepted.
- Physical opening: observed.
- New water flow: observed at the intended C12345 vegetable drippers.
- Physical closure: observed.
- New full-pressure supply flow stopped: observed.
- Residual drainage: diminishing.
- Time until drippers ceased or materially decayed: **Unavailable**.
- Manual isolation: not used.
- Retry count: zero.
- Final state: safe closed.

This is one supervised physical identity-and-shutdown proof. It does not prove
power-loss behavior, repeat reliability, measured volume, normal irrigation
runtime, B12345 actuation, routine transport readiness, or autonomous control.
It creates no standing permission to invoke ON/OFF again.

## Design-only append-only evidence contract

No migration or production evidence row is part of this candidate. A future
separately reviewed additive migration should use:

- immutable `packet_id` as the operational identity;
- canonical payload SHA-256 as evidence-content identity;
- a second canonical envelope SHA-256 binding the packet, evidence checksum,
  actor identity/basis, observation time, and duplicated transport/operator
  observations;
- separate transport acceptance, valve movement, water-flow, closure,
  residual-drainage, manual-isolation, and final-state fields;
- explicit availability beside nullable measurements such as drainage-decay
  seconds;
- exact replay returning the existing row without insertion;
- altered reuse of a packet identity rejected as an identity conflict;
- missing, extra, malformed, or provenance-mismatched fields rejected before
  an append candidate exists;
- append-only enforcement that blocks UPDATE, DELETE, and TRUNCATE;
- no direct PUBLIC, anon, or authenticated table/function access;
- protected owner-route reads only;
- no command, dispatch, schedule, retry, IFTTT, n8n, or hardware authority.

The first production evidence append, migration design/application, and any
hardware action each require separate authority.

## Remaining owner decisions

1. Summer and winter date boundaries.
2. Exact daylight operating window for each zone.
3. Minimum useful runtime for each zone.
4. Maximum safe continuous runtime for each zone.
5. Forecast-rain amount, probability, and time horizon.
6. Temperature limits, if any.
7. Seasonal crop-need bands.
8. Physical controller behavior after power loss.
9. Residual-drainage decay time for the completed C12345 proof, if known.
