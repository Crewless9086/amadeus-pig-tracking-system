# CHARLIE Always-On Executive Programme

Status: planned, logged, not approved for execution  
Owner: Charl  
Executive: CHARLIE  
Execution system: CORE  
Plan date: 2026-07-20  
Programme mission: `CHARLIE-ALWAYS-ON-EXECUTIVE-OS-20260720`  
Existing related mission: `CHARLIE-EXECUTIVE-ATTENTION-NOTIFICATION-20260720`

## 1. Executive outcome

CHARLIE must operate as Charl's always-on digital executive across the whole Amadeus business and agent workforce. CHARLIE must continuously observe business truth, compare it with owner goals, decide what can safely proceed, coordinate the correct domain agents, keep CORE supplied with useful work, recover failures without looping, and ask Charl only for decisions that genuinely require owner authority.

The outcome is not constant activity for its own sake. The outcome is continuous, evidence-backed progress toward measurable owner goals without silent idle time, duplicated work, fabricated priorities, or weakened safety gates.

## 2. Non-negotiable role separation

- CHARLIE is the private executive, portfolio governor, coordinator, prioritiser and owner interface.
- CORE is the governed mission engine used to plan, build, test, review, release and verify system work.
- Domain agents own their business reasoning: SAM owns sales conversations, Ledger owns financial truth, Herdmaster owns herd decisions, Butcher owns processing and fulfilment reasoning, Beacon owns marketing, and future agents own their declared domains.
- Deterministic services validate calculations, permissions, state transitions, audit records and protected actions.
- Charl owns goals, capital allocation, material business discretion and red-zone authority.
- CHARLIE must not absorb domain reasoning into question-specific executive handlers.

## 3. Definition of always on

At every executive tick, CHARLIE must be in one observable operating state:

1. `executing` — one or more missions are running.
2. `supervising` — work is healthy and CHARLIE is tracking evidence, deadlines and next gates.
3. `recovering` — a bounded internal recovery strategy is active.
4. `waiting_owner_parallel` — a protected decision is waiting for Charl while unrelated safe work continues.
5. `discovering` — CHARLIE is querying domain observers because no suitable runway exists.
6. `planning` — evidence is being converted into a bounded candidate mission.
7. `briefing` — no safe action remains and CHARLIE is explaining the exact owner decision or evidence gap.
8. `incident_hold` — execution is intentionally halted because continued operation could corrupt truth or exceed authority.

There must be no unlabelled idle state. `waiting_owner_parallel` must not freeze the portfolio. `incident_hold` must be rare, explicit, auditable and accompanied by a recovery requirement.

## 4. Current-state baseline and known gaps

What exists now:

- A Windows scheduled executive watchdog runs approximately every minute.
- Executive mode is active.
- CHARLIE can inspect CORE mission statuses and issue bounded control commands.
- Delegated policies currently permit automatic queue selection, queue continuation and low-risk final review.
- CORE can execute approved missions, preserve evidence, recover leases and run release processing.
- Read-only observers exist for SAM learning, Ledger payment exceptions, Herdmaster sales readiness and Beacon review backlog.

What is incomplete:

- Business coverage is narrow and is not a complete view of every agent or operating domain.
- Butcher has no dedicated executive observer.
- SAM observations focus on learning aggregates, not a clean sales pipeline and attention model.
- Ledger observes order payment exceptions but not a full cash, margin, receivables and commitment view.
- Herdmaster observes summary readiness counts but not animal-level exceptions, breeding risks, welfare, lifecycle or human observations.
- Beacon observes a media backlog but not the complete opportunity-to-campaign-to-lead-to-revenue loop.
- System health, deployments, data freshness, integrations and agent runtime health are not unified into the executive portfolio.
- A protected or unsuitable `new` mission can prevent an idle brief while still being ineligible for automatic selection.
- Recommendations are consulted mainly when the portfolio is fully idle, rather than continuously competing on business value.
- Notification idempotency can suppress a newly actionable decision when an older alert exists for the same mission.
- Owner attention currently mixes decisions, information, learning signals and duplicated conversation events.
- Mission priority metadata is incomplete, which weakens goal and revenue ranking.

## 5. Target executive architecture

```text
Owner goals and authority
          |
          v
CHARLIE Executive Control Plane
  |-- Goal ledger and KPI gaps
  |-- Portfolio state machine
  |-- Authority and trust policy
  |-- Opportunity/risk ranking
  |-- Owner attention manager
  |-- Recovery and anti-loop governor
          |
          +------------------------------+
          |                              |
          v                              v
Domain Observer Registry             CORE Mission Engine
  |-- SAM                              |-- plan/build/test/review
  |-- Ledger                           |-- evidence and handoffs
  |-- Herdmaster                       |-- PR/release/deploy
  |-- Butcher                          |-- monitoring and lessons
  |-- Beacon
  |-- farm operations
  |-- system/deployment health
          |
          v
Canonical Vault evidence and audit records
```

CHARLIE coordinates agents through evidence contracts. He does not replace them.

## 6. Standard domain observation contract

Every registered agent/domain must publish a versioned observation containing:

- `observer_id` and owning agent;
- observation timestamp, source timestamp and freshness status;
- facts and canonical source references;
- material changes since the last observation;
- opportunities;
- risks, incidents and exceptions;
- active commitments and due dates;
- decisions required;
- recommended next actions;
- expected goal, customer, operational or financial impact;
- confidence and missing evidence;
- authority tier required;
- deduplication/entity key;
- whether a mission already exists for the same condition;
- expiry or recheck time.

An unavailable observer must publish an explicit `unknown` or `stale` state. Silence must never be interpreted as health.

## 7. Required observer coverage

| Domain | Required executive truth | Initial actions CHARLIE may take |
| --- | --- | --- |
| CORE | queue, active stage, lease, progress, blocks, PR, release, deployment, loops | continue, recover, rank, escalate exact decision |
| SAM Live Stock | lead stage, unanswered conversations, proposed replies, stock/price evidence, conversion loss, owner corrections | request missing evidence, create safe improvement mission, escalate exact customer send |
| SAM Meat | controlled-learning state, launch locks, enquiries, missing facts, repeated objections | learn, research, propose; never open meat sales without owner authority |
| Ledger | orders, receivables, payment exceptions, pricing gaps, cash commitments, margin evidence | reconcile and propose; protected money decisions remain owner-gated |
| Herdmaster | sale readiness, breeding/welfare exceptions, lifecycle gaps, purpose conflicts, human observations | create review/planning missions; protected lifecycle/purpose writes remain owner-gated |
| Butcher | processing readiness, capacity, booking dependencies, yield and fulfilment exceptions | plan and reconcile; bookings/instructions remain governed |
| Beacon | campaign opportunities, content backlog, review state, lead attribution, performance and revenue evidence | research and prepare; public publishing remains owner-gated unless separately delegated |
| Farm operations | feed, water, irrigation, maintenance, compliance, deadlines and data freshness | create operational missions and alerts within policy |
| System health | agent heartbeat, scheduled tasks, integrations, credentials state without secret exposure, deployment and database health | bounded recovery, incident mission, exact owner escalation |

New agents must register an observer contract before CHARLIE can claim executive oversight of them.

## 8. Goal and portfolio model

Each mission and recommendation must bind to:

- an active owner goal;
- one measurable outcome or risk reduction;
- an owner or delegated authority tier;
- a responsible agent;
- an evidence source;
- a due date or review horizon;
- an expected value hypothesis;
- dependencies and conflicts;
- a completion measure.

CHARLIE must maintain a rolling runway target of three useful items: active work plus approved runnable work. Three is a control target, not a reason to approve weak work.

Priority scoring must consider:

- owner goal alignment;
- revenue creation or cash protection;
- customer impact and time sensitivity;
- animal welfare, compliance and operational risk;
- blocker removal and dependency leverage;
- evidence strength and freshness;
- estimated effort and reversibility;
- confidence;
- duplicate/conflict penalties.

The score and explanation must be stored. A deterministic score may shortlist work, but CHARLIE must produce a reasoned recommendation from domain evidence.

## 9. Continuous executive decision loop

Every bounded executive cycle must:

1. Load active goals, policies, trust tiers and current portfolio truth.
2. Check runner, agent, integration and evidence freshness health.
3. Reconcile missions with authoritative external state such as GitHub and deployment records.
4. Detect stalled work, repeated backflow, expired leases and identical failures.
5. Continue or recover existing work inside policy.
6. Identify protected decisions and place them in the owner attention queue.
7. Continue unrelated safe work while those decisions wait.
8. Calculate the useful execution runway.
9. Query all domain observers, even when CORE is busy.
10. Deduplicate observations against missions and prior observations.
11. Rank evidence-backed opportunities, risks and goal gaps.
12. Convert suitable items into bounded candidate missions.
13. Automatically approve only candidates permitted by policy and trust.
14. Start or wake CORE when runnable work exists.
15. Write the executive state, commands, evidence and outcomes to the Vault.
16. Notify Charl only when the attention policy requires it.

If no safe mission can proceed, the cycle must end in `briefing` with an exact explanation. It may not silently return because `new` rows exist.

## 10. Authority lanes

### Lane A — autonomous

CHARLIE may select and start work when it is evidence-backed, reversible, within a live delegation policy, below the configured risk limit and free of protected surfaces.

### Lane B — investigate before selection

CHARLIE may commission read-only research, request agent evidence, improve acceptance criteria, split an oversized mission, identify dependencies and create an unapproved proposal.

### Lane C — owner decision

CHARLIE must request Charl's decision for customer sends, public posts, payments, deposits, refunds, reservations, stock commitments, lifecycle or purpose writes, destructive actions, credentials, permission changes, migrations, material capital allocation, legal/compliance discretion and any policy explicitly reserved for Charl.

Lane C must not block Lane A work unless there is a real dependency.

## 11. Mission generation standard

CHARLIE may create a mission only when it contains:

- a specific problem and desired business outcome;
- owner-goal linkage;
- canonical evidence and freshness;
- responsible domain agent and supporting agents;
- bounded scope and explicit exclusions;
- acceptance criteria that can be proven;
- protected actions and authority requirements;
- dependencies;
- verification and rollback expectations;
- duplicate/family identity;
- a recommendation explaining why this work outranks alternatives.

Low-quality observations remain research items, not executable missions.

## 12. Owner attention and communications

The attention system must separate:

1. `decision_required` — Charl must approve, reject or choose.
2. `exception` — a material risk or failure needs awareness.
3. `executive_update` — progress completed or materially changed.
4. `recommendation` — ranked next work awaiting discretion.
5. `learning_only` — retained for agent improvement and excluded from urgent approvals.
6. `no_action` — resolved or informational evidence.

Every decision message must state:

- what changed;
- why it matters to an owner goal;
- CHARLIE's recommendation and confidence;
- evidence and material risks;
- the exact decision requested;
- what approval authorises;
- what approval does not authorise;
- what CHARLIE will do next;
- a dashboard link and working controls.

Notification identity must include mission, actionable state, decision class, candidate revision/review generation and material risk fingerprint. Delivery must store queued, claimed, sent, failed, retrying and dead-letter states. Unresolved high-priority decisions must use bounded reminders without spam.

## 13. SAM attention cleanup

SAM items must be grouped by canonical conversation/customer and current unresolved need. Older superseded events must remain audit history but not duplicate the active attention item.

SAM classifications must include:

- reply ready for owner send decision;
- edit required;
- owner handoff required;
- one missing fact to request;
- no reply/natural close;
- protected payment/order/stock decision;
- learning-only owner correction;
- recurring pattern for an improvement mission.

Learning-only signals must feed SAM evaluation, prompts, tests and lessons. They must not masquerade as customer decisions.

## 14. Recovery, anti-loop and continuity rules

- Every recovery condition receives a stable fingerprint.
- Identical recovery attempts have a strict budget.
- A repeated failure must change strategy, split scope, repair infrastructure or enter explicit incident hold.
- Proven upstream evidence must be preserved across targeted reruns.
- Candidate-bound revision and scope lineage must be enforced.
- CHARLIE must detect a mission returning to the same stage without new evidence.
- Failed notifications must not block mission state transitions.
- Mission state transitions must not depend on notification success.
- A protected decision waiting for Charl must not occupy the sole execution slot.
- A stopped/restarted runtime must resume from durable state without duplicate workers.

## 15. Required persistence and observability

The Vault must retain:

- executive cycle and operating state;
- goal snapshot and KPI gaps;
- observer registry and latest observations;
- observation-to-mission links;
- priority score and rationale;
- authority decision and policy version;
- commands and verified outcomes;
- notification generation and delivery lifecycle;
- owner attention item lifecycle;
- recovery fingerprints and budgets;
- agent/runtime health;
- mission, PR, deployment and post-release evidence;
- lessons and promoted improvements.

The dashboard must distinguish source truth from derived recommendation and show freshness.

## 16. Programme delivery sequence

### Phase 0 — freeze baseline and prove current truth

Deliverables:

- current process and data-flow map;
- current policies and trust tiers;
- observer coverage inventory;
- notification and queue failure reproductions;
- protected-action matrix;
- baseline metrics.

Exit gate: every claimed current capability has a reproducible test or live evidence record.

### Phase 1 — executive attention reliability

Primary mission: `CHARLIE-EXECUTIVE-ATTENTION-NOTIFICATION-20260720`.

Deliverables:

- generation-aware notification idempotency;
- durable delivery receipts and retries;
- clean decision messages and controls;
- SAM deduplication and classification;
- bounded reminders;
- regression coverage for the CAL failure.

Exit gate: a new actionable review creates exactly one new useful notification, and learning-only SAM entries do not enter urgent approvals.

### Phase 2 — never-silent portfolio continuity

Deliverables:

- explicit operating-state machine;
- fix for protected/unsuitable `new` work suppressing idle briefs;
- continuous runway maintenance;
- safe automatic selection with stored rationale;
- owner-wait parallelism;
- queue-deadlock and no-candidate handling.

Exit gate: every test portfolio ends in executing, recovering, discovering, briefing or an explicit incident hold—never unexplained idle.

### Phase 3 — complete observer registry

Deliverables:

- versioned observation contract;
- registry and freshness monitoring;
- full observers for SAM, Ledger, Herdmaster, Butcher, Beacon, farm operations and system health;
- stale/unknown evidence treatment;
- duplicate observation suppression.

Exit gate: CHARLIE can truthfully report the health, opportunity, risk and next action for every registered agent/domain.

### Phase 4 — goal-to-mission intelligence

Deliverables:

- durable goal/KPI linkage;
- cross-domain opportunity ranking;
- evidence-backed mission generation;
- conflict, dependency and capacity reasoning;
- research-before-build lane;
- mission family and duplicate controls.

Exit gate: with an empty CORE queue, CHARLIE produces a ranked, evidence-backed runway or a precise owner brief without invented work.

### Phase 5 — executive command centre

Deliverables:

- current executive operating state;
- goal progress and KPI gaps;
- agent/domain health;
- active/next/waiting work;
- owner decisions separated from learning and information;
- notification delivery truth;
- recovery and loop visibility;
- financial and outcome evidence where available.

Exit gate: Charl can understand what CHARLIE is doing, why, what changed and what is needed without inspecting raw CORE tabs.

### Phase 6 — unattended canary and graduated autonomy

Canary portfolio must contain:

- one safe new mission;
- one protected mission;
- one blocked recoverable mission;
- one unrecoverable/system incident;
- one duplicated SAM conversation;
- one learning-only SAM event;
- one evidence-backed opportunity from a non-CORE agent;
- one stale observer;
- an empty approved queue;
- a restart during active execution.

Expected behaviour:

- safe work is selected and started;
- protected work is clearly escalated;
- unrelated work continues;
- recovery is bounded and changes strategy when necessary;
- duplicates collapse;
- learning stays out of urgent approvals;
- stale evidence is labelled rather than guessed;
- restart resumes safely;
- one concise executive brief reflects authoritative state.

Autonomy expands only after clean canary evidence and explicit owner approval of the next trust tier.

## 17. Acceptance matrix

| Capability | Proof required |
| --- | --- |
| Scheduler continuity | repeated ticks across restart with no missed-run drift |
| Single executive authority | one active command outcome per idempotency generation |
| Queue continuity | safe candidate selected when runway is below target |
| No silent idle | explicit operating state and next action on every cycle |
| Goal alignment | every selected mission cites active goal and measurable outcome |
| Business-wide oversight | current observation or explicit stale/unknown for every registered domain |
| Protected authority | red-zone scenarios never execute without the required approval |
| Parallel continuity | protected waiting mission does not block unrelated safe mission |
| Anti-loop | identical failure budget enforced and alternate strategy recorded |
| Notification reliability | exact-once per generation, retry/dead-letter evidence, working controls |
| SAM clarity | one active item per conversation need; learning separated |
| Release truth | approved release reaches merged/deployed/verified or explicit incident state |
| Auditability | every recommendation, command, policy and outcome traceable |
| Executive usefulness | owner brief explains change, impact, recommendation and exact decision |

## 18. Confidence and rollout standard

No team may claim 100% certainty. The programme must instead earn high operational confidence through layered evidence:

1. deterministic unit and contract tests;
2. disposable database integration tests;
3. process ownership and restart tests;
4. notification transport tests with safe test destinations;
5. scenario/replay tests across all authority lanes;
6. dashboard/browser verification;
7. live canary with no protected side effects;
8. monitored limited rollout;
9. rollback drill;
10. post-rollout observation window and owner sign-off.

Target confidence for unattended activation: at least 96% under the existing owner governance standard, zero unresolved critical findings, zero escaped protected actions, zero duplicate workers, and complete evidence for the acceptance matrix.

## 19. Rollout and rollback

Rollout must be capability-by-capability, not a single global autonomy switch:

- observe only;
- recommend;
- create unapproved mission;
- select safe work;
- continue queue;
- perform bounded recovery;
- approve low-risk review;
- execute domain actions only where a separate audited rail and delegation exist.

Every capability requires an independent kill switch, policy expiry, audit trail and rollback procedure. Rollback must return the capability to observe/recommend mode without stopping unrelated executive observation.

## 20. Measures of success

- percentage of time with an explicit executive operating state;
- useful runway coverage;
- goal-aligned mission selection rate;
- owner interruptions per completed outcome;
- actionable-to-noise ratio in owner attention;
- duplicate notification and duplicate SAM item rate;
- time from actionable state to owner notification;
- time from safe empty queue to next selected mission;
- recovery success and repeated-loop rate;
- stale observer rate;
- mission completion, deployment and verified outcome rate;
- revenue, cash-protection or operational outcome attributable to missions;
- owner correction rate and trust-tier eligibility.

## 21. Explicit exclusions

This programme does not authorise:

- uncontrolled self-modification;
- arbitrary shell or tool access;
- weakening owner gates;
- customer sends, public posts, money actions, reservations, stock promises, lifecycle writes or migrations without their governed authority;
- fabricated missions merely to appear busy;
- replacing canonical domain agents with CHARLIE-specific business logic;
- claiming business-wide oversight before observer coverage is proven.

## 22. Definition of done

The programme is complete only when:

- all six delivery phases have passed their exit gates;
- CHARLIE observes every registered agent/domain through a current evidence contract;
- an empty or protected-only queue cannot produce silent standby;
- safe goal-aligned work continues automatically;
- protected decisions are concise and do not freeze unrelated work;
- retries cannot loop indefinitely;
- attention and learning are cleanly separated;
- owner notification delivery is auditable;
- CORE reliably builds, releases and verifies delegated work;
- the unattended canary and rollback drill pass;
- Charl approves the measured autonomy tier after reviewing evidence.

## 23. Resume record

When this programme resumes, begin with Phase 0 discovery and the already logged Phase 1 notification mission. Do not start implementation from this document alone. Re-read current live policies, mission state, agent registry, observer evidence and any changes deployed after 2026-07-20. Preserve this programme as the scope authority and record deviations through a new owner decision.
