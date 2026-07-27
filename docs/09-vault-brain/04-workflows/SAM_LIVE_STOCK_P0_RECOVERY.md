# SAM Live Stock P0 Recovery

Status: controlling owner direction from 2026-07-27.

Detailed implementation plan:

- `planning/SAM_LIVE_STOCK_P0_OPERATING_RECOVERY_2026-07-27.md`

## Problem

SAM Live Stock is live as a guarded inbound reviewer and exact
owner-approved sender, but the complete sales loop is not operational.

Confirmed production failures include:

- live Chatwoot messages missing from the SAM Owner Inbox;
- persisted queue observations remaining stale after newer inbound/outgoing
  messages;
- missing ownership excluding conversations before owner observation;
- Telegram cards using inconsistent controls and not covering every follow-up;
- broad customer questions receiving form-like clarification instead of useful
  source-backed category, price, and availability guidance;
- no live intake, draft-order, quote, reservation, or deal-progression loop.

## Controlling Outcome

Every livestock inbound must converge on one authoritative owner-work identity
and remain tracked until handled:

`observe -> reconcile -> understand -> remember -> check stock/price -> propose
next action -> owner approve where required -> send once -> verify -> progress
deal -> reconcile handled state`

Chatwoot remains conversation truth. The Owner Inbox is the current owner-work
projection. Telegram is optional notification evidence and can never be the
only place work exists.

## Coverage Rule

The bounded inventory must include:

- HUMAN conversations;
- missing/malformed/unsupported/conflicting ownership as visible
  `OWNERSHIP_DECISION_REQUIRED`;
- automatic-mode conversations only when current policy explicitly requires
  owner attention.

Webhook processing is the fast path. Periodic bounded reconciliation repairs
missed webhooks. Incomplete pagination or identity conflicts fail visibly and
must not publish a partial “all clear.”

## Commercial Response Rule

A customer must not be expected to understand Amadeus Farm’s internal sales
categories before receiving help.

For broad price or availability questions, SAM should present a concise,
source-backed menu from:

- Young Piglets;
- Weaner Piglets;
- Grower Pigs;
- Finisher Pigs;
- Ready-for-slaughter live pigs.

Only fresh eligible category counts and active effective-dated prices may be
used. Unavailable evidence remains unavailable. Internal animal identities
stay private.

For explicit quantity/category requests, SAM preserves known facts, shows the
current available/shortfall position, and asks only the next missing fact.

## Deal Memory Rule

SAM must keep one durable active livestock intake per customer requirement.
Known quantity, category/weight, sex preference, timing, handover, price
evidence, availability, stage, next action, and linked draft/quote identity
must survive later turns.

SAM must not ask for already known facts or create duplicate intakes/drafts.

## Authority Boundary

This P0 does not grant general automatic sending.

- owner-approved exact send remains required;
- intake writing may be enabled only after coverage and idempotency proof;
- draft-order creation requires complete facts, full eligible availability,
  active pricing, and owner-reviewed gates;
- quote sending is separately owner-approved;
- reservation, payment confirmation, stock movement, and final promises remain
  protected and disabled unless separately authorized.

## Confidence Gate

The target is at least 99% timely queue capture over a 100-turn
production-shaped replay, with 100% full-inbox reconciliation during the live
canary and zero silent omissions. Any exception must be visible as unavailable,
stale, ownership-required, specialist, protected, or delivery-uncertain.

Zero duplicate sends and 100% stock/price provenance are mandatory.

## Immediate Regression Identities

- 771: unanswered ownership exception;
- 2031: newer unanswered messages missing from persisted queue;
- 2029: commercially weak broad-price response;
- 2039: handled conversation with stale queue projection;
- 2040: 20-piglet lead without durable intake;
- 2023: handled conversation omitted by missing ownership.

## Source References

- `planning/SAM_LIVE_STOCK_P0_OPERATING_RECOVERY_2026-07-27.md`
- `docs/09-vault-brain/02-agents/sales/SAM.md`
- `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`
- `docs/09-vault-brain/05-playbooks/SAM_LIVE_STOCK_HUMAN_SALES_PLAYBOOK.md`
- `docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md`
- `docs/09-vault-brain/09-examples/SAM_LIVE_STOCK_GOLD_STANDARD_REPLIES.md`

