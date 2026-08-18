# ROOTLINE Water & Energy Manager Phase 1

## Operational boundary

Phase 1 creates one immutable, versioned advisory Water & Energy Plan per
Africa/Johannesburg operating date. Material evidence appends a generation;
unchanged evidence returns the existing generation. It is separate from the
legacy irrigation plan, command ledger, schedules, n8n and hardware.

All plan rows are database-constrained to:

- no irrigation-plan or command creation;
- no schedule or workflow mutation;
- no SmartLife, SONOFF, IFTTT or n8n call;
- no retry or hardware control.

## Evidence and partial operation

The plan combines current Sunsynk power, weather, forecast, Daily Advisor zone
evidence, historical power rollups and the latest owner tank observation.
Each source keeps its own freshness. A stale forecast disables only
forecast-dependent optimization. Missing tank evidence prevents tank-volume
conclusions but does not erase current power or weather.

Manual tank evidence may use bounded counts and a separately stated
`LOW`, `OK`, `FULL` or `Unknown` observation:

`Storage 4/5; Reservoir 8/12; observed YYYY-MM-DD HH:MM SAST`

The append-only record stores reporter, source and timestamp. A count never
means FULL by itself. It never derives litres, water depth, pressure, flow or
delivered volume. Future-dated evidence and conflicting idempotency replay are
rejected.

The owner dashboard shows source freshness, reserve, rain/forecast effect,
tanks, grid exposure, task dependencies and evidence gaps and remains
strictly read-only. Separate protected owner-admin routes can append a current
advisory generation or tank observation; neither action creates a command.
The protected read-only Oom Sakkie summary is
`GET /api/telemetry/rootline/water-energy-summary`; no n8n workflow is enabled.

## Reserve policy

- 40% SOC: absolute discretionary floor.
- Approximately 30%: owner-reported inverter grid-support point.
- 50%: provisional normal working reserve.
- 63% sunny, 67% mixed and 70% poor/uncertain: learned candidate reserves from
  historical overnight depletion.

The governing advisory reserve is the higher evidence-supported boundary.
Grid use is permitted for proven critical water/farm continuity, while
avoidable grid cost is minimized. The owner-supplied approximately R9/kWh
tariff remains provisional.

## Water topology

- Five 5,500 L storage tanks receive borehole and roof rainwater.
- Twelve 5,500 L reservoir tanks receive storage water through a solar
  transfer pump; reservoir overflow returns to storage.
- The storage full controller can stop the borehole pump independently, so an
  energized upstream plug is not proof of electrical pumping or water flow.
- The borehole upstream plug is associated with SmartLife, but its exact
  protected identity is Unknown.
- The solar-transfer control identity is Unknown.

## Fertilizer evidence

SONOFF 4CHPRO R3 `100204d497`, named `Controller (1) Right`:

- channel 1 `Kunsmis In`: fertilizer injection;
- channel 2 `Kunsmis Meng`: fertilizer mixing;
- channels 3 and 4: unused.

Injection requires exact product/zone compatibility, a compatible active
irrigation zone, ten minutes observed pre-flow, at most 60 seconds, ten minutes
between pulses, no overlapping pulse, and a bounded clean-water flush. The
approximately fifteen-minute twice-daily mixing proposal remains a
candidate. Exact relay/API binding, deterministic OFF and supervised physical
identity remain unproven, so Phase 1 cannot actuate either channel.

## Outcome separation

The plan records these as independent concepts:

1. advice/plan;
2. command acceptance;
3. observed electrical operation;
4. observed physical water flow;
5. measured delivered volume.

Evidence at one level never proves the next.
