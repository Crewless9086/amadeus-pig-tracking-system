# ROOTLINE C12345 Canary Preflight

Status: prepared, command-inert, not authorized.

Packet: `ROOTLINE-CANARY-C12345-CH2-G1`

Zone: `C12345` / C - Kamp / vegetables / drip irrigation

Logical events: `irrigation_1_ch2_on` and `irrigation_1_ch2_off`

Maximum pulse: 30 seconds; one ON attempt; zero retries.

## Non-negotiable shutdown contract

After any ON invocation, issue the independently prepared OFF request even when
the ON response fails, times out or is Unavailable. The sole exception is that
manual isolation has already established and physically verified a safe closed
state. Request acceptance, valve movement and water flow are separate facts.

No automated timer, retry, schedule, workflow, queue, transport adapter or
hardware authority exists. A human stopwatch, prepared independent OFF control
and accessible manual isolation enforce the bound.

## Printable owner checklist

Do not start unless every pre-start box is checked during daylight.

- [ ] Owner is at the channel-2 valve/manifold and can see nearby drippers.
- [ ] Controller/channel label and physical C12345 vegetable line agree.
- [ ] Manual isolation is identified, accessible and physically operable.
- [ ] No other irrigation zone or controller operation is active.
- [ ] No fertilizer injection or exposed people, animals, equipment or work.
- [ ] Current local weather is fresh and acceptable.
- [ ] Stopwatch is ready.
- [ ] OFF event is independently prepared before ON.
- [ ] OFF can be issued without depending on the ON response.
- [ ] One ON attempt only; hard stop at 30 seconds; zero retries.
- [ ] Any identity or behavior mismatch means OFF plus manual isolation.

Observation:

- [ ] ON request response recorded: accepted / failed / timeout / Unavailable.
- [ ] Physical valve response recorded: opened / did not open / unclear.
- [ ] Flow recorded: observed / not observed / unexpected / unclear.
- [ ] OFF issued after ON regardless of ON response, unless verified manual safe.
- [ ] OFF response recorded separately.
- [ ] Physical valve closure recorded separately.
- [ ] New supply flow stop at manifold recorded separately.
- [ ] Residual downstream drainage and decay time recorded separately.
- [ ] Full-pressure flow or unclear closure caused immediate manual isolation.
- [ ] Final physical state recorded as verified safe or Unavailable.

Required authorization:

> I authorize one supervised C12345 channel-2 physical canary during daylight
> under packet ROOTLINE-CANARY-C12345-CH2-G1, with myself present, manual
> isolation ready, OFF prepared before ON, one ON attempt only, zero retries,
> and a hard maximum pulse of 30 seconds.

## Append-only evidence payload

Each observation is appended as a new immutable entry; later evidence must not
rewrite an earlier uncertain or failed observation.

```json
{
  "packet_id": "ROOTLINE-CANARY-C12345-CH2-G1",
  "zone_id": "C12345",
  "generation": 1,
  "simulated": false,
  "authority": {
    "automatic_retry": false,
    "schedule": false,
    "workflow": false,
    "command_queue": false,
    "autonomous_continuation": false
  },
  "evidence": [
    {
      "evidence_id": "ROOTLINE-CANARY-C12345-CH2-G1-E01",
      "sequence": 1,
      "recorded_at": "Unavailable until test",
      "recorded_by": "Unavailable until test",
      "evidence_type": "on_request",
      "status": "Unavailable",
      "details": {"event": "irrigation_1_ch2_on", "attempt": 1}
    }
  ]
}
```

Allowed `evidence_type` values are `preflight`, `on_request`,
`physical_valve_opening`, `observed_water_flow`, `operator_abort`,
`off_request`, `physical_valve_closure`, `new_supply_flow_stopped`,
`residual_downstream_drainage`, `manual_isolation` and
`final_physical_state`.

Final safe state requires both observed physical closure and observed cessation
of new supply flow. Otherwise it remains `unavailable`.

## Post-canary reconciliation

- Packet, zone, generation, observer, local start/stop times:
- Preflight/weather evidence and freshness:
- ON request acceptance:
- Physical opening:
- Water-flow onset and observation point:
- OFF request acceptance:
- Physical closure:
- New supply flow stopped:
- Residual drainage behavior:
- Seconds until drippers ceased or materially decayed:
- Manual isolation used and why:
- Identity or behavior deviation:
- Final physical state: verified safe / Unavailable:
- Retry count: must be zero:
- Network requests: exactly one ON and required OFF, or no ON:
- Hardware authority created by ROOTLINE: no:
- Owner follow-up decision required:

## Offline rehearsal results

The pure rehearsal covers normal ON/flow/OFF, accepted ON without movement,
uncertain ON timeout, unexpected flow, OFF timeout, unclear physical closure,
verified manual isolation and operator abort. Every scenario has zero retries
and no network, credentials, persistence, schedule, workflow, queue or hardware
interface. Every uncertain shutdown ends `unavailable`.

## Historical duplicate-event impact audit

The two preserved `PLAN_CREATED` rows describe the same operational event at
`2026-05-22T22:06:14.597Z`, with original source rows 78 and 2.

- Current dashboard plan totals come from `irrigation_daily_plans` and
  `irrigation_plan_items`, not from summing `irrigation_events`.
- Current irrigation state comes from the latest
  `irrigation_state_snapshots` row.
- Recent-event presentation deduplicates equal timestamp, zone, type, reason,
  planned/actual minutes and actor values.
- Daily telemetry rollup construction and verification use the same
  operational-field deduplication. The duplicate therefore contributes one
  operational event, not two, to the affected historical rollup.
- The rows are historical and do not enter today's date-bounded dashboard or
  planning inputs.

Impact: no current dashboard plan total or current planning input is affected.
Raw database row counts still correctly show 78 provenance rows; any generic
raw-row counter that omits operational deduplication could over-count the
historical day.

Proposed remediation only: retain both immutable provenance rows, expose a
canonical operational fingerprint/read model for consumers, and require future
dashboard, rollup and planning code to use it rather than raw row count. Do not
update or delete either production row.
