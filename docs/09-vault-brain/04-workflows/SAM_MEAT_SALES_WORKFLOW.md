# SAM Meat Sales Workflow

SAM handles customer conversation and fact capture through Chatwoot/WhatsApp.

SAM must collect facts, respect service-window/template rules, and rely on backend gates for quote, payment, stock, booking, and document actions.

SAM must not invent price, availability, payment confirmation, final booking, slaughter, butcher, or delivery promises.

## Operating Flow

1. Customer responds inbound through Chatwoot/WhatsApp, public/social campaign exposure, existing relationship, or owner manual capture.
2. General SAM greets, acknowledges, uses verified post context, answers a
   verified general question, or asks one natural clarification as needed.
3. Before a meat claim, specialist tool, or consequential preparation, SAM
   explicitly graduates to the meat lane and records structured facts.
4. Backend validates quote-safe facts, price book, service-window state, and document gates.
5. Owner/operator reviews estimated quote, deposit request, carcass reservation, abattoir/butcher slot, final invoice, and delivery release when required.
6. SAM may send or draft wording only when the approved backend gate allows it.
7. Analyst/Oom Sakkie records learning evidence from confusion, objections, missing facts, conversion/loss reason, and follow-up needs.

The general-conversation doctrine has precedence until graduation. Unknown lane
alone is valid and must not cause owner interruption or Telegram escalation.
Conversation ownership (`AUTO_GENERAL`, `AUTO_SPECIALIST`, or `HUMAN`) remains
independent from business lane.

Every Meat reply, quote, invoice, or attachment uses
[`OUTBOUND_DELIVERY_TRUTH_STANDARD.md`](../07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md).
Preparation, attempt claim, Chatwoot acceptance, provider delivery/read,
failure, and ambiguity remain distinct. HTTP or mock success cannot complete a
Meat customer journey or graduate a canary.

## Agentic Conversation Loop

For each inbound message, SAM must:

1. classify the conversation stage;
2. load lead memory, Chatwoot attributes, recent messages, and Beacon/source campaign context;
3. select only the next useful action;
4. draft a human WhatsApp reply;
5. run safety, human-tone, memory, and escalation review;
6. send only when the service window and backend gates allow it;
7. record append-only evidence and learning metadata.

The fallback path must also sound human. LLM timeout must not cause robotic replies or silence when a safe deterministic answer exists.

## Required Facts Before Quote

- customer name and phone/context;
- product interest: half carcass, full carcass, or later custom cut;
- one Set A, Set B, or Set C collection for a half carcass;
- two half-carcass collection choices for a full carcass, which may be the same
  or different;
- delivery address/farm name and useful driver notes;
- town/area and address/location context where relevant;
- timing expectation;
- payment method, currently EFT only;
- freezer size, target packed kg, family size, or match preference when customer gives it;

Public meat sales are delivery-only. SAM must not present collection as an
option because there is no approved collection facility. SAM captures delivery
details and explains that delivery timing is confirmed only after the complete
carcass, payment, processing and delivery-capacity gates pass.
- active price book and VAT-inclusive pricing;
- clear WhatsApp service-window or template state.

Before generating a formal estimated quote, SAM must also have an approved
estimated packed-weight basis. The quote uses R130/kg including VAT and a 50%
estimated deposit, states that the final invoice uses actual packed weight,
and never promises slaughter or delivery timing.

## Hard Gates

- POP evidence never confirms payment.
- Deposit must be confirmed in the bank before slaughter/butcher/delivery gates unlock.
- Final balance must be confirmed in the bank before delivery release.
- Chatwoot labels and attributes must preserve existing conversation state.
- Vague meat-interest phrases should be treated as meat interest and answered with one meat-specific next question, not a generic loop.
- SAM must not use internal rollout words such as `pilot` in customer-facing messages.
- SAM must not sound robotic in customer-facing messages. Use the personality, playbook, and gold-standard examples when crafting live replies.
- New pilot offers use the three collections defined in
  `AMADEUS_MEAT_CUTTING_AND_COMMERCIAL_STANDARD.md`. Set D is historical only.
- A pig cannot move to slaughter booking until the whole carcass is committed
  and all required deposits are bank-confirmed.

## Source References

- `docs/09-vault-brain/04-workflows/SAM_GENERAL_CONVERSATION.md`
- `docs/09-vault-brain/07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md`
- `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md`
- `docs/08-business-modules/SAM_FARM_KNOWLEDGE_PACK.md`
- `docs/04-n8n/CHATWOOT_ATTRIBUTES.md`
- `docs/05-ai/AGENT_ROLES.md`
- `docs/09-vault-brain/02-agents/sales/SAM_MEAT_PERSONALITY.md`
- `docs/09-vault-brain/05-playbooks/SAM_MEAT_HUMAN_SALES_PLAYBOOK.md`
- `docs/09-vault-brain/09-examples/SAM_MEAT_GOLD_STANDARD_REPLIES.md`
- `docs/09-vault-brain/03-business/AMADEUS_MEAT_CUTTING_AND_COMMERCIAL_STANDARD.md`
