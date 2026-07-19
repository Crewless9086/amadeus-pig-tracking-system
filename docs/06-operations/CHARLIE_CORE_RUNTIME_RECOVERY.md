# CHARLIE CORE Runtime Recovery and Promotion

## Operating rule

CHARLIE's hosted command plane and the laptop CORE execution plane are separate health domains. Telegram responsiveness does not prove that the local agent workforce is ready.

CORE may start autonomously only when all cold-start gates pass:

- the runtime worktree matches its promoted manifest commit and root;
- GitHub CLI authentication is valid;
- exactly one Telegram transport is selected (`webhook`, `polling`, or deliberately `disabled`);
- no infrastructure hold, live supervisor, orphan runner, or repository-operation conflict exists;
- the scheduled task uses `pythonw.exe` and the promoted runtime worktree.

## Authoritative runtime

The owner checkout is not an execution runtime. It may contain owner files, local commits, and active notes. The promoted runtime is a detached clean worktree at `.charlie_runner/core-runtime-current`.

Promotion writes `.charlie_runner/runtime-manifest.json`. The manifest binds the runtime root to one tested commit. The watchdog refuses cold start when the manifest is missing, invalid, or does not match the runtime checkout.

## Safe promotion

```powershell
powershell -ExecutionPolicy Bypass -File scripts\promote_charlie_runtime.ps1
```

The promotion command fetches `origin`, refuses a dirty existing runtime, checks out the exact source revision detached, runs focused runtime tests, writes the manifest only after tests pass, registers the hidden `pythonw.exe` watchdog task, and verifies its installed action.

At cold start, CORE may bootstrap `GH_TOKEN` in process memory from the existing Windows Git credential. The token is never returned, logged, committed, or written to the runtime manifest. This keeps Git and GitHub CLI on one credential source after restart.

It does not reset the owner checkout, delete branches, apply migrations, claim missions, merge PRs, or start CORE.

## Read-only audit

```powershell
venv\Scripts\python.exe scripts\charlie_runtime_audit.py audit --runtime-dir .charlie_runner
```

Healthy output is `core_cold_start_ready`. Any blocker is typed and must remain visible; do not clear an infrastructure hold merely to make the dashboard green.

## Git discipline

- Autonomous work begins from a fetched immutable revision.
- Mission recovery consumes `FETCH_HEAD`, not a mutable or newly-created local branch.
- The owner checkout is reconciled commit-by-commit; never hard-reset it to repair CORE.
- A merged runtime fix is not operational until promotion tests pass and the manifest/task agree.
- Runtime drift is a blocker, not an informational warning.

## Telegram discipline

Hosted webhook is the primary private executive ingress. Local polling is diagnostic fallback only. Do not enable polling while Telegram has an active webhook for the same bot.

## Restart rehearsal

1. Audit cold-start readiness.
2. Start the scheduled watchdog once.
3. Verify one supervisor and one runner child.
4. Verify two fresh watchdog/heartbeat cycles.
5. Confirm runtime manifest and heartbeat source revision agree.
6. Dry-run queue selection.
7. Resume one approved recovery mission.
8. Confirm lease, stage, artifacts, and Telegram status before opening the remaining queue.

Production migrations remain a separate explicit approval even when a mission may author an additive unapplied migration.
