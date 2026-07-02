# Pig Purpose Rules

Purpose/allocation is dynamic and should use weights, growth, litter quality, demand, and outlet timing.

Fast growers from strong litters are reviewed first for breeding, then meat, then slaughter/abattoir fallback.

Slow growers and underperformers should be considered for livestock sale to reduce feed cost.

Unknown purpose is a data/classification problem, not a silent sale/meat/slaughter decision.

## Operating Rules

- One pig should have one operational truth.
- Meat candidates should be young and weight-dependent.
- Meat-window pigs that are not pre-sold in time should fall back to slaughter/abattoir.
- Lifecycle, purpose, death, movement, medical, litter, mating, breeding, weight, and slaughter records require approved backend paths and owner approval where needed.

## Readiness Buckets

Use these as advisory labels first, not automatic writes:

- `Needs Data`: missing identity, tag, sex, weight, age/stage, or pen data.
- `Needs Classification`: enough basic data exists but purpose is blank or `Unknown`.
- `Growing`: active/on-farm and below useful sale/slaughter/meat thresholds.
- `Livestock Candidate`: likely better to sell live, especially slow or underperforming pigs.
- `Slaughter Candidate`: suitable for abattoir/fallback outlet.
- `Meat Candidate`: young, healthy, weight-dependent candidate for pre-sold meat orders.
- `Retain / Breeding Candidate`: strong growth/litter/parent signal worth owner review.
- `Allocated`: already committed to an order, slaughter batch, or future meat workflow.
- `Exited`: already left farm or terminal status.

## Timing Rules

- Purpose attention should not appear immediately after weaning.
- First rule: wait 14 days after weaning before final purpose review.
- If the 14-day window has passed but no post-wean weight exists, dashboard attention should say `Post-wean weight needed`.
- Once a post-wean weight exists after the 14-day window, dashboard attention should say `Purpose review due`.
- Wean date and wean weight must come from `PIG_MASTER`, not only a formula view.

## Growth Bands

Use kg/day in UI and API:

- `Extremely Slow`: below `0.100 kg/day`;
- `Slow`: `0.100` to below `0.200 kg/day`;
- `Below Target`: `0.200` to below `0.300 kg/day`;
- `Steady`: `0.300` to below `0.400 kg/day`;
- `Good`: `0.400` to below `0.500 kg/day`;
- `Exceptional`: `0.500 kg/day` or higher.

## Herdmaster Boundary

Herdmaster can recommend purpose review, explain growth/litter signals, and prepare owner approval packets. It cannot change records without approved backend actions and owner approval.

## Source References

- `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md`
