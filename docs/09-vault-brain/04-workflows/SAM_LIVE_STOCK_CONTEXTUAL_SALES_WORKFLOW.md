# SAM Live Stock Contextual Sales Workflow

Status: owner-approved direction, recorded and queued. Do not begin until the
current WP1 Owner Inbox reconciliation reaches a clean stopping point and the
SAM Live Stock terminal confirms that its exact-file claim is released.

Priority key: `SAM-LIVE-STOCK-CONTEXTUAL-SALES-1`

## Business outcome

SAM Live Stock must understand imperfect customer language in the context of
the complete bounded conversation, ask HERDMASTER for a simple commercial stock
answer, present useful choices, and move the customer toward a quote.

The required result is not merely classification or a safe draft. It is:

1. understand what the customer is trying to buy;
2. extract quantity, sex, category/size, timing and collection/transport facts;
3. identify what is missing;
4. obtain fresh category availability and pricing from authoritative sources;
5. prepare a short, natural response that helps the customer choose;
6. progress to exact-animal matching and an owner-approved quote after the
   customer chooses.

Automatic sending, quoting, reservation, allocation, order creation and stock
mutation remain separately gated.

## Dependency and handoff

This workflow follows, and must not interrupt, WP1 Owner Inbox coverage and
reconciliation.

WP1 production truth recorded on 2026-07-27:

- WP1 merge `20e017392fdd7494c955198279157f2a466e58c9` is deployed.
- The complete open inventory contained 1,694 conversations across 68 pages.
- Only five Owner Inbox projections existed.
- The 100 most recent conversations contained:
  - 0 proven ordinary-reply opportunities;
  - 18 ownership decisions required;
  - 80 already handled;
  - 2 evidence-unavailable conversations.
- Conversation `2031` was correctly classified
  `CUSTOMER_ALREADY_HANDLED`; its prepared draft is retired.
- Conversation `771` remained an ownership/provider-window exception with no
  reply authority.
- Conversation `67` was the first current owner-resolution priority.
- The remaining 1,594 conversations were not yet authoritatively classified.
- Today's weight evidence was not yet reconciled.

WP1 may continue only through its bounded, no-send ownership-exception
reconciliation. It must not be mixed with this contextual-sales build.

Start this workflow only after SAM reports:

- the current WP1 operation has stopped or completed safely;
- no production reconciliation is running;
- no customer send or business mutation is pending;
- its existing implementation claim is released or the new scope is proven
  disjoint;
- exact current main and deployment truth are known.

## Primary production-shaped regression: conversation 67

Context supplied and interpreted by Charl:

Customer:

> Hello! Can I get more info on this?

Prior response:

> Hi Lionel! Happy to share more about Ms. Piggy's piglets. They're strong,
> well cared for, and growing well. What specific info do you want - age, size,
> or something else?

Latest customer message:

> Soggies to bay 10

Charl's authoritative interpretation:

- `soggies` means female pigs in this conversation;
- `bay` means buy;
- quantity is 10;
- lane is live-pig sales, not meat;
- category is undecided;
- the next useful action is to show current female counts and price ranges by
  customer-facing category, then offer a quote.

Expected structured intent:

```text
intent = buy_live_pigs
sex = female
quantity = 10
category = undecided
next_action = present_category_availability_and_price_ranges
```

This interpretation is reviewed evidence for this conversation, not a universal
rule that every use of `sow`, `soggie`, or similar wording means the same thing.

## Required customer response shape

SAM should produce a concise response like:

> Hi Lionel, yes, we do have at least 10 female pigs available. Our current
> recorded females are:
>
> - Young piglets: [count] available, from [price] to [price] each
> - Weaners: [count] available, from [price] to [price] each
> - Growers: [count] available, from [price] to [price] each
> - Finishers: [count] available, from [price] to [price] each
>
> Please let me know which category you would prefer, or whether you would like
> a mixture, and I will prepare a quote for 10 females.

Do not expose internal weight-band rows unless the customer asks. Counts,
prices, fulfilment and freshness must come from current authoritative evidence,
not from this example.

## Work package 2 - Contextual language understanding

- Read the complete bounded conversation context.
- Normalize spelling, phonetic language and ordinary South African/Afrikaans
  livestock wording.
- Treat direct commercial phrases such as "do you sell", "I want to buy",
  "available", "how much" and "price" as purchase evidence when they refer to
  livestock; they must not fall through to a general-information intent.
- Extract product lane, quantity, sex, category/size, timing, location and
  transport facts.
- Preserve alternate interpretations and confidence.
- Ask a clarification only when ambiguity materially changes the answer or
  authority.
- Treat conversation `67` and Charl's correction as a required regression.

### Required production-shaped regression: conversation 2054

Customer:

> Do you sell the piglets

Required interpretation:

```text
intent = buy_live_pigs
product = piglets
message_type = availability_enquiry
quantity = missing
sex = missing
category = young_piglet_or_weaner_not_selected
next_action = present_relevant_options_then_qualify_for_quote
```

This message is not unclear. `missing = none` is invalid because quantity and
sex are not supplied. SAM must answer the direct question, obtain current
customer-facing piglet/weaner availability and price evidence from HERDMASTER,
present useful choices, and ask only for the remaining quote facts.

A generic LLM fallback must never produce the customer recommendation when a
message contains commercial livestock intent, unresolved stock evidence,
required pricing evidence, or a possible quote/order progression.

## Work package 3 - HERDMASTER aggregate availability

HERDMASTER must answer a bounded aggregate question such as:

> How many current sale-eligible female pigs are available in each
> customer-facing category, and what is the active price range?

The response must contain:

- category;
- current eligible count;
- active price range;
- evidence timestamp;
- weight freshness;
- exclusions/holds;
- whether the requested quantity can be fulfilled;
- no private `Pig_ID` or tag information.

Category totals are not exact-animal selection. Exact matching occurs only
after the customer chooses a category or mixture.

## Work package 4 - Commercial dialogue policy

When quantity and sex are known but category is missing:

1. acknowledge the understood request;
2. present relevant available categories;
3. show category totals and price ranges;
4. ask the customer to choose one category or a mixture;
5. offer to prepare a quote.

Do not answer with an unexplained list of internal weights. Do not ask only
"what size?" when the customer has not been told what choices exist.

## Work package 5 - Quote progression

After the customer chooses:

1. refresh weights and eligibility;
2. identify the required number of exact eligible animals;
3. calculate the current total from the active price book;
4. prepare a quote candidate;
5. obtain owner approval;
6. send exactly once through the governed send path;
7. track the opportunity until won, lost, waiting, or deliberately closed.

This document does not authorize any of these protected operations.

## Required acceptance

- Conversation `67` produces the owner-confirmed structured interpretation.
- Conversation `2054` is classified as a piglet purchase/availability enquiry,
  never `unclear` or general information.
- Conversation `2054` reports quantity and sex as missing and offers relevant
  current piglet categories before asking for those facts.
- Commercial livestock enquiries cannot use the general-information LLM
  fallback.
- A HERDMASTER aggregate query returns customer-facing female category totals
  and active price ranges with freshness.
- The response is understandable without internal weight-band knowledge.
- Today's weights are either authoritative or explicitly unavailable; stale
  data cannot become an exact quote.
- Misspellings, phonetic language, mixed Afrikaans/English, quantities,
  ambiguous sow/female wording, and prior-message context have production-shaped
  regression coverage.
- No customer send or business mutation occurs during build/shadow testing.
- Independent review and exact-head CI pass.
- One separately authorized owner-reviewed canary proves the response on a
  current conversation.

## Documentation reconciliation still required

When current shared-file claims are released, reconcile this workflow into:

- `docs/00-start-here/NEXT_STEPS.md`;
- SAM Live Stock doctrine and workflow;
- HERDMASTER doctrine;
- `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md`;
- operating status;
- `docs/09-vault-brain/CHANGELOG.md`.

Until that reconciliation is merged, this dedicated workflow is the preserved
owner-approved plan and does not claim that the capability is built,
deployed, or operational.
