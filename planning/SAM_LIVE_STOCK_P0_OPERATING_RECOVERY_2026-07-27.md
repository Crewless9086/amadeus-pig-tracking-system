# SAM Live Stock P0 Operating Recovery

Date: 2026-07-27

Owner priority: P0 - live customers are being missed.

Status: approved planning brief; implementation still requires reviewed code,
tests, deployment, and bounded production canaries.

## Outcome Required Today

SAM Live Stock must operate as one supervised sales loop:

`Chatwoot inbound -> guaranteed observation -> authoritative owner queue ->
conversation memory -> current stock/price evidence -> useful response or
owner decision -> exact send -> delivery proof -> tracked sales next action ->
handled-state reconciliation`

The owner must have one dependable place to see all livestock work requiring
attention. Chatwoot remains the conversation system of record. The SAM Owner
Inbox becomes the authoritative work projection and must never silently omit a
conversation because ownership, review, Telegram delivery, or another optional
field is missing.

## What 99% Confidence Means

“99% confidence” is an operating target proven by evidence, not a promise that
software cannot fail.

The recovery is acceptable only when:

- 100% of open conversations in the configured livestock inbox reconcile
  against Chatwoot during the production canary;
- at least 99% of eligible inbound events appear in the Owner Inbox within two
  minutes across a production-shaped replay of at least 100 turns;
- the remaining at most 1% are explicit, visible `unavailable` exceptions,
  never silent omissions;
- zero duplicate customer sends occur;
- 100% of price, category, quantity, and availability claims used in customer
  drafts carry current backend provenance;
- zero unavailable stock/price values are converted to zero or invented;
- every actionable conversation has exactly one current projection, one clear
  next action, and a freshness timestamp;
- every send is bound to the exact latest inbound, draft hash, review,
  conversation identity, and provider window;
- every accepted send reaches a provider-confirmed state or a visible delivery
  exception without automatic retry;
- handled conversations leave the actionable queue on the next reconciliation;
- queue/API/browser tests, exact-head CI, post-merge CI, deployment health, and
  bounded live canaries all pass.

## Evidence From The Live Failure

Read-only production audit at 2026-07-27 09:13-09:18 SAST:

| Conversation | Current evidence | Failure |
|---|---|---|
| 771 | One unanswered inbound, open WhatsApp window | Missing ownership excluded it before Owner Inbox observation. Telegram card delivery outcome is unknown. |
| 2031 | Two unanswered inbounds; customer wants 10 pigs in two weeks; current review exists | Owner Inbox contains an older observation and did not reconcile the new inbound. |
| 2029 | Customer asked for price | Reply asked the customer to understand internal categories instead of presenting a useful verified offer menu. |
| 2039 | Later outgoing reply exists | Owner Inbox projection is stale. |
| 2040 | Customer wants 20 piglets; later outgoing exists | Missing ownership prevented Owner Inbox coverage; no durable intake or quote path was created. |
| 2023 | Later outgoing reply exists | Missing ownership prevented Owner Inbox coverage. |

Current production policy confirms:

- automatic replies: disabled;
- intake writing: disabled;
- draft-order creation: disabled;
- quote creation: false;
- order creation: false;
- exact owner-approved send: enabled;
- LLM review/drafting: enabled;
- Telegram new-lead/owner-review notification: enabled.

Therefore SAM is currently a guarded reply assistant, not a complete livestock
sales agent.

## Non-Negotiable Design Decisions

1. Chatwoot is the conversation source of truth.
2. The Owner Inbox is a projection of every owner-relevant livestock
   conversation, not a HUMAN-only audit and not a Telegram mirror.
3. Missing, malformed, unsupported, or conflicting ownership must create a
   visible ownership-decision item.
4. Telegram is an optional notification surface. Telegram failure must never
   remove work from the Owner Inbox.
5. Webhook observation is the fast path; bounded periodic reconciliation is the
   repair path. Both must be idempotent.
6. Every inbound message invalidates the prior projection and draft.
7. Broad buying questions receive guided selling information, not a bare form
   question.
8. Customer-facing availability uses category-level eligible counts and
   approved price evidence. Internal Pig_ID lists remain private.
9. Unknown or stale stock/price evidence produces a clear owner-visible
   exception, not a fabricated offer.
10. Sales intake memory persists known facts across turns so SAM does not ask
    for the same information again.
11. Draft order and quote preparation are owner-gated business operations.
    Reservation, payment confirmation, and final stock promises remain separate
    protected actions.
12. No automatic customer sending is introduced by this P0. Exact owner
    approval remains required while quality is proven.

## Work Package 0 - Freeze And Baseline

Purpose: prevent another moving-target repair.

Actions:

- record exact `origin/main`, deployed Render revision, current env policy, and
  migration state;
- capture a metadata-safe inventory of all open conversations in the configured
  inbox;
- record current Owner Inbox projection, latest review, Telegram lifecycle,
  and chronology identity for each;
- preserve the six reported conversations as regression fixtures;
- confirm no existing active claim overlaps the implementation files;
- create one bounded branch and claim.

Acceptance:

- exact live baseline is reproducible;
- no production write occurs;
- no customer content enters fixtures beyond owner-approved sanitized examples.

## Work Package 1 - Guaranteed Conversation Coverage

Purpose: no live inbound may disappear silently.

Implementation:

- create one bounded owner-attention inventory reader for the exact Chatwoot
  account and livestock inbox;
- include HUMAN conversations and ownership exceptions;
- include valid automatic-mode conversations only when current owner-attention
  policy requires it;
- reconcile on every inbound webhook after the SAM review is recorded;
- add a bounded periodic read-only reconciliation job or existing approved
  scheduler hook to repair missed webhooks;
- paginate deterministically and fail the whole run closed if inventory
  coverage is incomplete;
- persist one append-only observation per chronology/ownership/review/window
  hash;
- project exactly one latest state per work item;
- store no customer content in the work-event table.

Required states:

- `WAITING_FOR_OWNER_REPLY`;
- `OWNERSHIP_DECISION_REQUIRED`;
- `SPECIALIST_REVIEW_REQUIRED`;
- `PROTECTED_ACTION_REQUIRED`;
- `CUSTOMER_ALREADY_HANDLED`;
- `CUSTOMER_REPLY_PROHIBITED`;
- `IDENTITY_OR_EVIDENCE_UNAVAILABLE`;
- `STALE`.

Acceptance:

- conversations 771 and 2031 appear correctly after read-only revalidation;
- 2029, 2039, 2040, and 2023 project as handled if chronology remains
  unchanged;
- missing ownership is visible;
- newer inbound updates the existing work item;
- handled chronology removes actionable status;
- replay creates zero duplicate events;
- notification failure cannot prevent persistence.

## Work Package 2 - One Authoritative Owner Inbox

Purpose: Charl should not hunt across Dashboard, Telegram, and Chatwoot.

The Owner Inbox must show:

- customer/conversation identity and direct Chatwoot link;
- latest inbound time and unanswered count;
- current/stale review state;
- conversation stage;
- known customer requirement;
- missing facts;
- current category-level eligible availability;
- active pricing evidence and freshness;
- recommended next action;
- exact editable draft;
- provider-window state and expiry;
- Telegram notification state as informational evidence;
- send eligibility and withholding reason;
- delivery result;
- durable intake/draft-order/quote state when present.

Controls:

- refresh/reconcile read-only;
- resolve missing ownership;
- edit draft;
- approve exact draft;
- send once;
- no-reply/handled;
- keep with owner;
- prepare intake;
- prepare draft order/quote when gates pass.

All controls must be server-derived and revalidated. UI state cannot grant
authority.

Acceptance:

- the page renders current evidence, not yesterday’s projection;
- a new inbound visibly invalidates the old draft;
- every disabled button explains why;
- Telegram and Dashboard show the same current work identity;
- no mutation occurs from merely selecting, typing, refreshing, or opening.

## Work Package 3 - Commercially Useful Guided Selling

Purpose: stop treating buyers as if they already know the farm’s internal
categories.

For a broad question such as “How much for a pig?” SAM must prepare a bounded
offer menu using current evidence:

- Young Piglets;
- Weaner Piglets;
- Grower Pigs;
- Finisher Pigs;
- Ready-for-slaughter live pigs.

For each category, include only what is currently supported:

- approved weight band;
- active unit price or price basis;
- current eligible count or `availability being confirmed`;
- normal Riversdale/Albertinia handover posture.

Then ask one useful choice question.

Rules:

- category counts come from Herdmaster/Pig Allocation eligibility, not total
  pigs;
- price comes from active effective-dated `public.sales_pricing`;
- no internal Pig_ID is exposed;
- partial stock is offered as an option, not promised;
- missing evidence remains unavailable;
- broad information replies do not require a formal order;
- explicit quantity/category requests immediately show the available/shortfall
  position before asking the next missing fact.

Required regression cases:

- 2029: broad price question receives a verified category menu;
- 2040: 20 piglets preserves quantity/category, shows eligible availability,
  and asks only missing weight/sex/timing/location facts;
- 2031: 10 pigs in two weeks preserves quantity/timing and asks category/weight,
  sex preference, and handover choice—not “how will you use them?”;
- Afrikaans/English misspellings and brief replies preserve conversation
  context;
- an unavailable price or stale stock blocks the claim visibly.

## Work Package 4 - Durable Sales Memory And Deal Progress

Purpose: move from isolated replies to a tracked opportunity.

Persist or update one canonical livestock intake per active requirement:

- conversation/contact identity;
- category/weight;
- quantity;
- sex preference;
- timing;
- collection/handover choice;
- delivery request if customer initiated it;
- price evidence/version;
- availability observation;
- current stage;
- next action;
- linked draft order/quote identity;
- owner corrections.

Stages:

- `new_interest`;
- `qualifying`;
- `availability_check`;
- `price_ready`;
- `draft_order_ready`;
- `quote_review`;
- `waiting_for_customer`;
- `owner_action_required`;
- `closed_won`;
- `closed_lost`;
- `stale`.

Rules:

- reuse an existing active intake/draft order;
- never create duplicate drafts for the same active requirement;
- do not lose facts between turns;
- do not ask already answered questions;
- owner-approved correction outranks inferred facts;
- no reservation or promise before the protected reservation action succeeds.

Acceptance:

- 2040 becomes a visible 20-piglet opportunity;
- 2031 becomes a visible 10-pig/two-week opportunity;
- each has a next action and remains visible until resolved;
- replay/new message updates rather than duplicates the opportunity.

## Work Package 5 - Telegram As Reliable Notification, Not Authority

Purpose: make Telegram useful without making it the system of record.

Changes:

- one current Telegram card per current work identity;
- edit/supersede the card when chronology changes;
- safe reviewed drafts show `Approve Send`;
- unsafe or incomplete work clearly shows the blocker;
- new-lead cards may show approval only when an exact reviewed send action
  exists;
- card delivery failure/unknown becomes a visible Owner Inbox exception;
- bounded delivery verification;
- no automatic retry on ambiguous Telegram or customer-send outcomes;
- handled work marks/deletes the exact card according to reviewed cleanup
  policy.

Acceptance:

- every current actionable work item has either a confirmed Telegram
  notification or a visible notification exception;
- missing Telegram does not hide the work;
- Telegram and Owner Inbox actions bind the same draft/action identity;
- no duplicate cards or sends under replay.

## Work Package 6 - Owner-Gated Draft Order And Quote

Purpose: let SAM progress qualified leads toward a deal.

Sequence:

1. Enable durable intake writing only after Work Packages 1-5 pass.
2. Run one bounded intake canary on a revalidated real conversation.
3. Enable draft-order preparation/creation only when all required facts,
   pricing, and full availability gates pass.
4. Create or update one existing draft; never duplicate.
5. Generate an owner-review quote packet from the draft.
6. Customer quote sending remains a separate exact owner approval.
7. Reservation remains disabled unless separately reviewed and authorized.

Acceptance:

- exact source-backed totals;
- no quote when category, price, quantity, or availability is unavailable;
- draft creation is idempotent;
- no stock reservation;
- no payment claim;
- zero customer sends during migration/integration tests.

## Work Package 7 - Production Verification

Required test layers:

- unit tests for state, projection, guided selling, pricing and stock gates;
- production-shaped fixtures for the six reported conversations;
- disposable PostgreSQL tests for append-only, idempotency, concurrency,
  projection and privilege boundaries;
- browser tests for inbox freshness, disabled reasons, edit/approve/send and
  mobile behavior;
- webhook and reconciliation convergence tests;
- Telegram delivery/unknown/replay tests;
- 100-turn historical replay with at least 20 complete conversations;
- exact-head independent backend/security review;
- exact-head CI;
- post-merge CI;
- deployment health/policy verification;
- read-only full-inbox production reconciliation;
- bounded owner-approved canaries in this order:
  1. queue-only;
  2. one draft review;
  3. one exact send;
  4. one intake;
  5. one draft order;
  6. one quote review.

Stop immediately if:

- any open conversation is silently absent;
- any stale draft remains sendable;
- any stock/price claim lacks provenance;
- any duplicate send/order/intake occurs;
- any migration or privilege contract differs;
- any unrelated business authority becomes true.

## Same-Day Execution Order

### Block A - First 90 minutes

- Work Package 0 baseline.
- Architecture/source-map confirmation.
- Exact file claim.
- Implement Work Package 1 coverage and projections.
- Test 771/2031 and handled-state regressions.

### Block B - Next 90 minutes

- Implement current Owner Inbox projection and freshness.
- Integrate reconcile status and explicit unavailable states.
- Browser-test authoritative queue behavior.

### Block C - Next two hours

- Implement guided category/availability/price response.
- Implement durable intake memory.
- Add 2029/2031/2040 regression cases.

### Block D - Next 90 minutes

- Align Telegram card lifecycle with the current work identity.
- Add exact draft edit/approve/send controls.
- Prove zero duplicate notification/send behavior.

### Block E - Integration and deployment

- Run complete affected suite and 100-turn replay.
- Independent backend/security and sales-quality reviews.
- Merge only the reviewed head.
- Deploy and verify health/policy.
- Perform read-only full-inbox reconciliation.
- Run queue-only canary.

### Block F - Controlled business canaries

- Only after Block E passes, request separate owner authorization for intake,
  draft-order, quote, or customer-send canaries.

If the complete safe scope cannot be finished today, the minimum acceptable
live recovery is Work Packages 1-3 plus a current authoritative queue. Deal
write gates remain off rather than being rushed.

## Likely File Scope

Final scope must be confirmed against current main, but likely includes:

- `modules/sales/sam_owner_work_queue.py`;
- `modules/sales/sam_live_stock_runtime.py`;
- `modules/sales/sam_live_stock_launch_control.py`;
- `modules/sales/sales_transaction_routes.py`;
- `templates/sam-owner-inbox.html`;
- `static/js/samOwnerInbox.js`;
- `static/css/samOwnerInbox.css`;
- relevant additive Supabase migration only if a current-projection or intake
  table contract is missing;
- focused SAM queue/runtime/route/PostgreSQL/frontend/browser tests;
- this plan, controlling Vault workflow/rules, source map, and changelog.

No unrelated SAM Meat, BEACON, HERDMASTER, order, reservation, payment, farm
lifecycle, CORE, ROOTLINE, or public-posting files enter the claim without an
explicit architectural reason and owner approval.

## Required Terminal Delivery Format

The SAM Live Stock terminal must report:

- exact base/head/merge/deployment revisions;
- exact changed files;
- migration identity/checksum/application state;
- test and CI evidence;
- independent review verdict;
- live policy before/after;
- full-inbox reconciliation totals;
- per-conversation results for 771, 2031, 2029, 2039, 2040, and 2023;
- notification coverage;
- queue latency;
- stock/price provenance proof;
- sends/intakes/orders/quotes/reservations created;
- remaining blockers and exact owner decisions required.

