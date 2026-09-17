# ROOTLINE Borehole 1 protected commissioning guide

Status: source-prepared, command-inert, uncommissioned, authority disabled

This guide commissions one reported device only. It does not authorize a
provider command, configuration change, routine run, deployment, or autonomous
operation. The deployed ROOTLINE agent remains the eventual operational actor;
the development terminal must never operate the borehole.

## Exact identity contract

| Field | Current source truth |
| --- | --- |
| ROOTLINE identity | `BOREHOLE-1-MINI-R4-CH1` |
| Provider/account binding | `ewelink` / `ewelink_owner_account` |
| Reported provider device | `1002851416` |
| Reported display name | `Boorgat 1 Krag Toevoer` |
| Manufacturer/model/channel | SONOFF / MINI R4 / logical channel 1 |
| Physical effect | Borehole 1 pump power; exact motor/water effect remains unproven |
| Safe state | OFF |
| Command mapping | absent and unapproved; preserve as a commissioning field |
| Authority | `ROOTLINE_BOREHOLE_ENABLED` remains disabled; no standing authority |

An exact provider identity is not physical identity. Electrical ON is not pump
start, water movement, delivered volume, storage fill, or successful work.

## Charl's one supervised commissioning journey

Do this only in a separately approved protected window, with Charl physically
at the borehole controls and able to use the manual isolation. ROOTLINE should
prepare all read-only evidence before asking for that window.

1. Identify and record, without changing it, the exact manual breaker/isolation
   location, electrical supply, dry-run protection, full-tank cutoff, and the
   point where pump start/stop and water flow/stop can be observed. Any ambiguity
   stops the journey.
2. Obtain a fresh provider readback (at most five minutes old) proving device
   `1002851416`, display name `Boorgat 1 Krag Toevoer`, MINI R4, channel 1 only,
   online, and OFF. Record provider time and response digest separately.
3. Before any ON, separately verify power restoration is OFF; timers, scenes
   and provider interlocks are disabled; every output is OFF; and a native
   auto-OFF is configured and read back at no more than 30 seconds. Configuration
   changes are outside this source mission and need their own protected action.
4. Verify the pump is physically stopped and water flow is stopped. Confirm the
   manual isolation is reachable. If the supply is dry/low, pressure is unsafe,
   the full-tank cutoff blocks a useful observation, energy is unsafe, or another
   material load/control path conflicts, stop without ON.
5. After one exact protected approval, a future separately reviewed and deployed
   ROOTLINE commissioning runtime—not present in this stage and never this terminal—may create one fresh execution identity, durably
   claim it before ON, and issue one state-setting ON. Never retry an ambiguous
   ON. The commissioning maximum is 30 seconds.
6. Charl observes and records only irreducible physical facts: pump started,
   water flow observed, native auto-OFF occurred, pump stopped, and water flow
   stopped. Do not invent litres, pressure, motor current, tank gain, or a cause.
7. That future deployed runtime must record provider acceptance and readback separately from those
   observations. At the deadline it issues state-setting OFF even if native
   auto-OFF appeared to work. OFF may be repeated safely up to three bounded
   attempts. Completion requires authoritative provider OFF and physical pump
   stopped plus water flow stopped.
8. If final OFF is ambiguous, use manual isolation, contain this exact device,
   prohibit reuse, create one urgent physical exception, and preserve the active
   claim for restart recovery. Restart may only load and observe or drive bounded
   OFF; it may never create a new ON for the old identity.
9. Reconcile one immutable canonical commissioning baseline with the exact
   provider/device/channel, evidence digests, physical observations, native
   fail-OFF, manual isolation, dry-run/full-tank protections, safe pressure/flow
   observation, electrical supply, and approved maximum routine runtime.
10. Commissioning does not enable routine operation. A later independent review
    and exact protected authority packet must define scope, limits, revocation,
    concurrency, energy rules, follow-up, and activation. A fresh ordinary cycle
    through the deployed agent is still required before operational acceptance.

## Fail-closed operating prerequisites after commissioning

Every proposed run must bind fresh canonical water need and storage/reservoir
truth; the commissioned baseline; applicable standing authority; fresh provider
OFF; dry-run, low-water, supply-pressure/flow and full-tank interlocks; material
energy eligibility; an exclusive borehole/concurrent-load claim; a positive
bounded runtime; native auto-OFF; and final-OFF provider plus physical proof.
Unknown, stale, conflicting, missing, or changed evidence blocks only the run.

The command identity family is `<execution_id>:ON`, `<execution_id>:OFF:1`,
`:OFF:2`, and `:OFF:3`. Exactly one ON attempt is permitted. Provider receipts,
canonical receipts, and physical receipts remain separate. The next automatic
trigger is a canonical evidence change or the exact stop/reassessment deadline.

## Rollback and containment

Before commissioning: make no command and leave the registry uncommissioned.
During commissioning: state-setting OFF, bounded safe repeated OFF, manual
isolation, device containment, authority disabled. After commissioning: revoke
or leave disabled `ROOTLINE_BOREHOLE_ENABLED`, invalidate the commissioning
generation, preserve receipts, load any active claim on restart, prove final OFF,
and require a new generation before reuse. Never roll back by deleting history.

## Exact protected owner decision packet

Present this packet only after steps 1-4 are proven from fresh provider/read-only
evidence and all fields below are populated. Until then its state is
`NOT_READY_DO_NOT_ASK`.

```text
Decision ID: ROOTLINE-BOREHOLE-1-COMMISSION-30S-V1
Decision: Authorize or decline one supervised, maximum-30-second Borehole 1
commissioning run by a separately reviewed and deployed ROOTLINE commissioning runtime.
Exact device: eWeLink account binding <digest>; device 1002851416;
Boorgat 1 Krag Toevoer; SONOFF MINI R4; channel 1; physical Borehole 1 mapping
<observed physical identity>.
Preconditions proved at: <SAST timestamp and evidence digest>
Manual isolation: <exact location/procedure>
Dry-run protection: <identity and read-only/test proof>
Full-tank cutoff: <identity and read-only/test proof>
Supply pressure/flow observation: <exact method>
Pump/motor observation: <exact method>
Electrical supply: <exact identity>
Provider safety: OFF; restoration OFF; timers/scenes/interlocks disabled;
native auto-OFF exactly <seconds, maximum 30>.
Allowed effect: one ON attempt under a fresh claimed identity, then bounded OFF.
Required proof: provider ON/OFF receipts kept separate from observed pump start,
water flow, pump stop and water-flow stop.
Failure action: no ON retry; up to three state-setting OFF attempts; manual
isolation and containment if final OFF is unproven.
This decision does not approve routine/autonomous authority, deployment,
configuration change, provider mapping change, or any claimed water volume.
Choose exactly one: AUTHORIZE THIS ONE COMMISSIONING RUN / DECLINE.
```
