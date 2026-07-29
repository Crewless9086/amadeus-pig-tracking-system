# Oom Sakkie Farm Manager Source Handover

Status: source-ready coordination kernel; not integrated, merged, deployed, or
operationally proven.

Evidence cut: 2026-07-29 repository truth only. No production service, farm
data, Telegram, n8n, Render, customer channel, or hardware was read or changed.

## Governance note

The requested
`docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md` is
absent from this worktree. This source slice therefore applies the present
mandatory `AGENTIC_ARCHITECTURE_STANDARD.md`, `AGENT_AUTHORITY_MATRIX.md`,
Oom Sakkie doctrine, `NEXT_STEPS.md`, the implementation source map, and the
dated portfolio/claim evidence. The missing named standard must be reconciled
before production integration; this slice does not recreate or guess it.

## Current capability and genuine gap map

| Specialist | Structured result Oom Sakkie can receive today | Understand / answer / recommend | Remember / follow up / escalate | Genuine Oom Sakkie integration gap |
| --- | --- | --- | --- | --- |
| SAM Livestock | SAM runtime, launch-control, evaluation, order-context, and Herdmaster exact-eligibility structures exist. | SAM can reason about supervised live-pig conversations and source-bound availability. Oom Sakkie's canonical shared agent does not consume these results. | SAM owns customer conversation evidence and protected send/order/reservation gates. Oom Sakkie has no durable cross-domain follow-up binding. | No normalized result adapter, farm-queue ingestion, supported-answer binding, or family brief integration. SAM owns its domain reasoning and serialized production lane. |
| HERDMASTER | Canonical shared-agent result, daily brief, breeding, litter, growth, and exact-eligibility structures exist. | Canonical Oom Sakkie can delegate ordinary farm questions to Herdmaster and return its answer. The older local service has deterministic Herdmaster tools. | Specialist evidence includes missing facts and advisory actions; Oom Sakkie does not reconcile those with other domains or maintain promises. | This is the only canonical delegation currently wired. It remains a pass-through rather than farm management. |
| ROOTLINE | Deployed owner-only structured Daily Brief and built read-only Daily Advisor structures exist. | Rootline can explain weather, water, irrigation, power, freshness, holds, and evidence gaps without commanding hardware. | Rootline can expose unresolved owner decisions, but Oom Sakkie does not collect or reassess them. | No Oom Sakkie result adapter, question-answer binding, queue ingestion, or water/energy versus weather/solar/grid reconciliation. |
| BEACON | Structured media, opportunity, owner-review, publication-binding, learning, and performance evidence exists behind separate gates. | Beacon can recommend marketing work when fulfilment and approved usable media support it. Oom Sakkie cannot currently distinguish a usable request from premature media administration. | Beacon owns its evidence and publication gates; no Oom Sakkie follow-up linkage exists. | No normalized result adapter, usable-media condition, family assignment, or current-work suppression in Oom Sakkie. Media intake is built-only/default-disabled and is not integration proof. |
| SAM Meat | Structured readiness, truth snapshot, commercial standard, matching, fulfilment, and reconciliation evidence exists in pilot rails. | SAM Meat can prepare owner-reviewable commercial evidence, while all sends, money, reservations, allocation, slaughter, and fulfilment commitments stay protected. | Specialist rails retain their own state; Oom Sakkie has no consolidated commercial follow-up view. | No normalized result adapter or deduplication with SAM Livestock/customer work. Include only when a current meat exception or high-value action exists. |

Prepared/deployed specialist results are deliberately not labelled integrated.
The current canonical `modules/agents/oom_sakkie.py` delegates only to
Herdmaster and returns that specialist's answer.

## Prepared source

`modules/oom_sakkie/farm_manager_loop.py` adds stable typed, pure contracts:

- provenance-bound specialist results, work items, supported answers, and
  promised follow-ups;
- one deterministic cross-domain queue;
- explicit urgent, due-today, planned, waiting-evidence, and protected-owner
  states;
- suppression of completed, handled, stale, duplicated, and unusable-media
  work;
- customer/exception work before internal housekeeping;
- one relevant per-family view and at most one genuine question per person;
- evidence-only conversational answers;
- reassessment of promised follow-ups when a new structured result arrives;
- automatic demotion of customer, money, farm-write, publication, and hardware
  actions to protected owner decisions;
- no imports of database, route, network, filesystem, channel, or specialist
  execution services.

`tests/test_oom_sakkie_farm_manager_loop.py` proves prioritisation,
deduplication, specialist provenance, family relevance, supported and
unsupported answers, minimal questions, protected boundaries, follow-up
reassessment, and zero writes.

Independent final review: product/farm-operations approved the bounded
source-only target after transitive dependency propagation and provenanced
multi-input water/energy coordination were added. Backend/security/privacy
approved after future-evidence, resolution ownership, provenance, protected
action, privacy, determinism, and zero-I/O boundaries were hardened.

## Shared-file integration handover

Do not make these edits while another active claim owns them. A later,
separately authorized integration should:

1. Add read-only adapter functions in a new
   `modules/oom_sakkie/farm_manager_adapters.py`. Each adapter must call the
   specialist's canonical structured reader and translate only contract
   fields; it must not parse rendered prose.
2. Edit `modules/agents/oom_sakkie.py` so `farm_operating_brief` collects the
   approved adapters, passes their results to `build_family_brief`, and retains
   the existing Herdmaster delegation for supported herd questions. Preserve
   `write_authority=False`.
3. Edit `modules/oom_sakkie/tools.py` only if the older direct-channel runtime
   remains an approved surface: register a read-only `farm_manager_brief` and
   evidence-answer tool with no risk-level increase.
4. Edit `modules/oom_sakkie/service.py` only to route the existing operating
   brief intent to that read-only tool. Do not add a dashboard, form, route,
   sender, scheduler, poller, persistence path, or background loop.
5. Add adapter contract tests and extend
   `tests/test_oom_sakkie_operational_agent.py` and
   `tests/test_oom_sakkie_service.py` to prove missing/stale sources fail
   closed, each specialist retains provenance, protected actions remain
   decisions, and no write-capable function is called.
6. Any later Telegram delivery requires a separate owner-authorized change to
   the presently claimed gateway/routing files and a recipient/privacy review.
   This handover grants no such authority.

No registry, route, service, Telegram, GateKeeper, Render, n8n, CI,
configuration, migration, or production file is changed in this source slice.

## Exact later production proof

After shared-file ownership is released and integration is separately
authorized:

1. Bind one current, structured result from SAM Livestock, HERDMASTER,
   ROOTLINE, and BEACON; bind SAM Meat only if it has current actionable work.
2. Record result IDs, source references, observation times, confidence, and
   freshness without copying private identities into the proof packet.
3. Generate one owner-authenticated, read-only family brief.
4. Verify the highest-value current customer/exception, herd, water/energy,
   and usable-media priorities appear once, with why, assignee, next action,
   and specialist provenance.
5. Verify completed, stale, duplicate, already-handled, irrelevant
   infrastructure, and unusable-media work does not appear.
6. Ask Charl, Dad, and Mom to confirm that each sees only relevant work and no
   more than one genuine missing question.
7. Re-run with one newly arrived specialist result and prove the matching
   promised follow-up is reassessed rather than duplicated.
8. Audit database/query logs and mocks to prove zero POST/PATCH/DELETE,
   customer sends, money actions, animal/farm writes, public posts, migrations,
   n8n/Render invocations, and hardware commands.

## Mission stage and measurable outcome

Stage: independently reviewed source coordination kernel and acceptance proof.
Estimated mission completion: 78%. Remaining work is shared adapter
integration after claim release and the production proof above.

Expected family outcome: in the first supervised proof, one brief gives each of
the three family members no more than three relevant current actions and no
more than one genuine question, with zero duplicated/completed tasks and zero
protected actions executed.
