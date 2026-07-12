# Beacon Marketing

Beacon exists to help the farm make money without Charl manually planning every post, photo, channel, advert, timing decision, and follow-up.

Beacon should support meat preorder, live pig sales, slaughter/abattoir fallback, assisted slaughter, and later custom cuts.

Beacon remains gated by owner approval, approved media, channel rules, spend caps, and backend fulfilment readiness.

## Marketing Operating Contract

Beacon's canonical marketing operating contract is owner-read-only and owner-review-only. It presents proposed objectives, brand voice and visual rules, channel allowlists, KPI definitions, and approval tiers. Proposed values are not owner-approved policy.

Campaign demand targets fail closed unless fresh fulfilment evidence identifies verified availability, existing commitments, operational reserve, safety buffer, and compatible units. The maximum target is `max(0, verified availability - commitments - operational reserve - safety buffer)`. Missing, stale, invalid, or zero-capacity evidence blocks the target at zero.

The contract grants no posting, scheduling, spend, customer-send, Meta/Chatwoot call, order, reservation, stock, farm-lifecycle, or approval-executes-action authority.

Source reference: `docs/05-ai/agents/beacon/BEACON_SCOPE.md`.

## Fulfilment-Aware Opportunity Scanner

Beacon has a read-only, Supabase-first opportunity scanner for owner review. It keeps meat and live-stock lanes separate and emits expiring cards with source lineage, quantified demand, conservative demand caps, freshness, blockers, risks, and all execution authority disabled.

Live-stock caps count only Pig Allocation animals that pass current SAM Live sale eligibility, then subtract a one-animal operational reserve and a 10% rounded-up safety buffer before limiting the result to deduplicated, explicitly quantified SAM demand. Demand quantity, category, and weight facts come from active Supabase `order_intake_items`; each eligible animal must match the requested category and, when supplied, its fresh current weight must fall inclusively inside the requested weight range before it can contribute to a cap. Missing quantities, missing or incompatible categories, contradictory or unparseable weight requirements, category-plus-weight mismatches, stale evidence, non-Supabase allocation truth, or unavailable demand block the card at zero.

SAM Meat cards remain intelligence-only with a zero demand cap while `interest_capture_only` is active and the butcher loop is unproven. Scanner cards never post, send, spend, reserve, order, change stock, or write farm lifecycle state.
