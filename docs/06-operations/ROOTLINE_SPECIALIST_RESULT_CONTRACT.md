# ROOTLINE Specialist Result Contract

## Purpose and boundary

`rootline_specialist_result_v1` is ROOTLINE's reusable, read-only answer to:
what should we do about water and power today, why, when will ROOTLINE
reassess, and what genuine family fact is still needed?

The source boundary is
`modules/telemetry/rootline_specialist_result.py`. It composes the canonical
Phase 1 Water & Energy Plan and returns an in-memory result. It has no route,
database append, migration, schedule, workflow, Telegram send, device client
or hardware transport. Every result states `command_authority=false` and
`hardware_control=false`.

## Contract

Each result contains:

- operating date, timezone, stable result identity, evidence cutoff,
  generation and generation time;
- overall `Recommend`, `Hold`, `Needs Data` or `Do Not Run` status;
- per-source freshness and provenance;
- current SOC, solar, load and grid observations when available;
- current local weather separately from forecast;
- forecast freshness, confidence and explicit uncertainty;
- governing battery reserve, 40% absolute discretionary floor, approximately
  50% provisional working reserve and the governing reason;
- owner water observations with actor, timestamp and age, or `Unavailable`;
- separate borehole, B12345, C12345, fertilizer injection, fertilizer mixing
  and solar-transfer-dependency recommendations;
- a supported reason, next reassessment, and at most one genuine owner question;
- explicit separation of advice, command acceptance, electrical observation,
  device movement, water flow and delivered volume.

An absent sensor blocks only the physical claim that needs it. ROOTLINE never
invents litres, tank level, flow, soil moisture, device state or delivery.

## Forecast-rain rule

Forecast rain is neither observed local rain nor captured tank water. A fresh
meaningful-rain forecast can delay non-urgent borehole advice for at most 120
minutes from its forecast run. The result schedules a mandatory read-only
reassessment using fresh local weather and any available owner tank
observation. If rain has not materialized when the bound expires, forecast-only
suppression is removed and supported water work is reconsidered.

## Water and energy rules preserved

Water continuity outranks strict grid avoidance. Grid may be recommended when
genuinely necessary, while avoidable grid use remains minimized. The
independent solar transfer pump runs when solar permits and is represented only
as a non-controllable dependency.

Simple owner observations (`LOW`, `OK`, `FULL`, or a fraction) retain actor,
time and freshness. They are optional and are never assumed daily.

## Future Oom Sakkie integration

After the serialized HERDMASTER/SAM/BEACON queue is released, add one
owner-authenticated read-only Oom Sakkie tool that calls
`build_current_rootline_specialist_result()`, returns `owner_brief` plus the
structured result, and performs no writes. The future integration owner must
update these shared files, which this branch intentionally leaves untouched:

- `modules/oom_sakkie/tools.py` — handler and read-only tool registry entry;
- `modules/oom_sakkie/specialists.py` — ROOTLINE output convention if required;
- Oom Sakkie router/prompt policy only if tool discovery tests prove it is
  required;
- corresponding Oom Sakkie service/tool tests and source-map reconciliation.

Smallest operational proof: Oom Sakkie receives one owner read-only question,
calls ROOTLINE once, and returns the current specialist result with zero
database, farm, workflow, Telegram or hardware writes.

## Review and known limitation

Independent product/operations and backend/security/authority reviews approved
the source contract on 2026-07-29 with no blocking findings. The ROOTLINE test
suite passed 113 tests with two environment-dependent PostgreSQL skips.

The inherited Phase 1 `database_url` test seam scopes power, weather, history
and tank reads but does not inject a database-scoped Daily Advisor reader.
Normal production composition uses one configured environment and remains
read-only. Until that inherited seam is refactored, callers must not claim that
an explicit `database_url` proves backend or point-in-time snapshot isolation.
