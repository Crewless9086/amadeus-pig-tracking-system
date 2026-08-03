# ROOTLINE adaptive B/C irrigation management

Status: source-only decision and learning contract. It creates no command,
schedule, workflow, Telegram send, provider call, or hardware action.

## Business outcome

ROOTLINE manages B12345 and C12345 as independent water priorities. The farm
guidance is approximately four sufficient drip-irrigation days per camp per
week, not a rigid alternating timetable. Historical two-hour runs are useful
outcome evidence, not a mandatory duration. A current recommendation combines
recent verified irrigation, visible crop/soil need when available, observed
local weather and rain, separately labelled forecast evidence, current water
availability, season, and power/reserve evidence.

The pure component is
`modules/telemetry/rootline_adaptive_irrigation.py`. The canonical
`rootline_water_energy_plan` invokes it through the existing irrigation task
seam when adaptive evidence is supplied. This is not a scheduler or parallel
executor.

## Daily zone decisions

Each zone receives exactly one state:

- **Run now:** current evidence supports one bounded segment after immediate
  execution revalidation.
- **Run later:** need is supported, but season or power favours a later window.
- **Hold:** evidence supports not watering now, including recent completion or
  observed local rain.
- **Needs Data:** only the water-dependent execution lacks a necessary current
  fact; unrelated advice continues.
- **Completed:** a verified irrigation completion exists for the zone today.
- **Reassess after segment one:** segment one and shutdown are complete, but a
  new evidence generation must decide whether another segment remains useful.

Both camps may rank for the same day. They may not run simultaneously. A rank
is not command authority. Every execution remains separately bound to its
commissioning identity and a fresh canonical eligibility record.

## Need score and confidence

The bounded 0–100 need score uses only supplied facts:

- current visible need or owner correction;
- elapsed time since the latest completion;
- shortfall against the approximate four-day weekly guidance;
- fresh observed rain as an authoritative Hold signal;
- current water availability as an execution gate;
- current SOC and governing reserve for timing;
- season for evaporation/power timing.

Missing soil-moisture or flow instruments lower confidence and remain named
gaps. They do not erase recent completion, visible need, weather, water, or
power evidence. Forecast staleness lowers confidence but does not override
fresh local weather or block non-forecast-dependent reasoning. No score is a
claim of litres delivered, flow rate, or soil condition.

Summer generally favours evening/night irrigation. Winter may favour daylight
when current solar and reserve margin support it. Urgent water continuity may
justify grid exposure even below the normal reserve, while the reason and
uncertainty remain explicit.

## Commissioned execution boundary

- B12345: channel 1, commissioning
  `ROOTLINE-COMMISSION-D248A120ECE1961DB81B6C2E`.
- C12345: channel 2, commissioning
  `ROOTLINE-COMMISSION-70417672399B3525D658F6A2`.
- Power-cycle binding:
  `43fda51c1ecb3f638ef193a134551f5e802b3ffc1c236f46c561689ec69603ed`.
- Maximum execution: 60 minutes under independent native auto-OFF.
- ON: one attempt; ambiguity is contained, never retried automatically.
- OFF: state-setting and safely repeatable only while shutdown is unverified,
  up to the governed attempt limit.
- Segment two: new identity and fresh decision only after segment-one shutdown
  is independently verified.
- Borehole, fertilizer injection/mixing, channels 3/4, and simultaneous B/C
  remain outside this authority.

## Outcome learning

Every completed or failed run can produce an immutable learning packet with:

- planned and actual start/stop;
- planned and verified runtime;
- shutdown evidence;
- optional physical-flow observation;
- observed weather/rain after irrigation;
- later visible crop/soil response;
- owner correction;
- whether another segment was needed.

Learning returns bounded hints for the next decision. It cannot change the
four-day guidance, reserve policy, commissioning boundary, or other farm policy
silently. Delivered volume and flow rate remain `Unavailable` without meters.

## Oom Sakkie projection

Oom Sakkie should expose one useful daily recommendation, then update one
visible lifecycle at actual start and verified completion. It emits one alert
for failed shutdown, unexpected rain, water shortage, or material power
conflict. It suppresses an unchanged Hold/result digest and asks no question
when existing evidence supports the decision.

Example family brief:

> **Water today:** B is complete from its recent verified irrigation. C is the
> next priority. Current dry weather, available reservoir water and the battery
> margin support one C-Camp segment of up to 60 minutes this evening. B stays
> off. After C stops, I will verify shutdown and reassess fresh weather, water
> and power before deciding whether a second segment is useful. I will cancel
> the next segment for rain, water shortage, loss of reserve margin or any
> uncertain shutdown.

The wording intentionally omits internal identities, scores, implementation
terms, and unsupported water-volume claims.

## Future borehole policy (not implemented here)

Water continuity has priority over strict grid avoidance. Borehole pumping is
primarily an after-sunset catch-up operation, with power and independently
timestamped storage/reservoir evidence influencing advice. A full-storage
condition may leave an energized smart controller drawing no pumping load, so
electrical energization, motor load, water flow and delivered volume remain
separate observations. Low water may justify grid exposure. Missing sensors
reduce precision but do not prohibit proportional read-only advice.

No borehole hardware identity, binding, command, schedule, or autonomous
authority is added by this contract.
