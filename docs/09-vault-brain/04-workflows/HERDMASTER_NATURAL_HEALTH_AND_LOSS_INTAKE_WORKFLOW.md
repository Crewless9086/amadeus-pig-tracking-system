# HERDMASTER Natural Health And Loss Intake Workflow

Status: owner-approved next operating goal; not yet implemented or activated

## Business outcome

A family member can report an ordinary pig illness, injury, death, farrowing complication, piglet loss, or combined event to Oom Sakkie in natural language. Oom Sakkie and HERDMASTER identify the exact animal and event scope, ask only genuinely necessary follow-up questions, present one understandable consolidated preview, and use existing governed rails to record every supported canonical consequence exactly once after required confirmation.

The owner must not have to know which database tables, pages, forms, specialist lanes, or record types are affected.

## Natural intake examples

Supported messages include:

- `Tag 51 looks sick and is not eating.`
- `Pig 83 is limping.`
- `I found tag 22 dead this morning.`
- `Maya died yesterday after complications while farrowing. All 10 piglets were stillborn. We believe she had a uterine infection.`

Natural wording is evidence, not unrestricted write authority. The system must preserve the owner's exact words and separate observation from diagnosis, inference, and management action.

## Agentic intake behavior

1. Authenticate the family member and use the provider message timestamp as the report time.
2. Resolve the exact canonical animal from name, tag, Pig ID, pen, current mating/litter context, and recent conversation. If more than one animal matches, ask one precise identity question.
3. Retain facts already supplied and ask only for missing information that changes welfare action or canonical records.
4. For current illness or injury, prioritize immediate welfare. Do not delay urgent physical care while constructing records or waiting for a database confirmation.
5. Distinguish:
   - directly observed signs or outcomes;
   - owner-reported suspected cause;
   - veterinary diagnosis or treatment evidence;
   - agent inference, which must never be recorded as fact.
6. Reconcile all related canonical records and downstream projections before presenting the preview.
7. Present one concise before/after preview covering every proposed write and every intentionally unchanged area.
8. Require explicit confirmation for protected lifecycle, medical, mating, litter, movement, pen, or other farm-record writes.
9. Apply the confirmed event transactionally through existing canonical write rails with deterministic identity, locking, mismatch rollback, and exact replay prevention.
10. Verify canonical records and all affected current projections after the write, then return the next welfare or management follow-up through Oom Sakkie.

## Minimum proportional follow-up

Do not turn natural messages into rigid forms. Ask only what cannot be resolved authoritatively and materially changes the result.

Possible missing facts include:

- exact animal identity;
- whether the animal is alive and needs immediate assistance;
- observation/event date when it differs from the Telegram timestamp or wording such as `yesterday`;
- observable signs, injury, feed/water behavior, movement, breathing, discharge, temperature, farrowing progress, or other relevant welfare evidence;
- whether a cause is observed, suspected by the owner, or veterinarian-confirmed;
- treatment/product/dose/administrator evidence when treatment occurred;
- isolation, movement, disposal/removal, or veterinary follow-up facts when relevant.

Do not ask for unrelated fields merely because a form contains them. A report may remain partially recorded with a precise unresolved follow-up when the missing fact blocks only one dependent conclusion.

## Event families and reconciliation scope

### Sick or injured animal

Reconcile the current animal, medical/observation evidence, welfare urgency, pen and contact context, withdrawal implications, sale/breeding availability, isolation or movement, open tasks, treatment follow-up, and owner/veterinary escalation. Never diagnose from text alone or create medication facts without attributable evidence.

### Found dead or reported death

Reconcile lifecycle status, on-farm state, death/observed-found date, reported or confirmed cause, current pen occupancy, active mating/pregnancy/litter state, availability/reservation/sales projections, medical and welfare follow-up, removal/disposal evidence, herd counts, open work and mortality review. Do not fabricate a precise time or diagnosis.

### Farrowing and piglet loss

Reconcile the current mating, actual farrowing event, total born, born alive, stillborn, mummified or later-death distinctions, litter state, generated piglet identities where appropriate, maternal state, expected-date work, pen state, follow-up and reconciled counts. `Stillborn` means no live birth; a piglet dying after birth is a different lifecycle event.

### Compound event

A single natural report may affect multiple event families. It must produce one atomic business operation rather than requiring the owner to submit disconnected forms. Failure in any required protected write rolls back the whole compound operation unless the preview explicitly defines a safe independently committable observation-only portion.

## Maya acceptance journey

Use this owner-provided scenario as the primary compound-event acceptance journey, not as hard-coded Maya-specific logic:

> Maya died yesterday after complications while farrowing. All 10 piglets were stillborn. We believe she had a uterine infection.

The system must resolve the exact Maya and current mating, interpret `yesterday` relative to the authenticated message, and prepare a consolidated preview that can include:

- actual farrowing date;
- total born 10, born alive 0, stillborn 10;
- current mating-cycle closure and litter creation/closure as supported;
- Maya's lifecycle transition to deceased and off-farm/current-projection removal as appropriate;
- farrowing complications as owner-observed/reported context;
- uterine infection as owner-reported suspected cause unless veterinary evidence confirms it;
- removal from active breeding, sale availability, pen occupancy and future worklists;
- required disposal/removal, welfare, medical or mortality follow-up without inventing completion.

Acceptance requires one natural report, no repeated known questions, one consolidated preview, explicit confirmation, one atomic exact-once operation, zero duplicate litter/death/medical events on replay, reconciled herd/litter/mating/pen/availability projections, and a useful next prevention or follow-up recommendation.

## Authority and safety

Before operational proof, Oom Sakkie and HERDMASTER may authenticate, interpret, reconcile, prioritize welfare, ask questions and prepare previews. They may not silently write or infer:

- death, lifecycle or on-farm state;
- medical diagnosis, treatment or withdrawal clearance;
- mating, pregnancy, farrowing or litter outcomes;
- movement, pen occupancy, disposal/removal, purpose or availability;
- customer, reservation, allocation, order or sale changes.

Emergency welfare guidance must remain proportionate and must not be blocked by record-writing mechanics. Veterinary involvement is recommended when the animal is alive with serious signs or when diagnosis/treatment lies outside supported farm evidence.

## Delivery stages

1. Build a zero-I/O natural event interpreter and complete-effect preview contract.
2. Bind it to authenticated Oom Sakkie messages and complete canonical animal/event chronology.
3. Compose existing lifecycle-death, litter/stillborn, mating, medical/observation, movement/pen and projection rails into one governed transaction.
4. Add exact identity, stale chronology, concurrency, rollback, replay and partial-evidence tests.
5. Prove one ordinary sick/injured preview and one ordinary found-dead preview with zero writes.
6. Prove the Maya compound preview with zero writes.
7. After owner review, perform one supervised real event recording, verify every projection, and return the updated HERDMASTER recommendation through Oom Sakkie.

