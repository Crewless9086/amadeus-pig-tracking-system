# CHARLIE CORE Architecture

## Purpose

CHARLIE CORE is the top-level owner operating layer for the whole Amadeus business system. It coordinates business units, agents, decisions, result packets, and release gates without replacing the existing source-of-truth systems.

## Hierarchy

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

## Operating Model

CHARLIE is an owner command layer, not a database and not a hosted assistant.

Oom Sakkie remains the Farm Commander. It coordinates farm specialists and keeps the farm interface practical, warm, and owner-facing.

SAM Meat Sales is the urgent money-flow recovery path. It focuses on customer inquiries, missing facts, approved drafts, deposits, meat availability, and follow-up gates.

FRED Transport is the planned transport money path. It starts with lead/opportunity capture and read-only board planning before dispatch automation.

Build Team coordinates structured build requests, patch plans, tests, docs, and release gates.

Personal Command is a future read-only/draft-only business unit for owner personal admin, reminders, documents, and calendar planning.

## Source Of Truth

Supabase is the live operational source of truth for operational state, approvals, ledgers, handoffs, and owner decisions.

Markdown/docs/Brain/Vault are guidance only. They can describe decisions, plans, prompts, and operating rules. They must not become live collaboration state.

Google Sheets can remain as legacy input, operator view, import source, or temporary synced surface where existing modules still depend on it. It is not the final operational truth.

## Non-Core Tools

Obsidian is optional for reading or organizing Markdown. It is not runtime infrastructure.

External Jarvis, ZOEY, OpenCove, hosted assistants, Cursor, and Codex are not the core system. Cursor/Codex is the build workshop used to propose and apply approved changes.

## Safety

Gatekeeper and owner approvals are hard boundaries.

No customer messages, public posts, deposit requests, dispatch commitments, farm record writes, hardware control, quotes, stock allocations, order mutations, or deployments may happen without approved rails.

## First Approved Build Direction

1. Keep Oom Sakkie stable as Farm Commander.
2. Recover SAM Meat Sales using existing rails first.
3. Design the neutral Agent Collaboration Ledger.
4. Plan FRED lead/opportunity capture.
5. Build CHARLIE read-only orchestration only after owner approval.
