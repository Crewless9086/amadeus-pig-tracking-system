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
| Planner | CHARLIE CORE | CHARLIE CORE | Draft | `charlie-core/PLANNER.md` |
| Architect | CHARLIE CORE | CHARLIE CORE | Draft | `charlie-core/ARCHITECT.md` |
| Builder | CHARLIE CORE | CHARLIE CORE | Draft | `charlie-core/BUILDER.md` |
| Tester | CHARLIE CORE | CHARLIE CORE | Draft | `charlie-core/TESTER.md` |
| QA Red Team | CHARLIE CORE | CHARLIE CORE | Draft | `charlie-core/QA_RED_TEAM.md` |
| Reviewer | CHARLIE CORE | CHARLIE CORE | Draft | `charlie-core/REVIEWER.md` |
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
| Security Reviewer | Legal / Risk / Evidence | CHARLIE CORE | Planned review-board role | not created |
| Evidence Reviewer | Legal / Risk / Evidence | CHARLIE CORE | Planned review-board role | not created |
| Compliance Reviewer | Legal / Risk / Evidence | CHARLIE CORE | Planned review-board role | not created |
