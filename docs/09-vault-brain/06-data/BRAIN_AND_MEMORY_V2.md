# Brain And Memory v2

Status: Stage 1 doctrine for owner review.

Purpose: define how CHARLIE remembers useful context without creating hidden truth, duplicating live records, leaking private data, or letting learning silently change behavior.

## Core Doctrine

Vault Brain remains the canonical doctrine layer for identity, roles, workflows, business rules, data rules, standards, and playbooks.

Supabase/runtime records remain operational truth for live state, mission state, approvals, ledgers, events, audit records, agent runs, learning evidence, and owner decisions where migration has been completed.

Brain & Memory v2 does not replace the Vault Brain. It organizes memory around typed, source-linked records so agents can recall the right evidence while Brain Guard can still verify where the truth came from.

## Memory Classes

| Class | Purpose | Storage Owner | Authority | Example Sources |
| --- | --- | --- | --- | --- |
| Doctrine memory | Durable rules, roles, workflows, source-of-truth rules, standards, and business doctrine. | Vault Brain markdown after owner review. | Can guide agent behavior after Brain Guard/owner review. | `docs/09-vault-brain/` |
| Operational truth | Live farm, sales, order, approval, queue, and runtime state. | Supabase/runtime systems where migrated. | Current state for operations. | `charlie_missions`, farm tables, sales tables, order tables. |
| Mission working memory | Bounded context for one mission attempt: stage notes, handoffs, recovery notes, open questions, quality gates. | Mission metadata and normalized CHARLIE Vault tables. | Helps the current mission continue; not global doctrine. | `mission_memory`, `charlie_agent_runs`, `charlie_handoff_reports`. |
| Long-term typed memory | Owner-reviewed durable memory records that are reusable across missions but are not live state. | Future typed memory table or current normalized Vault artifacts until a specific schema is approved. | Advisory until converted into Vault doctrine or runtime code by owner-approved work. | Project lessons, recurring owner preferences, agent improvement notes. |
| Agent lessons | Lessons from failed, corrected, or accepted agent work. | `charlie_lessons`, handoff reports, quality gates, and approved learning proposal rails. | Advisory planning input only until a scoped mission changes doctrine, tests, prompts, or code. | CHARLIE CORE lessons, Oom Sakkie learning-influence proposals. |
| Sales conversation learning | Pattern evidence from sales conversations, not transcript memory. | Append-only sales learning events. | Evidence only; cannot change prompts, sends, prices, orders, reservations, stock, or workflows by itself. | `meat_sales_conversation_learning_events`. |
| Beacon campaign learning | Campaign execution and performance evidence. | Beacon media/campaign/performance records. | Recommendation input only; public posts and spend remain owner-gated. | Beacon manual post and campaign performance events. |
| Farm learning signals | Read-only farm observations, agent dry-run evidence, and advisory learning proposals. | Oom Sakkie append-only review/audit rails. | Advisory only; cannot alter farm records, dispatch agents, or unlock authority. | Oom Sakkie agent learning, learning influence, dispatch design rails. |
| Forbidden memory | Raw customer transcripts, secrets, private media, unapproved personal data, hidden owner decisions, and unsourced claims. | Nowhere in Brain & Memory v2. | Must not be stored as memory. | Full Chatwoot threads, WhatsApp transcripts, tokens, private media. |

## Typed Memory Record Shape

Every long-term typed memory record must be structured enough for Brain Guard to audit:

- `memory_id`: stable id.
- `memory_type`: one of the approved classes or a future owner-approved type.
- `scope`: `charlie`, `charlie_core`, `sam`, `beacon`, `oom_sakkie`, a business environment, or `shared`.
- `source_refs`: docs, table ids, mission ids, PRs, events, tests, or owner decisions that support it.
- `summary`: short factual claim.
- `allowed_use`: how agents may recall it.
- `forbidden_use`: actions it cannot authorize.
- `privacy_class`: `public`, `internal`, `owner_private`, `customer_private`, `farm_sensitive`, or `secret`.
- `authority_state`: `evidence_only`, `owner_reviewed`, `doctrine`, `runtime_enabled`, or `retired`.
- `owner_gate_required`: true when it could influence customer, money, farm, public, legal, migration, deployment, or lifecycle actions.
- `created_by` and `created_at`.
- `reviewed_by` and `reviewed_at` when owner or Brain Guard review has happened.
- `expires_at` or `review_after` when the memory can go stale.

If a record cannot name source references, it is not memory. It is an assumption or draft note.

## Source-Of-Truth Rules

Memory must not outrank source truth. Conflict order remains:

1. Latest direct owner instruction.
2. Supabase/runtime records for live state.
3. Vault Brain after owner review.
4. Active `docs/00-start-here/`.
5. Module-specific active docs.
6. Planning scratchpads and archived docs.

Brain & Memory v2 adds these rules:

- A memory record can point to truth; it cannot become truth just because it is easy to recall.
- Operational state must be recalled from the live source, not copied into long-term memory.
- Mission working memory expires with the mission unless a later owner-reviewed lesson or doctrine update promotes it.
- Agent lessons and sales/campaign/farm learning are evidence until a separate owner-approved mission changes doctrine, code, prompts, tests, or runtime behavior.
- If memory conflicts with Vault Brain or runtime records, agents must say the conflict and use the higher-ranked source.

## Recall Rules

Agents may recall memory only when it is relevant to the current mission, source-linked, within the agent's scope, and allowed by privacy class.

Required recall behavior:

- CHARLIE may recall mission state, owner decisions, cross-agent handoffs, and high-level owner preferences.
- CHARLIE CORE may recall mission working memory, stage artifacts, tests, review evidence, and approved lessons for workflow quality.
- SAM may recall lead facts, approved customer context, campaign source, and sales conversation learning summaries inside sales gates.
- Beacon may recall approved media status, campaign history, performance evidence, demand caps, and public-use gates.
- Oom Sakkie may recall farm state, farm attention, sales context that affects farm operations, and read-only agent learning evidence.
- Future agents may recall only the memory classes named in their agent file, registry entry, and workflow.

Agents must not recall:

- full customer transcripts as memory;
- secrets, tokens, credentials, or private config;
- private media unless the current workflow has explicit permission;
- old mission notes as current truth;
- learning evidence as authority to send, post, reserve, price, pay, migrate, deploy, or change farm records.

## Write Rules

Agents may write memory only through the correct rail:

- Doctrine changes go to the smallest correct Vault Brain file, plus `CHANGELOG.md`, and source-map updates when a new source becomes authoritative.
- Mission working memory goes to mission metadata and normalized Vault/handoff/quality-gate records.
- Runtime operational events go to the approved runtime table for that domain.
- Sales conversation learning goes to append-only learning events with no authority flags.
- Beacon performance and publish evidence go to Beacon evidence rails.
- Oom Sakkie learning influence stays in append-only proposal/review/audit rails.
- Long-term typed memories require a specific approved schema or a current Vault artifact with the typed shape above.

No agent may create a new memory store, table, hidden file, vector index, prompt cache, or transcript archive without owner-approved architecture, privacy review, and Brain Guard update.

## Forget, Retire, And Correct Rules

Memory must be correctable without rewriting history.

- Append-only evidence stays append-only. Correction happens by adding a correction/review event, not mutating the old event.
- Doctrine is corrected by editing the smallest correct Vault Brain file and adding a changelog entry.
- Runtime truth is corrected only through approved operational rails for that domain.
- A stale long-term memory must be marked `retired`, `superseded`, or `needs_review`; agents must not continue using it silently.
- Customer-private data, media, and mission attachments must follow the approved retention/deletion policy when that policy exists. Until then, do not expand storage.
- Forget requests from the owner must identify the target memory class and source record. If the target is append-only audit evidence, record a suppression/retirement event rather than deleting unless an explicit legal/privacy deletion workflow is approved.

## Privacy Boundaries

The system may store summaries, facts, and evidence needed to run approved workflows. It must not turn private conversations into general memory.

Rules:

- Do not store raw customer transcripts as long-term memory.
- Sales learning may store bounded excerpts and structured signals only when the approved append-only rail allows it.
- Customer facts belong in sales/lead/order records, not general agent memory.
- POP/payment evidence remains evidence only until bank-confirmed by approved rails.
- Private media must stay private unless media privacy and owner/public-use gates allow it.
- Farm operational data may be summarized for Oom Sakkie, but farm lifecycle writes remain locked behind approved backend rails.
- Secrets, tokens, environment values, credentials, and private keys are never memory.

## Promotion Path

A memory can influence behavior only by moving through explicit gates:

1. Evidence captured in an approved source.
2. Summary or lesson created with source references.
3. Brain Guard checks source coverage, privacy, conflict order, and update discipline.
4. Owner reviews when the memory could affect customer, money, farm, public, legal, migration, deployment, or lifecycle behavior.
5. A scoped mission updates doctrine, tests, prompts, code, or runtime configuration.
6. Tester/Reviewer evidence proves the behavior change.

Evidence-only memory never skips this path.

## Agent Boundaries

CHARLIE is the owner command identity. CHARLIE can use memory to help Charl see truth, decide, coordinate agents, and review work.

CHARLIE CORE is the workflow system. It can use memory to improve mission execution, evidence, review quality, and recovery, but it cannot convert memory into owner decisions.

SAM is sales-facing. SAM may use stateful lead facts and campaign context, but customer sends, quotes, payment, orders, stock reservations, and final booking remain gated.

Beacon is marketing-facing. Beacon may use media/campaign/performance memory to recommend campaigns, but posting, spend, public copy, and media use remain owner-gated.

Oom Sakkie is farm-command-facing. Oom Sakkie may use farm and learning evidence to summarize and recommend, but cannot change farm records, operate hardware, dispatch agents, or bypass owner gates.

Future agents must declare:

- allowed memory classes;
- forbidden memory classes;
- privacy classes they may access;
- source records they may read;
- write rails they may use;
- owner gates before memory can affect action.

## Stage 1 Non-Goals

This doctrine does not:

- add runtime memory tools;
- apply migrations;
- create new tables;
- change prompts or agent runtime;
- store full customer transcripts;
- authorize automatic learning consumption;
- approve any customer send, public post, payment, stock reservation, farm lifecycle write, migration, merge, or deploy.

## Source References

- `docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md`
- `docs/09-vault-brain/00-governance/BRAIN_GUARD.md`
- `docs/09-vault-brain/00-governance/UPDATE_RULES.md`
- `docs/09-vault-brain/01-identity/CHARLIE.md`
- `docs/09-vault-brain/01-identity/CHARLIE_CORE.md`
- `docs/09-vault-brain/01-identity/SYSTEM_HIERARCHY.md`
- `docs/09-vault-brain/02-agents/sales/SAM.md`
- `docs/09-vault-brain/02-agents/marketing/BEACON.md`
- `docs/09-vault-brain/02-agents/farm/OOM_SAKKIE.md`
- `docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md`
- `docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md`
- `docs/09-vault-brain/04-workflows/BEACON_CAMPAIGN_WORKFLOW.md`
- `docs/09-vault-brain/06-data/CHARLIE_VAULT_TABLES.md`
- `docs/09-vault-brain/08-business-rules/MEAT_SALES_RULES.md`
- `docs/09-vault-brain/08-business-rules/MEDIA_PRIVACY_RULES.md`
