# Component Ownership

## Purpose

Defines which layer owns each responsibility so future agents do not guess.

## Ownership Model

- Chatwoot owns customer message transport.
- n8n owns workflow orchestration.
- AI agents own language reasoning and response drafting.
- Flask backend owns business logic, validation, and safe writes.
- Google Sheets owns source data and formula-driven views.

## Rule

n8n must not bypass backend business logic for operational writes.
