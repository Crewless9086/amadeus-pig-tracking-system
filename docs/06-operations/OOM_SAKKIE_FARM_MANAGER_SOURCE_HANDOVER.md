# Oom Sakkie Farm Manager Source Handover

Status: source-ready coordination kernel; not integrated, merged, deployed, or
operationally proven.

Evidence cut: 2026-07-30 at `origin/main` revision `0ee4d7b8`. Repository truth
only. No production service, farm
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
| SAM Livestock | Current main contains the unified offer composition, Customer Front Door, protected continuous-follow-up and inbox-operator contracts. These remain SAM-owned integration work, not an Oom Sakkie input adapter. | SAM can reason about live-pig conversations, chronology and source-bound availability. Oom Sakkie's canonical shared agent does not consume these results. | SAM owns customer conversation evidence and protected send/order/reservation gates. The coordination kernel may rank a supplied SAM result but cannot invoke or advance the lane. | No normalized read-only family-manager adapter. SAM owns its domain reasoning and active serialized production lane. |
| HERDMASTER | Canonical shared-agent results expose direct answers, facts, source authority, observed freshness and confidence. Ordinary herd questions now include bounded pregnancy-evidence freshness while remaining read-only. | Canonical Oom Sakkie can delegate ordinary farm questions to Herdmaster and return its answer. | Specialist evidence includes missing facts and advisory actions; the isolated kernel can assign and reassess supplied follow-ups without changing herd state. | This remains the only canonical delegation currently wired. The daily family brief is not wired. |
| ROOTLINE | `rootline_specialist_result_v1` now exposes stable identity, evidence cutoff, per-source provenance/freshness, recommendations, next reassessment, at most one genuine question, and explicit zero-command authority. | Rootline can explain water continuity, weather versus forecast, solar reserve, grid cost, holds and evidence gaps without commanding hardware. | The isolated kernel can consume equivalent typed signals and prevents stale/unsupported ROOTLINE conclusions from suppressing supported sales, herd or marketing work. | No Oom Sakkie adapter is wired; the dedicated ROOTLINE contract explicitly defers shared integration until the serialized queue is released. |
| BEACON | Structured media and marketing evidence remains behind separate gates. The latest activation handover records a contained timeout and explicitly confirms no READY, photo request, media ingestion, publication or spend outcome. | Beacon can recommend marketing only when current fulfilment and usable-media evidence support it. | Contained/disabled/missing BEACON state blocks only its own unsupported conclusion in the coordination kernel. | No normalized family-manager adapter. Activation, Telegram, Render and GateKeeper remain excluded. |
| SAM Meat | Structured readiness, truth snapshot, commercial standard, matching, fulfilment, and reconciliation evidence exists in pilot rails. | SAM Meat can prepare owner-reviewable commercial evidence, while all sends, money, reservations, allocation, slaughter, and fulfilment commitments stay protected. | Specialist rails retain their own state; Oom Sakkie has no consolidated commercial follow-up view. | No normalized result adapter or deduplication with SAM Livestock/customer work. Include only when a current meat exception or high-value action exists. |

Prepared/deployed specialist results are deliberately not labelled integrated.
The current canonical `modules/agents/oom_sakkie.py` delegates only to
Herdmaster and returns that specialist's answer.

## Prepared source

`modules/oom_sakkie/farm_manager_loop.py` adds stable typed, pure contracts:

- provenance-bound specialist results, work items, supported answers, and
  promised follow-ups;
- one deterministic cross-domain queue;
- no more than three ranked actions per family member;
- explicit urgent, due-today, planned, waiting-evidence, and protected-owner
  states;
- suppression of completed, handled, stale, duplicated, and unusable-media
  work;
- customer/exception work before internal housekeeping;
- one relevant per-family view and at most one genuine question per person;
- evidence-only conversational answers;
- reassessment of promised follow-ups when a new structured result arrives;
- explicit specialist availability (`available`, `stale`, `disabled`,
  `missing`, `contained`) so a specialist gap blocks only conclusions that
  depend on it;
- automatic demotion of customer, money, farm-write, publication, and hardware
  actions to protected owner decisions;
- no imports of database, route, network, filesystem, channel, or specialist
  execution services.

`tests/test_oom_sakkie_farm_manager_loop.py` proves prioritisation,
deduplication, specialist provenance, family relevance, supported and
unsupported answers, minimal questions, protected boundaries, follow-up
reassessment, per-person action caps, partial specialist failure containment,
and zero writes.

Independent final review: product/farm-operations approved the bounded
source-only target after transitive dependency propagation and provenanced
multi-input water/energy coordination were added. Backend/security/privacy
approved after future-evidence, resolution ownership, provenance, protected
action, privacy, determinism, and zero-I/O boundaries were hardened.

The 2026-07-30 continuation was independently re-reviewed and approved after
adding the three-action family cap, single-render concise brief, typed
specialist availability, AVAILABLE-only signal/resolution consumption,
ROOTLINE-owned point-in-time coordination signals, future/stale containment,
and regression proof that one unavailable specialist does not erase healthy
work from other lanes.

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

## Demand-to-weighing coordination packet

Evidence cut: SAM release handover
`C:/tmp/sam-pr623-shadow-release-20260730.md`, read on 2026-07-30.

Current exact state:

- real read-only customer chronology was evaluated in six shadow cases;
- SAM proved that incomplete current sale-eligible inventory evidence blocked
  availability-bearing reassessment and calculated alternatives;
- the handover does not expose the individual customer requirements needed for
  a family brief;
- no forthcoming HERDMASTER sale-inventory reconciliation handover is present
  in this worktree or the supplied `C:/tmp` handover set;
- therefore usable inventory, exact animals to weigh, and customer opportunity
  counts remain `Unavailable`; none are inferred from SAM examples or historical
  animal files.

`build_sales_weighing_packet()` is the prepared pure coordination seam. It
accepts only:

1. fresh, provenance-bound SAM demand evidence containing quantity, sex,
   supported weight range, needed-by time and bounded commercial priority; and
2. fresh, provenance-bound HERDMASTER inventory evidence stating whether an
   opaque animal reference is usable now, blocked, or sale-eligible except for
   a fresh weight, plus the demand identities it can potentially support.

It then:

- separates `usable inventory now`, `weigh next`, `customer opportunity
  unlocked`, and protected decisions;
- ranks at most three measurements by the sum of source-supplied commercial
  value and time urgency across compatible current demands;
- suppresses completed, stale, blocked, unmatched and lower-ranked work;
- assigns weighing only to Dad in the prepared default family packet and
  performs no animal write;
- asks no family question when the missing item is specialist evidence rather
  than a genuine family fact;
- emits one automatic read-only follow-up instruction: after fresh measurements
  return, HERDMASTER re-verifies eligibility and freshness, then only verified
  inventory returns to SAM for offer reassessment.

The follow-up instruction is descriptive coordination output. It does not
dispatch HERDMASTER, call SAM, write weights, send a customer, reserve an
animal, promise stock or approve an offer.

Independent product/farm-operations and backend/security/privacy review
approved this demand-to-weighing addition after evidence freshness,
sex/weight compatibility, privacy-safe labels, duplicate containment,
observation-versus-persistence wording, and quantity-aware matching were
hardened. The final selector uses deterministic maximum-cardinality matching
so flexible animals do not create unnecessary weighing when a less-flexible
animal can satisfy the same remaining demand.

### Finalization gate when HERDMASTER arrives

Accept the handover only when:

- its specialist/result identity is HERDMASTER-owned;
- observation and weight timestamps are timezone-aware, non-future and inside
  the agreed freshness window;
- every opaque animal reference carries explicit `usable_now`,
  `needs_fresh_weight` or `blocked` state;
- `needs_fresh_weight` states affirm that other sale-eligibility evidence is
  complete rather than treating missing evidence as clearance;
- compatible demand identities bind to the fresh SAM packet;
- completed or superseded work is explicit;
- no raw customer identity, farm location, protected medical detail or
  executable action is embedded.

Until those checks pass, the exact concise brief is:

> Usable inventory now: unavailable. Weigh next: no supported animal task yet.
> Customer opportunity unlocked: awaiting matched fresh SAM demand and
> HERDMASTER inventory evidence. Protected decisions: all customer sends,
> reservations, orders and stock commitments remain with Charl and SAM's
> governed rails.

## Mission stage and measurable outcome

Stage: independently reviewed source coordination kernel and acceptance proof.
Estimated mission completion: 86%. Remaining work is shared adapter
integration after claim release and the production proof above.

Expected family outcome: in the first supervised proof, one brief gives each of
the three family members no more than three relevant current actions and no
more than one genuine question, with zero duplicated/completed tasks and zero
protected actions executed.
