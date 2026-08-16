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

The legacy promotion command below is retained for historical operations. Do not
run it beneath a development/Codex process tree because it combines source
validation, scheduled-task registration, and runtime staging.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\promote_charlie_runtime.ps1
```

The promotion command fetches `origin`, refuses a dirty existing runtime, checks out the exact source revision detached, runs focused runtime tests, writes the manifest only after tests pass, registers the hidden `pythonw.exe` watchdog task, and verifies its installed action.

At cold start, CORE may bootstrap `GH_TOKEN` in process memory from the existing Windows Git credential. The token is never returned, logged, committed, or written to the runtime manifest. This keeps Git and GitHub CLI on one credential source after restart.

It does not reset the owner checkout, delete branches, apply migrations, claim missions, merge PRs, or start CORE.

## Isolated source staging boundary

`scripts/charlie_runtime_stage.py` separates source staging from validation,
watchdog registration, and CORE startup. It consumes a full 40-character commit
and the SHA-256 of an immutable JSON validation receipt produced in a disposable
process boundary. The receipt binds the exact commit and records positive focused
and full-suite results, no host-process visibility, and zero targets outside the
boundary.

Both `plan` and `stage` require the exact current runtime, execution, and manifest
commit identities. This makes a deliberately retained mismatch explicit instead
of treating it as authority. Planning is read-only and reports `zero_effect`.
Staging requires clean worktrees, one unambiguous non-running watchdog task owned
by the runtime root, `supervisor_stopped`, `governed_stop_active`, and an unchanged
stop marker. It atomically acquires a non-stealable release-lane file and writes a
byte-exact rollback tuple before switching either detached worktree.

Only after both worktrees read back at the source commit does staging write the
manifest. It never clears the stop, registers/enables/invokes the watchdog, or
starts/stops CORE. Failure after the first switch restores both prior worktree
heads and the exact prior manifest bytes; the durable ledger retains the lane,
rollback, and result records for review.

Example read-only planning shape (values must come from independently verified
evidence, never from mutable aliases):

```powershell
python -B scripts\charlie_runtime_stage.py plan `
  --source-ref <40-character-commit> `
  --runtime-root <runtime-worktree> `
  --execution-root <execution-worktree> `
  --state-root <state-directory> `
  --receipt <sealed-receipt.json> `
  --receipt-sha256 <64-character-sha256> `
  --expected-runtime-head <40-character-commit> `
  --expected-execution-head <40-character-commit> `
  --expected-manifest-commit <40-character-commit>
```

Changing `plan` to `stage` is a separate authorized release action. Source review
and CI do not authorize that action and do not prove runtime-loaded behavior or
terminal-independent continuity.

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
