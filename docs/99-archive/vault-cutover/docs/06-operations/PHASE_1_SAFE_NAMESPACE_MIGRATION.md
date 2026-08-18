# Phase 1 Safe Namespace Migration

Status: complete; compatibility, local/Render rollout, cold start, hosted canary and rollback evidence passed.

Started: 2026-07-19.

## Purpose

Separate the two identities that the former `CHARLIE_*` namespace mixed together:

- `CHARLIE_*` is the private Executive: conversation, executive model policy, owner Telegram ingress, transcription and voice.
- `CORE_*` is the Agentic AI Workflow System: mission execution, model routing, release verification, runtime supervision and build relay.

Provider and shared integration names such as `OPENAI_*`, `ANTHROPIC_*`, `SUPABASE_*` and `RENDER_*` remain provider-owned. This phase does not rename them.

Dynamic model-routing families (`CHARLIE_AGENT_MODEL_*`, `CHARLIE_AGENT_PROVIDER_*`, `CHARLIE_MODEL_*`, and `CHARLIE_PROVIDER_*`) migrate mechanically to the equivalent `CORE_*` name, including registry cost overrides. Their suffixes are runtime-defined, so the migration derives them from keys actually present instead of maintaining an incomplete static list.

## Compatibility contract

Runtime reads use `modules/charlie/environment.py`.

1. A legacy key by itself continues to work.
2. A canonical key by itself works.
3. Equal canonical and legacy values work.
4. Differing canonical and legacy values fail closed and the exception contains names only, never values.
5. Legacy keys remain present throughout Phase 1. Retirement is a separate owner-reviewed change.

The old `CHARLIE_RUNNER_BASE_BRANCH` maps to `CORE_EXECUTION_BASE_BRANCH`. The name is intentionally execution-specific: it is the clean mission worktree base, not the live runtime control branch.

`CHARLIE_TELEGRAM_TRANSPORT` historically crossed two responsibilities. During compatibility it can feed both `CHARLIE_TELEGRAM_INGRESS_TRANSPORT` and `CORE_RELAY_TRANSPORT`; rollout must add both canonical keys with the same current value before the legacy key can ever be reviewed for retirement.

## Staged rollout

1. Merge and deploy compatibility code while environments remain unchanged.
2. Promote the same accepted commit to the supervised local CORE runtime.
3. Run the dotenv migration in dry-run mode. It reports names only and refuses all writes if any pair conflicts.
4. Back up the local dotenv privately and add equal canonical values while retaining legacy values.
5. Add equal canonical Render values while retaining legacy values; wait for a successful deployment.
6. Prove local cold start, supervisor stability, Executive hosted canary and CORE relay/mission canaries.
7. Re-run key-name-only ownership audits and record revision truth.

The execution base key is handled explicitly during rollout because old local values may name the superseded live-base branch. Both its canonical and legacy values must be normalised to `charlie-core-execution-base` in one controlled operation so mismatch blocking never sees a partial state.

## Rollback

- Code rollback: deploy/promote the preceding accepted commit; legacy keys were retained.
- Local configuration rollback: stop CORE, restore the private pre-migration dotenv backup, then cold start and audit.
- Render configuration rollback: restore the prior key set/value snapshot through the Render operator API, deploy the preceding accepted commit if needed, then run the hosted canary.
- A rollback is complete only when the runtime/deployed revision, process ownership, restart count, environment conflict audit and canaries are recorded.

No secret value may be copied into Git, logs, test output, evidence documents or pull-request text.

## Validation evidence before rollout

- CHARLIE regression suite: 769 tests passed.
- Environment ownership and migration tests: 12 tests passed.
- Full repository regression: 2,493 tests passed, 7 skipped by their existing optional-integration gates.
- Python compilation and `git diff --check`: passed.
- Live `.env` and Render changes: none at this checkpoint.

Final cold-start, hosted-canary, rollback-rehearsal and revision evidence will be appended after the compatibility commit is accepted and deployed.

## Completion evidence

- Compatibility PR #297 merged as `2b7903096e5d932a811e459ea59b00846c9cfc44`; dynamic migration completeness PR #298 merged as `1ee239fef4ba43af314eb8334887687d93c2e0ae`. Both required GitHub CI gates passed on both PRs.
- Render deployed `1ee239fef4ba43af314eb8334887687d93c2e0ae`, then redeployed that exact commit after environment updates and reached `live`.
- Local aliases were added backup-first; the execution base legacy/canonical pair was normalised to `charlie-core-execution-base`; the final audit reported every applicable pair equal and zero conflicts.
- Render added 19 equal canonical aliases through per-key updates, retained every legacy key, and the post-write audit reported zero additions and zero conflicts.
- Authenticated hosted canary passed owner login, `/charlie`, and the Executive SSE stream with `turn_started`, intent/capability/evidence events, `reply_ready`, `turn_completed`, and terminal status `private_charlie_replied`.
- CORE promotion ran 116 focused tests, wrote a manifest for `1ee239f`, and the restart-path audit returned `core_cold_start_ready` with exact root/commit agreement, GitHub access ready and webhook transport ready.
- Scheduled cold start produced one supervisor owning one runner, fresh heartbeats across sustained checks, zero supervisor restarts, no orphans, a non-deadlocked queue and active recovery mission work.
- Rollback rehearsal passed without interrupting production: private pre-change dotenv backups are present and parseable, legacy keys remain sufficient for the compatibility reader, the preceding Render deploy remains available for platform rollback, and unit tests prove migration conflicts refuse writes. No legacy retirement is approved in Phase 1.

## Corrected Render inventory finding

The Phase 0 Render snapshot stopped at the API's default 20-item page. The pagination-complete Phase 1 snapshot records 110 direct-service key names and no values. All are classified; `N8N_API_KEY` and `N8N_BASE_URL` are the only plane mismatches because the contract treats them as local/operator credentials. They were pre-existing, were not used by this namespace migration, and must be reviewed separately before removal. This correction does not weaken the Phase 1 namespace result.
