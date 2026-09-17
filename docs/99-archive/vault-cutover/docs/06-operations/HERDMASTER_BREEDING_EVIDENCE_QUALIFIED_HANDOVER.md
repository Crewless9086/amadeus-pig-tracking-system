# HERDMASTER evidence-qualified breeding handover

Status: Prepared / source-only / unmerged
Evidence cutoff: 2026-08-05T20:57:11.737242+00:00
Governance SHA-256: `F3BA9290E25F1F2C2B754E5733A1B642886A97E216C0355F86F8109F549B0F81`
Farm writes, mating actions, Telegram sends, shared-runtime activity: zero

## Outcome and authority

`herdmaster_breeding_recommendation_v1` is a pure evaluator. It accepts a
complete already-authorized evidence packet and returns one explained state and
next action per sow/gilt, every boar's qualification or exact exclusions,
English/Afrikaans owner text, and a material-evidence digest. It has no I/O,
delivery, observation-write, mating, medical, lifecycle, movement, availability
or reservation authority.

No current sow-to-boar pairing is actionable at this evidence cut. That is a
real evidence result, not a generic failure: every one of the 54 possible
female/boar pairs lacks complete attributable family trees, and every current
boar has Unknown breeding availability, Unknown withdrawal clearance and no
current structural-soundness observation. Female-specific gaps are retained
separately and missing evidence blocks only the unsupported decision.

## Exact current sow/gilt inventory

All 18 are canonical, Active, on farm, Sow, and Breeding purpose. The canonical
read projection did not expose a current pen for any of them. Medical projection
was Clear for all; withdrawal clearance and affirmative breeding availability
were Unknown for all. Parent IDs were absent for all bounded pedigrees.

| Female | Pig ID | Latest weight | Current reproductive state and next action |
|---|---|---:|---|
| Baby | `PIG-2026-7DAA` | 76.8 kg, 2026-07-20 | Inconclusive cycle, mating `MAT-2026-9EFC4E` on 2026-05-19; retain scheduled reproductive-status reassessment, no mating recommendation. |
| Lolly | `PIG-2026-94B9` | 54.6 kg, 2026-07-20 | Current status after 2026-05-18 litter is Unknown; establish current cycle and inspect. |
| Lucy | `PIG-2026-1248` | 90.8 kg, 2026-07-20 | Current status after 2026-05-30 litter is Unknown; 2/10 weaned is a material performance signal, not a diagnosis. |
| Olive | `PIG-2026-069E` | 89.8 kg, 2026-07-20 | Current status after 2026-05-05 litter is Unknown; establish current cycle and inspect. |
| Shupe | `PIG-2026-34BF` | 72.2 kg, 2026-07-20 | Current status after 2026-05-18 litter is Unknown; establish current cycle and inspect. |
| Sophie | `PIG-2026-5FA6` | 75.6 kg, 2026-07-20 | Current status after 2026-06-02 litter is Unknown; establish current cycle and inspect. |
| Mona | `PIG-2026-D050` | 116.0 kg, 2026-07-20 | Assumed Pregnant from attributable owner visual evidence against `MAT-2026-4B4E74` (2026-05-02); proportional farrowing preparation, never clinical confirmation, no new mating. |
| Mysikind | `PIG-2026-21BE` | 119.0 kg, 2026-07-20 | Assumed Pregnant from attributable owner visual evidence against `MAT-2026-140A06` (2026-05-02); proportional farrowing preparation, never clinical confirmation, no new mating. |
| Maya | `PIG-2026-5EB0` | 93.0 kg, 2026-07-06 | Current governed Pregnant result against `MAT-2026-7C2C8C` (2026-04-24); monitor the cycle. No inference from the earlier acceptance-example wording. |
| Teena | `PIG-2026-74FF` | 94.8 kg, 2026-06-22 | Nursing, litter `LIT-2026-1350` on 2026-07-02; protect nursing work and reassess after weaning. |
| Linda | `PIG-2026-5AA8` | 78.4 kg, 2026-06-22 | Current cycle Unknown and weight stale at cutoff; weigh and establish current cycle. |
| Bonnie | `PIG-2026-5376` | 79.2 kg, 2026-06-22 | Nursing, litter `LIT-2026-812B` on 2026-07-08; no mating review. |
| Waki | `PIG-2026-7531` | 99.2 kg, 2026-06-22 | Nursing, litter `LIT-2026-0538` on 2026-07-05; no mating review. |
| Bella | `PIG-2026-8F76` | 199.4 kg, 2026-06-29 | Historical pregnancy result does not establish current state; current reproductive-status review first. |
| Zigay | `PIG-2026-EEAC` | 85.6 kg, 2026-06-22 | Nursing/current canonical litter `LIT-2026-B1A8` on 2026-07-10; `LIT-2026-A523` is superseded history and cannot act as another current cycle. |
| Clovy | `PIG-2026-42B7` | 131.0 kg, 2026-07-06 | Historical pregnancy result does not establish current state; current reproductive-status review first. |
| Molly | `PIG-2026-B87A` | 109.2 kg, 2026-06-29 | Historical pregnancy result does not establish current state; current reproductive-status review first. |
| Ms Piggy | `PIG-2026-92F3` | 126.4 kg, 2026-05-19 | Post-weaning recovery after `LIT-2026-322B`; BCS 2, lean, normal movement, no visible injury and difficult temperament observed 2026-07-28. Weight is stale; recovery is not cleared. |

## Exact current boar inventory

| Boar | Pig ID | Age | Latest weight | Canonical state | Known service history | Current exclusions |
|---|---|---:|---:|---|---|---|
| Bola | `PIG-2026-8645` | 521 days | 97.8 kg, 2026-07-20 | Active, on farm, Breeding, medical Clear; pen Unknown | 8 recorded services in the current female chronology; attributable litter outcomes include strong and weaker survival, while offspring growth/structure remains insufficient | Parents Unknown; availability Unknown; withdrawal Unknown; current structural soundness Unknown. |
| Prince | `PIG-2026-E057` | 307 days | 72.6 kg, 2026-07-20 | Active, on farm, Breeding, medical Clear; pen Unknown | 1 current service, Baby `MAT-2026-9EFC4E`; outcome unresolved/Inconclusive | Parents Unknown; availability Unknown; withdrawal Unknown; current structural soundness Unknown. |
| Tyson | `PIG-2026-3B5F` | 521 days | 103.2 kg, 2026-07-20 | Active, on farm, Breeding, medical Clear; pen Unknown | 6 recorded services; attributable outcomes include Bonnie 9 born alive, Lucy 10/2, Olive 8/6, Shupe 10/8, plus current/other cycles | Parents Unknown; availability Unknown; withdrawal Unknown; current structural soundness Unknown. |

No boar is called fertile, sound, genetically suitable, available, or clear by
silence. Historical growth labels are not genetic conclusions.

## First real explained assessment

1. **Mona and Mysikind:** active Assumed Pregnant cycles outrank mating review.
   Continue proportional farrowing preparation and monitoring. Their status is
   operational planning evidence, not a clinical result.
2. **Baby:** Inconclusive is an unresolved active cycle. Retain the smallest
   scheduled reproductive-status reassessment. Do not recommend another mating.
3. **Maya, Bonnie, Teena, Waki and Zigay:** current pregnancy/nursing context
   blocks mating review. Zigay's superseded litter is history only.
4. **Ms Piggy:** post-weaning recovery is not cleared; stale weight and BCS 2
   matter before any readiness decision.
5. **The other ten females:** establish current reproductive state first, then
   obtain one grouped current inspection covering body condition, legs/movement,
   visible concerns and heat observed/not observed. Already known facts are not
   requested again.

For every potentially reviewable female, Bola, Prince and Tyson are enumerated
individually. Each is excluded today for the same four attributable reasons:
incomplete pair-specific pedigree, Unknown availability, Unknown withdrawal
clearance and Unknown current structural soundness. Prior pairing/litter
performance remains visible for later ranking but cannot override those gates.

## Material gaps

- Current pen projection for all 21 breeding animals.
- Complete attributable mother/father/ancestor identity for all 21 animals;
  this blocks all 54 current pair comparisons.
- Governed breeding availability and withdrawal clearance for all 21 animals.
- Current boar legs/feet/build/visible-concern evidence.
- Current cycle plus grouped physical inspection for Lolly, Lucy, Olive, Shupe,
  Sophie, Linda, Bella, Clovy and Molly; Bonnie/Teena/Waki/Zigay wait on their
  current litter or recovery phase.
- Current weight for Linda, Bonnie, Waki, Zigay, Bella, Molly and Ms Piggy under
  the 30-day matching threshold at this cutoff.
- Attributable offspring growth and structural evidence per sire/litter. Litter
  counts and survival are preserved separately from growth and maternal effect.

## Source and tests

- `modules/pig_weights/herdmaster_breeding_recommendation.py`: pure evaluator,
  evidence categories, cycle precedence, all-boar ranking/exclusion, material
  digest, English/Afrikaans packet, zero authority.
- `tests/fixtures/herdmaster_breeding_attention_20260805.json`: sanitized real
  canonical evidence cut with newer governed Mona/Mysikind/Baby observations.
- `tests/test_herdmaster_breeding_recommendation.py`: preferred boar,
  relatedness, multiple ranking, none, missing pedigree, active cycle,
  Assumed Pregnant, Inconclusive, post-weaning, repeat service, hold, stale
  evidence, grouped observations, changed evidence, replay and real-cut tests.

## Existing Oom Sakkie consumer boundary

Do not create a router. During a later serialized integration window, the
existing owner-authenticated HERDMASTER manager loader in
`modules/pig_weights/mating_routes.py` must assemble the complete evidence
packet after `_build_breeding_attention_packets()`, call
`evaluate_breeding_attention`, and pass only its sanitized deterministic packet
through the existing HERDMASTER specialist-consumption boundary used by the Oom
Sakkie management adapter. The shared Oom registry, intent routing, Telegram
trigger and send path remain unchanged. No raw protected animal context may be
sent to an external composer.

## Serialized integration and live proof

1. Obtain an explicit Control Tower release; acquire and durably claim the lane.
2. Fetch/reconcile current `origin/main`; preserve the reviewed pure contract.
3. Make only the reviewed adapter call described above; refresh both reviews if
   the head or behavior changes. Require exact-head CI, normal merge,
   exact-merge CI, exact deployment lineage and HTTP 200 `/health`.
4. Capture database and provider before digests. Use one owner-authenticated,
   read-only Oom Sakkie breeding-management request through the existing route.
5. Prove all current females and boars reconcile, Mona/Mysikind remain Assumed
   Pregnant, Baby remains Inconclusive, active/nursing cycles suppress matching,
   and every unavailable pairing exposes its exact gaps. If later evidence
   qualifies a female and boar, show the ranking as a recommendation requiring
   a separate exact owner mating approval—never execute it.
6. Replay the same evidence and prove the same assessment identity, no duplicate
   recommendation/card, zero farm rows, zero protected actions and unchanged
   unrelated database/provider/configuration digests.
7. Release shared runtime immediately to the named successor and record exact
   deployment, proof and handover evidence.

Prepared is not Integrated, Operational or Business-complete. The first
business-complete acceptance still requires a real owner observation to change
the explanation safely, with no unintended farm mutation, through deployed Oom
Sakkie consumption.

## Successor canonical-evidence reconciliation (2026-08-06)

Successor status: Prepared / source-only / unmerged. PR #729 remains unchanged
at reviewed head `0046b84b4339da4c31fd2c1b54dee88d6b036b67`; its commit is retained
in this branch lineage as content-equivalent commit `7dcda909`. The successor
was reconciled onto `origin/main`
`45c74c06dc2e3b8a5a38e47e520790481b196290` after SAM PR #731. No runtime,
Telegram, farm write, mating action or protected action was used.

The earlier statement that all breeding pens were Unknown was a loader defect,
not an owner-data gap. `current_canonical_pig_state` and each latest valid
movement agree for all 21 breeders:

| Pen | Current breeders |
|---|---|
| D3 | Baby, Lolly, Lucy, Olive, Shupe, Sophie |
| D4 | Bola, Prince, Tyson |
| D5 | Mona, Mysikind |
| Kraam Saal 01 | Maya, Teena |
| Kraam Saal 02 | Linda |
| Kraam Saal 03 | Bonnie |
| Kraam Saal 04 | Waki |
| Kraam Saal 05 | Bella |
| Kraam Saal 06 | Zigay |
| Kraam Saal 07 | Clovy |
| Kraam Saal 08 | Molly |
| Kraam Saal 09 | Ms Piggy |

### Evidence classification

- **Present but omitted by the old loader:** all 21 current pens; 15 exact
  service records (Bola 8, Prince 1, Tyson 6); canonical litter outcomes and
  attributable child survival/growth rows where recorded; boar ages derived
  from canonical birth dates.
- **Recoverable deterministically:** a current pen only when current state and
  latest valid movement agree; parentage only from explicit dam/sire columns or
  an exact non-superseded litter origin; withdrawal end only from an
  attributable treatment date plus governed withdrawal days (with any recorded
  end required to agree); unreserved only under a complete-through ledger;
  pair performance only from exact sow/boar mating and litter identities.
- **Genuinely absent:** `mother_pig_id` and `father_pig_id` for Baby, Bella,
  Bola, Bonnie, Clovy, Linda, Lolly, Lucy, Maya, Molly, Mona, Ms Piggy,
  Mysikind, Olive, Prince, Shupe, Sophie, Teena, Tyson, Waki and Zigay. None has
  an attributable litter origin that supplies those links. This is 42 exact
  missing direct-parent links, not a generic family-tree gap.
- **Coverage unavailable, therefore Unknown:** the active-reservation sources
  contain no breeder references, but no complete-through breeding-reservation
  boundary exists; the breeder medical query contains no attributable event,
  but no complete-through withdrawal boundary exists. Silence proves neither
  unreserved nor cleared.
- **Stale/conflicting:** current and latest pen projections had zero conflicts;
  direct versus litter parentage had zero conflicts. Existing historical
  pregnancy results remain historical and do not establish a current cycle.
- **Physical family observations:** current heat, body condition, legs/movement
  and visible concerns for a genuinely short-listed female; current legs, feet,
  build and visible-concern evidence for a short-listed boar. These are not
  requested while system-side pedigree, reservation or withdrawal evidence
  already blocks the pair.

### Second real assessment

Assessment identity: `HERD-BREED-7D4D523649536A4C0DAC55DB634069A1` at the
2026-08-06 cutoff. It assessed 18 females and three boars. All 54 pair-specific
pedigrees remain Unknown because the exact parent links above are absent; none
is silently converted to unrelated. There are zero Recommended and zero
Possible-but-needs-one-observation pairings, and 18 female cases are currently
Not eligible for a pairing recommendation. This is precise containment, not a
claim that every management conclusion is blocked:

- Mona and Mysikind remain Assumed Pregnant against their exact 2026-05-02
  matings; proportional farrowing preparation continues and is not clinical
  confirmation.
- Baby remains Inconclusive; no additional mating is recommended.
- Maya's governed cycle, Bonnie/Teena/Waki/Zigay nursing work and Ms Piggy's
  post-weaning recovery continue to outrank a mating recommendation.
- Bella, Clovy, Linda, Lolly, Lucy, Molly, Olive, Shupe and Sophie require a
  current reproductive-state determination, but the evaluator does not ask for
  redundant physical inspections before the system-side pair gates are fixed.

English and Afrikaans outputs retain these distinct cycle states and every boar
assessment exposes its own inclusion/exclusion reasons. The evaluator and
reconciler both report zero writes and zero protected actions; unchanged input
and input-row reordering produce the same internal packet and assessment ID.

### Successor source and adapter handover

- `modules/pig_weights/herdmaster_breeding_evidence.py` is the new pure,
  deterministic, zero-I/O canonical reconciler. The existing authenticated
  manager read service must supply its rows; it is not a parallel database,
  router or writer.
- `modules/pig_weights/herdmaster_breeding_recommendation.py` now labels each
  case `recommended`, `possible_but_needs_one_observation`, or `not_eligible`.
  It asks the grouped physical question only when all female blockers are
  physical and at least one boar has cleared the independent pair gates.
- `tests/test_herdmaster_breeding_evidence.py` covers recovered and conflicting
  pens, complete and incomplete reservation coverage, withdrawal calculation
  and conflict, litter-origin parentage, exact pedigree exclusions, partial
  pedigree, one valid recommendation, proportional questioning and replay.

Later, during an explicitly assigned serialized window, extend only the
existing authenticated read assembly in `farm_supabase_read_service.py` and
`mating_routes.py` to provide current pig state, latest valid movement,
non-superseded litter origins, mating/litter/child performance, medical rows and
explicit reservation/withdrawal coverage markers to the reconciler. Publish
only its sanitized evaluator packet through the existing Oom Sakkie specialist
consumer. The live proof must show recovered pens, the preserved current-cycle
states, exact pair exclusions, no repeated owner fact, stable replay identity,
zero Telegram send by HERDMASTER, zero farm/protected writes and unchanged
unrelated state. Missing complete-through ledgers require a governed projection
improvement; they must not be replaced by owner questions or silence-based
  clearance.

## 2026-08-08 proactive-management successor

This source-only reconciliation used canonical production evidence through
2026-08-08 and current main `0691d78b9d55cd7ae6d43eff9411a50548cb13f1`.
It performed no delivery, protected action or farm write.
The external read-only capture is
`C:\tmp\herdmaster-breeding-recovery-evidence-20260808.md`, SHA-256
`EFFDB0B5753429EAF3B06A54394122513A15EAA4C88D1B5704FD1F0A3EB93C50`;
the values below are production evidence, not a committed synthetic fixture.

### Exact pedigree recovery matrix

All 21 breeder master records have attributable import provenance in
`GS-MIG-5-2026-06-29`, but none has a canonical dam, sire or litter-origin
link. No exact alias row supplies a missing link. Each row below is therefore
Unknown, without a duplicate or cyclic pedigree; the source row is identity
evidence only and must not be treated as parentage.

| Breeder | Pig ID | Source row | Dam | Sire |
|---|---|---:|---|---|
| Baby | PIG-2026-7DAA | 3 | Unknown | Unknown |
| Bella | PIG-2026-8F76 | 19 | Unknown | Unknown |
| Bola | PIG-2026-8645 | 15 | Unknown | Unknown |
| Bonnie | PIG-2026-5376 | 8 | Unknown | Unknown |
| Clovy | PIG-2026-42B7 | 2 | Unknown | Unknown |
| Linda | PIG-2026-5AA8 | 11 | Unknown | Unknown |
| Lolly | PIG-2026-94B9 | 6 | Unknown | Unknown |
| Lucy | PIG-2026-1248 | 13 | Unknown | Unknown |
| Maya | PIG-2026-5EB0 | 148 | Unknown | Unknown |
| Molly | PIG-2026-B87A | 17 | Unknown | Unknown |
| Mona | PIG-2026-D050 | 21 | Unknown | Unknown |
| Ms Piggy | PIG-2026-92F3 | 12 | Unknown | Unknown |
| Mysikind | PIG-2026-21BE | 20 | Unknown | Unknown |
| Olive | PIG-2026-069E | 5 | Unknown | Unknown |
| Prince | PIG-2026-E057 | 18 | Unknown | Unknown |
| Shupe | PIG-2026-34BF | 4 | Unknown | Unknown |
| Sophie | PIG-2026-5FA6 | 14 | Unknown | Unknown |
| Teena | PIG-2026-74FF | 10 | Unknown | Unknown |
| Tyson | PIG-2026-3B5F | 7 | Unknown | Unknown |
| Waki | PIG-2026-7531 | 9 | Unknown | Unknown |
| Zigay | PIG-2026-EEAC | 16 | Unknown | Unknown |

Recovered parent links: **0**. Genuinely missing parent links: **42**. All 54
internal sow/boar combinations remain unknown-related and cannot become mating
recommendations. Reservation and withdrawal ledgers both lack a complete-
through boundary for all 21 breeders, so negative status remains Unknown. The
absence of breeder order/allocation or medical rows is not clearance.

The live litter projection exposes both `LIT-2026-A523` and `LIT-2026-B1A8`
as non-superseded Zigay litters on 2026-07-10. The reconciler now fails this
same-sow/same-date chronology closed and removes it from the current-cycle
index. It changes neither record.

### Maximum-three management packet

Packet `HERD-BREED-MGMT-B0001DA9D68C8EB10773CE2DD67137D7` contains:

1. Zigay: resolve the exact duplicate current litter chronology through its
   governed data-quality rail; no physical observation is requested.
2. Mona, Mysikind and Maya: continue proportional farrowing preparation and
   grouped monitoring. Mona and Mysikind remain Assumed Pregnant planning
   states, not clinical confirmation. Observe progression, appetite, movement,
   discharge and labour/illness signs at the next normal round.
3. Baby: preserve Inconclusive and observe heat/non-heat and ordinary
   reproductive changes at the scheduled reassessment; do not remate.

Nursing and recovery cases remain supported in the full assessment and are not
erased merely because only three actions are published. The packet has stable
English/Afrikaans rendering, deterministic identity, zero I/O, zero delivery,
zero mating authority and zero write authority.

### Smallest recovery and safe fallback

Ask once for an attributable historical breeder register, import sheet,
purchase/birth record or other source naming dam and sire for any listed
breeder; if no such source exists, record once that historical parentage is
unavailable. Reservation and withdrawal coverage are system-owned projection
gaps, not questions for the family.

If pedigree is permanently unavailable, retain the internal pair blocks and
seek attributable pedigree/DNA evidence or an externally documented unrelated
boar. This is an owner-review proposal only: unknown is never silently treated
as unrelated and no mating is authorized.

### Later serialized integration proof

After ROOTLINE explicitly releases production, integrate the exact reviewed PR
normally, require exact-merge CI and exact deployment lineage, and feed the
existing authenticated Oom Sakkie specialist-consumption boundary with this
read-only packet. Prove the same 21 identities/pens, 15 services, 0/42 parent
links, incomplete clearance coverage, Zigay conflict containment, maximum
three actions, English/Afrikaans rendering, deterministic replay and zero
Telegram/farm/protected writes. Release the lane immediately afterward.
