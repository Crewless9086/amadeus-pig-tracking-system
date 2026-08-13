# CMQ-20260813-03 grouped weight and movement reconciliation

Status: discovery

Owner: CORE, with HERDMASTER as farm-domain owner

Authority: read-only repository reconciliation at `03f6443bf6a13d0e4f6948debd3c944ec6b84b08` on 2026-08-13. This document authorizes no implementation, deployment, provider invocation, message, workflow change, or farm-data write.

## Evidence boundary

- **Documented/repository fact:** tracked source, migrations, tests and controlling documentation at the pinned commit.
- **Runtime-loaded fact:** none obtained in this slice. A route or environment-variable name in source is not proof that a deployed process loaded it.
- **Provider-verified fact:** none obtained; providers were not invoked.
- **Physical fact:** none obtained.

Consequently, “deployed” below means present in authoritative deployed-source lineage, not a new live-provider observation. Current production configuration, table counts and actual recent use remain Unknown.

## Canonical action map

| Entry/channel | Preview and confirmation | Execute/write owner | Canonical truth and replay | Finding |
|---|---|---|---|---|
| Application `/bulk-weights` | `static/js/bulkWeights.js` calls `/api/pig-weights/weights-batch/preflight`, then stages `/bulk-batches` and processes chunks. `pig_weights_controller.preview_bulk_weight_entries` delegates to the weight service. | `bulk_weight_batch_service.process_bulk_weight_batch`; when Supabase writes are available, `_process_one_row_supabase` writes `pig_weight_events` and optional `pig_location_events`. | `bulk_weight_batches` and `bulk_weight_batch_rows` stage/audit rows. Row identity is unique by `(batch_id,row_index)` and `idempotency_key`; event existence is checked before insert. Processing is row/chunk oriented, so the whole group is not one atomic transaction. Existing-batch recovery avoids restaging. | Canonical application rail, but not the same protected action service as OOM SAKKIE. |
| Application single movement | `POST /api/pig-weights/movements`; no grouped preview/confirm contract. | `create_movement_entry`, with Supabase-first support and legacy path retained. | Canonical target is `pig_location_events`; single-action replay/atomicity is narrower than the protected group contract. | Not a grouped-movement action and not channel-invariant with the grouped OOM flow. |
| Authenticated OOM SAKKIE typed or Telegram grouped weights, optionally naming one destination pen | `telegram_gateway.handle_telegram_gateway_message` calls `handle_grouped_weight_message`; `preview_grouped_herd_weights` resolves identities and `preview_bulk_weight_entries` performs the existing bulk preflight. A stored, expiring claim binds owner, private chat, provider message, evidence generation, exact payload and SHA-256 preview digest; callback/natural confirmation is single-owner claimed under row lock. | `execute_grouped_weight_claim` owns one database transaction, takes advisory locks for claim and every pig, rechecks canonical active/on-farm/current-pen state, then inserts batch, rows, weight events, optional location events and completes the claim. | `app_private.oom_protected_action_claims`, `bulk_weight_batches`, `bulk_weight_batch_rows`, `pig_weight_events`, `pig_location_events`, and `current_canonical_pig_state`. Exact callback replay is a no-op; executing recovery requires the same provider receipt; a changed row or existing same-date weight contains the claim. The group commits or rolls back as one database transaction. | Strongest current grouped weight/movement action. It reuses application preflight but not application staging/execution. |
| OOM SAKKIE browser typed/voice | Browser voice is transcription preparation only (`/api/oom-sakkie/voice/transcribe`); the returned text is placed into the same OOM input/send path. Browser speech recognition is another text-preparation fallback. | After text submission, authority depends on the OOM typed action router; voice itself has zero farm-write authority. | No audio-derived fact is canonical until the same typed preview/claim/confirmation contract accepts it. | Prepared channel convergence exists in source; runtime/provider readiness is Unknown. |
| Telegram voice | The private Telegram media rail can transcribe voice, but this scan did not find repository proof that its transcript is routed into the OOM grouped-weight protected action rather than the separate CHARLIE private runtime. | Unknown for grouped weights. | No channel-equivalence proof for a Telegram voice grouped-weight action was found. | Gap: do not claim voice parity. |

There is no separately implemented grouped-movement command. Movement is either an optional destination attached to each grouped-weight row (OOM), an optional/movement-only row in the application bulk batch, or a single movement endpoint. The owner journey therefore lacks one shared channel-invariant grouped-movement preview/confirm/execute contract.

## Supabase truth and guarantees

The canonical event identities are opaque `weight_event_id` and `location_event_id`; group audit identities are UUID `batch_id`/`row_id`; protected confirmation identity is a callback token plus mission, provider receipt, preview digest and evidence generation. Current state is projected through `current_canonical_pig_state`.

The OOM protected executor provides group atomicity through one database context/transaction, advisory locks on the claim and pigs, exact preview-digest equality, current-state revalidation and a single guarded transition from `executing` to `completed`. The application batch provides durable staging, per-row idempotency and resumable processing, but not all-or-nothing group atomicity. Its read-before-insert checks are useful replay guards but are not equivalent to the protected claim's serialized group contract. Production constraint/index parity and live table contents were not queried and remain Unknown.

## Retained authority and duplicates

- The Phase 0 register still classifies the Google Sheets farm master/write family as `migrate`: `WEIGHT_LOG` and `LOCATION_HISTORY` fallbacks can still affect runtime behavior. Source retains service fallbacks and legacy single/bulk helpers. Sheets therefore still possesses conditional business authority; it is not yet export-only.
- The provider-verified Phase 0 snapshot records active n8n OOM GateKeeper/assistant/backend relay paths and Sheets-bearing workflows. This slice made no fresh provider readback and cannot prove whether any currently handles grouped weights or movements. They remain retained/migrate according to the register, never new authority.
- Duplicate application implementations coexist: legacy `/weights-batch` direct save and durable `/bulk-batches` stage/process; Supabase-first row execution and Sheets fallback; single movement and batch optional movement; OOM atomic protected execution and application chunk execution.
- The contradiction is architectural rather than proof of duplicate production writes: multiple source paths can express the same business fact, while live callers and loaded configuration are Unknown.

## Existing ownership and file boundary

No open PR with “bulk weight” or “movement” in its title was returned on 2026-08-13. Four retained clean worktrees already contain related historical/cutover work: `bulk-weight-less-clicks` (`9622b4eb`), `bulk-weight-pen-confirmation` (`9427113d`), `weight-sheet-pen-separators` (`0b6ee799`), and `herdmaster-exposure-cycle-transition-20260812` (`5939489c`). Their heads produce no file delta against current `origin/main`, so their unique commits appear integrated; the worktrees were preserved.

Implementation would touch actively shared boundaries including `modules/pig_weights/pig_weights_routes.py`, `pig_weights_controller.py`, `pig_weights_service.py`, `bulk_weight_batch_service.py`, `farm_supabase_write_service.py`, `modules/oom_sakkie/grouped_weight_runtime.py`, `protected_action_claims.py`, `protected_action_runtime.py`, `telegram_gateway.py`, `static/js/bulkWeights.js`, migrations and focused tests. Control Tower must confirm these files are not presently owned by HERDMASTER, OOM SAKKIE, CODEX UI or another terminal before edits. No such clearance is inferred from clean historical worktrees.

## Smallest safe continuation

After Control Tower confirms a collision-free boundary, implement only a shared, side-effect-free canonical grouped-weight/movement **preview contract** and adapter-conformance tests. Keep both existing executors unchanged initially. Prove application typed, OOM typed and prepared browser-voice text normalize the same explicit rows, opaque pig/pen identities, date, digest and confirmation requirement; malformed/ambiguous facts fail closed; no preview writes; Telegram voice remains excluded until its routing is proven. This is smaller and safer than replacing either deployed executor or removing Sheets fallbacks.

Owner-visible acceptance journey: Charl enters the same clearly labelled non-production fixture through each in-process adapter test; each yields byte-equivalent preview rows/digest and the same “nothing recorded until confirmation” boundary; ambiguity yields one clarification; repository tests prove zero database/provider/Sheet calls. A later separately authorized implementation slice can bind both channels to one atomic executor and prove Sheets-unavailable operation.

## Completion boundary

This reconciliation completes discovery only. It does not complete Phase 0, the canonical cutover, deployment, production readiness or the Business outcome. No provider, runtime-loaded or physical evidence was created.
