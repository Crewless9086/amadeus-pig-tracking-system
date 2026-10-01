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

## Farm-manager authority envelope

Anton is the authenticated human farm manager. Within the farm and irrigation
domains he may report, preview, and confirm his own governed operational
actions, including mortality lifecycle confirmation. Authorization is based on
the authenticated principal's bounded role/capability, not a blanket
`is_owner` identity check. The preview and confirmation remain bound to the
same actor; Anton cannot confirm Charl's claim and Charl cannot silently
confirm Anton's claim. Audit evidence, canonical revalidation, atomic writes,
idempotency, replay containment, and irrigation/device safety controls remain
mandatory.

Across specialists governed by Oom Sakkie, Anton and Charl receive the same
operational routes, protected approval journeys and messages; only the
recipient's configured language differs. This parity includes HERDMASTER,
ROOTLINE, SAM, BEACON and governed DOCUMENTS work. A `farm_manager` must never
be diverted into the legacy observation-only family adapter after one of these
shared routes declines. Capability and action-kind boundaries remain explicit;
no wildcard owner identity is minted.

This authority does not grant Anton access to CORE or CHARLIE, permission or
role administration, credentials, or an unsafe hardware exception. Those are
platform/owner-administration boundaries, not Oom Sakkie specialist work. Every
shared specialist retains its existing actor-bound confirmation, evidence,
revalidation, audit, replay, provider and physical-safety gates. This creates no
second manager, bot, parser, database, queue, or lifecycle.

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

## Longitudinal welfare-case boundary

One stable welfare case follows one canonical pig, one attributable episode and
one concern. New evidence for that same episode appends to the existing case;
unrelated concurrent concerns for the pig remain distinct. Matching must use
chronology and concern continuity, preserve ambiguity as Unknown and never
collapse cases merely because they share a pig, wording or nearby time. A later
recurrence creates a linked new case. Natural correction appends evidence and
invalidates stale projections without rewriting history.

Every case lifecycle explicitly carries urgency, state, next check,
responsible owner, escalation, closure/reopening and provenance. Silence never
means recovery. A due check that produces no evidence remains due or escalates
under a later explicit event; it does not close. Immediate supported welfare
guidance always precedes record confirmation and remains available even if case
matching or persistence is unavailable.

The case links observation, treatment/medical, movement, mortality and
pig-lifecycle facts by their separate canonical identities. It never merges or
replaces them. Canonical death evidence explicitly closes the living-welfare
question, while mortality assessment, removal and disposal remain separate
work with their own lifecycle and owner. Unknown death, disposal or cause stays
Unknown and blocks only the dependent conclusion.

## Retained identity and litter selection

Reassess an old unresolved identity against the unchanged authenticated report
and current canonical identities. A date number must not become a competing pig
when the report explicitly identifies another tag. Reassessment cannot override a
resolved contrary identity, a correction, cancellation, prohibited recording or
ambiguous current match. The same protected preview must independently verify the
exact animal and supplied facts before confirmation.

Select a retained piglet-loss litter through the resolved sow's stable Pig ID,
active litter state and attributable incident date. Display names may be empty or
changed and must not act as identity predicates. Missing or multiple eligible
litters remain unresolved. The confirmation names the exact litter and selected
piglets without substituting a hard-coded sow name; no loss is recorded by selection.

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

## Retained mortality confirmation window

For an original retained mortality report that has never had a real protected
card attempt, one finite 30-minute confirmation window begins at the first
permitted delivery attempt. Waiting for the manager must not consume this
window. The existing report, claim, preview, operation and history remain the
same; no replacement report or automatic owner confirmation is created.

Admission requires complete bounded source, claim, case and delivery history,
current recipient authority and fresh canonical facts. Cancellation, correction,
supersession, conflicting effects, incomplete history or uncertain provider
history prevents admission. A documented correction of a false pre-send attempt
requires its exact audit chain; it is not permission to disregard real attempts.
Window creation and attempt ownership commit together exactly once. An attempt,
ambiguous result or prior window never starts another automatic window.

An expired orphan claim that was never presented or attempted may require a
replacement preview when current canonical material no longer matches its old
claim. This is not same-preview renewal or confirmation. Permit at most one
audited automatic replacement for the unchanged authenticated original report,
exact same resolved animal and mortality event family, after independently
rebuilding a complete current preview. The predecessor remains immutable history
with an explicit retired state; its token cannot become current again.

The replacement transaction locks and revalidates the original source, unique
predecessor and manager case. It requires complete bounded histories, current
recipient authority, no attempted/ambiguous delivery, cancellation, correction,
confirmation, competing claim or canonical effect. The audit binds the old claim,
source and manager history to the new preview and successor. Preparation sends
nothing. Presentation and confirmation independently verify that ancestry, current
facts and protected authority. A flag or missing old card alone proves nothing.
Any uncertainty retains the case for engineering reconciliation. A changed or
attempted successor cannot trigger repeated automatic replacement.

For an unresolved original report with a unique expired, never-attempted orphan,
the runtime may route directly into that existing locked replacement transaction.
It loads fresh canonical evidence there once; earlier cached evidence grants no
authority. If the exact request proves ordinary same-preview renewal instead,
the replacement attempt rolls back before returning to the normal renewal rail.
All other conflicts remain contained. This ordering changes no source, ancestry,
recipient, confirmation, delivery or farm-effect requirement.

An authenticated owner or authorized farm manager pressing an expired,
verifiably delivered retained mortality card requests a fresh review; that press
does not confirm a farm effect. Under the same source fence, the runtime may
create one audited successor confirmation generation for the same report,
principal, physical facts and canonical operation. The old token and expiry stay
unchanged. The new card explains the expiry, retains the original facts and
requires a genuine new confirmation within its own finite presentation window.
No animal or date is requested again merely because the earlier card expired.

Duplicate or racing old-card requests resolve the same successor. An older card
cannot branch another generation or cancel/change a newer one. Changed facts,
revoked authority, cancellation, supersession, unknown history or delivery
ambiguity prevents continuation. Complete bounded history and immutable audit
bindings are rechecked at admission; a caller-supplied continuation field is not
authority. The same manager case may reconcile the audited successor evidence
and resume its never-attempted delivery after interruption. Except for the strictly bounded never-attempted orphan replacement above, the
scheduler cannot create a confirmation generation. It can never restart an
attempted window. A failed or
late callback acknowledgement has receipt-deduplicated informational feedback;
it grants no farm authority and cannot conceal a refused preview.

The genuine protected callback must match its durable owner, chat, card and
receipt. Before recording, the existing mortality service revalidates the source
and canonical evidence. Source completion, canonical domain effects and the
existing protected claim completion commit in one transaction; failure rolls
all three back together. Exact callback recovery uses the original completed
operation without recording a second death. Source
cancellation and append operations share an ordered fence; canonical writers
outside that fence are checked through fresh validation, not presumed locked.
Source comparison uses the exact JSON representation persisted by the existing
writer, including semantic array fields. An already-completed ordinary mortality
confirmation returns fresh canonical readback without appending another source
completion. A missing or mismatched canonical event cannot be recreated from a
completed source.

After canonical completion, the existing scheduled recovery worker may resume
completion delivery when its previous delivery lease has expired, including a
worker interruption or delivery exception. It first verifies the exact canonical
event and current recipient authority, then reuses the existing idempotent message
lifecycle. An unresolved effect remains held. This does not authorize the scheduler
to execute a mortality claim that has not completed its domain transaction.

A known pre-send SQL timeout may be retried only after proven rollback and a
successful connection close. An uncertain commit or provider effect remains
contained. Local implementation approval does not establish deployed behavior
or dispense with genuine confirmation and operational acceptance.

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

The existing authenticated family principal supplies the durable output
language (`charl` defaults to English; a configured Afrikaans family principal
such as `dad` remains Afrikaans). Inbound-language detection never writes this
preference. The same selection is carried through the pure preview composer,
protected buttons, correction/failure states and completion.

### Protected write authority

`modules/pig_weights/herdmaster_health_loss_recording.py` contains narrowly
governed confirmed recording for supported factual welfare observations and
existing mortality handling. It is not a generic compound executor and grants
no authority to create arbitrary litter, mating, medical, movement, disposal,
availability, customer, or sales effects. Stage 1 neither invokes nor expands
this writer.

For a supported confirmed death, the writer uses one database transaction to
record the canonical lifecycle effect, close the attributable living-welfare
case with an append-only death event/link, complete now-invalid living-animal
checks with append-only manager-case events, and retain distinct mortality,
disposal and biosecurity work. Canonical readback must prove the pig, lifecycle,
welfare closure and active-projection outcome before completion is composed;
failure rolls the whole transaction back. Exact replay reuses the same
operation and readback and creates no second effect.

The protected claim stores that canonical completed result before Telegram
presentation. If the provider completion edit/send fails after commit, an
exact retry of the same bound callback receipt may reuse the stored result for
delivery only; it must not enter the farm writer again.
The existing scheduled protected-recovery cycle also leases a completed
mortality claim whose delivery has not yet been recovered, recomposes the
recipient-language presentation from the sealed identity and canonical result,
and edits/sends through the existing idempotent card lifecycle. It neither
requires another owner action nor creates a new provider or farm event. A
completed animal may retain its last `pig_current_state.current_pen_id` as historical location
context because that view derives the latest location event. Current pen
occupancy is instead the governed projection of Active, on-farm animals; death
completion must prove that active membership is zero rather than erase history.

`202608200002_create_pig_welfare_case_lifecycle.sql` is the reviewed additive
foundation for case identity, append-only case events and non-merging fact
links. `modules/pig_weights/pig_welfare_case_runtime.py` is the bounded adapter:
the existing authenticated health/loss handler opens or appends coordination
context, prefers durable open cases over its legacy 24-hour compatibility
chronology, carries HERDMASTER owner/urgency/next-check state and projects the
same case/work identity for the existing shared-attention contract. It creates
no second observation, treatment, movement, mortality, manager, queue or
Telegram lifecycle. Migration `202608200002` is mandatory on the production
migration rail. Once its immutable receipt, readiness probe and canonical
database configuration are present, the runtime is active by default;
`PIG_WELFARE_CASE_RUNTIME_ENABLED=false` is the explicit containment switch.
Missing schema, missing database configuration, malformed configured values
and database failure remain fail-closed. Exact deployed revision,
provider confirmation and canonical readback remain separate evidence gates.

### Production status

Production activation and canonical mortality acceptance were proven on
2026-08-24 by one actor-bound provider interaction: the transaction recorded
the lifecycle and welfare closure exactly once and canonical readback proved
the animal Dead, off farm, and absent from active pen and availability
projections. The provider completion failed after commit, so visible completion
and later terminal-independent continuity remain open acceptance evidence.
Historical GateKeeper execution `64196`, relay
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
