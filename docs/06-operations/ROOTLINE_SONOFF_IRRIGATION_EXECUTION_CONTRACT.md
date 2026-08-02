# ROOTLINE SONOFF B/C irrigation execution contract

Status: source-only contract; not deployed, configured, commissioned, or authorised to actuate.

## Proven hardware boundary

The controller is `IRRIGATION (1) - Left`, a SONOFF 4CH Pro R3 on eWeLink,
firmware 3.8.2. B12345 is channel 1 and C12345 is channel 2. Their identities
and supervised OFF behaviour have been physically proven. Firmware supports
independent per-channel native inching up to 60 minutes. Inching is not assumed
to be enabled. Channels 3/4, borehole, fertilizer, and simultaneous B/C remain
outside this contract.

## Commission each channel once

1. Inspect and record the exact device, firmware, zone, and channel.
2. Confirm power-restoration state is OFF for that channel.
3. Inventory eWeLink schedules/scenes and IFTTT automations; disable or remove
   every conflicting trigger through a separately authorised configuration
   change. An unknown inventory fails closed.
4. Under supervision, configure a short inching interval below 60 minutes,
   issue one deliberate ON, physically confirm the intended camp starts, and
   let the controller turn it OFF without an Oom Sakkie OFF command. Confirm
   physical stop and zero other-channel actuation. Repeat the proof with the
   cloud/process path unavailable after ON, and perform a supervised active
   power interruption proving restoration remains OFF with no automatic
   restart. Normal connected operation alone does not commission a fail-stop.
5. Configure that channel's production inching value to exactly 60 minutes and
   record configuration evidence. Do not infer that the test value was
   changed merely because the test succeeded.
6. Bind the evidence digest to one immutable commissioning identity. The
   physical commissioning does not expire merely with age. Any
   device, firmware, mapping, configuration, conflict, or revocation change
   requires recommissioning.

These are operational instructions for a later authorised commissioning
window. This source change performs none of them.

## Each irrigation execution

Every segment is a separate execution, at most 60 minutes, bound through
canonical readers (not client-supplied flags) to the exact
zone/channel, current plan generation, commissioning identity, fresh (15-minute
maximum) ROOTLINE eligibility decision, and native auto-OFF deadline. The
execution identity and lifecycle reservation must be durably persisted before
ON by the later reviewed adapter. The planned packet records maximum runtime,
not a guessed stop time. The deadline is bound only when unambiguous ON
acceptance and native-timer readback establish the actual start. The native
deadline uses that read-back timer (60 minutes), even when an earlier primary
OFF is planned for a shorter segment. A short segment completes from
authoritative primary-OFF acceptance plus verified shutdown; it must not claim
the still-armed 60-minute backstop fired. A full 60-minute segment requires the
native auto-OFF outcome.

One owner-visible, buttonless daily card is retained across both segments and
follows `Planned -> Active -> Stopped -> Completed`, or `Failed`. Concise
segment notices update that card; they do not create duplicate plan cards.
Telegram delivery reports lifecycle; it is
not the fail-stop. ON is state-setting and may be attempted only once. An
ambiguous ON outcome is contained and never retried automatically. OFF is
state-setting and physically idempotent: it may be repeated proportionally,
up to the governed attempt limit, only while shutdown is unverified. Accepted
transport is not physical state or water-flow evidence.

A two-hour watering objective is never one execution. Segment 1 must reach
Completed with independent native auto-OFF and authoritative shutdown evidence.
Routine completion may use trusted device outcome evidence; family physical
observation is reserved for commissioning or genuine uncertainty. Without a
trusted device outcome, unattended autonomy remains unavailable.
ROOTLINE then reads fresh power, weather, rain, water, plan, exclusions, and
concurrency evidence. Only a new eligible decision may create segment 2 with a
new identity. Cancellation, changed need, rain, stale/conflicting evidence,
manual isolation, another active zone, or failed shutdown prevents segment 2.

Implementation: `modules/telemetry/rootline_irrigation_execution_contract.py`.
Acceptance: `tests/test_rootline_irrigation_execution_contract.py`.
