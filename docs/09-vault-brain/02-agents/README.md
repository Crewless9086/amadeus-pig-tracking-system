# Agent Directory

Each agent has one dedicated file. Do not add new agents to a shared catch-all file.

To create a new agent:

1. Copy `_AGENT_TEMPLATE.md`.
2. Place it in the correct department folder.
3. Fill in role, watches, inputs, outputs, authority, forbidden actions, owner gates, source data, dashboard placement, and review evidence.
4. Add it to `AGENT_REGISTRY.md` once that registry exists.
5. Update `../01-identity/AGENT_ORGANOGRAM.md` once that organogram exists.
6. Update `../INDEX.md`.
7. Update `../CHANGELOG.md`.

Before any CHARLIE CORE build starts, the mission must state which business environment and which shared departments the agent belongs to or depends on.

Brain Guard must block review-ready status when an agent/workflow changed but the Vault Brain was not updated.
