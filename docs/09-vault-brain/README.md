# CHARLIE Vault Brain

Status: draft owner-review pack, created from existing repo knowledge on 2026-07-02.

This folder is the separated CHARLIE Vault Brain layer. It is meant to make CHARLIE CORE smarter by giving every agent one clean operating brain instead of scattered context across planning notes, old docs, workflow exports, and code comments.

Important boundary: Supabase remains operational truth for live mission state, approvals, ledgers, events, and runtime records. The Vault Brain is the controlling operating manual for identity, rules, roles, playbooks, source-of-truth guidance, review standards, and owner-approved business direction.

## Read Order

1. `00_BRAIN_GUARD.md`
2. `01_CHARLIE_IDENTITY.md`
3. `02_OWNER_OPERATING_MODEL.md`
4. `03_BUSINESS_MAP.md`
5. `04_AGENT_CHARTERS.md`
6. `05_MISSION_TYPE_PLAYBOOKS.md`
7. `06_EVIDENCE_AND_REVIEW_STANDARD.md`
8. `07_UI_DASHBOARD_STANDARD.md`
9. `08_DATA_AND_SUPABASE_CONTRACTS.md`
10. `09_BUSINESS_RULES_AND_LAW.md`
11. `10_GOLD_STANDARD_EXAMPLES.md`
12. `11_SOURCE_MAP.md`
13. `12_UPDATE_LOG.md`
14. `13_OPEN_QUESTIONS.md`

## How Agents Must Use This Folder

- Start with `00_BRAIN_GUARD.md` to understand update duties.
- Treat `01_CHARLIE_IDENTITY.md` and `02_OWNER_OPERATING_MODEL.md` as the highest-level behavioral contract.
- Use `03_BUSINESS_MAP.md` to understand which department or business lane owns the work.
- Use `04_AGENT_CHARTERS.md` before assigning work to any specialist agent.
- Use `05_MISSION_TYPE_PLAYBOOKS.md` to decide the workflow for the mission type.
- Use `06_EVIDENCE_AND_REVIEW_STANDARD.md` before declaring anything ready for owner review.
- Use `07_UI_DASHBOARD_STANDARD.md` before building dashboards or owner command surfaces.
- Use `08_DATA_AND_SUPABASE_CONTRACTS.md` before touching data paths, migrations, sheets, or Supabase.
- Use `09_BUSINESS_RULES_AND_LAW.md` before customer, marketing, money, privacy, transport, or farm-record decisions.

## Current Source Hierarchy

This folder consolidates but does not delete these active sources:

- `docs/00-start-here/`
- `docs/01-architecture/`
- `docs/02-backend/`
- `docs/03-google-sheets/`
- `docs/04-n8n/`
- `docs/05-ai/`
- `docs/06-operations/`
- `docs/07-decisions/`
- `docs/08-business-modules/`
- `planning/CHARLIE_CORE_EXTENDED_PLAN.md`
- `static/assets/agents/`
- selected tests and modules that encode current behavior

If a conflict exists, use this order until the owner approves a different hierarchy:

1. Direct latest owner instruction.
2. Supabase/runtime records for live state.
3. This Vault Brain, once owner-reviewed.
4. Active `docs/00-start-here/` docs.
5. Module-specific active docs.
6. Planning scratchpads and archived docs.

## Brain Guard Rule

Any mission that changes agent behavior, owner workflow, data truth, business rules, approval boundaries, dashboards, or source-of-truth contracts must update this folder or explicitly record why no Vault Brain update was needed.
