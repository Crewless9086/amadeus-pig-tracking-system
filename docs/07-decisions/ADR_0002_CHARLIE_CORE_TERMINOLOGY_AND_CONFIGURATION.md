# ADR 0002: CHARLIE, CORE and configuration ownership

Status: proposed for owner review in Phase 0.

Date: 2026-07-19.

## Context

The historical product name `CHARLIE CORE` is used across code, prompts, routes, database records, tests, documentation, environment variables and operational tooling. CHARLIE has since become Charl's private digital executive, while CORE is the subordinate Agentic AI Workflow System. Leaving all configuration under `CHARLIE_*` makes identity, deployment scope and authority difficult to reason about.

## Decision

- **Charl** is the human owner and final authority.
- **CHARLIE** is Charl's private digital executive, cross-business coordinator and owner interface.
- **CORE** is the Agentic AI Workflow System for governed software missions, capability repair, testing and delivery.
- Specialist agents retain their own names and configuration prefixes.
- New Executive configuration uses `CHARLIE_*`.
- New workflow/runtime configuration uses `CORE_*`.
- Historical `CHARLIE CORE` code, route, database and document identifiers may remain until migrated through reviewed compatibility changes. They do not redefine the identity hierarchy.

## Configuration planes

- Local owner configuration supplies local CORE, operator tools and local development.
- Render backend configuration supplies the hosted application and CHARLIE Executive ingress.
- CI supplies test-only credentials and flags.
- GitHub stores source and CI metadata, never application secrets.
- Supabase stores durable operational state, not deployment secrets.

## Migration rule

No existing key is renamed in place. Code first accepts a canonical key and one declared legacy alias. If both are set and normalized values differ, startup fails closed. A staged rollout adds canonical keys, verifies parity, observes both local and hosted behavior, then retires aliases in a later owner-reviewed change.

## Consequences

- Operators can tell which identity and deployment owns a setting.
- Local CORE configuration is not copied blindly into Render.
- Render Executive configuration is not assumed to configure local CORE.
- Compatibility code and documentation will temporarily carry both canonical and legacy names.
- Phase 1 must include conflict tests, secrets-safe diagnostics and rollback proof.

