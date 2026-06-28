# REPO CLEANUP AND DOCS GOVERNANCE PROMPT

Use this in Cursor/Codex after ACCESS-1.1 is merged/deployed and logout is confirmed working.

## Goal

Clean up repo documentation and working structure so future Cursor/Codex runs always know:

- current state
- next steps
- what is urgent
- what is backlog
- where owner notes go
- what docs are canonical
- what docs are legacy/archive
- what must not be touched

This cleanup is to reduce chaos, not create more files.

## Current architecture decisions to preserve

- CHARLIE CORE is the top-level owner operating layer.
- Oom Sakkie remains Farm Commander under CHARLIE.
- SAM Meat Sales is the current urgent money-flow path.
- FRED is the future Transport Commander / transport money path.
- Supabase is live operational truth.
- Markdown/docs/Brain/Vault are guidance only.
- Obsidian is optional and not runtime infrastructure.
- Cursor/Codex is the build workshop, not the production brain.
- External Jarvis/ZOEY/OpenCove tools are not the core.
- Gatekeeper/owner approval rails cannot be bypassed.
- No customer sends, public posts, payments/deposits, reservations, dispatch, hardware control, or production records without approved rails.

## Current production state to record

Production `main` should include, at minimum:

- Pig Tracker bulk-weight release: `ed3a27d Improve bulk weight duplicate and movement handling`
- SAM Command Room release: `f6487da Improve SAM meat sales command room (#1)`
- SAM full-width layout: `e41d4a6 Polish SAM meat sales full-width dashboard`
- SAM read-only command-state endpoint: `7d7dc7e Add read-only SAM command state endpoint (#2)`
- Owner access session guard: PR #3 / merge status to be verified
- Owner logout UX: ACCESS-1.1 / merge status to be verified

Verify this instead of assuming.

## Phase CLEANUP-0 only: audit and plan first

This first cleanup phase is report-only unless explicitly stated otherwise.

Do not move, delete, rename, commit, or archive files yet.

Do not touch code, migrations, routes, templates, static files, assets, `.env`, screenshots, external sources, or planning files.

## Before starting

Run and show:

```bash
git fetch origin
git branch --show-current
git status --short
git log --oneline --decorate -10 origin/main
git diff --name-only
git diff --stat
git ls-files --others --exclude-standard
```

Report:

- current branch
- whether main is up to date
- uncommitted files
- untracked files
- deleted files
- whether `.env` is tracked or untracked
- whether docs/00-start-here contains owner-created untracked docs
- whether planning/ToDoList.md exists
- whether docs/00-start-here/NEXT_STEPS.md exists
- whether docs/00-start-here/CURRENT_STATE.md exists

## Protect these paths

Do not edit without explicit approval:

- `.env`
- `.claude/settings.local.json`
- `external_sources/**`
- `screenshots/**`
- `test-results/**`
- `static/assets/agents/**`
- `supabase/migrations/**`
- `planning/Prompts.md`
- any untracked owner files under `docs/00-start-here/**`

## Inspect docs structure

Inspect:

```text
docs/
docs/00-start-here/
docs/01-architecture/
docs/02-backend/
docs/03-google-sheets/
docs/04-n8n/
docs/05-ai/
docs/06-operations/
docs/07-decisions/
docs/08-business-modules/
docs/99-archive/
planning/
```

Also inspect, if present:

```text
planning/ToDoList.md
docs/00-start-here/NEXT_STEPS.md
docs/00-start-here/CURRENT_STATE.md
docs/00-start-here/CHARLIE_ACTIVE_HANDOVER.md
docs/00-start-here/OVERNIGHT_DEBRIEF_*.md
```

## Required CLEANUP-0 deliverable

Return a report only:

### 1. Canonical docs map

Identify the small set of docs that should become the active source:

```text
docs/00-start-here/README.md
docs/00-start-here/CURRENT_STATE.md
docs/00-start-here/NEXT_STEPS.md
docs/00-start-here/WORKFLOW.md
docs/00-start-here/DEPLOYMENT_SOP.md
docs/00-start-here/OWNER_INBOX_GUIDE.md
docs/07-decisions/ADR_0002_CHARLIE_CORE_TOP_LEVEL_ORCHESTRATOR.md
docs/01-architecture/CHARLIE_CORE_ARCHITECTURE.md
docs/01-architecture/AGENT_COLLABORATION_LEDGER.md
docs/08-business-modules/SAM_MEAT_SALES_RECOVERY_PLAN.md
docs/08-business-modules/FRED_TRANSPORT_MODULE_PLAN.md
docs/05-ai/AGENT_ROLES.md
```

If any are missing, propose them.
If any exist under different names, map them.

### 2. Owner intake workflow

Design this workflow:

```text
Owner writes raw notes, thoughts, bugs, screenshots, and ideas in:
planning/ToDoList.md

Cursor/Codex triages ToDoList into:
docs/00-start-here/NEXT_STEPS.md

Then updates:
docs/00-start-here/CURRENT_STATE.md
```

The workflow must support urgency:

```text
P0 - live/operational issue
P1 - money path / sales
P2 - active build
P3 - planned module
P4 - idea/backlog
```

Use these buckets in `NEXT_STEPS.md`:

```text
## P0 Operational / Live Issues
## P1 Money Path
## P2 Current Build
## P3 Planned Build
## P4 Ideas / Backlog
## Blocked / Waiting
## Done Since Last Review
```

`CURRENT_STATE.md` should have:

```text
## Production State
## Active Branches / PRs
## Current Access Status
## SAM Status
## Oom Sakkie Status
## CHARLIE Status
## FRED Status
## Ledger Status
## Known Risks
## Last Updated
```

### 3. Inbox/scratch folder proposal

Propose a clean intake area:

```text
planning/inbox/
  notes/
  screenshots/
  prompts/
  raw-cursor-reports/
  processed/
```

Rules:

- owner can dump rough notes/screenshots there
- Cursor/Codex may read and triage
- processed notes are moved to `planning/inbox/processed/YYYY-MM/`
- canonical decisions must be copied into docs, not left only in inbox
- screenshots should not live in docs unless they are active reference assets
- nothing in planning/inbox is production truth

### 4. Archive proposal

Propose archive destination:

```text
docs/99-archive/legacy/
docs/99-archive/superseded/
docs/99-archive/old-prompts/
docs/99-archive/old-screenshots-index.md
```

Important:
Do not delete files yet.
Do not move files yet.
Do not archive machine exports blindly.

For each candidate file, classify:

```text
KEEP ACTIVE
MERGE INTO ACTIVE DOC
ADD LEGACY BANNER
MOVE TO ARCHIVE
DELETE LATER AFTER OWNER REVIEW
NEEDS OWNER REVIEW
```

### 5. Duplicate/obsolete docs list

Find docs that duplicate or conflict with the CHARLIE direction.

Search for:

```text
n8n is the brain
Google Sheets owns source data
Sheets are the database
Oom Sakkie is the top-level brain
Oom Sakkie is the owner brain
Backend is the single Oom Sakkie brain
Jarvis is the core
ZOEY is the core
Obsidian is the runtime
source of truth
brain
CHARLIE
Oom Sakkie
SAM
FRED
```

Report only.
Do not edit yet.

### 6. Deployment/branch SOP proposal

Create a deploy policy for future docs:

```text
Small frontend layout fix:
clean branch from origin/main -> tests -> direct main push allowed only if owner approves

Auth/security/backend/migration/send/payment/reservation/public-post:
PR required

No feature branch deploy unless Render is configured to watch that branch.
Render deploys main.
Never merge polluted branches.
Never use git add .
Never commit .env/test-results/screenshots/external_sources unless explicitly approved.
```

### 7. Next cleanup phase proposal

Recommend the next phase, likely:

```text
CLEANUP-1 — Create/update start-here docs and intake workflow
```

Expected CLEANUP-1 files only:

```text
docs/00-start-here/README.md
docs/00-start-here/CURRENT_STATE.md
docs/00-start-here/NEXT_STEPS.md
docs/00-start-here/WORKFLOW.md
docs/00-start-here/DEPLOYMENT_SOP.md
docs/00-start-here/OWNER_INBOX_GUIDE.md
planning/ToDoList.md only if it exists and owner approves
```

No archive/move/delete until CLEANUP-2.

## Report format

Return:

```text
CLEANUP-0 REPORT

1. Repo status
2. Current production state
3. Canonical docs map
4. Owner intake workflow proposal
5. Archive/legacy candidates
6. Duplicate/conflict findings
7. Proposed folder structure
8. Files that should stay untouched
9. Files proposed for CLEANUP-1
10. Files proposed for archive review later
11. Risks
12. Confidence score
13. GO/NO-GO recommendation for CLEANUP-1
```

No implementation beyond CLEANUP-0 is approved.
