# CHARLIE Mission Workflow

1. Owner creates or approves a mission.
2. CHARLIE normalizes it into a mission contract.
3. Local runner picks up approved mission.
4. Runner loads relevant Vault Brain context into each stage prompt.
5. Planner, Architect, Builder, Tester, QA Red Team, and Reviewer stages run.
6. Brain Guard checks Vault citations and update discipline.
7. Reviewer prepares owner review packet only after Brain Guard passes.
8. Mission stops at owner review.
9. Owner approves final release, sends back, pauses, rejects, or marks done.

## Mission Contract

Every mission must resolve to:

- mission id;
- raw owner request;
- title;
- urgency;
- mission type;
- selected agent team;
- reason each selected agent is needed;
- approval level;
- allowed scope;
- forbidden scope;
- hard stops;
- acceptance criteria;
- tests and pressure tests;
- rollback/recovery plan;
- owner decisions needed;
- review/debrief packet.

CHARLIE CORE must not run every agent for every mission. Intake must classify the mission and select the smallest capable agent team. UI missions use the UI council. Income-stream missions use business, risk, and evidence agents. Simple bugfixes should not wait on business or marketing agents unless the bug touches those areas.

For UI missions, the selected team must include Visual Reference Interpreter, Creative UI Designer, UX Interaction Designer, Frontend Design Implementer, and Visual QA Reviewer when screenshots, dashboard redesigns, approval flows, command centers, or visual references are involved.

## Stage Evidence

Each stage must produce structured evidence:

- Planner: scope, acceptance criteria, test plan, risks.
- Architect: source of truth, files/contracts, implementation approach.
- Builder: changes made and changed files.
- Tester: exact tests and pass/fail evidence.
- QA/Red-Team: regression/security/privacy/UX/evidence challenge.
- Reviewer: owner review packet and recommended decision.
- All stages: `vault_sources_used`, commands/files inspected, and either Vault updates or a no-update reason when relevant.

Missing artifacts block progress. Tester failure returns to Builder. Reviewer send-back returns to the named stage and preserves prior artifacts.

## Provider Routing

CHARLIE CORE may route selected specialist/review stages through Claude/Anthropic when `ANTHROPIC_API_KEY` is configured. The temporary typo alias `ANTROPIC_API_KEY` is also accepted so a configured owner environment does not fail closed for spelling alone.

Claude routing is active only for review/specialist reasoning stages such as Council Synthesis, Risk Agent, QA Red Team, Product Reviewer, Business Reviewer, Security Reviewer, and Evidence Reviewer. Builder and Tester remain local runner stages until Claude tool execution has a separate owner-reviewed safety design.

## Vault Enforcement

CHARLIE CORE missions are not allowed to be treated as review-ready unless the active stage artifacts prove Vault Brain usage.

The runner checks:

- stage artifacts cite `docs/09-vault-brain/` sources;
- the mission has a Mission Vault payload;
- retrieved Vault sources have source-selection reasons and source coverage evidence;
- Vault-sensitive changes to CHARLIE runtime, agent docs, or workflow docs include `vault_updates` or `no_vault_update_required`;
- preserved upstream artifacts from old send-back runs are visible as warnings, not silent truth.

If these checks fail, Brain Guard blocks owner review and the mission remains blocked until the responsible stage fixes the evidence or updates the Vault.

## Autonomy Boundary

CHARLIE CORE can run supervised missions with stronger memory, retrieval, tests, and evidence than before. It must still stop for owner review before release, money, customer contact, public posting, migrations, stock reservations, or farm lifecycle writes.

The target is to outperform a single assistant on repeatability, memory, evidence, queue discipline, and overnight throughput. It is not allowed to outperform the owner gate by bypassing it.

## Owner Approval Inbox

CHARLIE may show a unified Owner Approval Inbox for exact agent-prepared operational suggestions from Beacon, SAM Live Stock, SAM Meat, Butcher, and Herdmaster.

The inbox is an owner-review surface only. It may record `approve`, `edit`, `reject`, `pause`, and `send_back` decisions against a normalized item attached to the Mission Vault, but that recorded decision does not itself send a customer message, post publicly, create an order, quote, invoice, payment confirmation, stock reservation, butcher/slaughter booking, migration, or farm lifecycle write.

Every inbox item must identify its source agent, source type, exact proposed action or text, next gate, forbidden actions or risk flags when known, owning mission id, and current decision state. Domain-specific execution remains with the existing approved send/post/money/stock/butcher/farm gates after exact owner approval is recorded.

## Approval Levels

- `LEVEL 0`: report only.
- `LEVEL 1`: read-only investigation/planning.
- `LEVEL 2`: docs/planning edits.
- `LEVEL 3`: code/test/PR handoff; no merge.
- `LEVEL 4`: release/merge handoff after final owner approval.
- `LEVEL 5`: red-zone work requiring exact explicit confirmation.

## Runner Truth

Telegram and `/charlie` record mission authority, but they do not execute shell commands directly. A local runner/Codex process must pick up and execute approved work.

If an agent subprocess times out or crashes, CHARLIE must convert the failure into a blocked review packet with stdout/stderr excerpts, return code, changed files, and recovery guidance. A timed-out runner must not leave a mission silently stuck in `in_progress`.

When a runner result moves a mission to `pr_ready`, the review-ready notification must key off the mission status rather than a narrow internal status string.

`planning/CODEX_CHAT.md` is the laptop-friendly active scratchpad. Supabase mission records are the durable queue. The Vault Brain is the doctrine layer that tells agents what rules and context to follow.

## Source References

- `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`
- `docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md`
- `docs/06-operations/CHARLIE_BUILD_RELAY_PLAN.md`
- `planning/CHARLIE_CORE_EXTENDED_PLAN.md`
- `docs/09-vault-brain/00-governance/BRAIN_GUARD.md`
