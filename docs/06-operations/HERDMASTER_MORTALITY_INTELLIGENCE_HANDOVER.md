# HERDMASTER mortality intelligence source handover

## Boundary

The pure evaluator remains zero-I/O. The successor integration adds a read-only canonical loader and consumes the typed packet through Oom Sakkie's existing authenticated farm-manager boundary and existing append-only review rail. It adds no route, queue, writer or Telegram path and cannot write mortality/lifecycle/medical facts, diagnose disease or prescribe treatment. Existing authenticated intake, preview, confirmation and P0 lifecycles remain authoritative.

## Evidence as at 2026-08-03

The bounded read-only reconciliation used an inclusive 90-day period of 2026-05-06 through 2026-08-03; the rolling 30-day window begins 2026-07-05 and the 7-day window begins 2026-07-28.

The 3 August fixture contained 16 dated current loss identities after treating PIG-2026-1AC2 / LIT-2026-A523 as superseded. Current production reconciliation no longer supports that disposition: A523 and B1A8 are both current representations of the same litter signature and the disposition rail is empty. The loader therefore marks deaths attached to either unresolved duplicate representation conflicting and excludes only those conclusions. Thirty raw historical Dead/Died identities have no attributable exit date; each remains `insufficient_evidence` and outside rolling counts rather than receiving an invented date or cohort classification.

The historical identity list remains fixture lineage, not current production truth. The live loader derives identities from `current_canonical_pigs` plus raw historical mortality rows on every assessment, retains future-dated rows for explicit evaluator exclusion, and labels noncurrent historical rows superseded. Exact current 7/30/90 counts must be established by the authenticated live proof after deployment.

Reproducible current signals include:

- LIT-2026-9E4A: three dated later deaths (PIG-2026-44C1, PIG-2026-6F78, PIG-2026-CA66) plus undated loss representations. The three had attributable newborn treatment records; this proves records, not treatment exposure as cause.
- LIT-2026-EB92: two dated later deaths (PIG-2026-72B7, PIG-2026-69B2) plus undated loss representations. Both have attributable newborn treatment records and declining last recorded weights; causality is not established.
- LIT-2026-A523 and LIT-2026-B1A8 currently share one sow/boar/farrowing signature without an authoritative disposition. Their attached losses are conflicting for intelligence until HERDMASTER resolves that separate governed data-integrity state.
- PIG-2026-BCEB (tag 125) died 2026-08-02 after a 6.2 kg to 5.8 kg last-step decline. It remains part of the completed authenticated Oom Sakkie lifecycle evidence, not a new case.
- ROOTLINE observed rollups cover 72 days from 2026-05-22 to 2026-08-02 (about 90.6% average daily coverage), including several observed cold nights. Forecasts remain separate and cannot prove exposure. Water observations on 2026-08-01 report storage/reservoir state Unknown; silence does not prove continuity or interruption.

The historical baseline is not reliable: canonical lifecycle recording became complete too recently for a stable prior 90-day comparison; numerous Dead/Died rows lack an attributable exit date/reason; duplicate/superseded litter representations exist; and no stable time-varying herd-at-risk denominator exists. Only dated event counts and explicitly supported associations may be published.

## Oom Sakkie integration

`modules/pig_weights/herdmaster_mortality_evidence.py` reads canonical current/historical deaths, litters, weights and observed weather in a read-only transaction. `modules/oom_sakkie/herdmaster_mortality_runtime.py` authenticates the existing manager authority and persists `review_identity`, `evidence_digest` and `deduplication_key` on the existing review rail. Unchanged evidence suppresses another notification; material evidence refreshes stable lifecycle `HERDMASTER-MORTALITY-CURRENT`. `farm_manager_runtime.py` folds the resulting work item into the existing consolidated brief. No direct owner-send path exists.

Operational proof must show canonical inclusion/exclusion, exact 7/30/90 counts, forecast/observation separation, current-versus-superseded litter handling, one concise family assessment, unchanged replay suppression, and zero farm/medical/lifecycle/Telegram writes.

## Mission stage

- Prepared: yes
- Integrated: yes; PRs #723/#724 are live at merge `c1913270a0ae16f2cfb971ecc9c6b5db0bacfdcc`
- Operational: read-only authenticated consumption proven; provider-confirmed owner presentation pending the next genuine request
- Business-complete: no
