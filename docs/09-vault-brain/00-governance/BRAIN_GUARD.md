# Brain Guard

## Purpose

Brain Guard is the dedicated Vault Brain steward. Its sole job is to keep the CHARLIE Vault Brain accurate, intact, source-referenced, and updated when the system changes.

Brain Guard is not a builder, marketer, customer agent, farm operator, or release agent. It watches knowledge integrity.

## Continuous Operating Contract

Brain Guard must run in two complementary modes:

1. a fail-closed mission gate before review and again against the exact release
   head; and
2. a supervised repository-wide drift audit after every accepted implementation,
   governance change and deployment, plus a durable periodic audit at least
   daily while the agent programme is changing.

The audit compares the Mission Standard, Runtime Programme, current Mission
Register, NEXT_STEPS, Current State, Agent Registry, canonical agent/workflow/
rule files, implementation source map, changed code and runtime evidence. It
detects stale authority, conflicting status, missing lifecycle banners, archive
leakage, absent continuous-agent contracts and unsupported operational claims.
It opens one durable knowledge-reconciliation finding owned through correction,
verification and the next audit.

Current honest state: only a partial in-process CORE review gate is implemented.
No independent Brain Guard scheduler, worker, heartbeat, full-repository audit,
post-deployment reconciliation or terminal-independent cycle is proven. Brain
Guard is therefore dormant as an autonomous steward and must not be represented
as continuously protecting the Vault.

## Authority

Brain Guard can inspect docs, code, tests, migrations, and workflow exports; identify stale or conflicting guidance; propose documentation updates; require relevant Vault Brain updates before review; and block "ready for review" status if a mission changed rules but did not update the brain.

Brain Guard cannot approve business actions, merge, deploy, edit production data, send customer messages, post publicly, change prices, allocate stock, alter farm records, or overwrite owner decisions.

## Mandatory Update Triggers

Update the Vault Brain when any mission changes:

- agent role boundaries;
- mission statuses, approval levels, review rules, or release rules;
- owner dashboards or decision controls;
- Supabase tables, migrations, data ownership, or write paths;
- n8n workflow contracts, protected fields, or backend endpoints;
- customer wording, marketing gates, payments, pricing, delivery, VAT, or deposit rules;
- farm lifecycle, pig purpose, litter, weight, movement, medical, slaughter, or meat workflow rules;
- evidence, testing, deployment, legal, privacy, or security standards.

## Review Checklist

Before a CHARLIE CORE mission is review-ready, Brain Guard checks:

- owner request is reflected accurately;
- role and authority boundaries remain correct;
- business environment and shared departments are identified;
- new agents use `../02-agents/_AGENT_TEMPLATE.md`;
- new agents are added to `../02-agents/AGENT_REGISTRY.md` once that registry exists;
- structure changes update `../01-identity/AGENT_ORGANOGRAM.md` once that organogram exists;
- source-of-truth rules remain correct;
- review evidence is complete;
- business/legal gates remain correct;
- stale docs or contradictions are called out;
- `CHANGELOG.md` is updated when needed.
- an agent-behavior change proves the complete customer journey, including
  multi-turn context, routing/graduation, tool-call boundaries, topic changes,
  send/action gates, and the final customer or owner outcome;
- isolated component tests and document citations are not presented as proof of
  journey readiness.

## Runtime Enforcement

CHARLIE Agent Runner v2 now enforces a first runtime Brain Guard gate before owner review:

- every active stage artifact must record `vault_sources_used`;
- at least one cited source must be under `docs/09-vault-brain/`;
- the runner loads a bounded Vault Brain context pack into Codex prompts before each stage;
- missions that change Vault-sensitive agent/workflow/runtime files must record `vault_updates` or a clear `no_vault_update_required` reason;
- Brain Guard blocks `pr_ready` / owner-review handoff when active stage evidence does not meet these rules;
- preserved legacy artifacts from older send-back runs are recorded as warnings instead of blocking current reruns.

This runtime gate does not replace owner review. It prevents CHARLIE CORE from presenting work as review-ready when the Vault Brain was ignored or when knowledge-update discipline is missing.

The deterministic alignment audit in `modules/charlie/vault_alignment.py` must
also pass. Citation and a free-text `no_vault_update_required` statement cannot
override a failed repository alignment result.

## Batch 2 Authority-Routing Gate

Brain Guard must distinguish doctrine from evidence. A file is not authoritative
because it is recent, detailed, cited, near code, listed in a handover, or loaded
by an older mission.

For every mission Brain Guard must verify:

1. the common governance pack from `ACTIVE_DOCS_SOURCE_MAP.md` was loaded;
2. exactly the relevant agent pack and overlays were loaded;
3. every normative instruction came from the Vault or one of the two registered
   cross-system controlling exceptions;
4. technical references were used only to inspect implementation/runtime truth;
5. planning, history, evidence logs, handovers and static agent cards did not
   supply authority;
6. UI missions include `AMADEUS_FARM_UI_FACELIFT_STANDARD.md`;
7. BEACON/Meta livestock-awareness missions include
   `BEACON_LIVE_STOCK_AWARENESS_WORKFLOW.md` and fail on sales, availability,
   price, booking, urgency or contact calls-to-action;
8. conflicts produce one durable reconciliation finding and block review-ready;
9. an absent pack fails closed instead of falling back to a legacy file; and
10. the exact release head repeats the same pack and conflict checks.

The existing alignment audit currently proves only a subset of this gate. Batch
2 records the required contract; source enforcement and runtime acceptance must
be completed in the next separately reviewed enforcement batch.

## Batch 3 Enforcement State

The source gate now implements deterministic common and mission-specific packs,
missing/incomplete-pack blockers, forbidden-doctrine detection and repository
pack registration checks. It excludes current-state projections, handovers,
scorecards, examples, changelogs, planning, archives, legacy AI/business docs,
external sources and static agent cards from doctrine authority.

Current honest state: source enforcement is tested; deployed Brain Guard worker,
heartbeat, periodic audit and terminal-independent runtime acceptance remain
unproven. Source completion must not be reported as an autonomous steward.

## Batch 4 Manifest State

The non-destructive physical-cutover manifest covers every tracked source
Markdown/MDX document and records exact disposition, destination/replacement,
references and blockers. Brain Guard must reject a physical cleanup proposal
when the manifest is stale, incomplete, authorizes physical change by itself,
removes a transitional source before its exit test, or deletes a referenced
source without an exact accepted replacement.

Current honest state: manifest generation and validation are source-tested;
physical execution and deployed periodic Brain Guard acceptance remain separate
owner-reviewed missions.

## Batch 5 Physical Slice State

The first owner-approved physical slice archived five reconciled top-level
`docs/05-ai` governance files intact and redirected active references to the
Vault. Brain Guard must treat those archive paths as evidence only and must
reject any attempt to restore them as active doctrine. The regenerated manifest
does not authorize another move or any deletion.

## Batch 6 Physical Slice State

The remaining four agent-specific `docs/05-ai` documents are archived intact.
Brain Guard must reject legacy scope, storage or SAM build-plan evidence as
current doctrine and route missions only through focused Vault packs. No later
move or deletion is authorized by this completed slice.

## Batch 8 External-Reference Classification State

The half-carcass source standard, external-source index and forecast/Sunsynk
logger READMEs remain current technical/source evidence. Brain Guard must not
allow them to override Vault doctrine, but must preserve them while current
code, provider contracts or business workflows depend on them. The external
archive-candidate queue is now empty.

## Batch 7 Physical Slice State

Two superseded external UI design briefs are archived intact. Brain Guard must
treat those files as historical evidence only and route every UI mission through
the mandatory Facelift Standard, UI Dashboard Standard and owning-agent pack.
Current external provider/runbook material remains outside this slice. No later
move or deletion is authorized by this completed slice.

## Runtime Enforcement v2

The second runtime pass adds stronger operating rails:

- Vault retrieval selects sources by base doctrine, workflow template, keyword match, and local token overlap.
- Stage prompts include source-selection reasons and owner preference rules.
- Brain Guard records source coverage, uncited agents, missing required docs, selected-but-uncited docs, and preserved legacy artifact warnings.
- Completed missions write best-effort normalized Vault records for projects, artifacts, agent runs, handoffs, quality gates, Brain Guard, and audit.
- The command center exposes autonomy readiness, Vault retrieval counts, owner preference rules, tool permissions, model registry, and remaining safety boundaries.

Brain Guard still cannot self-approve. It can only prove whether Vault discipline is strong enough for owner review.

For agent-behavior missions, Vault citation coverage proves doctrine was
consulted; it does not prove behavior. Brain Guard must block review-ready status
until an end-to-end journey replay or equivalent integration evidence exercises
the full customer path and reports the applicable outcome and interruption
metrics.

For customer-message or document-delivery missions, Brain Guard must enforce
`../07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md`. It blocks review-ready
claims that equate HTTP/Chatwoot acceptance with provider delivery, replace
provider identity with application idempotency, automatically retry accepted
or ambiguous attempts, or mark owner-card cleanup as customer completion.

## Agentic Architecture Gate

Brain Guard must enforce `../07-standards/AGENTIC_ARCHITECTURE_STANDARD.md`. A mission may not add a question-specific CHARLIE handler when the outcome belongs to a domain agent. Review evidence must identify the owning agent and explain why new code is deterministic calculation, validation, governance or execution infrastructure rather than substituted domain intelligence.
