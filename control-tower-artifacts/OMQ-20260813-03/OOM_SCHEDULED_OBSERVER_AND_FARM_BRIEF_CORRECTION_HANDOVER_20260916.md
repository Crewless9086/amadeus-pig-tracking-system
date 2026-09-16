# Oom Sakkie scheduled observer and farm-brief correction handover

Status: current mission handover, 2026-09-16. Continue existing mission
`OMQ-20260813-03` under the Agentic Farm Runtime Programme. Production still
serves `3d321e4932cf205d03e759cc71a26edd411bc9d2`.

## Scheduled evidence and its limit

The passive observer completed its scheduled window from
2026-09-15 18:56 SAST through 2026-09-16 06:57 SAST. Charl's morning brief was
provider-confirmed as Telegram message 4395 with answer hash
`4608e2518bd22483d7158cdc3f2459a09c955bccb997e20fc040535df82d0a4a`.
Charl's supplied brief is accepted as evidence of delivery and improved wording.

It does not establish Anton's acceptance, completion of any farm operation,
business acceptance, or a canonical write. A separate recipient projection
exists, but this handover makes no identity inference from it.

The observer is passive and states
`business_acceptance_asserted: false`. Its morning collection has one retained
limitation: plan-hash verification raised `AttributeError` because the collected
`SimpleNamespace` did not contain `why`. Provider delivery and the saved
manager lifecycle are independently present; the failed verifier section means
the collection is not represented as complete.

Sanitized evidence is committed beside this handover in
`PR1336_SCHEDULED_OBSERVER_RESULT_20260916.json`. Raw evidence remains in the
existing private observation directory and is not copied into the repository.

## Farm finding

The backend reconciliation produced two clear results.

First, 74 is the current eligible/tagged cohort snapshot, with zero recorded
weights in the window and zero pigs explicitly marked
`individual_weighing_due_now`. It does not identify 74 pigs that need weighing.
Historical cohort membership cannot be reconstructed from the current snapshot.
A specific due-now lifecycle or a new farm instruction is required before an
individual weighing task exists.

Second, the backend contains 42 attributable historical mortality candidate
events: 14 stillbirth, 26 individual death and 2 crushed. None falls in the last
seven days. Five fall in the last 30 days and 40 in the last 90 days. The
historical records remain intact. The old aggregate has no evidence of current
work and should not be repeated each morning. A new event or an exact still-open
individual mortality lifecycle is required to reopen morning work.

Mysikind and Mona are distinct animals and remain distinct outcomes. The
qualified correction presents them separately and asks only one bound question
when a missing farm fact is needed.

## Worker execution and continuation

The qualified correction binds visible follow-through to the real
`oom_manager_cases` and `oom_manager_case_events` records. It reports whether
a worker is absent, queued, running, failed, delivered, checked with nothing new,
or deferred after a deadline. Later empty reassessment events no longer hide the
most recent actual outcome, and observation timestamps alone do not trigger a
replacement message.

An answer retires its exact bound task while preserving unrelated legitimate
questions. Every brief states that it did not record or complete farm work.
Unavailable operations stay unavailable until the relevant permission,
confirmation and physical fact exist. A preview or observation is never
presented as a saved farm update.

## Irrigation trace

C Camp execution `ROOTLINE-EXECUTION-0C182359F30AFE1ABE0D2F6F` has
authoritative controller ON at 00:35:16 SAST and OFF at 02:04:24 SAST. The native
stop deadline was 01:35 SAST. The stored 59.9833-minute value is a segment budget,
while the two observed boundaries span about 89 minutes. Neither value proves
actual water-flow duration or delivered volume; the brief must not report a
duration.

The nine relevant messages were eight ROOTLINE provider deliveries plus Charl's
morning brief. Six of the ROOTLINE messages were routine reassessment
notifications whose evidence alternated between forecast/live rain and dry
states. The direct start/stop rail already delivered verified boundaries.
Routine reassessment will now be silent. A genuine question or failed lifecycle
remains visible.

Verified state messages become exactly one concise icon line for ON and one for
OFF. The next morning brief includes the verified overnight boundaries. It does
not claim watering duration or volume.

## Concrete unpublished correction

Local commit `86bcee2709374353b7daf8d68bda839bac69337c`, tree
`8582052f2cab5bf1a7abc4d26c27ebb085c6e23b`, parent
`3d321e4932cf205d03e759cc71a26edd411bc9d2`, implements these bounded backend
and presentation changes. It changes no migration, workflow, selector,
permission or n8n logic.

Fresh qualification passed all 272 herd tests and 27 subtests against a new
database after preserving an earlier 271-pass attempt and correcting its
over-broad queue assertion. Exact change, qualification, hosted requirements and
rollback are in
`OOM_FARM_BRIEF_RUNTIME_CANDIDATE_DECISION_20260916.md`.

The candidate is local and unpublished. It needs exact runtime-candidate approval
before branch publication, refreshed admission, hosted checks, pull request,
merge or web-only deployment. The existing fixture-only successor permission
does not cover application runtime changes.

## Acceptance and holds

The deployed model probe remains successful and unrepeated. The scoped Telegram
reply-ID fix remains published. The current transport owner and backend
replacement boundary remain unchanged, and no n8n business logic was added.

Linda's genuine typed first question, delivered answer and contextual follow-up
remain pending. Anton's acceptance, a current-version genuine confirmation,
genuine cancellation, and one genuinely needed permitted farm update with saved
readback also remain pending. Historical callback effects remain reconciled and
must not be retried.

Migration, weaning, first-treatment, native voice, permission,
physical-operation, ROOTLINE and CHARLIE holds remain unchanged. A morning brief,
priority annotation, preview or observation is not completed farm work.

The next usable farm outcome after release is a morning brief containing current
priorities, relevant overnight irrigation evidence and one clear bound question,
without historical archive noise. Ordinary Linda read-only conversation remains
eligible now and does not wait for the scheduler or this runtime release.
