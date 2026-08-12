# ROOTLINE Agentic Device Management Plan

Status: owner-approved follow-on direction; do not interrupt the active eWeLink readback and tonight-irrigation mission.

## Outcome

ROOTLINE must manage farm water infrastructure through one scalable, device-class-aware operating loop. B/C irrigation is the first operational proof, not a special-case planner that becomes harder to extend. Future borehole controls, valves, breakers, fertilizer equipment and sensors plug into typed device contracts with only relevant planning inputs.

## Delivery order

1. Complete the current eWeLink schema normalization, authoritative readback, fresh plan and eligible tonight irrigation outcome.
2. Correct B/C planning so gravity-fed valves are independent of SOC, solar, load, grid and dynamic reserve. Preserve weekly debt, weather, water availability, season, history and owner corrections.
3. Repair weekly-obligation continuity: missing visual need must not erase verified debt, and stale or incomplete completion coverage must create a bounded history exception rather than a false `Hold`.
4. Implement one typed device registry/contract boundary using the authoritative classifications in `ROOTLINE_WATER_ENERGY_RULES.md`. Do not create separate planners per device.
5. Make the planner compose only relevant evidence per device class and expose which evidence influenced each decision.
6. Implement manager-quality notifications: one daily plan, silent unchanged reassessment, one pending question once, and concise Start, Completed/Stopped, Failed or Intervention messages. Technical detail is on demand.
7. Prove B and C independently across weekly debt, dry/rain conditions, adequate/low water, stale power, low SOC and high SOC. B/C outcomes must be identical when only power evidence changes.
8. Add future devices one at a time through the same contract, commissioning and operational-proof path: borehole, fertilizer injection, fertilizer mixing, then additional valves/breakers/sensors as their physical bindings become available.
9. Replace calendar-only recovery with the governed effective-rainfall and zone water-balance
   capability in `ROOTLINE_EFFECTIVE_RAINFALL_WATER_BALANCE_PLAN.md`. Preserve the existing
   debt ledger for audit while observed rainfall earns explicit partial/full credit only
   through a versioned evidence-backed model.

The fertilizer expansion uses `Controller (1) Right` / SONOFF 4CH Pro R3 device
`100204d497`, with channel 1 typed as `fertilizer_injection_valve` and channel 2 typed
as `fertilizer_mixer`. It must use `irrigation_auxiliary_devices` and
`irrigation_auxiliary_tasks`; neither channel may be inserted into or ranked as an
irrigation zone. The owner-confirmed physical behavior, provisional 120-second/two-pulse
injection envelope, ten-minute pre-flow/flush, five-minute pre-segment mixing and split
30-minute daily mixing limit are recorded in `ROOTLINE_WATER_ENERGY_RULES.md`.

## B/C acceptance

- Four-day-per-zone weekly obligations are maintained from verified outcome history.
- A routine plan does not require Charl to report visible need.
- Fresh observed rain, adequate/insufficient reservoir water, recent completion, weekly debt, season and crop evidence influence the plan proportionally.
- SOC, solar, load, grid and forecast-derived reserve cannot change B/C need, rank, window or eligibility.
- Only controller/readback safety evidence can block B/C actuation after the water plan supports it.
- Each segment remains at most 60 minutes; segment two requires verified shutdown and a fresh water decision.
- No simultaneous B/C operation until separately proven.
- Unchanged reassessments produce zero Telegram sends or edits.
- One genuine eligible run starts, stops, verifies shutdown, updates history once and produces concise owner-visible lifecycle messages.

## Expansion acceptance

A new device is operational only when its typed contract, physical mapping, readback, safe state, dependencies, commissioning, standing authority, outcome verification and notification behavior are proven. Missing evidence remains local to that device. ROOTLINE must continue supported work for other devices.
