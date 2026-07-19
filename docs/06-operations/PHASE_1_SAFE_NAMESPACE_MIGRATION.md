# Phase 1 Safe Namespace Migration

Status: compatibility implementation validated; live environment rollout pending.

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
