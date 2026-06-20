# Sam Farm Knowledge Pack

## Purpose

Sam needs farm context and personality without making unsafe promises.

Editable knowledge lives in:

`config/sam_farm_knowledge.json`

The backend reads this file when Sam builds replies. This lets the owner improve Sam's public farm story, tone, product menu, service areas, and FAQ wording without changing Python code.

## What Belongs Here

- Farm story and background.
- Short public intro for Sam.
- Service area wording.
- Google Maps public link.
- General product menu wording.
- Cut set explanations.
- Deposit and POP explanation wording.
- FAQ wording.
- Tone and personality rules.
- Things Sam must never claim.

## What Must Not Belong Here

- Actual live stock availability.
- Bank account secrets.
- Exact confirmed slaughter, butcher, delivery, or collection dates.
- Confirmed payment state.
- Final prices unless they are also controlled by the backend price book.
- Anything that lets Sam bypass backend gates.

## Safety Split

The knowledge pack can shape conversation.

The backend still controls:

- price book,
- quote-safe rules,
- document sends,
- WhatsApp window rules,
- POP versus money-in-bank,
- carcass reservations,
- slaughter/butcher/delivery gates,
- final invoice and delivery release.

## Sam LLM Agent V2

Sam can run as an LLM-first conversation agent when:

- `SAM_MEAT_BACKEND_AGENT_V2_ENABLED=1`
- `SAM_MEAT_BACKEND_LLM_MODEL` is set
- `OPENAI_API_KEY` is set

In this mode the LLM may propose:

- a short customer reply,
- a structured fact patch,
- missing fields,
- confidence,
- whether Sam should reply at all.

The LLM does not get final authority. The backend validates the output before it is used and blocks unsafe wording such as invented prices, final booking claims, payment-confirmed claims, or confirmed slaughter/butcher/delivery promises.

Customer-facing Sam wording must not use internal rollout terms such as `pilot`.

## How To Check It

After deploy, open:

`/api/sales/sam-farm-knowledge`

Expected result:

- `status = ok`
- `configured = true`
- `knowledge.public_profile.farm_name = Amadeus Farm`

## Current Editing Rule

Edit `config/sam_farm_knowledge.json`, commit, and deploy.

Later build: add a Farm App editor so approved owner edits can update the knowledge pack through the UI.
