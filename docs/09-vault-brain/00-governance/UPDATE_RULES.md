# Vault Brain Update Rules

## Rule

Any mission that changes durable operating knowledge must update the smallest correct Vault Brain file.

## Procedure

1. Identify changed behavior or decision.
2. Find the affected folder and file.
3. Update that file only.
4. Add a dated entry to `../CHANGELOG.md`.
5. Update `../10-source-map/ACTIVE_DOCS_SOURCE_MAP.md` if a new source becomes authoritative.
6. Add open issues to `OPEN_QUESTIONS.md`.
7. State in the mission debrief which Vault Brain docs changed or why none changed.
8. Run `python scripts/audit_vault_alignment.py` and retain the exact result.
9. Re-run the audit against the exact release head and after deployment when
   runtime/current-state truth changed.

`no_vault_update_required` is an assertion to verify, not an automatic pass. It
must identify the changed behavior and why every affected current-state, agent,
workflow, rule, source-map and lifecycle document remains correct.

## Agent And Structure Rules

Every new agent must use `../02-agents/_AGENT_TEMPLATE.md`.

Every new agent must be added to `../02-agents/AGENT_REGISTRY.md` once that registry exists.

Every structure change must update `../01-identity/AGENT_ORGANOGRAM.md` once that organogram exists.

Every CHARLIE CORE mission must identify the business environment and shared departments involved before build work starts.

Brain Guard must block review-ready status if an agent, workflow, business rule, data contract, approval gate, dashboard, or source-of-truth boundary changed but the correct Vault Brain files were not updated.

Brain Guard must also block when current documentation describes an agent as
active, operational or complete without the Continuous Operations Acceptance
Gate evidence, or when a historical document remains discoverable as current
authority without a supersession banner.

## Do Not

- Dump new knowledge into one giant file.
- Create duplicate agent files.
- Hide owner decisions in planning scratchpads only.
- Delete old docs before source migration is reviewed.
