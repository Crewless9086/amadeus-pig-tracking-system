# Oom Sakkie Agent Roster

Status: Planning document. Do not implement these as autonomous workers until the read-only kiosk has been used daily and reviewed.

## Design Direction

Oom Sakkie is the user-facing farm operating assistant. Specialist agents should feed Oom Sakkie with narrow, auditable work products. They should not become separate brains, separate chat surfaces, or uncontrolled autonomous loops.

The inspiration is a crew model: systems for revenue, code, customers, data, communications, and intelligence. For Amadeus, the roster must be farm-first: pigs, pork sales, crops, telemetry, security, code, media, and business growth.

Hard rules:

- Human approval before any write, customer message, public post, physical control, or Telegram cutover.
- Backend-as-brain remains the architecture. n8n remains I/O and scheduled workflow until an explicit migration phase.
- Every specialist starts read-only.
- Every specialist must declare tools, data sources, risk level, and trace behavior before implementation.
- Oom Sakkie may summarize specialist findings; specialists do not directly speak to users unless explicitly approved.

## First-Class Roles

### Oom Sakkie - The Farm Brain

Role: User-facing voice/kiosk/Telegram assistant.

Job:

- Answer internal farm questions.
- Route to approved read-only tools.
- Surface stale warnings, safety notes, links, trace IDs, and review state.

Current state:

- Local kiosk is implemented as Phase 10.6.
- Backend-as-brain is confirmed.
- Telegram is not cut over.

Risk:

- Read-only today.
- Future writes require exact confirmation payloads and idempotency.

### Sentinel - Security And Safety Advisor

Role: Security, threat, and safety reviewer.

Job:

- Watch for exposed routes, weak auth, secret leakage, unsafe tool expansion, and prompt-injection risk.
- Review Oom Sakkie policy, tool registry, and trace behavior.
- Flag any new write/physical/customer-facing tool before it ships.

First inputs:

- `modules/oom_sakkie/`
- route tests
- Supabase migrations
- `NEXT_STEPS.md`
- `CURRENT_STATE.md`

First output:

- Daily or phase-end security brief with findings ordered by severity.

Risk:

- Read-only advisory.
- No secret access.

### Forge - Code Steward

Role: Developer/code health agent.

Job:

- Inspect failing tests, stale docs, risky diffs, route contracts, and migration drift.
- Suggest next safe build slices.
- Prepare handoff packets for Codex/Claude review.

First inputs:

- Git diff
- test results
- route contracts
- `HANDOFF.md` or review packet

First output:

- Code-review style findings and small patch recommendations.

Risk:

- Read-only initially.
- Future code-writing must be mediated by Codex and human approval.

### Prism - Design Director

Role: Product/interface design reviewer.

Job:

- Improve kiosk readability, layout, information hierarchy, and operational usability.
- Keep the UI practical, not decorative.
- Review voice state, trace visibility, safety panels, and wall-screen legibility.

First inputs:

- `templates/oom-sakkie.html`
- `static/css/main.css`
- screenshots from kiosk browser

First output:

- Design critique and small UI improvement proposals.

Risk:

- Read-only advisory until a specific design slice is approved.

### Ledger - Business And Profit Advisor

Role: Pork business and financial advisor.

Job:

- Analyze sales, livestock, slaughter, meat pipeline, costs, margins, demand, and cash timing.
- Surface profit/loss questions Oom Sakkie should answer.
- Recommend business-module improvements.

First inputs:

- sales dashboard read model
- meat planning read model
- order/sales summaries
- future cost/margin tables

First output:

- Weekly business brief: what is selling, where margin is weak, and what to do next.

Risk:

- Read-only advisory.
- No customer messages, quotes, invoices, or public posts.

### Atlas - Farm Data Analyst

Role: Trends and analytics specialist.

Job:

- Analyze herd trends, weights, growth classes, litter outcomes, weather, power, irrigation, and sales patterns.
- Find anomalies and produce simple questions for Oom Sakkie to answer.
- Help review Oom Sakkie traces and suggest what should be checked next, without marking feedback automatically.

First inputs:

- pig allocation readiness
- weight reports
- telemetry rollups
- sales dashboard

First output:

- Trend brief with links to the relevant farm screens.
- Advisory review queue for owner/Claude inspection.

Risk:

- Read-only.
- No automatic trace feedback marking until a separate approval policy exists.

### Rootline - Crop And Plant Specialist

Role: Crops, plants, irrigation, and growing conditions specialist.

Job:

- Review irrigation status, weather, soil/plant notes, future crop data, and growth tasks.
- Help plan crop care without controlling irrigation hardware.

First inputs:

- weather now/today/forecast
- irrigation status
- future crop logs

First output:

- Crop attention brief: water, heat, wind, rain, and next inspection tasks.

Risk:

- Read-only.
- No irrigation start/stop.

### Herdmaster - Pig Management Specialist

Role: Pig lifecycle and herd attention specialist.

Job:

- Track pig readiness, classifications, litter attention, growth, weaning, deaths, treatments, and breeding review.

First inputs:

- pig allocation readiness
- litter attention
- weight report
- breeding analytics

First output:

- Herd attention brief with exact pig/litter links.

Risk:

- Read-only until approved lifecycle-write tools exist.

### Butcher - Pork Pipeline Specialist

Role: Meat, livestock, slaughter, and abattoir readiness specialist.

Job:

- Watch meat candidates, preorder gaps, fallback abattoir candidates, and slaughter timing.
- Help decide what should be sold as livestock, meat, or slaughter.

First inputs:

- meat planning
- sales dashboard
- pig allocation readiness

First output:

- Pork pipeline brief.

Risk:

- Read-only.
- No customer-facing messages or sale creation.

### Beacon - Media And Market Voice

Role: Media pages, public updates, and marketing draft specialist.

Job:

- Draft farm updates, product page ideas, Facebook/Meta copy, and customer education content.

First inputs:

- approved product catalogue
- approved brand rules
- owner-provided photos/content

First output:

- Draft-only content packets requiring owner approval.

Risk:

- Draft-only.
- No public posting.
- No customer messaging.

### Quartermaster - Operations And Inventory Planner

Role: Supplies, medicine, feed, tasks, and operating stock specialist.

Job:

- Watch practical supply needs: feed, medicine, tags, equipment, and repeat tasks.

First inputs:

- product register
- medical logs
- future inventory/cost tables
- farm attention summaries

First output:

- Operations shopping/task brief.

Risk:

- Read-only/draft-only.
- No purchases.

### Gatekeeper - Orchestrator And Approval Controller

Role: Delegation, routing, and approval policy specialist.

Job:

- Decide which specialist should inspect a question.
- Enforce channel risk caps.
- Queue approval requests.
- Keep one brain: Oom Sakkie remains the final user-facing voice.

First inputs:

- tool registry
- runtime policy
- trace review packet
- future specialist manifests

First output:

- Routing decision and approval requirement.

Risk:

- Internal-only.
- Must not bypass human approval.

## Suggested Build Order

Do not build the full crew at once.

1. Keep Oom Sakkie local kiosk read-only until daily traces are boring.
2. Add a specialist manifest format: name, role, data sources, tools, risk level, owner approval rule.
3. Add `Sentinel` as read-only policy/review summarizer using existing review packet.
4. Add `Forge` as code-review/handoff helper using repo-local files and test results.
5. Add `Ledger`, `Herdmaster`, and `Butcher` as read-only business/farm brief generators.
6. Add `Rootline` after crop/plant data exists.
7. Add `Prism` after kiosk usability has enough screenshots and owner feedback.
8. Add `Beacon` only after draft/approval/public-posting rules are explicit.
9. Add `Gatekeeper` only after at least three specialists exist and their manifests are stable.

## First Implementation Slice Candidate

Phase 10.7A should not spawn live agents. It should create the manifest and review scaffolding:

- `context/agents/oom-sakkie-roster.md` or equivalent runtime-readable doc.
- A typed specialist manifest schema.
- A read-only endpoint or CLI that lists planned specialists.
- No tool execution.
- No LLM delegation.
- No autonomous loops.
- No writes.

Phase 10.7B can add a trace review advisor as a deterministic read-only endpoint:

- Read existing trace summaries and feedback.
- Prioritize unreviewed or previously flagged traces.
- Suggest what the owner or Claude should inspect next.
- Do not mark traces.
- Do not call an LLM.
- Do not run on a schedule.
- Do not feed findings back into Oom Sakkie without human review.

## Names Held For Later

- Sentinel - security and safety.
- Forge - code and tests.
- Prism - design and UI.
- Ledger - business/margin.
- Atlas - analytics/trends.
- Rootline - crops/plants.
- Herdmaster - pigs/lifecycle.
- Butcher - pork pipeline.
- Beacon - media/market voice.
- Quartermaster - operations/inventory.
- Gatekeeper - routing/approval.

These names are working names. Keep them if they help the owner remember the crew; change them if the tone feels wrong after actual use.
