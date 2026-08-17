# Agent Workforce Control Room Plan

Date: 2026-07-26  
Owner: Charl  
Product surface: `/charlie-agents`

## Decision

The Workforce page is the canonical owner-facing view of the Amadeus agent
team.

It must answer, from current authoritative evidence:

1. Who is on the team?
2. What business outcome does each agent own?
3. What can the agent observe, recommend, execute, verify, and learn today?
4. What authority is enabled, disabled, or awaiting owner approval?
5. What real production evidence supports the displayed maturity?
6. What is blocking the agent?
7. What is the next best safe action?
8. Is the agent eligible to propose graduation?

The page must not become a second authority store, mission queue, or static
marketing page. It is a read projection over canonical agent, runtime,
evidence, mission, learning, and authority sources.

## Product outcome

Charl should be able to open one page and understand the whole agentic
workforce without consulting terminals, raw database tables, GitHub, or
planning documents.

The page should make the difference between these states obvious:

- designed;
- built;
- deployed;
- evidence gathering;
- owner-gated operational;
- repeatably operational;
- learning;
- graduation candidate;
- bounded autonomous;
- unavailable;
- stopped or blocked.

Built, merged, deployed, and operational are different claims and must never
be collapsed into one status.

## Agentic capability model

Every agent is evaluated across the same six capability dimensions:

| Dimension | Owner question | Evidence examples |
| --- | --- | --- |
| Observe | Can the agent read current authoritative reality? | Fresh source reads, bounded inventory, telemetry, provider evidence |
| Reason | Can it produce grounded classifications and recommendations? | Review packets, scorecards, explanations, policy results |
| Act | Can it perform a real bounded operation? | Owner-authorized publication, ownership change, append-only decision |
| Verify | Can it prove the external or physical outcome? | Provider result, public post, authoritative refresh, physical observation |
| Learn | Can it persist outcomes and improve later recommendations? | Performance snapshots, owner ratings, corrected decisions, learning events |
| Graduate | Can it produce an evidence-backed owner-review candidate? | Persisted thresholds, distinct cases, policy pass rate, reliability record |

No single combined percentage may conceal an unavailable or prohibited
dimension. The UI may show an overall maturity label, but it must also show the
six underlying states.

## Maturity levels

| Level | Label | Required meaning |
| --- | --- | --- |
| 0 | Defined | Identity, role, owner, sources, and boundary documented |
| 1 | Observing | Reads authoritative evidence without action authority |
| 2 | Advising | Produces grounded owner recommendations |
| 3 | Owner-gated operational | Has completed a real owner-authorized action |
| 4 | Repeatably operational | Multiple verified real outcomes under the same contract |
| 5 | Learning | Persists comparable outcomes and changes recommendations from evidence |
| 6 | Graduation candidate | Meets persisted thresholds for owner review |
| 7 | Bounded autonomous | Owner has separately activated a narrow authority class |

An agent cannot reach a higher level because code exists. Each level requires
production evidence appropriate to that capability.

Graduation creates an owner-review candidate only. It never changes authority
automatically.

## Workforce summary

The top-level summary should show:

- total registered agents;
- agents with current evidence;
- owner-gated operational agents;
- repeatably operational agents;
- agents actively learning;
- graduation candidates;
- agents needing owner attention;
- agents stopped or unavailable;
- live missions and review-ready missions;
- freshness of the oldest critical workforce source.

The summary must distinguish `0` from `Unavailable`.

## Agent roster

Each roster row should show:

- agent name and department;
- current maturity label;
- runtime state: live, stopped, unavailable, or planned;
- authority state: advisory, owner-gated, or bounded autonomous;
- evidence freshness;
- current blocker or next action indicator.

Static planned agents remain visible, but must not appear operational.

## Agent detail

Selecting an agent should show:

### Identity and responsibility

- role;
- commander/owner;
- business outcome owned;
- authoritative systems;
- linked workspace.

### Current status

- code state;
- deployment state;
- runtime state;
- production evidence state;
- last successful real outcome;
- last verified observation;
- evidence freshness.

### Agentic capability matrix

Show Observe, Reason, Act, Verify, Learn, and Graduate separately with:

- current state;
- supporting evidence count;
- target or threshold where defined;
- latest evidence time;
- source status;
- concise explanation.

### Authority

Show explicit capability classes, not a generic autonomy switch:

- customer send;
- public posting;
- scheduling;
- retry;
- ownership change;
- order/quote/reservation;
- stock or livestock mutation;
- payment/financial mutation;
- Telegram/owner notification;
- advertising/boosting/spend;
- hardware/transport execution.

Each class must be `enabled`, `owner_gated`, `disabled`, `unavailable`, or
`not_applicable`, with its authoritative source.

### Current attention

- blockers;
- stale or unavailable evidence;
- pending owner decisions;
- failed canaries;
- expiring response or action windows;
- stopped runtime or disabled gates.

### Next best safe action

Display one evidence-derived next action with:

- why it is next;
- agent responsible;
- whether it is read-only, repository work, owner decision, production write,
  external publication, or physical action;
- required authorization;
- exact linked workspace or mission where available.

The Workforce page does not execute protected actions directly in the first
release. It links to the authoritative owner surface.

### Graduation

- current contract version;
- evidence thresholds;
- observed distinct cases;
- policy compliance;
- reliability;
- owner usefulness ratings where relevant;
- eligible/not eligible;
- exact missing evidence;
- authority that would still require separate owner activation.

## Initial authoritative adapters

Implement adapters in this order:

1. CHARLIE and CORE
   - mission store;
   - runner/supervisor/stop-marker truth;
   - ownership and containment evidence;
   - review and CI outcomes.
2. SAM Live Stock
   - conversation learning;
   - reply-class graduation;
   - owner work and ownership exceptions;
   - customer-delivery evidence and policy gates.
3. BEACON
   - media and publication evidence;
   - organic media learning;
   - comparable performance windows;
   - owner usefulness ratings;
   - publication and spend authority.
4. HERDMASTER
   - canonical observation evidence;
   - animal decision/review evidence;
   - Auction List readiness and owner-gated state;
   - zero business-mutation boundaries.
5. ROOTLINE
   - telemetry freshness;
   - plan-only state;
   - physical-canary evidence;
   - scheduler, command, transport, and hardware authority.
6. SAM Meat, Oom Sakkie, Ledger, Butcher, FRED, and remaining agents
   - add only when an authoritative scorecard adapter exists;
   - otherwise display documented status with `Not measured`.

## API contract

Advance the API from `charlie_agent_workforce_v1` to a reviewed v2 contract.
Each agent projection should include:

- `identity`;
- `responsibility`;
- `maturity`;
- `runtime`;
- `deployment`;
- `evidence_freshness`;
- `capability_dimensions`;
- `authority_classes`;
- `metrics`;
- `recent_outcomes`;
- `blockers`;
- `owner_decisions`;
- `next_best_action`;
- `graduation`;
- `sources`;
- `links`.

Every source must report:

- status;
- observed/retrieved time;
- freshness state;
- authoritative/advisory classification;
- failure reason when unavailable.

The v1 route should remain compatible until the v2 page and adapters are
verified.

## Source-of-truth and safety rules

- Never infer production readiness from Git or deployment alone.
- Never infer external delivery from an attempted action.
- Never infer physical success from command acceptance.
- Never convert missing evidence to zero.
- Never calculate maturity from caller-supplied aggregate claims.
- Count distinct persisted evidence identities.
- Compare only compatible evidence windows and capability classes.
- Show stale evidence as stale.
- The Workforce page is owner-only.
- No page refresh may send, publish, schedule, change ownership, mutate
  livestock, spend, or control hardware.
- No displayed threshold may activate authority.

## UI direction

Retain the current three-part desktop concept:

- team roster;
- team/authority map;
- selected-agent detail.

Improve it with:

- department and status filters;
- `Needs attention`, `Operational`, `Learning`, and `Planned` views;
- status chips with a shared vocabulary;
- six-dimension capability display;
- explicit authority matrix;
- recent verified outcomes;
- linked owner decisions;
- next-best-action card;
- source freshness and unavailable states;
- compact mobile agent cards instead of forcing the full map.

Percentages should be used only where a defined evidence contract exists.
Never show a decorative percentage for an unmeasured agent.

## Documentation ownership

The following documents must remain aligned:

- `docs/06-operations/CHARLIE_AGENT_WORKFORCE.md`
- `docs/09-vault-brain/02-agents/AGENT_REGISTRY.md`
- individual agent doctrine files;
- `docs/09-vault-brain/07-standards/AGENT_AUTHORITY_MATRIX.md`
- `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md`
- this implementation plan until delivery is complete.

The structured registry and runtime adapters are authoritative for the UI.
Planning prose does not make an agent operational.

## Delivery stages

### Stage 1: contract and truth reconciliation

- Reconcile the registry with current production agents and teams.
- Define shared maturity, runtime, authority, freshness, and blocker enums.
- Add production-shaped fixtures for BEACON, SAM, HERDMASTER, ROOTLINE, CORE,
  and an unavailable planned agent.
- Document v2 API without changing authority.

### Stage 2: backend adapters

- Add adapter interface and per-agent source status.
- Implement BEACON, SAM, HERDMASTER, ROOTLINE, CHARLIE, and CORE adapters.
- Keep unavailable adapters explicit.
- Add bounded concurrent reads and a total response deadline.

### Stage 3: owner UI

- Add filters, capability dimensions, authority matrix, outcomes, next action,
  and graduation detail.
- Preserve the current page while the v2 response is unavailable.
- Complete visual review at desktop and mobile sizes.

### Stage 4: production verification

- Deploy read-only.
- Verify owner 200 and anonymous/client denial.
- Compare displayed facts with canonical sources for each measured agent.
- Confirm refresh produces zero protected actions.
- Correct outdated static stage labels.

### Stage 5: ongoing workforce learning

- Add adapters as agents gain real evidence.
- Record owner usefulness of recommendations.
- Show graduation candidates without self-activation.
- Use workforce gaps to propose future CHARLIE missions.

## Acceptance criteria

- Charl can determine the real status and next action for each current agent
  from one page.
- BEACON, SAM, HERDMASTER, ROOTLINE, CHARLIE, and CORE use live authoritative
  adapters.
- Planned/unmeasured agents never receive invented percentages.
- Code, deployment, runtime, evidence, and authority are visibly separate.
- Every enabled authority class cites a canonical source.
- Every blocker and next action is evidence-derived.
- Stale/unavailable sources remain visible.
- Graduation is evidence-derived and owner-review-only.
- Anonymous and non-owner access is denied.
- Refreshing the page produces zero customer, public, business, livestock,
  financial, scheduling, Telegram, or hardware actions.

## Explicit non-goals

- Replacing Mission Control.
- Executing protected actions directly from the initial Workforce release.
- Creating a second agent registry or authority database.
- Giving every agent a percentage.
- Automatic graduation.
- Hiding incomplete or failed agent states.

