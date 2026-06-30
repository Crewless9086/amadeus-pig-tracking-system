# CHARLIE Mission Protocol

This protocol keeps Telegram, `planning/CODEX_CHAT.md`, Cursor, and Codex aligned around one mission system.

CHARLIE is the owner command layer. CHARLIE oversees build missions, approval state, agent coordination, and owner debriefs. Oom Sakkie, SAM, FRED, and future agents operate inside their domains, but CHARLIE owns the mission queue and escalation rules.

## Intake Sources

Mission intake may come from:

- Telegram through `@CharlieCoreBot`
- `planning/CODEX_CHAT.md`
- Cursor/Codex chat
- `planning/ToDoList.md`
- future CHARLIE owner cockpit UI

All intake paths must normalize into the same mission contract before build work starts.

## Mission Contract

Every mission must resolve to:

- mission id
- raw owner request
- mission title
- urgency: P0, P1, P2, P3, or P4
- mission type
- approval level
- current status
- source of truth
- allowed scope
- forbidden scope
- hard stops
- tests and pressure tests
- rollback plan
- owner decisions needed
- debrief link or PR link when available

Telegram mission intake is stored in Supabase `charlie_missions`. Mission decisions and state changes are recorded in `charlie_mission_events`.

`planning/CODEX_CHAT.md` remains the laptop-friendly active mission scratchpad. Supabase is the durable mission queue.

## Mission Vault

Each mission carries a structured vault record in Supabase metadata. The vault is the canonical mission packet that feeds Codex/Cursor and later specialist agents.

The vault must capture:

- problem statement
- desired outcome
- mission stage
- acceptance criteria
- test plan and pressure-test plan
- forbidden actions
- owner decisions needed
- media/reference links
- rollback plan
- confidence target

The current dashboard supports mission intake with rough concept text, desired outcome, urgency/type, and media/reference links. Binary media upload is a later storage phase; for now, mission media references are paths, URLs, or owner notes stored with the mission.

## Shared Context Pack

Every CHARLIE mission carries the same context pack so Telegram intake, dashboard intake, Codex pickup, and later specialist agents do not drift.

The context pack includes:

- active truth docs: `CHARLIE_MISSION_PROTOCOL.md`, `CURRENT_STATE.md`, `NEXT_STEPS.md`, `WORKFLOW.md`, `DEPLOYMENT_SOP.md`, and `OWNER_INBOX_GUIDE.md`
- shared data rules: Supabase is canonical where migrated; Google Sheets is legacy/reference/export unless a route is explicitly still fallback
- approval rules for LEVEL 1 through LEVEL 5
- agent order: planner, architect, builder, tester, reviewer
- parallel work status, currently disabled until Phase 6 parallel controls are proven

Codex/Cursor must treat the context pack as the mission brief. If the owner gives a rough idea in Telegram or the dashboard, CHARLIE stores the rough idea and the shared context pack together. Codex then scopes, builds, tests, and debriefs from that combined packet.

## Agent Workflow

CHARLIE mission work follows five structured roles:

- planner - turns owner concept into a scoped mission plan
- architect - identifies source of truth, files, risks, and acceptance criteria
- builder - implements scoped changes under the approval level
- tester - runs focused tests, regression tests, and pressure tests
- reviewer - checks diff safety, docs, debrief, and release readiness

These roles are currently tracked as mission metadata and followed by Codex/Cursor. Stage 6 adds owner-visible handoff controls and Telegram workflow updates so each role can record findings for the next role. They are not yet separate autonomous parallel agents. Parallel workers come later after mission isolation, branch boundaries, and conflict controls are proven.

## Owner Review Gate

CHARLIE's target workflow must stop at owner review before anything is pushed live.

The intended mission loop is:

1. Owner creates or approves a mission from Telegram or `/charlie`.
2. Local runner picks up the approved mission and writes the execution packet into `planning/CODEX_CHAT.md`.
3. Codex/Cursor executes the structured stages: planner, architect, builder, tester, reviewer.
4. Reviewer prepares the owner review packet and marks the mission `pr_ready`.
5. CHARLIE shows the mission in a dashboard Review section.
6. Owner reviews the packet, local preview, findings, bugs, test results, risks, PR/diff, and comments.
7. Owner either approves final release, sends the mission back with comments, pauses, or rejects it.
8. Final owner approval records `release_approved`; only a local Codex release bridge may then proceed through release/merge/deploy checks under the normal deployment SOP.
9. After verified release or explicit closeout, CHARLIE marks the mission `done`, `merged`, or `deployed` as appropriate.

The Review section must show:

- mission title, id, urgency, approval level, and current stage
- problem statement, desired outcome, acceptance criteria, and forbidden actions
- planner, architect, builder, tester, and reviewer findings
- files changed, commits, branch, PR link, and diff summary
- test commands, pass/fail results, pressure-test notes, and known bugs
- local preview command or local URL when available
- Render/live preview link when available
- migration/data-write/safety proof
- owner comments and decision history
- clear actions: approve final release, send back with comments, pause, reject, or mark done when no release is needed

Owner comments are mission instructions. When the owner sends a mission back from review:

- CHARLIE records the comment in the Mission Vault and mission events.
- mission status returns to `approved` when local runner/Codex pickup is needed again.
- workflow stage returns to the correct point, usually planner for scope changes, architect for design/source-of-truth changes, builder for implementation fixes, or tester for verification-only fixes.
- Codex/Cursor must include the owner comments in the next execution packet.
- previous findings remain attached so the mission keeps its audit trail.

Final approval is separate from build approval. LEVEL 3 can build, test, commit, push, and open a PR, but it must stop at owner review. Final approval must record `release_approved`, not normal `approved`; LEVEL 4 can merge/release only after the owner approves the final review packet and the deployment SOP checks are clean. Red-zone actions still require separate explicit approval even inside LEVEL 4.

No mission should be considered complete merely because code was written. A mission is complete only when the owner accepts the final review result, or when the owner explicitly marks a non-release mission done.

## Status Model

Allowed mission statuses:

- `new`
- `triaged`
- `planned`
- `approved`
- `in_progress`
- `blocked`
- `pr_ready`
- `merged`
- `deployed`
- `done`
- `paused`
- `rejected`

Status changes are mission records only. A status change does not execute shell commands, merge code, apply migrations, deploy, or write operational data.

## Telegram Command Console

Current safe commands:

- `/help` - command list and safety rules
- `/status` - repo/project state summary
- `/next` - current CHARLIE handoff: active/PR-ready mission, approved waiting pickup, new missions waiting approval, then `NEXT_STEPS.md` fallback
- `/missions` - recent durable mission queue records
- `/mission <idea>` - create mission intake
- `/mission <mission id>` - show mission detail
- `/debrief <mission id>` - show mission detail/debrief view
- `/review` - show PR-ready or blocked missions waiting for owner review
- `/approve <mission id> level1` - approve read-only investigation
- `/approve <mission id> level3` - approve code/test/PR handoff
- `/approve <mission id> level4` - approve merge/release handoff after verification
- `/workflow <mission id> tester complete` - record planner/architect/builder/tester/reviewer handoff state
- `/done <mission id>` - mark completed/old mission records done
- `/pause <mission id>` - pause a mission
- `/reject <mission id>` - reject a mission

Approval commands record owner authority for the Codex runner handoff. Telegram never executes shell commands directly. A running Codex/Cursor session or local runner must still pick up the approved mission and obey the recorded level.

## Codex Pickup Bridge

Codex can pick up the next approved CHARLIE mission with:

```bash
python scripts/charlie_mission_pickup.py
```

The pickup bridge:

- reads the next approved mission from Supabase
- writes the mission into `planning/CODEX_CHAT.md`
- marks the mission `in_progress`
- optionally sends an owner Telegram notification with `--notify`

Dry-run mode:

```bash
python scripts/charlie_mission_pickup.py --dry-run
```

This bridge is the safe handoff from Telegram to Codex. It does not make Telegram run shell commands directly. A running Codex/Cursor session must still execute the pickup and follow the mission protocol.

Watch mode:

```bash
python scripts/charlie_mission_pickup.py --watch --notify
```

Watch mode polls for an approved mission and picks up the first one it finds. It still only writes `planning/CODEX_CHAT.md`, marks the mission `in_progress`, and notifies the owner. It does not execute arbitrary build commands.

Continuous local watch mode:

```bash
python scripts/charlie_mission_pickup.py --watch --continuous --notify --interval-seconds 30
```

Continuous mode keeps polling after each check. It will not pick up another approved mission while a mission is already `in_progress` or `pr_ready`.

The pickup bridge writes the mission approval level and runner mode into `planning/CODEX_CHAT.md`:

- `LEVEL 0` -> report only
- `LEVEL 1` -> read-only scope and evidence
- `LEVEL 2` -> docs/planning edits
- `LEVEL 3` -> code/test/PR build, no merge
- `LEVEL 4` -> merge/release handoff after diff and tests are verified
- `LEVEL 5` -> red-zone work still requires exact owner confirmation

## Local Runner Control

Approval records owner permission. It does not start Codex by itself. A local runner must be active for approved missions to move automatically into `planning/CODEX_CHAT.md`.

Local helper commands:

```bash
python scripts/charlie_runner_control.py status
python scripts/charlie_runner_control.py start
python scripts/charlie_runner_control.py stop
```

The runner writes a local heartbeat under `.charlie_runner/`. The `/charlie` dashboard reads that heartbeat and shows whether the local runner is active, stale, or not started. The dashboard still cannot start or stop shell processes directly.

## CHARLIE Mission Cockpit

The owner-only cockpit lives at:

```text
/charlie
```

The cockpit shows mission queue records, counts by status, and safe decision buttons. Cockpit decisions call the same protected mission APIs used by Telegram command decisions.

The cockpit can approve missions by level. The cockpit cannot execute shell commands directly, deploy manually, apply migrations, send customers, post publicly, take payments, reserve stock, or change farm lifecycle records.

The cockpit also shows runner handoff status:

- active mission, if one is `in_progress` or `pr_ready`
- next approved mission waiting for local pickup
- local runner active/stale/not-started status and last-seen time
- local runner start/status/stop commands
- clear note that web/Telegram cannot execute shell commands directly

Telegram `/next` must mirror this same handoff state before showing static planning fallback items. The owner should be able to see the same mission that `/charlie` is showing, open it with `/mission <id>`, and record approval with `/approve <id> level1`, `level3`, or `level4`.

## Required Codex Startup

Before acting on any mission, Codex must read:

- `planning/CODEX_CHAT.md`
- `docs/00-start-here/README.md`
- `docs/00-start-here/CURRENT_STATE.md`
- `docs/00-start-here/NEXT_STEPS.md`
- `docs/00-start-here/WORKFLOW.md`
- `docs/00-start-here/DEPLOYMENT_SOP.md`
- this file

If the mission came from Telegram, Codex must also inspect the Supabase mission record or the `/missions` queue summary when available.

## Approval Levels

The approval levels in `planning/CODEX_CHAT.md` remain authoritative:

- LEVEL 0 - report only
- LEVEL 1 - read-only investigation / planning
- LEVEL 2 - docs / planning edits
- LEVEL 3 - code/test build
- LEVEL 4 - release / merge / deploy
- LEVEL 5 - destructive / production data-changing work

If the owner approves a mission in Telegram, that approval means "Codex may proceed within the recorded approval level and hard stops." It does not override red-zone actions.

LEVEL 3 approval lets Codex create a branch, edit scoped code/docs/tests, run tests, commit, push, and open a PR. It does not allow merging.

LEVEL 4 approval lets Codex verify a named PR/diff/tests and merge when clean. It does not allow migrations, production data writes, manual deploys, destructive cleanup, customer sends, public posts, payments, reservations, or farm lifecycle writes unless those actions are separately and explicitly approved.

## Hard Stops

CHARLIE, Codex, Cursor, and all agents must stop before:

- destructive deletes
- production data writes
- Google Sheets writes
- Supabase writes outside approved paths
- migrations
- customer sends
- public posts
- payment/deposit changes
- stock reservations
- pig lifecycle/purpose changes
- `.env` or secret changes
- unclear source of truth
- expanding beyond approved scope
- failed tests that cannot be fixed safely
- touching screenshots, external sources, or static assets unless approved
- building CHARLIE/FRED/ledger/Phase 3A.6 unless explicitly approved

## Agent Hierarchy

- Owner: final decision authority.
- CHARLIE: owner command layer, mission governance, approval tracking, debrief control, and cross-agent overview.
- Codex/Cursor: builders that execute scoped missions under CHARLIE protocol and repo rules.
- Oom Sakkie: farm CEO/operator surface under CHARLIE.
- SAM: meat/sales command surface under CHARLIE.
- FRED: transport/logistics planning under CHARLIE.

Agents may propose, draft, classify, and report. They may not bypass owner approval gates.

## Debrief Requirement

Every completed build mission must report:

- branch
- commit SHA
- PR link
- files changed
- tests run
- pressure-test result
- migration/data-write status
- unsafe-action proof
- Render/live verification plan
- next owner action

The debrief should be sent in chat and, when useful, summarized through CHARLIE Telegram notification.
