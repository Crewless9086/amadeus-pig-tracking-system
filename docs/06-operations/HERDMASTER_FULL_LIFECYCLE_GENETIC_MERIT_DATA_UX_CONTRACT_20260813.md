# HERDMASTER full-lifecycle genetic merit data and UX contract

Date: 2026-08-13

Mission: `HMQ-20260813-04`

Status: proposed authoritative documentation/data contract; no source or UI implementation

Surfaces: herd `/breeding-analytics`; named animal `/breeding-analytics/<pig_id>`

## 1. Owner outcome and boundary

Charl must be able to see what the herd's attributable lifetime evidence says,
what it does not say, and what evidence should be reviewed next. The herd page
supports comparison and navigation. The named-animal page explains one animal's
chronology, partners, offspring and limitations. Both are read-only projections
over canonical Supabase facts.

This mission does **not** create a mating recommendation score, genetic ledger,
animal classification, movement, exposure, mating, service, conception,
pregnancy, treatment, sale, financial allocation or other farm fact. It does
not implement either UI. A later HERDMASTER data slice may implement the
read-model packet; a separately assigned CODEX UI slice may render that packet.

## 2. Reconciled historical evidence

The following clean retained artifacts are evidence, not implementation bases:

- `C:\tmp\herdmaster-lifetime-genetic-merit`, head `68cf41c4...`: unique
  mission-plan commit; retain as `released-retain`.
- `C:\tmp\herdmaster-lifetime-genetic-merit-stages1-3`, head `c1702487...`:
  four unique commits behind current main, exposed by open PR #823; retain as
  `released-retain` and do not merge or rebase.
- PR #823's `herdmaster_lifetime_genetic_merit.py` and tests remain useful pure
  evaluator/test design. They predate current exposure events, corrected
  observations, litter supersession, actual-weaning distinction, mortality
  chronology and current owner-read contracts. No source file from that PR is
  adopted by this documentation PR.

The historical plan's evidence axes and anti-causation rules are retained. Its
delivery-stage assumption that a detailed Weight/Breeding report alone is the
target is superseded by the owner's page-specific direction here.

## 3. Non-negotiable interpretation rules

1. Display authoritative animal name first. Show tag and Pig ID as secondary
   identity. If the name is genuinely Unknown, use the tag, then Pig ID.
2. Missing, unresolved or incomplete evidence stays `Unknown`; it is never
   converted to zero, failure, clearance or poor merit.
3. Every rate shows numerator, denominator, eligible/missing counts, cutoff and
   sample size. A percentage without its denominator must not render.
4. Current projections may select an effective fact while the evidence packet
   retains correction/supersession lineage and contradiction warnings.
5. Pair evidence, sow-across-partners evidence and boar-across-partners evidence
   remain separate. One parent's association with a litter outcome is not a
   genetic-causation claim.
6. Management, health, treatment, season, weather, environment, pen/feed,
   market channel and evidence coverage qualify comparisons. They must not be
   silently adjusted away or asserted as causes.
7. No simplistic `good/bad bloodline`, single merit score or traffic-light
   judgement is permitted. Axis summaries and confidence remain decomposable.
8. Current recommendation/placement eligibility stays owned by Breeding
   Attention. Analytics may link to it but cannot create or clear a hold.

## 4. Evidence availability matrix at current main

Status meanings: `available` is directly canonical; `derivable` requires a
bounded projection and stated conditions; `stale` exists but may not establish
current state; `conflicting` requires visible reconciliation; `missing` lacks
authoritative coverage; `not-authoritative` may be context only.

| Requested fact | Status | Current canonical source | Contract and limitation |
| --- | --- | --- | --- |
| Animal identity/name/sex/type/purpose/status | available | `current_canonical_pigs`, `pigs` | Name first; tag and Pig ID secondary; corrections govern current projection. Purpose/status are current management facts, not merit. |
| Dam/sire and family relationships | available/partial/conflicting | canonical pigs, litter parent IDs, `get_family_tree`, HERDMASTER pedigree reconciliation | Show known relationships and exact Unknown links. Cycles, duplicate identities or conflicting parents block pair-clear claims. Founder assumption is bounded doctrine, not invented pedigree. |
| Mating chronology | available | `mating_events`, current mating overview | Preserve event ID, sow/boar IDs, date, status and linked litter. A mating row is not automatically a completed service opportunity. |
| Physical exposure | available | `pig_breeding_exposure_events` | Start/end/actual removal and current exposure are distinct. A proposal is never physical placement; a 17-day exposure does not prove service or conception date. |
| Pregnancy checks | available/stale | mating event check fields | Show method, assessor, date/time and freshness when present. Historical pregnancy does not establish current pregnancy. |
| Conception/farrowing opportunity | derivable | mating/exposure plus authoritative linked litter | Count only complete-through opportunities with exact or unambiguous governed attribution. Silence is Unknown, not failure. |
| Litter counts | available with data-quality states | canonical litter overview, litter supersessions | Total born, born alive, stillborn and mummified remain nullable facts. Exclude superseded current rows but expose lineage/warnings. |
| Actual weaning | available/partial | actual-weaning evidence, piglet lifecycles, litter projection | Planned/legacy `wean_date` alone is not actual weaning. Use governed actual completion and exact child outcomes. |
| Weaned count/survival | derivable/partial/missing | governed litter count and exact child lifecycle | `weaned_count / born_alive` only when both are authoritative and compatible. Never substitute current on-farm children or coerce missing weaned to zero. |
| Weaning weight | available/partial | pig `wean_weight_kg`, exact wean date, weight events | Show covered/missing offspring, comparable age, mean, median, range and dispersion. Ordinary nearby weights are not relabelled weaning weights. |
| Post-weaning growth | derivable/partial | `pig_weight_events`, exact child/weaning identity | ADG only for positive elapsed time and compatible measures. Provide 30/60/90-day windows with tolerance and coverage; never rank unmatched ages as equivalent. |
| Pre-/post-weaning mortality | available/partial/conflicting | `pig_lifecycle_events`, effective mortality/corrections, mortality intelligence | Separate stages using dated authoritative events. Retain original and correction. Unknown cause stays Unknown. |
| Health/medical context | available/stale | `pig_medical_events`, withdrawal/medical projections | Context at animal/cohort/time; never infer genetic cause or clearance. Disclose incomplete chronology. |
| Human observations | available/stale/conflicting | append-only `pig_observation_events` including supersession | Show observer, observed date, factual note, source and effective/current marker. Preserve contradictory and superseded history. |
| Movement/environment/management | available/partial/not-authoritative for genetics | `pig_location_events`, pen, feed/weather/ROOTLINE evidence when attributable | Qualifying context only. Different pens, seasons, feed or illness reduce comparability; absence does not prove equivalence. |
| Current breeding state/holds | available | Breeding Attention operating loop/current exposure | Link/display context; analytics cannot place, clear, classify or assign a boar. |
| Lifetime destination | derivable/partial | lifecycle/current pig state, sale items, meat/auction evidence | Distinguish active growing, sold, auction, slaughter/meat, breeding retention, death/removal and Unknown. Selection/retention is not proof of merit. |
| Individual sale revenue | available only when exact | `sales_transactions`, `sales_transaction_items` | Use exact child item attribution and actual amounts only. Show channel/date/status. |
| Auction/lot financial outcome | available at lot level/partial | auction invoice-aware sale records | Never divide lot value into invented individual revenue. A labelled analytical cohort estimate is non-canonical and optional. |
| Costs and margin | missing/partial | only attributable cost rows that genuinely exist | Do not claim profit, margin or genetic financial superiority without compatible attributable feed, medical, labour and other cost coverage. Gross revenue is not margin. |
| Herd benchmark | derivable | same effective packet at cutoff | Use eligible comparable records only; disclose cohort rules, n, missing n, period and dispersion. Never benchmark an Unknown as zero. |
| Time trend | derivable/partial | dated litter, weight, lifecycle and outcome events | Minimum two comparable periods; display n and material source/coverage changes. A trend is descriptive association. |
| Pair/partner comparison | derivable/partial | exact pair matings/litters/outcomes | Show exact pair n beside each partner and animal-across-partners baseline. Do not credit/blame one parent or compare incomparable management without warning. |

### Current defect to replace, not copy

`build_breeding_analytics_from_evidence` currently uses `or 0` for nullable
`born_alive` and `weaned_count`. That legacy aggregate is acceptable only as a
known incomplete screen; the full-lifecycle packet must use explicit nullable
values and denominator eligibility. Existing current UI labels animals by tag/
ID rather than canonical name first. Both limitations are contract gaps, not
authority to rewrite historical facts.

### Read-only production inventory at 2026-08-13 cutoff

Authenticated production returned HTTP 200 for both current endpoints. The herd
payload contained 19 sow rows, 3 boar rows, 20 mating rows and 24 litter rows.
Its row contract exposes only tag/Pig ID, aggregate mating/pregnancy/farrowing/
litter counts, born-alive/weaned totals and survival. It does not expose names,
denominator eligibility, missing counts, confidence, trends, partner context,
offspring weights/growth, mortality, health/observations, destinations or
financial outcomes. The detail payload exposes animal, matings, litters and
data-quality flags but not the requested full lifecycle.

The live Supabase schema confirms the canonical tables/fields named in the
matrix, including parent/litter/wean fields on `pigs`; weight, location,
medical, litter, mating, lifecycle, observation and exposure events; item-level
sales; lot/invoice financial fields; and litter supersession lineage. Schema
presence is not completeness or attribution proof; every packet must still
measure actual eligible and missing coverage at its evidence cutoff.

## 5. Page-specific read-only packet

One backend contract version, proposed as
`herdmaster_full_lifecycle_merit_read_v1`, serves both pages. It is computed at
one `evidence_cutoff`, reports `writes_performed: false`, and includes source
progress/deadline state. It must fail unavailable rather than silently return
partial values as complete.

### 5.1 Shared envelopes

Each metric has:

- `status`: available / derived / unknown / stale / conflicting /
  not_authoritative;
- `value` plus `unit`, or null;
- `numerator`, `denominator`, `eligible_count`, `observed_count`,
  `missing_count` where applicable;
- `sample_size`, `period_start`, `period_end`, `evidence_cutoff`;
- `confidence`: High / Moderate / Limited / Unknown;
- `limitations`, `context_qualifiers`, and supporting event/animal identities.

Confidence is evidence confidence, never biological worth. Every axis carries a
versioned `confidence_rule_id`; initial rules are
`herdmaster_merit_confidence_v1`. Implementations may not reinterpret the
labels without a reviewed rule-version change:

- **High:** exact identity/attribution; zero unresolved contradiction; at least
  3 eligible independent opportunities/cohorts; at least 80% outcome coverage;
  and no known material management/season/environment comparability difference.
- **Moderate:** exact identity/attribution; zero unresolved contradiction; at
  least 2 eligible opportunities/cohorts; at least 60% coverage; comparability
  differences are known and explicitly bounded.
- **Limited:** exact identity/attribution but only 1 eligible opportunity/cohort,
  coverage below 60%, stale supporting context, or a material unresolved
  comparability difference.
- **Unknown:** denominator, attribution or governing evidence is missing or
  conflicting, or the axis cannot be classified deterministically.

An axis whose natural sampling unit is an individual offspring uses eligible
offspring as `sample_size`, but confidence remains capped at Limited when all
offspring come from only one litter/cohort. The packet discloses both offspring
and independent-cohort counts. Thresholds apply per axis; they do not combine
different biological measures into a score.

### 5.2 Herd page `/breeding-analytics`

Return:

- cutoff/source/data-quality summary;
- herd benchmark definitions and eligible/missing counts;
- separate sow and boar rows, names first;
- row axes: reproductive opportunities, attributable litters, born-alive,
  weaning survival, weaning quality, comparable growth, mortality/robustness,
  destinations and supported financial outcome;
- confidence/coverage badge, plain interpretation and material warning;
- current trend summary and named partners/pairs without collapsing them into
  one rank;
- `detail_href` for whole-row keyboard/pointer navigation.
- backend-owned route-safe navigation objects for related animal, litter and
  Breeding Attention targets: `{href, accessible_label, available,
  unavailable_reason}`. `href` is an internal absolute path or null; CODEX must
  not construct it from labels or IDs.

Default ordering is data-quality attention then name, not a genetic leaderboard.
Any alternate sort labels the chosen descriptive metric and retains Unknowns
outside numeric ordering.

### 5.3 Named page `/breeding-analytics/<pig_id>`

Return:

- canonical name, tag, Pig ID, sex/role and current management state;
- family graph: parents, siblings where attributable, mates and offspring;
- complete mating/exposure/litter chronology with exact partner names/IDs;
- offspring cohort table with born/weaned status, weights/growth, health,
  mortality, destination and financial coverage;
- pair comparison against the same animal with other partners and partner's
  comparable baseline;
- time-series values and event markers;
- current/superseded observations and relevant health/management context;
- data-quality warnings and missing-evidence tasks;
- plain-language interpretation.
- route-safe navigation objects for every displayed parent, sibling, partner,
  offspring and litter, plus the current animal's Breeding Attention target.
  Missing/unavailable targets render as non-link text with the supplied reason.

## 6. Plain-language interpretation contract

Every herd row and named profile must contain all four labelled sections:

- **Going well:** supported descriptive outcomes only, with n and period.
- **Needs attention:** supported adverse association or current management/data
  concern, not a genetic verdict.
- **Missing evidence:** exact absent denominator, attribution or comparable
  follow-up needed to interpret the axis.
- **Next review:** the next read-only reassessment trigger or physical evidence
  to record through its existing canonical action.

When no supported positive or adverse statement exists, **Going well** or
**Needs attention** uses neutral Unknown-safe copy (“No supported conclusion at
this cutoff”) rather than disappearing. Going well always gives n and period;
Needs attention stays non-causal; Missing evidence names the exact gap; Next
review names the trigger or existing canonical action. Empty headings are not
permitted.

Required qualifier form: “These offspring were associated with this parent/pair
under the recorded management and period. This does not establish genetic
causation.” Where health, season, environment or management context differs,
name it or state it is Unknown.

## 7. Chart specifications for later CODEX UI work

No chart is implemented by this contract PR.

1. **Outcome chain coverage:** horizontal staged counts—born alive, authoritative
   weaned, comparable weights, later outcomes—with missing counts, never a
   funnel that implies every missing child died.
2. **Time trend:** litter/cohort date on x-axis; metric and unit on y-axis;
   points sized/labelled by denominator; gaps for Unknown; correction markers.
3. **Partner comparison:** grouped dot/range plot per exact partner, with n,
   confidence and comparable-period qualifier; never causal “best boar/sow”.
4. **Growth:** individual or cohort weight against age/days since weaning;
   comparable windows shaded; no line across missing intervals.
5. **Survival:** counts and percentages together with born-alive denominator;
   Unknown weaned cohorts rendered as Unknown, not 0%.
6. **Financial:** exact attributable `gross_total` and, only when supplied by
   canonical `sales_transactions`, `net_settlement_payable`. Gross is the
   transaction amount before recorded VAT/commission/other deductions. Net
   settlement payable is gross including VAT less the explicitly recorded
   commission including VAT and other deductions; it is a channel settlement,
   not profit or contribution margin. Show the deduction fields and source
   sale/lot identity. If item-to-transaction attribution cannot support the
   requested animal/cohort scope, keep net Unknown. Costs/margin stay Unknown
   unless compatible attributable cost coverage exists. Lot values remain lot
   level.

All charts require accessible tabular equivalents, keyboard focus, text summary,
units, cutoff, sample size, missing count and source limitation.

## 8. Proposed backend read-model additions

HERDMASTER data implementation owns:

1. `load_full_lifecycle_merit_evidence(cutoff, pig_id=None)` using one bounded,
   read-only, repeatable snapshot over current canonical sources.
2. Effective litter/observation/lifecycle resolution that returns both current
   governing facts and lineage/warning metadata.
3. Opportunity eligibility projection so conception/farrowing denominators
   include only complete-through attributable opportunities.
4. Exact offspring cohort binding from canonical parent/litter identities.
5. Nullable survival/weaning aggregation and coverage disclosures.
6. Comparable-age/days-since-weaning growth projection with configurable,
   versioned tolerances.
7. Pair, parent-across-partner and herd benchmark projections with context
   qualifiers; no automatic merit score.
8. Exact financial attribution adapter that preserves item versus lot scope and
   declares cost coverage.
9. Versioned pure composer for herd rows and named profiles, deterministic from
   the same evidence cutoff.

Prefer service composition over a new table. Add a database view only if query
correctness/performance requires it, and never a writable ledger. Reuse existing
owner-read access and `/api/pig-weights/breeding-analytics*` routes or introduce
an explicitly versioned read endpoint without changing mutation authority.

## 9. CODEX UI handover boundary

After Control Tower assigns file ownership, CODEX UI may change only templates,
CSS, client rendering and browser tests for these two surfaces. It consumes the
approved packet and must not recalculate biological metrics, invent defaults,
infer causes, own access policy or write farm state.

UI acceptance must prove names-first identity; tag/Pig ID secondary; whole-row
navigation; mobile/desktop/table accessibility; Unknown-safe tables/charts;
denominator/sample/confidence disclosure; readable four-part interpretation;
links to existing animal/litter/Breeding Attention pages; no facelift-only
completion claim.

## 10. Validation plan for later implementation

### Pure/statistical

- missing born-alive or weaned count stays null and never enters denominator;
- partial cohort coverage reports observed/missing n;
- effective non-superseded litter/observation/lifecycle fact governs current
  projection while the superseded original and full lineage remain visible;
- silence never becomes conception failure or mortality;
- rates always equal disclosed numerator/denominator;
- median/dispersion and comparable-window growth use eligible records only;
- one excellent small litter remains visibly Limited confidence;
- exact pair, sow and boar views do not double-count;
- benchmark eligibility and time-period changes are disclosed;
- lot revenue is never divided into child revenue; missing costs block margin;
- deterministic repeat at same cutoff yields byte-stable semantic content and
  zero writes.

### Database-shaped

- disposable PostgreSQL fixture with corrections, conflicting parents,
  planned-versus-actual weaning, incomplete outcomes, health/observations,
  weight windows, mortality and item/lot sales;
- repeatable-read snapshot under concurrent appended evidence;
- query deadline/partial-source failure returns unavailable, not false zero;
- database counts unchanged before/after herd and animal reads.

### Route/security

- owner-read privacy for herd/detail JSON and page journeys;
- invalid/Unknown Pig ID fails closed without cross-animal leakage;
- no write service imported or invoked;
- dashboard/profile repeated GETs have zero farm effect.

### Browser/owner UX

- names first with tag/Pig ID secondary and Unknown fallback;
- whole row and keyboard navigation;
- backend-provided internal hrefs only; names-first accessible labels; null
  targets remain non-link text with an explicit unavailable reason;
- Unknown survival does not display 0%; denominators and sample sizes visible;
- chart gaps, accessibility tables and plain-language qualification visible;
- partner comparison never says a parent caused the outcome;
- mobile and desktop regressions for herd and named profile.

## 11. Stop and later completion boundary

This documentation PR stops before backend or UI implementation. Prepared means
the evidence contract is reviewed and merged. It is not Integrated,
Operational, Business-complete or Closed. Later business completion remains one
fresh material canonical event causing a useful, name-led, fully qualified
read-only reassessment without farm mutation or duplicate delivery.
