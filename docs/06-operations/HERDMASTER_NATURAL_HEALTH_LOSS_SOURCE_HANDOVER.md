# HERDMASTER natural health and loss intake — source handover

## Mission state

Prepared (20%). This source-only contract is deliberately disconnected from Oom Sakkie, persistence, migrations, Telegram, n8n, Render, and every deployed route. It performs no I/O and grants no farm or protected-action authority.

## Prepared contract

`modules/pig_weights/herdmaster_natural_health_loss_intake.py` evaluates an already-authenticated owner report together with a complete canonical evidence packet. It returns:

- one exact canonical animal identity, or one precise Pig ID/tag clarification;
- `sick`, `injured`, `found_dead`, `farrowing_complication`, `piglet_loss`, or `compound_event`;
- separate observed facts, owner-suspected causes, owner-attributed veterinary evidence, and agent inference;
- an immediate welfare priority and at most one smallest missing-evidence question;
- explicit proposed effects across lifecycle, mating, litter, medical observation, movement/pen, availability, and downstream work;
- one before/after preview, its exact protected confirmations, and a deterministic operation identity bound to the provider message and canonical evidence generation;
- a fail-closed future transaction policy: all supported compound effects are atomic, exact-preview confirmation is required, and replay must change zero rows.

Unsupported facts remain Unknown and block only the affected effect. The evaluator never diagnoses illness, infers death or pregnancy, creates piglet identities, closes an unidentified mating, or treats stillbirth as death after live birth.

## Primary acceptance journey

For “Maya died yesterday after complications while farrowing. All 10 piglets were stillborn. We believe she had a uterine infection.” the generic evaluator:

- resolves `yesterday` in the provider timezone;
- preserves total born 10, born alive 0, stillborn 10, and later deaths 0;
- classifies uterine infection only as owner-suspected, not diagnosed;
- proposes death, active/availability, applicable mating, litter, observation, and downstream effects without executing them;
- leaves removal/disposal Unknown and asks only that irreducible question;
- requires confirmation of the exact consolidated preview before any future governed transaction.

Maya is test evidence only; no animal name or identifier is hard-coded in the contract.

## Later shared-adapter work

A separately authorized production mission must make the smallest shared Oom Sakkie integration changes after reconciling current main and claims. The adapter must:

1. authenticate and preserve provider message identity, timestamp, and timezone;
2. load complete canonical identity and chronology evidence plus a stable evidence-generation token;
3. call the pure evaluator and send only its privacy-minimal clarification or preview;
4. bind owner confirmation to the exact operation ID, preview, evidence generation, and required protected confirmations;
5. invoke a service-only serializable persistence function that revalidates all evidence, commits every supported compound effect atomically, and rolls back on mismatch;
6. persist deterministic idempotency evidence and prove direct and whole-message replay change zero rows;
7. refresh HERDMASTER recommendations only after a successful confirmed commit;
8. prove unrelated farm-state digests, protected actions, configuration, and specialist routes remain unchanged.

No shared registry, adapter, routing, configuration, migration, or CI-registration file is changed by this PR.

## Prepared Oom Sakkie preview adapter

`modules/oom_sakkie/herdmaster_health_loss_preview.py` is the smallest source-only bridge to the existing authenticated gateway authority. It accepts the opaque private-owner authority already issued by the Telegram gateway plus the provider message identity/time and complete canonical evidence, calls the zero-I/O evaluator, and returns either one privacy-minimal clarification or one human-readable consolidated preview. It neither routes nor sends messages, consumes confirmations, persists records, or creates a competing write path.

The future shared-router edit is intentionally deferred: after private-owner authentication, pass the existing gateway authority together with Telegram update/message identity, Telegram provider timestamp and timezone into `prepare_health_loss_owner_preview`; load canonical evidence through existing HERDMASTER/lifecycle/litter/observation projections; return `owner_text` through the existing reply transport. A later confirmation callback must validate the operation ID, evidence generation, protected-confirmation set, evaluator preview hash, and exact rendered `owner_text_sha256` in `confirmation_binding`, then delegate each already-governed effect to its canonical service inside one serializable coordinator. No generic health/loss writer is authorized.

## Required operational proof

Integration is not business-complete until an authenticated ordinary family report produces one correct preview, explicit owner confirmation produces exactly the previewed canonical effects once, replay creates zero rows, recommendations refresh, and farm-state digests prove zero unrelated mutations. Shared runtime must then be released to the named successor immediately.
