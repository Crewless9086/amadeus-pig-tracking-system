# Agent Collaboration Ledger

## Purpose

The Agent Collaboration Ledger is the shared Supabase-backed operational ledger for agent work across CHARLIE, Oom Sakkie, SAM, FRED, Build Team, Personal Command, and future businesses.

It is not Markdown. It is not Obsidian. It is not a `charlie_*` namespace.

## Naming Decision

Use neutral table names:

- `business_units`
- `agent_teams`
- `agent_tasks`
- `agent_result_packets`
- `agent_activity_events`
- `agent_handoffs`
- `agent_shared_context_snapshots`
- `approval_requests`
- `owner_decisions`

## Minimal Relationships

```text
business_units 1--many agent_teams
agent_teams 1--many agent_tasks
agent_tasks 1--many agent_result_packets
agent_tasks 1--many agent_activity_events
agent_tasks 1--many agent_handoffs
agent_tasks 1--many agent_shared_context_snapshots
approval_requests 1--many owner_decisions
agent_tasks many--one approval_requests
agent_result_packets many--one approval_requests
```

## Required Field Concepts

The schema design review must explicitly include or reject:

- `trace_id`
- `run_id`
- `correlation_id`
- `idempotency_key`
- `confidence`
- `visibility_scope`
- `expires_at`
- `resolved_at`
- `completed_at`
- `updated_at`
- `created_by`
- `source_refs_json`
- `schema_version`
- `parent_task_id`
- `blocked_reason`
- `approval_request_id`

## Approval Mapping

Existing domain approval rails stay in place.

Generic `approval_requests` and `owner_decisions` provide a shared index and command queue. Existing approvals map into the ledger with:

- `source_ref_type`
- `source_ref_id`
- `business_unit_id`
- `agent_team_id`
- `approval_state`

## Safety

No agent may treat a result packet as permission to act. Result packets are evidence. Mutating actions require approved rails and an owner decision where required.

## Migration Rule

No migration is approved by this document. SQL must be reviewed in a separate phase after the design is accepted.
