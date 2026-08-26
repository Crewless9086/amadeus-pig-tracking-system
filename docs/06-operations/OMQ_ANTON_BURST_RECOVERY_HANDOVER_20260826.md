# OMQ Anton Rapid Telegram Burst Recovery Handover — 2026-08-26

Mission lifecycle state: WORKING

Owner-visible outcome: every genuine Anton farm report keeps an independent
provider-bound lifecycle, reaches the correct protected preview, is recorded
exactly once only after its own confirmation, and is followed through without
Charl or Anton repeating already retained facts.

## Governance preflight

- Worktree: `.w/anton-burst-recovery`; branch
  `fix/anton-burst-correlation-20260826`; base/current authoritative main
  `b1dca216b3f95a640892f5cd1bce29cd95e62a81`.
- Standard: tracked blob `3002b94713e286c4eb2019419c438cc378c337fa`,
  SHA-256 `44e34c69145b83d2cd5b6a5322a6c2c124789fa647e19f19b3e39a7293a5202b`,
  883 physical lines, read completely.
- Protocol: tracked blob `8fbd0b9c9160164e31a17a2cbfa51ab88792a909`,
  SHA-256 `d4eb4b54a660ce39dfc92cb0fa253b0f2e3d7314462984702602d0f4b66a7e0a`,
  249 physical lines, read completely.
- Runtime Programme: tracked blob
  `fb44d7f86c47e605c283ed33c28ba2c4267d6edb`, SHA-256
  `721281eeacc33ae11877ce610fe7a76ba06de6b75db4573f64933073fd358309`,
  226 physical lines, read completely.
- Feedback template: tracked blob
  `1233aee625e45821a685614a33b1eb101c666ffd`, SHA-256
  `6d81bdfd41770f30e7e2e9acea584e747e007fe3ab155d3427fb17599a26111f`,
  221 physical lines, read completely.

## Fresh read-only reconciliation

Observed 2026-08-26 from Supabase under a read-only transaction. No Telegram
send, callback, replay, confirmation, farm write or hardware action occurred.

| Report | Provider/canonical result | Recovery state |
| --- | --- | --- |
| Pig 146 dead on 2026-08-23 | Pig `PIG-2026-E58B` is still Active/on farm. No claim or lifecycle result exists in the inspected burst. | Missing lifecycle/preview/confirmation; preserve the supplied fact and recover from attributable provider chronology. Do not ask Anton to repeat the death/date. |
| Mona: 12 total, 1 stillborn on 2026-08-26 | Provider message `4051` created independent mission `OOM-HERD-LITTER-13CC42C781683097EF1BBF7D`; preview/card `4053` correctly binds Mona `PIG-2026-D050`, 11 born alive + 1 stillborn, mating `MAT-2026-4B4E74`. Claim is delivered but expired/unconfirmed; no new litter row exists. | Re-preview from the retained provider event/current canonical evidence, then request only confirmation of that exact preview. Do not repeat counts/date/mother. |
| `Linds 3 kleintjies dood` | Provider `4052` is retained as its own waiting lifecycle but identity was unresolved. | Superseded only for spelling/identity by the later exact Linda provider report; preserve as corroborating chronology, never as a separate additional three deaths. |
| Linda: three piglets died on 2026-08-26 | Provider `4054` is retained under independent mission `OOM-HERDMASTER-C74BDE99E970D4ABA97DC493`, correctly resolves Linda `PIG-2026-5AA8`, but the generic health evaluator interpreted the sow as the subject and asked what happened to Linda. No litter-loss record exists. | Reusable semantic/action defect. Bind the active Linda litter as subject, preserve count 3/date, and obtain only any facts the canonical piglet-death action genuinely requires (specific tagged piglets, or valid sex/count allocation for untagged piglets). Do not ask who Linda is or how many died. |
| Linda first treatment on 2026-08-25 | No medical event dated 2026-08-24 or later was found in the inspected canonical treatment rows. | Outstanding. Do not infer products, dose, route, batch, recipient coverage or completion. Ask only the smallest missing treatment fields after current active-litter readback; reuse the existing protected first-treatment action and PR #1291 lineage. |
| Pig 138 dead/removed/buried on 2026-08-26 | Provider `4055` opened the case, `4057` added exact removal/burial, card `4058` was confirmed through provider callback `7672064839568633510`; canonical `PIG-2026-6BB3` is Dead/on_farm false with exit 2026-08-26 and lifecycle event `LIFE-HL-14C031928489C6B8ED1C71A2`. | BUSINESS result for this one report only. Do not replay, re-preview, reconfirm or ask any fact again. |

## Reusable defect and bounded source preparation

Independent inbound rows and protected claims can coexist. The unsafe shared
boundary is free-text continuation selection: when several health cases are
open in one chat, the resolver previously attached an entity-free, unthreaded
reply to the newest waiting case. Chronology proves only that a reply came
later; it does not prove which case was meant. In addition, semantic bare
entity references such as `138` were not matched to already canonical context
tags unless the text repeated `pig/tag/vark`.

The bounded candidate now:

- refuses newest-case fallback when multiple cases remain open;
- requires reply-card, exact operation identity or unique explicit/semantic
  entity binding; otherwise it preserves every case and asks one clarification;
- accepts a semantic bare reference only when it exactly equals one open
  canonical context tag; and
- adds rapid-burst regression tests proving unthreaded ambiguity and exact-138
  binding while preserving the independent Pig 146 lifecycle.

Focused result: `33 passed` in
`tests/test_oom_sakkie_herdmaster_health_loss_runtime.py`.

This correction does not yet implement the separate Linda active-litter
piglet-death semantic/action adapter or recover missing provider delivery for
Pig 146. Technical progress is not an owner outcome.

## Exact recovery instructions

1. Do nothing for Pig 138; it is already canonical and exactly-once complete.
2. Do not resend any of the five original facts. The deployed recovery must
   adopt the attributable provider rows where they exist and create fresh
   current preview identities rather than replay old claims.
3. For Mona, show a refreshed exact preview and ask only to confirm/correct it.
4. For Pig 146, recover the original provider event if provider chronology can
   prove it; show one exact death preview and ask only its still-missing
   removal/disposal fact (if canonical/provider evidence has not supplied it)
   plus the protected confirmation.
5. For Linda's three deaths, bind the report to Linda's current active litter.
   Ask only for identities or sex/count allocation that the canonical
   piglet-death action cannot derive. The supplied count and date are known.
6. For Linda's first treatment, current readback must first establish active
   piglets and any partial existing medical evidence. Ask only for missing
   product(s), dose/route/batch when required by policy, and whether every
   eligible piglet received it; never infer these from the phrase “first
   treatment.” Present one protected exact preview before recording.
7. Process each recovery lifecycle serially for human clarity, but keep all
   other cases durably queued. A later reply must bind by replying to its card
   or naming its exact sow/pig/tag. Provider message speed must never change
   ownership, identity or effects.

## Operational reality and authority

- Operational actor: deployed Oom Sakkie -> deployed HERDMASTER canonical
  action spine.
- Genuine trigger: Anton's retained provider messages and later natural
  confirmation through his authenticated private Telegram identity.
- Terminal may implement, test, review, deploy and observe only.
- Terminal must not send owner messages, confirm claims, write farm data,
  manufacture provider evidence or replay the burst.
- Runtime autonomy for this recovered queue is not proven; current honest state
  is `WORKING / event evidence retained / deployed completion incomplete`.
- Standing authority preserves Anton's own farm-manager attribution and
  protected confirmation; it does not allow Charl or the terminal to confirm
  Anton's claims.

## Forward pipeline

- Current mission: recover Anton's burst and repair reusable per-message
  correlation/lifecycle isolation.
- Next: Linda active-litter piglet-death adapter using the existing canonical
  litter-death action; reconcile PR #1291 first-treatment journey without a
  second writer.
- Later: deploy, perform fresh provider-origin recovery previews, obtain only
  genuine confirmations, verify canonical readback/replay containment and one
  later terminal-independent multi-message cycle.
- Automatic promotion trigger: exact-head independent review approval and free
  serialized release lane; provider recovery then resumes without owner fact
  repetition.

Owner action requested now: none. Any later confirmation must be shown only
after current evidence is reconstructed into a correct exact preview.

