# Matings and Breeding Read-Model Regression Checklist

## Status and scope

Owner-approved preparation artifact. No implementation, production mutation or acceptance event is authorized by this checklist.

Use with `MATINGS_ACTIVE_EXPOSURE_UI_SIMPLIFICATION_PLAN_20260812.md`. HERDMASTER proves canonical projection and eligibility; Codex/UI proves presentation and interaction.

## Canonical production cases

Preserve these five 2026-08-12 active exposures exactly once:

| Sow | Boar | IN | Planned UIT | Expected farrowing |
|---|---|---|---|---|
| Sophie | Bola | 2026-08-12 | 2026-08-28 | 2026-12-04 through 2026-12-20 |
| Olive | Tyson | 2026-08-12 | 2026-08-28 | 2026-12-04 through 2026-12-20 |
| Shupe | Tyson | 2026-08-12 | 2026-08-28 | 2026-12-04 through 2026-12-20 |
| Lucy | Tyson | 2026-08-12 | 2026-08-28 | 2026-12-04 through 2026-12-20 |
| Lolly | Prince | 2026-08-12 | 2026-08-28 | 2026-12-04 through 2026-12-20 |

Before using the table, reconcile current production identities and the authoritative current name for `PIG-2026-069E`; the table is owner context, not permission to rename an animal.

## HERDMASTER read-model regression gate

- [ ] Owner-authenticated `/api/pig-weights/matings` returns a separate human-readable sow name, sow ID, boar name and boar ID.
- [ ] No ID is placed into a name field.
- [ ] All five active cycles return `By beer`/typed active-exposure meaning.
- [ ] `mating_date` and exact service remain empty or Unknown for window-based exposure.
- [ ] IN, planned/actual UIT, service window and farrowing window remain separate facts.
- [ ] The five cycles are neither duplicated nor rewritten.
- [ ] Legacy exact-date mating rows retain their established projection.
- [ ] Anonymous access does not gain protected data merely to match owner-session enrichment.
- [ ] The exact browser request used by `/matings` consumes the corrected owner-authorized response.

## Active-exposure eligibility gate

- [ ] Each active exposure start without a matching actual removal is excluded before cohort scheduling.
- [ ] Sophie, Olive, Shupe, Lucy and Lolly appear exactly once under `Tans by beer`.
- [ ] None appears in `Plaas Nou`.
- [ ] None appears in `Volgende Groep`.
- [ ] Same-day plan generation cannot reschedule a placement already completed that day.
- [ ] A later date inside the exposure interval cannot reschedule the sow.
- [ ] Planned UIT reaching its date does not manufacture actual removal.
- [ ] After genuine actual removal, the next state follows canonical cycle rules and does not automatically create another placement.

## Litter/pregnancy precedence gate

- [ ] Molly's attributable `LIT-2026-5C36`, farrowed 2026-08-11, controls her current state.
- [ ] Molly shows nursing/post-litter while her litter is unweaned.
- [ ] Molly does not show current pregnancy, ready placement or generic unresolved evidence.
- [ ] Her historical pregnancy remains preserved in history.
- [ ] Bella's nursing case resolves through the same rule family.
- [ ] Distinct litter dates and evidence remain distinct.
- [ ] Governed weaning advances current state without a second manual lifecycle write.

## Body-condition eligibility gate

- [ ] Reconcile the exact latest valid, non-superseded 2026-08-11 observation for Bonnie, Waki, Zigay and Teena.
- [ ] Read threshold values from the shared authoritative breeding policy.
- [ ] Fresh below-minimum or above-maximum evidence blocks placement.
- [ ] Below-threshold sows appear exactly once under recovery/hold with score and observation date.
- [ ] None appears in `Plaas Nou` or `Volgende Groep` while outside the governed range.
- [ ] Weaning chronology, calendar date, capacity and earlier recommendation cannot override the gate.
- [ ] Missing/stale condition becomes `Needs current condition`, not ready and not assumed poor.
- [ ] Time alone cannot clear recovery hold.
- [ ] Later attributable in-range evidence can restore readiness review but cannot create placement automatically.
- [ ] Body condition is not treated as genetic merit, fertility proof or pregnancy evidence.

## UI acceptance gate

- [ ] The page uses the approved dashboard shell, navigation, tokens and Afrikaans terminology.
- [ ] The active-exposure section is entirely absent with zero active groups.
- [ ] With active groups it is compact, task-oriented and subordinate to the overall breeding register.
- [ ] Each active group shows names, IN, planned UIT, current pen and due/upcoming/overdue meaning.
- [ ] `Teken werklike UIT aan` is the only primary group action.
- [ ] Protected preview appears only after the action is chosen.
- [ ] Internal `MAT-EXPOSURE-*`, exposure identities, hashes and governance wording are secondary technical evidence.
- [ ] Individual window-based cards show names, `By beer`, IN, UIT, farrowing range and pen.
- [ ] Legacy exact-date cards use an appropriate exact-date layout.
- [ ] Current and historical cycles for one sow are distinguishable rather than appearing as duplicates.
- [ ] Empty, loading, stale, error, awaiting-confirmation and successful states are usable.
- [ ] Desktop/laptop and mobile screenshots show no clipping, overflow or unexplained whitespace.
- [ ] Charl approves the faithful local sample before deployment.

## Safety and completion gate

- [ ] Read-model and UI verification causes zero farm writes.
- [ ] Existing protected grouped action remains preview-bound, atomic and replay-safe.
- [ ] No removal, service, conception, pregnancy, movement or litter is inferred.
- [ ] Deployment and synthetic tests are not called Business completion.
- [ ] Final business proof waits for a genuine owner-visible page journey and, for removal, a genuine physical UIT journey.
