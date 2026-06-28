# CHARLIE / SAM / Oom Sakkie — Single-Terminal Handover

Date: 2026-06-27  
Status: active handover for restarting with one Cursor/Codex terminal  
Purpose: prevent branch confusion, mixed terminal edits, wrong pushes, and loss of approved work.

---

## 1. Current Big Picture

The project direction is now locked:

```text
You
  ↓
CHARLIE CORE
  Top-level private owner operating layer
  ↓
Team leaders:
  Oom Sakkie = Farm Commander
  SAM = Meat Sales Command
  FRED = future Transport Commander
  Build Team = product/software delivery
  Personal Command = future personal/life admin
  Gatekeeper = approval/safety overlay
```

Core rules:

```text
Supabase = live operational truth.
Markdown/docs/Brain/Vault = guidance only.
Cursor/Codex = build workshop, not production brain.
Oom Sakkie remains Farm Commander.
SAM Meat Sales is the urgent money-flow path.
FRED is future transport money path.
Gatekeeper/owner approval rails cannot be bypassed.
```

External Jarvis/ZOEY/OpenCove/Obsidian are not the core. Obsidian may later be used only as an optional Markdown viewer/editor.

---

## 2. Current Branch/Deploy Situation

Known branch facts from the recent sessions:

```text
charlie-core-v3-approved-phase0b
  6886858 Document CHARLIE core baseline and stabilize Oom cockpit
  5425092 Improve bulk weight duplicate and movement handling

main was previously:
  e3e7903 Use product knowledge tool for Sam cut sets
```

Pig Tracker bulk-weight work was cherry-picked/released separately.

Owner reports Render is live for:

```text
ed3a27d Improve bulk weight duplicate and movement handling
```

Important:

```text
Do not merge charlie-core-v3-approved-phase0b into main.
Do not push the CHARLIE branch to main.
Do not use git add .
Do not stash automatically.
```

Before any new release, verify the live branch and commits:

```bash
git fetch origin
git log --oneline --decorate -8 origin/main
git show --name-only --oneline ed3a27d
```

---

## 3. Accepted Phase Status

### Accepted and complete

```text
Phase 0B     Evidence and safety verification
Phase 0B.1   Oom Sakkie Playwright harness reliability
Phase 0B.2   Oom Sakkie cockpit resilience and asset fallback
Phase 1      Docs/ADR cleanup
Phase 1B     Legacy doc conflict containment
Phase 2A     Agent Collaboration Ledger design review
Phase 3A.0   SAM Meat Sales Command Room planning
Phase 3A.1   SAM frontend-only Command Room shell
Phase 3A.2   SAM UI/test hardening
```

### Not yet approved

```text
No CHARLIE UI build.
No FRED build.
No ledger SQL migration.
No route guard implementation.
No backend resilience changes.
No agent portrait generation.
No voice integration.
No customer-send behavior change.
No public-post behavior change.
No dispatch automation.
```

---

## 4. SAM Meat Sales Current State

SAM is no longer just a technical workbench. The approved working direction is:

```text
/sales/meat-leads = SAM Meat Sales Command Room
```

Phase 3A.1 changed:

```text
templates/meat-sales-leads.html
static/js/meatSalesLeads.js
static/css/meatSalesLeads.css
```

It added:

```text
left lead list sorted by urgency/money state
center selected lead command panel
right gate stack
secondary System Workbench
Sam Missing Facts
Draft Reply
Owner Decision
Ledger Money Gate
Butcher Availability Gate
Beacon Demand Draft
Gatekeeper Approval/Block
Supabase History
computeLeadNextAction()
```

Phase 3A.2 changed:

```text
static/js/meatSalesLeads.js
tests/sam_meat_command_room_playwright.spec.js
```

It also generated local screenshot only:

```text
test-results/sam-meat-command-room.png
```

Do not commit test-results unless explicitly approved.

Safety status:

```text
computeLeadNextAction() is pure.
It does not fetch.
It does not approve.
It does not send.
It does not reserve.
It does not record payment.
It does not create public posts.

guidedNextStep() no longer chains:
pricing → owner approval → draft → approval → send
```

The Playwright test confirms the guided next-step button does not call these risky endpoints:

```text
/owner-money-path-approval
/customer-followup-send-approval
/customer-followup-send
/draft-order
/carcass-reservations
/deposit-events
/beacon/facebook-post-executions
```

---

## 5. Current Next Best Step

Before doing any more feature work, perform a clean single-terminal reset and status audit.

### New immediate phase

```text
Phase RESET-1 — Single-Terminal Repo Reconciliation
```

Purpose:

```text
close mixed-terminal confusion
identify exactly what is committed/uncommitted
protect owner files
prepare clean SAM release if screenshot is approved
```

RESET-1 is report-only unless explicitly approved.

---

## 6. Close Existing Terminals Safely

Before closing each old terminal, capture and save output somewhere safe:

```bash
git branch --show-current
git status --short
git log --oneline --decorate -8
git diff --name-only
git diff --cached --name-only
git diff --stat
```

Then stop all old terminals.

Do not ask any old terminal to commit, push, stash, clean, or merge.

---

## 7. New Terminal Startup Commands

Open one new Cursor/Codex terminal in the repo root and run:

```bash
git fetch origin
git branch --show-current
git status --short
git log --oneline --decorate -12
git diff --name-only
git diff --cached --name-only
git diff --stat
```

Then inspect key branch state:

```bash
git log --oneline --decorate -8 origin/main
git log --oneline --decorate -8 charlie-core-v3-approved-phase0b
```

If `sam-meat-command-room-release` exists remotely or locally, inspect it:

```bash
git branch --all | grep sam-meat
```

Windows PowerShell alternative:

```powershell
git branch --all | Select-String sam-meat
```

---

## 8. Files That Must Not Be Accidentally Committed

Never stage these unless specifically approved:

```text
test-results/
screenshots/
external_sources/
.claude/settings.local.json
planning/Prompts.md
docs/00-start-here/*
static/assets/agents/oom-sakkie/hero/*
unrelated deleted files
```

Never use:

```bash
git add .
```

Use explicit paths only.

---

## 9. Expected SAM Release Files

If screenshot is approved and SAM is released, the release should include only:

```text
templates/meat-sales-leads.html
static/js/meatSalesLeads.js
static/css/meatSalesLeads.css
tests/sam_meat_command_room_playwright.spec.js
```

Do not include:

```text
test-results/sam-meat-command-room.png
CHARLIE docs
ledger docs
Pig Tracker files
external_sources
screenshots
owner start-here docs
```

---

## 10. Required SAM Release Checks

Before committing SAM release, run:

```bash
node --check static/js/meatSalesLeads.js
node --check tests/sam_meat_command_room_playwright.spec.js
```

Run focused SAM/meat tests:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_sam_meat_runtime tests.test_meat_ops tests.test_meat_match_engine tests.test_meat_fulfillment tests.test_meat_documents tests.test_meat_reconciliation
```

Run SAM Playwright spec:

```bash
npx playwright test -c tests tests/sam_meat_command_room_playwright.spec.js --reporter=line
```

The previous successful evidence was:

```text
114 focused SAM/meat Python tests passed.
SAM Playwright command-room spec passed: 3 passed.
```

---

## 11. Approved SAM Release Flow

Only after screenshot review:

```bash
git switch -c sam-meat-command-room-release
git add templates/meat-sales-leads.html
git add static/js/meatSalesLeads.js
git add static/css/meatSalesLeads.css
git add tests/sam_meat_command_room_playwright.spec.js
git diff --cached --name-only
git diff --cached --stat
```

Stop and review staged files.

If clean:

```bash
git commit -m "Improve SAM meat sales command room"
git push -u origin sam-meat-command-room-release
```

Then merge/release through the PUSH flow.

Do not push directly to `main` unless explicitly approved at that moment.

---

## 12. Longer-Term Next Phases After SAM Release

Recommended order:

```text
Phase 3A.3   SAM release preparation and deployment
Phase 3A.4   SAM command-state endpoint planning
Phase 2B     Minimal Agent Collaboration Ledger SQL review/migration
Phase 0C     PRISMA CHARLIE UI Product Spec as build artifact
Phase 4      CHARLIE read-only owner cockpit
Phase 3B     FRED Transport planning/MVP
```

Do not let ledger work delay SAM’s money path.

---

## 13. Single-Terminal Operating Rule

Use one terminal only until the repo is clean.

If multiple terminals are used later:

```text
one controller
one branch per workstream
one file ownership list
one release terminal
no shared dirty working tree
```

But for now:

```text
one terminal
one branch
one approved phase
one staged file list
one push path
```
