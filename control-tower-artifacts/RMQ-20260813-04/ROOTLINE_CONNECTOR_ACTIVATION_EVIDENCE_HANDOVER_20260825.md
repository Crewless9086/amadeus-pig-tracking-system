# ROOTLINE connector activation evidence handover — 2026-08-25

Status: **DURABLY LOGGED — NOT YET AN OWNER OUTCOME** in the reviewable commit
carrying this handover.

Classification: evidence and activation blocker within existing Mixer
`RMQ-20260813-02`, Injector `RMQ-20260813-03A/03B` and Borehole
`RMQ-20260813-06` lineages. Priority is unchanged. No new mission, device
store, scheduler or authority rail is created.

Fresh zero-control provider readback established:

- Fertilizer controller `100204d497` channel 2 (Mixer) was online and OFF, but
  its native auto-OFF read back as 300 seconds rather than the intended 1,800
  seconds. The provider reported channel 2 as supervised.
- The same controller channel 1 (Injector) was online and OFF with a 120-second
  native auto-OFF and power-restoration state OFF, but no canonical supervised
  Injector execution event exists.
- Borehole `1002851416` channel 1 was online and reported ON. Native auto-OFF
  duration/enabled, power-restoration state and conflicting-control-path truth
  were incomplete. No evidence attributes that ON state to a ROOTLINE flag,
  scheduler claim or command.

The canonical ROOTLINE plan remained `Await batch` for Mixer and `Await
eligible irrigation` for Injector, with zero fertilizer execution events.
Mixer and Injector production flags remained disabled. These facts prohibit a
truthful fertilizer `standing_active` migration or five-flag activation now.
The scalar Borehole authority row does not convert incomplete provider safety
readback or an unattributed ON state into a commissioned owner outcome.

Next automatic action after the exact owner correction is fresh provider
readback, followed by the existing governed commissioning/evidence journey.
Only canonical evidence may then be bound by a reviewed append-only authority
migration. Render configuration and natural need-driven operation remain
separate later gates.

**ACTION REQUIRED NOW: Set Mixer CH2 native auto-OFF to 30 minutes (1,800
seconds).** Do not repeat a Telegram message or presence statement, and do not
perform any Injector or Borehole action now. ROOTLINE owns fresh readback,
commissioning reconciliation and every later automatic next step.

No authority migration, Render configuration change, database write, provider
control call or hardware command occurred.

## Provider correction readback

At `2026-08-25T20:48:04Z`, a fresh zero-control provider readback verified
fertilizer controller `100204d497` online with CH2 OFF, native auto-OFF enabled
at exactly 1,800 seconds and power-restoration state OFF. The read performed
three provider reads and zero provider control calls. CH1 remained unchanged:
OFF, native auto-OFF enabled at 120 seconds and power-restoration state OFF.

This resolves the Mixer configuration mismatch in `RMQ-20260813-02`; it is
commissioning evidence, not proof of a fresh Mixer execution or owner outcome.
The current plan still says `Await batch`, both fertilizer flags remain disabled
and zero fertilizer execution events exist. Injector `RMQ-20260813-03A/03B`
therefore remains blocked only on the existing automatic supervised-evidence
journey. ROOTLINE owns that next step without Telegram repetition, presence or
another owner action. No authority migration or five-flag activation is allowed
until the complete exact evidence contract is canonical and read back.

**OWNER ACTION: NONE.**
