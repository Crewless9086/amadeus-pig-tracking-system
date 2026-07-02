# CHARLIE Vault Brain

Status: structured draft owner-review pack, created from repo evidence on 2026-07-02.

This folder is the separated CHARLIE Vault Brain layer. It gives CHARLIE CORE and every specialist agent a clean operating manual instead of scattered context across planning notes, legacy docs, workflow exports, and code comments.

Important boundary: Supabase remains operational truth for live mission state, approvals, ledgers, events, and runtime records. The Vault Brain is the controlling operating manual for identity, roles, playbooks, source-of-truth guidance, review standards, and owner-approved business direction.

## Start Here

Read:

1. `INDEX.md`
2. `00-governance/BRAIN_GUARD.md`
3. `01-identity/SYSTEM_HIERARCHY.md`
4. `01-identity/AGENT_ORGANOGRAM.md`
5. `01-identity/CHARLIE.md`
6. `02-agents/AGENT_REGISTRY.md`
7. `02-agents/README.md`
8. the specific agent, business, workflow, or standard file for the mission.

## Folder Map

- `00-governance/` - Brain Guard, update rules, source-of-truth rules, approvals, open questions.
- `01-identity/` - Charl, CHARLIE, CHARLIE CORE, Oom Sakkie, hierarchy.
- `02-agents/` - one dedicated file per agent, grouped by department.
- `03-business/` - one dedicated file per business lane.
- `04-workflows/` - owner, mission, release, sales, campaign, migration workflows.
- `05-playbooks/` - reusable mission-type playbooks.
- `06-data/` - Supabase, Google Sheets legacy, Vault tables, domain data models.
- `07-standards/` - evidence, UI, testing, deployment, customer, security standards.
- `08-business-rules/` - farm, pig, meat, payment, marketing, media/privacy, transport, legal rules.
- `09-examples/` - gold-standard examples.
- `10-source-map/` - source maps and migration notes.

## Conflict Order

If guidance conflicts, use this order until the owner approves a different hierarchy:

1. Latest direct owner instruction.
2. Supabase/runtime records for live state.
3. This Vault Brain, once owner-reviewed.
4. Active `docs/00-start-here/` docs.
5. Module-specific active docs.
6. Planning scratchpads and archived docs.

## Brain Guard Rule

Any mission that changes agent behavior, owner workflow, data truth, business rules, approval boundaries, dashboards, or source-of-truth contracts must update this folder or explicitly record why no Vault Brain update was needed.
