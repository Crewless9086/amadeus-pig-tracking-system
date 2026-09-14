# HERDMASTER lifetime genetic-merit source coverage — stages 1–3

Cutoff-bound recommendation evidence must use current canonical projections while retaining immutable historical and supersession provenance. Missing coverage blocks only its own axis.

| Evidence link | Canonical source | Current attribution | Exact gap / rule |
|---|---|---|---|
| Breeding identity and pedigree | `current_canonical_pigs`, `pigs`, litter dam/sire and existing breeding pedigree packet | Exact Pig ID; known dam/sire links | Foundation ancestry can remain Unknown under the bounded founder decision; known unsafe relationships still exclude |
| Mating/exposure | `mating_events` | Exact mating, sow, boar and date/exposure | A 17-day exposure does not prove one service or conception date; silence is not failure |
| Supported conception | Attributable `mating_events` → `current_canonical_litters` linkage or one unambiguous 100–130-day same-pair farrowing | Exact pair and litter | Conception rates require complete-through opportunity outcomes; otherwise Unknown |
| Litter production | `current_canonical_litters` | Exact sow, boar, litter | Superseded/duplicate litter IDs and disposed child identities excluded from current aggregates but retained historically |
| Survival to weaning | Litter born-alive/weaned fields and child `wean_date` | Exact litter/pair | Missing weaned count is Unknown, never zero; current on-farm count is not a substitute |
| Weaning quality | Canonical child `wean_weight_kg`, `wean_date` | Exact child/litter | Coverage and missing count shown; no nearby ordinary weight is silently relabelled a weaning weight |
| Post-weaning growth | `pig_weight_events` plus exact child `wean_date`/weight | Exact child/litter | Only positive elapsed time and ±7-day comparable 30/60/90-day windows; partial subsets disclosed |
| Later mortality | Governed pig exit/lifecycle evidence and mortality corrections | Exact child/litter | Dated pre-/post-weaning losses separated; undated or suspected loss remains Unknown; no cause inference |
| Lifetime destination | Canonical pig lifecycle/purpose plus sale items | Exact child | Active, sale, auction, slaughter/meat, breeding retention, death/removal or Unknown; auction disposal is not ordinary sale merit |
| Financial outcome | `sales_transactions`, `sales_transaction_items`, auction invoice-aware fields and attributable-cost rows | Exact child only when item value exists; exact lot otherwise | Never divide a lot total into invented child proceeds; margin remains Unknown without compatible attributable cost coverage |
| Context | Movements, observations, medical, feed/water and ROOTLINE observations | Exact animal/cohort/time where supplied | Associated context only; never genetic cause or clearance |

## Remaining reusable data-quality requirements

- Preserve explicit mating-to-litter linkage whenever a governed litter is recorded.
- Record governed weaning count, child weaning date and child weaning weight independently.
- Retain exact parent IDs for every attributable future child.
- Identify whether mating opportunity outcomes are complete through a stated boundary before calculating conception reliability.
- Retain item-level financial value only when the transaction genuinely supplies it; keep auction/lot values at lot level otherwise.
- Add attributable cost coverage before any profit or gross-margin comparison.

No schema or migration is required for stages 1–3. Later loader integration may expose these existing sources to the pure packet; it must not create a second ledger, dashboard, Telegram lifecycle or mating executor.
