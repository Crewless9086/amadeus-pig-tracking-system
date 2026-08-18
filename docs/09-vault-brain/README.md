# CHARLIE Vault Brain

Status: authoritative doctrine root. Batch 2 authority routing approved 2026-08-18.

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

## Single-Authority Rule

Only focused doctrine under `docs/09-vault-brain/` is normative agent doctrine.
The two controlling cross-system exceptions are explicitly registered here:

- `docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md` - canonical runtime architecture;
- `docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md` - mandatory evidence envelope.

`docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md` is current mission-state
evidence, not reusable doctrine. Code, tests, schemas, provider records and
technical runbooks are implementation/runtime evidence. They may prove how the
system works, but may not redefine an agent role, public policy, business rule,
owner approval boundary or source-of-truth contract.

Planning files, historical evidence, handovers, static agent cards and any
unclassified document are never authority. A terminal must not resolve a
conflict by choosing whichever document is newer or more detailed.

## Conflict Order

If guidance conflicts, use this order until the owner approves a different hierarchy:

1. Latest direct owner instruction.
2. `00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md` for operating method.
3. Supabase/provider/runtime records for live state.
4. Current Control Tower Mission Register and canonical Runtime Programme.
5. Current focused Vault doctrine under the lifecycle standard.
6. Current technical/runtime evidence, used only inside the doctrine boundary.
7. Planning, handovers, static projections, superseded evidence and archives;
   never authority.

## Mandatory Mission Packs

Every mission loads the common governance pack plus exactly the relevant agent,
workflow, business-rule and data/standard overlays recorded in
`10-source-map/ACTIVE_DOCS_SOURCE_MAP.md`. UI work always adds the Amadeus Farm
Facelift Standard. Public/Meta work always adds the relevant channel-policy
workflow. Missing, contradictory or unclassified pack material fails closed and
becomes one Brain Guard finding; it is not replaced with a legacy document.

## Brain Guard Rule

Any mission that changes agent behavior, owner workflow, data truth, business rules, approval boundaries, dashboards, or source-of-truth contracts must update this folder or explicitly record why no Vault Brain update was needed.
