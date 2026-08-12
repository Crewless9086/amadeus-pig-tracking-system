# SAM Customer Front Door Goal

Status: Active source-only goal  
Production owner: SAM Livestock continuous inbox mission  
Front Door authority: No production or customer-send authority during preparation

## Business outcome

Every new customer receives a warm, useful first response even when the first message is only a greeting, small talk, a public farm question, or an unclear enquiry. The customer never needs to understand Amadeus's internal lanes.

SAM Customer Front Door must:

1. Respond briefly and naturally to greetings and useful small talk.
2. Answer supported public farm facts from the canonical Farm Knowledge.
3. Use conversation, campaign, post, contact, inbox, attachment, and prior-message context before asking a question.
4. Ask at most one natural clarification when intent remains unclear.
5. Retain facts and chronology when handing the same conversation to SAM Livestock or SAM Meat.
6. Route protected commitments, payments, availability, delivery, visits, complaints, and exceptional terms to one precise owner exception.
7. Avoid unnecessary replies to acknowledgement-only or naturally closed turns.

## Current production truth

- SAM Livestock is the only enabled automatic specialist lane.
- General farm and unclear routing contracts exist, but safe AUTO_GENERAL customer dispatch is disabled.
- `config/sam_farm_knowledge.json` contains a draft owner-editable public profile, voice, product menu, selected FAQs, service areas, and blocked-claim rules.
- Existing Farm Knowledge does not by itself prove a continuously operating customer front door.

## Authority boundaries

The Front Door may eventually answer supported public facts and ordinary conversational clarification.

It may not:

- invent price, stock, availability, location, delivery, visit permission, dates, animal facts, welfare claims, payment status, or commercial commitments;
- create quotes, reservations, allocations, orders, payments, customer ownership changes, or farm/stock writes;
- publish, advertise, boost, spend, or invoke protected specialist actions;
- expose internal lane names, governance language, confidence scores, blockers, or system terminology to customers.

## First operational proof

One genuine new customer first contact that is not yet clearly Livestock or Meat must:

1. arrive through the existing authenticated Chatwoot webhook;
2. receive either a supported public-farm answer or one warm intent clarification;
3. preserve conversation context;
4. transfer automatically when later Livestock or Meat intent becomes clear;
5. avoid duplicate replies and protected claims;
6. require no Charl approval unless a genuinely protected decision appears.

## Success measure

One genuine customer progresses from unclear first contact to the correct specialist lane without repeating information, without Charl writing the conversation, and without unsupported or protected claims.
