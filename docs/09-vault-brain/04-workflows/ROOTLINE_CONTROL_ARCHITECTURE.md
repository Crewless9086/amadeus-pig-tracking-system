# ROOTLINE Control Architecture

Status: authoritative target architecture and authority boundary.

Evidence cut: `2026-07-25`, repository revision
[`6123c1e`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/6123c1e54134ccde5b3cc14d607d12ccaecc020d).

This document defines the intended mature ROOTLINE operating model. It does not
grant hardware authority or claim that planned capabilities are built,
deployed, configured, or operational.

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

The platform behind IFTTT is **Unknown — owner/hardware inventory required**.
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
