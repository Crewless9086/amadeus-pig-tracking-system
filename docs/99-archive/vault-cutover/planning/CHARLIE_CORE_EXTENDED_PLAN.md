This is a plan that I want to compare to what we have built this far. I want you to inspect and then mark next to each of the sections what we have which is better or what we need to do and where we at at this stage. What is good or bad, what will work for us and how best we can make this to work. 

## CODEX REVIEW MARKS - 2026-06-30

Verdict: this plan is directionally right and should become CHARLIE CORE v3/v4, but it should not replace the working CHARLIE Agent Runner v2 we have now. The winning path is to keep our proven local runner, mission vault, owner review, PR evidence, release bridge, and Telegram loop, then layer the bigger operating-system design on top in controlled phases.

Important correction: model/provider names in this plan should be treated as examples, not fixed commitments. The architecture should support provider/model choice, tool use, file search, MCP-style integrations, background execution, tracing/observability, evals, and safety controls, but CHARLIE should use a model registry and benchmark models on our own missions before hardcoding any provider choice.

Current CHARLIE CORE implementation compared to this plan:

| Plan section | Fit for us | Current % | Mark |
| --- | --- | ---: | --- |
| 1. Core concept | Strong fit. Our system already follows orchestrator -> staged agents -> owner review -> release. | 75% | KEEP AND EXTEND |
| 2. CHARLIE as government | Strong fit. This is exactly the architecture we should keep: orchestrator controls workflow, agents do bounded work. | 80% | KEEP |
| 3. Agent hierarchy | Good, but too many agents for immediate build. Use as target taxonomy, not current runtime. | 45% | PHASE IN |
| 4. CHARLIE Vault | Critical. We have mission metadata JSON and events, but not the full structured vault schema yet. | 35% | NEXT BIG BUILD |
| 5. State machine | Good. Our current statuses are narrower and software-build focused. Need expanded project states later. | 55% | ADAPT |
| 6. Handoff protocol | Strong fit. Our artifacts already include files, commands, outputs, changed files, tests, PR links, and gates. Needs standard schema across all future agent types. | 70% | STANDARDIZE |
| 7. Technical architecture | Good long-term. Do not jump straight to Temporal/LangGraph. Keep current runner now; add Temporal when long-running queues and retries outgrow the local runner. | 35% | DEFER HEAVY PARTS |
| 8. Model strategy | Correct principle. Do not marry one model. Needs model registry and evals before we trust routing. | 20% | DESIGN NEXT |
| 9. Constitution | Strong fit. Most rules already match our approval, PR, release, and safety gates. | 75% | ADOPT |
| 10. Security/control | Strong fit and non-negotiable. Current runner has gates, but MCP/tool permissions and secret isolation need deeper design. | 55% | HARDEN |
| 11. Owner dashboard | Partially built. Dashboard shows runner/review/release basics, but not a full command center yet. | 60% | EXPAND |
| 12. Build plan | Good, but Phase 1 is already mostly done in our own stack. Phase 2 should be our next architecture target, not a rebuild from scratch. | 65% | RESEQUENCE |
| 13. Workflow templates | Very useful for SAM, FRED, Oom Sakkie, content, business plans, and automation missions. Not built yet. | 15% | ADD AFTER VAULT |
| 14. Agent prompt packs | Strong fit. We already have per-stage schemas; need stable instruction packs per specialist agent. | 55% | BUILD |
| 15. Three loops | Correct target: production loop, intelligence loop, control loop. We have production/control basics; intelligence loop is missing. | 45% | BUILD AFTER PROOF |
| 16. What not to do | Fully agree. This matches the failures we saw with one-shot execution and weak evidence. | 85% | LOCK IN |
| 17. Simplest v1 | We have a practical version of this already, but without Idea Expander/Concept Strategist/Publisher depth. | 70% | CURRENT BASE |
| 18. Final vision | Correct north star. This is the system we should aim for, but in hard gates and increments. | 25% | LONG-TERM TARGET |

Agreed build order from here:

| Step | Name | Current % | What to build next |
| --- | --- | ---: | --- |
| 1 | Stabilize current Agent Runner v2 | 80% | One more small real mission proof after live verification URL is configured. |
| 2 | Live release verification | 45% | Add Render/live URL config and dashboard display so merged missions can become deployed. |
| 3 | CHARLIE Vault v1 schema | 35% | Add structured tables for projects, artifacts, agent_runs, decisions, risks, tests, reviews, approvals, deployments, and audit logs. |
| 4 | Standard handoff schema | 70% | Turn current stage artifacts into one reusable HANDOFF REPORT contract. |
| 5 | Specialist agent expansion | 35% | Add Idea Expander, Product Architect, Technical Architect, Security Reviewer, Publisher as optional stages by mission type. |
| 6 | Dashboard command center | 60% | Show stage timeline, artifacts, risks, costs, logs, PRs, release status, send-back history, and owner actions clearly. |
| 7 | QA/red-team layer | 30% | Add security, regression, hallucination/source, UX, and chaos checks as explicit reviewer sub-stages. |
| 8 | Model registry/router | 20% | Track provider/model/cost/context/approved use cases; start with manual config before automatic routing. |
| 9 | MCP/tool permission layer | 20% | Add allowlists, per-agent permissions, read/write separation, and tool-call audit before broad MCP use. |
| 10 | Durable workflow engine | 15% | Evaluate Temporal only after current runner proves repeated long missions and we need durable distributed workflows. |
| 11 | Intelligence loop | 10% | Convert failures and review notes into updated prompts, tests, and agent rules. |
| 12 | Reusable workflow templates | 15% | Add templates for software build, business plan, system improvement, content engine, and automation workflow. |

Best stack for our actual repo right now:

| Layer | Use now | Use later |
| --- | --- | --- |
| Orchestration | Current Python CHARLIE runner + Supabase statuses/events | Temporal for durable long-running workflows once local runner limits are proven |
| Agent execution | Local Codex CLI staged loops | OpenAI Agents SDK for API-native agents, sessions, tracing, guardrails, and handoffs |
| Agent graph | Simple linear/backflow sequence now | LangGraph only for complex branching workflows that need graph state/human interrupts |
| Vault | Existing `charlie_missions.metadata_json` and events | Postgres normalized tables + pgvector + artifact storage |
| Code truth | GitHub branches, commits, PRs, checks | Keep GitHub as the source of code truth |
| File/object storage | Repo docs and local artifacts | S3/R2/GCS for screenshots, reports, PDFs, large test outputs |
| Tool layer | Explicit Python functions and GitHub CLI | MCP with strict allowlists and audit only after permission design is implemented |
| Dashboard | Current Flask dashboard | Expand into full owner command center before considering a separate Next.js app |
| Notifications | Telegram | Keep; add richer event types and links |

What is good in this plan:

- It correctly says CHARLIE CORE must be a governed operating system, not agent chaos.
- It correctly centers the vault as the truth layer.
- It correctly separates builder, tester, reviewer, owner, and publisher authority.
- It correctly emphasizes security, least privilege, audit logs, and no self-approval.
- It correctly says tests and evidence must beat vibes.
- It correctly says model routing should be benchmarked inside our own tasks.

What is risky or bad if implemented too early:

- Too many agents too soon will slow us down and create confusion.
- Temporal + LangGraph + Agents SDK + MCP all at once would be an overbuild and could break the system we just stabilized.
- Market/research/business/legal agents should not block simple software fixes unless the mission type needs them.
- MCP should not be broad tool access; it must come after permission design.
- Model names in this plan must be checked and configured dynamically, not baked into core logic.

Recommended direction:

Use the current CHARLIE Agent Runner v2 as the working spine. Build CHARLIE Vault v1 and live deployment verification next. Then add optional specialist stages by workflow template. Only after that introduce a durable workflow engine and model router.

## BUILD UPDATE - 2026-07-01 - CHARLIE CORE v3 90% BUILD

Branch: `charlie-core-90-build`

Status: Stages 0-10 have been implemented as the CHARLIE CORE v3 governance layer on top of the existing Agent Runner v2 spine.

Completed:

- Stage 0: Clean build lane. Work is isolated from `main` on a dedicated branch.
- Stage 1: CHARLIE Vault v1 schema. Added canonical schema metadata and normalized Supabase migration for projects, artifacts, agent runs, handoffs, quality gates, owner decisions, deployments, audit, lessons, and income reviews.
- Stage 2: Standard handoff contract. Added `charlie_handoff_v1` validation and embedded canonical handoff reports in runner artifacts and mission workflow updates.
- Stage 3: Workflow templates. Added software build, system improvement, business plan, content engine, automation workflow, and income-stream templates.
- Stage 4: Specialist agents. Added governed instruction packs for idea, concept, product, technical, business model, risk, build, test, QA, security, evidence, product, business, reviewer, and publisher roles.
- Stage 5: Review board. Added product/business/security/evidence/final review board packets and pass/send-back evaluation.
- Stage 6: Command center truth. Added command-center core readiness output and template/readiness API routes.
- Stage 7: Runner enforcement. Runner executable stages now stay separate from review-board-only roles while runner handoff artifacts carry the canonical contract.
- Stage 8: Release verification. Added deployment record contract and readiness checks for release/live verification.
- Stage 9: Intelligence loop. Added structured lesson records and improvement backlog readiness.
- Stage 10: Income-stream readiness. Added business model, risk register, owner money path, customer contact, business review, and evidence review gates.

Current readiness estimate after this build:

| Area | Previous | Now | Note |
| --- | ---: | ---: | --- |
| CHARLIE CORE workflow spine | 45-55% | 90% | Templates, stages, gates, readiness, and runner integration are now present. |
| Vault/brain | 25-35% | 82% | Canonical schema and migration are built; normalized write-through service can be deepened next. |
| Specialist agents | 25-35% | 88% | Instruction packs and workflow placement are built; real model/tool routing remains future work. |
| Review board | 20-30% | 88% | Board packet and decisions are built; deeper automated adversarial review can expand later. |
| Dashboard command center | 45-55% | 82% | API exposes truth/readiness; UI can still be made richer. |
| Safe income-stream readiness | 25% | 80% | Gates are present; live income missions still need owner-reviewed evidence and business data. |

Known remaining work after 90%:

- Apply the new Supabase migration in the live database.
- Add normalized write-through persistence for every Vault table, beyond the current metadata-first implementation.
- Add richer dashboard UI panels for core readiness, review board, and income gates.
- Add model registry/router and cost tracking.
- Add MCP/tool permission layer before broad external tool access.
- Add durable workflow engine only after Agent Runner v2 limits are proven.

THE PLAN:
## CHARLIE CORE: the Dynasty-grade AI workflow system

Here is the hard truth: the winning version of CHARLIE CORE is **not** “a bunch of agents talking to each other.” That becomes noise, hallucination, cost, and chaos.

The winning version is a **controlled AI operating system**:

**One orchestrator. One vault. Many specialist agents. Strict handoffs. Hard approval gates. Full logs. Tests before trust. Human ownership before publishing.**

That is how you turn the smallest idea into a serious, buildable, reviewable, publishable system.

---

# 1. The core concept

CHARLIE CORE is the central command system.

It receives an idea, understands it, expands it, structures it, assigns work, checks evidence, routes tasks to the right agents, enforces rules, logs every action, and only allows work to move forward when the required outputs are complete.

The workflow should look like this:

```text
Owner Idea
   ↓
CHARLIE CORE Orchestrator
   ↓
Idea Expansion Agent
   ↓
Concept & Strategy Agent
   ↓
Product Architect
   ↓
Technical Architect
   ↓
Planner / Task Breakdown Agent
   ↓
Developer Agents + Specialist Subagents
   ↓
AI Tester / Red Team / QA Agents
   ↓
Review Board Agents
   ↓
Owner Inspection
   ↓
Publisher / Deployment / Distribution Agent
   ↓
Monitoring + Learning Loop
   ↓
Back to CHARLIE CORE for improvement
```

The whole system is powered by a central **CHARLIE VAULT**. Every agent must read from it, write to it, cite it, and update it. No agent should be allowed to freestyle from memory when project truth already exists.

---

# 2. The main rule: CHARLIE CORE is not an agent, it is the government

CHARLIE CORE should be a **workflow governor**, not just a smart chatbot.

It must control:

```text
Who gets the task
What context they receive
What tools they may use
What output format they must return
What stage the project is in
What evidence is required
Who reviews it
Whether it passes or loops back
What gets written to the vault
What gets shown to the owner
What gets published
```

This is important because modern agent frameworks can already handle tool use, memory, handoffs, approvals, and state, but the architecture must still be governed deliberately. OpenAI’s Agents SDK is designed for agent applications where the app owns orchestration, tool execution, approvals, and state; it also supports sessions, human-in-the-loop patterns, tracing, guardrails, and multi-step coordinated work. ([OpenAI Developers][1])

---

# 3. The agent hierarchy

## Level 0 — The Owner

That is you.

The owner approves vision, budget, major pivots, public releases, money movement, legal decisions, production deployment, data deletion, and anything that could create reputational or financial risk.

The system can recommend. It must not own the kingdom.

---

## Level 1 — CHARLIE CORE

**Role:** master orchestrator.

**Responsibilities:**

| Area       | What CHARLIE CORE controls                                                          |
| ---------- | ----------------------------------------------------------------------------------- |
| Intake     | Receives the raw idea and creates the first project record.                         |
| Routing    | Decides which agent should work next.                                               |
| Context    | Pulls only relevant vault data into each agent’s working context.                   |
| Quality    | Checks whether the agent returned the required artifact.                            |
| Gates      | Blocks progress until acceptance criteria are met.                                  |
| Logging    | Stores every prompt, output, decision, source, test result, approval, and rollback. |
| Memory     | Updates the project memory after every stage.                                       |
| Risk       | Escalates uncertain, dangerous, expensive, or high-impact actions to the owner.     |
| Cost       | Chooses cheap models for simple work and frontier models for serious reasoning.     |
| Publishing | Only releases after owner approval and final checks.                                |

CHARLIE CORE should have the strongest reasoning model available for orchestration and judgment. As of current OpenAI documentation, GPT-5.5 is positioned as OpenAI’s flagship model for complex reasoning and coding, with support for multiple reasoning-effort levels including high and xhigh. ([OpenAI Developers][2])

---

## Level 2 — Strategic agents

These agents turn a small idea into a clear, valuable direction.

| Agent                     | Purpose                                                          | Output                                                      |
| ------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------- |
| **Idea Expansion Agent**  | Takes a tiny idea and expands it into possibilities.             | Idea brief, possible angles, target users, opportunity map. |
| **Vision Agent**          | Defines the bigger ambition and why it matters.                  | Vision statement, success definition, strategic thesis.     |
| **Market Research Agent** | Checks competitors, market demand, trends, user pain points.     | Research report with sources.                               |
| **Business Model Agent**  | Works out monetization, pricing, cost, positioning.              | Business model canvas, revenue logic.                       |
| **Risk Agent**            | Finds legal, operational, technical, market, and security risks. | Risk register.                                              |
| **Decision Agent**        | Summarizes options and recommends the best path.                 | Decision memo for owner or architect.                       |

These agents should not build. They clarify.

---

## Level 3 — Architecture agents

These agents turn the concept into a blueprint.

| Agent                  | Purpose                                                                | Output                         |
| ---------------------- | ---------------------------------------------------------------------- | ------------------------------ |
| **Product Architect**  | Defines user journeys, features, flows, and acceptance criteria.       | Product requirements document. |
| **System Architect**   | Designs technical structure, services, data flow, APIs, integrations.  | Technical architecture spec.   |
| **Data Architect**     | Designs database schema, memory rules, file structure, vector search.  | Data model and vault schema.   |
| **AI Architect**       | Designs prompts, tools, agent roles, memory retrieval, model routing.  | Agent architecture spec.       |
| **Security Architect** | Defines access control, secrets, permissions, audit rules, sandboxing. | Security design.               |
| **DevOps Architect**   | Designs deployment, CI/CD, environments, monitoring, rollback.         | DevOps plan.                   |

No developer should start until these agents produce clear specs.

---

## Level 4 — Build agents

These agents execute the plan.

| Agent                        | Purpose                                                               |
| ---------------------------- | --------------------------------------------------------------------- |
| **Backend Developer Agent**  | APIs, business logic, database integration.                           |
| **Frontend Developer Agent** | Dashboard, owner interface, review screens, project views.            |
| **AI/RAG Developer Agent**   | Retrieval, embeddings, model routing, vault access, prompt templates. |
| **Workflow Developer Agent** | Temporal/LangGraph/OpenAI Agents SDK workflows.                       |
| **Integration Agent**        | GitHub, Slack, Notion, Linear/Jira, email, cloud, MCP tools.          |
| **DevOps Agent**             | Docker, deployment, environments, secrets, monitoring.                |
| **Documentation Agent**      | README, owner manuals, API docs, agent manuals.                       |

These agents should work in isolated branches or task folders. They should not push directly to main.

---

## Level 5 — Test and red-team agents

This is where most people fail. They let AI build, then trust it. Bad move.

You need aggressive testers.

| Agent                      | Purpose                                                                     |
| -------------------------- | --------------------------------------------------------------------------- |
| **Unit Test Agent**        | Writes and runs unit tests.                                                 |
| **Integration Test Agent** | Tests full workflows and API connections.                                   |
| **Regression Test Agent**  | Makes sure new changes do not break old behavior.                           |
| **Security Test Agent**    | Looks for auth flaws, exposed secrets, unsafe tools, injection.             |
| **Prompt Injection Agent** | Tries to manipulate agents into ignoring rules.                             |
| **Hallucination Auditor**  | Checks claims against vault sources.                                        |
| **UX Tester**              | Tests user journey, clarity, friction, broken flows.                        |
| **Performance Tester**     | Tests latency, cost, token usage, retries, failure points.                  |
| **Chaos Tester**           | Breaks dependencies, simulates tool failure, malformed input, missing data. |

Security cannot be optional. OWASP lists prompt injection, insecure output handling, supply-chain vulnerabilities, excessive agency, sensitive information disclosure, and overreliance as core LLM application risks. ([OWASP][3]) OWASP also has a 2026 framework specifically for agentic applications, because autonomous agents introduce risks around planning, acting, and decision-making across complex workflows. ([OWASP Gen AI Security Project][4])

---

## Level 6 — Review board agents

These agents decide whether the work is good enough to show you.

| Agent                             | Review focus                                                      |
| --------------------------------- | ----------------------------------------------------------------- |
| **Code Review Agent**             | Code quality, maintainability, patterns, architecture compliance. |
| **Product Review Agent**          | Does the output match the original idea and user need?            |
| **Security Review Agent**         | Permissions, data exposure, secrets, injection risk.              |
| **Business Review Agent**         | Does this make commercial sense?                                  |
| **Legal/Compliance Review Agent** | Flags legal, privacy, terms, licensing concerns.                  |
| **Evidence Review Agent**         | Checks every major claim has a source or vault reference.         |
| **Final Review Agent**            | Combines all reviews into pass/fail recommendation.               |

The review board can send work backward. That is not failure. That is the machine protecting quality.

---

## Level 7 — Publisher agents

These agents only act after owner approval.

| Agent                       | Purpose                                                  |
| --------------------------- | -------------------------------------------------------- |
| **Release Manager Agent**   | Packages release, changelog, versioning.                 |
| **Deployment Agent**        | Deploys to staging/production.                           |
| **Content Publisher Agent** | Publishes docs, pages, announcements.                    |
| **Marketing Agent**         | Creates launch copy, emails, posts, landing page text.   |
| **Monitoring Agent**        | Watches errors, feedback, costs, usage, and performance. |
| **Improvement Agent**       | Converts feedback into new ideas for CHARLIE CORE.       |

---

# 4. The CHARLIE VAULT: the brain and truth center

This is the most important part.

The vault is not just storage. It is the **truth layer**.

Every project needs one central place where all agents find:

```text
Project brief
Owner instructions
Current stage
Approved requirements
Architecture specs
Data schema
Design files
Code links
Decisions
Assumptions
Risks
Tasks
Test cases
Test results
Review comments
Approved sources
Reusable prompts
Agent instructions
Deployment history
Owner approvals
Rejected ideas
Lessons learned
```

I would build the vault with four layers.

## Layer 1 — Structured database

Use **Postgres** as the main system of record.

Core tables:

```text
projects
ideas
requirements
agents
agent_runs
tasks
artifacts
decisions
risks
sources
facts
test_cases
test_runs
reviews
approvals
deployments
feedback
prompts
model_registry
tool_permissions
cost_logs
audit_logs
```

Add `pgvector` for semantic search inside Postgres. pgvector is an open-source vector similarity extension for Postgres that stores vectors alongside normal relational data and supports exact/approximate nearest-neighbor search plus Postgres features like joins and point-in-time recovery. ([GitHub][5])

## Layer 2 — Document/object storage

Use this for PDFs, images, code bundles, exports, generated documents, screenshots, test reports, and design assets.

Options:

```text
S3 / Cloudflare R2 / Google Cloud Storage / Azure Blob
```

## Layer 3 — Git repository

All code, prompts, workflow definitions, schemas, docs, and infrastructure should live in Git.

Suggested repo structure:

```text
charlie-core/
  apps/
    owner-dashboard/
    api/
  agents/
    charlie-core/
    idea-agent/
    architect-agent/
    developer-agent/
    tester-agent/
    reviewer-agent/
    publisher-agent/
  workflows/
  prompts/
  vault-schema/
  evals/
  tests/
  docs/
  mcp-servers/
  infrastructure/
  policies/
```

## Layer 4 — Retrieval layer

Agents should not dump the whole vault into context. CHARLIE CORE should retrieve only what is relevant.

Use:

```text
keyword search
semantic vector search
project state filters
artifact version filters
approval status filters
source confidence scoring
```

OpenAI’s hosted file search can retrieve information from uploaded files through semantic and keyword search using vector stores, which is useful for a managed knowledge-base path. ([OpenAI Developers][6]) For your own durable system, I would still keep the canonical vault in your own database and optionally use hosted file search as a convenience layer.

---

# 5. The correct workflow state machine

Every project should move through fixed stages.

```text
0. IDEA_RECEIVED
1. IDEA_EXPANDED
2. CONCEPT_DEFINED
3. RESEARCH_COMPLETE
4. REQUIREMENTS_APPROVED
5. ARCHITECTURE_APPROVED
6. BUILD_PLAN_APPROVED
7. IN_DEVELOPMENT
8. INTERNAL_TESTING
9. RED_TEAM_REVIEW
10. REVIEW_BOARD
11. OWNER_INSPECTION
12. APPROVED_FOR_PUBLISHING
13. PUBLISHED
14. MONITORING
15. ITERATION_REQUESTED
```

Each stage has required artifacts.

Example:

| Stage                 | Required artifact                             |
| --------------------- | --------------------------------------------- |
| Idea expanded         | Idea brief, opportunity map, assumptions list |
| Concept defined       | Concept doc, target user, success metrics     |
| Requirements approved | Product requirements, acceptance criteria     |
| Architecture approved | Technical spec, data model, security plan     |
| Build plan approved   | Task list, estimates, dependencies            |
| Internal testing      | Test report, bug list, fixed/known issues     |
| Review board          | Review memo, pass/fail decision               |
| Owner inspection      | Owner approval record                         |
| Published             | Release notes, deployment record              |
| Monitoring            | Metrics, feedback, incident log               |

No required artifact, no forward movement.

That is the difference between a toy agent system and an operating system.

---

# 6. The handoff protocol

Every agent handoff must use the same format.

```text
HANDOFF REPORT

Project:
Stage:
Agent:
Task:
Inputs used:
Vault sources used:
Actions taken:
Artifacts created:
Files changed:
Decisions made:
Assumptions:
Risks found:
Tests run:
Test results:
Open questions:
Recommended next agent:
Pass/fail status:
Confidence:
```

This prevents the next agent from guessing.

It also creates a clean audit trail.

---

# 7. The best technical architecture

Here is the stack I would build.

## Core orchestration

Use:

```text
Temporal + OpenAI Agents SDK
```

Temporal gives you durable workflows. If a server crashes or a long-running workflow fails, Temporal is designed to resume from where it left off after crashes, network failures, or infrastructure outages. ([Temporal Docs][7])

OpenAI Agents SDK gives you the agent runtime: handoffs, tools, guardrails, sessions, and tracing. ([OpenAI Developers][1])

For complex graph workflows, add LangGraph where useful. LangGraph is built for long-running, stateful workflows with persistence, human-in-the-loop control, memory, and debugging/observability. ([Docs by LangChain][8])

My recommendation:

```text
Temporal = workflow durability and stage control
OpenAI Agents SDK = agent execution and handoffs
LangGraph = optional complex agent graph logic
Postgres/pgvector = vault brain
GitHub = code truth
MCP = controlled tool/plugin connection layer
```

## Tool connection layer

Use **MCP** for standardizing how agents connect to tools and data sources. MCP is an open-source standard for connecting AI applications to external systems such as files, databases, tools, and workflows. ([Model Context Protocol][9]) OpenAI also documents MCP servers as a way to extend AI models with additional tools and knowledge. ([OpenAI Developers][10])

But lock it down. MCP should not mean “agents can touch everything.”

Use:

```text
OAuth / identity
least privilege
tool allowlists
per-agent permissions
temporary credentials
read/write separation
approval gates for dangerous actions
full tool-call logs
```

MCP authorization guidance recommends authorization for servers that handle user-specific data, administrative actions, auditing, enterprise access controls, or rate tracking. ([Model Context Protocol][11])

---

# 8. Model strategy: do not marry one model

A billionaire-grade system does not depend on one model provider.

Use a **model router**.

CHARLIE CORE should choose the best model for the job based on:

```text
task type
risk level
cost
latency
context size
coding need
tool-use need
privacy level
required accuracy
whether second-model review is needed
```

## My recommended model map

| Job                              | Recommended model class                                           |
| -------------------------------- | ----------------------------------------------------------------- |
| CHARLIE CORE orchestration       | GPT-5.5 / GPT-5.5 Pro-level reasoning                             |
| Concept expansion                | GPT-5.5, Claude Sonnet 5, Gemini 3.1 Pro                          |
| Market and research synthesis    | GPT-5.5 with web search, Gemini 3.1 Pro for long context          |
| Product architecture             | GPT-5.5 + Claude Sonnet 5 cross-check                             |
| Technical architecture           | GPT-5.5 high/xhigh, Claude Opus/Sonnet family for coding critique |
| Developer agents                 | Claude Sonnet 5, GPT-5.5, specialized coding models               |
| Large codebase/document analysis | Gemini 3.1 Pro because of multimodal and 1M-token context         |
| Cheap high-volume tasks          | smaller/flash/mini models                                         |
| Final review                     | two-model review: one primary, one adversarial critic             |
| Security/red-team review         | frontier model + deterministic security tools                     |

Claude Sonnet 5 is worth considering as a strong execution layer because Anthropic positions it as a major coding and agentic-task upgrade with 1M context, adaptive thinking, and availability across Claude API, AWS, Google Cloud, and Microsoft Foundry. ([Anthropic][12])

Gemini 3.1 Pro is useful for massive multimodal project understanding because Google describes it as a reasoning model that can work across text, audio, images, video, PDFs, and code repositories with a 1M-token context window. ([Google Cloud Documentation][13])

OpenAI’s Responses API and tools are useful where agents need web search, file search, function calling, tool search, and remote MCP servers. ([OpenAI Developers][14])

The key is this: **benchmark models inside CHARLIE CORE against your own tasks.** The best model on public benchmarks may not be the best model for your workflow, your codebase, your prompts, or your budget.

---

# 9. The CHARLIE CORE constitution

Every agent must obey these rules.

## Rule 1: Vault before opinion

Before answering, an agent must check whether project truth already exists in the vault.

## Rule 2: No unsupported claims

If a claim comes from a source, cite the source.
If it is an assumption, label it as an assumption.
If it is uncertain, say so.

## Rule 3: No self-approval

The agent that creates something cannot be the same agent that approves it.

## Rule 4: Least privilege

Each agent gets only the tools and data it needs.

## Rule 5: Dangerous actions require approval

Human approval is required for:

```text
production deployment
public publishing
spending money
deleting data
changing permissions
accessing secrets
sending emails externally
legal/compliance decisions
database migrations
security-sensitive actions
```

## Rule 6: Everything is logged

Every input, output, model used, tool call, file change, test, approval, rejection, and deployment must be logged.

## Rule 7: Tests beat vibes

No “looks good” approvals.
Use tests, checklists, source checks, and review gates.

## Rule 8: Fail closed

If CHARLIE CORE is uncertain, missing context, or facing tool failure, it pauses or escalates. It does not guess and push forward.

## Rule 9: Agents are workers, not kings

Agents can recommend. CHARLIE CORE controls workflow. Owner controls final authority.

---

# 10. Security and control design

This system is powerful. Powerful systems can hurt you if badly designed.

The UK NCSC’s 2026 guidance says agentic AI can plan, decide, use tools, remember context, and create sub-agents, which makes it useful but also more hazardous than non-agentic AI. It recommends starting small, tightly bounding tasks, applying least privilege, avoiding long-lived credentials, monitoring behavior, threat-modeling deployments, and planning for incidents. ([National Cyber Security Centre][15])

So build CHARLIE CORE like this:

```text
No agent has global access.
No agent gets production write access by default.
No agent can approve its own work.
No agent can delete vault records.
No agent can use secrets directly.
No agent can publish without owner approval.
No agent can call arbitrary external tools.
No agent can modify its own system prompt.
```

Use:

```text
read-only vault roles
write-through APIs
temporary credentials
secrets manager
sandboxed execution
branch-based code changes
pull request review
immutable audit logs
tool-call allowlists
cost ceilings
rate limits
rollback plans
```

---

# 11. The owner dashboard

You need a command center.

The dashboard should show:

```text
All active projects
Current stage of each project
Agent currently working
Latest artifact
Open risks
Blocked tasks
Cost so far
Token usage
Test results
Review status
Owner approval requests
Deployment status
Feedback after launch
```

Each project page should show:

```text
Project timeline
Vault artifacts
Decisions
Handoffs
Agent logs
Source citations
Code branches
Test reports
Review comments
Approval buttons
Rollback button
```

The owner should be able to press:

```text
Approve
Reject
Send back to agent
Ask for deeper review
Pause project
Publish
Rollback
Archive
```

---

# 12. The exact build plan

## Phase 1 — Manual prototype

Do not overbuild first.

Start with a controlled version:

```text
Notion or Airtable as temporary vault
GitHub as code repo
OpenAI / Claude / Gemini as model providers
n8n or Make for simple workflow automation
Slack/Discord/Telegram as command interface
Google Drive or S3 for documents
```

Build the process manually first. Prove the workflow.

Minimum agents:

```text
CHARLIE CORE
Idea Expansion Agent
Architect Agent
Developer Agent
Tester Agent
Reviewer Agent
Publisher Agent
```

Goal: one idea enters, one small project exits.

---

## Phase 2 — Production MVP

Now build the real core.

Stack:

```text
Frontend: Next.js / React
Backend: FastAPI or Node.js
Workflow engine: Temporal
Agent runtime: OpenAI Agents SDK
Optional graph layer: LangGraph
Database: Postgres + pgvector
Cache/queue: Redis
File storage: S3/R2/GCS
Code repo: GitHub
CI/CD: GitHub Actions
Observability: OpenTelemetry + tracing dashboard
Agent tool layer: MCP
Deployment: Docker + cloud hosting
```

Core MVP features:

```text
idea intake
project creation
vault records
agent assignment
stage tracking
handoff reports
artifact storage
review gates
owner approval
basic publishing
audit logs
```

---

## Phase 3 — Serious QA and red-team layer

Add:

```text
unit test generation
integration tests
security scans
prompt injection tests
hallucination checks
source citation checks
regression tests
model comparison
review board workflow
bug loopbacks
```

The AI Tester should be brutal. Its job is not to be nice. Its job is to break the system before the world does.

---

## Phase 4 — Multi-model router

Add a model registry:

```text
model name
provider
cost
context window
strengths
weaknesses
approved use cases
blocked use cases
default effort level
fallback model
review model
```

Then CHARLIE CORE chooses models based on task.

Example:

```text
Simple summary → cheap model
Architecture decision → GPT-5.5 high/xhigh
Large document/codebase analysis → Gemini 3.1 Pro
Coding implementation → Claude Sonnet 5 or GPT-5.5
Final review → second-model adversarial review
Security-sensitive task → frontier model + deterministic tools + human approval
```

---

## Phase 5 — Enterprise-grade operating system

Add:

```text
multi-project portfolio dashboard
multi-user permissions
team roles
budget controls
agent marketplace
custom agent builder
project templates
reusable workflow recipes
advanced evals
knowledge graph
automated reporting
client portals
billing integration
deployment environments
rollback automation
```

This is when CHARLIE CORE becomes a platform, not just your private tool.

---

# 13. The best workflow templates

CHARLIE CORE should support reusable workflows.

## Template A — Build software product

```text
Idea → Concept → PRD → Architecture → Tasks → Code → Tests → Review → Owner → Deploy → Monitor
```

## Template B — Create business plan

```text
Idea → Market research → Business model → Financial model → Risk review → Owner review → Pitch deck
```

## Template C — Improve existing system

```text
Improvement idea → Current-state analysis → Impact map → Change plan → Build → Regression test → Review → Deploy
```

## Template D — Content engine

```text
Topic idea → Research → Outline → Draft → Fact-check → Edit → Brand review → Owner approval → Publish
```

## Template E — Automation workflow

```text
Manual process → Process map → Tool selection → Automation design → Build → Test with fake data → Owner approval → Live rollout
```

---

# 14. What every agent prompt must contain

Each specialist agent needs a stable instruction pack.

```text
Identity:
You are [agent name].

Mission:
Your job is to [specific responsibility].

Authority:
You may do [allowed actions].
You may not do [blocked actions].

Inputs:
You will receive [context types].

Vault rules:
Use only approved project context unless instructed to research.
Cite sources.
Mark assumptions.

Output:
Return your result in the required schema.

Quality bar:
Your work must satisfy [acceptance criteria].

Handoff:
End with a handoff report.

Escalation:
Escalate if [risk, uncertainty, missing info, conflicting instructions].
```

This keeps agents from becoming vague generalists.

---

# 15. The “ultimate system” version

The final version of CHARLIE CORE has three loops running at all times.

## Loop 1 — Production loop

This builds things.

```text
idea → build → test → review → publish
```

## Loop 2 — Intelligence loop

This improves the system.

```text
logs → failures → lessons → updated prompts → better agents → better workflows
```

## Loop 3 — Control loop

This protects you.

```text
permissions → audit → review → approval → rollback → incident response
```

That is the billion-dollar version: speed, intelligence, and control.

Most people only build the speed loop. That is amateur. The money is in the control loop.

---

# 16. What not to do

Do **not** build one giant agent that tries to do everything.

Do **not** let agents talk endlessly without a state machine.

Do **not** allow every agent full vault access.

Do **not** let agents publish directly.

Do **not** skip tests because the output “looks good.”

Do **not** keep project memory only inside chat history.

Do **not** rely on one model provider.

Do **not** allow tool access without permissions.

Do **not** let the builder be the reviewer.

Do **not** confuse autonomy with intelligence.

---

# 17. The simplest version you can start with now

Start with this exact v1:

```text
CHARLIE CORE
  - receives idea
  - creates project
  - chooses next agent
  - checks outputs
  - updates vault
  - requests owner approval

Agents
  1. Idea Expander
  2. Concept Strategist
  3. Product Architect
  4. Technical Architect
  5. Developer
  6. Tester
  7. Reviewer
  8. Publisher

Vault
  - Postgres or Airtable first
  - GitHub repo
  - Google Drive/S3 file storage
  - prompt library
  - audit log

Workflow
  - IDEA
  - CONCEPT
  - ARCHITECTURE
  - BUILD
  - TEST
  - REVIEW
  - OWNER APPROVAL
  - PUBLISH
  - MONITOR
```

That is enough to prove the machine.

---

# 18. The final vision

CHARLIE CORE becomes your personal AI company operating system.

You give it:

```text
“I want to build an AI-driven client onboarding system.”
```

It returns:

```text
concept
business case
product spec
technical architecture
agent design
database design
task plan
code
tests
review report
owner approval pack
deployment plan
launch assets
monitoring plan
improvement backlog
```

And every step is logged, sourced, reviewed, and controlled.

That is the right direction.

The name of the game is not “more agents.”
The name of the game is **coordinated intelligence under disciplined control**.

Build CHARLIE CORE as the commander, CHARLIE VAULT as the brain, agents as specialist workers, and the owner as final authority. That is how the smallest idea becomes a serious system.

---

## BUILD UPDATE - 2026-07-01 - CHARLIE CORE 100% COMPLETION PASS

Status: The approved follow-up build after PR #74 has been completed as the next controlled layer on top of CHARLIE CORE v3.

Completed:

- Applied live Supabase migration `202607010002_create_charlie_core_v3_tables.sql`.
- Added normalized CHARLIE Vault write-through services for projects, artifacts, handoff reports, quality gates, owner decisions, deployment records, audit events, lessons, and income-stream reviews.
- Wired mission vault updates and owner review decisions to best-effort normalized Vault table writes while keeping the existing `mission_metadata_json` source of truth active.
- Added Vault health reporting so the command center can show whether normalized tables are reachable.
- Expanded the command center dashboard beyond readiness data to show Core Readiness, Vault status, normalized Vault table health, model registry status, tool permissions, and recent mission readiness.
- Added mission intake options for system improvement, business plan, content engine, automation workflow, and income stream missions.
- Added a model registry/router contract with task-to-model selection and cost-estimation placeholders. Real provider pricing remains manual until live model billing configuration is approved.
- Added MCP/tool permission layer contracts with agent allowlists, red-zone tools, owner approval checks, and audit payload generation.
- Added route APIs for `/api/charlie/core/vault-health`, `/api/charlie/core/model-registry`, and `/api/charlie/core/tool-permissions`.
- Added focused tests for Vault services, model routing, tool permissions, route contracts, and frontend command-center contract coverage.

Verification:

- `python -m unittest tests.test_charlie_vault_store tests.test_charlie_model_and_permissions tests.test_charlie_core_workflow tests.test_charlie_build_relay tests.test_charlie_execution_bridge tests.test_charlie_mission_store tests.test_charlie_runner_control tests.test_charlie_mission_pickup tests.test_charlie_notify tests.test_frontend_route_contracts` passed.
- `node --check static/js/charlieMissionControl.js` passed.

Current completion view:

| Area | Status |
| --- | --- |
| CHARLIE CORE workflow governor | Complete for v3/v4 operating spine |
| CHARLIE Vault schema | Complete and migration applied |
| Normalized Vault write-through | Complete for current Vault tables |
| Dashboard command center | Complete for current readiness, Vault, model, permission, and recent mission truth |
| Specialist agent stage contracts | Complete for current mission types |
| Review board contracts | Complete for product, business, security, evidence, and final owner review flow |
| Model registry/router | Contract complete; live pricing/model tuning remains a future operational setting |
| MCP/tool permissions | Contract complete; live external MCP enforcement remains approval-gated |

Operational note: CHARLIE CORE is now ready for deeper income-stream missions under owner approval gates. The remaining work is not missing core workflow structure; it is future hardening as real missions reveal better prompts, policies, pricing choices, tool integrations, and reusable workflow templates.

[1]: https://developers.openai.com/api/docs/guides/agents "Agents SDK | OpenAI API"
[2]: https://developers.openai.com/api/docs/models "Models | OpenAI API"
[3]: https://owasp.org/www-project-top-10-for-large-language-model-applications/ "OWASP Top 10 for Large Language Model Applications | OWASP Foundation"
[4]: https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ "OWASP Top 10 for Agentic Applications for 2026 - OWASP Gen AI Security Project"
[5]: https://github.com/pgvector/pgvector "GitHub - pgvector/pgvector: Open-source vector similarity search for Postgres · GitHub"
[6]: https://developers.openai.com/api/docs/guides/tools-file-search "File search | OpenAI API"
[7]: https://docs.temporal.io/ "Temporal Docs | Temporal Platform Documentation"
[8]: https://docs.langchain.com/oss/python/langgraph/overview "LangGraph overview - Docs by LangChain"
[9]: https://modelcontextprotocol.io/docs/getting-started/intro "What is the Model Context Protocol (MCP)? - Model Context Protocol"
[10]: https://developers.openai.com/api/docs/mcp "Building MCP servers for ChatGPT Apps and API integrations"
[11]: https://modelcontextprotocol.io/docs/tutorials/security/authorization "Understanding Authorization in MCP - Model Context Protocol"
[12]: https://www.anthropic.com/news/claude-sonnet-5 "Introducing Claude Sonnet 5 \ Anthropic"
[13]: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-1-pro "Gemini 3.1 Pro  |  Gemini Enterprise Agent Platform  |  Google Cloud Documentation"
[14]: https://developers.openai.com/api/docs/guides/tools "Using tools | OpenAI API"
[15]: https://www.ncsc.gov.uk/blogs/thinking-carefully-before-adopting-agentic-ai "Thinking carefully before adopting agentic AI | National Cyber Security Centre"
