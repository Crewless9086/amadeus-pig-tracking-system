# Vault Cutover Batch 15 Reconciliation

Status: `COMPLETE / NINE GENERATED PROJECTIONS / DRIFT FAILS CLOSED`
Date: 2026-08-18
Baseline: `60516e5f3c97ed745d4b65ab7bd20cfef70f6092`

## Scope And Result

The nine handwritten `static/assets/agents/*/agent.md` notes were reconciled.
Their paths remain stable for UI/runtime compatibility, but their content is now
generated from:

- the exact focused Vault agent doctrine file;
- the matching per-agent `agent.json` asset metadata; and
- the central `static/assets/agents/agent_registry.json` metadata.

Each projection records the canonical role and SHA-256 identities of its inputs,
states `GENERATED / NON_DOCTRINE`, grants no authority, and makes no operational
status claim. Beacon's stale local `Posts` role label was reconciled to the
central `Marketing Lead` asset label.

## Enforcement

`scripts/build_agent_card_projections.py` regenerates the exact nine-card set.
Its `--check` mode detects missing, additional, stale, malformed or mismatched
cards and metadata. The same check is part of the standard Vault alignment audit,
so manual card edits or source drift fail closed in Brain Guard and CI.

## Boundaries

- No agent doctrine or operational authority moved into static assets.
- No visual, voice, provider or agent was activated.
- No runtime, deployment, database, farm, customer or hardware change occurred.
- No path was deleted or archived.
- The remaining physical queue is 181 documents in Batches 16-27.
