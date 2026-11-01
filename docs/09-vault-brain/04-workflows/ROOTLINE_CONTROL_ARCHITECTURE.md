# ROOTLINE Control Architecture

> **Current status semantics:** the historical Daily Brief route is a bounded
> read-only projection, not an operating ROOTLINE agent. Continuous operation
> requires durable evidence-change/due-time triggers, a supervised worker,
> maintained current plan, outcome/reassessment ownership and terminal-close
> continuity as defined by ROOTLINE's Continuous Operating Contract.

Status: authoritative control architecture and authority boundary.

Evidence cut: `2026-07-25`, repository revision
[`6123c1e`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/6123c1e54134ccde5b3cc14d607d12ccaecc020d).

This document defines ROOTLINE's durable operating model. Dated evidence below
is historical context only. Current policy comes from this architecture and
`../08-business-rules/ROOTLINE_WATER_ENERGY_RULES.md`; current operational state
requires the mission register plus fresh canonical, provider and physical
readback. This document grants no hardware authority.

## Device-Class Graduation And Execution

Each device class graduates independently through typed registry identity,
exact provider/account/device/channel binding, safe OFF and restoration state,
native fail-stop, dependency/interlock proof, supervised physical
commissioning, canonical authority and separately reviewed activation. A B/C
valve proof cannot commission A, fertiliser or borehole equipment.

A CH4 uses the existing device/evidence/authority spine with its own proof and
separate enablement. The compatible A/B/C operating-policy successor retains
legacy B/C policies and supplies explicit A runtime, need and supply inputs;
missing A inputs block only dependent A actions. A shares the existing global
irrigation claim lock, current rain-stop, parent history and safe OFF recovery.
A revoked or unavailable new-start authority must not abandon an already
recorded exact-channel shutdown duty. E CH3 remains inadmissible. Neither this
source capability nor a migrated history writer establishes live activation.

Every execution must bind the current plan generation, commissioning and
authority identity/version, exact device/channel, evidence cutoff, maximum
runtime and idempotency key before ON. ON is attempted once. Ambiguity causes
containment, never automatic ON retry. OFF is exact-channel and safely
repeatable only inside bounded recovery until authoritative shutdown is proven.
Completion requires the device-specific evidence defined by the focused Water
And Energy Rules. Governed supply/pulse controller completion uses exact fresh
ON/OFF readbacks; physical flow and volume remain separate and may be Unknown. An
energized relay or accepted request is never enough.

A failed borehole startup may retire as Aborted only after the canonical claim
and consumed OFF barrier are bound to a fresh exact provider OFF read under the
same locks that serialize ON and OFF dispatch. An old containment summary cannot
release it. OFF reservations remain consumed across crashes; delayed commands
must refuse after retirement. The failed execution and its consumption identity
remain recorded, without completion or water-delivery credit. Later eligible
work requires a fresh assessment and execution identity.

Routine B/C work may use only the explicitly enabled standing envelope in the
Water And Energy Rules. Fertiliser mixer, injection and borehole remain
independent protected profiles until their own commissioning and activation
proof exists. A terminal may repair, test, deploy and observe these rails but
must never substitute for the deployed ROOTLINE actor or physical outcome.

## Shared eWeLink demand and availability

Existing provider-independent eligibility runs before optional device reads.
Every required proof still uses the fresh authenticated ownership, inventory and
status GETs; no positive evidence cache may satisfy command, active-injector,
abort, final-flush or shutdown obligations. Reassess original evidence at the
post-read clock, and check claim/primary deadlines again at the actual ON edge.

All participating read/OAuth callers share the existing append-only review-event
rail. Conservatively charge possible attempts before dispatch, including failed
and ambiguous requests, with a local 40,000-attempt rolling 31-day cap per app and
region. Apply a separate global one-second completed-request pace and 250-attempt
rolling five-minute ceiling. Holds are app-wide across token/region changes.
A transaction-held sender fence must remain compatible with transaction pooling;
it cannot guarantee fencing of unrelated clients or traffic outside this rail.

JSON provider error 412 permits one due full probe per hour. Transient failures
back off 1/5/15/60 minutes, with bounded Retry-After. Genuine token expiry may
rotate within that same probe; failure itself cannot trigger refresh. Only a
complete bound normalized snapshot restores availability. Locally counted usage
starts at its recorded coverage epoch; prior/provider usage, entitlement,
remaining balance and external-client coverage remain Unknown. Unknown balance
alone creates neither a permanent owner gate nor a 31-day start embargo.

Reserve active proof capacity before canonical execution claim. Other callers
cannot spend it; attempted/unresolved reserves require fresh exact OFF before
release. Before request admission, discard only expired never-attempted reserves.
A missed OFF cleanup may release accounting capacity from the exact original
canonical claim, permit and originally fresh terminal OFF proof, with bounded
chronology, identity and contradiction checks. This never refreshes present
device truth or alters physical/business completion; unresolved and ambiguous
duties remain reserved, and later separate executions retain their own reserve.
Exhausted attempted duties may replenish one four-attempt proof group
hourly within the same limits, preserving the obligation and never reviving ON.
A proven unsent claim may retire only from its exact canonical claim/outcome and
fresh locked OFF proof; preserve history, and never refund an uncertain ON.

Optional mixer readiness collection and its separate fresh manager refresh each
admit at most one full observation per 30 minutes across participating workers.
Normal suppression records zero sends and its next eligibility; the existing
manager cadence waits without manufacturing an owner exception. It reuses no
positive snapshot. Mandatory execution/safety reads retain their own admission.
IFTTT OFF and native fail-stop never wait for quota, a probe or budget persistence;
unverifiable shutdown stays Unknown and unavailable for reuse.

## Business Outcome

ROOTLINE is the farm's eventual water, irrigation, weather, power, and
infrastructure operator. Its end goal is to plan, safely execute, verify, and
adapt the routine majority of irrigation and associated water/power
coordination within owner-approved limits. It is not merely a dashboard or
weather reporter.

At maturity ROOTLINE should:

- create and revise daily irrigation plans;
- control approved physical irrigation valves;
- pause, skip, resume, and reprioritize zones;
- coordinate pumps and borehole windows with power and tank evidence;
- respond to rain, wind, and weather forecasts;
- respect owner/farm-team instructions and manual exclusions;
- verify execution independently from command delivery;
- retain a complete, append-only audit trail; and
- interrupt the owner only for exceptions, uncertainty, consequential
  decisions, and actions outside delegated authority.

## Current Truth

| Capability | Current evidence | State and limitation |
| --- | --- | --- |
| Production ROOTLINE | Existing telemetry/read-model services | Read-only telemetry and prepared summaries; no hardware authority. |
| Irrigation status | Backend status endpoint and workflow `2.3.3` | Read-only. It cannot start, stop, pause, resume, or alter a plan. |
| Phase A Daily Brief | PR [#464](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/464), merge [`187e07f`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/187e07fb9f531549d35b04824ec9149875fabb85) | Built, merged, deployed, and owner-route operational as Level 1 read-only advice. One controlled owner-authenticated GET returned structured HTTP 200 evidence. Deterministic flags prohibit writes, alerts, Telegram, schedules, IFTTT, and hardware control. |
| Latest bounded evidence audit | Controlled owner-only Daily Brief read, `2026-07-25` | Telemetry evidence was partial. Tank, pump, and borehole evidence were unavailable; forecast was stale; power was suspicious/unverified because battery, solar, and load all reported zero. Two planned zones returned `review`; no zone received `proceed`. None is proof of a safe or normal condition. |
| Legacy controller | Imported workflow `2.3.2` | Inactive. It contains IFTTT ON/OFF calls and must not be casually activated or used as a shortcut to control authority. |
| Hardware control | No separately approved live proof | Not operational and not authorized. |

Code in a repository is not deployment evidence. Deployment is not
configuration proof. Configuration is not proof that a valve moved. A
successful canary is not general autonomous authority.

## Terminology And Existing Hardware Bridge

The current legacy bridge is **IFTTT** (If This Then That), not FTP or FTTP.
The imported
[`2.3.2` controller](../../04-n8n/workflows/2.3.2%20-%20Run%20Irrigation%20Controller/README.md)
can call zone-specific IFTTT ON/OFF webhook events. Its export is inactive and
contains credential material that must be removed from workflow logic before
any future use; this document intentionally does not reproduce it.

n8n and IFTTT are not the decision-making source of truth. Backend/Supabase
must own validation, commands, locks, safety policy, idempotency, audit,
verification, and recovery. IFTTT—or a future adapter—may remain only a thin
actuator bridge.

The registered irrigation and fertilizer controllers and Borehole 1 use eWeLink;
the separately configured Eskom breaker uses SmartLife/Tuya. Exact device/channel
and commissioning evidence is required for each; no platform-wide inheritance.
Do not infer Home Assistant, Sonoff, Tuya, Shelly, ESP hardware, or any other
platform without authoritative inventory evidence.

## Staged Authority

| Level | Authority | Required graduation evidence |
| --- | --- | --- |
| **Level 1 — Observe and advise** | Read approved evidence; produce briefs and recommendations; zero hardware authority. | Canonical source inventory; provenance/freshness handling; safe Unknown/Unavailable behavior; multi-day read-only replay; no-write/no-dispatch proof; owner acceptance of summaries. |
| **Level 2 — Owner-approved control** | Prepare one exact action; bind exact owner approval; execute once; verify and audit the outcome. No automatic retry after an ambiguous result. | Level 1 accepted; hardware/topology inventory confirmed; deterministic command ledger/state machine; stable command identity; permissions and interlocks tested; simulation passed; kill switch proven; one limited owner-approved physical canary with independent state/flow verification and recovery evidence. |
| **Level 3 — Bounded autonomous control** | Execute approved routine irrigation within explicit limits; adapt priorities inside policy; escalate exceptions only; preserve immediate kill switch/manual override. | Level 2 canaries across representative conditions; physical-state and available flow verification; pause/resume/replan proof; stuck valve, connectivity, telemetry-stale, restart, power-failure, manual-override, and emergency-stop drills; measured exception/false-success rates; approved zones/windows/runtime/simultaneity policy; owner approval of the exact autonomy envelope and rollback. |

Graduation is a separately approved decision. Built, merged, deployed,
configured, operationally proven, and autonomous-authority-enabled are six
distinct states and must be reported separately for every level and phase.

## Command State Machine

Each command has one stable identity, target zone/valve, requested action,
policy version, evidence snapshot, authority level, actor/approval identity
where required, and idempotency key.

```text
planned
  -> approved                    (Level 2 or policy-required Level 3 action)
  -> command_claimed
  -> command_dispatched
  -> actuator_acknowledged
  -> physical_state_confirmed
  -> water_flow_confirmed        (when independent sensors exist)
  -> completed
```

Valid terminal or interrupting states include:

- `paused`
- `skipped`
- `failed`
- `ambiguous`
- `manually_overridden`
- `emergency_stopped`

Rules:

- HTTP 200 or IFTTT acceptance proves only transport acceptance, not valve
  movement.
- Valve-state evidence does not automatically prove water flowed.
- If flow sensors do not exist, `water_flow_confirmed` remains Unavailable; the
  system must not fabricate it or silently equate valve state with flow.
- An ambiguous command must not be automatically retried.
- Claiming the same command identity must be idempotent.
- Recovery must reconcile physical valve, pump, and available flow state before
  issuing another action.
- `completed` requires the verification evidence defined for that hardware
  inventory and authority level.
- Manual override and emergency stop outrank scheduled or autonomous work.

## Safety Evidence And Interlocks

Hardware control must fail closed when any required evidence is unknown, stale,
missing, unavailable, or conflicting. Those conditions remain
`Unknown`/`Unavailable`; they are never interpreted as safe, zero, off, or
completed.

Required future controls and evidence:

| Area | Required contract |
| --- | --- |
| Topology | Canonical valve-to-zone mapping, crop/camp relationship, switching hardware, pump dependency, tank source, borehole dependency. |
| Water readiness | Tank level, borehole readiness, pump state, flow/pressure where available, stuck-open/stuck-closed detection. |
| Power | Current Sunsynk condition, freshness, load/battery/grid constraints, restart/power-failure recovery. Suspicious all-zero evidence is not normal. |
| Weather | Current rain/wind evidence, forecast freshness, approved thresholds, and explicit stale/unavailable handling. |
| Operating envelope | Allowed windows, maximum runtime, minimum switch interval/cooldown, simultaneous-zone limit, missed-irrigation policy. |
| Process interlocks | Fertilizer/injection state, mixing/flushing requirements, maintenance locks, manual exclusions and isolation. |
| Containment | Connectivity-failure behavior, command timeout, immediate kill switch, manual override, emergency stop, restart reconciliation. |

No control action may depend on a guessed default for a safety-critical field.
Safe defaults may only make control more restrictive and must be explicit in
the approved policy.

## Agentic And Deterministic Boundary

ROOTLINE's agentic reasoning may:

- interpret owner instructions;
- explain conditions and uncertainty;
- compare safe options;
- propose schedules;
- adapt routine priorities within approved policy; and
- communicate concise summaries and exceptions.

Deterministic backend controls own:

- command and target identity;
- permissions and authority-level enforcement;
- safety limits and evidence freshness;
- validation;
- locks and concurrency;
- cooldowns;
- idempotency;
- actuator dispatch;
- outcome verification;
- append-only audit; and
- emergency containment.

ROOTLINE is agentic in planning, explanation, and bounded adaptation. Hardware
execution is governed and deterministic. An LLM may never directly call a
valve webhook, grant its own authority, mark an action complete, weaken an
interlock, or decide that missing evidence is safe.

## System Relationships

| Participant | Responsibility |
| --- | --- |
| ROOTLINE | Domain operator and decision planner for water, irrigation, weather, power, and infrastructure. |
| Backend/Supabase | Canonical source of truth, command/audit rail, safety enforcement, locks, idempotency, and recovery. |
| n8n | Optional thin scheduler/integration/delivery layer; never the operational brain or safety-policy owner. |
| IFTTT/future adapter | Actuator bridge only; it does not decide whether an action is safe. |
| Oom Sakkie | Conversational owner interface and alert/approval surface; it presents ROOTLINE evidence but does not inherit hardware authority. |
| Weather and Sunsynk feeds | Evidence providers; freshness and quality must be evaluated before use. |
| Future crop specialist | Supplies crop/water-demand intent; cannot directly command valves. |
| Owner/farm team | Highest-priority instruction, exclusion, manual override, isolation, and emergency authority. |

## Owner Interruption Policy

Routine successful work should be grouped into concise operating summaries,
not sent as one Telegram message per command.

Immediate owner/farm-team escalation is reserved for:

- failed or ambiguous valve actions;
- unexpected or missing flow where flow evidence is required;
- pump, borehole, tank, or power risk;
- stale, unavailable, or conflicting safety evidence;
- repeated missed irrigation;
- conflict with a manual override or exclusion;
- equipment/connectivity failure;
- an action outside the approved autonomy envelope; or
- emergency stop.

Unknown evidence may block control without generating repeated notifications.
Use deduplication, severity, quiet-hours rules where safe, and one durable
exception identity.

## Hardware Inventory And Owner Decisions

The table below records the original discovery checklist, not a declaration that
the now-registered controllers are unknown. Exact current bindings are in the
typed registry and focused Water And Energy Rules; activation and outcome proof
are recorded in the current mission handover.

Every value below requires authoritative confirmation. Do not fill blanks by
inference.

| Inventory item | Required evidence | Current state |
| --- | --- | --- |
| Every physical valve | Stable hardware identity and physical inspection | Unknown |
| Canonical zone ID | Approved valve/zone registry | Unknown |
| Controlled crop/camp | Current crop/camp mapping | Unknown |
| Switching hardware | Make/model/interface and safe command contract | Unknown |
| Current IFTTT events | Verified ON/OFF event per valve without exposing keys | Known to exist in legacy source; exact inventory requires owner confirmation |
| Pump dependency | Valve/zone-to-pump dependency | Unknown |
| Maximum runtime | Approved per-zone and system limits | Unknown |
| Simultaneous operation | Electrical/hydraulic allowance | Unknown |
| Tank source | Canonical tank identity and level source | Unknown |
| Flow/pressure sensors | Sensor identity, placement, freshness, failure behavior | Unknown |
| Manual isolation | Physical/manual isolation procedure | Unknown |
| Failure-safe state | Expected state on power/network/controller failure | Unknown |
| Downstream platform behind IFTTT | Authoritative hardware/platform inventory | Unknown |

## Delivery Roadmap

## Borehole 1 MINI R4 intake boundary

Device `1002851416`, SONOFF MINI R4/UIID138, displayed as
`Boorgat 1 Krag Toevoer`, has one physical output (logical channel 1). Provider
switch placeholders do not create four physical channels. Its paired events are
`borehole_1_on` and `borehole_1_off`; event setup alone grants no authority.
Its commissioning contract must prove a bounded native fail-OFF,
power restoration OFF, timers/scenes/interlocks disabled, current provider OFF, no ON
retry and resolved installed protections. Authoritative provider ON then OFF
proves the governed supply cycle under the owner's current rules. It never
proves pumping or water delivery. Four hours is a ceiling; a shorter exact
validated native limit bounds every window and must not be extended.

## Integrated supervision and evidence ownership

The authenticated minute claim supervises active A/B/C, mixer, injector and
borehole duties before optional planning and reports. The same minute control
claim may admit eligible work independently of report cadence. After verified
OFF and fresh reassessment, a continuing irrigation parent has priority over
new irrigation work, in that pass or the next minute pass. An incomplete parent
may cross midnight only within the bounded handover period; weather, need,
containment, authority, OFF/rearm and remaining-runtime checks still apply.

All irrigation valves remain globally sequential. Mixer, injector, borehole
and Eskom may overlap under their own authority, power, safety and dependency
rules. Shared transaction locks serialize admission and command edges; each
device owns its own claim, deadline and containment. Every known active device
must receive supervision even when another device's evidence or provider fails.
An already-ON auxiliary sibling requires exact current canonical ownership and
native safety. Injection also requires its exact irrigation parent to remain ON.
Current weather and dry-clearance history must share one coherent cutoff and
observation identity; mismatched, stale, rainy or unhealthy evidence holds.

One canonical current decision feeds execution, the daily card and the
specialist response. A planned Hold cannot be promoted by a second advisory
override. A nominal two-hour B/C parent has two 3,599-second segments (7,198
bounded seconds), with fresh reassessment and verified OFF before segment two.
The first segment does not discharge the full parent/day obligation.

Status rendering preserves provider receipt timestamps and distinguishes them
from device-event time. A later OFF observation proves OFF at that observation;
it does not establish the exact stop instant or actual overrun. Keep the
historical record, but do not repeatedly escalate a resolved historical gap as
a current unsafe output. Unknown current shutdown remains an exception.

Mixer reservations, premix and completed controller intervals share the same
SAST-day 30-minute budget. Injection uses the active canonical zone, exact fresh
ON, two 120-second pulses and verified OFF, spacing and final flush. Pulse
control completion does not depend on a flow sensor or manufacture a dose.

Eskom uses the existing event rail and canonical device authority, fixed-host
signed Tuya GET readback and exact IFTTT events. Claims compare the latest
completed transition under lock; a durable dispatch reservation is single-use.
The final raw-power freshness check and provider send remain inside the
exclusive transition fence. Only a durable sender outcome and later readback
permit completion; an interrupted sender cannot automatically replay.

| Phase | Outcome and gate |
| ---: | --- |
| 1 | Read-only Daily Brief. Report built/merged/deployed/configured/operational separately; zero hardware authority. |
| 2 | Hardware and topology inventory accepted by owner/farm team. |
| 3 | Backend command ledger, stable identity, idempotency, locks, audit, and state machine. |
| 4 | Deterministic valve adapter with secrets removed from workflow logic. |
| 5 | Simulation/dry-run proof across safety, ambiguity, duplicate, failure, and recovery cases. |
| 6 | One exact owner-approved valve canary with kill switch ready. |
| 7 | Independent physical-state and available flow verification. |
| 8 | Pause, skip, resume, and replanning proof. |
| 9 | Emergency-stop, manual-override, restart, and power/connectivity recovery proof. |
| 10 | Limited-zone Level 3 canary inside an explicit autonomy envelope. |
| 11 | Gradual bounded autonomous rollout using measured exception and verification evidence. |

Every phase reports:

- built;
- merged;
- deployed;
- configured;
- operationally proven; and
- autonomous authority enabled.

## Reconciliation Record

The following table is the historical initial-delivery record. It does not
override the integrated contract above or establish current commissioning.

| Classification | Reconciliation |
| --- | --- |
| Existing truth retained | Backend/Supabase owns durable truth and rules; n8n stays thin; `2.3.3` is read-only; `2.3.2` is inactive; Phase A is advisory/no-I/O; alerts and automation triggers are separate. |
| Contradictions corrected | ROOTLINE's end goal is routine physical operation, not permanent dashboard-only advice. The hardware bridge is IFTTT, not FTP/FTTP. Transport acceptance, valve state, flow, and completion are separate evidence states. |
| Gaps made explicit | No command ledger/state machine, approved adapter, independent physical/flow proof, Level 2 canary, Level 3 envelope, or operational hardware authority is established by current evidence. |
| Unresolved owner/hardware facts | Complete valve/zone/topology inventory, downstream IFTTT platform, pumps, tanks, sensors, runtime and simultaneity limits, isolation, and failure-safe behavior remain Unknown. |
| Deferred reconciliation completed | After PR #464 merged, `ROOTLINE.md` was linked to this architecture, the implementation source map recorded the deployed Level 1 route, and the Vault changelog recorded bounded Phase A delivery evidence. The SAM outbound-delivery source-map domain remains separate and unchanged. |

## Source References

- [`ROOTLINE.md`](../02-agents/farm/ROOTLINE.md)
- [`TELEMETRY_DATA_MODEL.md`](../06-data/TELEMETRY_DATA_MODEL.md)
- [`SUPABASE_TELEMETRY_PLAN.md`](../../02-backend/SUPABASE_TELEMETRY_PLAN.md)
- [`2.3.1 — Build Daily Irrigation Plan`](../../04-n8n/workflows/2.3.1%20-%20Build%20Daily%20Irrigation%20Plan/README.md)
- [`2.3.2 — Run Irrigation Controller`](../../04-n8n/workflows/2.3.2%20-%20Run%20Irrigation%20Controller/README.md)
- [`2.3.3 — Irrigation Status Tool`](../../04-n8n/workflows/2.3.3%20-%20Irrigation%20Status%20Tool/README.md)
- [`Oom Sakkie identity`](../01-identity/OOM_SAKKIE.md)
- [`Oom Sakkie farm agent`](../02-agents/farm/OOM_SAKKIE.md)
- [`BRAIN_GUARD.md`](../00-governance/BRAIN_GUARD.md)
