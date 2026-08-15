# HERDMASTER weighing-batch intelligence source handover — 2026-08-11

## Stage and scope

Prepared (20%) only. This source adds no migration, writer, route ownership, Telegram callback, queue, dashboard, deployment, or production claim. It extends the existing Weight Report with a deterministic read-only packet when an exact completed canonical `bulk_weight_batches.batch_id` is supplied.

## Canonical boundary

- The requested batch must have `status = complete`; otherwise analysis fails closed.
- Successful batch rows and linked weight events are the measured evidence.
- Previous comparisons use only an attributable weight strictly earlier than the batch date.
- Expected coverage is bound to the immutable pig identities and batch-time `from_pen_id` values in the completed batch manifest. Later movement/current-location changes cannot rewrite the denominator, pen grouping, digest, or replay identity. Missing measurements remain `null`/Unknown, never zero.
- Completed counters, unique audit rows, weight-bearing rows, and their exact canonical event bindings must reconcile before analysis; any truncation or duplicate binding fails closed.
- Attributable contextual evidence retains source identity and observation time and is labelled Associated, never causal.
- Optional growth thresholds must be supplied as evidence; the evaluator invents no universal threshold.

## Deterministic output

The packet contains coverage, comparable change and elapsed days, supported rate, gain/loss/unchanged/slow-growth/no-comparison groups, repeated decline, reweigh flags, pen/cohort patterns, missing expected animals, at most three findings, and at most one grouped Afrikaans question. Its digest binds the batch, rows, histories, expected population, context, and correction lineage. Unchanged replay returns the same identities and performs zero I/O.

## Existing Weight Report integration

The existing `/weight-report` page and API accept optional `batch_id`. Without it, existing behavior is unchanged. With it, the page prints HERDMASTER metrics, labelled findings, next actions, and the concise Afrikaans summary. No competing report or dashboard was created.

## Read-only reconciliation evidence

The owner-provided 2026-08-11 D3 facts (Bonnie 64.4 kg, Waki 70.0 kg, Zigay 71.4 kg, Teena 69.2 kg) are read-only fixture values only. They are not a completed business proof and authorize no Telegram summary.

## Future integration and operational proof

After OOM SAKKIE explicitly releases the overlapping production scope:

1. Merge the reviewed exact head through the serialized lane; require exact-merge CI and deployment lineage.
2. For a genuine new completed batch, open the existing report using its exact `batch_id`.
3. Publish through the existing specialist-consumption boundary; add no router or callback.
4. Prove one printable report and one provider-confirmed summary with at most three findings and one grouped question.
5. Prove correction lineage and unchanged replay create no duplicate alert, summary, question, or farm effect.
6. Prove zero unrelated weight, movement, feed, treatment, purpose, lifecycle, sale, mating, message, or hardware mutation.

Business-complete requires that future genuine batch outcome. Source, tests, review, PR, CI, merge, and deployment alone do not satisfy it.
