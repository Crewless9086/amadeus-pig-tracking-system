# ADR 0002: CHARLIE CORE Top-Level Owner Orchestrator

Status: Accepted

Date: 2026-06-27

## Context

The system has grown from farm operations, Chatwoot sales flows, Oom Sakkie, Sam Meat, Beacon, Gatekeeper, n8n workflows, Google Sheets integrations, Supabase tables, and build-team planning. Older wording sometimes described n8n, Oom Sakkie, Google Sheets, Obsidian, or a Jarvis-style assistant as the main brain.

That is no longer the approved architecture.

## Decision

CHARLIE CORE is the top-level owner operating layer across all businesses.

The approved hierarchy is:

```text
CHARLIE CORE
  Owner Command Layer
  Oom Sakkie / Farm Business
  SAM Meat Sales
  FRED Transport
  Build Team
  Brain / Vault
  Personal Command
```

Oom Sakkie remains the Farm Commander under CHARLIE. It is not replaced.

SAM Meat Sales is the urgent money-flow recovery path.

FRED is the planned Transport Commander and future money path.

Supabase remains the live operational source of truth. Markdown, docs, Brain, and Vault are human-readable guidance only.

Obsidian is optional. It is not runtime infrastructure.

External Jarvis, ZOEY, OpenCove, hosted assistants, Cursor, and Codex are not the production brain. Cursor/Codex is the build workshop.

## Collaboration Rule

Agents share structured operational results through Supabase records, not Markdown.

The shared ledger must use neutral table names, not `charlie_*` names, because it must serve CHARLIE, Oom Sakkie, SAM, FRED, Build Team, Personal Command, and future businesses.

Initial ledger concepts:

- `business_units`
- `agent_teams`
- `agent_tasks`
- `agent_result_packets`
- `agent_activity_events`
- `agent_handoffs`
- `agent_shared_context_snapshots`
- `approval_requests`
- `owner_decisions`

Existing domain approval rails are not replaced. They are mapped with `source_ref_type` and `source_ref_id`.

## Safety Rule

Gatekeeper and owner approval rails cannot be bypassed.

No customer message, public post, deposit request, dispatch action, farm record write, hardware control, code deployment, quote send, stock allocation, or order mutation may happen without approved rails.

## Consequences

- `/oom-sakkie` remains the warm farm command center.
- `/charlie` is planned as the owner-only top command interface, but no implementation is approved by this ADR.
- SAM recovery can proceed using existing meat-sales rails before the full ledger exists.
- FRED starts with docs/schema and lead/opportunity capture planning before dispatch automation.
- Build Team work is planned and gated, not autonomous.
