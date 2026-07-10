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
Update SAM Live Stock conversation planning for requested delivery only. If customer asks delivery/transport/drop-off/far-away question, capture destination town/address/location and one-way km requirement, calculate or request the missing distance/destination, then draft an owner-reviewed reply with collection-first wording and optional delivery estimate. Do not advertise delivery in normal stock/price replies. Add Telegram card fields: delivery requested, destination, one-way km, delivery fee estimate, total with livestock + delivery, and owner override warning. Feed owner corrections into learning. Tests: general price reply should not mention delivery; delivery question should produce delivery-aware draft; unknown destination asks one useful question; known km calculates R20/km; safety scanner blocks delivery promises but allows estimates.
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
sam_live_stock_agentic_workflow
```

### Approval Level

```text
LEVEL 3
```

---

## CHARLIE MISSION RECORD

```text
Mission ID: CHARLIE-MISSION-C49AB9AE9B8646DD
Mission title: SAM Live Stock Delivery-Aware Conversation Planner
Mission status at pickup: in_progress
Runner mode: code_test_pr
Vault stage: returned_to_builder
```

---

## MISSION VAULT

### Problem Statement

```text
Update SAM Live Stock conversation planning for requested delivery only. If customer asks delivery/transport/drop-off/far-away question, capture destination town/address/location and one-way km requirement, calculate or request the missing distance/destination, then draft an owner-reviewed reply with collection-first wording and optional delivery estimate. Do not advertise delivery in normal stock/price replies. Add Telegram card fields: delivery requested, destination, one-way km, delivery fee estimate, total with livestock + delivery, and owner override warning. Feed owner corrections into learning. Tests: general price reply should not mention delivery; delivery question should produce delivery-aware draft; unknown destination asks one useful question; known km calculates R20/km; safety scanner blocks delivery promises but allows estimates.
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
- No production data writes unless explicitly approved.
- No migrations unless explicitly approved.
- No customer sends, public posts, payments, reservations, or lifecycle writes unless explicitly approved.
- No .env, secrets, screenshots, external_sources, static/assets, or planning/Prompts.md unless explicitly approved.
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
- risk_agent: complete - Create risk register across technical, legal, financial, operational, brand, and data risks.
- council_synthesis: complete - Reconcile upstream agent thinking into one council-approved brief before planning or building.
- planner: complete - Turn owner concept into scoped mission plan.
- architect: complete - Identify files, data sources, risks, and implementation approach.
- builder: active - Implement scoped changes under approval level.
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
