# HERDMASTER first real mortality assessment — 2026-08-03 cutoff

Status: source/read-only assessment. No delivery or farm mutation.

## Authoritative cutoff and counts

All evidence is bounded at `2026-08-03T23:59:59+02:00`. The preserved supported counts remain 1 confirmed dated loss in 7 days, 13 in 30 days and 16 in 90 days. The 90-day period is 2026-05-06 through 2026-08-03 inclusive. Pig 127 / PIG-2026-D13C is authenticated owner-reported mortality evidence pending its existing governed lifecycle; it is not included as canonical mortality. Zigay's A523 cohort remains superseded history.

The 16 included canonical identities remain exactly those enumerated in `HERDMASTER_MORTALITY_INTELLIGENCE_HANDOVER.md`.

## Complete undated accounting

No existing evidence supplies a biological event date for any of these rows. Import creation/update timestamps are technical provenance only.

**Legitimate undated historical loss (12):** PIG-2026-0D33, PIG-2026-31D2, PIG-2026-465B, PIG-2026-63C7, PIG-2026-6617, PIG-2026-6711, PIG-2026-8FEC and PIG-2026-D5EE from LIT-2026-6EC0 (10 born alive, 2 weaned); PIG-2026-4972 and PIG-2026-C60A from LIT-2026-8A0F (8 born alive, 6 weaned); PIG-2026-2ED8 and PIG-2026-2FE0 from LIT-2026-G6R2 (11 born alive, 9 weaned). Cohort arithmetic supports the loss count but not dates or causes.

**Conflicting (15):** PIG-2026-0BDD, PIG-2026-15E2 and PIG-2026-F870 (LIT-2026-9E4A); PIG-2026-CD55 and PIG-2026-CD56 (LIT-2026-EB92); PIG-2026-2516 (LIT-2026-1025); PIG-2026-2186 (LIT-2026-75EE); PIG-2026-98AE (LIT-2026-741E); PIG-2026-AC21 (LIT-2026-68D1); PIG-2026-5B63, PIG-2026-5B64 and PIG-2026-5B65 (LIT-2026-0LBF); PIG-2026-3AEA, PIG-2026-6E8D and PIG-2026-6E8F (LIT-2026-OTY0). In each group, adding the undated identities to dated deaths exceeds the litter's attributable born-alive/weaned loss count. They remain historical conflicting representations, not silently deduplicated.

**Insufficient evidence (3):** PIG-2026-E926 has an imported Died status but its litter has no weaned count; PIG-2026-8EA1 and PIG-2026-C4D8 have imported Died status and longitudinal records but no attributable litter/control count or lifecycle event. No duplicate/superseded identity exists among these 30, and none can be reclassified as an attributable dated loss.

## Patterns and limitations

- Litter clustering is reproducible for 9E4A (three dated later deaths), EB92 (two dated later deaths), and canonical B1A8 (one stillborn and two crushed deaths). A523 is excluded.
- Weak/stalled or declining last-step growth overlaps several losses, including 69B2, 6D24, 6F78 and BCEB. Counter-evidence: other affected animals lack comparable fresh weights, some surviving peers also fluctuate, and no controlled growth threshold or diagnosis is present.
- Several confirmed deaths overlap adequately covered observed cold nights. Counter-evidence: exposure is farm-level rather than individual, warm/intermediate days also occur, exact housing protection is Unknown, and forecast evidence is excluded.
- Treatment rows prove attributable records, not beneficial or harmful causal exposure. Feed-change, feed-access, drinking and water-continuity observations remain insufficient. ROOTLINE water observations report Unknown states; silence proves neither continuity nor interruption.
- Pen and movement history is incomplete for many affected and surviving controls, so a pen-specific causal claim is unsupported.

No defensible herd-at-risk denominator can be reconstructed historically. `pigs.status` and `on_farm` are current mutable snapshots; most deaths have no effective exit date; the lifecycle rail was introduced after much of the period; and there is no complete immutable daily membership/stage interval. Minimum future requirement: every canonical animal must have effective-dated, immutable entered/on-farm, lifecycle-stage-change and exited/off-farm events, with supersession semantics and daily projection coverage.

## Ranked hypotheses — not diagnoses

1. **Moderate confidence: early-life/litter vulnerability merits investigation.** Supported by multiple losses within three litters. Contradicted/limited by small groups, conflicting imported identities, different event types and missing comparable observations from survivors.
2. **Low-to-moderate confidence: weak or declining growth may identify vulnerable piglets.** Supported by attributable pre-loss trajectories in a subset. Limited by missing/freshness differences and surviving animals with fluctuating weights.
3. **Low confidence: cold exposure may have coincided with vulnerability.** Supported by observed ROOTLINE cold nights near some losses. Limited by incomplete individual exposure, housing, feed/water and survivor evidence; causality is not established.

## One grouped owner question

For the surviving littermates and penmates from the affected groups, are they eating, drinking, moving and breathing normally now, and was there any shared feed or water interruption around the losses?

## Proportional actions

1. Inspect surviving affected littermates/penmates once for appetite, drinking, movement and breathing; escalate serious signs or a further loss promptly for veterinary assessment.
2. Verify current feed access and water continuity for those groups without inferring that either caused prior deaths.
3. Record only genuinely observed abnormalities through the existing governed health/loss preview and confirmation path.

Automatic reassessment: refresh the same review identity when a canonical mortality/lifecycle event, attributable survivor observation, weight, movement, feed/water record, treatment record or observed ROOTLINE exposure materially changes. Unchanged evidence suppresses a new alert.

## Oom Sakkie-ready English

Over the last 90 days we can confirm 16 dated losses: 13 were in the last 30 days and one in the last seven. The clearest pattern is that some losses group within the same litters, and a few affected piglets had stalled or falling weights. Several losses also fell near observed cold nights. These are warning signals, not proven causes. Thirty older loss records have no trustworthy death date; 12 are supported as historical losses, 15 conflict with litter totals or dated records, and three remain too incomplete to classify. Pig 127's owner report stays separate until its existing record process completes.

Actions: check the surviving affected littermates and penmates for appetite, drinking, movement and breathing; verify their feed and water access; seek veterinary help promptly for serious signs or another loss. Question: For those survivors, are they normal now, and was there any shared feed or water interruption around the losses?

## Oom Sakkie-ready Afrikaans

Oor die laaste 90 dae kan ons 16 gedateerde verliese bevestig: 13 was in die laaste 30 dae en een in die laaste sewe. Die duidelikste patroon is dat party verliese binne dieselfde werpsels groepeer, en 'n paar aangetaste varkies se gewig het gestagneer of gedaal. Verskeie verliese was ook naby waargenome koue nagte. Dit is waarskuwingstekens, nie bewese oorsake nie. Dertig ouer verliesrekords het geen betroubare sterfdatum nie; 12 word as historiese verliese ondersteun, 15 bots met werpseltotale of gedateerde rekords, en drie bly te onvolledig om te klassifiseer. Pig 127 se eienaarsverslag bly apart totdat die bestaande rekordproses klaar is.

Aksies: kyk na die oorlewende aangetaste werpsel- en hokmaats se eetlus, drink, beweging en asemhaling; bevestig hul voer- en watertoegang; kry vinnig veeartsenyhulp by ernstige tekens of nog 'n verlies. Vraag: Lyk daardie oorlewendes nou normaal, en was daar enige gedeelde voer- of wateronderbreking rondom die verliese?

## Integration boundary

Use `build_oom_sakkie_mortality_packet` from the HERDMASTER producer and pass the typed packet to the existing specialist-consumption/manager boundary. Persist `review_identity`, `evidence_digest` and `deduplication_key` at the existing delivery dedup rail. Do not create a route, queue, direct Telegram sender or writer. The future proof must show one bilingual-capable assessment, at most three actions and one question, unchanged replay suppression, Pig 127 separation, and zero farm/medical/lifecycle writes.
