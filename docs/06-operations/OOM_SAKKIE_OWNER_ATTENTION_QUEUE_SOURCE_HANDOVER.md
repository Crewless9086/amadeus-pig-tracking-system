# Oom Sakkie Owner Attention Queue — Source Handover

Status: source-ready only; unmerged and undeployed

## Prepared result

The pure coordination kernel in
`modules/oom_sakkie/owner_attention_queue.py` prepares three outputs without
performing I/O:

1. one buttonless period summary, counting only the latest provenance-bound
   state per account/inbox/contact/conversation;
2. digest-bound protected-decision cards with bounded callback-safe choices;
3. stable, buttonless systemic incident alerts with typed affected scope and
   manual-coverage guidance.

Ordinary leads, inbound messages, acknowledgements and SAM-handled work create
no individual Telegram intent. Conflicting chronology ties, incomplete
bindings, unsafe identifiers, forged cards and receipt mismatches fail closed.

## Shared-file integration handover

No shared runtime adapter was changed. In a later serialized Oom Sakkie window,
the existing owners must make these bounded integrations rather than add a new
bot, trigger, router or ledger:

- the existing SAM status projection supplies provenance-bound observation
  timestamps, chronology sequence, opaque identities and canonical evidence
  hashes to `build_owner_attention_queue`;
- the existing Telegram adapter creates/edits the one summary identity, creates
  protected cards, and edits expired/resolved cards in place;
- the existing GateKeeper owner callback authenticates the actor, loads the
  separately trusted owner hash and card digest, and calls
  `consume_decision_card`;
- the existing owner-decision evidence rail atomically compare-and-consumes the
  prepared replay key and returns one durable receipt;
- only that receipt is passed to `build_resolved_card_edit`; replay performs no
  write, send or edit;
- existing incident-message identity storage retains stable alert IDs across
  summary periods and resolves/edits an incident only when its state changes.

Integration tests must exercise these exact existing adapters for provider
message identity, atomic receipt uniqueness, stale-button removal, changed
chronology, callback replay, incident lifecycle, SAM-disabled containment and
preservation of every unrelated Oom Sakkie, SAM, HERDMASTER, ROOTLINE and BEACON
route.

## Verification at prepared head

- focused queue contract: 17 passed, 3 subtests passed;
- relevant Oom Sakkie, SAM, Telegram and relay integration selection: 672
  passed, 7 skipped, 289 subtests passed;
- independent product/owner-experience/operations review: approved;
- independent backend/security/privacy/authority review: approved;
- Oom Sakkie browser behavior smoke: passed;
- Python compilation and `git diff --check`: passed.

No Telegram call, deployment, merge, customer/farm mutation, decision
consumption or shared-runtime acquisition occurred.
