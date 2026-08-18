# ADR 0001: Documentation Source Of Truth

## Status

Accepted

## Context

The project spans several layers: Chatwoot, n8n workflows, AI agents, a Flask backend, and Google Sheets. Existing documentation was useful but spread across `project-memory/`, `planning/`, and large workflow export files. This made it difficult for agents and humans to know which file was authoritative.

## Decision

Use `docs/` as the canonical documentation source of truth.

Existing `project-memory/` files remain legacy source material until reviewed and migrated. Existing `planning/` files remain scratch and intake notes only.

## Consequences

- New approved documentation should be added under `docs/`.
- Changes to backend, n8n, Google Sheets, AI behavior, or operations must update the relevant docs area.
- Legacy docs should only be marked superseded after their content has been migrated and verified.
- Backend refactoring waits until the documentation structure is in place.
