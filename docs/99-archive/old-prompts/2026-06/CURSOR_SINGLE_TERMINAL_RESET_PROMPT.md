# Cursor / Codex Prompt — Start Here After Closing All Terminals

You are operating as the only active Cursor/Codex terminal for this repo.

Read and follow:

```text
docs/00-start-here/CHARLIE_ACTIVE_HANDOVER.md
```

If that file does not exist yet, create it from the owner-provided handover text before doing anything else.

Current task:

```text
Phase RESET-1 — Single-Terminal Repo Reconciliation
```

This is report-only.

Do not code.
Do not commit.
Do not push.
Do not stash.
Do not clean.
Do not merge.
Do not run migrations.
Do not edit files.
Do not use git add .

First run:

```bash
git fetch origin
git branch --show-current
git status --short
git log --oneline --decorate -12
git diff --name-only
git diff --cached --name-only
git diff --stat
git log --oneline --decorate -8 origin/main
```

Then inspect the CHARLIE branch:

```bash
git log --oneline --decorate -8 charlie-core-v3-approved-phase0b
```

Then report:

1. Current branch.
2. Whether there are staged files.
3. Whether there are uncommitted files.
4. Whether SAM Phase 3A.1/3A.2 files are currently dirty, committed, or absent.
5. Whether the SAM Playwright spec exists.
6. Whether `test-results/sam-meat-command-room.png` exists but is untracked.
7. Whether `origin/main` includes `ed3a27d Improve bulk weight duplicate and movement handling`.
8. Whether the CHARLIE branch contains commits that must not be merged into main.
9. Exact list of files that would be included in a SAM release branch.
10. Exact list of files that must remain uncommitted.
11. Recommendation:
    - GO/NO-GO for SAM release prep
    - GO/NO-GO for docs update
    - GO/NO-GO for any push

Rules:

- Do not merge `charlie-core-v3-approved-phase0b` into `main`.
- Do not push the CHARLIE branch to `main`.
- Do not commit `test-results/`.
- Do not commit screenshots, external_sources, .claude, planning/Prompts.md, docs/00-start-here, or unrelated owner files.
- Do not claim Render is updated unless `origin/main` has the release commit and Render deploy evidence is provided.

Return a concise RESET-1 report and wait for owner approval.
