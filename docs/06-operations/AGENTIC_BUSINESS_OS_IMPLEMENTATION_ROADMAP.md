# Agentic Business Operating System Implementation Roadmap

Status: owner-approved governing implementation program.

Started: 2026-07-19.

## Outcome

Build Amadeus into an evidence-led operating system in which CHARLIE continuously understands the business, specialist agents observe and reason inside their domains, CORE builds and repairs capabilities, Charl approves only genuine high-impact decisions, and every action is verified against a measurable outcome.

This roadmap governs delivery sequencing. The architecture doctrine remains `AGENTIC_OPERATING_SYSTEM_PROGRAM.md`. A phase is not complete because code exists; it is complete only when its acceptance gates pass and its evidence is merged into the authoritative repository.

## Non-negotiable rules

1. Charl is the owner and final authority.
2. CHARLIE is Charl's private digital executive.
3. CORE is the Agentic AI Workflow System used for software delivery and governed capability repair.
4. SAM, Beacon, Herdmaster, Ledger, Oom Sakkie and future specialists own domain reasoning; CORE must not replace them with question-specific code.
5. Production writes, customer sends, public posts, payments, reservations, lifecycle changes, migrations, merges and deployments remain behind explicit authority policies until measured trust graduates that exact capability.
6. Interactive Cursor/Codex work and live CORE work use separate branches and worktrees.
7. `origin/main` is the accepted source; promotion and deployment are explicit, observable events.
8. Evidence Memory may propose change but cannot silently rewrite Doctrine Vault or grant itself authority.
9. No environment-variable rename is a big-bang operation. Aliases, conflict detection, observation and rollback precede retirement.
10. “100% confidence” means every defined gate passed with no known unresolved blocker; it is never a claim that future defects are impossible.

## Phase 0 — Configuration and naming governance

Deliver:

- terminology ADR for Charl, CHARLIE and CORE;
- machine-readable environment ownership contract;
- local, Render, CI, operator and runtime scope classification;
- legacy, ambiguous and proposed-alias register;
- secrets-safe environment audit tool;
- migration, conflict and rollback policy;
- baseline evidence report with names only, never secret values.

Exit gates:

- every current local and Render key is classified or explicitly reported unknown;
- CHARLIE Executive and CORE ownership is unambiguous;
- no `.env` or Render value is changed;
- contract and validator tests pass;
- owner reviews Phase 1 migration matrix before any rename.

## Phase 1 — Safe namespace migration

Introduce canonical `CHARLIE_*` Executive and `CORE_*` workflow namespaces with legacy fallbacks, mismatch blocking, staged local/Render rollout, observation windows and independently tested rollback. Remove old names only in a later reviewed change.

Exit gates: old/new parity, conflict tests, local cold start, hosted canary, no secret exposure, rollback rehearsal and owner-approved retirement list.

## Phase 2 — Concurrent-development and release control

Add a workspace ownership registry, source-map overlap detection, feature-worktree enforcement, mission/file leases, single merge/promotion/deploy coordination, and revision truth across Cursor, CORE, GitHub and Render.

Exit gates: simulated concurrent edits are detected before build; owner `main` is never used as execution space; releases identify source, PR, promoted commit and deployed commit.

## Phase 3 — Unified operational event and business-state system

Create typed, durable, idempotent events and projections for leads, conversations, orders, payments, animals, campaigns, missions, incidents, approvals and outcomes. Define freshness, provenance, replay and privacy rules.

Exit gates: replay produces the same business state; duplicate/late/partial events are safe; authority and audit fields are mandatory; existing sources reconcile without destructive migration.

## Phase 4 — Domain observer loops

Activate bounded observation loops in value order: SAM follow-up and lead health, Ledger reconciliation and cash exceptions, Herdmaster readiness and anomaly detection, Beacon opportunity and performance analysis. Observers may propose but do not silently increase action authority.

Exit gates: scheduled/event-driven operation, freshness and failure telemetry, useful recommendation evidence, false-positive measurement, no unauthorized writes or sends.

## Phase 5 — CHARLIE executive planning loop

Give CHARLIE a durable cross-business world view, goals, KPI gaps, prioritisation, delegation, bounded planning, decision bundling, follow-up and outcome checks. CHARLIE routes software capability work to CORE and operational work to the owning agent.

Exit gates: daily executive cycle, evidence-linked priorities, bounded runway, genuine owner-decision inbox, stale-plan recovery and no invented business truth.

## Phase 6 — Controlled authority graduation

Graduate exact capabilities through observe, draft, owner-approved execution, bounded autonomy and expanded autonomy using measured trust, reversibility, value/risk limits and kill switches.

Exit gates: per-capability trust ledger, minimum sample sizes, rollback/compensation, automatic regression, zero blanket agent authority and immediate owner visibility for red-zone actions.

## Phase 7 — Executive cockpit and outcome system

Unify business health, goals, agent health, missions, decisions, expected value, action history, outcomes, trust, incidents and local/GitHub/Render revision truth in one owner command surface.

Exit gates: one authoritative dashboard and daily brief, source freshness visible, decision/action/outcome traceability, responsive failure states and live owner canary.

## Delivery protocol

Each phase uses: inspect → design → owner hard-stop review where authority changes → isolated build → focused tests → expanded regression → CI → merge → promotion/deployment when applicable → live canary → evidence log → next-phase approval.

No later phase may hide an unresolved foundation defect from an earlier phase. Independent safe work may proceed only when its source, authority and merge ownership do not overlap.

