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
Repair the exact Security Reviewer defect found on canonical PR #373. The correction-batch create, approve, and execute routes must fail closed for non-loopback requests unless a genuine authenticated owner-admin session exists, including when OWNER_ACCESS_ENABLED=0 or local-development settings are active. Restrict any local-development bypass explicitly to loopback. Update canonical PR #373 only; do not open another PR. Preserve the passing transactional, freshness, idempotency, audit, UI, planning, Builder, Tester, and QA evidence from the parent mission. Do not apply the migration and do not change any pig or farm record.
```

### Desired Outcome

```text
Codex scopes this CHARLIE mission, updates active docs, builds only within the approved level and hard stops, tests thoroughly, and reports a debrief.
```

### Urgency

```text
P0
```

### Mission Type

```text
security correction
```

### Approval Level

```text
LEVEL 3
```

---

## CHARLIE MISSION RECORD

```text
Mission ID: CHARLIE-HERDMASTER-STAGE-AUTH-GUARD-20260722
Mission title: Herdmaster correction batches: fail-closed owner-session guard
Mission status at pickup: in_progress
Runner mode: code_test_pr
Vault stage: blocked_at_architect
```

---

## MISSION VAULT

### Problem Statement

```text
Repair the exact Security Reviewer defect found on canonical PR #373. The correction-batch create, approve, and execute routes must fail closed for non-loopback requests unless a genuine authenticated owner-admin session exists, including when OWNER_ACCESS_ENABLED=0 or local-development settings are active. Restrict any local-development bypass explicitly to loopback. Update canonical PR #373 only; do not open another PR. Preserve the passing transactional, freshness, idempotency, audit, UI, planning, Builder, Tester, and QA evidence from the parent mission. Do not apply the migration and do not change any pig or farm record.
```

### Desired Outcome

```text
Codex scopes this CHARLIE mission, updates active docs, builds only within the approved level and hard stops, tests thoroughly, and reports a debrief.
```

### Acceptance Criteria

```text
- Non-loopback correction-batch create, approve, and execute requests cannot reach their services without an authenticated owner-admin session in every supported OWNER_ACCESS_ENABLED configuration.
- Any local-development bypass is explicit, loopback-only, and cannot be activated by request-controlled forwarding headers.
- Deterministic negative tests cover OWNER_ACCESS_ENABLED=0 and local-development settings across create, approve, and execute, asserting denial and zero service calls.
- Existing authenticated owner-admin, freshness, idempotency, atomic audit, draft, stale, missing-weight, tamper, and duplicate-execution tests remain green.
- Canonical PR #373 is updated in place and tested at its new exact revision; no duplicate PR is created.
- Migration application, live canary, and every pig-record mutation remain separately owner-gated and are not performed by this mission.
```

### Test Plan

```text
- Run focused owner-access and correction-batch route tests, including non-loopback negative cases with services mocked.
- Run the complete pig allocation readiness and owner access suites.
- Run current GitHub checks on canonical PR #373 and bind evidence to its exact new head.
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
- visual_reference_interpreter: complete - Convert owner screenshots, sketches, and reference media into concrete layout, hierarchy, interaction, and visual-match requirements.
- creative_ui_designer: complete - Design a distinctive, owner-aligned UI concept with information architecture, visual hierarchy, layout rhythm, and interaction intent before implementation.
- ux_interaction_designer: complete - Turn the UI concept into ergonomic workflows, visible actions, responsive behavior, empty/error states, and owner decision paths.
- product_architect: complete - Shape product flow, owner value, user behavior, and acceptance boundaries.
- technical_architect: complete - Design implementation structure, file/API/data impacts, integration risk, and test strategy.
- council_synthesis: complete - Reconcile upstream agent thinking into one council-approved brief before planning or building.
- planner: complete - Turn owner concept into scoped mission plan.
- architect: complete - Identify files, data sources, risks, and implementation approach.
- frontend_design_implementer: complete - Translate approved UI concept and interaction spec into frontend code while preserving the visual reference contract.
- builder: complete - Implement scoped changes under approval level.
- tester: complete - Run tests and pressure checks.
- qa_red_team: complete - Challenge the work for regressions, unsafe actions, weak evidence, and owner-risk before review.
- visual_qa_reviewer: complete - Compare the finished UI against owner reference media, design requirements, desktop/mobile screenshots, and visible owner actions.
- product_reviewer: complete - Check that the result matches owner intent, user value, and acceptance criteria.
- security_reviewer: complete - Review permissions, secrets, data exposure, injection, and dangerous actions.
- evidence_reviewer: complete - Check claims, tests, citations, artifacts, and proof against the Vault.
- reviewer: complete - Review diff, unsafe actions, docs, test evidence, QA findings, and release notes.
- publisher: complete - Prepare deployment/publishing packet after owner approval and verification.
```

### Shared Mission Context Pack

```text
Version: charlie_context_pack_v1

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
