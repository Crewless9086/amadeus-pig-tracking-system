# ROOTLINE Water And Energy Rules

Status: owner-confirmed operating knowledge

Last governance reconciliation: 2026-08-12

Purpose: provide the controlling business and physical-system rules for ROOTLINE water, energy, weather, and future device-management work.

## Operating Goal

ROOTLINE should protect reliable farm water while minimizing avoidable prepaid-grid use. Grid avoidance is an optimization goal, not permission to risk farm water or other critical farm functions.

ROOTLINE must observe, reason, plan, verify outcomes, learn from forecast and operating performance, and escalate only genuine exceptions. It must never claim control over an unconnected or independently operated device.

## Physical Water System

The confirmed high-level water path is:

1. Roof rainwater and the borehole feed five storage tanks of approximately 5,500 litres each.
2. An independent solar transfer pump moves water from those storage tanks to twelve reservoir tanks of approximately 5,500 litres each.
3. The reservoir supplies downstream farm demand and irrigation.
4. Reservoir overflow returns to the storage side, reducing avoidable water loss.

### Borehole

- Borehole 1 uses a separately commissioned SmartLife/IFTTT plug. It is a
  distinct typed device and authority domain; B/C irrigation or fertilizer
  commissioning never grants borehole authority.
- Commissioning proves the exact plug/control identity only. It does not by
  itself prove that the motor ran, water moved, storage filled, or routine or
  autonomous authority is enabled.
- Every governed actuation still requires the exact canonical binding, fresh
  provider state, explicit applicable owner/standing authority, bounded native
  shutdown, power-restoration-safe state, manual isolation and physical or
  provider outcome verification. Missing evidence fails the protected action
  closed.
- The borehole may operate at night; there is no owner-reported noise-hour restriction.
- The pump/controller has its own internal protection and storage-full cutoff.
- If the storage tanks are full, the internal controller can stop pumping even while the smart plug remains energized.
- ROOTLINE may not infer that the borehole ran, pumped water, or filled storage merely because the smart plug was ON.
- Once the exact canonical action and applicable authority are governed, nighttime is the borehole catch-up window. ROOTLINE chooses start time and duration from water continuity, storage/reservoir evidence, actual rain, forecast reliability, battery/solar/grid evidence, and expected need.
- The internal full-tank cutoff means an energized overnight window is not itself proof of needless pumping, but ROOTLINE must verify actual outcome rather than equating plug state with water movement.

### Solar Transfer Pump

- The solar transfer pump is not connected to a smart controller.
- It runs independently when its available solar conditions permit.
- It is not currently a ROOTLINE-controlled device.
- ROOTLINE may treat it only as an external physical dependency or an observed outcome.
- ROOTLINE must not schedule it, command it, require a smart-device binding for it, or describe it as controllable.
- A future control classification requires an explicit physical/control-system change and a new owner-reviewed device binding.

### Tank Evidence

There are currently no integrated electronic tank-level sensors available to ROOTLINE.

ROOTLINE may request a simple owner observation when it would materially change the plan. Storage and reservoir observations are independent and may arrive hours apart. Supported shorthand includes:

- `Storage 4/5`
- `Reservoir 8/12`

The authenticated message timestamp is the default observation time. Charl specifies another time only when reporting an earlier observation. The counts describe tanks currently regarded as available/full enough for the stated observation. They do not prove litres, flow, or future demand. Some reservoir tanks may deliberately be isolated to preserve emergency water in case of a leak.

A fresh storage observation remains useful if reservoir evidence is stale or missing, and vice versa. Missing one blocks only dependent conclusions; Oom Sakkie must not require both in one message or ask again for a supplied fact.

ROOTLINE must not demand this observation every day when the decision can be made safely without it.

## Forecast And Observed Weather

Forecast rain, locally observed rain, and captured useful water are different evidence classes.

### Forecast Rain

- Forecast rain is a future probability, not proof that rain occurred.
- It is not proof that either storage group received water.
- It may influence timing, reserve, and a bounded decision to defer pumping.
- It must never be recorded or reasoned about as captured water.

### Local Weather Station

- Fresh local-station readings are authoritative evidence of conditions observed at the farm.
- A local rain reading can prove detected rainfall under the active freshness rules.
- It still does not prove how much useful water entered the tanks.
- Routine autonomous B/C dry release is machine-evidenced. It requires the
  governed local station to be healthy and fresh, an automatically calculated
  continuous zero-rain interval of at least 30
  minutes, at least two durable boundary readings, and no missing or
  conflicting reading in that interval. Owner review, manual visible-rain
  confirmation, and per-cycle approval are not routine execution gates.
- Rain above the active current-rain threshold produces Hold. Stale, unhealthy,
  missing or conflicting local-station evidence also fails closed; standing
  authority does not bypass these current-weather gates. Forecast freshness is
  planning quality: stale or unavailable forecast evidence must be reported as
  degraded confidence, but it is not by itself a B/C execution prohibition.
  Forecast rain may change planning, prioritisation, duration or future-window
  selection only through an explicit active governed forecast threshold;
  `Unknown` forecast-threshold policy grants no invented execution Hold.

### Captured Water

Useful captured water requires tank evidence or another future authoritative observation. Neither a forecast nor a rain-gauge reading alone proves the storage outcome.

### Mandatory Reassessment

A forecast-based decision to delay borehole pumping must:

1. state the evidence cutoff and forecast confidence;
2. define a reassessment deadline;
3. compare predicted rain with fresh local observations;
4. consider every independently available storage/reservoir observation and current water-continuity risk;
5. create a recovery recommendation at the next suitable energy window if useful rain did not materialize.

The exact routine reassessment time/window remains to be set in an owner-reviewed policy. Until set, ROOTLINE must label a forecast-only recommendation `Defer and Reassess` or equivalent, not an unconditional full-period `Do Not Run`, unless separate current water evidence proves pumping unnecessary.

ROOTLINE must learn forecast reliability by retaining privacy-safe predicted-versus-observed outcomes. It must not silently treat a repeatedly unreliable forecast source as high confidence.

## Water Continuity And Grid Policy

- Farm water continuity and critical farm functions outrank strict grid avoidance.
- Water is a standing essential requirement, not an optional demand Charl must repeatedly classify as `needed` or `urgent`.
- Avoidable grid use should be minimized across days and months.
- Grid-supported pumping is permitted when genuinely required to protect water continuity.
- ROOTLINE should conserve battery/grid capacity on days when pumping is not needed so capacity remains available on poor-weather or high-water-demand days.
- Expected rain may justify a bounded delay, but it may not create an avoidable water shortage.
- If expected rain fails, ROOTLINE should recover the missed pumping opportunity rather than wait indefinitely.
- When storage and reservoir evidence show adequate water, ROOTLINE may stop at an owner-approved SOC threshold to avoid unnecessary grid use.
- When both storage and reservoir are low, water wins: ROOTLINE may recommend governed overnight grid-backed pumping even when battery energy is low.

Current owner-confirmed energy boundaries:

- approximately 40% SOC is the absolute floor ROOTLINE should not intentionally cross for discretionary pumping;
- the inverter/grid fallback begins at approximately 30%;
- approximately 50% is the provisional normal working reserve;
- ROOTLINE may recommend a higher dynamic reserve from forecast confidence and learned consumption;
- the current poor/uncertain evidence policy may govern at 70%;
- prepaid grid energy is approximately R9/kWh and historically about R2,000 per month, but billing-grade reconciliation is still required.

Present solar production alone is not sufficient reason to reduce the governing reserve.

## Irrigation And Fertilizer Context

Irrigation eligibility, runtime, weather, available water, and energy must be reasoned about together.

### B and C camp irrigation policy

- `B12345` (B Camp) and `C12345` (C Camp) are loaded in the irrigation app.
- B Camp is approximately 80 m x 30 m (2,400 m2) of lucerne. C Camp is approximately
  30 m x 10 m (300 m2) of mixed vegetables including spinach and beetroot.
- Both camps have very sandy soil. Drip irrigation normally infiltrates without visible
  pooling or runoff, but deep drainage beyond the crop root zone remains possible. ROOTLINE
  must not give B and C identical effective-rainfall credit merely because they share one
  rain observation.
- The nearby farm weather station is the owner-designated authoritative local rainfall source
  for B and C until a stronger local source is commissioned. Preserve its observation time
  and coverage; forecast rain remains separate and receives no delivered-water credit.
- B and C use the same owner-confirmed nominal drip layout: 3.5 litres/hour per emitter,
  approximately 1 m emitter spacing and 0.5 m row spacing. This implies approximately
  7 mm/hour, 7 mm per verified 60-minute segment and 14 mm per nominal two-segment day.
  Approximate nominal zone flow is 16,800 litres/hour for B and 2,100 litres/hour for C.
  These calculations are planning estimates until measured flow/pressure and actual emitter
  coverage validate them; ON/OFF receipts alone never prove delivered water.
- The historical rigid app pattern was one camp from 22:00-00:00 SAST every other day. It is baseline evidence only and must not become ROOTLINE's permanent decision rule.
- The owner target is to irrigate each of B and C Camp approximately four days per week, normally for about two hours because they are drip systems, while optimizing for adequate soil water and yield rather than mechanically following a calendar.
- This weekly requirement is the default agronomic obligation. Charl must not repeatedly report that a camp visibly needs water before ROOTLINE can plan or execute routine irrigation. A visual observation is useful priority/correction evidence, not a standing prerequisite.
- ROOTLINE must maintain per-zone weekly delivery debt from verified completed segments. Weather, observed rain, season, water availability, power, prior outcome and owner correction may move, shorten, recover or hold a segment, but an absent visual report must not silently erase the weekly obligation.
- ROOTLINE must produce a fresh plan for each operating day from crop/season need, recent completed irrigation, soil or other available need evidence, storage/reservoir evidence, and observed and forecast weather. B/C valve actuation is gravity-fed and must not be delayed, held, scored down, or made `Needs Data` because of battery SOC, solar, load, grid state, forecast-derived reserve, or stale power telemetry. Power may be reported as wider farm context, but it is not a B/C irrigation eligibility or timing gate.
- Under the current envelope ROOTLINE may run B only, C only, or both sequentially; it may shorten a run, move it, or hold it. Concurrent B/C is a future expansion requiring separate hydraulic/electrical commissioning, exact owner authorization, reviewed implementation and explicit activation; it does not inherit current B/C standing authority. The plan must state what will run, when, for how long, why, and when it will reassess.
- Summer generally favours night irrigation so water can enter the soil with lower avoidable loss. Winter or current conditions may support daytime irrigation. Clock time is an adaptive decision, not a fixed rule.
- Frequency and nominal two-hour duration are agronomic starting targets, not authority to under-water, over-water, or invent crop/soil evidence. Material deviations require an evidence-backed reason and must preserve the weekly delivery objective or schedule recovery.
- Weekly day debt is not identical to crop-water deficit. Fresh observed effective rainfall
  may proportionally reduce, satisfy or defer a zone obligation through the versioned
  water-balance contract in `docs/06-operations/ROOTLINE_EFFECTIVE_RAINFALL_WATER_BALANCE_PLAN.md`.
  Forecast rain receives zero delivered-water credit. Until that contract is operational,
  rain may Hold/reassess irrigation but must not silently erase or manufacture debt.
- Energy policy is device-class specific. It governs material electrical loads such as the Borehole 1 pump and fertilizer mixer, not passive water delivery through the B/C gravity-fed valves. ROOTLINE must never apply a generic farm-energy gate to every registered device.
- Before direct control, each valve identity, ON/OFF behavior, deterministic OFF, water flow, manual isolation, and safe failure must be physically proven.
- A stable per-zone, per-Johannesburg-operating-date consumption key must be
  atomically consumed before dispatch. Regenerated equivalent decisions,
  concurrent workers and replay may not dispatch the same zone twice on the
  same operating day.
- The old rigid app schedule should be retired only when ROOTLINE's reviewed IFTTT control rail is operational and verified. Until then, ROOTLINE may plan and monitor, but disabling the only working executor would risk missed irrigation.

### Irrigation execution and owner visibility

Once the reviewed IFTTT rail is operational, ROOTLINE is the irrigation execution owner within its approved envelope. It must use exact device bindings, deterministic OFF, bounded retries, outcome verification, and safe containment.

The safety objective is not "exactly one OFF request." The required physical outcome is that an authorized run cannot remain on beyond its maximum runtime:

- `ON` is a state-setting action, never a toggle. An ambiguous `ON` result is not retried automatically.
- `OFF` is a state-setting, physically idempotent action. Repeating `OFF` is safe and is required when stop confirmation is absent or ambiguous.
- Before `ON`, ROOTLINE must arm and verify an independent maximum-runtime fail-stop that does not depend on the same process surviving. Preferred implementations, in order, are a device-native countdown/auto-OFF/inching function, a device-native paired stop schedule, or a separately durable controller/workflow with a device backup.
- A command receipt proves transport acceptance only. Where direct device state, electrical-current, flow, or valve-position evidence exists, ROOTLINE uses it to verify start and stop. Until such telemetry exists, supervised physical observation may prove a bounded commissioning run.
- A bounded run records one authorized execution identity, its maximum runtime, backup-stop deadline, primary stop attempt, every safe repeated `OFF`, observed outcome, and final containment state.
- Failure to arm the independent fail-stop blocks `ON`. Failure to verify shutdown after the fail-stop creates one urgent hardware exception and keeps the zone unavailable for autonomous reuse.

For B/C autonomy, the owner-approved standing operating envelope is deliberately narrow: proven B and C irrigation valves only; no fertilizer or borehole actuation; no concurrent B/C run; each native fail-stop segment is at most 3,599 seconds; a nominal two-hour objective requires two distinct segments with verified shutdown and a fresh canonical decision before segment two. Source defaults fail closed and require the exact runtime authority flag to be explicitly enabled during a separately assigned production window. This documentation audit did not read production configuration and does not establish the current deployed flag value; it authorizes no enabling. When separately proven enabled, ROOTLINE may execute eligible B/C segments within this envelope without routine per-run permission. A genuine boundary exception, same-zone same-day duplicate, uncertain shutdown, unavailable fail-stop, conflicting evidence or proposed expansion requires containment and owner attention.

Oom Sakkie must maintain one daily Telegram card per day's irrigation plan rather than producing notification clutter. Its lifecycle is:

- `Planned`: zones, intended window/runtime, reason, evidence cutoff, and next reassessment;
- `Active`: exact zone(s), verified start time, and expected stop/reassessment;
- `Hold`: reason, affected zone(s), and next trigger;
- `Stopped`: stopped early or contained, with reason and remaining work;
- `Completed`: verified stop, delivered runtime/outcome evidence, deviations, and next expected irrigation.

The daily card should be edited for low-attention plan changes. Because edits do not reliably notify Charl, each actual hardware start and completion/stop must also produce one new, concise, human-friendly buttonless operational notification following `../07-standards/OOM_SAKKIE_TELEGRAM_MESSAGE_STANDARD.md`. After confirmed completion, a superseded temporary start notification may be deleted for presentation cleanup while the daily card and durable audit evidence remain. A command/provider receipt alone must not mark `Active` or `Completed`; physical or authoritative device outcome evidence is required. Buttons are reserved for genuine protected exceptions or authority decisions.

Unchanged automatic reassessments are silent. ROOTLINE sends no repeated full technical packet merely because a timer fired. One unchanged missing fact is requested once and remains pending until answered, superseded, or no longer material. A new visible message is reserved for a material plan change, hardware start, verified stop/completion, failure, or required intervention. Detailed SOC, load, forecast provenance, scores, internal identities, and evidence gaps remain available on request or for a genuine exception rather than appearing in every routine family notification.

### Device-class planning model

Every new ROOTLINE device must be registered once with a typed operating contract rather than inheriting assumptions from another device. The contract records:

- physical function and served system;
- passive/gravity-fed or electrically powered classification;
- energy relevance (`none`, `minor_control_only`, `material_load`, or `unknown`);
- exact control provider, device and channel;
- authoritative state/readback fields and freshness;
- safe default, independent fail-stop, maximum runtime and restoration behavior;
- physical dependencies such as reservoir water, pump pressure, another valve, or human isolation;
- planning inputs that are relevant to this device class;
- explicit exclusions that must not influence its plan;
- commissioning evidence, observation/verification method and rollback;
- standing authority and the exceptions that require owner attention.

Adding a device must not require rewriting ROOTLINE's whole planner. The typed contract supplies device-specific facts to a shared loop: observe, determine need, rank, plan, verify eligibility, act within standing authority, confirm outcome, learn, and notify only material change. An unknown field blocks only the action or claim that depends on it.

Confirmed initial classifications:

- B/channel 1 and C/channel 2: commissioned gravity-fed irrigation valves; `minor_control_only`; farm SOC/reserve is excluded from irrigation need, ranking, timing and execution eligibility. Commissioning does not mean the production autonomy flag is enabled.
- Borehole 1 SmartLife/IFTTT plug/pump: separately commissioned `material_load`; water continuity, storage/reservoir state, night catch-up, SOC, solar, grid and forecast reliability are relevant, with water continuity allowed to outweigh grid avoidance. Electrical ON is not proof of motor operation, pumping or delivered water.
- Solar transfer pump: independently operated and monitor-only; no ROOTLINE actuation authority.
- Fertilizer injection valve: flow-dependent control device; active irrigation, pre-flow, pulse spacing and clean-water flush are relevant; farm SOC is not assumed relevant without a material load.
- Fertilizer mixer: `material_load` until measured otherwise; energy-aware scheduling is relevant.
- Unknown breakers, plugs, valves and sensors: disabled for actuation until their own typed contract and commissioning evidence exist; they must not contaminate unrelated device decisions.

### Current fertilizer timing and missing bindings

The historical irrigation-app injection windows are 22:05-22:07, 22:35-22:37, and 23:05-23:07 SAST. They are baseline evidence only, do not prove fertilizer flowed, and must not become fixed ROOTLINE timing.

The fertilizer injection valve and fertilizer mixing valve each still require exact IFTTT ON/OFF functions and physical identity/outcome proof before ROOTLINE control. After that, ROOTLINE chooses injection and mixing times from that day's irrigation plan, fertilizer need, required pre-flow/flush, weather, and energy. If energy is poor, non-urgent mixing may be deferred and recovered at a better window. Timer or relay state alone is not proof of mixing.

The fertilizer controller facts currently supplied by the owner are:

- manufacturer: SONOFF;
- model: 4CHPRO R3;
- device ID: `100204d497`;
- controller name: `Controller (1) Right`;
- channel 1: `Kunsmis In`;
- channel 2: `Kunsmis Meng`;
- channels 3 and 4: physically unconnected at the time of this decision.

Confirmed direction:

- fertilizer is an owner-made natural liquid mixture;
- both irrigation zones may eventually receive it;
- irrigation should establish water flow before injection;
- the historical app injection began five minutes after irrigation started; this is evidence of the former setup, not a permanent pre-flow rule;
- provisional minimum interval between injection pulses is 10 minutes;
- injection must end early enough for clean-water irrigation to flush the line;
- channel 2 currently mixes fertilizer for 30 minutes daily; a future reviewed plan may split this into two 15-minute periods;
- the stated injection-duration evidence conflicts: 60 seconds was supplied as a maximum while the owner also indicated longer than 60 seconds may be preferable.

The historical app used two-minute injection windows. ROOTLINE must derive future pulse timing from the reviewed fertilizer structure and physical flow/concentration evidence rather than preserve those clock times blindly.

The owner regards temporary static-line contact with this natural mixture as low risk. This does not prove relay identity, deterministic OFF, timing accuracy, or successful injection.

### Fertilizer controller facts confirmed 2026-08-09

The owner confirmed the following exact IFTTT Webhooks event names for
`Controller (1) Right` / device `100204d497`:

- channel 1 / `Kunsmis In` ON: `controller_1_ch1_on`;
- channel 1 / `Kunsmis In` OFF: `controller_1_ch1_off`;
- channel 2 / `Kunsmis Meng` ON: `controller_1_ch2_on`;
- channel 2 / `Kunsmis Meng` OFF: `controller_1_ch2_off`.

These do not textually collide with the established B/C events under the
`irrigation_1_ch*` namespace. ROOTLINE must still bind them to the exact provider device,
channel and physical outcome during commissioning rather than trusting names alone.

Physical behavior:

- `Kunsmis In` opens the fertilizer injection valve into the irrigation station's
  shared mainline. The pressure drop starts the shared approximately 1 kW pump through
  its independent pressure switch. The mainline supplies B, C and future zones on the
  same station, so injection is not a crop zone and must bind to the one verified active
  irrigation zone.
- `Kunsmis Meng` opens a recirculation valve back into the fertilizer tank. The same
  pressure-switched pump starts and creates the flow that mixes the tank. Mixing is an
  auxiliary support task and can run independently from irrigation.
- Both functions can be stopped in the app, at the controller, or manually at the
  co-located valves.
- The fertilizer tank auto-fills with water and is expected not to fall below its operating
  level. Water-only refill progressively dilutes the fertilizer mixture, so a full tank is
  not proof of nutrient concentration or fertilizer readiness. The owner adds a new batch
  of fertilizer mixture weekly on Mondays.
- If injection remains open while an irrigation zone is flowing, it can empty the
  fertilizer tank into the irrigation main. This makes bounded native auto-OFF and
  injection-to-active-zone interlocking mandatory even though the pump has an independent
  pressure control.
- If the mixer remains open, the tank continues recirculating. If the tank cannot supply
  flow, the owner reports that the pressure-controlled pump does not start. Provider and
  physical commissioning must still prove valve identity and shutdown.

Initial owner operating envelope for commissioning and planning:

- injection pulse target and maximum: 120 seconds;
- owner reports native channel-1 Inching configured at two minutes; provider readback and
  physical commissioning must verify the exact 120-second value before injection ON;
- minimum injection pulses per eligible 60-minute irrigation segment: two;
- clean-water pre-flow before the first pulse: at least 10 minutes;
- clean-water flush after the final pulse: at least 10 minutes;
- minimum spacing between injection pulses remains 10 minutes;
- mix for approximately five minutes before the first irrigation segment and again before
  a subsequent segment when fertilizer will be injected;
- independent daily mixing may total at most 30 minutes, split into smaller sections as
  energy conditions permit;
- channel 2 requires an independently verified native mixing fail-stop before autonomous
  use; the initial target is five minutes per mixing segment, with no more than 30 verified
  minutes per day;
- the mixer/pump path is treated as an approximately 1 kW material load until measured;
- B/C gravity-fed irrigation remains independent of farm energy state, while fertilizer
  mixing may be optimized against energy evidence;
- injection cannot run unless exactly one eligible irrigation zone is already active and
  clean-water pre-flow is proven;
- mixing and injection remain outside standing autonomy until each channel receives exact
  provider readback, typed auxiliary-device registration, independent supervised physical
  commissioning, native fail-stop proof, deterministic OFF, replay proof and separate
  activation authority.

The operating envelope establishes how to execute a supported fertilizer task; it does not
establish when fertilizer is agronomically required, the mixture's concentration/recipe,
or whether B and C should receive the same fertilizer programme. Those remain separate
eligibility evidence and must not be inferred from an available/full tank.

The initial owner fertilizer programme is to inject during every eligible B or C irrigation
run because the farm is rebuilding the soil. This establishes intended frequency, but it
does not prove dose or concentration. ROOTLINE must mix before injection and track the Monday
batch, subsequent injection events and water-only refill/dilution. Autonomous dosing must
remain bounded by measured or owner-approved batch capacity, recipe and injection flow; a
fixed valve duration must not be presented as a fixed nutrient dose until those facts are
known.

## Future SmartLife, SONOFF, And IFTTT Setup

Future setup should create consistent ON and OFF functions for intended channels, including currently unused channels when useful for later installation.

An unused channel must be recorded as:

- configured but physically unconnected;
- disabled for ROOTLINE runtime use;
- safe default OFF;
- no assumed equipment, flow, energy, or farm effect.

Creating an IFTTT function does not prove a physical device mapping and does not grant ROOTLINE actuation authority. A commissioned mapping likewise does not grant another device class authority or prove a specific farm outcome.

The future setup runbook must record, without storing secrets:

- platform and owner-facing device name;
- controller and physical channel;
- webhook/event naming convention;
- ON and OFF functions;
- connected or unconnected state;
- served equipment;
- safe default and deterministic OFF;
- manual isolation and emergency stop;
- supervised identity proof;
- rollback procedure.

Charl may use ChatGPT for step-by-step setup, but the final authoritative mappings and verification evidence must be reconciled into the repository. Prior chat context is not the source of truth.

## Authority Boundary

These rules authorize observation, reasoning, adaptive planning and owner summaries. They document the owner-approved standing B/C envelope, but do not themselves enable its production runtime flag. Hardware configuration, activation and expansion remain separate protected decisions.

They do not authorize outside that proven B/C envelope:

- borehole, solar-transfer, fertilizer, uncommissioned channel or unrelated hardware actuation;
- ambiguous ON retry, simultaneous B/C, automatic segment-two continuation without fresh decision, or execution beyond 3,599 seconds;
- treating unconnected channels as equipment;
- treating forecast rain as observed or captured water;
- treating an energized plug as proof of pumping or water delivery.

Standing B/C authority becomes operational only when the reviewed implementation binds existing commissioned evidence, the automatic scheduler, deterministic state-setting ON, native 3,599-second auto-OFF, safe repeated OFF, provider-confirmed OFF/shutdown, atomic same-zone daily consumption, daily plan lifecycle and exception containment, and the exact production authority flag is explicitly enabled. This removes routine per-run approval only inside that enabled envelope; it does not waive prerequisites or expand authority to fertilizer or Borehole 1.

## Channel-Invariant Canonical Actions

The application, typed Oom Sakkie, Telegram and voice must normalize equivalent
ROOTLINE intent into one versioned specialist-owned canonical action. Every
channel uses the same authoritative evidence, preview identity and digest,
owner/standing-authority check, idempotency key, executor, provider verification
and canonical readback. A channel may improve presentation but may not add a
private mutation path, weaken confirmation or reinterpret completion.

Hardware actions require explicit owner authorization unless they fall inside
an explicitly enabled and proven standing envelope. Voice transcription,
Telegram delivery, UI clicks and semantic interpretation are intent evidence,
not actuation authority. Completion requires the device-specific provider and
physical verification defined above.
