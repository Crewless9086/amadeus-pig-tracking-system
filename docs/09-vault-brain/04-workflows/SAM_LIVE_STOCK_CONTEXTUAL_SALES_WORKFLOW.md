# SAM Live Stock Contextual Sales Workflow

Status: supervised owner-draft foundation. No automatic customer or business
authority is granted by this workflow.

## Purpose

Convert a bounded current Chatwoot chronology into a commercially useful,
source-backed livestock recommendation without losing known customer facts or
asking customers to choose categories they have not been shown.

## Interpretation Contract

SAM reads at most 20 bounded conversation messages. The newest customer
message controls the current request. Older customer messages may establish
live-pig context or product family, but may not silently override a newer
quantity, sex, category, timing, location, or transport fact.

Normalization covers ordinary South African English and Afrikaans livestock
language, spelling mistakes, and conservative phonetic forms. Examples include
`varkies`, `speenvarkies`, `wyfies`, `mannetjies`, `beskikbaar`, `prys`,
`pricce`, and the production-shaped `Soggies to bay 10`. Normalization is
deterministic and may not invent a fact that the bounded chronology does not
support.

Commercial intent includes deterministic evidence such as:

- `do you sell`;
- `want to buy`;
- `available` or `availability`;
- `price`, `prys`, `how much`, or `quote`.

Commercial livestock, stock, price, quote, order, or reservation intent blocks
the general-information LLM fallback.

## Customer Fact Model

The interpretation records:

- product family;
- quantity;
- sex;
- selected category, or explicit undecided category state;
- timing;
- location;
- transport expectation;
- smallest missing quote facts;
- one recommended next sales action.

Piglet enquiries without a selected category expose Young Piglets and Weaner
Piglets as options. General live-pig enquiries expose only categories backed
by current eligible HERDMASTER counts and active price evidence.

## HERDMASTER Customer Aggregate

The customer-facing aggregate is read-only and contains:

- customer-facing category;
- current eligible count;
- active effective-dated price range;
- authoritative observation timestamp and freshness;
- sanitized exclusion counts and blockers.

It never contains private `Pig_ID`, tag, pen, medical, reservation, or
customer-note values. Eligibility must come from the exact HERDMASTER animal
eligibility contract and known-unallocated sale purpose. Pricing must come
from configured Supabase `sales_pricing` evidence; code defaults are not
authoritative customer evidence.

Availability older than 24 hours, malformed/naive timestamps, missing current
eligibility, unavailable pricing, inactive pricing, or ineffective pricing
fails closed. SAM may state that it is checking current evidence, but may not
claim stock, count, price, quote, reservation, delivery, or commitment.

## Response Policy

A supervised recommendation must:

1. answer the direct customer question;
2. present only current relevant category options;
3. state verified counts and price ranges without private animal identity;
4. ask only the smallest missing quote facts;
5. offer a quote as a future owner-gated action, never claim one was created.

Conversation 67 must preserve female / quantity 10 / category undecided and
offer verified category choices before a quote. Conversation 2054 must answer
that piglets are sold, present current Young Piglet and Weaner options, then
ask quantity and sex.

## Authority Boundary

This package produces drafts and recommendations only:

- no automatic customer send;
- no quote creation or quote send;
- no intake write;
- no order or reservation;
- no allocation or stock change;
- no ownership or Telegram action;
- no payment, farm, protected, or other business mutation.

Any live recommendation requires a separately authorized owner-reviewed
canary after deployment and read-only shadow verification.

## Deferred Shared Documentation

ROOTLINE owns the shared `NEXT_STEPS.md`, implementation source map, and Vault
changelog during this package. Their reconciliation is deferred rather than
overwritten or partially edited.
