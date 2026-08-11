# HERDMASTER Weighing Batch Intelligence Plan

Status: owner-approved future mission. Do not start automatically while a higher-priority serialized mission owns production.

## Business outcome

One completed bulk-weighing upload must produce:

1. one printable, evidence-rich Weight Report;
2. one concise HERDMASTER management summary through Oom Sakkie;
3. at most one grouped, material follow-up question;
4. a durable attributable answer that improves later herd interpretation.

The system must use recorded data rather than make Charl manually compare rows or remember possible causes.

## Trigger and mission identity

Start only after a canonical bulk-weight batch is accepted as complete. Bind the analysis to its exact batch ID, accepted row identities, completion time and deterministic evidence digest.

Do not trigger for:

- a draft or partial upload;
- validation failure or rollback;
- a replayed batch;
- a print-only sheet;
- an unchanged report refresh;
- individual exploratory weight entry unless later explicitly included.

One completed batch may produce at most one current analysis and one owner delivery. A corrected or superseding batch must retain lineage rather than silently replace evidence.

## Required canonical evidence

### Weight evidence

- exact batch and accepted entries;
- pig identity, name/tag, pen and cohort/litter where attributable;
- current and previous accepted weight;
- dates and elapsed days;
- weight difference and supported growth per day;
- same-day duplicates, missing previous weight and implausible/reweigh candidates;
- active/on-farm and lifecycle state at the evidence cutoff;
- pigs expected in covered pens but not weighed, labelled as not weighed rather than zero.

### Context evidence

Read proportionately for the interval between comparable weighings:

- local observed weather, temperature and rainfall;
- pen and movement chronology;
- feed changes, feed interruptions or feeding observations when recorded;
- water interruptions or relevant ROOTLINE evidence;
- treatment, medical, withdrawal and welfare evidence;
- weaning, nursing, pregnancy and other reproductive state;
- mortality or litter/cohort clustering;
- scale, operator or weighing-condition evidence if attributable.

Absence of context is Unknown, not proof that no change occurred.

## Deterministic analysis before language generation

Compute and preserve:

- accepted entries and unique pigs weighed;
- coverage by pen and cohort;
- average and median current weight;
- average and median change;
- supported average growth per day;
- gain, slow-growth, unchanged, loss and no-comparable-previous counts;
- individual, litter/cohort, pen and herd-level patterns;
- largest supported gains and losses;
- repeated declines across consecutive comparable weighings;
- animals requiring reweigh before interpretation;
- missing coverage and non-active animals included in error.

Thresholds must be evidence-qualified by age, elapsed days, cohort and prior farm distribution. Do not apply one universal growth threshold to every pig. Explicit zero remains zero; missing is never converted to zero.

## Interpretation boundary

Every finding must separate:

- **Measured:** direct canonical weight result;
- **Associated:** attributable context occurring in the same relevant interval;
- **Unknown:** unsupported cause or missing context;
- **Next action:** proportional verification, observation or management review.

Weather, feed, water, disease, handling, scale error or pen movement may be associated evidence but must never be stated as the cause without attributable proof.

## Pattern and question rules

- Prefer a grouped pen/cohort finding over many duplicate animal alerts.
- Ask no question when the result is ordinary and no material uncertainty changes action.
- Ask at most one grouped question about the most decision-relevant missing fact.
- Reuse known owner facts and existing farm observations; never ask Charl to repeat them.
- Example: `Het die voer, hoeveelheid of voertye in D3 verander sedert die vorige weging?`
- Bind the reply to the exact batch, animals/pen, provider identity and observation time through the existing governed observation lifecycle.
- A later answer must refresh the interpretation without duplicating the batch, report or Telegram message.

## Owner presentation

### Telegram

Use natural Afrikaans, names/pen labels before internal IDs and a compact structure:

`HERDMASTER — WEEKLIKSE GEWIGSOPSOMMING`

- number weighed and coverage;
- average supported change;
- maximum three material findings;
- one concise relevant-context section;
- one next action or at most one grouped question.

Do not send the full table, every Pig ID, repeated disclaimers or one alert per animal. Link or direct Charl to the detailed Weight Report.

### Printable Weight Report

Extend the existing `/weight-report`; do not create a competing report. Preserve:

- date/batch scope and evidence identity;
- summary metrics;
- loss/reweigh flags;
- pen/cohort summaries;
- detailed rows;
- missing coverage;
- concise HERDMASTER findings, known context, Unknowns and follow-up status;
- print-safe layout.

## Authority and safety

The first mission is read-only analysis and governed observation intake. It has no authority to change feed, medication, lifecycle, purpose, pen, sales status, mating, weight entries or hardware. It may not diagnose illness. Serious or repeated welfare patterns must clearly recommend appropriate human/veterinary assessment.

## Source areas to inspect

- `/bulk-weights` and canonical bulk-weight batch acceptance;
- `/weight-report` and `/api/pig-weights/weight-report`;
- `modules/pig_weights/pig_weights_service.py` and Supabase read/write boundaries;
- canonical weight, movement, litter, medical and observation tables;
- ROOTLINE weather/water read-only evidence;
- existing Oom Sakkie owner-task and family-message lifecycle;
- existing HERDMASTER observation rail;
- dashboard navigation and report tests.

## Delivery stages

1. Reconcile current schema, batch completion identity and report contract.
2. Build a pure deterministic weighing-analysis packet and fixtures.
3. Add contextual read-only evidence adapters with explicit provenance and cutoffs.
4. Extend the existing Weight Report with the agentic findings section.
5. Add one deduplicated Oom Sakkie presentation lifecycle.
6. Add the single grouped-question and attributable-answer continuation.
7. Obtain herd/operations and backend/security/privacy/authority review.
8. Integrate under serialized production ownership.
9. Prove one genuine completed farm weighing batch end to end.

## Completion proof

Business completion requires a fresh real weighing upload proving:

- exactly one completed batch and analysis identity;
- correct accepted/rejected/omitted counts;
- useful individual and grouped growth findings;
- missing pigs are not treated as zero;
- contextual evidence is correctly labelled measured/associated/unknown;
- one printable report is owner-visible;
- one concise provider-confirmed Telegram summary is delivered;
- at most one grouped question is asked only if material;
- an answer, if supplied, is retained and refreshes the same mission;
- replay creates zero duplicate analyses, reports, questions, messages or farm writes.

CI, deployment, a fixture, a handover or a synthetic Telegram message is not completion.

## Expected business result

Charl completes weighing once and receives a short, evidence-backed explanation of herd growth, the few matters needing attention and the smallest useful next question, while the detailed printable report preserves the underlying evidence for management decisions over time.
