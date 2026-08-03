# CHARLIE CORE adaptive minimal-dispatch handover

Status: source-only candidate. No queue record, runtime, dispatch, Telegram message, production write, merge or deployment is created by this contract.

## Outcome

A future natural CHARLIE development request follows one existing CORE path:

1. CHARLIE normalizes the objective into the existing mission contract.
2. `bounded_coordination_score()` produces one deterministic score from six 0–4 factors: business impact, urgency, operational risk, scope breadth, evidence uncertainty and required authority.
3. `build_orchestration_packet()` maps the score to T0–T4 and selects the smallest capable role set. A simple source correction uses one worker. Domain or protected reviewers are added only by evidence triggers.
4. `plan_development_dispatch()` creates a `proposed` plan. It does not release or dispatch anything.
5. Only Charl or private executive CHARLIE may append owner authorization and release. Oom Sakkie operational authority cannot grant CORE code or production authority.
6. Release remains `released`, not pickup. A worker must return a durable dispatch acknowledgement and matching start receipt before CORE reports pickup or progress.
7. Missing acknowledgement produces one deterministic contained exception. Ambiguous external effects are contained and never automatically retried.
8. Completion requires exact artifact evidence, a measurable business outcome or literal `NO BUSINESS OUTCOME` with a reason, and the next dependency.

Implementation: `modules/charlie/adaptive_orchestration.py` and `modules/charlie/development_coordination.py`. This reuses the existing mission workflow, event ledger, runner heartbeat and final-artifact ingestion boundaries. It does not create a second queue, dispatcher or CORE.

## Deterministic tier and team policy

| Tier | Meaning | Minimum base team |
|---|---|---|
| T0 | Read-only inspection | `source_mapper` |
| T1 | Small bounded source change | `builder` |
| T2 | Multi-step bounded change | `builder`, `tester` |
| T3 | Cross-module/uncertain CORE change | `source_mapper`, `technical_architect`, `builder`, `tester`, `reviewer` |
| T4 | Protected authority or high consequence | T3 safety path plus `qa_red_team`, `publisher`, and only triggered domain/security/evidence/business reviewers |

UI, security, database, customer, financial, hardware, publication, farm and sales triggers add only their required specialist roles. The selected workflow is generation-bound using the existing adaptive orchestration binding.

## Explicit state contract

`proposed → owner_authorized → released → acknowledged → started → waiting_for_evidence → completed_with_artifact`

Exceptional terminals are `contained` and `genuinely_blocked`. `genuinely_blocked` requires the same blocker at least three times plus proof that owner input or external-state change is required. Release never implies acknowledgement, start or completion.

Each acknowledgement binds `worker_id`, `dispatch_id` and `acknowledged_at`. Start must bind the same dispatch ID and `started_at`. Duplicate/circular worker handoffs and overlapping predecessor/successor bindings fail closed.

## Completion contract

```json
{
  "business_outcome": "Measurable result, or NO BUSINESS OUTCOME",
  "outcome_reason": "Required when there is no business outcome",
  "artifact_evidence": ["exact path/revision/result identity"],
  "next_dependency": "exact dependency id or null"
}
```

An artifact can close dependent work only when its `next_dependency` matches. A process exit, release, heartbeat or prose claim cannot substitute for the completion artifact.

## S02–S07 reconciliation at deployed `0b620632`

| Proposal | Current disposition | Delivered value removed | Smallest preserved post-P0 value |
|---|---|---|---|
| S02 HERDMASTER adapter | Conditional residual; do not create broadly | Natural health/loss intake, evidence-bound previews, proactive management rounds and Oom consumption are deployed | Only acceptance-proven exactly-once recording or specialist adapter defects |
| S03 ROOTLINE management | Operational acceptance/commissioning first | Current plan, supervised execution contract and governed commissioning decision are deployed | Physical commissioning/acceptance remains separately owner governed; source mission only for a proven reusable defect |
| S04 SAM Livestock | Preserve as post-P0 software candidate | Existing narrow livestock and delivery-truth rails remain baseline | Typed Oom manager evidence/owner-attention adapter and continuous narrow proof |
| S05 BEACON organic | Preserve as post-P0 software candidate | Existing owner-gated organic publication and analytics rails remain baseline | Typed Oom manager evidence plus repeatable two-cycle organic proof |
| S06 BEACON paid boost | Deferred | No paid authority inferred | Activate only after S05 organic evidence and exact spend authority |
| S07 CORE reliability | Replaced by focused capability slices | Adaptive packets, generation binding, final-artifact ingestion and PR #680 replacement rail already exist | This minimal-dispatch/receipt correction only; no legacy always-on programme |

Smallest post-P0 programme: first finish Oom Sakkie P0 acceptance. Then create no S01 when it passes; activate only an acceptance-proven S02/S03 residual if one exists; otherwise proceed independently with S04 and S05. Keep S06 deferred. Integrate this focused S07 slice and PR #680 only through their separate owner review/release gates.

## Controlled activation proof still required

After owner-reviewed integration, use a disposable or explicitly authorized canary mission—not a legacy production mission—to prove: one proposal, one authorization, one release, one worker acknowledgement, one matching start, heartbeats while running, and one completion artifact. A missing acknowledgement must produce exactly one exception. Production pickup must remain disabled until that proof and a separate owner activation decision.
