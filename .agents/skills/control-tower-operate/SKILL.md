---
name: control-tower-operate
description: Operate Amadeus Control Tower across missions, agents, terminals, PRs, releases, commissioning, and owner outcomes. Use when coordinating or reporting multi-lane Amadeus work; do not use as Amadeus runtime architecture.
---

# Operate Control Tower

Remain the top-level interactive parent. Never turn the owner's Control Tower session into a child worker. Delegate bounded implementation or review tasks; keep mission priority, authority, release decisions, acceptance, and owner communication here.

Before acting, read the complete tracked `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md`. Follow its selected active authorities, durable-register, terminal-sweep, Check Receipt, and full-handover requirements. The Vault defines product truth; this skill only governs how Codex conducts the work.

## Conduct

1. Fetch authoritative `origin/main`; record exact current main, local head, ahead/behind, worktree dirt, open PRs, live agents/terminals, and collisions.
2. Reconcile the request into an existing mission and lineage where possible. Log new findings without reprioritizing them unless the owner explicitly does so or the finding unblocks an existing outcome.
3. Define the owner-visible outcome, owner work removed, protected boundary, genuine acceptance journey, replay/rollback evidence, and terminal-independent continuation before dispatch.
4. Keep WIP bounded. Give one writer ownership of a file/lineage at a time; use a different agent for independent exact-head review when risk warrants it.
5. Collect evidence continuously. A commit, PR, green CI, deployment, configuration, heartbeat, or contained failure is technical state, never an owner outcome.
6. Serialize shared-main merges, production migrations, provider actions, and hardware commissioning. Stop on revision, schema, identity, authority, or effect mismatch.
7. Continue automatically at full safe capacity. Do not ask the owner to relay terminal prompts or repeat approvals already covering the exact action.
8. Emit exactly one mutually exclusive owner-status line in each Control Tower handover. If the owner alone blocks progress, use `ACTION REQUIRED NOW: <one exact approval or physical action>`. Otherwise use `OWNER ACTION: NONE` and keep working. Never emit both forms, including a second `ACTION REQUIRED NOW: NONE` line.
9. Update the tracked durable mission register after material transitions. Preserve failed-review findings and superseded lineages instead of hiding them.
10. Before handover, sweep every terminal/agent/PR/worktree/runtime lane and classify it as continue, review hold, release hold, blocked, superseded, or terminal.

## Workspace autonomy and artifact routing

Keep routine development writes inside the approved repository workspace. Before any file write, classify it and route it as follows:

1. **Canonical durable documentation:** use its existing governed repository path and update rules. This includes doctrine, the durable mission register, formal canonical handovers, standards, and Control Tower receipts. Commit it only when the mission authorizes that durable change.
2. **Mission-working evidence:** use `control-tower-artifacts/<mission-or-pr>/`, with stable subdirectories such as `handovers/`, `acceptance/`, and `screenshots/`. Reuse a more specific existing authoritative workspace path when one is already governed. This tree is intentionally untracked.
3. **Disposable runtime/test output:** use `.codex-runtime/missions/<mission-or-pr>/`. Configure test, browser, render, and comparison tools to use this workspace-local path where supported. This tree is intentionally untracked.

Do not use `%TEMP%`, AppData, Desktop, Documents, `C:\\tmp`, or dynamically invented external directories for routine artifacts. Do not repurpose system `TEMP`, `HOME`, or similar environment variables. If a tool unavoidably requires external temporary storage, first try a workspace-local option; otherwise request one narrowly scoped reusable permission with the exact reason. Never request unrestricted filesystem access merely to suppress prompts.

Every child dispatch must provide:

- repository working directory;
- exact mission artifact directory;
- exact disposable runtime directory;
- instruction not to write elsewhere.

Operate autonomously within those workspace paths and the bounded mission. External writes, secrets, protected production actions, customer communication, payments, hardware operation, destructive changes, and ungoverned business-record mutations retain their normal authority boundaries.

## Completion boundary

Do not declare completion until the relevant operational-acceptance skill proves the exact deployed revision, genuine journey, canonical/provider/physical effects as applicable, replay or duplicate safety, and a later terminal-independent cycle. If those are missing, report the exact remaining acceptance gap and continue.

End Control Tower handovers with:

- `Decision: YES | NO | WAIT`
- `Why:`
- `Send to exact terminal:` use `CONTINUE—SEND NOTHING` when already running
- `Expected business result:`
- exactly one owner-status line using the mutually exclusive rule above
