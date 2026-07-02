# SAM Meat Sales Workflow

SAM handles customer conversation and fact capture through Chatwoot/WhatsApp.

SAM must collect facts, respect service-window/template rules, and rely on backend gates for quote, payment, stock, booking, and document actions.

SAM must not invent price, availability, payment confirmation, final booking, slaughter, butcher, or delivery promises.

## Operating Flow

1. Customer responds inbound through Chatwoot/WhatsApp, public/social campaign exposure, existing relationship, or owner manual capture.
2. SAM identifies the sales lane and records structured facts.
3. SAM asks one useful next question when facts are missing.
4. Backend validates quote-safe facts, price book, service-window state, and document gates.
5. Owner/operator reviews estimated quote, deposit request, carcass reservation, abattoir/butcher slot, final invoice, and delivery release when required.
6. SAM may send or draft wording only when the approved backend gate allows it.
7. Analyst/Oom Sakkie records learning evidence from confusion, objections, missing facts, conversion/loss reason, and follow-up needs.

## Required Facts Before Quote

- customer name and phone/context;
- product interest: half carcass, full carcass, or later custom cut;
- cut set, defaulting to Set A in pilot unless owner overrides;
- delivery or collection;
- town/area and address/location context where relevant;
- timing expectation;
- payment method, currently EFT only;
- budget, target packed kg, or match preference when customer gives it;
- active price book and VAT-inclusive pricing;
- clear WhatsApp service-window or template state.

## Hard Gates

- POP evidence never confirms payment.
- Deposit must be confirmed in the bank before slaughter/butcher/delivery gates unlock.
- Final balance must be confirmed in the bank before delivery release.
- Chatwoot labels and attributes must preserve existing conversation state.
- Vague meat-interest phrases should be treated as meat interest and answered with one meat-specific next question, not a generic loop.
- SAM must not use internal rollout words such as `pilot` in customer-facing messages.

## Source References

- `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md`
- `docs/08-business-modules/SAM_FARM_KNOWLEDGE_PACK.md`
- `docs/04-n8n/CHATWOOT_ATTRIBUTES.md`
- `docs/05-ai/AGENT_ROLES.md`
