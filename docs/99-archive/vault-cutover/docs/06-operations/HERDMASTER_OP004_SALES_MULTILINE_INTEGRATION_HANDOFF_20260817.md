# HERDMASTER OP-004 To SALES Multi-Line Integration Handoff

Status: authoritative contract integrated; SALES consumption pending in the preserved worktree.

## Integrated authority

- PR `#1001` merged to authoritative `main` as `355f1154b3d09dd591d6b988060260e5e500bd3d`.
- Typed source contract: `modules/pig_weights/herdmaster_live_transfer_contract.py`.
- Contract version: `herdmaster_live_transfer_disclosure_v1`.
- Zero-write composer: `compose_live_transfer_contract(snapshot, as_of=...)`.
- Canonical loader for an existing order: `build_live_transfer_contract(pig_ids, order_id, as_of=...)`.
- The packet explicitly reports `writes_performed: false`, `creates_order_line: false`,
  `creates_reservation: false`, `generates_document: false`, and
  `creates_buyer_acknowledgement: false`.

This contract is authoritative for purpose, active/on-farm state, treatment evidence,
food-chain withdrawal disclosure, transport fitness, quarantine, infectious/notifiable
disease, veterinary movement stop, serious welfare/health holds, existing-order membership,
price-band compatibility, and active order-line duplication protection. Missing current
live-transfer evidence fails closed as `Unknown`; food-chain withdrawal remains a separate
axis and never becomes a guessed live-transfer prohibition or clearance.

## Preserved SALES implementation

Worktree `C:\tmp\sales-multiline-livestock-quote-20260817`, branch
`fix/sales-multiline-livestock-quote-20260817`, remains intentionally dirty and was not
modified by HERDMASTER. Its current unique work includes:

- modified `app.py`, `modules/orders/order_routes.py`,
  `modules/pig_weights/pig_weights_service.py`, `static/js/addOrder.js`, and
  `templates/add-order.html`;
- untracked `modules/orders/livestock_quote_preview.py`,
  `tests/test_livestock_quote_preview.py`, and two owner-preview screenshots.

The only direct file collision is `modules/pig_weights/pig_weights_service.py`. SALES must
preserve the current-main version and reapply only its intentional wording change after
reconciliation. It must not copy, recreate, simplify, or fork the HERDMASTER live-transfer
logic inside Orders.

## Exact consumption change

1. Reconcile the SALES branch onto `main >= 355f1154` without stashing, resetting, or
   overwriting its dirty files.
2. In `modules/orders/livestock_quote_preview.py`, retain only request-line normalization,
   sex/weight exact-near-projected ranking, cross-line candidate de-duplication, grouped
   counts, and shortfall calculation.
3. Remove `_render_candidate()` authority over purpose, withdrawal, health, movement,
   quarantine, disease, welfare, treatment disclosure, and recommendability.
4. Supply one HERDMASTER contract packet for the complete candidate set from a single
   canonical, repeatable-read evidence snapshot. For a request preview that has no order,
   call `compose_live_transfer_contract()` with an empty order object and empty order lines;
   do not invent an order ID. For an existing draft, use the real canonical order and lines.
5. Index `packet["pigs"]` by `identity.pig_id`. A candidate is recommendable only when all
   of the following are true:
   - `livestock_transfer_eligibility.state == "eligible_on_current_evidence"`;
   - `current_purpose_eligibility.state == "eligible"`;
   - `active_on_farm_eligibility.state == "eligible"`;
   - `current_order_eligibility.state` is `candidate_not_added` or
     `included_draft_unreserved` as appropriate; and
   - `order_line_duplication_protection.state` is not conflicting or blocked.
6. Carry `treatment_disclosure`, `food_chain_eligibility`, every independent gate, evidence
   IDs/reasons, `packet_digest`, `contract_version`, and `evidence_cutoff_date` through the
   preview response without weakening or rewording their authority.
7. Rank only recommendable candidates into `exact_match`, `near_match`, or
   `projected_growth`. Show blocked/Unknown candidates in a separate grouped
   `purpose_or_evidence_review` preview; never count them toward supported fulfilment.
8. Report each request line independently with requested quantity, exact count, near count,
   projected count, supported count, and shortfall. Report a grouped review section by
   blocking axis/reason so Charl receives one useful decision surface rather than repeated
   per-pig questions.
9. Preserve these separate states in API and UI: customer request captured; HERDMASTER
   recommendation advisory; reservation none; fulfilment none. Preview must not call order
   creation, line sync, reservation, allocation, purpose apply, customer send, or document
   generation.
10. Keep the existing Orders engine authoritative for any later explicitly confirmed draft,
    line, reservation, approval, and fulfilment transition. The preview must not become a
    second order engine.

## Required acceptance

- The four-line request `10 female 5-6 kg`, `10 male 5-6 kg`, `1 female 15-19 kg`, and
  `1 male 15-19 kg` totals exactly 22 requested pigs without collapsing lines.
- One pig can appear in at most one recommended line in a preview.
- Exact, near and projected candidates are counted separately; unsupported candidates do
  not hide the numerical shortfall.
- Non-Sale/Unknown purpose appears only in grouped purpose review and is never silently
  changed or counted as fulfilment.
- Unknown/blocked live-transfer evidence remains visible with the authoritative HERDMASTER
  reason and evidence identity.
- Active order-line conflicts fail closed; no duplicate active `(order_id, pig_id)` can be
  created, including under concurrency.
- Route authentication runs before canonical evidence reads.
- Provider/canonical failure returns a zero-write failure without leaking private details.
- Tests assert zero calls to order creation, sync-lines, reserve, purpose apply, send, and
  document generation for every preview path.
- The rendered page labels request, recommendation, reservation, and fulfilment separately
  on desktop and mobile.

## Protected boundary

No customer send, order creation, reservation, allocation, purpose/farm write, price
commitment, document generation, or fulfilment is authorized by this handoff. A later exact
owner confirmation must use the existing protected action and Orders rails; it must never
reuse preview generation as confirmation.
