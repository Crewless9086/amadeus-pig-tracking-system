# System Architecture

## Purpose

This document defines the approved top-level system architecture after the CHARLIE CORE decision.

## Top-Level Model

CHARLIE CORE is the top-level owner operating layer.

Oom Sakkie remains the Farm Commander under CHARLIE.

SAM Meat Sales is the urgent money-flow recovery path.

FRED Transport is the planned transport commander and future money path.

Build Team is the controlled engineering workflow for structured build requests, patch plans, tests, docs, and release gates.

## Component Roles

| Component | Role |
| --- | --- |
| Supabase | Live operational source of truth for operational records, approvals, ledgers, handoffs, and owner decisions. |
| Flask backend | Business logic, validation, route contracts, read models, and safe writes behind approved gates. |
| Oom Sakkie | Farm Commander and owner-facing farm command center under CHARLIE. |
| SAM | Meat sales/customer conversation specialist under approved customer-message gates. |
| FRED | Planned transport commander, starting with lead/opportunity capture and read-only board. |
| Gatekeeper | Approval boundary and safety enforcement. |
| Chatwoot / WhatsApp | Customer communication transport, not the brain. |
| n8n | Workflow runner/integration helper, not the brain. |
| Google Sheets | Legacy input/operator view/import source where still used, not final operational truth. |
| Markdown / Brain / Vault | Human-readable guidance only, not live state. |
| Cursor / Codex | Build workshop, not production brain. |

## Source Of Truth

Supabase is the live operational source of truth.

Markdown/docs/Brain/Vault are guidance only.

Google Sheets must not be treated as the final operational truth. Existing modules may still read from Sheets during migration, but new operational collaboration state should be designed for Supabase.

## Data Flow

```text
User / owner / customer event
  -> approved interface or webhook
  -> backend validation and business rules
  -> Supabase operational record
  -> agent result packet / approval request where needed
  -> owner decision
  -> approved action or blocked state
  -> CHARLIE / Oom Sakkie summary
```

## Safety Rules

No component may bypass Gatekeeper or owner approval rails.

No customer messages, public posts, deposits, dispatch commitments, farm record writes, hardware control, quotes, stock allocation, order mutation, or deployments may happen without approved rails.

## Non-Core Tools

Obsidian, Jarvis-style references, ZOEY, OpenCove, hosted assistants, Cursor, and Codex are not runtime core infrastructure.

They may be used as references or build tools only when approved.
