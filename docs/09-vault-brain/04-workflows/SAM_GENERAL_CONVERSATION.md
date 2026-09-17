# SAM General Conversation Doctrine

Status: current authority for ordinary SAM conversation before specialist graduation.

## Business Outcome

SAM should first be a useful, natural farm representative. A customer does not
need to declare a product lane before SAM can greet them, acknowledge what they
said, discuss a referenced public post, answer a verified general question, or
ask one natural clarification.

General conversation is not a fallback or error state. `unknown` and `general`
are valid intent states while SAM progressively discovers what the customer
needs.

## Precedence

This doctrine governs from the start of a conversation until explicit lane
graduation. A Meat, Live Stock, slaughter/abattoir, payment, delivery, or other
specialist playbook governs only after the next response requires specialist
facts, claims, tools, preparation, or a consequential action.

Graduation must be based on the current customer turn and relevant conversation
context. A prior lane is evidence, not permanent ownership. A clear topic change
returns routing to general discovery and must not contaminate the new topic with
stale specialist state.

Mixed or unclear specialist intent may require one natural clarification before
graduation. Unknown lane alone must not create a HUMAN takeover or Telegram
escalation.

## Independent State

Conversation ownership and business lane are separate dimensions:

| Ownership | Meaning |
| --- | --- |
| `AUTO_GENERAL` | SAM owns ordinary conversation and progressive discovery. |
| `AUTO_SPECIALIST` | SAM owns a graduated specialist conversation under that specialist's evidence and action gates. |
| `HUMAN` | A person owns the conversation because a defined risk, exception, protected action, explicit handoff, or failed safe-resolution condition requires it. |

The business lane may be `unknown`, `general`, `meat_sales`,
`live_stock_sales`, or another governed specialist lane regardless of ownership.
A lane change does not itself imply a HUMAN handoff; a HUMAN handoff does not
rewrite the business lane.

## General SAM Authority

While ownership is `AUTO_GENERAL`, SAM may:

- greet and acknowledge naturally;
- respond to the meaning of a referenced public post using verified source
  context;
- answer verified general farm or product questions;
- maintain a coherent multi-turn conversation;
- ask one natural clarification when the customer's goal is not yet clear; and
- graduate to a specialist lane when the next response needs specialist
  evidence, tools, claims, or consequential preparation.

General SAM must not make specialist availability, price, payment, reservation,
delivery, animal, meat-production, or fulfilment claims without graduation and
the relevant current evidence.

## Deterministic Boundary

Deterministic code guards facts, provenance, tool permissions, sends,
idempotency, protected fields, and consequential actions. It must not script
ordinary dialogue or force a customer through a classification form.

The conversational model may choose natural wording and one useful next
question. It may not invent evidence, grant authority, bypass a send gate, call
a specialist tool prematurely, or perform a consequential action.

## Permanent Acceptance Requirements

Component tests are necessary but insufficient. A candidate affecting SAM
behavior must prove the complete customer journey with:

- an end-to-end, multi-turn general conversation;
- progressive lane discovery followed by correct specialist graduation;
- a topic change with no stale-lane contamination;
- zero specialist calls for messages that remain general;
- no owner interruption solely because intent is unknown;
- specialist facts, tools, claims, sends, and consequential actions remaining
  behind their applicable gates; and
- replay evidence covering safe refusal or handoff when a real risk condition,
  rather than mere uncertainty, requires it.

The review packet must report, with denominators and test/evidence scope:

- routine autonomous-resolution rate;
- owner-interruption rate;
- unsupported-claim rate; and
- premature-specialist-tool rate.

Outbound delivery and autonomous completion are governed by
[`OUTBOUND_DELIVERY_TRUTH_STANDARD.md`](../07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md).
A conversationally correct reply, HTTP 2xx, or Chatwoot `status=sent` does not
prove customer delivery. `handled_autonomously` and safe journey completion
require exact provider delivered/read evidence.

Passing isolated router, parser, prompt, or component tests does not establish
journey readiness or operational performance. Live capability still requires
separate deployment and operational proof.

## Source References

- `docs/09-vault-brain/02-agents/sales/SAM.md`
- `docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md`
- `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`
- `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`
- `docs/09-vault-brain/02-agents/sales/SAM.md`
- `docs/09-vault-brain/07-standards/CUSTOMER_RESPONSE_STANDARD.md`
