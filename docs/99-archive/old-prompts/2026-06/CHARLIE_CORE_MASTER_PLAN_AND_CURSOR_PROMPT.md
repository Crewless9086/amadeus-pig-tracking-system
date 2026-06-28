# CHARLIE CORE Master Plan And Cursor Planning Prompt

Date: 2026-06-27  
Status: owner planning brief for Cursor / repo LLM review  
Primary outcome: produce a repo-aware, evidence-backed build plan before coding  
Required confidence gate: 96% or higher, backed by repo evidence and test strategy

---

# 0. Direct Decision

We are no longer searching for an outside product to become the main Jarvis.

The main operating layer will be built inside our own system and will be called:

> **CHARLIE CORE**

CHARLIE is the top-level operating brain. CHARLIE has overview across the owner, the farm, future transport, sales, build work, SOPs, business goals, and the agent teams.

**Important:** CHARLIE is not a third-party platform. CHARLIE is the controller/orchestrator inside this codebase.

External tools such as Cursor, Codex, Claude Code, local Jarvis, ZOEY, n8n, Chatwoot, WhatsApp, ElevenLabs, or Obsidian may be used as tools or workers later, but they must not become the source of truth or the uncontrolled boss of the system.

---

# 1. North Star

The owner wants a Jarvis-like operating system that can:

- understand the owner’s businesses, projects, sales, SOPs, and current priorities;
- run an overview across multiple business units;
- delegate work to specialist teams and sub-agents;
- keep all agents aligned to the same Brain/Vault rules;
- track tasks, results, blockers, handoffs, and decisions;
- notify the owner only when input, approval, money, risk, or direction is needed;
- help build the software itself by creating structured build requests, patch plans, test plans, and release gates;
- keep Supabase as the live operational truth;
- keep risky actions behind Gatekeeper and owner approval.

The user does not want another SaaS product maze. The goal is one controlled operating system with one brain and many teams.

---

# 2. Correct Hierarchy

Use this hierarchy:

```text
CHARLIE CORE
  ├── Owner Command Layer
  │     ├── priorities
  │     ├── approvals
  │     ├── decisions
  │     ├── personal/admin tasks later
  │     └── daily command brief
  │
  ├── Farm Business
  │     └── Oom Sakkie
  │           ├── Ledger
  │           ├── Herdmaster
  │           ├── Beacon
  │           ├── Sam
  │           ├── Gatekeeper
  │           ├── Rootline
  │           ├── Butcher
  │           └── Quartermaster
  │
  ├── Meat Sales Team
  │     ├── Sam as customer conversation lead
  │     ├── Ledger as pricing/deposit/follow-up lead
  │     ├── Butcher as stock/meat pipeline lead
  │     ├── Beacon as demand-generation lead
  │     └── Gatekeeper as send/price/order approval lead
  │
  ├── Transport Business
  │     └── FRED
  │           ├── Dispatch Agent
  │           ├── Loads / Sales Agent
  │           ├── Fleet Agent
  │           ├── Driver Comms Agent
  │           ├── Finance Agent
  │           └── Compliance Agent
  │
  ├── Build Team
  │     ├── Product Planner
  │     ├── PRISMA UI Designer
  │     ├── Backend Engineer
  │     ├── Database Engineer
  │     ├── QA Tester
  │     ├── Docs Keeper
  │     └── Release Gatekeeper
  │
  └── Brain / Vault
        ├── source-of-truth rules
        ├── SOPs
        ├── business playbooks
        ├── agent authority boundaries
        ├── customer tone and scripts
        ├── product/UI decisions
        ├── build standards
        ├── decisions and review logs
        └── owner preferences
```

**Oom Sakkie is not replaced.** Oom Sakkie becomes the Farm Commander under CHARLIE.

**FRED is the Transport Commander.** FRED will be built as the future transport business operating layer under CHARLIE.

**SAM remains critical.** SAM must be fixed for meat sales/customer conversation because this is the fastest commercial need.

---

# 3. Tool Decision

## 3.1 Cursor

Cursor remains the primary development tool and repo-aware build environment.

Use Cursor to:

- inspect the repo;
- plan changes;
- edit files;
- run tests;
- create migrations;
- update docs;
- implement CHARLIE, SAM recovery, and FRED.

## 3.2 Supabase

Supabase remains the operational source of truth.

Supabase owns:

- live business records;
- customers;
- orders;
- sales;
- payments/deposits;
- approvals;
- audit logs;
- agent tasks;
- agent result packets;
- agent handoffs;
- transport jobs later;
- farm records;
- any action that changes the real world.

## 3.3 Brain / Vault

The Brain/Vault is the human-readable guidance layer.

It owns:

- SOPs;
- playbooks;
- agent rules;
- policies;
- owner preferences;
- tone rules;
- prompt guidance;
- UI/product decisions;
- “why we decided this” logs.

This can be Markdown inside `docs/`. Cursor can edit it now. Obsidian is optional later as a nicer viewer/editor, not a runtime dependency.

## 3.4 Obsidian

Do not add Obsidian as required infrastructure.

Obsidian may later open the same Markdown docs folder as a human editor, but the Flask app, Supabase, and agents must not depend on Obsidian.

## 3.5 External Jarvis / ZOEY / Claude Code

Do not make external Jarvis/ZOEY the core brain.

They may later become workers through controlled APIs:

```text
External worker
  -> safe CHARLIE API
  -> Supabase result packet / handoff / draft
  -> Gatekeeper
  -> owner approval if needed
```

No external worker may get broad Supabase service-role access, direct customer-send authority, payment authority, farm-record write authority, deploy authority, or hardware-control authority.

---

# 4. Source Of Truth Policy

## Supabase wins for live facts

If Supabase and Markdown disagree about a live operational fact, Supabase wins.

Examples:

- customer status;
- order status;
- payment status;
- product availability;
- pig/litter data;
- transport job status;
- approvals;
- audit logs;
- agent task state.

## Brain/Vault wins for approved guidance

Brain/Vault owns approved guidance:

- how SAM should speak;
- when Gatekeeper should block;
- how Ledger should treat pricing, deposits, and follow-ups;
- how Butcher should treat demand-before-slaughter;
- how FRED should classify transport opportunities;
- what PRISMA must follow for UI;
- what the owner wants and why.

## Backend gates win for action authority

If a Markdown rule says something is allowed but the backend gate blocks it, the backend gate wins until the rule is reviewed and implemented safely.

---

# 5. Required Agent Collaboration Layer

This is the most important missing piece.

Agents must not work in isolation. They need a shared collaboration layer in Supabase.

The Cursor LLM must inspect existing tables first, then propose the minimum safe migration or reuse plan.

Required concepts:

```text
agent_tasks
agent_result_packets
agent_activity_events
agent_handoffs
agent_shared_context_snapshots
approval_requests / existing approval rails
owner_decisions
```

## 5.1 agent_result_packets

Purpose: clean, shareable result from an agent.

A result packet is not private reasoning. It is a safe operational summary that other agents can read.

Example:

```text
agent_id: sam
business_unit: farm
team_id: meat_sales
result_type: customer_follow_up_needed
title: Three meat customers need reply drafts
summary: Two customers are missing delivery area. One customer asked for price confirmation.
recommendation: Ask Ledger to confirm price, then let Sam prepare WhatsApp drafts.
priority: high
requires_owner_approval: true
gatekeeper_status: approval_required
status: active
```

## 5.2 agent_handoffs

Purpose: one agent formally hands work to another.

Example:

```text
from_agent_id: butcher
to_agent_id: sam
reason: Product availability confirmed
task: Prepare customer reply draft for pork pack availability. Do not send.
status: open
```

## 5.3 agent_activity_events

Purpose: append-only event stream of what agents did.

Examples:

```text
Sam prepared draft.
Ledger flagged price missing.
Gatekeeper blocked send.
Oom Sakkie summarized result.
FRED created transport lead review.
```

## 5.4 agent_shared_context_snapshots

Purpose: daily or per-business short summary for CHARLIE.

Example:

```text
Today’s Meat Sales Snapshot:
- 8 active leads
- 3 need customer replies
- 2 need price approval
- 1 potential bulk buyer
- Sam is blocked until WhatsApp channel rules are confirmed
```

---

# 6. CHARLIE Core Responsibilities

CHARLIE is responsible for:

- owning the top-level daily command brief;
- knowing which business units exist;
- knowing which teams and agents belong to each business;
- tracking projects and workstreams;
- routing user requests to the right commander or build team;
- reading result packets and shared context snapshots;
- surfacing blockers and approvals;
- maintaining the Brain/Vault structure;
- asking the owner for decisions when needed;
- preventing scattered/uncontrolled tool usage;
- producing structured plans before build work starts.

CHARLIE must not:

- bypass Gatekeeper;
- write live records without approved workflows;
- send customer messages without approved send rails;
- create payments/deposits without source-of-truth evidence;
- deploy code without release gate;
- allow external workers to act directly on production systems.

---

# 7. Oom Sakkie Responsibilities Under CHARLIE

Oom Sakkie remains the farm owner-facing command center.

Oom Sakkie should:

- provide the farm daily brief;
- coordinate farm agents;
- show farm approvals and blockers;
- surface Meat Sales priorities;
- keep the System Workbench secondary;
- use the visible farm command UI already planned;
- route farm-specific requests to Ledger, Sam, Butcher, Beacon, Herdmaster, Rootline, Gatekeeper, or Quartermaster.

Oom Sakkie should not become the universal personal/business Jarvis. CHARLIE sits above it.

---

# 8. SAM Meat Sales Recovery Priority

This is the first money-focused operational priority.

Goal:

> Fix SAM and the meat sales flow so customers, leads, replies, product interest, stock readiness, pricing, deposits, and approval gates are clear.

## 8.1 Current problem to investigate

Cursor must inspect the repo and identify what is broken in:

```text
/sales/meat-leads
/sales/meat-driver
/sales/slaughter
/sales-dashboard
modules/sales/*
modules/oom_sakkie/*sales*
Chatwoot/WhatsApp/customer-followup env gates
existing Supabase meat sales tables/migrations
Sam specialist/dashboard state
Ledger/Butcher/Beacon links to meat sales
```

## 8.2 Required outcome

The system must support this owner workflow:

```text
1. Lead or customer inquiry exists.
2. SAM shows missing customer facts.
3. Ledger shows price/deposit/follow-up status.
4. Butcher shows meat/product availability or demand pressure.
5. Beacon can draft demand-generation posts, but not publish.
6. Gatekeeper shows what is blocked and why.
7. Owner approves price/send/order where needed.
8. Result is logged in Supabase.
9. Oom Sakkie / CHARLIE can summarize the money status.
```

## 8.3 Do not automate too soon

SAM may prepare drafts and check missing facts.

SAM must not send customer messages until:

- Chatwoot/WhatsApp channel rules are active;
- opt-in/template/window rules are respected;
- owner approval path exists;
- Gatekeeper records the approval.

---

# 9. FRED Transport Business MVP

FRED is the Transport Commander under CHARLIE.

The goal is to create a money-capable transport module without overbuilding.

## 9.1 First FRED scope

FRED should track:

- transport leads;
- load/customer opportunities;
- pickup and delivery locations;
- vehicle/driver availability;
- quote status;
- job status;
- costs and expected margin;
- documents/compliance reminders;
- customer follow-ups;
- owner approval requirements.

## 9.2 Initial FRED sub-agents

```text
FRED — Transport Commander
Dispatch Agent — schedules jobs and routes
Loads / Sales Agent — finds and tracks transport opportunities
Fleet Agent — vehicle readiness and maintenance reminders
Driver Comms Agent — driver/customer coordination drafts
Finance Agent — quote, cost, deposit, margin tracking
Compliance Agent — documents, permits, risk and safety reminders
```

## 9.3 FRED must follow the same model

FRED must use:

- Supabase for live data;
- Brain/Vault for SOPs and rules;
- Gatekeeper for risky actions;
- result packets and handoffs for collaboration;
- owner approval before customer sends, quotes, deposits, or job confirmations.

---

# 10. Build Team Under CHARLIE

The Build Team exists to reduce owner time spent building manually.

It should not replace Cursor. It should structure work so Cursor/LLM sessions can build safely.

## Build Team roles

```text
Product Planner
  Converts owner ideas into scope, acceptance criteria, and phased implementation.

PRISMA UI Designer
  Designs simple, warm, human-first interfaces that follow product vision.

Database Engineer
  Proposes migrations, RLS, indexes, and data contracts.

Backend Engineer
  Implements routes, services, modules, APIs, and safe workers.

Frontend Engineer
  Implements templates, static JS/CSS, and UI interactions within current stack.

QA Tester
  Writes and runs tests, regression checks, and manual verification steps.

Docs Keeper
  Updates docs, ADRs, decision logs, and Brain/Vault files.

Release Gatekeeper
  Blocks unsafe release, missing tests, secret leaks, broken migrations, or unapproved risky changes.
```

## Build Team workflow

```text
Owner request
  -> CHARLIE creates build request
  -> Product Planner scopes it
  -> Database Engineer checks data model
  -> PRISMA checks UI/UX
  -> Backend/Frontend propose implementation
  -> QA defines and runs tests
  -> Release Gatekeeper checks risk
  -> owner approves
  -> implementation proceeds
  -> result packets and docs are updated
```

---

# 11. Repo-Aware Planning Requirements

Before coding, Cursor must inspect the existing project and produce a plan.

Cursor must read or locate these areas:

```text
app.py
modules/
modules/oom_sakkie/
modules/sales/
modules/orders/
modules/telemetry/
services/database_service.py
supabase/migrations/
templates/
static/js/
static/css/
static/assets/agents/agent_registry.json
docs/00-start-here/
docs/01-architecture/
docs/05-ai/
docs/07-decisions/
docs/08-business-modules/
requirements.txt
pytest / Playwright configuration if present
```

If a file or folder does not exist, Cursor must report that clearly instead of inventing it.

---

# 12. Confidence And Bug Gate

Cursor must not rush into coding.

The LLM must produce:

```text
1. Repo findings with file paths.
2. Current architecture summary.
3. What already exists and should be reused.
4. What is missing.
5. Bugs or conflicts found.
6. Risk list.
7. Proposed phases.
8. Database impact.
9. UI impact.
10. Test strategy.
11. Rollback strategy.
12. Confidence score.
```

## Confidence rule

- If confidence is below 96%, do not code.
- If confidence is 96% or higher, explain the evidence supporting that confidence.
- Do not fake confidence.
- Do not claim 100% certainty.
- “100% pass” means the proposed acceptance tests, migrations, and UI checks must pass before the phase is considered complete.

## Bug rule

Every discovered bug must be recorded as:

```text
Bug ID:
Area:
File(s):
Symptom:
Likely cause:
Risk:
Fix recommendation:
Test needed:
Priority:
```

## Approval rule

Cursor must first produce the plan. The owner reviews. Only after approval may Cursor implement Phase 1.

---

# 13. Phase Plan To Propose

Cursor should inspect the repo and then adapt this draft phase plan.

## Phase 0 — Repo inspection and master plan only

No code changes.

Output:

- exact current repo state;
- exact docs found;
- exact routes and modules found;
- exact Supabase/migrations found;
- exact broken SAM/meat sales findings;
- exact recommended CHARLIE Core plan;
- exact FRED MVP plan;
- exact proposed DB/data model;
- exact test plan;
- confidence score.

## Phase 1 — Documentation and Brain structure

Add or update docs only.

Possible files:

```text
docs/00-start-here/CHARLIE_CORE_MASTER_PLAN.md
docs/01-architecture/CHARLIE_CORE_ARCHITECTURE.md
docs/01-architecture/AGENT_COLLABORATION_LEDGER.md
docs/01-architecture/BUSINESS_UNIT_ARCHITECTURE.md
docs/08-business-modules/SAM_MEAT_SALES_RECOVERY_PLAN.md
docs/08-business-modules/FRED_TRANSPORT_MODULE_PLAN.md
docs/07-decisions/ADR_XXXX_CHARLIE_CORE_TOP_LEVEL_ORCHESTRATOR.md
```

If `docs/farm-brain/` already exists, extend it carefully. If not, propose whether to use:

```text
docs/brain/
```

or:

```text
docs/farm-brain/ for farm-specific knowledge
and docs/charlie-brain/ for top-level multi-business knowledge
```

Do not duplicate existing docs wholesale.

## Phase 2 — Agent Collaboration Ledger design

Plan first, then implement after approval.

Likely data concepts:

```text
business_units
agent_teams
agent_tasks
agent_result_packets
agent_activity_events
agent_handoffs
agent_shared_context_snapshots
owner_decisions
```

Cursor must inspect current existing Oom Sakkie trace/approval tables first and reuse where practical.

## Phase 3 — SAM Meat Sales Recovery

Fix the money flow.

Required outputs:

- SAM dashboard exposes missing facts and reply readiness;
- Ledger exposes price/deposit/follow-up status;
- Butcher exposes meat availability/demand pressure;
- Beacon exposes draft-only demand generation;
- Gatekeeper exposes approvals/blocks;
- no customer send without existing/approved rails;
- Oom Sakkie/CHARLIE can summarize the flow.

## Phase 4 — CHARLIE Core minimal orchestrator

Add top-level `CHARLIE` layer without breaking Oom Sakkie.

Potential module structure, subject to repo inspection:

```text
modules/charlie_core/
  __init__.py
  business_units.py
  registry.py
  tasks.py
  result_packets.py
  handoffs.py
  shared_context.py
  approvals.py
  brain_context.py
  build_requests.py
```

Potential routes, subject to repo style:

```text
/api/charlie/brief
/api/charlie/business-units
/api/charlie/tasks
/api/charlie/result-packets
/api/charlie/handoffs
/api/charlie/approvals
```

Do not create a new frontend framework.

## Phase 5 — FRED Transport MVP

Add FRED as a new business module under CHARLIE.

Start with:

- docs;
- schema proposal;
- routes;
- simple dashboard;
- lead/job tracking;
- quote/draft-only flow;
- owner approval gates;
- result packets.

## Phase 6 — Build Team workflow

Add structured build request and patch planning workflow across all modules.

This may reuse existing Oom Sakkie build/patch/deploy rails if they already exist.

## Phase 7 — Brain retrieval later

Only after docs/governance are stable.

Start read-only. Approved docs only. Retrieval events logged. No risky action execution from Brain retrieval.

---

# 14. Non-Negotiables

Do not:

- replace Supabase;
- move live data into Markdown;
- make Obsidian required;
- use external Jarvis/ZOEY as the core brain;
- create a new frontend framework;
- break `/oom-sakkie`;
- remove existing Oom Sakkie agents;
- bypass Gatekeeper;
- send WhatsApp/customer messages without approval rails;
- write payments/deposits/orders without source-of-truth workflows;
- deploy code without test and release gate;
- expose secrets in frontend or docs;
- fake test results;
- invent files/routes/tables that were not inspected.

---

# 15. Acceptance Criteria For The Plan

The plan is acceptable only if it answers:

1. What exactly exists today?
2. What is broken in SAM/meat sales?
3. How will CHARLIE sit above Oom Sakkie without replacing it?
4. How will agents share results and handoffs in Supabase?
5. How will FRED be added as transport commander?
6. What docs must be created or updated?
7. What migrations are needed, if any?
8. What can be reused from current Oom Sakkie traces/approval/build rails?
9. What are the safety boundaries?
10. What test commands will be run?
11. What can be delivered first to help money/sales?
12. What requires owner approval before implementation?
13. What is the confidence score and evidence?

---

# 16. Copy/Paste Prompt For Cursor — Planning Mode

Copy everything below this line into Cursor.

---

## CURSOR PROMPT: CHARLIE CORE REPO REVIEW AND BUILD PLAN

You are now acting as **CHARLIE SYSTEM ARCHITECT + TOP DEVELOPER + RELEASE GATEKEEPER** for this repo.

You are not here to make random changes. You are here to inspect the whole project, understand the current architecture, find what already exists, identify what is broken, and produce a build plan that is safe, practical, phased, and strong enough to execute.

The owner’s decision is final:

> Build **CHARLIE CORE** as the top-level Jarvis-like operating layer across all businesses.  
> Keep **Oom Sakkie** as the Farm Commander under CHARLIE.  
> Fix **SAM Meat Sales** as the urgent money-flow priority.  
> Plan **FRED** as the Transport Commander/module.  
> Keep **Supabase** as the live operational source of truth.  
> Keep Brain/Vault Markdown as approved guidance only.  
> Do not make Obsidian, ZOEY, or hosted Jarvis the core system.  
> Do not bypass Gatekeeper or owner approval.

### Your mindset

Think like a world-class principal engineer and systems architect.

You are simple, practical, careful, and confident. You do not overcomplicate the view or the architecture. You reuse what exists. You do not rebuild the whole app if the current app can be extended safely. You protect business data. You protect the owner’s time. You build toward revenue and reliable operations.

### Required first action

Inspect the repo before proposing implementation.

Read or locate these areas:

```text
app.py
modules/
modules/oom_sakkie/
modules/sales/
modules/orders/
modules/telemetry/
services/database_service.py
supabase/migrations/
templates/
static/js/
static/css/
static/assets/agents/agent_registry.json
docs/00-start-here/
docs/01-architecture/
docs/05-ai/
docs/07-decisions/
docs/08-business-modules/
requirements.txt
test configuration / pytest / Playwright configuration
```

If a path does not exist, say it does not exist. Do not invent files.

### Current known direction

The current product direction is:

- `/oom-sakkie` remains the farm command center.
- The owner-facing flow must avoid long technical workbenches.
- Oom Sakkie must coordinate farm agents.
- Specialist agents should feel like focused rooms, not database tables.
- System Workbench is secondary audit/admin.
- Dangerous actions remain blocked until approval rails exist.
- Agent assets belong under `static/assets/agents/`.
- Supabase remains the operational truth.
- Brain/Vault docs are human-readable guidance only.
- Obsidian is optional only.

### Target architecture

Use this hierarchy:

```text
CHARLIE CORE
  ├── Owner Command Layer
  ├── Oom Sakkie / Farm Business
  ├── Meat Sales Team
  ├── FRED / Transport Business
  ├── Build Team
  └── Brain / Vault
```

Oom Sakkie is not replaced. It becomes the farm commander.

FRED is the planned transport commander.

SAM is the urgent meat sales/customer conversation priority.

### Required collaboration model

Agents must share safe, structured results through Supabase.

Evaluate existing traces/approvals/build rails first. Then propose how to add or reuse:

```text
business_units
agent_teams
agent_tasks
agent_result_packets
agent_activity_events
agent_handoffs
agent_shared_context_snapshots
approval_requests / existing approval rails
owner_decisions
```

Do not move live collaboration state into Markdown.

### Urgent business priority: SAM Meat Sales

Inspect and plan how to fix:

```text
/sales/meat-leads
/sales/meat-driver
/sales/slaughter
/sales-dashboard
modules/sales/*
modules/oom_sakkie/*sales*
Chatwoot/WhatsApp/customer-followup gates
meat sales Supabase migrations/tables
Sam specialist/dashboard state
Ledger/Butcher/Beacon/Gatekeeper connections
```

Plan a working flow where:

```text
Lead/customer inquiry -> Sam missing facts -> Ledger price/deposit/follow-up -> Butcher availability/demand pressure -> Beacon draft demand copy -> Gatekeeper approval/block -> Owner decision -> Supabase log -> Oom Sakkie/CHARLIE summary
```

No customer message may be sent without approved rails.

### Future money module: FRED Transport

Plan FRED as a transport module under CHARLIE.

First MVP should cover:

```text
transport leads
load/customer opportunities
pickup/delivery locations
vehicle/driver availability
quote status
job status
cost/margin
documents/compliance reminders
customer follow-ups
owner approval gates
```

Initial FRED team:

```text
FRED — Transport Commander
Dispatch Agent
Loads / Sales Agent
Fleet Agent
Driver Comms Agent
Finance Agent
Compliance Agent
```

### Build Team requirement

Plan a Build Team under CHARLIE:

```text
Product Planner
PRISMA UI Designer
Database Engineer
Backend Engineer
Frontend Engineer
QA Tester
Docs Keeper
Release Gatekeeper
```

This Build Team must help create structured build requests, patch plans, test plans, and release gates.

### Confidence gate

Before any code is written, output a plan with confidence.

Rules:

- If confidence is below 96%, do not code.
- If confidence is 96% or higher, explain the repo evidence that supports it.
- Do not fake 100% certainty.
- Do not claim tests passed unless you ran them.
- “100% pass” means the defined acceptance checks and tests must pass before the implementation is accepted.

### Bug gate

Find and log bugs/conflicts in this format:

```text
Bug ID:
Area:
File(s):
Symptom:
Likely cause:
Risk:
Fix recommendation:
Test needed:
Priority:
```

### Output required now

Do not code yet.

Produce a markdown plan with these sections:

```text
1. Executive decision
2. Repo findings with file paths
3. Existing architecture summary
4. What already exists and must be reused
5. What is missing
6. Current SAM Meat Sales diagnosis
7. Proposed CHARLIE Core architecture
8. Proposed Agent Collaboration Ledger
9. Proposed SAM Meat Sales recovery plan
10. Proposed FRED Transport MVP plan
11. Proposed Build Team workflow
12. Brain/Vault and docs plan
13. Supabase/data model impact
14. UI impact
15. Safety and Gatekeeper rules
16. Bugs/conflicts found
17. Implementation phases
18. Test strategy with exact commands
19. Rollback strategy
20. Confidence score and evidence
21. Questions for owner approval
```

### Critical constraints

Do not:

- replace Supabase;
- move live data into Markdown;
- make Obsidian required;
- make ZOEY or hosted Jarvis the main system;
- create a new frontend framework;
- rebuild `/oom-sakkie` unnecessarily;
- remove current farm agents;
- bypass Gatekeeper;
- send customer messages without approved rails;
- expose secrets;
- invent routes/tables/files;
- skip tests;
- implement before the owner approves the plan.

### Final instruction

Your immediate task is **planning only**.

Inspect the repo. Produce the plan. Be direct. Flag bugs. Flag risks. Propose the shortest safe path that delivers revenue first through SAM Meat Sales, then sets up CHARLIE Core and FRED Transport correctly.

Do not start coding until the owner approves the plan.

---

# 17. Copy/Paste Prompt For Cursor — Implementation Mode After Plan Approval

Only use this after the owner has reviewed and approved the planning output.

---

## CURSOR PROMPT: IMPLEMENT APPROVED CHARLIE PHASE

You are now implementing the approved CHARLIE Core phase.

Use the approved plan only. Do not expand scope.

Before editing:

1. Restate the approved phase.
2. List exact files you will touch.
3. List exact tests you will run.
4. Confirm no secrets will be exposed.
5. Confirm Supabase remains source of truth.
6. Confirm Gatekeeper/approval rails are not bypassed.

During implementation:

- make small commits/patches logically;
- update docs alongside code;
- keep current Flask/Jinja/static JS/CSS stack unless the approved plan says otherwise;
- reuse existing Oom Sakkie rails where possible;
- add tests for new behavior;
- log any new bug found;
- stop if a risk appears that changes the approved plan.

Before finishing:

1. Run the agreed tests.
2. Report pass/fail evidence.
3. List changed files.
4. List any unresolved risks.
5. List manual checks needed.
6. Produce next recommended phase.

Do not claim completion unless the acceptance checks pass.

---

# 18. Owner Notes For Review

When Cursor returns the plan, review especially:

- whether it found the real SAM/meat-sales breakages;
- whether it preserves Oom Sakkie as farm commander;
- whether CHARLIE is clearly above Oom Sakkie;
- whether agent collaboration is Supabase-backed;
- whether FRED is MVP and money-focused, not overbuilt;
- whether the Build Team helps reduce owner time;
- whether it avoids tool shopping and external product dependency;
- whether tests and rollback are real;
- whether confidence is justified by repo evidence.

Only approve Phase 1 if the plan is clear, practical, and safe.

