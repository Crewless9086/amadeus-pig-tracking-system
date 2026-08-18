# Oom Sakkie HERDMASTER management-round consumer

Status: source contract prepared; deployed-agent integration remains blocked
pending the exact shared runtime hook below.

## Outcome

`modules/oom_sakkie/herdmaster_management_adapter.py` is the single typed,
zero-I/O consumption boundary between HERDMASTER's deployed
`build_management_round` contract and Oom Sakkie's existing
`SpecialistResult` / `build_family_brief` kernel. It adds no router, queue,
webhook, table, Telegram path, or farm writer.

The boundary accepts only either a fresh private-owner gateway authority or a
sealed scheduled-manager context. It binds the authenticated owner hash,
management-round identity, deduplication key, evidence generation, specialist
contract version, trusted-clock-bounded invocation timestamp, invocation
context/mission digest, result digest, and active-case state.

## Current protected proof

- Pig 11 / `PIG-2026-E88A` is supplied as an active Oom Sakkie lifecycle and
  is excluded before HERDMASTER ranking. Card 3171 and its existing welfare
  case remain the sole owner interaction.
- Mona / `PIG-2026-D050` and Mysikind / `PIG-2026-21BE` remain operationally
  **Assumed Pregnant**, never clinically confirmed. Their proportional plan
  retains the approximate 22–26 August farrowing range and 8–15 August
  preparation window. Clinical scanning remains optional.
- Baby / `PIG-2026-7DAA` remains **Inconclusive**.
- At most three HERDMASTER actions become typed internal manager work items.
  Oom Sakkie's existing family brief performs the final cross-specialist
  consolidation and one-question limit.

## Replay and failure behavior

An exact prior consumption suppresses the replay with zero result packet,
work item, question, or card. Reuse of a publication/deduplication identity
with a changed result, evidence generation, invocation mission, or active-case digest fails closed
as one deterministic typed systemic exception. Authentication, freshness,
specialist availability, malformed output, and contract-version failures are
also contained only for HERDMASTER.

Conflicting prior rows fail closed independent of row order. Malformed active
lifecycle input is contained inside the zero-authority boundary.

The adapter always reports zero farm, mating, pregnancy, health, lifecycle,
movement and availability writes; zero Telegram sends/cards/questions; and
zero protected actions. HERDMASTER output remains internal specialist
evidence and never inherits delivery authority.

## Integration and production proof

The current source has no deployed caller. A terminal import of this module is
not deployed-agent activity and must not be represented as production proof.
Do not merge or deploy this PR until a reviewed integration adds all of the
following through existing infrastructure (no new router, queue, webhook or
table):

1. an existing authenticated generic-manager or scheduled-manager entrypoint;
2. authoritative current canonical-round and owner-observation loaders;
3. an authoritative active-lifecycle loader that proves card 3171 owns Pig 11;
4. prior-consumption loading plus durable binding recording/readback in an
   existing audit/lifecycle store; and
5. an end-to-end test through that deployed entrypoint.

### Exact shared-file integration handover

Do not use `owner_task_lifecycle` as a second dispatcher and do not add a
scheduled endpoint. Extend the existing deployed-agent entrypoint
`modules/agents/oom_sakkie.py::run_oom_sakkie` as follows:

- Add `gateway_authority` to the `run_oom_sakkie` request contract. Require a
  fresh, unbound `GatewayOwnerAuthority` issued by the existing authenticated
  gateway. Pass that sealed base authority unchanged to
  `consume_herdmaster_management_round`; the adapter performs the single
  `bind_gateway_owner_authority(..., "herdmaster_proactive_management_round")`
  operation. Never pre-bind and forward it, because an already-bound capability
  is intentionally rejected. `run_oom_sakkie` is not currently authenticated
  and must fail closed when this exact field is absent or invalid. A scheduled
  call must instead carry a sealed
  `ScheduledManagerContext` issued by `issue_scheduled_manager_context`; this
  handover adds no scheduler or scheduled endpoint. Immediately after the
  current HERDMASTER `herd_overview` delegation succeeds, call a new runtime
  coordinator in `modules/oom_sakkie/herdmaster_management_runtime.py` and
  merge its `SpecialistResult` into the existing Oom Sakkie manager result.
- The new runtime coordinator must call a new public read-only function in
  `modules/pig_weights/mating_routes.py` that returns the current
  `_build_breeding_attention_packets()["operating_loop"]`; it must reject an
  incomplete source snapshot and must not expose the private helper elsewhere.
- The same coordinator must load attributable pregnancy observations from a
  provenance-bound existing audit artifact. Repository/production inspection
  found no durable Mona/Mysikind/Baby observation artifact as of 2026-08-02;
  therefore this loader must fail closed until HERDMASTER supplies that
  artifact contract. It must never reconstruct those observations from this
  handover or tests.
- Load active HERDMASTER owner lifecycles from
  `public.sam_live_stock_conversation_review_events` using the existing
  `oom_sakkie_herdmaster_health_loss_runtime` event source and
  `review_json->'herdmaster_health_loss'`. Require current states
  `waiting_for_input` or `preview_ready`, exact pig identity, lifecycle mission
  identity and card identity. This is what must prove Pig 11/card 3171; no
  hardcoded animal/card exception is allowed.
- Reuse `public.sam_live_stock_conversation_review_events` for the consumption
  audit; do not add a table. Record `event_source =
  'oom_sakkie_herdmaster_management_consumer'`, deterministic
  `review_event_id`, and `review_json->'herdmaster_management_consumption'`
  containing only the adapter `binding`, accepted item identities and
  zero-authority flags. The readback query must select that JSON by
  management-round identity or deduplication key, ordered by `created_at,
  review_event_id`. Project every stored binding into the adapter's flat
  `prior_consumptions` schema: `management_round_identity`,
  `deduplication_key`, `result_digest`, `evidence_generation`,
  `active_case_digest = active_case_deduplication_state.digest`, and
  `invocation_context_digest = invocation_context.digest`. Pass every projected
  row, not the nested binding object. An existing conflicting row must contain
  the round.
- Do not reuse `_record_task_event` or `_load_task_events` with a false owner
  task identity. Reuse their existing audit-store persistence pattern and
  exact-once `review_event_id` behavior in the new runtime module.

Add `tests/test_oom_sakkie_herdmaster_management_runtime.py` with disposable
Postgres coverage for authenticated `run_oom_sakkie` consumption, anonymous
denial, incomplete canonical read, missing/mismatched pregnancy provenance,
Pig 11/card 3171 loading and suppression, durable binding readback, exact
replay, conflicting rows, process interruption between consume/record, zero
farm rows and zero Telegram/card/question effects. Add a regression to
`tests/test_oom_sakkie_operational_agent.py` that
the legacy `herd_overview` answer is unchanged when the proactive coordinator
returns a typed contained result. Add no registry, route or service-adapter
entry.

After that hook is reviewed, exact-head green, normally merged, exact-merge
green and deployed with exact lineage, invoke it once through a fresh
authenticated private-owner or scheduled-manager context. Assert:

1. exactly one internal manager result with no more than three actions;
2. Pig 11 is absent and no duplicate card/question/case exists;
3. Mona, Mysikind and Baby retain the semantics above;
4. farm-row and Telegram changes are zero; and
5. an identical replay returns `herdmaster_management_round_replay_suppressed`
   with zero new packets or work items.

If no manager action survives cross-specialist reconciliation, send no owner
card merely for proof. Release runtime immediately after proof or exact
containment.
