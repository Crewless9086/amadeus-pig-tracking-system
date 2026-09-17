# ROOTLINE Phase B Hardware And Control-Topology Inventory

Status: sanitized read-only evidence report
Audited: 2026-07-25
Repository baseline: `6123c1e54134ccde5b3cc14d607d12ccaecc020d`

This report supplies the Phase 2 inventory evidence required by the
authoritative
[`ROOTLINE Control Architecture`](../09-vault-brain/04-workflows/ROOTLINE_CONTROL_ARCHITECTURE.md).
It does not supersede that Level 1-3 roadmap or grant Level 2 authority.

## Authority Boundary

This report inventories evidence required before any valve-control canary. It
does not authorize or implement control.

- IFTTT webhooks called: no
- n8n workflows activated or edited: no
- valves, pumps, tanks, or boreholes controlled: no
- irrigation plans or schedules changed: no
- configuration, schemas, or production data changed: no
- secrets or full webhook URLs recorded: no

`Unavailable` means the inspected authoritative sources did not prove the
fact. It does not mean zero, absent, healthy, safe, or not required.

## Evidence And Precedence

1. Supabase production reads:
   `irrigation_zones`, plan/state/event tables, auxiliary-device tables, and
   sensor-state tables.
2. Legacy `Amadeus_Irrigation_Logs` Sheet tabs: `ZONES`, `RULES`, `STATE`,
   `DAILY_PLAN`, and `LOG`.
3. Live n8n read-only workflow metadata for workflow
   `f6oPLsaolGH4pMKC`.
4. Committed workflow export and README for
   `2.3.2 - Run Irrigation Controller`.
5. Current repository migrations and Rootline/telemetry doctrine.

The Sheet is the source of the imported zone rows but is not sufficient
hardware proof. Supabase is authoritative for the current imported inventory;
the live n8n API is authoritative for workflow activation state.

## Source Summary

- Supabase contains two active irrigation zones, 73 daily plans, 146 plan
  items, one state snapshot, and 78 events.
- Supabase contains zero irrigation auxiliary devices, zero auxiliary tasks,
  and zero irrigation sensor-state rows.
- The Sheet contains two matching zone rows, nine rules, one state row, 272
  plan rows, and 140 log rows.
- The live legacy controller is inactive. It has 17 nodes and was last updated
  at `2026-03-12T18:30:00.817Z`.
- Live node names, connections, and decision code match the committed export.
- Configured environment names include `N8N_API_KEY` and `N8N_BASE_URL`.
  No configured environment key name containing `IFTTT` or `IRRIGATION` was
  found.
- The legacy controller's two HTTP nodes reference an IFTTT trigger path and
  key path directly and do not reference protected n8n environment/variable
  names. No URL or key value is reproduced here.

## Hardware And Topology Inventory

### Zone `B12345`

| Fact | Evidence-backed value |
| --- | --- |
| Canonical zone ID | `B12345` |
| Owner-facing name | `B - Kamp` |
| Active | yes |
| Priority | `5` |
| Allowed operating window | start/end `Unavailable`; Sheet says `odd_days` |
| Summer runtime default | `120 minutes` |
| Winter runtime default | `60 minutes` |
| Soil/crop/camp evidence | Sheet soil `sand`; Sheet notes and Supabase location notes say `Lucern`; formal crop-context field is Unavailable |
| IFTTT ON event | `irrigation_1_ch1_on` |
| IFTTT OFF event | `irrigation_1_ch1_off` |
| Downstream integration | IFTTT webhook is proven; physical device/platform beyond IFTTT is Unavailable; Home Assistant entity is blank |
| Pump dependency | Unavailable |
| Tank dependency | Unavailable |
| Borehole dependency | Unavailable |
| Simultaneous-zone constraint | Physical constraint Unavailable; legacy workflow models one current zone |
| Maximum runtime | conflict: zone summer default and global max are `120 minutes`, while unused `safety_timeout_minutes` is `60`; safe maximum is Unavailable |
| Minimum cooldown | Sheet global rule `1 minute`; device-safe cooldown is Unavailable |
| Flow sensor | Unavailable; zero sensor rows |
| Pressure sensor | Unavailable; zero sensor rows |
| Valve-state confirmation | Unavailable |
| Manual isolation/override | Unavailable |
| Failure-safe state | Unavailable |
| Fertilizer/injection interlock | Unavailable; zero auxiliary devices/tasks and no controller check |
| Primary classification | `unsafe_for_control` |
| Contributing classifications | `inventory_partial`, `actuator_unproven` |

Unresolved evidence: allowed hours, physical valve/device identity, pump/tank/
borehole topology, exclusivity, safe timing limits, physical state/readback,
manual isolation, de-energized behavior, and fertilizer interlocks.

### Zone `C12345`

| Fact | Evidence-backed value |
| --- | --- |
| Canonical zone ID | `C12345` |
| Owner-facing name | `C - Kamp` |
| Active | yes |
| Priority | `3` |
| Allowed operating window | start/end `Unavailable`; Sheet says `even_days` |
| Summer runtime default | `120 minutes` |
| Winter runtime default | `60 minutes` |
| Soil/crop/camp evidence | Sheet soil `sand`; Sheet notes and Supabase location notes say `Beetroot`; formal crop-context field is Unavailable |
| IFTTT ON event | `irrigation_1_ch2_on` |
| IFTTT OFF event | `irrigation_1_ch2_off` |
| Downstream integration | IFTTT webhook is proven; physical device/platform beyond IFTTT is Unavailable; Home Assistant entity is blank |
| Pump dependency | Unavailable |
| Tank dependency | Unavailable |
| Borehole dependency | Unavailable |
| Simultaneous-zone constraint | Physical constraint Unavailable; legacy workflow models one current zone |
| Maximum runtime | conflict: zone summer default and global max are `120 minutes`, while unused `safety_timeout_minutes` is `60`; safe maximum is Unavailable |
| Minimum cooldown | Sheet global rule `1 minute`; device-safe cooldown is Unavailable |
| Flow sensor | Unavailable; zero sensor rows |
| Pressure sensor | Unavailable; zero sensor rows |
| Valve-state confirmation | Unavailable |
| Manual isolation/override | Unavailable |
| Failure-safe state | Unavailable |
| Fertilizer/injection interlock | Unavailable; zero auxiliary devices/tasks and no controller check |
| Primary classification | `unsafe_for_control` |
| Contributing classifications | `inventory_partial`, `actuator_unproven` |

Unresolved evidence is the same category set as `B12345`.

## Classification Result

Neither zone is `inventory_complete`. No identity conflict exists between the
Supabase and Sheet IDs/names/runtimes/priorities, but physical actuator
identity is unproven. Both zones are therefore unsafe for control.

## Missing Owner Decisions

Charl must explicitly confirm, per zone:

1. The physical valve/controller/channel mapped to the canonical ID and IFTTT
   event pair.
2. Whether the current zone name and camp/crop description are correct.
3. Allowed hours and days, including exceptions and seasonal changes.
4. The safe maximum continuous runtime and whether `60` or `120` minutes is
   authoritative.
5. Minimum OFF cooldown and minimum ON duration.
6. Whether only one zone may run, and whether pumps or supply capacity impose
   a stricter constraint.
7. Pump, tank, and borehole dependencies and operating windows.
8. Manual exclusion/override ownership and how it is recorded.
9. Physical isolation and emergency-stop location.
10. The safe de-energized state for every valve and pump.
11. Fertilizer/injection sequencing and hard interlocks.
12. The nominated first canary zone and physical observer.

## Missing Sensors And Evidence

- No flow readings or flow-sensor identity.
- No pressure readings or pressure-sensor identity.
- No electrical/limit-switch valve-state confirmation.
- No tank sensor rows.
- No pump run/health feedback.
- No borehole availability or protection evidence.
- No command acknowledgement separated from physical confirmation.
- No evidence that OFF succeeded after ON.
- No manual isolation diagram or photograph.
- No controller/device model, channel map, or vendor/platform proof beyond
  IFTTT.
- No measured maximum flow, pressure, or simultaneous-zone capacity.

## Legacy Controller Topology

The live and exported workflow agree on 17 nodes.

Decision/read path:

`Schedule -> STATE -> RULES -> weather Sheet -> ZONES -> today's DAILY_PLAN
-> Code: Decide action -> START/STOP branches`

Command path:

- START: IFTTT ON HTTP node.
- STOP: IFTTT OFF HTTP node.

Post-command bookkeeping:

- START updates `DAILY_PLAN` to running, updates `STATE` to running, then
  appends `ZONE_STARTED`.
- STOP updates `DAILY_PLAN` to done, updates `STATE` to idle, then appends
  `ZONE_COMPLETED`.

Direct Google Sheets dependencies:

- `STATE`
- `RULES`
- weather current row
- `ZONES`
- `DAILY_PLAN`
- `LOG`

## Legacy Controller Safety Audit

| Question | Finding |
| --- | --- |
| Active? | No; live n8n says `active=false` |
| Secret reference | IFTTT key path is embedded in HTTP URL expressions; no protected environment/variable reference |
| Command acceptance distinct from valve state? | No |
| Valve state distinct from water flow? | No |
| Retry behavior | No explicit retry configuration on command nodes |
| Idempotency/deduplication | Not present |
| Ambiguous HTTP outcome | No explicit state; timeout-after-actuation can leave physical and Sheet truth divergent |
| Emergency stop | Not present |
| Manual override/exclusion | Not present |
| Multiple zones | Logic models one current zone, but does not prove or enforce physical exclusivity outside this workflow |
| Weather gate | Rain/wind only; no freshness proof |
| Power gate | Not present |
| Pump/tank/borehole gate | Not present |
| Flow/pressure confirmation | Not present |
| Valve feedback | Not present |
| Fertilizer interlock | Not present |
| Safety timeout | Sheet rule exists but decision code does not use it |
| Cooldown | Sheet rule exists but decision code does not use it |
| Allowed window/days | Zone columns exist; decision code does not enforce them |
| Inactive-zone gate | Not enforced in decision code |
| Empty event-name protection | No explicit rejection before HTTP command |

## Why The Legacy Controller Must Remain Inactive

1. Physical valve identity and platform are unproven.
2. Command acceptance, physical valve state, and water flow are conflated.
3. Direct webhook expressions retain a hardware secret boundary in n8n.
4. No command ledger, idempotency key, or duplicate suppression exists.
5. No safe ambiguous-outcome state or reconciliation procedure exists.
6. No emergency-stop or proven manual isolation path exists.
7. No pump, tank, borehole, power, or fertilizer interlock exists.
8. No flow, pressure, or valve-state confirmation exists.
9. Allowed windows, odd/even days, cooldown, inactive state, and the safety
   timeout are not enforced by the decision code.
10. The `60`-minute safety timeout conflicts with the `120`-minute zone/global
    maximum and is not applied.
11. Sheet writes after HTTP calls can describe running/done without physical
    confirmation.
12. External/manual actuation can invalidate the single-zone Sheet model.

## Proposed Backend Command State Machine

This is a future design, not an implemented command path.
The authoritative control architecture governs the final state terminology
and graduation gates; this inventory proposal elaborates the evidence needed
without changing that roadmap.

1. `unavailable`: inventory or evidence missing.
2. `inventory_verified`: exact zone/device/channel mapping owner-confirmed.
3. `interlocks_verified`: fresh power, tank, pump, borehole, manual exclusion,
   time window, cooldown, and fertilizer gates pass.
4. `command_prepared`: immutable intended action, duration, reason, evidence
   hashes, idempotency key, expiry, and rollback plan.
5. `owner_approved`: exact prepared command approved for one generation.
6. `command_sent`: transport request issued once.
7. `command_accepted`: transport accepted; physical outcome still unknown.
8. `physical_confirmation_pending`: wait for independent valve/flow evidence.
9. `running_confirmed`: valve and expected flow/pressure confirmed.
10. `stop_prepared` / `stop_sent` / `stop_accepted`.
11. `stopped_confirmed`: valve closed and flow ceased.
12. `completed`: all evidence reconciled.

Exceptional terminal/holding states:

- `held`
- `expired`
- `rejected`
- `ambiguous_outcome`
- `physical_mismatch`
- `emergency_stop_required`
- `quarantined`

No retry may leave `ambiguous_outcome` automatically. A second command requires
physical reconciliation and a new owner-approved generation.

## Proposed Exact First Valve Canary

Candidate: `B12345` / `B - Kamp`, IFTTT channel-1 event pair.

Why this candidate: it is the first canonical imported zone and has a clear,
matching Supabase/Sheet/event identity. This is an administrative selection,
not evidence that it is safer than `C12345`.

The canary remains prohibited until the owner supplies every missing physical
fact and explicitly confirms `B12345` as the nominated valve.

Required bounded procedure:

1. Daylight, no irrigation demand, and no fertilizer/injection activity.
2. Owner-approved pulse duration after device/vendor limits are known; target
   at most 30 seconds, but do not use 30 seconds if the hardware requires a
   different minimum.
3. One physical observer at the valve/outlet with direct voice/phone contact.
4. A second operator at the proven physical kill switch/isolation.
5. Prove the OFF/isolated state before starting.
6. Prepare one immutable ON command and its paired OFF containment command.
7. Send ON once; never retry an ambiguous response.
8. Require independent valve and flow confirmation within the approved short
   window.
9. Send OFF once immediately after proof or at the hard canary deadline.
10. Require valve-closed and zero-flow confirmation.
11. Quarantine the zone on any identity mismatch, timeout, unexpected flow,
    failure to close, or unplanned pump/tank/borehole behavior.

## Required Kill Switch And Physical Observer

Software kill switch:

- global hardware execution default false;
- per-zone canary enable false by default;
- one-generation owner approval;
- command expiry;
- no automatic retry;
- emergency stop prepares OFF but does not claim success without confirmation.

Physical kill switch:

- owner-identified electrical isolation or upstream manual water isolation;
- accessible without entering a hazardous area;
- tested before the canary without actuating the irrigation valve;
- observer authorized and able to use it immediately.

The current repository and data do not prove that either physical mechanism
exists.

## Rollback And Containment

- Keep the legacy n8n controller inactive.
- Keep future transport disabled by default.
- On ambiguity: stop automatic commands, physically isolate supply, inspect
  valve/flow, record the discrepancy, and quarantine the exact zone.
- Do not mark a zone stopped because an HTTP request returned successfully.
- Preserve append-only command, acceptance, physical confirmation, and
  containment evidence.
- Revert any future software change separately; physical containment takes
  precedence over software rollback.

## Smallest Future Implementation Claim

After the owner completes and approves this inventory, the smallest safe
implementation is a plan-only command-state packet with no transport:

- `modules/telemetry/irrigation_command_service.py` (new)
- `modules/telemetry/telemetry_routes.py`
- `tests/test_irrigation_command_service.py` (new)
- one new migration for an append-only irrigation command/evidence ledger

That slice may validate inventory, interlocks, idempotency, expiry, approval
generation, and state transitions while keeping:

- IFTTT transport absent;
- hardware execution false;
- schedule mutation false;
- automatic retry false.

IFTTT transport and the first physical canary must be separate later claims
with fresh owner authority and physical readiness evidence.

## Delivery States

- Phase B inventory report built: yes
- Control code built: no
- Merged: no
- Deployed: no
- IFTTT configured in backend/n8n environment: no evidence
- Legacy controller configured in n8n: yes, but inactive
- Hardware-control operational: no
- Autonomous irrigation operational: no
- Valve canary authorized or run: no
- Alerts or Telegram actions: no
- Production writes: no
