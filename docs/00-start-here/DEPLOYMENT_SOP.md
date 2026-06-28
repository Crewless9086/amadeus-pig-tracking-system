# Deployment SOP

This is the short deployment policy for Cursor/Codex sessions.

## Render Rule

Render deploys from `main` unless the service is explicitly configured otherwise.

Feature branches do not go live unless merged to `main` or Render is intentionally pointed at that branch.

Always verify Render after `main` changes.

Feature-branch deploy assumptions must be verified before relying on them.

## Branch Policy

Start from a clean branch or clean worktree based on `origin/main`.

Never merge polluted branches.

Never merge old SAM release branches or CHARLIE planning branches unless a later owner approval names them explicitly.

## Direct Main Push Policy

A small safe UI/layout fix may direct-push to `main` only when the owner explicitly approves direct-to-main and the final diff is exactly the approved file list.

Auth, security, backend, migrations, customer-send, payment/deposit, reservation, public-post, route guard, and production data changes require a PR.

## Required Pre-Release Output

Before commit or merge, show:

```bash
git status --short
git diff --name-only origin/main...HEAD
git diff --stat origin/main...HEAD
```

Also report:

- exact files changed
- tests/checks run
- pass/fail results
- whether untracked files exist
- whether `.env`, screenshots, test-results, external sources, `.claude`, or owner files are untouched

## Staging Rules

Never use `git add .`.

Stage only the owner-approved files by exact path.

Then show:

```bash
git diff --cached --name-only
git diff --cached --stat
```

Commit only if the staged file list is exactly correct.

## Never Commit Unless Explicitly Approved

- `.env`
- token values or secrets
- `test-results/`
- `screenshots/`
- `external_sources/`
- `.claude/settings.local.json`
- `planning/Prompts.md`
- unrelated owner files
- generated assets
- migrations not explicitly approved

## Post-Merge

After merge or direct push:

```bash
git fetch origin
git log --oneline --decorate -5 origin/main
```

Then check available deploy/CI status and report what is visible.
