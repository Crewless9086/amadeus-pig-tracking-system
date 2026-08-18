# HERDMASTER Natural Health And Loss Intake Workflow

Status: owner-approved canonical workflow; stage 1 source prepared; production behavior unproven

## Business outcome

A family member can report an ordinary pig illness, injury, death, farrowing
complication, piglet loss, or combined event to Oom Sakkie in natural language.
Oom Sakkie and HERDMASTER preserve the report, resolve the exact animal and
chronology, ask only materially necessary questions, and present one
understandable preview of every potentially affected canonical domain. Protected
effects occur only after explicit confirmation through their existing governed
services.

The owner must not need to know database tables, forms, specialist lanes, or
record types.

## Evidence semantics

Natural wording is evidence, not diagnosis or write authority. Every result must
keep these categories separate:

- direct owner observation or reported outcome;
- owner-suspected cause;
- attributable veterinary diagnosis or treatment evidence;
- agent inference, which is never promoted to fact.

The owner's exact text, authenticated principal, provider message identity,
provider time and timezone remain bound to the preview. Unsupported diagnosis,
ambiguous identity, conflicting chronology, or stale evidence fails closed.

Mortality assessment must reconcile every attributable loss without treating
an undated or missing-cause record as zero. Show dated, undated, corrected and
Unknown-cause counts separately. Rank possible contributing factors only as
hypotheses, never diagnoses, and ask one grouped physical question covering the
smallest missing weather, housing, feed/water, health or herd-context evidence.
The answer becomes append-only observation evidence and must be consumed on the
next assessment rather than requested again.

## Proportional intake

Resolve identity from canonical Pig ID, tag, name and current context. If the
match is not unique, ask one precise identity question. Retain supplied facts
and ask at most the smallest question whose answer materially changes immediate
welfare guidance or a proposed canonical effect. Do not turn the conversation
into a form or repeat known animal, date, count, cause, or welfare facts.

For a live animal, classify observable urgent warning signs without diagnosing.
Record construction and confirmation must never delay immediate physical or
veterinary assistance for breathing distress, inability to stand or drink,
serious bleeding, continuing difficult farrowing, severe distress, or another
supported urgent sign.

## Complete-effect preview

One consolidated preview enumerates each potentially affected domain and marks
every effect as `proposed` or `Unknown / unchanged`:

- lifecycle and current/on-farm state;
- medical observations, diagnosis provenance, treatment and withdrawal;
- mating, farrowing and litter outcomes;
- movement, pen occupancy and removal/disposal evidence;
- breeding and sale availability;
- reservations, sales and customer commitments;
- downstream welfare, mortality and management work.

Stillborn piglets were never live births. A piglet that dies after live birth is
a distinct lifecycle outcome. Unknown removal, disposal, diagnosis, treatment,
exact death time, litter count, or mating identity must remain Unknown and block
only dependent effects.

All protected effects require explicit confirmation of the exact preview,
operation identity, canonical evidence generation, and required confirmation
set. A future compound executor must revalidate evidence and commit supported
effects atomically with exact replay changing zero rows. This workflow does not
authorize such an executor.

## Immutable stage-one fixtures

1. Pig 002: the owner reports that the pig is not eating, appears otherwise
   fine, is lying down, and will be monitored. The interpreter preserves those
   observations, does not diagnose, resolves exactly one Pig 002 or asks one
   identity question, and escalates only from supported warning signs.
2. Maya: the owner reports maternal death during farrowing, ten stillborn
   piglets, and a suspected uterine infection. The interpreter preserves death,
   farrowing and counts as reported outcomes, keeps uterine infection
   owner-suspected unless veterinary evidence confirms it, and proposes all
   applicable lifecycle, mating, litter, medical, pen/availability and follow-up
   effects without writing them.

These fixtures are immutable test evidence. They must never consume or replay a
provider update or become animal-specific production logic.

## Current implementation truth

### Prepared source

- `modules/pig_weights/herdmaster_natural_health_loss_intake.py` is the pure,
  zero-I/O interpreter and complete-effect preview contract.
- `modules/oom_sakkie/herdmaster_health_loss_preview.py` is a pure adapter from
  existing authenticated owner authority to the evaluator; it does not route,
  send, persist, or consume confirmation.
- Focused pure tests cover ordinary illness, injury, found-dead, farrowing loss,
  compound events, identity ambiguity, chronology, provenance, urgency,
  duplicate facts, deterministic identity and zero authority.

### Runtime wiring present in source

`modules/oom_sakkie/herdmaster_health_loss_runtime.py` and the existing family
message lifecycle contain authenticated intake/context wiring. Presence in
source does not prove that a deployed route is enabled, correctly configured,
or operationally successful.

### Protected write authority

`modules/pig_weights/herdmaster_health_loss_recording.py` contains narrowly
governed confirmed recording for supported factual welfare observations and
existing mortality handling. It is not a generic compound executor and grants
no authority to create arbitrary litter, mating, medical, movement, disposal,
availability, customer, or sales effects. Stage 1 neither invokes nor expands
this writer.

### Production status

Production activation and a genuine end-to-end health/loss journey remain
unproven by this workflow. Historical GateKeeper execution `64196`, relay
execution `64197`, and the original Pig 002 provider update are failed-
acceptance evidence only and must not be consumed, replayed, resent, or used as
a write trigger.

## Delivery stages

1. Audit and complete the zero-I/O interpreter and complete-effect preview.
2. Separately review authenticated routing and canonical evidence loading.
3. Separately compose protected canonical services under one transaction.
4. Prove identity, chronology, concurrency, rollback and zero-effect replay.
5. Only with explicit production authority, prove one genuine owner journey and
   authoritative readback.

Prepared source, runtime wiring, deployed configuration, provider verification,
operational proof and business completion are distinct states.
