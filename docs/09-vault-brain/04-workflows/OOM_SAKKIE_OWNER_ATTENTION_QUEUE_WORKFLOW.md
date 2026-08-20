# Oom Sakkie Owner Attention Queue Workflow

Status: coordination kernel integrated; shared read-only projection implemented

## Outcome

Oom Sakkie gives the owner one low-noise attention stream through the existing
Telegram, GateKeeper, SAM owner-card and decision-evidence infrastructure.
This workflow adds no bot, trigger, customer router, callback namespace owner,
decision ledger or runtime scheduler.

## Shared Attention Projection

The attention queue is the single typed owner-attention decision projection
for the homepage, Brief, Telegram and later voice presentation. Specialists
contribute attributable work-item facts; browser code and channel renderers do
not independently decide which farm work exists or recalculate priority.

Each current item carries one stable identity, category, specialist owner,
priority/watch classification, exact owner action, evidence provenance and
freshness, safe detail target, and open/resolved/superseded lifecycle. Every
authorized channel consumes the same ordered identities and lifecycle. A
compact channel may render fewer items, but must expose the total hidden count
and a governed route to the complete projection.

`status_reconciliation`, `physical_action_due` (including genuine weighing),
and `informational_watch` are distinct task classes. A missing or conflicting
animal status remains specialist reconciliation until HERDMASTER proves a
physical action is required. A ROOTLINE refresh or timeout remains assigned to
ROOTLINE/Oom Sakkie unless one precise physical observation is irreducibly
required from the owner. Failure of one specialist must not erase unrelated
current items from another specialist.

## Three output classes

1. **Sales-status summary:** exactly one stable identity per configured period,
   edited in place when its existing Telegram message identity is known. It
   selects the latest provenance-bound chronology position per conversation,
   rejects conflicting exact ties, and reports new enquiries, automatically answered customers, qualification
   progress, awaiting customers, genuine owner decisions and systemic failures.
   It has no buttons.
2. **Protected decision card:** one card only when current canonical evidence
   requests a protected authority such as special price, delivery commitment,
   reservation, allocation, binding quote, order or payment. It binds account,
   inbox, contact, conversation, latest inbound, evidence-packet hash,
   requested authority, decision identity and expiry. Only source-declared
   actionable choices become buttons.
3. **System alert:** a separate deduplicated buttonless alert only when SAM is
   disabled, systemically contained or cannot observe authoritative chronology.
   It uses a stable incident identity across summary periods, names affected
   work, and gives typed guidance on whether manual coverage is required.

Ordinary leads, inbounds, acknowledgements, qualification steps, waiting states
and automatically answered conversations never create individual Telegram
notifications or buttons.

## Decision lifecycle

- Before presentation or consumption, compare every binding field and expiry
  with current canonical evidence.
- A changed latest inbound, chronology identity, evidence hash, authority or
  participant identity expires the card. Edit that same Telegram message,
  remove all buttons and return ownership to SAM for reassessment.
- The decision identity and trusted card digest are derived from the complete
  binding, authority, expiry and canonical choices; callers cannot choose them.
- Consumption preparation requires the separately trusted card digest, the
  exact current binding, a current expiry, one listed actionable choice and an
  authenticated actor hash equal to the separately trusted owner hash.
- The existing adapter must atomically compare-and-consume the replay key and
  return a durable authoritative receipt. Only that receipt permits preparation
  of an in-place resolved-card edit with no buttons, next owner and trigger.
- Callback replay creates zero decisions, sends, edits, customer actions and
  farm actions. Do not delete the card or send a completion message.

## Integration boundary

`modules/oom_sakkie/owner_attention_queue.py` is I/O-free and reports zero
writes/calls performed. A later serialized
adapter change must map its intents to the existing SAM card lifecycle,
GateKeeper callback route, Telegram edit/send functions and existing durable
decision evidence. It must not bypass their identity, claim, chronology,
provider, callback-replay or owner-authentication checks.

No summary/card/alert intent itself authorizes Telegram, customer, Chatwoot,
farm, commercial or hardware activity.

`modules/oom_sakkie/owner_attention_projection.py` is the single read-only
channel projection over the existing general-manager specialist collectors.
It creates no persistence or trigger. The homepage, complete owner-attention
view, daily Brief and Telegram formatter consume its ordered stable work IDs,
classification, specialist ownership, provenance/freshness, exact owner action,
safe detail target and lifecycle. Browser code may display this packet but may
not add, remove, rank or reclassify owner-attention work.

## Existing-rail adapter

`modules/oom_sakkie/owner_attention_adapter.py` projects current SAM inbox
dispositions without customer content. The existing reconcile loop calls it
after SAM reaches its normal durable disposition; adapter failure is contained
and cannot stop SAM. A default-off environment gate controls delivery.
Summary, decision and incident identities use the existing owner-card lifecycle
and review-event evidence table. Authenticated `sam_live_owner_decision:`
callbacks remain inside the existing governed SAM callback namespace and
the existing Oom Sakkie webhook, record one receipt through that rail,
and edit the same card without applying a customer or protected action.
Specific authenticated requests retain their specialist meaning. A natural
breeding or mating-plan request is consumed by HERDMASTER from the current
canonical breeding worklist and receives a HERDMASTER response; it is not
recast as a broad daily farm brief. English, Afrikaans and mixed language use
the same semantic domain contract. Only genuinely broad priorities/whole-farm
requests enter the consolidated manager round.

Before presenting active welfare or mortality work, the queue reconciles the
specialist lifecycle against canonical animal state. Dead, Sold or off-farm
animals retire stale active projections. Historical lifecycle and provider
chronology remain immutable audit evidence, but no completed/superseded task
may reappear as current owner work.

## Actionable daily-manager continuation

The scheduler stores one typed binding for the single grouped question on the
provider-delivered daily plan. The next authenticated reply loads that binding
before generic semantic intake. Exact reply identity or one compatible
English/Afrikaans semantic continuation may advance it; unrelated direct
specialist requests remain direct requests. Proven partial evidence is retained
and receives only one smallest missing follow-up. A complete answer retires
that exact task-generation question without suppressing a later materially new
question.

Daily presentation is limited to three do-today items and three watch items.
Sale attention resolves human customer/outlet, amount and payment truth and
links to the existing canonical transaction. The owner-governed payment-state
rail first previews the actual received amount against current amount due, then
requires authenticated digest-bound confirmation. Full receipt equals amount
due; partial receipt retains the actual lesser amount. Only confirmation
changes receipt state/amount/method/date, and it does not rewrite BKB invoice,
VAT, commission, settlement-payable or item-price facts. Telegram describes
payment-evidence review until canonical readback exists.

## Context, Specialist And Recovery Ordering

Authenticated intake resolves exact callback/confirmation, reply-to lifecycle,
one unambiguous active contextual question and explicit entity/domain intent
before broad manager interpretation. Notification receipts enrich chronology
but never replace the waiting lifecycle. Completed or superseded cases cannot
capture later unrelated text.

New facts create a new evidence generation. Natural corrections invalidate the
prior preview without deleting it and prepare a fresh deterministic preview.
Stale confirmations fail closed. Protected grouped actions lock affected
records, revalidate eligibility and commit atomically when promised; partial
failure rolls back and exact replay changes zero rows.

Manager composition consumes typed specialist facts, not rendered prose. One
unavailable specialist blocks only dependent conclusions. Priorities favour
welfare, time-sensitive farm work and money/customer exceptions over internal
housekeeping. Every surfaced item names its usable completion path or states
truthfully that no current action exists.
