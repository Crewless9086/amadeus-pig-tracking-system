# Deployment Standard

Render deploys from `main` unless configured otherwise.

Use clean branch/worktree discipline. Never use `git add .`. Stage exact files only.

Always verify live after `main` changes.

Source reference: `docs/00-start-here/DEPLOYMENT_SOP.md`.

## Branch And Commit Discipline

- Confirm branch with `git status` / `git branch`.
- Do not mix unrelated worktrees.
- Do not commit runner scratchpad noise unless the mission explicitly updates it.
- Stage exact files only.
- Commit message must describe the real change.
- Push the correct branch/remote.

## Release Gate

Before release/merge/deploy:

- tests relevant to changed surface passed;
- docs/Vault updated where behavior, agent roles, workflows, data, or business rules changed;
- migrations/data writes are explicitly identified;
- rollback or recovery path is known;
- owner final approval is recorded where required.

## Live Verification

After `main` changes that should deploy:

- verify Render/live target or explain why no live deploy is expected;
- confirm the exact URL checked;
- confirm key page/API behavior;
- if deploy is slow/pending, state the status rather than assuming success.
