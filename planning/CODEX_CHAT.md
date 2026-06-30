# CODEX CHAT - ACTIVE MISSION TEMPLATE

This is the single active mission intake file for Codex/Cursor.

Owner can write rough thoughts here. Codex must turn them into a clear mission, plan, safe scope, implementation path, tests, and debrief.

Use this file when you want to start a new mission without writing a perfect prompt.

This file and Telegram mission intake both follow `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`. Supabase `charlie_missions` is the durable mission queue; this file is the laptop-friendly active mission scratchpad.

---

## OWNER QUICK INPUT

### Concept / Problem / Idea

The concept is to create a lightweight CHARLIE Build Relay that connects me, Telegram, Cursor, and Codex so development can continue even when I am away from the laptop. This is the first practical step toward the bigger CHARLIE system, similar in spirit to Jarvis, where CHARLIE becomes my digital command layer and helps manage the build process. I have created a dedicated Telegram bot, @CharlieCoreBot, which should only be used by me and must be protected so no one else can control the build system. The bot API key will be stored securely in the .env file and must never be committed, printed, exposed in frontend code, or added to documentation. The purpose of the bot is to let Codex communicate with me from Cursor while it is working: it can send me progress updates, completion reports, approval requests, hard-stop alerts, and mission summaries. Instead of stopping every few minutes for small approvals, Codex must follow the structure and authority rules written in CODEX_CHAT.md and continue working until the task is complete, tested, pressure-tested, or truly blocked. If I send a new concept through Telegram, Codex should place that concept into the correct section of CODEX_CHAT.md, read the instructions already defined there, and begin the mission using the correct repo workflow. If I ask “what is next,” Codex should read NEXT_STEPS.md, return the next available missions as clear Telegram button options, and allow me to choose one from my phone. Once I select an option, Codex should write that selected mission into CODEX_CHAT.md, follow the mission rules, update the related docs, and continue building without needing me to sit at the laptop. This relay becomes the early version of CHARLIE’s future build-command system: Telegram is my remote control, NEXT_STEPS.md is the mission menu, CODEX_CHAT.md is the active instruction file, and Codex is the builder that keeps going until the mission is complete or a real owner-level decision is required.

### Desired Outcome

The desired outcome is that I can keep building the Amadeus Farm App, Oom Sakkie, SAM, FRED, and eventually CHARLIE from anywhere without being trapped in front of Cursor all day. I should be able to send a mission from Telegram, approve a mission by pressing a button, or ask Codex what the next priority is without opening the laptop. Codex should then read the current state, check NEXT_STEPS.md, load the chosen mission into CODEX_CHAT.md, and continue working under the rules already defined in the repo. Once a mission is active, Codex should not stop for every small implementation choice; it should build, test, pressure-test, fix bugs, update docs, commit, push, and prepare the work for review according to the approved authority level. I should only be interrupted for real red-zone decisions, such as destructive migrations, production data deletion, missing secrets, failed tests that cannot be fixed, confidence dropping below the required threshold, or any action involving customer sends, payments, public posts, reservations, or unsafe production writes. When Codex needs approval, Telegram should send me a short message with clear button choices, so I can approve, reject, pause, or choose the next path from my phone. When Codex completes a task, it should send a clear debrief showing the branch, commits, files changed, tests run, pressure-test results, PR link, deployment status, confidence score, and what I need to live-test. The system must keep CURRENT_STATE.md, NEXT_STEPS.md, and CODEX_CHAT.md updated so the repo remains clean and Codex always knows what has been done, what is active, and what comes next. This allows long autonomous build sessions instead of broken stop-start conversations where progress depends on me approving every minor step. The final outcome is a proper build-control workflow where CHARLIE eventually becomes the command layer that manages missions, approvals, Codex instructions, release tracking, owner notifications, and operational follow-ups while I continue moving and working from anywhere.

### Urgency

Optional. If blank, Codex must classify.

- P0 - live/data-loss/security/revenue-blocking
- P1 - money path or urgent operational improvement
- P2 - current planned build
- P3 - future planned build
- P4 - idea/backlog

```text
URGENCY?
```

### Mission Type

Optional. If blank, Codex must classify.

- report-only
- planning/docs
- bugfix
- feature build
- migration plan
- release/merge
- cleanup
- live verification

```text
TYPE?
```

### Approval Level

Optional. If blank, Codex must choose the safest level and stop before hard stops.

- LEVEL 0 - Report only
- LEVEL 1 - Read-only investigation / planning
- LEVEL 2 - Docs / planning edits
- LEVEL 3 - Code/test build
- LEVEL 4 - Release / merge / deploy
- LEVEL 5 - Destructive / production data-changing work

```text
APPROVAL?
```

---

## DEFAULT CODEX OPERATING RULES

Codex must always:

- Read this file first.
- Read:
  - `docs/00-start-here/README.md`
  - `docs/00-start-here/CURRENT_STATE.md`
  - `docs/00-start-here/NEXT_STEPS.md`
  - `docs/00-start-here/WORKFLOW.md`
  - `docs/00-start-here/DEPLOYMENT_SOP.md`
  - `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`
- Check branch/status/diff before edits.
- Work from `main` unless a clean worktree/branch is needed.
- Use one branch/worktree per mission when code changes are needed.
- Keep changes scoped to the mission.
- Prefer existing repo patterns over new architecture.
- Update active docs when the mission changes current state or next steps.
- Preserve owner notes until they are copied into canonical docs or processed inbox.
- Never use `git add .`.
- Debrief with exact files changed, tests run, risks, and next steps.

---

## APPROVAL LEVELS

Codex must classify each mission into one approval level.

If owner explicitly states an approval level, use it.
If unclear, default to LEVEL 1.

### LEVEL 0 - Report Only

Allowed:

- inspect files
- inspect git status/log/diff
- read-only searches
- produce report

Forbidden:

- file edits
- commits
- pushes
- migrations
- production writes

### LEVEL 1 - Read-Only Investigation / Planning

Allowed:

- inspect code/docs
- run safe read-only commands
- run existing tests if they do not write production data
- inspect read-only Supabase/Google Sheets if explicitly relevant and safe
- produce plan/report

Forbidden:

- file edits unless owner later approves
- production writes
- migrations
- commits/pushes

### LEVEL 2 - Docs / Planning Edits

Allowed:

- edit docs/planning files
- update `CURRENT_STATE.md`
- update `NEXT_STEPS.md`
- update relevant planning docs
- create report docs

Forbidden:

- code changes
- migrations
- production writes
- commits/pushes unless explicitly approved

### LEVEL 3 - Code/Test Build

Allowed:

- create branch/worktree
- edit scoped code/tests/templates/static files
- run tests
- commit and push only if owner explicitly says commit/push is approved

Forbidden:

- merge to main unless explicitly approved
- production migrations
- production data writes
- customer sends
- public posts
- payments/deposits
- reservations
- lifecycle/purpose writes unless explicitly in scope

### LEVEL 4 - Release / Merge / Deploy

Allowed only when owner explicitly approves:

- merge PR
- push to main
- apply approved migration
- verify deploy

Must still show:

- diff
- files changed
- tests run
- migration status if any
- GO/NO-GO

### LEVEL 5 - Destructive / Data-Changing Work

Requires explicit approval every time.

Includes:

- deleting folders/files
- `git clean`
- destructive reset
- production Supabase writes
- production Google Sheets writes
- migrations that alter/drop/update existing data
- customer sends
- public posts
- payments/deposits
- reservations
- lifecycle/purpose writes

---

## HARD STOPS

Codex must stop and report before doing any of these unless the mission explicitly approves them:

- destructive deletes
- production data writes
- Google Sheets writes
- Supabase writes
- migrations
- customer sends
- public posts
- payment/deposit changes
- stock reservations
- pig lifecycle/purpose changes
- `.env` or secret changes
- unclear source of truth
- expanding beyond approved files/scope
- failed tests that cannot be fixed safely
- touching screenshots/external_sources/static assets unless approved
- building CHARLIE/FRED/ledger/Phase 3A.6 unless explicitly approved

---

## CODEX MUST PRODUCE THIS BEFORE BUILDING

### Mission Summary

Codex rewrites the owner concept into a clean mission.

### Classification

- Urgency:
- Mission type:
- Approval level:
- Build confidence:
- Is this safe to execute now?

### Scope

- Allowed files/areas:
- Forbidden files/areas:
- Source of truth:
- Related docs:

### Plan

Codex must list:

1. Inspection needed
2. Implementation steps
3. Tests
4. Pressure tests if relevant
5. Rollback plan
6. Owner decisions needed
7. GO/NO-GO

### Confidence Gate

No code build should start unless confidence is 96%+.

If below 96%, Codex must list:

- exact missing evidence
- exact files/routes/data to inspect
- exact test needed
- exact owner question, only if the system cannot inspect it itself

---

## EXECUTION RULES

When execution is approved, Codex must:

1. Create/use a clean branch if code changes are needed.
2. Show:
   - `git branch --show-current`
   - `git status --short`
   - `git diff --name-only origin/main`
   - `git diff --stat origin/main`
3. Make scoped edits only.
4. Run relevant tests.
5. Update docs when current state or next steps changed.
6. Commit/push only if approval level allows it.
7. Never merge without explicit merge approval unless the mission explicitly grants emergency merge permission.

---

## DOC UPDATE RULES

Codex must update docs when relevant.

Use:

- `docs/00-start-here/CURRENT_STATE.md`
  - live state
  - merged/deployed work
  - active blocker
  - current branch/phase
  - what is not started

- `docs/00-start-here/NEXT_STEPS.md`
  - priorities
  - P0-P4 queue
  - blocked/waiting
  - next approved build

- `docs/06-operations/`
  - operational plans
  - evidence logs
  - migration plans
  - pressure-test reports

- `planning/ToDoList.md`
  - raw owner notes
  - processed markers
  - links to plan files

- `planning/inbox/processed/YYYY-MM/`
  - preserved copies of completed raw notes when needed

Do not silently delete owner notes.

---

## CONTINUATION COMMAND

If owner says:

`Following CODEX_CHAT.md, continue with NEXT_STEPS.md.`

Codex should:

1. Read this file.
2. Read `CURRENT_STATE.md`.
3. Read `NEXT_STEPS.md`.
4. Identify the highest-priority unblocked item.
5. Classify approval level.
6. Proceed if safe under the current approval rules.
7. Stop only for hard stops or missing owner decisions.

---

## ACTIVE MISSION WORKSPACE

Codex fills this in during the mission.

### Mission Summary

```text
Build CHARLIE Build Relay v0: an owner-only Telegram command layer that can report status, list NEXT_STEPS mission options, prepare mission intake, and optionally update CODEX_CHAT.md when explicitly enabled by env.
```

### Plan

```text
1. Reuse the existing Oom Sakkie Telegram security pattern: disabled by default, owner allowlist, webhook secret, and no unsafe authority.
2. Add CHARLIE relay policy and Telegram webhook endpoints.
3. Support /status, /next, /select, /mission, and free-text mission intake.
4. Keep commit/merge/deploy/shell/production-write/customer/public/payment/reservation/lifecycle authority false.
5. Gate CODEX_CHAT.md file writes behind CHARLIE_BUILD_RELAY_CODEX_CHAT_WRITE_ENABLED.
6. Document the rollout and next phases in docs/06-operations/CHARLIE_BUILD_RELAY_PLAN.md.
7. Add tests for security, owner allowlist, button options, mission intake, and explicit CODEX_CHAT write gating.
```

### Execution Log

```text
Branch: charlie-relay-architecture-plan
Files changed: app.py, modules/charlie/*, tests/test_charlie_build_relay.py, tests/test_owner_access.py, CHARLIE relay plan, active docs, ToDoList reset/log.
Tests run: tests.test_charlie_build_relay, tests.test_owner_access, tests.test_oom_sakkie_routes, tests.test_frontend_route_contracts, tests.test_workflow_contracts, tests.test_oom_sakkie_service, tests.test_sam_command_state, tests.test_sam_meat_runtime, py_compile.
Results: focused tests passed. One combined SAM command timed out, then passed when split.
Blockers: no live Telegram webhook configured yet; requires Render/.env env vars and Telegram webhook setup after PR approval/merge.
```

### Debrief

```text
What changed: CHARLIE Build Relay v0 now exists as a safe disabled-by-default owner Telegram relay with /status, /next, /select, /mission, and optional CODEX_CHAT write gating.
What did not change: no customer sends, public posts, payments, reservations, production data writes, migrations, deploys, commits/merges from Telegram, or farm lifecycle writes.
Risks: Telegram cannot fully drive Codex unless a local Codex/Cursor process or future Supabase mission queue consumes the mission; Render filesystem writes are not durable.
Owner verification: configure @CharlieCoreBot env vars, set webhook, send /help, /status, /next, and /mission test messages.
GO/NO-GO: GO for PR review of v0; NO-GO for dangerous Telegram approvals or autonomous deployment authority.
```

---

## CLEANUP RULE

After owner accepts the mission:

1. Important outcomes must be copied into `CURRENT_STATE.md` and/or `NEXT_STEPS.md`.
2. Any detailed plan/report must live in the correct docs folder.
3. Raw owner notes may be copied to `planning/inbox/processed/YYYY-MM/`.
4. This file should be reset to this template so the owner has a clean sheet for the next mission.
