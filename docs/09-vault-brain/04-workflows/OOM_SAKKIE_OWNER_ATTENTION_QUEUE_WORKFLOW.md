# Oom Sakkie Owner Attention Queue Workflow

Status: coordination kernel integrated; existing-rail adapter prepared

## Outcome

Oom Sakkie gives the owner one low-noise attention stream through the existing
Telegram, GateKeeper, SAM owner-card and decision-evidence infrastructure.
This workflow adds no bot, trigger, customer router, callback namespace owner,
decision ledger or runtime scheduler.

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
