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

## Authoritative Availability Observation

Animal existence is not commercial availability. A customer-facing count
requires one append-only owner-confirmed cohort observation with:

- an explicit timezone-aware Johannesburg observation instant, normalized to
  UTC;
- a server-derived owner principal and reviewed physical/weighing source;
- an exact cohort digest and privacy-safe per-animal lineage digest;
- category and sex totals;
- explicit exclusion and unresolved counts;
- a reviewed lifetime, initially 24 hours and never more than 48 hours.

The owner preview displays proposed totals, all exclusion reasons, unresolved
rows, observation time, and expiry before confirmation. The cohort observation
does not edit HERDMASTER animals. Known reservations, allocations, medical or
withdrawal holds, sold/moved/dead state, non-sale purpose, incomplete
eligibility evidence, and missing identity/category exclude or withhold rows.
A newer individual observation changes the cohort digest and prevents the old
cohort evidence from authorizing a recommendation.

Request time, database read time, application deployment time, and page-open
time are never availability evidence. Replay of the same owner confirmation is
withheld; a conflicting observation at the same owner/time fails closed.
Malformed, stale, conflicting, incomplete, or unavailable observation evidence
cannot support customer-facing counts or availability.

The observation event is evidence only. The recommendation endpoint separately
revalidates exact account, conversation, contact, inbox, and latest public
inbound identity, rereads current chronology and HERDMASTER state, binds active
pricing, and returns an owner-review card without persisting or sending it.

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

The contextual interpretation is deployed and production-shadowed. The
availability-backed recommendation remains operationally unproven until a
separately authorized owner observation is recorded and the conversation-67
owner-review card is generated without sending.

## Deferred Shared Documentation

ROOTLINE owns the shared `NEXT_STEPS.md`, implementation source map, and Vault
changelog during this package. Their reconciliation is deferred rather than
overwritten or partially edited.
