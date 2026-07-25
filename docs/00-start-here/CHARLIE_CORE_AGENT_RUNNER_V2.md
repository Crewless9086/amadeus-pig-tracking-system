# CHARLIE CORE Agent Runner v2

CHARLIE CORE Agent Runner v2 is the execution model for turning approved CHARLIE missions into owner-reviewable software work. It replaces the old one-shot Codex execution pattern with staged specialist, Planner, Architect, Builder, Tester, QA/Red-Team, and Reviewer agent loops.

## Core Rule

CHARLIE does not launch one large mission prompt and wait blindly. CHARLIE owns the workflow, runs bounded agent stages, records artifacts after each stage, and stops visibly when a stage cannot produce evidence.

## Adaptive Mission Orchestration

New eligible missions receive a versioned orchestration packet before
execution. The mission score selects the **smallest sufficient workflow**, not
the smallest possible workflow. Existing persisted workflows remain frozen;
the compatibility adapter executes valid historical missions without silently
rewriting them. Adaptive orchestration applies only to newly created eligible
missions or to a later, explicitly persisted generation caused by materially
changed evidence.

Every score dimension records a score, evidence, confidence, unknown state and
reason:

- scope size and component/file count;
- architectural complexity, uncertainty and evidence availability;
- reversibility, blast radius and external side effects;
- customer, privacy, authentication/security and financial impact;
- schema/migration, hardware/physical, publication/reputation and production
  configuration impact;
- owner-decision dependency.

Unknown high-consequence evidence raises the tier or blocks. No numerical score
can override a mandatory protected trigger.

| Tier | Intended work | Minimum safe path |
| --- | --- | --- |
| T0 | Read-only inspection, inventory, audit or advice | One capable source/domain agent; no Builder, repository write or external mutation |
| T1 | Small reversible mutation | Builder, Tester and Reviewer with bounded source inspection |
| T2 | Standard bounded feature | Source Mapper or Architect as justified, Builder, Tester and Reviewer |
| T3 | Cross-module or elevated operational work | Relevant architects/specialists, Builder, Tester, QA Red Team and explicit release evidence |
| T4 | Protected/high-consequence work | Full relevant governance, mandatory specialists, owner gates and exact operational proof |

T0 is read-only only. A documentation correction and a code correction are
mutations and therefore require at least T1. UI/reference work mandates design
specialists and Visual QA; security/authentication mandates Security Reviewer;
schema/migration mandates database/evidence review; customer delivery mandates
customer-safety and delivery-truth review; money/payment mandates financial
governance; hardware/irrigation mandates ROOTLINE hardware safety;
publication/campaign/spend mandates the relevant publication governance; and
legal/rights/privacy mandates evidence/security review. These protected
triggers force T4 where they represent protected action and cannot be
score-downgraded.

Each selected agent records why it was selected, whether it is mandatory, its
evidence trigger, required output, authority, tools, allowed mutations,
prohibited actions, time/token/attempt budget and handoff recipient. Skipped
normally expected agents record why they are unnecessary. Authority remains
bounded per mission. Scoring does not authorize deployment, publication,
financial action, customer sends, migrations or hardware control.

After durable artifact ingestion, materially changed risk, scope, uncertainty,
binding, lineage, generation or owner evidence may add a new orchestration
generation. Identical evidence reuses the current generation. Live workflow
expansion may add safety roles but cannot remove existing, active, completed or
mandatory gates. Repository writers remain serialized; only independent
read-only work may run concurrently. Backflow targets the smallest relevant
stage, and per-stage attempts, total recovery cycles, elapsed time and token
budgets remain bounded.

Candidate binding and parent/input artifact lineage remain prerequisites for
protected consumption. Orchestration persistence failure fails closed before a
transition or protected execution. Recovery cannot silently rebuild a
different team without material evidence.

The owner-only mission-summary surface derives throughput from the existing
mission, artifact and execution evidence rather than creating a second ledger.
It exposes tier, selected/skipped counts, overall and per-stage elapsed time,
attempts, backflows, expansion generations, final outcome, owner interventions
and blocked reason. Missing historical values display `Unavailable`, never
zero.

Delivery truth remains explicit: **implemented** means code and tests exist;
**deployed** means the reviewed revision reached the service; **promoted**
means governed CORE runtime, execution and manifest revisions match; and
**naturally proven** means a real governed mission exercised the behavior with
durable evidence. None of those states implies another.

## Agent Stages

- Idea Expander: optional specialist stage for agent/system/workflow/business/content missions; clarifies opportunity, owner value, constraints, and non-goals.
- Product Architect: optional specialist stage for agent/system/workflow/business/content missions; defines user flow, product boundaries, and acceptance shape.
- Planner: scopes the mission, acceptance criteria, test plan, risks, and next handoff.
- Architect: inspects implementation boundaries, source files, route/data contracts, and build approach.
- Builder: applies the scoped implementation and records changed files.
- Tester: runs focused verification and records pass/fail evidence.
- QA/Red-Team: challenges regressions, weak evidence, unsafe actions, missing tests, security/privacy risk, and owner-facing failure modes.
- Reviewer: reviews requirements, diff, tests, safety gates, release notes, and owner recommendation.

## Required Evidence

Each stage must produce a final artifact with structured evidence. CHARLIE records the artifact in the Agent Runner ledger, normalizes it into a `charlie_handoff_report_v1`, and updates Mission Vault workflow status. A stage may not advance silently without an artifact.

Every agent artifact must include:

- summary
- files inspected
- commands run
- stdout/stderr tail where relevant
- next action
- stage-specific evidence

Idea Expander must include opportunity, owner value, and non-goals. Product Architect must include user flow, acceptance boundaries, and risk notes. Planner must include acceptance criteria and test plan. Architect must include files to inspect, risks, and implementation plan. Builder must include changed files and build notes. Tester must include tests run and pass/fail status. QA/Red-Team must include QA findings, red-team status, and risk rating. Reviewer must include release notes, QA evidence, and recommended owner decision.

## Quality Gates

CHARLIE checks each artifact before advancing. The Tester gate requires `test_status = pass` and no reported errors/bugs. The QA/Red-Team gate requires `red_team_status = pass`, no reported errors/bugs, and no high/critical risk rating. The Reviewer gate requires `recommended_owner_decision = approve_final_release`, QA evidence, and no reported errors/bugs. Missing command/file evidence blocks the mission instead of creating a weak review packet.

Validation missions must include PR evidence before owner review.

## Backflow

Tester failure sends the workflow back to Builder. Reviewer rejection or findings send the workflow back to Builder unless the Reviewer artifact names a different valid `send_back_stage`. Backflow is bounded by a retry limit so the mission cannot loop forever. Backflow events are recorded in the Agent Runner ledger and the owner review packet.

**Cross-session loop cap (Stage 1 reliability fix).** The per-run ledger backflow counter resets every runner session, so before this fix a repeated blocker could loop across restarts and churn overnight without ever landing. The hard-loop cap is now **mission-durable**: each backflow stamps its blocker fingerprint into durable mission memory, and the loop detector counts prior occurrences across all previous sessions (`_durable_backflow_fingerprint_count`). A blocker that repeats across sessions converts to an honest owner-review block with a recovery packet instead of an infinite retry.

**Bounded discovery and mission families.** Exact-text fingerprints are not the only limit. CORE also groups findings into semantic families and applies a mission-wide correction budget. In-scope acceptance failures return to Builder while budget remains. New non-red hardening or adjacent work after the budget becomes a deduplicated child mission awaiting owner approval. Pre-existing failures that reproduce on `main` and broad-suite advisory timeouts do not fail the parent. Red-zone findings always stop for owner review.

Parent decomposition is finalized with a compare-and-set update: the parent may enter `paused/waiting_children` only when the complete non-empty child ID set is stored in the same parent update. Child IDs are deterministic, child records point back to the parent, and the executive reconciler repairs a legacy or interrupted parent list from those authoritative child records before attempting family completion.

The acceptance matrix is frozen before Builder and updated by Tester/QA evidence. This gives the parent a finite completion boundary while preserving every actionable discovery.

## Dashboard Visibility

The local runner heartbeat exposes:

- Agent Runner version
- current agent
- current action
- current final artifact path
- agent ledger path
- latest stage summary
- recent commands/files/output tails
- elapsed/progress details where available

The CHARLIE dashboard surfaces these fields in the Local Runner panel.

Mission Control also separates acceptance completion from workflow position. It shows matrix rows, fixes completed, review runs, backflow budget, cycling warnings, and linked child missions so productive hardening is not mistaken for a frozen percentage.

The dashboard also exposes a CHARLIE CORE Command Center with queue counts, review/blocked state, release state, deployed/merged state, live verification configuration, Vault version, and current runner boundary.

`merged` and `deployed` are delivery states, not proof that the requested business capability is operational. CHARLIE evaluates terminal missions against their remaining operational gates. When a protected operation or live verification remains, it records durable unfinished business, creates a deterministic linked follow-up in `new` state, and sends a plain-language executive brief. The follow-up is never silently approved, and protected operations remain owner-gated.

## Mission Vault v1

The current runtime remains backward compatible with `charlie_missions.metadata_json`. The structured Vault v1 schema is available through `supabase/migrations/202606300002_create_charlie_vault_v1_tables.sql` and defines:

- `charlie_vault_projects`
- `charlie_vault_artifacts`
- `charlie_agent_runs`
- `charlie_handoff_reports`
- `charlie_quality_gates`
- `charlie_owner_decisions`
- `charlie_deployments`
- `charlie_audit_log`

## Blocked Behavior

If an agent does not produce a valid final artifact, CHARLIE records a blocked review packet with:

- blocked agent
- blocked reason
- changed files
- execution ledger path
- stdout/stderr excerpts when available

This prevents silent stuck missions.

## Owner Review

When all stages complete, CHARLIE creates a review packet and moves the mission to `pr_ready`. Owner review remains mandatory before release. Send-back comments rerun from the chosen workflow stage and downstream stages.

When owner review sends a mission back to a stage, upstream artifacts are preserved and only the selected stage plus downstream stages rerun. This keeps good planning/architecture evidence intact while still forcing new Builder/Tester/Reviewer evidence.

**Cross-session evidence recovery (Stage 1 reliability fix).** When a mission resumes in a new runner session, upstream artifacts are recovered not only from the review packet and vault handoff reports but also from **durable mission memory** (`latest_by_agent`). Before this fix, a resumed downstream agent (e.g. QA/Red-Team) could be handed an empty `previous_agent_artifacts` and correctly refuse to certify implementation it could not see — re-blocking work that had already passed in an earlier session. Recovered artifacts are additive and never overwrite evidence already present for the run.

## Release

Final approval moves the mission to release handling. The release bridge remains separate from the build agents and may merge a referenced PR only after owner final approval and release evidence are present. After merge, the release bridge watches the configured live URL for a bounded verification window and marks the mission `deployed` only if live verification succeeds. Otherwise it records the merge and deploy-watch evidence for follow-up.

Live verification URL priority:

1. `CHARLIE_RELEASE_VERIFY_URL`
2. `AMADEUS_BACKEND_URL` + `/charlie`
3. `RENDER_EXTERNAL_URL` + `/charlie`
4. `RENDER_EXTERNAL_HOSTNAME` + `/charlie`

If no URL is configured, the mission may become `merged`, but it cannot become `deployed`.

## Extended Architecture Alignment

CHARLIE Agent Runner v2 is the working spine for the larger CHARLIE CORE operating-system plan. The next architecture should extend this runner instead of replacing it immediately.

Recommended order:

1. Configure live release verification so merged missions can become deployed.
2. Normalize the Mission Vault into structured Postgres tables for projects, agent runs, artifacts, decisions, risks, tests, reviews, approvals, deployments, cost logs, and audit logs.
3. Standardize every stage artifact into one reusable handoff report contract.
4. Add optional specialist stages by mission type: Idea Expander, Product Architect, Technical Architect, Security Reviewer, Publisher, and Monitoring.
5. Add model registry and tool permission layers before broad MCP/model routing.
6. Evaluate Temporal, OpenAI Agents SDK, and LangGraph only after repeated long-running missions show the local runner needs durable distributed orchestration.

Current best fit:

- Keep the Python runner, Supabase mission records, GitHub PRs, Telegram notifications, and Flask dashboard as CHARLIE CORE v2.
- Use Postgres/Supabase as the canonical vault before adding external vector/file-search layers.
- Use GitHub as code truth and owner-reviewed PRs as release gates.
- Treat provider/model names as configurable registry entries, not hardcoded architecture.
