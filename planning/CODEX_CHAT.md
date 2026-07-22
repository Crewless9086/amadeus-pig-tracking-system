# CODEX CHAT - ACTIVE MISSION TEMPLATE

This mission was picked up from the CHARLIE Supabase mission queue.

Codex must follow:

- `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`
- `docs/00-start-here/CURRENT_STATE.md`
- `docs/00-start-here/NEXT_STEPS.md`
- `docs/00-start-here/WORKFLOW.md`
- `docs/00-start-here/DEPLOYMENT_SOP.md`

---

## OWNER QUICK INPUT

### Concept / Problem / Idea

```text
Complete only this bounded recovery slice:
- Stale or missing weights reduce confidence and cannot trigger an automatic correction.
- Corrections require an explicit owner-approved batch and produce a complete audit event; no silent writes occur.
```

### Desired Outcome

```text
Codex scopes this CHARLIE mission, updates active docs, builds only within the approved level and hard stops, tests thoroughly, and reports a debrief.
```

### Urgency

```text
P1
```

### Mission Type

```text
farm operations improvement
```

### Approval Level

```text
LEVEL 3
```

---

## CHARLIE MISSION RECORD

```text
Mission ID: CHARLIE-HERDMASTER-STAGE-RECONCILIATION-20260721-R7E0E8AA2
Mission title: Herdmaster weight-stage reconciliation and owner-approved corrections - recovery slice 2
Mission status at pickup: in_progress
Runner mode: code_test_pr
Vault stage: blocked_at_security_reviewer
```

---

## MISSION VAULT

### Problem Statement

```text
Complete only this bounded recovery slice:
- Stale or missing weights reduce confidence and cannot trigger an automatic correction.
- Corrections require an explicit owner-approved batch and produce a complete audit event; no silent writes occur.
```

### Desired Outcome

```text
Codex scopes this CHARLIE mission, updates active docs, builds only within the approved level and hard stops, tests thoroughly, and reports a debrief.
```

### Acceptance Criteria

```text
- Not captured yet; Codex must scope this before build.
```

### Test Plan

```text
- Not captured yet; Codex must scope this before build.
```

### Forbidden Actions

```text
- Not captured yet; Codex must scope this before build.
```

### Media / References

```text
- No media references captured.
```

### Agent Workflow

```text
- idea_expander: complete - Expand rough owner intent into opportunity, user outcome, non-goals, assumptions, and first risks.
- source_mapper: complete - Map the real existing implementation before planning or building: routes, modules, templates, scripts, tests, migrations, active docs, and legacy sources.
- product_architect: complete - Define user journeys, acceptance boundaries, product quality bar, and owner-visible outcomes.
- technical_architect: complete - Design implementation structure, file/API/data impacts, integration risk, and test strategy.
- planner: complete - Break approved direction into scoped tasks, gates, tests, and rollback plan.
- architect: complete - Map the planned work to repository structure, APIs, data, and constraints.
- builder: complete - Implement scoped changes under the approved authority level.
- tester: complete - Run unit, integration, regression, and workflow checks with explicit evidence.
- qa_red_team: complete - Challenge regressions, weak evidence, unsafe tool use, prompt risk, and owner-risk.
- product_reviewer: complete - Check that the result matches owner intent, user value, and acceptance criteria.
- security_reviewer: complete - Review permissions, secrets, data exposure, injection, and dangerous actions.
- evidence_reviewer: complete - Check claims, tests, citations, artifacts, and proof against the Vault.
- reviewer: complete - Combine evidence and recommend owner decision.
- publisher: complete - Prepare deployment/publishing packet after owner approval and verification.
```

### Shared Mission Context Pack

```text
Version: charlie_core_v3

Active truth docs:
- Not captured yet; Codex must scope this before build.

Shared data rules:
- Not captured yet; Codex must scope this before build.

Approval rules:
- Not captured yet; Codex must scope this before build.

Parallel work:
disabled_until_phase_6_parallel_controls
```

---

## APPROVAL LEVEL HANDOFF

```text
LEVEL 3: code and tests may be changed within the mission scope. Create a branch, run tests, commit, push, and open a PR. Do not merge.
```

---

## REQUIRED CODEX STARTUP

1. Read `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`.
2. Read `CURRENT_STATE.md`, `NEXT_STEPS.md`, `WORKFLOW.md`, and `DEPLOYMENT_SOP.md`.
3. Classify scope, hard stops, confidence, and tests.
4. Proceed only within the approved mission level.
5. Update docs and debrief when done.
