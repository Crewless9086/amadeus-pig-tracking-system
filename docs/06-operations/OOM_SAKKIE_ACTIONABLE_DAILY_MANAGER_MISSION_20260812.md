# Oom Sakkie actionable daily manager mission

Date: 2026-08-12
Owner approval: Charl approved this mission and its product direction.
Target terminal: OOM SAKKIE
Mission owner-visible outcome: one concise, context-aware farm-manager conversation that prioritises work, routes direct questions to the correct specialist, retains the active question context, and provides a usable path to complete every surfaced item.

## Why this mission exists

The underlying manager and specialist evidence is useful, but the current Telegram experience makes Charl interpret internal state and repeated explanations. On 12 August the scheduled `TODAY'S FARM PLAN` asked one grouped mortality observation. Charl answered that the affected penmates were eating, drinking and moving normally. The reply lost the active group context and incorrectly asked for one pig identity. Charl then asked specifically for the irrigation plan; the request fell through to the generic `TODAY'S FARM BRIEF` instead of returning a short ROOTLINE answer.

The daily output also exposed raw sale IDs, repeated long 30/90-day mortality evidence, and described payment follow-up without a direct, human-usable completion path.

These are systemic manager-journey defects, not failures by Charl to phrase replies correctly.

## Existing authoritative foundations to preserve

- `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md`
- `docs/09-vault-brain/02-agents/farm/OOM_SAKKIE.md`
- `docs/09-vault-brain/04-workflows/OOM_SAKKIE_OWNER_ATTENTION_QUEUE_WORKFLOW.md`
- `docs/09-vault-brain/07-standards/OOM_SAKKIE_TELEGRAM_MESSAGE_STANDARD.md`
- `docs/06-operations/OOM_SAKKIE_FARM_MANAGER_ROUND_HANDOVER.md`
- `docs/06-operations/OOM_SAKKIE_LLM_SEMANTIC_FRONT_DOOR_HANDOVER.md`
- `docs/06-operations/OOM_SAKKIE_BREEDING_ROUTING_TASK_RETIREMENT_HANDOVER_20260811.md`
- existing specialist evidence, protected actions, replay suppression, provider identity and owner authority boundaries;
- existing Supabase-backed sales transaction read/update rails, including payment status, method, payment date and sale status;
- existing ROOTLINE, HERDMASTER and sales canonical facts. Oom Sakkie must compose them, not create competing truth.

## Reconciliation with the open PR #828 outcome

The previous OOM SAKKIE terminal remains outcome-bound to a fresh genuine post-deployment breeding-plan request after PR #828. It holds no runtime and was instructed to wait silently. This mission does not discard or duplicate that work.

- Preserve Telegram 3527 as the genuine misrouted-request evidence and Telegram 3528 as immutable generic-brief defect evidence.
- Preserve PR #828's deployed rule that specific breeding-plan requests route to HERDMASTER.
- Treat the next genuine owner-created breeding-plan request as both the outstanding PR #828 proof and this mission's direct-specialist-routing proof when it naturally occurs.
- Do not manufacture, request, resend, replay or poll for a breeding-plan message.
- Do not create a second Oom Sakkie mission lifecycle that competes for the same inbound. Reconcile and extend the deployed shared router and manager lifecycle.

## Product contract

### 1. Distinguish plan, brief and specialist answer

- `TODAY'S FARM PLAN` is the proactive scheduled prioritisation message.
- A broad owner request for a farm overview may return a refreshed farm brief.
- A specific request for irrigation, breeding, sales, welfare or another supported domain must route to that specialist and answer that question first. It must not substitute a generic farm brief.
- If specialist evidence is unavailable, answer concisely with the exact missing evidence, current safe state and next automatic action.

### 2. Progressive disclosure

The scheduled plan must normally contain no more than:

- three `DO TODAY` outcomes;
- three `WATCH` outcomes;
- one grouped question only when owner evidence is genuinely required;
- one short next-reassessment line.

Each item uses a human name and business meaning. Raw IDs appear only when needed for disambiguation or in expanded evidence. Long statistics, provenance and safety rationale move behind `Details`, a follow-up question, or the browser evidence view.

### 3. Retain reply context

An authenticated reply to an active provider-delivered manager question must bind to that question/card/lifecycle before generic semantic intake.

For the 12 August mortality journey, a reply about surviving piglets or penmates is group evidence. It must not demand one pig ID unless the original question genuinely required an individual identity. Partial grouped answers retain proven fields and ask only the smallest material missing fact.

Scheduler messages, later generic briefs and unrelated historical lifecycles must not steal or resurrect the reply.

### 4. Actionable attention items

Every surfaced item must provide or identify its completion path:

- welfare observation -> bind natural grouped evidence or open the governed health path;
- breeding work -> open or invoke HERDMASTER's current plan;
- irrigation -> invoke ROOTLINE and show current plan/execution/hold plus next reassessment;
- sale settlement -> resolve the canonical sale to outlet/customer, amount, sale type and existing payment action;
- missing UI/action -> state that the action is unavailable rather than repeatedly surfacing an unfinishable task.

### 5. Sales and money due

Do not show a bare sale ID as the primary label. Resolve and display outlet/customer, transaction type, due amount, payment state and due date where evidenced.

Reconcile the sales listed on the 12 August plan:

- `SALE-5DB6C593991BCCC7`
- `SALE-D1A9E79BF527C6D2`
- `SALE-AUCT-27B6355EAFEA82F3942B`
- `SALE-8AE513CC55071FA6`

Determine whether each can be completed through the existing `/sales/slaughter` payment update, another current sales surface, or lacks an owner-facing action. Preserve the auction distinction between net settlement payable and payment actually received. Never manufacture receipt.

Provide one unified owner route or exact deep link for recording `Unpaid`, `Deposit_Paid`, `Part_Paid` or `Paid`, with attributable amount, method and date. Protected confirmation and audit rules remain intact. Do not create a second sales ledger.

### 6. Priority must reflect farm value

Rank rather than dump. The plan should make clear why an item matters:

- animal welfare or escalating loss risk;
- cash collection and overdue settlement;
- breeding/farrowing timing and genetic progress;
- irrigation/crop need and power/water constraints;
- routine work that can wait.

Mortality trend detail must not crowd out ordinary actionable farm work unless current attributable evidence shows escalation.

## Required acceptance journeys

Use reviewed fixtures and then fresh production journeys. Do not ask Charl to repeat the already failed 12 August replies merely as a test.

1. A scheduled plan is short, prioritised, human-readable and contains at most one grouped question.
2. A natural grouped reply binds to the active manager question and records/retains group evidence without asking for an irrelevant pig ID.
3. A direct `What is the irrigation plan for today?` request routes to ROOTLINE and produces a concise ROOTLINE answer, not the generic farm brief.
4. `Tell me more` expands only the selected item with evidence and provenance.
5. A sale-attention item uses a human label and opens the correct existing canonical transaction.
6. Charl can mark one genuinely received payment through the owner-facing governed path and the next manager plan no longer reports that settlement as outstanding.
7. Replay, concurrent scheduler activity and delayed provider delivery produce zero duplicate questions, messages, actions or writes.
8. Generic farm briefs remain available for genuinely broad requests.

## Completion boundary

Source changes, tests, CI, review, deployment, message delivery or replay containment are not completion. Business completion requires fresh provider-verified proof of:

- one scheduled concise plan;
- one contextually correct natural reply;
- one direct specialist question answered by that specialist;
- one genuine owner-completed sale-payment journey disappearing from subsequent attention.

If a suitable genuine payment is not yet received, the mission may prove the first three journeys and remain explicitly waiting for payment proof without manufacturing it.

## Safety and scope

- Preserve unrelated work and serialized production ownership.
- No hardware control belongs to this mission.
- No farm, customer, payment or sale write may occur without the existing protected owner action.
- Never infer payment receipt, animal observations or specialist evidence.
- Use names first; retain exact IDs in the audit/evidence layer.
- Do not add another competing daily manager, sales store or routing system.

## Expected business result

Charl receives a short morning plan he can act on in seconds, can answer its question naturally without losing context, can ask a direct specialist question and receive the direct answer, and can close real money-due items through a visible governed path. Oom Sakkie reduces memory and administration instead of repeating evidence back to the owner.
