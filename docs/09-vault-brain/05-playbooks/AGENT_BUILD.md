# Agent Build Playbook

Use when adding or changing an agent, specialist role, voice/visual identity, or workflow stage.

## Required Updates

- Create/update the agent file from `_AGENT_TEMPLATE.md`.
- Add/update `02-agents/AGENT_REGISTRY.md`.
- Update `01-identity/AGENT_ORGANOGRAM.md` if hierarchy changes.
- Update relevant business/workflow/rule docs if authority changes.
- Update static/runtime asset docs if visual/voice identity changes.
- Add source references.

## Brain Guard Block

If code/runtime changes an agent but the Vault does not reflect role, authority, inputs, outputs, or boundaries, Brain Guard must block review-ready.

Before building/changing an agent, update or create its dedicated agent file with role, watches, inputs, outputs, authority, forbidden actions, source data, owner gates, dashboard placement, and evidence.
