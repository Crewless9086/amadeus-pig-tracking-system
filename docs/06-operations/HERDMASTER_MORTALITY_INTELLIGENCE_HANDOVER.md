# HERDMASTER mortality intelligence source handover

## Boundary

Prepared source only. The evaluator consumes complete, already-canonical evidence and performs zero I/O. It does not register a route, read production, write mortality/lifecycle/medical facts, send Telegram, diagnose disease, or prescribe treatment. Existing authenticated Oom Sakkie intake, preview, confirmation, manager composition, and P0 lifecycle remain authoritative.

## Evidence as at 2026-08-03

The bounded read-only reconciliation used an inclusive 90-day period of 2026-05-06 through 2026-08-03; the rolling 30-day window begins 2026-07-05 and the 7-day window begins 2026-07-28.

Canonical rows contain 16 dated current loss identities in the 90-day period after excluding superseded Zigay representation PIG-2026-1AC2 / LIT-2026-A523. These comprise 3 stillborn identities, 2 deaths after live birth, 2 crushed deaths, and 9 other dated deaths. The resulting dated counts are 1 in 7 days, 13 in 30 days, and 16 in 90 days. At least 29 additional Dead/Died identities have no attributable exit date and are excluded from rolling counts, not silently assigned a date.

Reproducible current signals include:

- LIT-2026-9E4A: three dated later deaths (PIG-2026-44C1, PIG-2026-6F78, PIG-2026-CA66) plus undated loss representations. The three had attributable newborn treatment records; this proves records, not treatment exposure as cause.
- LIT-2026-EB92: two dated later deaths (PIG-2026-72B7, PIG-2026-69B2) plus undated loss representations. Both have attributable newborn treatment records and declining last recorded weights; causality is not established.
- LIT-2026-B1A8: one stillborn and two crushed-after-birth identities. LIT-2026-A523 and its child identities are superseded history and must never create a second current cluster.
- PIG-2026-BCEB (tag 125) died 2026-08-02 after a 6.2 kg to 5.8 kg last-step decline. It remains part of the completed authenticated Oom Sakkie lifecycle evidence, not a new case.
- ROOTLINE observed rollups cover 72 days from 2026-05-22 to 2026-08-02 (about 90.6% average daily coverage), including several observed cold nights. Forecasts remain separate and cannot prove exposure. Water observations on 2026-08-01 report storage/reservoir state Unknown; silence does not prove continuity or interruption.

The historical baseline is not reliable: canonical lifecycle recording became complete too recently for a stable prior 90-day comparison; numerous Dead/Died rows lack an attributable exit date/reason; duplicate/superseded litter representations exist; and no stable time-varying herd-at-risk denominator exists. Only dated event counts and explicitly supported associations may be published.

## Later Oom Sakkie integration

Pass a normalized evidence packet into `build_mortality_intelligence`, then publish its concise assessment through the existing specialist-consumption/manager boundary. Do not add a router or direct owner-send path. Persist the review identity and evidence digest at the existing delivery/dedup boundary: unchanged evidence suppresses another alert; material evidence refreshes the same review identity. The single grouped question should ask about surviving affected penmates/littermates and any feed or water interruption only when those facts remain Unknown.

Operational proof must show canonical inclusion/exclusion, exact 7/30/90 counts, forecast/observation separation, current-versus-superseded litter handling, one concise family assessment, unchanged replay suppression, and zero farm/medical/lifecycle/Telegram writes.

## Mission stage

- Prepared: yes (20%)
- Integrated: no
- Operational: no
- Business-complete: no
