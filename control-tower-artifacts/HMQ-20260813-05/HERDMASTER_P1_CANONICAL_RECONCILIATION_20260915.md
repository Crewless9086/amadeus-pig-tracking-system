# HERDMASTER P1 canonical reconciliation — 2026-09-15

## Evidence boundary

At `2026-09-15T16:10:09.339406Z`, one repeatable-read transaction proved
`transaction_read_only=on` and read the ten retained priority-one manager cases,
their exact pigs/litter, welfare and lifecycle events, recent observations, and
bounded manager-case events. Every section succeeded. The transaction rolled
back; there were no farm, task, mission, configuration, permission, or physical
operation writes and no provider sends.

The ten existing `OOM-CASE-*` identities all remain present. Recent claim,
delivery-suppression, exception, and reassessment events show scheduler activity;
they do not establish farm work or close any case.

## Results by retained case

| Existing case | Canonical result that can be resolved now | Evidence still required |
|---|---|---|
| `OOM-CASE-005CCF213CF11F3AAE44BF28` — pig 146 welfare | `PIG-2026-E58B` is still canonical **Active/on farm**; welfare case `WELFARE-92AA99CDA8F0ECEE98AE8FF9` is **open/urgent**. The retained death report therefore conflicts with current canonical lifecycle, rather than proving this welfare case complete. | A protected mortality re-preview and genuine scoped owner confirmation if the historical death must be recorded; then canonical lifecycle readback. Until that happens, obtain a fresh physical welfare observation because the living record remains active. |
| `OOM-CASE-06F41E4EF440CC20585E312C` — Waki | The newest canonical observation remains BCS 2 on 2026-08-24, superseding BCS 1 on 2026-08-11. No newer observation exists. | Fresh observed condition, appetite, movement, and welfare. Historical improvement to BCS 2 cannot establish current recovery. |
| `OOM-CASE-0AA47A67BCA8B781902CEF95` — `PIG-2026-3EE5` mortality follow-up | Death is canonical: **Dead/off farm**, lifecycle event `LIFE-HL-0D1EC2654FB93120EB55B4F7`, effective 2026-08-23, operation `HERD-HEALTH-LOSS-036F552C93AFF1E3F2B5610A8D1AF8CC`. Its living-welfare case is canonically closed by death. The death must not be recorded again. | A fresh observation of remaining animals and exact outstanding follow-up actions. |
| `OOM-CASE-0F6334544590218757B7A013` — Prince physical observation | Prince is canonical **Active/on farm**. The monitoring welfare case exists. The most recent observation is the 2026-08-24 owner report that he was eating, standing, moving, and behaving normally; that historical report does not answer the current physical question. | One fresh physical observation: what is now observed about Prince (`PIG-2026-E057`)? |
| `OOM-CASE-941B596A6526D7C63FABA58B` — Linda piglet losses | Linda’s saved litter `LIT-OOM-D7F1943733BEDCE0` is canonical and active: 9 total born, 8 born alive, 1 mummified, and eight generated piglets all still **Active/on farm**. There is no supersession, lifecycle loss, or related operational receipt in the bounded read. Reports 4052/4054 say three piglets died on 2026-08-26 and remain preserved with `canonical_effect:none`; the saved farrowing is not evidence that those losses were recorded. | Identify the exact affected piglets or the minimum remaining loss detail, create a fresh protected litter-loss preview, obtain genuine scoped confirmation, then verify canonical pig/litter readback. Do not replay farrowing. |
| `OOM-CASE-B59577B008D2E358F64F8771` — two-death cluster | Both deaths are canonical and separate: `PIG-2026-3EE5` via `LIFE-HL-0D1EC2654FB93120EB55B4F7`, and `PIG-2026-6BB3` via `LIFE-HL-14C031928489C6B8ED1C71A2`. Each living-welfare concern is closed by its own death. The grouped case may link these facts but must not merge identities or replay either death. | Fresh remaining-animal observations and the exact status of each follow-up action. |
| `OOM-CASE-CC21227E8D19954412953DE7` — retained pig 146 mortality | Identity is resolved: tag 146 maps to `PIG-2026-E58B`. Canonical data contains no death lifecycle event or operational receipt and still says Active/on farm. Provider report 3926 remains preserved with no canonical effect. | Fresh protected mortality preview using the retained date/report, genuine scoped confirmation, and matching canonical readback. A new generic identity question is unnecessary. |
| `OOM-CASE-CC6916A02E4A6819DE9AC514` — Linda welfare | Linda is canonical **Active/on farm**; `WELFARE-590484EA3FD5AF45AE6EBEE1` remains **monitoring/watch** with its last event on 2026-08-26. | Fresh observed sow condition and current litter-care/welfare facts. |
| `OOM-CASE-D2D021AD952D54D4EBB16689` — Teena | The newest canonical observation remains BCS 2 on 2026-08-24, superseding BCS 1 plus a skin concern on 2026-08-11. No newer observation exists. | Fresh observed condition, appetite, movement, skin, and welfare. Historical BCS improvement cannot establish current recovery. |
| `OOM-CASE-E083BF22E3A135A96ED75CE5` — Prince monitoring | `WELFARE-499AC31B1561E8AF5D8DF87D` remains **monitoring/watch**. The manager case still has an expired 2026-08-26 lease. This can be reconciled operationally by the existing cadence while preserving the case identity and linking the separate physical-observation case. | The same fresh Prince observation required by `OOM-CASE-0F6334544590218757B7A013`; do not merge the two case identities or treat a renewed lease as the welfare outcome. |

## Holds and follow-through

Canonical death existence is now resolved for `PIG-2026-3EE5` and
`PIG-2026-6BB3`. Their follow-up outcomes remain open pending real observations.
Pig 146 and Linda’s reported losses have resolved identities and exact canonical
gaps, but any new mortality/loss recording remains behind the existing protected
preview and owner-confirmation path. Prince, Linda, Waki, and Teena require fresh
physical observations.

All first-treatment, weaning, migration, permission, and physical-operation holds
remain unchanged. Scheduled HERDMASTER activity may refresh or reassign the exact
cases; it may not turn priority, a claim, a delivery receipt, or elapsed time into
a completed farm outcome.

Machine-readable canonical evidence is retained in
`P1_CANONICAL_HERD_RECORDS.private.json`; it contains private operational data and
must stay in the sealed local evidence folder.
