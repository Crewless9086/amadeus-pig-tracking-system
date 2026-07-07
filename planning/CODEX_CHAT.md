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
Formalize the agent authority matrix for CHARLIE CORE and define where Claude is used as a reviewer. Map Beacon, SAM Live Stock, SAM Meat, Butcher, Herdmaster, Oom Sakkie, Gatekeeper, Ledger, Atlas, Sentinel, and Forge to their source modules, allowed actions, blocked actions, approval gates, required tests, and Claude-review triggers.
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
system improvement
```

### Approval Level

```text
LEVEL 3
```

---

## CHARLIE MISSION RECORD

```text
Mission ID: CHARLIE-MISSION-ABDA6E4ED53D1838
Mission title: Agent Authority Matrix And Claude Review Integration
Mission status at pickup: in_progress
Runner mode: code_test_pr
Vault stage: blocked
```

---

## MISSION VAULT

### Problem Statement

```text
Formalize the agent authority matrix for CHARLIE CORE and define where Claude is used as a reviewer. Map Beacon, SAM Live Stock, SAM Meat, Butcher, Herdmaster, Oom Sakkie, Gatekeeper, Ledger, Atlas, Sentinel, and Forge to their source modules, allowed actions, blocked actions, approval gates, required tests, and Claude-review triggers.
```

### Desired Outcome

```text
CHARLIE knows which modules and tests belong to each agent and when Claude review is required before authority increases.
```

### Acceptance Criteria

```text
- Agent-to-module/test/source map exists and matches current repo paths.
- Claude review is required/recommended for authority increases, customer/public automation, payment/meat/slaughter, and agent runtime changes.
- CHARLIE source map can route these future missions to the right implementation areas.
- No new autonomous execution authority is granted by this mission.
```

### Test Plan

```text
- Run focused unit tests for touched modules.
- Run route/frontend contract tests when routes or UI are touched.
- Prove unsafe actions remain blocked by policy/authority flags.
- Prepare owner review packet with changed files, tests, risks, rollback, and next gate.
- Run CHARLIE source map, mission workflow, and Oom Sakkie agent runtime tests.
```

### Forbidden Actions

```text
- Do not send customer messages without an approved customer-send gate.
- Do not post publicly without exact owner approval and channel gate.
- Do not create orders, quotes, invoices, reservations, stock changes, slaughter bookings, butcher bookings, payment confirmations, or farm lifecycle writes unless the mission explicitly builds and tests the gate and still stops at owner review.
- Do not change Render production envs without owner instruction.
- Do not merge or deploy without final owner release approval.
```

### Media / References

```text
- No media references captured.
```

### Agent Workflow

```text
- idea_expander: complete - Expand rough owner idea into a clearer opportunity, user outcome, and non-goals.
- source_mapper: complete - Map the real existing implementation before planning or building: routes, modules, templates, scripts, tests, migrations, active docs, and legacy sources.
- product_architect: complete - Shape product flow, owner value, user behavior, and acceptance boundaries.
- technical_architect: complete - Design implementation structure, file/API/data impacts, integration risk, and test strategy.
- risk_agent: blocked - Create risk register across technical, legal, financial, operational, brand, and data risks.
- council_synthesis: pending - Reconcile upstream agent thinking into one council-approved brief before planning or building.
- planner: pending - Turn owner concept into scoped mission plan.
- architect: pending - Identify files, data sources, risks, and implementation approach.
- builder: pending - Implement scoped changes under approval level.
- tester: pending - Run tests and pressure checks.
- qa_red_team: pending - Challenge the work for regressions, unsafe actions, weak evidence, and owner-risk before review.
- product_reviewer: pending - Check that the result matches owner intent, user value, and acceptance criteria.
- security_reviewer: pending - Review permissions, secrets, data exposure, injection, and dangerous actions.
- evidence_reviewer: pending - Check claims, tests, citations, artifacts, and proof against the Vault.
- reviewer: pending - Review diff, unsafe actions, docs, test evidence, QA findings, and release notes.
- publisher: pending - Prepare deployment/publishing packet after owner approval and verification.
```

### Shared Mission Context Pack

```text
Version: charlie_context_pack_v1

Active truth docs:
- docs/09-vault-brain/INDEX.md
- docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md
- docs/09-vault-brain/00-governance/UPDATE_RULES.md
- docs/09-vault-brain/00-governance/BRAIN_GUARD.md
- docs/09-vault-brain/01-identity/SYSTEM_HIERARCHY.md
- docs/09-vault-brain/01-identity/CHARLIE.md
- docs/09-vault-brain/01-identity/CHARLIE_CORE.md
- docs/09-vault-brain/02-agents/AGENT_REGISTRY.md
- docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md
- docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md
- docs/09-vault-brain/07-standards/TESTING_STANDARD.md
- docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md
- docs/00-start-here/CURRENT_STATE.md
- docs/00-start-here/NEXT_STEPS.md
- docs/00-start-here/WORKFLOW.md
- docs/00-start-here/DEPLOYMENT_SOP.md
- docs/00-start-here/OWNER_INBOX_GUIDE.md

Shared data rules:
- Vault Brain docs under docs/09-vault-brain are the canonical doctrine for agents, workflows, business rules, data rules, standards, and playbooks.
- Every CHARLIE CORE mission must cite the Vault Brain docs used before owner review.
- Brain Guard must block review-ready status when Vault-sensitive work lacks Vault update evidence or an explicit no-update reason.
- Supabase is the canonical durable source where migrations have cut over the app.
- Google Sheets is legacy/reference/export unless a route is explicitly still in fallback mode.
- Mission findings must be recorded in the Mission Vault before handoff to the next role.
- Builder agents must use the Mission Vault, active docs, acceptance criteria, tests, and forbidden actions before editing.

Approval rules:
- LEVEL 1 is read-only investigation.
- LEVEL 2 is docs/planning only.
- LEVEL 3 may build, test, commit, push, and open PR; it may not merge.
- LEVEL 4 may merge after verified diff/tests; red-zone actions still require explicit approval.

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
