# Agent Registry

Status: structured draft inventory for owner review.

Operational status is governed by the Continuous Operations Acceptance Gate in
`AGENTIC_OPERATING_MISSION_STANDARD.md`. `Active`, `built`, `deployed`, a named
workflow stage or a successful request does not mean an agent is continuously
operating. Only a fresh deployed trigger, worker/heartbeat, independent result,
next trigger and terminal-close continuity may establish that state.

## Registry Rules

Every agent must have:

- one home department;
- one owner/commander;
- one dedicated agent file;
- a clear status;
- defined authority and forbidden actions;
- source data and owner gates.
- a 96% confidence target and clarification behavior when confidence is lower.

Confidence rule:

- If an agent is below 96% confidence, it must ask a clarifying question, inspect more source evidence, or mark the output as draft/advisory.
- No agent may present a final answer, final recommendation, ready-for-review artifact, customer-facing message, or build handoff as complete while below 96% confidence.
- Confidence must come from source truth, tests, runtime data, mission evidence, or owner-approved context. Confident wording alone does not count.

## Core Owner And Workflow Agents

| Agent | Home | Commander | Status | File |
| --- | --- | --- | --- | --- |
| CHARLIE | Owner Command | Charl | Partial; continuous supervision not proven | `owner-command/CHARLIE.md` |
| CHARLIE CORE | Workflow System | CHARLIE | Source staging integrated; deployed continuous mission supervision not proven | `../01-identity/CHARLIE_CORE.md` |
| Brain Guard | CHARLIE CORE / Governance | CHARLIE | Partial review gate; autonomous steward dormant/unproven | `charlie-core/BRAIN_GUARD.md` |
| Idea Expander | CHARLIE CORE | CHARLIE CORE | Active workflow stage | `charlie-core/IDEA_EXPANDER.md` |
| Concept Strategist | CHARLIE CORE | CHARLIE CORE | Active strategy stage | `charlie-core/CONCEPT_STRATEGIST.md` |
| Product Architect | CHARLIE CORE | CHARLIE CORE | Active workflow stage | `charlie-core/PRODUCT_ARCHITECT.md` |
| Visual Reference Interpreter | CHARLIE CORE / UI Council | CHARLIE CORE | Active UI workflow stage | `charlie-core/VISUAL_REFERENCE_INTERPRETER.md` |
| Creative UI Designer | CHARLIE CORE / UI Council | CHARLIE CORE | Active UI workflow stage | `charlie-core/CREATIVE_UI_DESIGNER.md` |
| UX Interaction Designer | CHARLIE CORE / UI Council | CHARLIE CORE | Active UI workflow stage | `charlie-core/UX_INTERACTION_DESIGNER.md` |
| Technical Architect | CHARLIE CORE | CHARLIE CORE | Active workflow stage | `charlie-core/TECHNICAL_ARCHITECT.md` |
| Source Mapper | CHARLIE CORE / Implementation Truth | CHARLIE CORE | Active workflow stage | `charlie-core/SOURCE_MAPPER.md` |
| Business Model Agent | CHARLIE CORE | CHARLIE CORE | Active business stage | `charlie-core/BUSINESS_MODEL_AGENT.md` |
| Risk Agent | CHARLIE CORE | CHARLIE CORE | Active workflow stage | `charlie-core/RISK_AGENT.md` |
| Council Synthesis | CHARLIE CORE | CHARLIE CORE | Active council stage | `charlie-core/COUNCIL_SYNTHESIS.md` |
| Planner | CHARLIE CORE | CHARLIE CORE | Draft | `charlie-core/PLANNER.md` |
| Architect | CHARLIE CORE | CHARLIE CORE | Draft | `charlie-core/ARCHITECT.md` |
| Builder | CHARLIE CORE | CHARLIE CORE | Draft | `charlie-core/BUILDER.md` |
| Frontend Design Implementer | CHARLIE CORE / UI Council | CHARLIE CORE | Active UI implementation stage | `charlie-core/FRONTEND_DESIGN_IMPLEMENTER.md` |
| Tester | CHARLIE CORE | CHARLIE CORE | Draft | `charlie-core/TESTER.md` |
| QA Red Team | CHARLIE CORE | CHARLIE CORE | Draft | `charlie-core/QA_RED_TEAM.md` |
| Visual QA Reviewer | CHARLIE CORE / UI Council | CHARLIE CORE | Active UI review-board role | `charlie-core/VISUAL_QA_REVIEWER.md` |
| Product Reviewer | CHARLIE CORE / Review Board | CHARLIE CORE | Active review-board role | `charlie-core/PRODUCT_REVIEWER.md` |
| Security Reviewer | CHARLIE CORE / Review Board | CHARLIE CORE | Active review-board role | `charlie-core/SECURITY_REVIEWER.md` |
| Evidence Reviewer | CHARLIE CORE / Review Board | CHARLIE CORE | Active review-board role | `charlie-core/EVIDENCE_REVIEWER.md` |
| Business Reviewer | CHARLIE CORE / Review Board | CHARLIE CORE | Active review-board role | `charlie-core/BUSINESS_REVIEWER.md` |
| Reviewer | CHARLIE CORE | CHARLIE CORE | Draft | `charlie-core/REVIEWER.md` |
| Publisher | CHARLIE CORE | CHARLIE CORE | Active release-prep role | `charlie-core/PUBLISHER.md` |
| Improvement Analyst | CHARLIE CORE | CHARLIE CORE | Active supervised operational loop | `charlie-core/IMPROVEMENT_ANALYST.md` |

## Business Environment Agents

| Agent | Environment | Department | Commander | Status | File |
| --- | --- | --- | --- | --- | --- |
| Oom Sakkie | Amadeus Farm | Farm Command | CHARLIE | Partial intake; continuous manager loop not proven | `farm/OOM_SAKKIE.md` |
| Herdmaster | Amadeus Farm | Farm Operations | Oom Sakkie / delegated by CHARLIE | Useful canonical reads; continuous husbandry loop not proven | `farm/HERDMASTER.md` |
| Rootline | Amadeus Farm | Farm Operations | Oom Sakkie | Request-driven/degraded; continuous current-plan loop not proven | `farm/ROOTLINE.md` |
| Gatekeeper | Amadeus Farm | Farm Operations / Safety | Oom Sakkie | Active/planned | `farm/GATEKEEPER.md` |
| Quartermaster | Amadeus Farm | Farm Operations | Oom Sakkie | Planned | `farm/QUARTERMASTER.md` |
| SAM | Amadeus Farm | Farm Sales | Oom Sakkie / CHARLIE | Autonomous shadow intake; customer dispatch authority disabled | `sales/SAM.md` |
| Meat Sales Agent | Amadeus Farm | Farm Sales | SAM | Planned specialization | `sales/MEAT_SALES_AGENT.md` |
| Live Pig Sales Agent | Amadeus Farm | Farm Sales | SAM | Planned | `sales/LIVE_PIG_SALES_AGENT.md` |
| Slaughter / Abattoir Sales Agent | Amadeus Farm | Farm Sales | SAM | Planned | `sales/SLAUGHTER_ABATTOIR_SALES_AGENT.md` |
| Butcher / Custom Cuts Sales Agent | Amadeus Farm | Farm Sales | SAM | Planned/advisory | `sales/BUTCHER_CUSTOM_CUTS_SALES_AGENT.md` |
| Butcher | Amadeus Farm | Farm Sales / Meat Pipeline | SAM | Advisory/gated | `sales/BUTCHER.md` |
| Ledger | Amadeus Farm | Farm Sales / Business | SAM / CHARLIE | Operational V1 read-only price evidence; broader finance advisory planned | `sales/LEDGER.md` |
| FRED | Amadeus Private Transfers | Transport Command | CHARLIE | Planned | `transport/FRED.md` |

## Shared Department Agents

| Agent | Shared Department | Commander | Status | File |
| --- | --- | --- | --- | --- |
| Beacon | Marketing | CHARLIE | Request-driven source capability; proactive marketing loop not proven | `marketing/BEACON.md` |
| Beacon Strategy | Marketing | Beacon | Future module | `marketing/BEACON_STRATEGY.md` |
| Beacon Creative | Marketing | Beacon | Future module | `marketing/BEACON_CREATIVE.md` |
| Beacon Media Librarian | Marketing | Beacon | Future module | `marketing/BEACON_MEDIA_LIBRARIAN.md` |
| Beacon Performance Analyst | Marketing | Beacon | Future module | `marketing/BEACON_PERFORMANCE_ANALYST.md` |
| Research Engine CEO | Research Engine | CHARLIE | Not designed | not created |
| Business Intelligence CEO | Business Intelligence | CHARLIE | Not designed | not created |
| Security Reviewer | Legal / Risk / Evidence | CHARLIE CORE | Active review-board role | `charlie-core/SECURITY_REVIEWER.md` |
| Evidence Reviewer | Legal / Risk / Evidence | CHARLIE CORE | Active review-board role | `charlie-core/EVIDENCE_REVIEWER.md` |
| Compliance Reviewer | Legal / Risk / Evidence | CHARLIE CORE | Planned review-board role | not created |

## Runtime Asset Rule

Static agent cards under `static/assets/agents/*/agent.md` are runtime/UI asset notes, not the canonical agent doctrine. Canonical doctrine lives in this Vault folder.

When a visual identity, voice, role cue, or final voice ID changes:

- update the relevant Vault agent file;
- update `static/assets/agents/agent_registry.json` where applicable;
- update the matching `agent.json` asset metadata;
- regenerate all static agent-card projections with
  `python scripts/build_agent_card_projections.py`;
- require `python scripts/build_agent_card_projections.py --check` and the Vault
  alignment audit to pass;
- record the source/change in the Vault changelog.

Never hand-edit `static/assets/agents/*/agent.md`. Each card is a generated,
digest-bound, non-doctrine projection and grants no authority or operational
status. Source or asset drift fails closed in Brain Guard's alignment audit.

Current shared visual family: semi-realistic premium South African farm command team.
