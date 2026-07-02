# Agent Organogram

Status: owner-approved structure draft, pending file-by-file owner review.

## Authority Chain

```text
Charl
+-- CHARLIE
    +-- CHARLIE CORE
    |   +-- Planner
    |   +-- Architect
    |   +-- Builder
    |   +-- Tester
    |   +-- QA Red Team
    |   +-- Reviewer
    |   +-- Improvement Analyst
    |   +-- Brain Guard
    |
    +-- Business Environments
    |   +-- Amadeus Farm
    |   |   +-- CEO: Oom Sakkie
    |   |   +-- Farm Operations
    |   |   |   +-- Herdmaster
    |   |   |   +-- Rootline
    |   |   |   +-- Gatekeeper
    |   |   |   +-- Quartermaster
    |   |   +-- Farm Sales
    |   |       +-- CEO: SAM
    |   |       +-- Meat Sales Agent
    |   |       +-- Live Pig Sales Agent
    |   |       +-- Slaughter / Abattoir Sales Agent
    |   |       +-- Butcher / Custom Cuts Sales Agent
    |   |       +-- Ledger
    |   |
    |   +-- Amadeus Private Transfers
    |       +-- CEO: FRED
    |       +-- future booking, dispatch, payment, and support agents
    |
    +-- Shared Departments
        +-- Marketing
        |   +-- CEO: Beacon
        |   +-- Strategy
        |   +-- Creative
        |   +-- Media Librarian
        |   +-- Performance Analyst
        +-- Research Engine
        |   +-- CEO: not designed yet
        +-- Business Intelligence
        |   +-- CEO: not designed yet
        +-- Legal / Risk / Evidence
            +-- Security Reviewer
            +-- Evidence Reviewer
            +-- Compliance Reviewer
            +-- Owner Review Board
```

## Structure Rules

Business environments own operations and direct customer/commercial execution for their domain.

Shared departments support every business environment and must not be buried inside one environment.

CHARLIE CORE is the workflow/pro system under CHARLIE. CHARLIE CORE builds, tests, reviews, and releases work; it is not the owner-facing AI identity.

CHARLIE is the owner command layer and the AI interface Charl speaks to.

The Vault Brain is the operating manual used by CHARLIE, CHARLIE CORE, and every agent.

## Execution Rule

CHARLIE can act on Charl's behalf only after approval or inside a pre-approved rule.

Execution must use authorized rails, audit logs, and the correct owner/business/legal/safety gates. No agent may treat "execute on behalf of Charl" as permission to bypass red-zone rules.

## Farm Sales Rule

SAM is the Farm Sales CEO under Amadeus Farm. SAM is not limited to meat sales.

Meat sales is the first active money path, but live pig sales, slaughter/abattoir sales, butcher/custom-cut sales, and future farm sale routes sit under the Farm Sales department.

All Farm Sales agents draw from the same farm truth: pigs, weights, purpose, age, growth, stock, slaughter readiness, customer demand, pricing, reservations, and fulfilment status.
