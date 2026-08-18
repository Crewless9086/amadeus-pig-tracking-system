# Deployment Standard

Render deploys from `main` unless configured otherwise.

Use clean branch/worktree discipline. Never use `git add .`. Stage exact files only.

Always verify live after `main` changes.

Legacy compatibility path: `docs/00-start-here/DEPLOYMENT_SOP.md`.

## Branch And Commit Discipline

- Confirm branch with `git status` / `git branch`.
- Do not mix unrelated worktrees.
- Do not commit runner scratchpad noise unless the mission explicitly updates it.
- Stage exact files only.
- Commit message must describe the real change.
- Push the correct branch/remote.

Never use `git add .`. Before commit or merge inspect status, the exact
`origin/main...HEAD` file list and diff statistics. Stage only exact approved
paths, then inspect the cached file list/statistics before committing.

Never commit secrets, `.env`, tokens, test results, screenshots,
`external_sources/`, local `.claude` settings, owner scratch files, generated
assets or unapproved migrations. A direct push to `main` requires exact owner
approval and an exact bounded file list; auth, security, backend, migration,
customer-send, payment, reservation, public-post, route-guard and production
data changes use a reviewed PR.

## Release Gate

Before release/merge/deploy:

- tests relevant to changed surface passed;
- docs/Vault updated where behavior, agent roles, workflows, data, or business rules changed;
- migrations/data writes are explicitly identified;
- rollback or recovery path is known;
- owner final approval is recorded where required.

The release report identifies exact changed files, tracked/untracked state,
tests and outcomes, migration/data-write status, rollback, and confirmation that
unrelated owner files were untouched.

## Live Verification

After `main` changes that should deploy:

- verify Render/live target or explain why no live deploy is expected;
- confirm the exact URL checked;
- confirm key page/API behavior;
- if deploy is slow/pending, state the status rather than assuming success.

After merge, fetch authoritative main, record the exact merge/revision and check
available CI/deployment evidence. A healthy URL alone does not prove the changed
business path. If no deployment is expected, say so explicitly.
