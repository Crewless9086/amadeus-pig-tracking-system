# ROOTLINE Effective Rainfall And Water-Balance Plan

Status: owner-approved queued ROOTLINE capability. It follows the active daily-plan,
fertilizer-device and serialized production work; it is not authority to change current
irrigation history, discharge debt, actuate hardware or manufacture rainfall credit.

## Business outcome

ROOTLINE must manage crop water rather than mechanically repay calendar days. The existing
approximately four-days-per-zone weekly target remains a planning baseline, but observed
effective rainfall, verified irrigation, soil storage and subsequent crop response determine
whether B or C still needs water.

The family-facing result must distinguish:

- verified irrigation delivery;
- observed rainfall;
- effective rainfall credited to each zone;
- remaining water-equivalent obligation;
- schedule debt retained only where water need remains;
- confidence, Unknowns and the next reassessment.

Forecast rain may influence timing but never counts as delivered water.

## Current limitation

The current weekly ledger discharges an irrigation day only from a unique, shutdown-verified
outcome explicitly marked `objective_satisfied=true`. Observed rain can create Hold but does
not pay down the debt. Therefore the present debt means "verified irrigation outcomes not
completed," not "the crop lacks this exact quantity of water."

ROOTLINE must not silently convert historical rain into completed irrigation days. Introduce
an explicit activation/complete-through boundary and retain the old day-debt projection for
audit while the water-equivalent model is calibrated.

## Canonical model

Use two linked but distinct ledgers:

1. **Schedule obligation:** expected zone watering opportunities derived from the approved
   four-days-per-week baseline and agronomic programme.
2. **Zone water balance:** millimetres of supported water supply and estimated crop demand.

For each B/C zone and trusted interval, preserve:

- observed local rainfall in millimetres, station identity, observation time and coverage;
- forecast rain separately, with zero delivered-water credit;
- effective-rainfall method, coefficient/rule version, credited millimetres and confidence;
- verified irrigation runtime and, when available, measured flow/volume;
- estimated irrigation millimetres with its method and confidence when flow is unavailable;
- observed or estimated evapotranspiration/crop demand;
- soil type, infiltration/runoff assumptions, root-zone capacity and slope/drainage evidence;
- prior balance, new supply, estimated demand, cap/floor and resulting deficit/surplus;
- owner crop/soil correction, visible response and later sensor evidence;
- exact obligation effect: no credit, partial credit, satisfied, deferred or Needs Data;
- stable evidence digest and complete-through boundary.

Never convert a light shower, forecast, reservoir capture or weather-station value directly
into a completed zone outcome without the governed effective-rainfall calculation.

## Staged delivery

### Stage 1 - conservative rain credit

- Use fresh observed local rain only.
- Keep B and C separate even when they share the same weather station.
- Apply one owner-reviewed provisional rain-credit rule with confidence bands.
- Light/uncertain rain can pause a start without discharging an obligation.
- Material soaking rain can create partial or full zone credit when the evidence/rule supports
  it.
- Reassess after the rain/infiltration observation window instead of immediately scheduling
  catch-up irrigation.
- Show `Provisional` rather than presenting estimated rain credit as measured soil water.

### Stage 2 - irrigation equivalence

- Determine B and C irrigated area.
- Determine emitter nominal flow, emitter count/spacing and active-line layout, or obtain a
  measured zone flow rate.
- Convert a verified 60-minute segment to estimated/measured litres and millimetres:
  `millimetres = delivered_litres / irrigated_square_metres`.
- Preserve uncertainty and never infer continuous flow merely from ON/OFF receipts.

### Stage 3 - soil and crop calibration

- Record crop type, planting/use, soil texture, slope/drainage and effective root depth per
  zone.
- Use observed weather and an evidence-backed evapotranspiration method with an explicit
  version; forecasts remain planning evidence, not completed demand.
- Collect short owner field observations after representative rain and irrigation events.
- Compare crop/soil response with estimated balances and propose coefficient changes.

### Stage 4 - sensor improvement

- Add a local manual rain gauge or second trusted rain observation near B/C if the station is
  not representative.
- Add zone flow measurement to replace emitter-derived estimates.
- Add soil-moisture sensors at representative depths/locations when economical.
- Sensor absence must lower confidence, not erase supported rainfall or irrigation evidence.

### Stage 5 - governed learning

- ROOTLINE may analyse prediction error, owner corrections, sensor readings, crop response,
  runtime and weather to propose improved coefficients and thresholds.
- Learning produces a versioned recommendation and before/after replay against historical
  evidence.
- No learned rule silently changes production. Material policy versions require reviewed
  acceptance and preserve the prior version for rollback/audit.

## Owner information and field measurements

Confirmed owner evidence on 2026-08-09:

- B Camp remains lucerne;
- B Camp approximate irrigated dimensions: 80 m x 30 m, approximately 2,400 m2;
- C Camp contains mixed vegetables, including spinach and beetroot;
- C Camp approximate irrigated dimensions: 30 m x 10 m, approximately 300 m2;
- both camps have very sandy soil;
- drip irrigation normally infiltrates without visible pooling or surface runoff;
- the farm is intentionally rebuilding/improving this sandy soil;
- the farm weather station is very close to B and C and the owner regards it as the most
  accurate available local rainfall truth for both camps;
- confirmed common B/C irrigation layout: nominal emitter output 3.5 litres/hour,
  approximately 1 m between emitters and 0.5 m between rows;
- the nominal layout implies approximately 7 mm/hour (`3.5 / (1 x 0.5)`) before measured
  flow, pressure, blocked-emitter and edge-layout corrections;
- at that nominal rate, one verified 60-minute segment represents approximately 7 mm and
  two verified 60-minute segments approximately 14 mm;
- B's approximate nominal flow is 16,800 litres/hour across 2,400 m2; C's approximate
  nominal flow is 2,100 litres/hour across 300 m2. These are layout-derived estimates, not
  measured continuous-flow evidence.

Model implications:

- low observed surface runoff does not prove all water remains in the crop root zone;
  rapid drainage below the root zone remains possible in very sandy soil;
- B's established lucerne and C's mixed, generally shallower-rooted vegetables must retain
  separate crop-demand/root-zone assumptions;
- the same observed rainfall may produce different obligation credit in B and C;
- C's smaller area does not itself imply lower millimetres of crop demand; area changes the
  litres required to deliver each millimetre;
- no crop coefficient, root depth, field capacity or effective-rainfall percentage is yet
  proven by these owner observations.

Minimum initial facts from Charl:

- crop/use in B and C; **confirmed initially**;
- approximate irrigated area for each zone; **confirmed initially**;
- whether the current weather station is representative of both camps; **confirmed**;
- soil description for each zone (sand/loam/clay or known analysis), drainage/slope and any
  material difference between B and C; **confirmed initially as very sandy with no material
  surface runoff under drip irrigation**;
- irrigation layout evidence: dripper nominal litres/hour and emitter count/spacing, or a
  measured flow rate; **confirmed nominal layout for both zones; measured flow remains a
  later confidence improvement**;
- ordinary post-rain observation method Charl can provide initially, such as soil wetting
  depth, standing/runoff, and whether crop/soil still visibly needs water.

Useful later facts:

- effective root depth and crop stage;
- historical yield/crop response;
- calibrated rain gauge, flow meter and soil-moisture readings.

Charl should not have to report these every day. They are commissioning/calibration facts.
After activation, ROOTLINE owns automatic weather ingestion, balance updates, reassessment
and exceptions; Charl supplies only material corrections or genuinely unavailable physical
observations.

## Initial acceptance journeys

1. No rain: obligation remains and an otherwise eligible zone can run.
2. Forecast rain only: zero credit; timing may move proportionally.
3. Trace observed rain: Hold/reassess may occur, but no unsupported debt discharge.
4. Supported soaking rain: partial/full zone credit and no blind catch-up.
5. Conflicting/stale station evidence: zone-local Needs Data without changing old history.
6. Same rain, different B/C soil or crop: different credit is possible and explained.
7. Verified irrigation plus rain: cap credit at supported need; do not create fictitious
   surplus or double-count water.
8. Replay: zero additional credits, completions, messages, commands or rows.

## Notifications

- The daily plan states rain credit only when material to the decision.
- One material update explains that rain reduced, satisfied or did not satisfy an obligation.
- Unchanged balance reassessments remain silent.
- Technical water-balance detail is available on request, not sent every 15 minutes.

## Stop condition

Business-complete requires one genuine observed-rain event to create a defensible B/C
water-balance update, proportional obligation effect and clean Oom Sakkie explanation; the
subsequent scheduler decision must avoid unnecessary irrigation without hiding remaining
need, and replay must produce zero effects.
