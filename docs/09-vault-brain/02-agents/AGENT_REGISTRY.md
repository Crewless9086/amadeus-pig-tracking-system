# Agent Registry

Status: structured draft inventory for owner review.

## Registry Rules

Every agent must have:

- one home department;
- one owner/commander;
- one dedicated agent file;
- a clear status;
- defined authority and forbidden actions;
- source data and owner gates.

## Core Owner And Workflow Agents

| Agent | Home | Commander | Status | File |
| --- | --- | --- | --- | --- |
| CHARLIE | Owner Command | Charl | Active/maturing | `owner-command/CHARLIE.md` |
| CHARLIE CORE | Workflow System | CHARLIE | Active/maturing | `../01-identity/CHARLIE_CORE.md` |
| Brain Guard | CHARLIE CORE / Governance | CHARLIE | Draft/required | `charlie-core/BRAIN_GUARD.md` |
| Idea Expander | CHARLIE CORE | CHARLIE CORE | Active workflow stage | `charlie-core/IDEA_EXPANDER.md` |
| Concept Strategist | CHARLIE CORE | CHARLIE CORE | Active strategy stage | `charlie-core/CONCEPT_STRATEGIST.md` |
| Product Architect | CHARLIE CORE | CHARLIE CORE | Active workflow stage | `charlie-core/PRODUCT_ARCHITECT.md` |
| Visual Reference Interpreter | CHARLIE CORE / UI Council | CHARLIE CORE | Active UI workflow stage | `charlie-core/VISUAL_REFERENCE_INTERPRETER.md` |
| Creative UI Designer | CHARLIE CORE / UI Council | CHARLIE CORE | Active UI workflow stage | `charlie-core/CREATIVE_UI_DESIGNER.md` |
| UX Interaction Designer | CHARLIE CORE / UI Council | CHARLIE CORE | Active UI workflow stage | `charlie-core/UX_INTERACTION_DESIGNER.md` |
| Technical Architect | CHARLIE CORE | CHARLIE CORE | Active workflow stage | `charlie-core/TECHNICAL_ARCHITECT.md` |
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
| Improvement Analyst | CHARLIE CORE | CHARLIE CORE | Active foundation | `charlie-core/IMPROVEMENT_ANALYST.md` |

## Business Environment Agents

| Agent | Environment | Department | Commander | Status | File |
| --- | --- | --- | --- | --- | --- |
| Oom Sakkie | Amadeus Farm | Farm Command | CHARLIE | Active direction | `farm/OOM_SAKKIE.md` |
| Herdmaster | Amadeus Farm | Farm Operations | Oom Sakkie | Active/planned | `farm/HERDMASTER.md` |
| Rootline | Amadeus Farm | Farm Operations | Oom Sakkie | Read-only/gated | `farm/ROOTLINE.md` |
| Gatekeeper | Amadeus Farm | Farm Operations / Safety | Oom Sakkie | Active/planned | `farm/GATEKEEPER.md` |
| Quartermaster | Amadeus Farm | Farm Operations | Oom Sakkie | Planned | `farm/QUARTERMASTER.md` |
| SAM | Amadeus Farm | Farm Sales | Oom Sakkie / CHARLIE | Active money path | `sales/SAM.md` |
| Meat Sales Agent | Amadeus Farm | Farm Sales | SAM | Planned specialization | `sales/MEAT_SALES_AGENT.md` |
| Live Pig Sales Agent | Amadeus Farm | Farm Sales | SAM | Planned | `sales/LIVE_PIG_SALES_AGENT.md` |
| Slaughter / Abattoir Sales Agent | Amadeus Farm | Farm Sales | SAM | Planned | `sales/SLAUGHTER_ABATTOIR_SALES_AGENT.md` |
| Butcher / Custom Cuts Sales Agent | Amadeus Farm | Farm Sales | SAM | Planned/advisory | `sales/BUTCHER_CUSTOM_CUTS_SALES_AGENT.md` |
| Butcher | Amadeus Farm | Farm Sales / Meat Pipeline | SAM | Advisory/gated | `sales/BUTCHER.md` |
| Ledger | Amadeus Farm | Farm Sales / Business | SAM | Advisory/planned | `sales/LEDGER.md` |
| FRED | Amadeus Private Transfers | Transport Command | CHARLIE | Planned | `transport/FRED.md` |

## Shared Department Agents

| Agent | Shared Department | Commander | Status | File |
| --- | --- | --- | --- | --- |
| Beacon | Marketing | CHARLIE | Partially active/controlled | `marketing/BEACON.md` |
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
- update the static asset note;
- update `static/assets/agents/agent_registry.json` where applicable;
- record the source/change in the Vault changelog.

Current shared visual family: semi-realistic premium South African farm command team.
