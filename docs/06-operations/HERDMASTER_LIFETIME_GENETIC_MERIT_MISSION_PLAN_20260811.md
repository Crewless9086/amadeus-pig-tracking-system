# HERDMASTER Lifetime Genetic Merit Mission Plan

Date: 2026-08-11  
Owner: Charl Nieuwendyk  
Status: Approved mission plan; implementation not started  
Execution owner: HERDMASTER specialist terminal  

## 1. Owner-visible outcome

HERDMASTER must recommend practical sow-to-boar pairings using the complete attributable outcome chain available in Amadeus:

`mating/exposure -> conception outcome -> litter size -> born alive -> survival to weaning -> weaning weight -> post-weaning growth -> later mortality -> sale/slaughter/breeding outcome -> financial value`

The result must help Charl build a stronger, more productive and more profitable herd. It must remain practical: name the sow, primary boar, reserve boar, proposed placement window, strongest supporting evidence, material weakness, and confidence. It must not hide behind IDs, produce an unexplained mathematical ranking, or confuse missing evidence with poor performance.

## 2. Existing truths to preserve

- A sow becomes a practical placement candidate from governed weaning/reproductive chronology; standing-heat observation is not a prerequisite.
- Normal physical placement is a 17-day boar exposure window intended to cover two farm heat cycles. It does not prove an exact service or conception date.
- Current welfare, structural, medical, withdrawal, reservation and known-family conflicts remain hard or scoped holds.
- D3 and other pens are locations, not permanent reproductive-state rules.
- Prince and any future new boar require bounded controlled trials; lack of offspring evidence must not become a permanent self-reinforcing exclusion.
- Foundation animals with genuinely unavailable ancestry may be treated under Charl's explicit bounded founder assumption as having no known relationship to one another. This is not invented pedigree. Known descendants and every subsequently attributable family relationship must remain tracked and enforced.
- No recommendation creates a mating, movement, pregnancy, treatment, sale or other farm fact.

## 3. Evidence model

For every candidate pair, build an immutable evidence packet at one cutoff. Separate:

### 3.1 Reproductive opportunity and conception

- Exact recorded sow and boar exposure/mating events.
- Exposure start/end where available.
- Whether an attributable litter followed the exposure.
- Empty return, repeat service or unresolved outcome only when canonically recorded.
- Farrowing following exposure is a supported conception outcome; silence is Unknown, not failed conception.
- Calculate conception/farrowing success only from complete-through attributable opportunities.

### 3.2 Litter production

- Total born, born alive, stillborn and mummified counts.
- Exact sow, boar and litter attribution.
- Exclude superseded, conflicting or duplicate litter representations.
- Report sample size and data completeness with every rate.

### 3.3 Survival to weaning

- Weaned count divided by born alive for exact pair, sow, boar and cohort views.
- Retain the actual counts alongside the percentage.
- Never use current-on-farm count as a substitute for governed weaned count.
- Unknown or incomplete weaning is not scored as zero.

### 3.4 Weaning quality

- Individual weaning weights, coverage count and missing count.
- Mean, median, range and dispersion where coverage permits.
- Compare weights only at comparable weaning ages and with clear units.
- Keep survival and weight visible together so a small heavy litter cannot automatically dominate a larger healthy litter.

### 3.5 Post-weaning growth

- Use attributable child identities and dated weight events.
- Calculate comparable-age or comparable-days-since-weaning growth windows, initially 30, 60 and 90 days where evidence permits.
- Use average daily gain only across valid positive elapsed time and compatible evidence.
- Separate complete-cohort results from partial weighed subsets.
- Pen, feed, weather, illness and management evidence are context, not automatically genetic causes.

### 3.6 Later mortality and robustness

- Attribute canonical dated deaths to litter, sow, boar and exact pair.
- Separate pre-weaning and post-weaning mortality.
- Use age-at-loss and observation coverage where available.
- Unknown cause remains Unknown. Do not infer genetics, infection, feed or management as cause.
- A mortality association may lower confidence or flag review; it becomes a genetic exclusion only with sufficient repeated attributable evidence and reviewed doctrine.

### 3.7 Lifetime destination

- Track each attributable child to its latest canonical outcome: active growing, livestock sale, auction, meat/slaughter, breeding retention, death, removal or Unknown.
- Preserve outcome timing and cohort coverage.
- Do not treat auction disposal of intentionally selected slow growers as equivalent to ordinary livestock success.
- Breeding retention is evidence of selection, not proof of superior genetics by itself.

### 3.8 Financial outcome

- Bind only authoritative revenue and attributable costs.
- Preserve lot-level auction or sale values when individual pig values are Unknown; never divide them into invented individual proceeds for canonical accounting.
- Analytical per-pig or per-kilogram estimates may be shown only as labelled management estimates.
- Separate gross revenue, VAT, commission, other deductions, net settlement and payment receipt.
- Feed, medication, labour and other costs remain Unknown until attributable evidence exists.
- Prefer contribution/gross-margin comparisons only when the compared cohorts have compatible coverage. Market channel and sale timing must be shown as context rather than falsely labelled genetic merit.

## 4. Recommendation method

Do not collapse the full chain into one unexplained score. Produce an explainable evidence profile with these axes:

1. Reproductive reliability.
2. Litter productivity.
3. Survival and robustness.
4. Weaning quality.
5. Post-weaning growth.
6. Lifetime productive outcome.
7. Financial outcome.
8. Evidence confidence and sample size.

Use the profile to assign one transparent class:

- Proven repeat
- Supported cross
- Corrective cross
- Controlled trial
- Limited evidence
- Held/excluded

Any internal numeric calculation must be deterministic, versioned, included in the evidence packet, decomposable by axis, tested against missing-data bias, and rendered to Charl as plain reasons rather than a naked score.

### 4.1 Attribution and fairness

- Calculate exact-pair evidence separately from sow evidence and boar-across-sows evidence.
- Do not credit or blame one parent for an outcome without showing the pair and cohort context.
- Compare contemporary or otherwise defensibly comparable cohorts where possible.
- Do not reward larger sample size merely because an older boar has had more opportunities.
- Apply confidence/shrinkage or evidence tiers so one excellent litter does not outweigh consistent multi-litter evidence without disclosure.
- Reserve a bounded portion of practical capacity for controlled trials of eligible unproven boars.

### 4.2 Decision priority

Hard safety and known-family exclusions apply first. Among eligible pairs, prefer the best evidence-supported balance of:

- reliable conception/farrowing;
- healthy born-alive litter size;
- survival to weaning;
- sound weaning weight without sacrificing survival;
- healthy comparable post-weaning growth;
- low unexplained later loss;
- useful sale, slaughter or breeding outcomes;
- supported financial contribution;
- sufficient evidence confidence.

No single metric, including workload, litter size, weight, survival or revenue, may dominate without an explicit owner-approved rule.

## 5. Practical owner output

The normal Afrikaans Telegram result must be concise:

### PLAAS NOU / VOLGENDE GROEP

For each sow:

- `Sow name -> Primary boar` and reserve.
- Placement dates.
- One-line reason containing the most decision-relevant lifetime evidence.
- One material limitation only when it changes the decision.

Example form, not fabricated data:

`Lolly -> Bola; reserve Tyson. Proven repeat: strong survival to weaning, supported weaning weight and comparable post-weaning growth across an attributable litter. Financial outcome remains incomplete.`

### BEHEERDE PROEF

Name the unproven boar, selected sow, why she is a safe interpretable trial, and which future outcomes will determine success.

### NIE TANS GESKIK NIE

Use names and short genuine blockers. Do not repeat long generic evidence lists.

The detailed application/print report may show the full evidence axes, counts, rates, weights, growth windows, outcomes, financial evidence and Unknowns.

## 6. Automatic refresh triggers

Recompute the read-only recommendation when canonical material evidence changes, including:

- a litter is weaned or corrected;
- a mating/exposure or reproductive outcome is recorded;
- a weight batch adds comparable offspring growth evidence;
- a mortality lifecycle is completed or corrected;
- a child reaches sale, auction, slaughter, breeding retention or removal;
- attributable financial settlement is added or reconciled;
- a welfare, medical, withdrawal, reservation or family-tree fact changes.

An older Telegram plan must not silently remain presented as current after a material trigger. Oom Sakkie should either provide the refreshed concise plan on request or clearly state the plan's evidence cutoff.

## 7. Implementation constraints

- Reuse canonical Supabase animals, litters, matings, weights, medical/lifecycle events, sales and financial projections. Do not create a parallel herd ledger.
- Inspect and document exact source coverage before adding schema.
- Add only governed additive views/events needed to bind missing attribution or completeness.
- Preserve immutable corrections and superseded history.
- Missing evidence is Unknown, never zero, failure or clearance.
- Deterministic replay must produce the same recommendation identity and zero new effects.
- HERDMASTER remains read-only for recommendation generation.
- Oom Sakkie may deliver the result through the existing authenticated specialist-consumption boundary.
- Actual mating and movement remain separately confirmed protected actions.

## 8. Required validation

Tests must prove at least:

- complete and partial lifecycle coverage;
- no invented conception failure from silence;
- weaning percentage changes pair evidence correctly;
- average/median weaning weight uses only covered piglets;
- post-weaning deaths are not mistaken for pre-weaning loss;
- comparable-age growth prevents age-biased ranking;
- one high-performing small litter does not silently dominate balanced evidence;
- new-boar controlled trials remain possible;
- auction lot values are not invented per pig;
- missing costs prevent false profit claims;
- known relationships remain excluded under the bounded founder doctrine;
- superseded litters and identities cannot double-count;
- a newly completed weaning materially refreshes the recommendation;
- natural English/Afrikaans output is concise and name-led;
- replay produces the same evidence identity and zero writes/messages beyond the governed delivery lifecycle.

## 9. Delivery stages

1. Reconcile canonical source coverage and publish a gap matrix.
2. Implement the pure lifetime-outcome evidence packet and deterministic tests.
3. Implement explainable pair profiles and controlled-trial allocation.
4. Integrate the detailed Weight/Breeding report without creating a competing dashboard.
5. Integrate concise Oom Sakkie delivery.
6. Deploy only in a serialized production window.
7. Prove one fresh real-world recommendation after a genuine material event.
8. Compare the resulting owner-visible plan with the prior plan and explain every changed pairing.

## 10. Business completion

The mission is Business-complete only when a genuine new canonical event causes HERDMASTER to produce one refreshed practical breeding plan that:

- accounts for every eligible and held sow exactly once;
- uses the full available lifetime evidence chain without fabricating missing links;
- gives an interpretable primary/reserve or controlled trial;
- explains changed recommendations in farm language;
- is provider-confirmed delivered once;
- creates no mating or farm mutation;
- replays with zero duplicate effects;
- is reviewed by Charl as useful for the next physical placement decision.

CI, a PR, deployment, a handover or a synthetic fixture is not completion.
