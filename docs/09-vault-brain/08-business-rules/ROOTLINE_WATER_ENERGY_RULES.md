# ROOTLINE Water And Energy Rules

## Owner-directed controller recovery and truthful shutdown - 27 November 2026

The owner requested the shared repair after a mixer remained running following
an OFF notification during intermittent connectivity, and approved implementation
and release. Home Assistant queue acceptance alone no longer establishes a
successful Sonoff command. A correlated response from the exact commissioned
controller accepting the exact channel/state establishes controller acceptance,
not independently observed relay state or measured flow. Preserve independent
raw device observations and act on later contradictory OFF reports. MQTT state
can include a bridge-synthesized command echo and must not alone confirm ON.

Retain each original execution and OFF deadline until the controller accepts
OFF. After the existing initial three attempts, retry only the still-owned OFF
at most once per five minutes, with durable serialization and a newer-ownership
and explicit-isolation fence. Never repeat uncertain ON or reopen an owner-stopped
or completed programme. A transport-proven failure before any LAN command was
sent may retire the unused claim without inventing an OFF observation; existing
eligibility and remaining-window rules govern any subsequent fresh claim.

Availability belongs to the physical controller. Loss of Controller (1) Right
pauses mixing and injection, not independently eligible irrigation, borehole or
Eskom. Check connectivity through the existing cycle, preserve the first outage
time, send one useful outage notice and one recovery notice, and reconcile owned
OFF duties before admitting remaining eligible work. Unexpected OFF while a
controller is reachable is an interrupted run, not an offline controller.

A fresh, exactly correlated getState acknowledgement with a device sequence may
anchor recovery of the existing raw observer after reset. It supplies no switch
state: outputs remain Unknown until a subsequent decrypted raw device report
arrives after that anchor with a sequence at least the acknowledged value.
Anchors expire after sixty seconds and must be reacquired after HA restart.
Cached discovery data, MQTT echoes and requested state never seed observations.
The unauthenticated LAN protocol cannot prove a cryptographic boot generation
or exclude every old-generation replay; report that limitation honestly.

Keep operating durations, native countdown configuration, Eskom policy and
historical receipts unchanged. No external flow, dose or physical-contact sensor
is added as an operating prerequisite.

## Owner-directed borehole power restoration — 27 November 2026

The owner reported an overnight blackout followed by the borehole AC switch
returning OFF, then manually restored ON. The owner explicitly requested changing
the existing borehole controller (1002851416, channel1) to restore its previous
state after power loss and repairing ROOTLINE's stale command-state handling.
For this exact borehole controller, Last state supersedes previous restoration-OFF
requirements. This does not change camp, mixer or injector restoration settings.
Preserve the current relay state while changing this configuration. ROOTLINE must
retain its existing weather/energy supervision and explicit manual isolation;
restoration configuration does not itself prove a later blackout recovery.
Reconcile supported later external switch reports without presenting cached
command acceptance as current physical state or repeating an uncertain ON.

## Owner-directed editable injection programme - 26 November 2026

The owner selected two ten-minute injections per sixty minutes of irrigation,
with Camps A, B, C and E eligible. Expose injection duration, injections per
sixty minutes and individual camp selection through the existing authenticated
owner settings page. The owner will save the desired settings there after
release; a source deployment alone must not change the saved operating policy.
Absent an explicit effective save, retain the existing two-minute pulse,
two-per-hour B/C programme and any existing lower legacy pulse cap.

New effective saves govern prospective command-accepted, scheduled pulses:
duration one to ten minutes and one or two pulses per hour, in the selected
commissioned camps only. The per-hour selection replaces the former per-run
cap for this new programme. Preserve ten minutes of clean-water preflow,
at least ten minutes between accepted pulse shutdown and the next pulse,
and at least ten minutes of final flush. Admit only pulses that fit the
remaining parent irrigation window; do not overlap or extend the parent run.

Pin the selected policy and duration to each new canonical claim. Existing
claims and accepted-ON targets retain their original timing through later
settings changes, expiry or restart. A changed pulse count after a completed
pulse takes effect on the next camp run; do not reinterpret existing pulse
ordinals or interrupt the independent irrigation run. Longer pulses remain durable owned duties
on the existing minute scheduler, with no wait beyond its existing bounded
horizon. Parent loss, manual isolation and existing stop conditions retain
priority; uncertain ON is never repeated. Command acceptance does not establish
measured flow, physical duration, concentration or dose.


## Owner-directed clear notifications - 26 November 2026

Prepare the programme at the existing nightly planning time, but send the
routine daily Telegram plan at06:30 Africa/Johannesburg, once per local day.
Later routine notices require a material change; new observations alone do not
justify repeating the same plan. Explicit owner requests and urgent equipment
exceptions remain available outside that routine-plan window.

List scheduled camps as separate bullets in actual run order, with local windows
such as10h00-11h00 and the date once in the heading. Use distinct activity/device
emojis. Do not label advisory planning recommendations as current equipment state;
omit unhelpful generic auxiliary Needs Data/Recommend labels. Retain truthful
partial, completed, uncertain-command and unresolved shutdown distinctions.
Equipment transitions, delivery recovery and deduplication remain on the existing
canonical notification rail. This changes presentation and routine-plan delivery
time only, not forecast timing, equipment authority or operating limits.


## Owner-directed injector timing target â€” 22 November 2026

The owner selected a120-second injector target and explicitly directed reporting
of any command-delivery delay, with continuation through deployment and live
verification. For new accepted-ON pulses, measure the target from accepted ON
and request OFF at that target through the existing durable supervision path.
Report actual command-attempt and acceptance timing and any delay truthfully;
do not claim an exact physical duration or measured dose from command receipts.
This supersedes a strict120-second ceiling where it conflicts with this target.
Native countdown remains optional. Existing and uncertain shutdown duties must
not be extended. Preserve immediate shutdown for parent loss, manual isolation
or other existing stop conditions, and retain bounded uncertain-command recovery
without repeating an uncertain ON. Early interruption is not a completed pulse.

## Owner-directed command-based Home Assistant operation â€” 22 November 2026

The owner explicitly approved continuing through live activation and directed
ROOTLINE to send ON and OFF commands without waiting for separate controller
feedback. This supersedes contrary requirements below that make independent
switch readback a prerequisite for routine Home Assistant execution or normal
command-based lifecycle progression. Feedback improvement is deferred; it must
not keep this approved operating mode inactive.

Use the existing authenticated Home Assistant connection, exact device/channel
bindings and ROOTLINE execution/scheduler rails. A successfully accepted ON/OFF
service call is the operational result accepted by the owner for this mode.
Record and report it as command acceptance, not independently verified relay
state, pumping, water flow or measured delivery. Do not manufacture authoritative
readback or overwrite historical verified evidence with a weaker claim.

Preserve the agreed irrigation durations, weather and energy rules, explicit
manual isolation, single execution ownership, durable OFF duties across restart,
and protection against duplicate ON commands. A rejected request or network
timeout is failed or uncertain, not accepted. Do not repeat an uncertain ON;
retain its shutdown duty and use the existing bounded OFF recovery. An accepted
OFF may close the command-based duty while retaining unverified physical state.

This approval covers implementation, review, release and activation of this
bounded mode through the existing system. No new feedback account login or
cloud-observer installation is required for it. Keep the working independent
Eskom control and its existing30% ON /35% with solar recovery OFF policy intact.
Optional stronger observation can be added later without changing the ordinary
owner-approved command operation into a recurring approval or attendance gate.

## Owner-directed provider economy and visible input failures â€” 20 November 2026

ROOTLINE must minimize avoidable provider requests while retaining fresh evidence
at command and verification boundaries. Reuse one complete authenticated device
observation when it supplies the required facts; coordinate routine discovery
across workers and restart. Reduced polling must not delay owned shutdown,
conceal manual isolation, reuse stale evidence as fresh, or weaken identity,
authority, duplicate-command or verification checks. Measured test savings do
not prove a provider quota, remaining allowance or restored access.

Provider limits and unavailable weather, forecast or power inputs must not fail
silently. Through the existing owner channel, identify the affected capability,
what remains possible, and the next automatic recovery check. Preserve a stable
incident identity, suppress confirmed duplicates, contain ambiguous delivery,
and report verified recovery truthfully. A retry time is not a provider reset
time. A dated recovery is not proof that equipment resumed or is currently OFF.

Use the existing sensor, forecast, execution and notification records. Missing
evidence remains unavailable; stale numerical readings must not appear current.
An accepted backup forecast is distinct from complete forecast failure. Input
recovery and useful warnings belong to the deployed runtime, without recurring
owner monitoring or confirmations. Coordinate ownership with existing health
alerts before enabling replacement notices, preserving unrelated alerts and
rollback. This instruction does not authorize purchasing provider capacity,
changing account permissions, bypassing limits or manufacturing recovery.

## Owner-directed daily plan and live-condition adjustment â€” 20 November 2026

The owner's direct clarification supersedes contrary recurring forecast and
intraday forecast-deferral requirements below. The operating target is one
simple daily plan that ROOTLINE executes and adjusts autonomously. This policy
records the required behaviour; it does not claim the current runtime implements it.

At 23:30 Africa/Johannesburg, refresh the forecast once for the nightly planning
cycle and prepare the next local operating day's 24-hour plan. Use the correct
forecast dates, recent weeks' plans, actual completed irrigation and outstanding
work, together with the existing limits and guidance. Save one canonical plan
with intended work, timing and linked irrigation, mixer, injector and power
decisions. Reuse the existing scheduler, plan, execution and history records.

Execute the saved plan during the day. If actual weather, power or equipment
conditions block planned work, adjust the remaining plan using live observations,
completed work, available time and existing limits, without another forecast
fetch or reconsideration of forecast predictions. Preserve original owned OFF
duties, current safety/isolation controls and duplicate-command protection.
Condition-based borehole AC backup and Eskom decisions remain subordinate to
actual solar, battery and equipment evidence; a planned window cannot force ON
against the governing energy rules.

Record unfinished work and its reason for the next nightly plan. Catch-up must
remain within daily/weekly limits and must not duplicate already completed work,
override weather/energy constraints or manufacture delivery credit. Maintain
useful plan and material-change notices through the existing owner channel.
Repeated forecast refreshes or full-plan rebuilds are not substitutes for
executing and supervising the saved day's work.

The once-daily forecast cycle may use its existing backup source if the primary
fails. Failed acquisition must be reported honestly and cannot silently replace
actual completed work or turn yesterday's forecast into a fresh one. Retain the
approved operating rules and safe execution while resolving missing planning
evidence. Do not create another scheduler, queue or parallel plan system.

Unfinished irrigation retains its original obligation identity and verified
completion accounting, including work blocked before its first start. Allocate
recovery within the next day's normal allowance; never add that allowance again
as catch-up. Retain unresolved older work even when recent-plan context is
bounded. Attribute completion to the owning operating date across midnight.
A consumed single-segment daily run does not gain another start through a plan
revision. Existing unused legacy segments retain only their original authority.

A saved programme is intended work, never command authority. New starts still
require fresh live eligibility and the existing locked claim. Missing planning
evidence must not suppress owned OFF duties or independently supported borehole
AC backup and Eskom decisions. One deployment transition may adopt the existing
valid current-day inert plan without re-fetching forecasts or replacing its task
material; later days require their matching nightly programme evidence.

Auxiliary starts must leave the existing start window available before capacity
reservation and again before the durable claim. A contained claim that never
sent ON may retire only through the existing runtime recovery with complete
canonical history, command locks and fresh exact OFF evidence. Record zero
ON attempts distinctly from an unknown dispatched outcome, preserve reservations
and unfinished work, and never label safe retirement as completed mixing.

## Owner correction: borehole switch is AC backup â€” 20 November 2026

This direct owner correction supersedes any contrary interpretation below.
The controlled borehole switch (eWeLink device 1002851416, channel 1) supplies
AC backup to the hybrid borehole. The pump has its own separate solar panels.
Turning this AC supply OFF does not establish that the pump stopped; the pump
can continue on its own solar supply. Switch ON does not establish pumping.

When the agreed Sunsynk sunshine proxy is at or above 1.5 kW, ROOTLINE must keep
the borehole AC backup OFF and turn an owned AC supply OFF through its existing
guarded control path. Sunshine is not a reason to enable this AC switch.
Below that threshold, assess AC backup using the existing battery, charging/
discharging and grid-support rules, retaining the 30% battery floor. Do not
invent a new threshold or confuse the separate solar pump supply with Sunsynk
household power. Retain current evidence, explicit isolation, installed
protections and existing duplicate-command safeguards.

Reports must identify borehole AC backup ON/OFF separately from actual pumping,
which remains unknown without its own evidence. Earlier continuous-operation
approval did not authorize permanent AC backup during sufficient sunshine.
Existing weather rules cannot establish that disabling AC also stops solar
pumping. This correction is authority for repair, not proof of deployment or
of a verified AC OFF outcome.

## Owner-directed plan and equipment visibility â€” 16 November 2026

This instruction supersedes routine-plan silence below. Through the existing
Oom Sakkie Telegram delivery path, show the first fresh current daily irrigation
plan even when no owner decision is needed. Retain confirmed same-day unchanged
plan suppression and report material changes. A plan describes intended work;
it never establishes that equipment ran or that water was delivered.

After mandatory equipment supervision, bounded current-plan and verified
transition reporting must remain independent of unrelated manager reports and
control success. Report unavailable or failed checks honestly. Reporting never
extends the control-cycle deadline, delays owned shutdown or grants actuation.

Each verified valve, injector, mixer, borehole and Eskom ON/OFF transition gets
one concise visible notice with the observed time. Use canonical execution and
provider evidence, stable transition identities and existing durable delivery
claims. Accepted commands alone do not establish a transition. Preserve exact
provider ambiguity without resend; only a proven unsent attempt permits the
existing bounded retry. Do not invent continuous-borehole stop times or measured
water, nutrient or whole-job completion from switch state.

The deployed worker establishes one immutable, server-dated notification
recovery boundary at the start of its first operating day. It recovers bounded
batches of subsequent canonical transitions across midnight and restart using
the existing execution and family delivery records. Older events remain
historical evidence and are not relabelled delivered. Invalid transition
projections retain an explicit verification-required reason and ROOTLINE owner;
they cannot block later valid notices or masquerade as provider success.

## Owner-approved continuous borehole policy â€” 16 November 2026

This section supersedes contrary borehole duration and weather rules below.
The owner explicitly approved the corrected policy in the current conversation.
It is policy authority, not evidence that the replacement runtime or controller
configuration has already been deployed and verified.

- Reliable water supply is the primary goal. Prefer solar and appropriate battery
  use, but use Eskom when needed rather than sacrifice water availability.
- The hybrid borehole has its own solar supply, separate from the Sunsynk system.
  Use Sunsynk solar production at or above 1.5 kW as the owner's agreed sunshine
  proxy for borehole solar operation. It is not a direct pump energy meter.
- Below that sunshine signal, assess battery SOC, charging/discharging and grid
  support. Retain the existing 30% battery floor and Eskom support policy. Negative
  battery power in the existing telemetry convention indicates charging; SOC is
  the percentage remaining. Household AC load is supporting context and cannot
  by itself establish pump-only battery or grid consumption.
- Operate continuously while conditions support operation. Remove the four-hour
  run cap and ten-hour automatic cutoff from the new operating mode. Do not
  replace these with another arbitrary duration cap or artificial segmentation.
  The existing scheduler must retain durable ownership and condition-based OFF
  supervision across restart. Historical timed executions retain their original
  evidence and are not silently rewritten as continuous executions.
- Forecast heavy rain may postpone a new start once for one hour. Reassess local
  observed rain at the end of that hour; if none is detected, resume eligibility
  assessment. Forecast alone must not repeatedly defer the same opportunity.
- Detected local rain stops a ROOTLINE-owned borehole run. Reassess hourly and
  resume eligibility after one rain-free hour, subject to energy and safety.
  Missing readings do not prove a rain-free hour and do not alone stop a running
  pump. Preserve explicit OFF/isolation instructions and installed dry-run and
  storage-full protections. A full tank remains handled by the installed cutoff.
- Record decisions, switch outcomes, available energy context and forecast
  performance for later improvement. Use approximately R9.20/kWh for estimated
  grid costs. Label estimates and do not attribute all household grid import to
  the borehole or infer measured water delivery from electrical ON.

Implement and verify this through the existing ROOTLINE control path. Coordinate
the controller change only when replacement continuous supervision is ready;
do not claim timer removal or new weather behaviour from this policy update.

## Owner-directed simplified operation â€” 15 November 2026

This latest owner instruction supersedes contrary requirements below for
mandatory native inching, artificial run segmentation, repeated commissioning,
flow/volume proof, physical attendance and routine per-run confirmation. It
applies to Camps A, B, C and E, borehole, fertiliser injector and mixer, and the
ESKOM breaker. Existing device identities, actual manual isolation and the
agreed weather, irrigation and solar operating rules remain meaningful facts.

- Irrigation runs for its planned duration as one continuous run. Persist the
  intended OFF time in the existing canonical execution and let the existing
  durable scheduler perform and reconcile OFF after restart. Inching is optional
  controller configuration, not a prerequisite or a reason to split the run.
- Authoritative application/provider ON and OFF establish switch operation.
  Do not require flow measurements, litres, human attendance or another owner
  confirmation to establish that result. Do not claim measured water delivery.
- Missing or stale observations are unavailable information, not evidence that
  equipment failed. Preserve an owned run's planned stop, reobserve normally,
  and do not freeze unrelated devices because of a historical read or attempt.
  Current adverse weather and explicit manual OFF/isolation still take effect.
- Keep the owner's existing eWeLink schedules working until the replacement is
  ready and its handover is explicitly coordinated. Enabled controller timers
  must not make every channel unusable. Distinguish externally scheduled/manual
  runs from ROOTLINE-owned runs; do not duplicate starts or stop an unowned run
  merely because ROOTLINE lacks a start receipt.
- Correct device/channel identity, durable stop ownership, duplicate-command
  control and honest unknown-state reporting are implementation responsibilities,
  not recurring owner paperwork. Previously valid device setup is reused.
- Fertiliser follows the agreed mixing, injection, irrigation and flush timing;
  elapsed authoritative irrigation ON time supplies timing evidence without a
  flow-measurement prerequisite. A native countdown is optional here as well.
- Existing qualified same-day mixing remains reusable within the 30-minute
  daily cap; continuous irrigation does not create a new premix prerequisite
  for every hour. Preserve the established two bounded pulses per eligible
  hour without stopping irrigation. Missing routine batch confirmation alone
  does not block this time-based programme; an explicit current empty, unsafe
  or not-ready batch report still holds injection. Never invent batch contents.
- ESKOM uses its existing exact breaker binding and agreed solar/battery policy;
  it is not an irrigation timer and must not receive a fabricated timed OFF.
  Unavailable power telemetry retains its state until current evidence returns.
- Report what is planned, when it will run, what is running, and what stopped.
  Report a specific current failure honestly without substituting internal
  checklists or old commissioning labels for the equipment's actual state.

Enablement and current operation are established from live configuration and
provider/canonical results, not from this document. A genuinely missing device
mapping or unfinished physical connection must be identified precisely; it does
not hold back already configured equipment. Preserve historical records without
reinterpreting old segmented executions as new continuous runs.

Current owner facts: A targets two hours on approximately four days weekly
and shares B's gravity-fed supply. E is confirmed connected and ready on
15 November, with its own owner-confirmed target of two hours on four days
weekly, the same target as A. E crop and physical supply details remain unknown
and do not establish measured water delivery.

## Authority And Evidence Precedence

This file is the single durable policy source for ROOTLINE water, irrigation,
fertiliser and borehole decisions. The ROOTLINE agent and Control Architecture
define role and execution structure. Code, schemas and provider records prove
implementation/runtime facts. Dated plans, inventories, canaries, onboarding
notes, handovers and commissioning packets are archived evidence only and may
not override these rules or establish current state.

Current eligibility always requires fresh canonical and provider evidence.
Historical device identities and commissioning receipts remain immutable
evidence but are not replayable execution authority. Unknown stays Unknown and
blocks only the dependent action or claim.

Status: owner-confirmed operating knowledge

Last governance reconciliation: 2026-10-29 (integrated-operation owner corrections).

Purpose: provide the controlling business and physical-system rules for ROOTLINE water, energy, weather, and future device-management work.

## Operating Goal

ROOTLINE should protect reliable farm water while minimizing avoidable prepaid-grid use. Grid avoidance is an optimization goal, not permission to risk farm water or other critical farm functions.

ROOTLINE must observe, reason, plan, verify outcomes, learn from forecast and operating performance, and escalate only genuine exceptions. It must never claim control over an unconnected or independently operated device.

## Existing borehole and B/C operation

The owner's 2 November operating correction governs these three established
devices. Their commissioned identities and successful history remain valid.
New-device work does not restart their commissioning.

- Application/provider ON and OFF establish switch operation. Litres, water
  volume, flow measurement, tank-fill proof, physical attendance and repeated
  owner approval are not operating or acceptance prerequisites for these devices.
  Preserve existing records without inventing measured delivery.
- Borehole 1's owner-selected native inching is ten hours (36,000 seconds),
  replacing the earlier one-hour setting and four-hour ceiling for this device
  only. Ten hours is the fallback maximum, not the required duration of every
  run. Current energy decisions may choose shorter supply windows.
- A missing read alone must not cancel an already governed bounded run or
  freeze unrelated equipment. Keep its existing stop deadline, retry observation
  through the normal scheduler and report unavailable state honestly. Explicit
  owner OFF/isolation instructions and actual adverse evidence still apply.
- Reconcile interrupted B/C records automatically using fresh exact OFF state
  and the existing locked recovery path. Preserve consumed segments and unknown
  runtime; do not replay a spent segment or fabricate completed irrigation.
- Preserve and supervise an owner-started borehole ON without an unnecessary
  OFF/ON cycle. A missing ROOTLINE start receipt alone is not a stop instruction.
- B/C remain sequential. Borehole supply is independent of B/C, fertilizer,
  optional plan delivery and new-device commissioning. Authentication, exact
  device/channel identity, bounded stopping and duplicate-command control remain.

This section supersedes contrary volume, attendance, per-run confirmation and
borehole-duration requirements below only for these established devices. It
changes no fertilizer, Eskom, A-camp or uncommissioned-device authority.

## Physical Water System

The confirmed high-level water path is:

1. Roof rainwater and the borehole feed five storage tanks of approximately 5,500 litres each.
2. An independent solar transfer pump moves water from those storage tanks to twelve reservoir tanks of approximately 5,500 litres each.
3. The reservoir supplies downstream farm demand and irrigation.
4. Reservoir overflow returns to the storage side, reducing avoidable water loss.

### Borehole

- Borehole 1 uses eWeLink device `1002851416`, display name
  `Boorgat 1 Krag Toevoer`, a SONOFF MINI R4 sole output represented as logical
  channel 1, with exact IFTTT events `borehole_1_on` and `borehole_1_off`. It is a
  distinct typed device and authority domain; B/C irrigation or fertilizer
  commissioning never grants borehole authority.
- Power restoration must be OFF. Four hours is the governance ceiling, not a
  claim about current native configuration. Every supply window is bounded by
  the shorter, exact native fail-stop proven in its current canonical baseline
  and provider readback. The earlier statement that four-hour inching was
  already installed was not verified by the 29 October provider snapshot.
  Under the
  owner's standing authority, fresh authoritative provider/app OFF -> ON -> OFF
  is sufficient commissioning and operational proof; routine physical presence,
  preview and confirmation are not required.
- Every governed actuation still requires the exact canonical binding, fresh
  provider state, explicit applicable owner/standing authority, bounded native
  shutdown, power-restoration-safe state and provider outcome verification.
  Missing evidence fails the protected action
  closed.
- The borehole may operate at night; there is no owner-reported noise-hour restriction.
- The pump/controller has its own internal protection and storage-full cutoff.
- If the storage tanks are full, the internal controller can stop pumping even while the smart plug remains energized.
- ROOTLINE may report the exact governed power cycle from provider ON/OFF, but
  may not infer pumped volume or storage fill merely because the smart plug was ON.
- The approximately 1.2 kW inverter load is supporting evidence only and never
  a gate or stop condition.
- Once separately commissioned and enabled, Borehole 1 is normally supplied
  throughout the day and night through supervised bounded windows. Solar,
  then battery, then grid support water availability. Forecast rain or a full
  tank observation alone does not cancel this supply programme: the installed
  full-tank cutoff controls pumping. Fresh low-energy or explicit unsafe/isolation
  evidence still stops or prevents the affected window.
- The internal full-tank cutoff means an energized overnight window is not itself proof of needless pumping, but ROOTLINE must verify actual outcome rather than equating plug state with water movement.

Installed pump protections and current observations are different evidence.
The installed profile must resolve to canonical evidence with exact source,
identity, timestamp and digest, device binding and manual-isolation proof.
The owner confirms automatic dry-run shutdown, storage-full cutoff and manual
OFF/isolation. Confirmed dry-run shutdown governs source-water absence; no
additional positive pressure reading, flow-meter gate or unreported protection
subtype is required for this installed profile. Missing water/pressure
measurements remain Unknown, not a current all-clear. Explicit unsafe facts
persist until a later attributable correction; omission, stale positive
readings or out-of-order ingestion cannot clear them. Normal full-tank cutoff
is expected, while a cutoff fault is unsafe. Do not request daily synthetic
tank, pressure or dry-run confirmations when the installed profile governs.

### Eskom supply policy

The owner's continuous borehole/grid programme uses fresh battery SOC of 30%
or below to request Eskom ON. Eskom OFF requires SOC at least 35% and solar
actually charging/recovering the battery; grid-only charging cannot authorize
OFF. Between these boundaries retain the current breaker state. Unknown,
conflicting or stale power/charging direction cannot authorize a transition.
These thresholds supersede the general discretionary reserve only for this
continuous-supply programme. Mixer reserve remains separately protected.

The exact SmartLife `Eskom Grid` device and switch DP are private configuration,
not source constants. IFTTT `eskom_grid_on`/`eskom_grid_off` must be paired with
authenticated exact-device Tuya online/switch readback and canonical standing
commissioning. Grid watts are not a breaker-state substitute. Consume a durable
transition and dispatch reservation before sending; serialize the final fresh
decision, command and saved outcome; reconcile only a post-sender readback.
An interrupted sender without durable outcome cannot resend automatically.
Absent API entitlement, mapping or commissioning blocks Eskom only, not gravity B/C.

This grid-support breaker uses the exact `smartlife_eskom_hysteresis_v1`
profile: retain state (`UNCHANGED`) when a fresh transition is not authorized;
zero maximum/native countdown fields explicitly mean no countdown. An unrelated
valve timer must not disconnect required grid support before solar recovery.
The canonical profile instead requires independently proven electrical
protection and manual isolation, with current canonical evidence references,
exact physical identity and unrevoked standing policy. This exception belongs
only to the named 30/35 grid programme; pumps, valves and other breakers retain
their existing native fail-stop requirements. No electrical proof is inferred
from a Boolean switch response or an ON/OFF applet.

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
- Conserve discretionary battery/grid use. The separately commissioned,
  normally-on borehole supply follows the 30/35 policy above; forecast rain or
  adequate storage alone must not suppress its supply availability.
- When both storage and reservoir are low, water wins: ROOTLINE may recommend governed overnight grid-backed pumping even when battery energy is low.

Current owner-confirmed energy boundaries:

- approximately 40% SOC is the absolute floor ROOTLINE should not intentionally cross for discretionary pumping;
- the inverter/grid fallback begins at approximately 30%;
- approximately 50% is the provisional normal working reserve;
- ROOTLINE may recommend a higher dynamic reserve from forecast confidence and learned consumption;
- the current poor/uncertain evidence policy may govern at 70%;
- prepaid grid energy is approximately R9/kWh and historically about R2,000 per month, but billing-grade reconciliation is still required.

Present solar production alone is not sufficient reason to reduce the governing
reserve. Fresh net solar headroom may support a bounded mixer opportunity without
spending battery reserve; the active mixer checks current load without counting
its own load twice. Loss of sufficient power stops the current mixing window.

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
- A nominal two-hour parent uses two 3,599-second bounded segments (7,198
  seconds), not a third two-second run. Credit the full daily objective only
  after both segments are complete. Fresh verified segment-one OFF permits
  reassessment of the remainder; a new wet/not-needed decision can still hold it.
- ROOTLINE must produce a fresh plan for each operating day from crop/season need, recent completed irrigation, soil or other available need evidence, storage/reservoir evidence, and observed and forecast weather. B/C valve actuation is gravity-fed and must not be delayed, held, scored down, or made `Needs Data` because of battery SOC, solar, load, grid state, forecast-derived reserve, or stale power telemetry. Power may be reported as wider farm context, but it is not a B/C irrigation eligibility or timing gate.
- Under the current envelope ROOTLINE may run B only, C only, or both sequentially; it may shorten a run, move it, or hold it. Concurrent B/C is a future expansion requiring separate hydraulic/electrical commissioning, exact owner authorization, reviewed implementation and explicit activation; it does not inherit current B/C standing authority. The plan must state what will run, when, for how long, why, and when it will reassess.
- Under the 2026-10-31 owner direction, commissioned B/C gravity-fed drip irrigation is eligible throughout all 24 hours when current need, weather and safety evidence support it. Summer daylight or a fixed 22:00 start must not defer an otherwise eligible segment. Fresh weather evidence, rain holds, proven dry release, weekly delivery debt, sequential valves, native backup shutoffs and exact execution authority remain required; this timing policy does not enable an uncommissioned zone.
- Frequency and nominal two-hour duration are agronomic starting targets, not authority to under-water, over-water, or invent crop/soil evidence. Material deviations require an evidence-backed reason and must preserve the weekly delivery objective or schedule recovery.
- Weekly day debt is not identical to crop-water deficit. Fresh observed effective rainfall
  may proportionally reduce, satisfy or defer a zone obligation through the versioned
  water-balance contract in `docs/06-operations/ROOTLINE_EFFECTIVE_RAINFALL_WATER_BALANCE_PLAN.md`.
  Forecast rain receives zero delivered-water credit. Until that contract is operational,
  rain may Hold/reassess irrigation but must not silently erase or manufacture debt.

### Water-credit lifecycle

- Canonical completed runtime, provider ON/OFF receipts and an authenticated
  normal-flow observation remain separate evidence. None independently proves
  delivered litres.
- A delivered-volume credit is append-only and binds one immutable ROOTLINE
  execution identity to the accepted physical-evidence digest and either a
  verified volume measurement or a governed, zone-specific calibration record.
- Runtime-derived or owner-confirmed flow without measurement/calibration keeps
  delivered volume `Unknown`. It may prove execution and physical outcome, but
  it must not manufacture litres.
- One execution may receive at most one exact credit. Exact replay is a no-op;
  changed volume, evidence, calibration or zone is a conflict and must fail
  closed without rewriting irrigation history, schedule debt or earlier credit.
- Supabase `irrigation_water_credit_events` is canonical. n8n and Google Sheets
  have no credit, accounting or policy authority.
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
- Owner decision 2026-08-24: for the governed Fertilizer mixer, Fertilizer
  injector and Borehole controller, fresh authoritative application/provider
  ON then OFF readback is sufficient operational start/stop proof. Routine
  owner physical presence, observation or per-run confirmation is not required;
  ROOTLINE holds standing authority for exact registered devices inside current
  eligibility and bounded fail-stop/interlock contracts; Charl and Anton will
  report exceptions. This does not make a command receipt sufficient, prove
  fertilizer or water moved, or waive exact device binding, current need,
  interlocks, idempotency, replay protection, deterministic maximum-runtime
  OFF, final verified OFF, or canonical lifecycle readback. Mixer remains bound
  to the commissioned CH2 1,800-second fail-stop and may be split only by a
  current governed plan. Injector remains bound to
  exactly one active irrigation zone, at least ten minutes pre-flow, at most
  120 seconds injection and at least ten minutes clean-water flush. Borehole
  may not be commanded until exact device/provider binding and bounded
  fail-OFF are proven.
- A bounded run records one authorized execution identity, its maximum runtime, backup-stop deadline, primary stop attempt, every safe repeated `OFF`, observed outcome, and final containment state.
- Failure to arm the independent fail-stop blocks `ON`. Failure to verify shutdown after the fail-stop creates one urgent hardware exception and keeps the zone unavailable for autonomous reuse.

For B/C autonomy, the owner-approved standing operating envelope is deliberately narrow: proven B and C irrigation valves only; no fertilizer or borehole actuation; no concurrent B/C run; each native fail-stop segment is at most 3,599 seconds; a nominal two-hour objective requires two distinct segments with verified shutdown and a fresh canonical decision before segment two. Source defaults fail closed and require the exact runtime authority flag to be explicitly enabled during a separately assigned production window. This documentation audit did not read production configuration and does not establish the current deployed flag value; it authorizes no enabling. When separately proven enabled, ROOTLINE may execute eligible B/C segments within this envelope without routine per-run permission. A genuine boundary exception, same-zone same-day duplicate, uncertain shutdown, unavailable fail-stop, conflicting evidence or proposed expansion requires containment and owner attention.

Oom Sakkie maintains the daily irrigation plan canonically. A routine plan or
automatic reassessment with no owner decision and no material execution event
is silent on Telegram. Its lifecycle is:

- `Planned`: zones, intended window/runtime, reason, evidence cutoff, and next reassessment;
- `Active`: exact zone(s), verified start time, and expected stop/reassessment;
- `Hold`: reason, affected zone(s), and next trigger;
- `Stopped`: stopped early or contained, with reason and remaining work;
- `Completed`: verified stop, delivered runtime/outcome evidence, deviations, and next expected irrigation.

The daily card should be edited for low-attention plan changes. Because edits do not reliably notify Charl, each actual hardware start and completion/stop must also produce one new, concise, human-friendly buttonless operational notification following `../07-standards/OOM_SAKKIE_TELEGRAM_MESSAGE_STANDARD.md`. After confirmed completion, a superseded temporary start notification may be deleted for presentation cleanup while the daily card and durable audit evidence remain. A command/provider receipt alone must not mark `Active` or `Completed`; physical or authoritative device outcome evidence is required. Buttons are reserved for genuine protected exceptions or authority decisions.

Unchanged and no-action automatic reassessments are silent. ROOTLINE sends no
periodic plan card merely because a timer fired. One unchanged missing fact is
requested once and remains pending until answered, superseded, or no longer
material. A new visible message is reserved for hardware start, verified
stop/completion, failure, or one exact owner decision. Internal state/reason
tokens, SOC, load, forecast provenance, scores, identities and evidence gaps
remain in canonical evidence or on-request diagnostics, never routine family
output.

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

The fertilizer injection and mixing valves use the governed exact provider
bindings and canonical device baseline. ROOTLINE chooses execution from that
day's prepared fertilizer batch, irrigation plan, fertilizer need, required
pre-flow/flush, weather and energy. If energy is poor, non-urgent mixing may be
deferred and recovered at a better window. Relay state proves the bounded
electrical execution outcome, not fertilizer movement or concentration.

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
- the planner may split that daily Mixer allowance into bounded sessions, but
  each execution must use the task's exact remaining `planned_seconds` and may
  never silently expand a short remainder to the 1,800-second native limit;
- Injector `Run now` exists only while one exact B/C execution is actively ON,
  current fertilizer need is explicit, ten-minute clean-water pre-flow is
  proven, and enough remaining segment time exists for the pulse and flush;
- the stated injection-duration evidence conflicts: 60 seconds was supplied as a maximum while the owner also indicated longer than 60 seconds may be preferable.

The historical app used two-minute injection windows. Current pulse timing is
the owner-approved bounded programme below, not replay of legacy clock schedules.
Absent flow or concentration evidence does not block its controller sequence.

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
- mixing has an independent daily target and ceiling of 30 minutes, split into
  suitable energy opportunities. Premixing counts toward the same total;
- the same prepared batch's qualified mixing earlier that day may support
  injection. Do not require another five-minute mix before every segment or
  exceed the daily ceiling after the target has already been met;
- channel 2 requires its independently verified native 1,800-second fail-stop
  before autonomous use; routine opportunities may use smaller 600-second
  windows. Durable reserved/completed controller time, including premix,
  shares the 1,800-second SAST-day ceiling. Count uncertain/interrupted
  reservations conservatively; never refund unknown time into endless retries;
- the mixer/pump path is treated as an approximately 1 kW material load until measured;
- B/C gravity-fed irrigation remains independent of farm energy state, while fertilizer
  mixing may be optimized against energy evidence;
- injection cannot run unless exactly one eligible irrigation zone is already active and
  clean-water pre-flow is proven;
- mixing and injection remain outside standing autonomy until each channel receives exact
  provider readback, typed auxiliary-device registration, independent supervised physical
  commissioning, native fail-stop proof, deterministic OFF, replay proof and separate
  activation authority.

The standing programme below establishes the intended B/C frequency. It does
not establish nutrient dose, concentration or agronomic benefit.

The initial owner fertilizer programme is to inject during every eligible B or C irrigation
run because the farm is rebuilding the soil. This establishes intended frequency, but it
does not prove dose or concentration. ROOTLINE tracks the weekly prepared batch,
same-batch mixing, subsequent pulses and refill/dilution. A real prepared-batch
record is required; empty, unsafe and not-ready reports suspend fertilizer.
Authenticated owner intake supports `Fertilizer batch prepared`, `Fertilizer
batch empty`, `Fertilizer batch unsafe` and `Fertilizer batch not ready`; replay
preserves the original observation time. No daily fertilizer-needed prompt is
required. A missing batch produces one fertilizer-specific gap while water-only
irrigation remains possible.

Exact ON/OFF readbacks, two bounded 120-second controller pulses, the spacing,
preflow and final flush establish controller-sequence completion. A flow sensor,
batch recipe, concentration or measured volume is not a prerequisite for that
control programme. Never describe controller completion as verified flow,
litres delivered, nutrient dose or soil benefit.

## Independent device operation and irrigation handover

Only irrigation valves must remain sequential across all commissioned zones.
Mixer, fertilizer injector, borehole and Eskom may operate together when each
has its own current authority and safety proof. Mixing is not an injector OFF
prerequisite and borehole operation does not reserve the mixer's operating time.
Injection still requires one actual active irrigation parent, proven preflow,
the same-batch premix, bounded pulses, spacing, verified shutdown and final flush.
Loss of the parent dependency stops the injector without abandoning other duties.

Control runs on the authenticated minute cadence independently of reports.
After verified segment OFF, prefer the eligible remaining parent segment over
a new camp's job. Reassess immediately or on the next minute tick; do not wait
for a report. A segment ending on either side of midnight retains the same
bounded 30-minute continuation opportunity, without creating irrigation credit
or bypassing fresh need, weather, containment or authority checks. Uncommissioned
or disabled zones remain ineligible; A requires its own stated gates and E remains held.

## Future SmartLife, SONOFF, And IFTTT Setup

Future setup should create consistent ON and OFF functions for intended channels, including currently unused channels when useful for later installation.

An unused channel must be recorded as:

- configured but physically unconnected;
- disabled for ROOTLINE runtime use;
- safe default OFF;
- no assumed equipment, flow, energy, or farm effect.

Creating an IFTTT function does not prove a physical device mapping and does not grant ROOTLINE actuation authority. A commissioned mapping likewise does not grant another device class authority or prove a specific farm outcome.

A camp is irrigation controller channel 4 and E camp channel 3. Their paired
events are `irrigation_1_ch4_on/off` and `irrigation_1_ch3_on/off` respectively.
The owner's 2026-10-31 readiness statement resolves A's pipework prerequisite;
it does not prove commissioning or activation. A/B/C are drip irrigation and
may be assessed throughout all 24 hours against current need and weather.
A's exact CH4 physical identity, offline/native fail-stop, restoration OFF,
manual isolation, commissioning generation, canonical authority and separate
`ROOTLINE_A_ENABLED` flag remain independent prerequisites. E remains
plumbing-not-ready, uncommissioned and inactive.

A uses its own explicit operating-policy successor. Its useful minimum,
maximum segment and requested total runtime, need-based or weekly target,
and supported supply class must come from attributable owner/canonical
knowledge. The B/C two-hour/four-day target and fertilizer programme do not
transfer to A. A stricter current A total or segment limit holds incompatible
new work from an existing parent without rewriting its history. A remaining
segment that still fits the current limits may continue after fresh validation. Missing crop or flow calibration prevents dependent agronomic
or volume claims; it need not block a separately proven controller objective.
The implemented supply profile admits proven gravity-fed A only; unknown or
unsupported supply remains a dependent hold.

A shares the existing mutually exclusive irrigation coordinator and history.
Segments remain bounded by the native 3,599-second backup with independent
primary OFF; a shorter own target requires exact fresh ON/OFF and its original
primary deadline before controller completion. Rain or unproven active weather
stops A using the same sticky stop barrier and PARTIAL accounting as B/C.
Unmet need remains recorded; no stopped or controller-only interval invents
water volume. A need-based history epoch begins at its actual canonical
commissioning cutoff, never a fabricated week-start absence. The existing
measured-water-credit schema and B/C history stay unchanged. These source
rules do not create a device record, policy, authority or live enablement.

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

### Standing water-availability policy for ordinary B/C irrigation

Inside the already commissioned B/C envelope, absence or staleness of a tank-count
observation is not evidence of insufficient supply and must not independently create a
question or execution Hold. ROOTLINE assumes water is available unless Charl reports an
insufficient supply or fresh canonical evidence proves a dry supply, supply fault or
conflict. Any such current adverse evidence remains fail-closed. Storage is planned as
requiring replenishment by default unless credible current evidence says otherwise.

This assumption creates neither litres nor millimetres, does not create water credit, and
does not authorize Borehole 1. Borehole actuation still requires its own commissioned
provider identity, fail-OFF contract, conflict isolation and resolved installed
protections. Provider ON/OFF proves the governed supply cycle; it does not prove
physical pump operation or water movement.

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
not actuation authority. Completion requires the device-specific verification
defined above; control completion and physical delivery remain distinct.


## Owner irrigation controls approved 25 November 2026

Charl approved the irrigation-page concept and its full implementation and release.
The authenticated owner may inspect the three-day forecast, all eight registered
inputs, the saved daily programme, camp summaries and recorded run/change history.
The page is a channel into the existing ROOTLINE operational intake, planner and
executor. It does not introduce a second scheduler or browser-to-device transport.

A reviewed Save records the authenticated owner, exact settings or plan revision,
reason, scope and idempotent request identity. Ongoing settings remain effective
until replaced. Today-only settings expire at the next Africa/Johannesburg midnight.
Confirmed settings are consumed by the automatic controller without requiring chat.
Editable limits must be populated from the actual runtime policy and validated by
the same consumer; unsupported limits remain explicitly read-only.

The owner may adjust future camp durations, unstarted daily-plan order, duration,
priority, reason and skip choices, and supported energy thresholds. A day-plan edit
must reach the actual scheduled order and eligibility checks. Already accepted ON
claims retain their original OFF obligations; editing a plan cannot extend or erase
a current duty, count unperformed work as complete, or reset consumed daily work.

One-off run and stop requests enter the same durable claims, locks, device identity
and shutdown supervision as unattended operation. A request is not itself command
acceptance. A request that is already satisfied must close without a later duplicate
effect. Newer owner restrictions and request expiry are rechecked at the command
edge. Resume clears the owner's pause only, never a separate isolation/fault hold.

Eskom pause retains the current supply state. Explicit one-off grid ON requires
fresh power evidence; grid OFF retains the existing battery and solar-recovery
conditions. Confirmed owner threshold changes supplement the registered baseline
policy without changing the commissioned device identity or protections. Existing
thresholds remain the defaults until the owner saves a change.

These controls preserve command-accepted operation and truthful controller-time
accounting. They add no water-volume or physical-mixing measurement prerequisite.
Publishing the page does not prove the pending nightly forecast, injection or
repeated unattended cycles; those outcomes require their genuine runtime evidence.


## Owner-approved balanced Telegram reporting — 25 November 2026

ROOTLINE uses the existing Oom Sakkie delivery rail for a concise daily plan,
material run changes, camp results and actionable exceptions. Use clear emojis,
local event times, the affected input, a plain reason and the next automatic step.
Link to the irrigation page for settings, full plan, receipts and history.
A completed segment or accepted OFF must never label an unfinished programme
complete. Command-mode notices describe accepted commands without repeating
physical-water/mixing disclaimers; they do not claim measured water or dose.
Borehole AC-backup switching remains distinct from independent solar pumping.

Keep brief sensor-reading gaps in history. The first notice may wait five minutes
only when canonical evidence proves no active or pending work is affected;
unknown impact, command failures and shutdown uncertainty remain immediate.
A recovery notice requires a previously delivered outage notice. Preserve stable
identities, replay silence, immutable attempted content and ambiguous-send holds.
Routine high-battery notices are quiet under ROOTLINE input-health ownership;
low-battery, grid and other operational warnings retain their existing policy.
Remove routine optional tank questions from summaries while preserving genuinely
required owner decisions. These presentation changes do not alter control limits,
forecast schedules, command authority, original OFF duties or operating policy.

## Owner-directed camp controller confirmation — 27 November 2026

An accepted camp ON request immediately owns its original bounded OFF duty, but
remains Requested until the existing Home Assistant MQTT subscription reports ON
for the exact registered controller channel after that command attempt. Use the
original non-retained subscription report timestamp and validated topic/payload;
API retrieval time, entity change time, retained replay and service acceptance do
not establish this confirmation. A confirmed report remains valid until a later
contradictory report; unchanged state or missing optional reports do not create a
continuous freshness prerequisite. A later OFF report interrupts the camp through
the existing serialized, bounded OFF recovery. Pending or contradicted camps,
including legacy accepted-only duties, cannot authorize injection or receive
successful programme credit. Never retry ON or extend the original stop deadline.
Owner messages and the application distinguish Requested, Running and Interrupted.
This is controller-report evidence, not water or dose measurement. Mixer and
auxiliary timing/dispatch are unchanged by this bounded camp repair.
Historical receipt intervals remain visible as unconfirmed command time only;
they grant no running/completion credit or injector authority. Preserve their
existing notification identities rather than replaying old results as new alerts.
