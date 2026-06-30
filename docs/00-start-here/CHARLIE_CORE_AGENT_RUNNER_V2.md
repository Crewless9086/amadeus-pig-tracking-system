# CHARLIE CORE Agent Runner v2

CHARLIE CORE Agent Runner v2 is the execution model for turning approved CHARLIE missions into owner-reviewable software work. It replaces the old one-shot Codex execution pattern with staged specialist, Planner, Architect, Builder, Tester, QA/Red-Team, and Reviewer agent loops.

## Core Rule

CHARLIE does not launch one large mission prompt and wait blindly. CHARLIE owns the workflow, runs bounded agent stages, records artifacts after each stage, and stops visibly when a stage cannot produce evidence.

## Agent Stages

- Idea Expander: optional specialist stage for agent/system/workflow/business/content missions; clarifies opportunity, owner value, constraints, and non-goals.
- Product Architect: optional specialist stage for agent/system/workflow/business/content missions; defines user flow, product boundaries, and acceptance shape.
- Planner: scopes the mission, acceptance criteria, test plan, risks, and next handoff.
- Architect: inspects implementation boundaries, source files, route/data contracts, and build approach.
- Builder: applies the scoped implementation and records changed files.
- Tester: runs focused verification and records pass/fail evidence.
- QA/Red-Team: challenges regressions, weak evidence, unsafe actions, missing tests, security/privacy risk, and owner-facing failure modes.
- Reviewer: reviews requirements, diff, tests, safety gates, release notes, and owner recommendation.

## Required Evidence

Each stage must produce a final artifact with structured evidence. CHARLIE records the artifact in the Agent Runner ledger, normalizes it into a `charlie_handoff_report_v1`, and updates Mission Vault workflow status. A stage may not advance silently without an artifact.

Every agent artifact must include:

- summary
- files inspected
- commands run
- stdout/stderr tail where relevant
- next action
- stage-specific evidence

Idea Expander must include opportunity, owner value, and non-goals. Product Architect must include user flow, acceptance boundaries, and risk notes. Planner must include acceptance criteria and test plan. Architect must include files to inspect, risks, and implementation plan. Builder must include changed files and build notes. Tester must include tests run and pass/fail status. QA/Red-Team must include QA findings, red-team status, and risk rating. Reviewer must include release notes, QA evidence, and recommended owner decision.

## Quality Gates

CHARLIE checks each artifact before advancing. The Tester gate requires `test_status = pass` and no reported errors/bugs. The QA/Red-Team gate requires `red_team_status = pass`, no reported errors/bugs, and no high/critical risk rating. The Reviewer gate requires `recommended_owner_decision = approve_final_release`, QA evidence, and no reported errors/bugs. Missing command/file evidence blocks the mission instead of creating a weak review packet.

Validation missions must include PR evidence before owner review.

## Backflow

Tester failure sends the workflow back to Builder. Reviewer rejection or findings send the workflow back to Builder unless the Reviewer artifact names a different valid `send_back_stage`. Backflow is bounded by a retry limit so the mission cannot loop forever. Backflow events are recorded in the Agent Runner ledger and the owner review packet.

## Dashboard Visibility

The local runner heartbeat exposes:

- Agent Runner version
- current agent
- current action
- current final artifact path
- agent ledger path
- latest stage summary
- recent commands/files/output tails
- elapsed/progress details where available

The CHARLIE dashboard surfaces these fields in the Local Runner panel.

The dashboard also exposes a CHARLIE CORE Command Center with queue counts, review/blocked state, release state, deployed/merged state, live verification configuration, Vault version, and current runner boundary.

## Mission Vault v1

The current runtime remains backward compatible with `charlie_missions.metadata_json`. The structured Vault v1 schema is available through `supabase/migrations/202606300002_create_charlie_vault_v1_tables.sql` and defines:

- `charlie_vault_projects`
- `charlie_vault_artifacts`
- `charlie_agent_runs`
- `charlie_handoff_reports`
- `charlie_quality_gates`
- `charlie_owner_decisions`
- `charlie_deployments`
- `charlie_audit_log`

## Blocked Behavior

If an agent does not produce a valid final artifact, CHARLIE records a blocked review packet with:

- blocked agent
- blocked reason
- changed files
- execution ledger path
- stdout/stderr excerpts when available

This prevents silent stuck missions.

## Owner Review

When all stages complete, CHARLIE creates a review packet and moves the mission to `pr_ready`. Owner review remains mandatory before release. Send-back comments rerun from the chosen workflow stage and downstream stages.

When owner review sends a mission back to a stage, upstream artifacts are preserved and only the selected stage plus downstream stages rerun. This keeps good planning/architecture evidence intact while still forcing new Builder/Tester/Reviewer evidence.

## Release

Final approval moves the mission to release handling. The release bridge remains separate from the build agents and may merge a referenced PR only after owner final approval and release evidence are present. After merge, the release bridge watches the configured live URL for a bounded verification window and marks the mission `deployed` only if live verification succeeds. Otherwise it records the merge and deploy-watch evidence for follow-up.

Live verification URL priority:

1. `CHARLIE_RELEASE_VERIFY_URL`
2. `AMADEUS_BACKEND_URL` + `/charlie`
3. `RENDER_EXTERNAL_URL` + `/charlie`
4. `RENDER_EXTERNAL_HOSTNAME` + `/charlie`

If no URL is configured, the mission may become `merged`, but it cannot become `deployed`.

## Extended Architecture Alignment

CHARLIE Agent Runner v2 is the working spine for the larger CHARLIE CORE operating-system plan. The next architecture should extend this runner instead of replacing it immediately.

Recommended order:

1. Configure live release verification so merged missions can become deployed.
2. Normalize the Mission Vault into structured Postgres tables for projects, agent runs, artifacts, decisions, risks, tests, reviews, approvals, deployments, cost logs, and audit logs.
3. Standardize every stage artifact into one reusable handoff report contract.
4. Add optional specialist stages by mission type: Idea Expander, Product Architect, Technical Architect, Security Reviewer, Publisher, and Monitoring.
5. Add model registry and tool permission layers before broad MCP/model routing.
6. Evaluate Temporal, OpenAI Agents SDK, and LangGraph only after repeated long-running missions show the local runner needs durable distributed orchestration.

Current best fit:

- Keep the Python runner, Supabase mission records, GitHub PRs, Telegram notifications, and Flask dashboard as CHARLIE CORE v2.
- Use Postgres/Supabase as the canonical vault before adding external vector/file-search layers.
- Use GitHub as code truth and owner-reviewed PRs as release gates.
- Treat provider/model names as configurable registry entries, not hardcoded architecture.
