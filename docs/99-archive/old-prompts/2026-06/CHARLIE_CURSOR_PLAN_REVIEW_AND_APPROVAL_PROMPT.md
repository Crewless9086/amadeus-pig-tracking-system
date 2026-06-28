# CHARLIE Core Cursor Plan Review And Approval Prompt

Status: Review Required Before Final Approval  
Owner priority: SAM Meat Sales first, FRED Transport next, CHARLIE as owner-level command interface  
Decision: Do not code yet. Produce an updated plan first.

---

## 1. Current Decision

The current Cursor plan is directionally correct, but it is not approved for implementation yet.

The plan currently sits at 94% confidence because the full Python test suite, Playwright/browser tests, live Supabase schema health checks, access-control posture, and dirty worktree review were not completed.

Before any code implementation, produce a revised plan that reaches at least 96% confidence based on evidence. If 96% cannot be reached, state exactly what remains unknown and what must be checked.

No coding until the updated plan is reviewed and approved by the owner.

---

## 2. Owner Answers To Cursor Questions

### Q1. Approve Phase 1 docs/ADR cleanup first?

Owner answer:
Only after the revised plan reaches at least 95% confidence and the owner reads it again.

Required Cursor action:
Do not modify docs yet. First produce a final plan v2 with:
- exact files to add/update
- exact stale docs to supersede
- exact wording to remove or replace
- exact owner review checklist
- confidence score and evidence

### Q2. Generic `charlie_*` tables or neutral names?

Decision:
Use neutral, reusable table names.

Recommended:
- `business_units`
- `agent_teams`
- `agent_memberships`
- `agent_tasks`
- `agent_result_packets`
- `agent_activity_events`
- `agent_handoffs`
- `agent_shared_context_snapshots`
- `owner_decisions`
- `approval_requests` only if cross-business approvals cannot cleanly use existing approval rails

Do not use `charlie_*` for shared collaboration tables because these tables will serve CHARLIE, Oom Sakkie, SAM, FRED, Build Team, and future business teams.

Acceptable code/module naming:
- `modules/charlie_core/`
- `/charlie`
- `/api/charlie/...`

But the shared ledger tables should stay neutral.

Cursor must produce:
- ERD-style table relationship summary
- column list for each proposed table
- indexes
- RLS/access policy notes
- migration rollback strategy
- tests for create/list/read/status updates
- exact mapping from existing Oom Sakkie/SAM rails into the generic ledger

### Q3. Should CHARLIE get its own page now?

Decision:
Yes. CHARLIE must get its own owner-only page now.

Important:
CHARLIE is not just a small summary inside `/oom-sakkie`. CHARLIE is the top-level owner command interface.

Oom Sakkie remains the Farm Commander and the farm staff-facing interface. CHARLIE is the owner-only operating layer above all major teams and businesses.

Required route:
- `GET /charlie`

Required API:
- `GET /api/charlie/overview`
- `GET /api/charlie/teams`
- `GET /api/charlie/activity`
- `GET /api/charlie/agent-map`
- `POST /api/charlie/command` only as draft/read-only at first; no risky action execution

Initial CHARLIE mode:
Read-only and draft-only.

CHARLIE UI direction:
Build an incredible, simple, alive owner command interface. Not a messy approval sheet.

The UI should feel like:
- a living command brain
- one clear owner cockpit
- animated/pulsing team status
- active agents and subagents visible
- business units shown as team clusters
- CHARLIE in the center as the owner-level orchestrator
- Oom Sakkie, SAM Meat Sales, FRED Transport, and Build Team as major team leaders/nodes
- click a team leader to open a focused workspace/window
- type/talk to CHARLIE to route work
- show what each team is doing now
- show what is blocked
- show what needs owner approval
- show what is making money or needs attention
- show what was recently completed
- allow navigation into `/oom-sakkie`, `/sales/meat-leads`, future `/fred`, and build-planning pages

Do not build a complex frontend framework. Use current Flask/Jinja/static JS/CSS stack unless the repo already supports another approach.

CHARLIE acceptance:
- owner-only page
- no page-level chaos
- no raw table dump
- live-feeling visual map
- team leader cards/nodes
- active pulse/status states
- command bar
- recent activity feed
- decision queue
- "open team workspace" behavior
- no dangerous action without Gatekeeper/owner approval

### Q4. SAM recovery first UI target?

Decision:
SAM Meat Sales is urgent and must be the first money-flow repair.

The first operational target is `/sales/meat-leads`, but it must become a SAM Meat Sales Command Room, not a technical table.

SAM should behave like a smart human salesperson:
- sees every meat lead
- knows what is missing
- drafts the next message
- asks for approval when needed
- watches WhatsApp/Chatwoot window/template status
- knows price/deposit/follow-up state via Ledger
- knows availability/reservation/fulfillment constraints via Butcher
- uses Beacon for demand copy when needed
- lets Gatekeeper block risky sends/promises
- shows the owner one clear next action per lead

Required SAM MVP:
- one row/card per lead
- "next best action" per lead
- missing facts checklist
- draft reply
- approval/send state
- price/deposit state
- product/availability state
- follow-up due
- owner decision card
- no-send/no-promise gates visible

SAM must focus on meat sales first. Livestock sales expansion comes later.

Cursor must inspect:
- Chatwoot inbound webhook
- Chatwoot policy route
- meat leads API
- pricing API
- quote packet/PDF/send
- deposits
- Butcher meat match
- reservations
- instruction drafts
- fulfillment
- driver route/events
- reconciliation
- send gates/env flags
- route guards

### Q5. Trusted-local sales mutation routes or explicit admin guards?

Decision:
Add explicit admin/local access guards before expanding CHARLIE/FRED.

Explanation:
Shared data and access guards are different things.

Shared data means CHARLIE, Oom Sakkie, SAM, Ledger, Butcher, Gatekeeper, and later FRED can see structured result packets, tasks, handoffs, and summaries.

Access guards mean not everyone or every process can call write/send/deposit/mutation routes.

This must be solved before CHARLIE or FRED can safely orchestrate sales actions.

Required Cursor action:
Inspect all sales mutation routes, especially:
- `modules/sales/sales_transaction_routes.py`
- all `POST`, `PUT`, `PATCH`, `DELETE` routes under `modules/sales/`
- customer webhook endpoints
- send endpoints
- deposit/payment endpoints
- quote/invoice endpoints
- reservation endpoints

Classify each route:
- public webhook
- owner/admin-only
- local-review-only
- internal service-only
- disabled until env flag enabled
- external worker forbidden

Then propose a consistent access policy:
- customer inbound webhooks must remain callable only with webhook verification
- owner/admin mutation routes require an explicit guard
- internal service routes require local/internal guard
- send routes require env flag + approval hash + channel policy + owner approval
- no external worker receives broad service-role access

Add tests for denied and allowed cases.

### Q6. Missing portraits?

Decision:
Generate starter portraits and support fallbacks.

Use:
- `static/assets/agents/<agent-id>/portraits/`
- `static/assets/agents/<agent-id>/voice/`
- `static/assets/agents/<agent-id>/agent.json`
- `static/assets/agents/agent_registry.json`

Important:
The UI must never break if a portrait is missing. It should use the portrait if present and a clean fallback if not.

Near-term assets to prioritize:
- charlie
- oom-sakkie
- sam
- fred
- gatekeeper
- ledger
- butcher
- beacon

Add an asset existence test for every image referenced in `agent_registry.json`.

---

## 3. Required Changes To Current Plan

The current plan is good but must be amended before approval.

### Add Phase 0B: Evidence And Safety Verification

Before Phase 1 docs:
- inspect dirty worktree
- list all modified/deleted/untracked files
- run available Python tests or state exact blockers
- run Playwright/browser tests or state exact blockers
- run JS syntax checks
- inspect live Supabase schema health or state exact blockers
- inspect access-control posture for sales mutation routes
- produce risk register

### Add Phase 0C: CHARLIE UI Product Spec

Before building `/charlie`, produce:
- CHARLIE product vision
- route/API list
- wireframe
- data sources
- animation/status states
- team leader/node map
- permission model
- owner-only access model
- acceptance checklist

CHARLIE must not become a table dashboard. It must be a powerful but simple owner command interface.

### Add Phase 2A: Agent Collaboration Ledger Design Review

Before writing migration:
- propose ERD
- define table columns
- define status enums
- define risk enums
- define visibility scopes
- define source references
- define event immutability
- define relationship to existing Oom Sakkie/SAM rails
- define read/write permissions
- define tests
- only then create migration

### Add Phase 3A: SAM Meat Sales Recovery

Before adding broad CHARLIE automation:
- repair `/sales/meat-leads`
- create SAM Command Room view
- show one next action per lead
- show missing facts
- show draft reply
- show approvals
- show no-send gates
- connect Ledger/Butcher/Beacon/Gatekeeper summaries
- prove the money path works

### Add Phase 3B: FRED Transport Parallel Planning

Because FRED needs to make money soon, do not wait indefinitely for "SAM commercially stable".

After SAM MVP is scoped and the no-send gates are clear:
- create FRED docs/schema plan
- create transport lead capture MVP
- create read-only transport opportunity board
- do not build full dispatch automation yet
- no quotes, customer sends, deposits, driver commitments, or job confirmations without approval rails

### Add Phase 4: CHARLIE Read-Only Orchestrator And UI

Build `/charlie` read-only first:
- overview
- team map
- agent activity
- result packet feed
- decision queue
- command bar draft-only
- navigation into team workspaces

No risky execution yet.

---

## 4. Non-Negotiable Rules

- Supabase remains operational truth.
- Brain/Vault/Markdown is guidance only.
- No Obsidian runtime dependency.
- No ZOEY or hosted Jarvis as core.
- No external worker gets broad service-role access.
- No bypassing Gatekeeper.
- No customer messages without approved send rails.
- No public posts without owner approval.
- No deposit/payment status from POP alone.
- No slaughter/butcher/delivery promise without backend gate.
- No code deploy without owner approval.
- No full autonomy until draft/approval flows prove reliable.
- No new frontend framework unless the owner explicitly approves it.

---

## 5. Cursor Prompt To Produce Final Plan V2

Copy/paste this into Cursor:

```text
You are acting as PRISMA + top-level systems architect for CHARLIE CORE.

Do not code yet.

Read the uploaded CHARLIE plan, the existing repo docs, and this owner review. Produce a revised final implementation plan v2.

The owner’s decisions are:

1. No implementation is approved yet. The plan must reach at least 96% confidence before coding. If it cannot reach 96%, explain exactly what is missing.
2. Use neutral shared ledger table names, not `charlie_*`, because the ledger must serve CHARLIE, Oom Sakkie, SAM, FRED, Build Team, and future businesses.
3. CHARLIE gets its own owner-only page now: `/charlie`. CHARLIE is the top-level owner command interface above Oom Sakkie, SAM Meat Sales, FRED Transport, and Build Team.
4. CHARLIE must be visually incredible but simple: live-feeling, pulsing, interactive, team-map style, not a raw approval table.
5. SAM Meat Sales is the urgent money-flow repair. `/sales/meat-leads` must become a SAM Meat Sales Command Room with one clear next action per lead.
6. FRED Transport must be planned soon enough to make money, but start with lead/opportunity capture and read-only board before full dispatch automation.
7. Add explicit access guards before expanding CHARLIE/FRED. Shared data is good; unsafe mutation route exposure is not acceptable.
8. Generate starter portraits if possible, but the UI must support fallbacks and must not break on missing assets.

Before producing the revised plan, inspect the repo again and answer these sections:

A. Dirty Worktree Review
- list modified/deleted/untracked files
- identify owner-created files that must not be overwritten
- state safe branch/commit/stash recommendation

B. Test And Health Evidence
- run or confirm commands for Python unit tests
- run or confirm JS syntax checks
- run or confirm Playwright tests
- run or confirm Supabase/database health checks
- state exact blockers for anything not run

C. Access-Control Audit
- inspect sales mutation routes
- classify each POST/PUT/PATCH/DELETE route as public webhook, owner/admin-only, local-review-only, internal service-only, env-flagged send route, or external-worker-forbidden
- propose exact guard function/policy
- propose denial/allowance tests

D. CHARLIE UI Product Spec
- route: `/charlie`
- APIs
- wireframe
- color/style direction
- animation/status states
- team leader map
- command bar behavior
- result-packet feed
- owner decision queue
- windows/workspaces for Oom Sakkie, SAM, FRED, Build Team
- acceptance checklist

E. Agent Collaboration Ledger Design
- recommend neutral table names
- ERD-style relationships
- columns
- indexes
- enums/statuses
- visibility scopes
- RLS/access notes
- migration filename suggestion
- tests
- mapping from existing Oom Sakkie/SAM rails

F. SAM Meat Sales Recovery
- current backend pieces found
- current broken/unclear operator path
- proposed `/sales/meat-leads` command-room design
- one-next-action-per-lead model
- draft-reply model
- Ledger money gate
- Butcher availability gate
- Beacon demand draft gate
- Gatekeeper approval/block state
- no-send rules
- acceptance tests

G. FRED Transport MVP
- route/module plan
- first schema plan
- lead/opportunity capture
- read-only board
- team roles
- no customer send/quote/deposit/driver commitment without approvals
- how FRED reports into CHARLIE

H. Updated Phases
- Phase 0B evidence/safety verification
- Phase 0C CHARLIE UI spec
- Phase 1 docs/ADR cleanup
- Phase 2 Agent Collaboration Ledger migration/tests
- Phase 3A SAM Meat Sales recovery
- Phase 3B FRED lead/opportunity planning
- Phase 4 CHARLIE read-only orchestrator/UI
- Phase 5 Build Team workflow
- Phase 6 Brain/Vault retrieval later

I. Confidence Score
- give confidence percentage
- evidence supporting it
- what keeps it below 96 if applicable
- do not claim tests passed unless they were run
- do not propose coding until plan is approved by owner

Output the final plan in a clean markdown structure with explicit GO / NO-GO gates.
```

---

## 6. Approval Recommendation

Do not approve implementation yet.

Approve only this next step:

`Cursor: Produce Final Plan V2 with Phase 0B evidence, access-control audit, CHARLIE UI spec, SAM money-flow recovery, FRED MVP plan, and neutral Agent Collaboration Ledger design.`

After that plan comes back, review it before any docs, migrations, or UI are changed.
