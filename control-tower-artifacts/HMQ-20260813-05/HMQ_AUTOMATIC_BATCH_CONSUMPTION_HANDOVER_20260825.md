# HMQ-20260813-05 automatic batch consumption handover

- Existing mission only: `HMQ-20260813-05` / `HMQ-20260813-00`.
- Classification: source repair; no owner outcome yet.
- Reused runtime: existing five-minute Oom Sakkie general-manager worker and
  canonical `app_private.oom_manager_cases` lifecycle.
- Input boundary: completed `bulk_weight_batches`, their exact
  `pig_weight_events`, and exact `pig_observation_events` keyed by the accepted
  draft/pig identity.
- Output boundary: one stable BCS case and one stable material-weight case per
  exact pig, using only the deterministic latest qualifying canonical event
  across completed batches, with exact evidence references, generation/idempotency protection,
  bounded reassessment, and terminal completion only from newer qualifying
  canonical evidence.
- Preserved safeguards: read-only collection, no heat inference, no diagnosis,
  no batch replay, no new queue/store/schema/scheduler, no provider or farm
  effect during source preparation.
- Release acceptance: reviewed merge and exact deploy; one natural worker cycle
  must create/advance the supported exact-pig cases from canonical evidence;
  readback must prove no duplicate case/event; a later independent cycle must
  be an exact replay while follow-up remains durably owned.
- Owner action: none.
