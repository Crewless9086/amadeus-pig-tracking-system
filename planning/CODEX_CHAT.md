# CODEX CHAT - ACTIVE MISSION
Hi Codex, you are my head developer. I snacked you from the billionairs (Elon Musk, Naval Ravikant, Jeff Bezos and top polymaths), you are taking my ideas and reprogramming them into full blown billionar/CEO operarting system. You take something small and deepdive into our system and plan the best method to make this into something big. You see leverage, long term vision and asynmetric outcomes. You make a plan to get the best out of this, taking into consideration everything we have set up this far and how we can make it work togther. 

You're goals is to make us money and make us grow to become these legendary billionairs. You always think how best we can get that way, fast save and with precision. You advise, plan strategically and you keep going till you get almost 100% certantly this is correct and will work. You test, find bugs, fix problems and keep testing till you kow what you are about to debrief me on is the final and the utter best with 98% confidence this will work. You keep trying autonoumsly to get to these results. 

This is the single active mission intake file for Codex/Cursor.               
Owner can write rough thoughts here. Codex must turn them into a clear mission, plan, safe scope, implementation path, tests, and debrief.

This is the single active mission intake file for Codex/Cursor.

Owner can write rough thoughts here. Codex must turn them into a clear mission, plan, safe scope, implementation path, tests, and debrief.

---

## OWNER QUICK INPUT

### Concept / Problem / Idea

The probelm we had was when I added bulk weights and pen movements we got and error or fault which was related to the google sheet time out, we tried to fix this a few times but we keep getting stuck. I got tired of this and wanted to know if we migrated to supabase would this resolve these google sheet hiccups? I rather changed to something working instead of patching up and struggling. 

Owner notes:

a plan was formulated and I had a look , but the idea is that I wanted a full migration and ensure all functions, google sheet formulas and results are all carried over to supabase, meaninf the backend has to make up for all formulas in the current google sheets and so forth. That said it's a big mission but I do think this will resolve all these minor issues? 

### Desired Outcome

I have a simple sheet where my dad or the farm workers can upload bulk weight and pen movements and it's lodas with one press of a button, no time out, not isseas and all data is logged. 

### Urgency

Optional. If blank, Codex must classify.

- P0 - live/data-loss/security/revenue-blocking
- P1 - money path or urgent operational improvement
- P2 - current planned build
- P3 - future planned build
- P4 - idea/backlog

This is urgent as this is holding me up, and I need to add the bulk new weight in order to continue ahead with meat sales and then setting up fred and getting beacon to do a post. I'm just getting stuck here now. 

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

## APPROVAL LEVEL

Codex must classify the mission into one approval level.

If owner explicitly states an approval level, use it. - I give level 5 approval on this mission
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

Allowed files/areas:

Forbidden files/areas:

Source of truth:

Related docs:

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

"Following `CODEX_CHAT.md`, continue with `NEXT_STEPS.md`."

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
Codex writes summary here.
```

### Plan

```text
Codex writes plan here.
```

### Execution Log

```text
Branch: gs-mig-1-canonical-schema-dry-run
Files changed: canonical schema migration proposal, dry-run importer, dry-run tests, active docs, GS-MIG-1 report
Tests run: tests.test_google_sheets_farm_import_dry_run, tests.test_pig_weights_bulk_service, py_compile, live read-only dry-run
Results: dry-run mapped 217 pigs, 1,235 weight events, 185 location events, 261 medical events, 20 pens, 17 litters, 15 mating events, 3 products, 18 settings
Blockers: 6 WEIGHT_LOG rows missing Pig_ID need review before canonical import; migration not applied
```

### Debrief

```text
What changed:
What did not change:
Risks:
Owner verification:
GO/NO-GO:
```

---

## CLEANUP RULE

After owner accepts the mission:

1. Important outcomes must be copied into `CURRENT_STATE.md` and/or `NEXT_STEPS.md`.
2. Any detailed plan/report must live in the correct docs folder.
3. Raw owner notes may be copied to `planning/inbox/processed/YYYY-MM/`.
4. This file should be reset to this template so the owner has a clean sheet for the next mission.
