# CHARLIE CORE Agent Runner v2

CHARLIE CORE Agent Runner v2 is the execution model for turning approved CHARLIE missions into owner-reviewable software work. It replaces the old one-shot Codex execution pattern with staged Planner, Architect, Builder, Tester, and Reviewer agent loops.

## Core Rule

CHARLIE does not launch one large mission prompt and wait blindly. CHARLIE owns the workflow, runs bounded agent stages, records artifacts after each stage, and stops visibly when a stage cannot produce evidence.

## Agent Stages

- Planner: scopes the mission, acceptance criteria, test plan, risks, and next handoff.
- Architect: inspects implementation boundaries, source files, route/data contracts, and build approach.
- Builder: applies the scoped implementation and records changed files.
- Tester: runs focused verification and records pass/fail evidence.
- Reviewer: reviews requirements, diff, tests, safety gates, release notes, and owner recommendation.

## Required Evidence

Each stage must produce a final artifact with structured evidence. CHARLIE records the artifact in the Agent Runner ledger and updates Mission Vault workflow status. A stage may not advance silently without an artifact.

## Dashboard Visibility

The local runner heartbeat exposes:

- Agent Runner version
- current agent
- current action
- current final artifact path
- agent ledger path
- elapsed/progress details where available

The CHARLIE dashboard surfaces these fields in the Local Runner panel.

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

## Release

Final approval moves the mission to release handling. The release bridge remains separate from the build agents and may merge a referenced PR only after owner final approval and release evidence are present.
