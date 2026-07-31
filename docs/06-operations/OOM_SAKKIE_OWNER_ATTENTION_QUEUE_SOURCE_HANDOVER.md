# Oom Sakkie Owner Attention Queue — Source Handover

Status: kernel integrated; shared adapter prepared for reviewed deployment

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

The bounded adapter now lives in
`modules/oom_sakkie/owner_attention_adapter.py`. It reuses the existing SAM
inbox result, owner-card lifecycle, review-event evidence rail, Telegram
send/edit helpers and authenticated direct-owner callback. It adds no bot,
trigger, router, webhook, workflow family, table or decision ledger:

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

Integration tests exercise these exact existing adapters for provider
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

Adapter review evidence:

- focused queue/adapter/inbox selection: 57 passed, 3 subtests passed;
- shared Oom Sakkie/SAM/Telegram selection: 623 passed, 7 skipped, 289
  subtests passed;
- independent owner-experience/product/operations review: approved;
- independent backend/security/privacy/authority review: approved.

No Telegram call, deployment, merge, customer/farm mutation, decision
consumption or shared-runtime acquisition occurred.

The preceding source-only statement describes the kernel PR. During the later
authorized serialized window, PR #641 and the reconciled PR #631 were merged
normally with exact-head and exact-merge CI. Render reached merge `2bda3248`,
and the existing active relay Build node was updated alone to reviewed SHA-256
`732d38a80dc777f634bc189a949b5f318a37bf308f9c57cfeb55e36e3c8372a1`.

## Deployment gate and bounded proof

`OOM_SAKKIE_OWNER_ATTENTION_QUEUE_ENABLED` is the only new runtime gate. Keep
it false until the exact adapter merge is deployed and healthy. Then enable
only that key and run one read-only current-SAM reconciliation with customer
processing capped at zero. It may establish one owner summary identity; the
repeat proof must edit that identity or deduplicate it. It must send no
customer message and must not manufacture a protected decision.
