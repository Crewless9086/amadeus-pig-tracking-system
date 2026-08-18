# Oom Sakkie Sentinel Single-Shot Runbook

Purpose: run the first supervised Sentinel advisory LLM smoke without widening Oom Sakkie's authority.

This is not a daily automation. Use it only after the 10.9BP-BS Claude review passes, GitHub Actions are green, and the owner explicitly approves the smoke window.

## Non-Negotiables

- Keep `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED` off before and after the smoke.
- Run locally or on the trusted kiosk host only.
- Do not expose the kiosk through a same-host reverse proxy during the smoke.
- Do not add tool execution, farm-data writes, public/customer output, Telegram, deploy, physical controls, or financial actions.
- One approval means one attempt. If the outbound LLM call fails after the consumed event is recorded, create a fresh approval for any retry.

## Prerequisites

1. Latest `main` is pulled locally.
2. `Oom Sakkie Audit Rails` is green for the current commit.
3. `Oom Sakkie Browser Behavior` is green for the current commit.
4. Claude has reviewed `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md` and passed the 10.9BP-BS batch.
5. Supabase migrations are applied through:
   - `202606090002_create_oom_sakkie_dispatch_execution_approvals.sql`
   - `202606090003_allow_single_shot_sentinel_dry_run_results.sql`
6. OpenAI-compatible env is configured:
   - `OPENAI_API_KEY`
   - `OOM_SAKKIE_LLM_ROUTER_MODEL`
   - optional `OOM_SAKKIE_LLM_ROUTER_URL`
7. `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED` is still off.

## Prepare One Approved Request

Create or select a Sentinel dry-run request and dispatch request that are intentionally low-risk.

Required chain:

1. Sentinel dry-run request exists.
2. Dispatch request exists for `specialist_slug = sentinel`.
3. Dispatch request latest decision is `approved_for_design_review`.
4. Dispatch execution approval exists with:
   - `approval_type = approved_for_single_dry_run_execution`
   - `one_shot_scope.dry_run_request_id` set to the Sentinel dry-run request ID.
5. The approval has no `consumed_by_single_dry_run_result` event.

## Enable For The Short Smoke Window

Set:

```text
OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED=1
```

Restart the local Flask process if needed so the process sees the env change.

Confirm policy before running:

- `specialist_dry_run.enabled = true`
- `specialist_dry_run.configured = true`
- `specialist_dry_run.can_write = false`
- `specialist_dry_run.runs_specialist_tools = false`
- `specialist_dry_run.dispatches_further = false`

## Run Exactly Once

Call the local review-gated endpoint:

```text
POST /api/oom-sakkie/dispatch-execution-approvals/<approval_id>/run-sentinel-dry-run
```

Expected success shape:

- `success = true`
- `mode = single_shot_sentinel_advisory_result`
- `consumed = true`
- `runs_specialist_llm = true`
- `runs_specialist_tools = false`
- `writes = false`
- `applies_runtime_change = false`
- `dispatches_further = false`
- `dry_run_result_id` is present.

Expected failure after outbound error:

- status `502`
- `consumed = true`
- no automatic retry.

## Verify Append-Only Result

After a successful run:

1. Open the dry-run result review packet for the returned `dry_run_result_id`.
2. Confirm the result is advisory text only.
3. Confirm findings do not claim actions were taken.
4. Confirm latest result mode/status:
   - `mode = single_shot_sentinel_advisory_result`
   - `status = recorded_from_single_shot_sentinel_llm`
5. Confirm flags:
   - `dispatch_enabled = false`
   - `runs_specialist_tools = false`
   - `writes = false`
   - `applies_runtime_change = false`
6. Attempting the same approval again should return already-consumed behavior and must not call the LLM again.

## Disable Immediately

Unset or set false:

```text
OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED=
```

Restart the local Flask process if needed.

Confirm policy after the smoke:

- `specialist_dry_run.enabled = false`
- authority matrix `effective_single_shot_enabled = false`
- top-level `specialist_llm_enabled = false`

## Record Outcome

Log in `CURRENT_STATE.md` only after the smoke is complete:

- commit SHA tested,
- approval ID,
- dry-run request ID,
- dry-run result ID,
- whether the approval replay was blocked,
- whether the flag was turned back off,
- any owner notes.

Do not design the next authority step until this smoke result has been reviewed.
