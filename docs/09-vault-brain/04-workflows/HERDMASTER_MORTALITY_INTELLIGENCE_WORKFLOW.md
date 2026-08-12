# HERDMASTER Mortality Intelligence Workflow

Status: owner-approved post-P0 capability direction

## Outcome

Oom Sakkie and HERDMASTER must turn governed health and loss records into useful farm-management intelligence. Support both natural on-demand requests and proactive surveillance. Identify defensible patterns, explain uncertainty, ask only for evidence that could materially change the assessment, and recommend proportional action without presenting correlation as diagnosis or cause.

This capability starts only after the Oom Sakkie P0 operational spine passes its genuine end-to-end gate. The recent cluster of pig deaths is the first real analysis journey, not a one-off implementation tied to particular animals.

## Family experience

An authenticated, authorized family member may ask naturally in Afrikaans or English. Oom Sakkie must acknowledge the request and return one concise management assessment. Charl must not assemble exports, operate specialist terminals, translate messages, or visit separate herd, weather and weight pages.

When evidence crosses a governed surveillance threshold, Oom Sakkie should raise the review proactively.

## Evidence and analysis

HERDMASTER must reconcile, where available:

- deaths, illness, injury, stillbirth, crushed deaths and farrowing complications;
- rolling 7-, 30- and 90-day counts against an evidence-backed baseline;
- age, lifecycle, sex, breed, sow, boar, litter and cohort;
- pen occupancy, movements and shared exposure windows;
- longitudinal weights, growth trajectory and freshness;
- symptoms, observations, treatments, medication and withdrawal;
- feed changes, feed access, water availability and drinking observations;
- surviving penmate and littermate condition;
- missing, conflicting, duplicate or stale records.

ROOTLINE contributes separately attributable observed weather, power and water-continuity evidence. Forecasts remain separate from observations. Missing optional evidence blocks only its associated conclusion.

The result must separate:

1. **Proven facts** supported by canonical or authenticated evidence.
2. **Detected patterns** reproducible counts, clusters, timing or trajectories.
3. **Ranked hypotheses** with confidence, supporting evidence and counter-evidence.
4. **Unknowns** that are unavailable, stale, conflicting or unattributable.
5. **Next discriminating evidence** most likely to distinguish the hypotheses.
6. **Recommended actions** for welfare, husbandry, inspection, biosecurity, records or veterinary escalation.
7. **Reassessment trigger** that refreshes the analysis.

Compare affected animals with appropriate surviving controls where evidence permits. State small samples, recording gaps and changing herd composition clearly.

## Causality and authority

The system may report clustering and plausible associations. It must not claim that weather, feed, medication, infection, genetics or another factor caused a death without governed authoritative evidence. Never infer diagnosis, treatment, time of death, exposure or recovery from silence. Immediate welfare takes priority over retrospective analysis.

Read-only analysis does not authorize farm-record changes, treatment, medication, movement, culling, mating, customer communication or hardware control. New observations use the existing health/loss preview and confirmation rails. Analytical hypotheses never become canonical diagnoses or causes of death.

## Proactive surveillance

Triggers may include mortality above baseline; shared pen, litter, cohort or exposure; weak growth before loss; repeated symptoms; or meaningful weather, water, feed or movement overlap. Each trigger creates or refreshes one deduplicated review identity. Do not send one alert per animal or repeat unchanged advice.

## First operational proof

After P0 completion, use the genuine recent-deaths period to:

1. enumerate included and excluded events;
2. calculate a baseline or explain why it cannot be calculated;
3. analyse litter, pen, age, weight, health/treatment and ROOTLINE evidence;
4. provide confidence-ranked findings and counter-evidence;
5. ask at most one grouped question;
6. deliver one provider-confirmed Oom Sakkie assessment;
7. perform zero unsupported mutations;
8. prove unchanged evidence produces no duplicate review;
9. define the next automatic reassessment trigger.

Business completion requires an owner-useful assessment or an honest evidence-backed conclusion that no reliable pattern can yet be established. Source, tests, packets or containment alone do not complete the mission.
