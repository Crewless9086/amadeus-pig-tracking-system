# HERDMASTER whole-herd next-round handover

Status: Prepared (20%), source-only

## Business outcome prepared

Once Oom Sakkie's P0 spine and existing HERDMASTER manager consumer are available, one authenticated manager round can immediately consume a deterministic HERDMASTER packet that separates already-active lifecycles from genuinely new herd work.

The packet does not create a page, router, queue, Telegram send or farm write. It is an I/O-free specialist result for the existing Oom Sakkie manager boundary.

## Current prioritized composition

Protected active lifecycles are listed for visibility but never consume a new-action slot and never create another question or case:

- Pig 11: preserve its existing welfare lifecycle/card and reassess only from the already-bound confirmation or newer attributable evidence.
- Pig 125: preserve its existing mortality preview/confirmation lifecycle and card 3184; do not repeat timing, removal or confirmation questions.
- Pig 127: obtain its exact canonical Pig ID and current active lifecycle/card from Oom Sakkie's existing active-case loader; do not hard-code or duplicate it.

The expected highest-value new actions are:

1. Mysikind (`PIG-2026-21BE`): operational `Assumed Pregnant`, attributable to the existing belly-drop/teat-growth observation and exact 2026-05-02 mating. Present approximately 2026-08-22 through 2026-08-26 as an uncertain farrowing range and approximately 2026-08-08 through 2026-08-15 as proportional preparation. Clinical scanning remains optional; no clinical-confirmation claim is permitted.
2. Mona (`PIG-2026-D050`): the same governed operational distinction and date windows, bound to her own exact 2026-05-02 mating identity and attributable observation.
3. Monday targeted weighing: one consolidated natural family request containing only canonically identified pigs whose current weight is genuinely decision-bearing and missing/stale.

Baby (`PIG-2026-7DAA`) remains explicitly `Inconclusive` in the monitoring section. She is not treated as pregnant and remains eligible for only the smallest attributable reassessment.

Breeding-readiness and data-quality matters remain visible but cannot displace more urgent supported work. A male shortlist is accepted only after current female readiness evidence is complete. Even then it is conditional, never an actionable mating recommendation, and a mating still requires the existing exact female/male/date preview and owner confirmation boundary. Zigay remains contained through its governed supersession work rather than being altered here.

## Natural Monday weighing journey

The manager asks once:

> On Monday, send one message with each listed pig's tag and measured weight in kg; include the weighing date once and include an observation time only if known.

Example family response:

> Monday weights: Tag 41 was 23.4 kg and Tag 52 was 19.8 kg. Weighed 3 August 2026; time Unknown.

The future adapter must:

1. resolve every tag/name to one canonical Pig ID and reject ambiguity;
2. split the message into exact weight facts without inferring missing weights;
3. produce one consolidated before/after preview containing every pig, weight, evidence date and observation time;
4. bind confirmation to the exact preview hash, authenticated owner and evidence generation;
5. invoke only the existing governed conversational weight writer after confirmation;
6. record each weight exactly once, prove direct and whole-message replay add zero facts, and refresh the HERDMASTER recommendation;
7. perform zero mating, pregnancy, lifecycle, movement, health, purpose or availability writes.

## Existing Oom Sakkie integration boundary

Do not register a second consumer. The later Oom Sakkie change should extend the existing `modules/oom_sakkie/herdmaster_management_runtime.py` manager consumption input so it can accept the new whole-herd packet after loading:

- current canonical HERDMASTER worklist/evidence generation;
- current active lifecycles, including Pig 11, Pig 125 and Pig 127;
- attributable owner reproductive observations;
- the minimal Monday reweigh candidate set;
- current breeding-readiness evidence and contained data-quality matters.

The existing authenticated authority, consumption store, manager bulkhead/deadline and replay boundary remain authoritative. No change belongs in Telegram, GateKeeper, n8n, Render configuration or the shared specialist router during this source-only mission.

## Operational acceptance proof

A later serialized proof must show one fresh authenticated manager request returns at most three new actions; active Pig 11/125/127 questions remain suppressed; Mona/Mysikind retain non-clinical proportional preparation; Baby remains Inconclusive; the Monday response receives one exact grouped preview; unsupported breeding advice is absent; direct replay creates zero consumption or farm rows; and no unrelated provider/database state changes.
