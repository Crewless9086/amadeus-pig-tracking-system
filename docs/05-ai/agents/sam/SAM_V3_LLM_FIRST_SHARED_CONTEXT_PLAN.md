# Sam v3 LLM-First Shared Context Runtime

## Purpose

Sam v3 moves Sam Meat away from rule-first customer replies and into an LLM-first sales agent model.

The backend remains the authority gate, but the LLM becomes the primary conversation brain. Code should validate, save facts, block unsafe actions, and provide emergency fallback only. Normal customer wording should come from Sam's LLM context packet.

## Why This Exists

The Sam v2 runtime still used many deterministic customer-facing reply branches. That made Sam feel like a form script and caused repeated symptom fixes for natural customer messages.

The intended farm-agent model is shared knowledge:

- Beacon creates public campaign/post/media context.
- Sam reads that context when a customer replies.
- Butcher uses confirmed demand and reservation state.
- Ledger/Admin uses quote, invoice, deposit, POP, and bank state.
- Atlas reviews conversation evidence and proposes improvements.
- Oom Sakkie gives the owner the final operational view and gates.

Sam must not answer from one isolated WhatsApp line when the system knows the customer came from a Beacon meat post.

## Five-Stage Build

### Build 1 - Shared Campaign Context

Beacon campaign, publish, and post evidence must become readable source context for Sam.

Sam context may include:

- `campaign_id`
- `source_campaign_id`
- post/channel source
- product focus
- sales lane
- campaign/post text
- media context when available
- target area
- call to action

### Build 2 - Sam Context Packet

Every inbound Chatwoot message gets a context packet before the LLM call.

The packet includes:

- current customer message
- recent conversation messages when available
- Chatwoot labels and custom attributes
- active lead facts and latest lead event
- Beacon/source campaign context
- farm knowledge pack
- business rules
- safety gates
- allowed and blocked actions

### Build 3 - LLM-First Sam v3

Sam v3 LLM output becomes the primary source of customer-facing text.

The LLM returns structured JSON:

```json
{
  "intent": "warm_interest",
  "should_reply": true,
  "reply_text": "short customer-facing reply",
  "facts_patch": {},
  "next_action": "soft_qualify_interest",
  "missing_fields": [],
  "confidence": 0.93,
  "risk_flags": []
}
```

### Build 4 - Tool And Action Contract

The backend validates the LLM output and controls what Sam can do.

Allowed:

- update lead facts
- tag/attribute Chatwoot conversation
- ask natural qualifying questions
- record POP as unverified
- suggest quote readiness
- hand off to owner, Butcher, Ledger, or payment gate

Blocked unless a specific backend gate says otherwise:

- invented price
- final availability
- final booking confirmation
- payment confirmation without bank evidence
- stock/carcass reservation
- slaughter, butcher, or delivery booking confirmation
- public posting or paid promotion

### Build 5 - Conversation Replay Stress Tests

Stress testing must replay full human conversations, not only isolated parser cases.

Required examples:

- warm campaign replies such as `Yummy`
- vague interest
- spelling mistakes
- half answers
- shared location/address
- price pressure
- POP/payment proof
- quote request
- rude or frustrated customer
- no-intent fade-out
- Facebook/Instagram/WhatsApp source context

## Completion Standard

Each build must pass focused tests before the next build starts.

Final completion requires:

- Sam v3 policy reports enabled/configured state.
- Context packet includes source campaign fields.
- LLM-first decision can answer warm social campaign replies without deterministic menu text.
- Unsafe LLM output is blocked.
- Full replay stress tests pass with no launch-blocking customer-facing failures.

## Implementation Log

### 2026-06-23 - Builds 1-5 Implemented Locally

Sam v3 is now wired behind `SAM_MEAT_BACKEND_AGENT_V3_ENABLED=1`.

Implemented:

- `modules/sales/sam_shared_context.py` builds the shared context packet from Chatwoot inbound metadata, labels, custom attributes, recent messages, active lead context, Beacon/source campaign context, farm knowledge, business rules, and allowed/blocked actions.
- `modules/sales/sam_meat_runtime.py` now attempts Sam v3 before Sam v2, uses v3 LLM output as the first customer-facing reply when it passes safety validation, and preserves blocked v3 decisions instead of hiding them behind the v2 fallback.
- The backend still blocks unsafe LLM output that invents money amounts, confirms bookings, confirms payment, or confirms slaughter/butcher/delivery timing without the relevant backend gate.
- Replay tests cover warm Beacon-post replies such as `Yummy`, address/context continuation, no-intent fade-out, and unsafe hallucination blocking.

Verification:

- `python -m unittest tests.test_sam_v3_shared_context tests.test_sam_v3_replay_stress tests.test_sam_meat_runtime` passes.
- `python -m unittest tests.test_sam_meat_stress` passes.

Next live check:

- Deploy with `SAM_MEAT_BACKEND_AGENT_V3_ENABLED=1`, `SAM_MEAT_BACKEND_AGENT_V2_ENABLED=0`, `SAM_MEAT_BACKEND_LLM_ENABLED=1`, `SAM_MEAT_BACKEND_LLM_MODEL` set, and `OPENAI_API_KEY` set.
- Run one fresh Chatwoot conversation that starts from a Beacon/Facebook meat post context.
