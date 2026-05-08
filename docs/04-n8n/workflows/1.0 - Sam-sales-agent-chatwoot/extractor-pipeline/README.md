# Order Intent Extractor pipeline (`1.0`)

Hybrid flow: optional **`gpt-4.1-mini`** proposes bounded JSON intent; **Code** validates and merges **`order_state.requested_items[]`** before **`Code - Decide Order Route`**.  
**Partial-stock multi-band** path also relies on **deterministic** parsing of Sam’s last turn into **`last_agent_offer.caps`** and on **`Code - Build Order State`** / **`Code - Build Sync Existing Draft Payload`** — the extractor is **not** required for **`nearby_band_*`** when **`sam_text_parse`** succeeds.

## Files

| Workflow node | Source `.js` file |
|---|---|
| `Code - Build Extractor Inputs` | `Code-Build-Extractor-Inputs.js` |
| `Code - Should Run Extractor` | `Code-Should-Run-Extractor.js` |
| `Code - Invoke Order Intent Extractor` | `Code-Invoke-Order-Intent-Extractor.js` |
| `Code - Validate Extractor Output` | `Code-Validate-Extractor-Output.js` |
| `Code - Merge Extractor Into Order State` | `Code-Merge-Extractor-Into-Order-State.js` |
| `Code - Build Sync Existing Draft Payload` | `Code-Build-Sync-Existing-Draft-Payload.js` |

## Inject embedded code into `workflow.json`

From this directory (**`extractor-pipeline/`**):

| Script | Updates node(s) |
|--------|------------------|
| `python apply_extractor_inputs_patch.py` | **`Code - Build Extractor Inputs`** only (safe, no graph changes). |
| `python apply_sync_existing_payload_patch.py` | **`Code - Build Sync Existing Draft Payload`**. |
| `python patch_build_order_state_nearby_bands.py` | **`Code - Build Order State`** — nearby-band extract + **`mergeAdjacentBandsWithOfferCaps`**. Prefer when that node drifted from repo; backup **`workflow.json`** first on production copies. |
| `python apply_extractor_patch.py` | **Full extractor chain** — recreates extractor nodes (**new IDs**); use when (re)seeding subgraph, not for small JS edits. |

After any inject, **re-import** **`../workflow.json`** into n8n if your live workflow is not git-linked.

---

## Sam text fallback (`last_agent_offer` · `sam_text_parse`)

Built in **`capsFromSamText`** from **last `Sam:`** line (`lastSamMessage`) when Steward **`sync_results`** / **`results`** do not populate caps.

Coverage (keep in sync with **`Code-Build-Extractor-Inputs.js`**):

- **`N available in [the] X–Y kg`** (optional **`range` / `ranges`** after **`kg`** where applicable).
- **`N (more) in [the] X–Y kg`** (optional **`more`**; plural **`ranges`**).
- **`N [pigs\|weaners\|piglets] in X–Y kg`** (bullets or inline).
- **`N in the X–Y kg band`**, **`keep the N from X–Y kg`**, exact-band / weaner exact phrasing, etc.

**Common failure modes (fixed in repo 2026-05-08):**

- Only **`pigs`** in regex → **`weaners`** bullets dropped → **`caps`** lacked **7–9** / **15–19**.
- **`there are N available…`** duplicated **`N available…`** counts → inflated one band (**removed `reThereAre`** overlap with **`reAvail`** in extractors).

If **`extractor_skip_reason`** = **`no_reconstructable_last_agent_offer`** or **`caps`** is too small: extend **`capsFromSamText`** (and **`extractAdjacentBandOffersFromTranscript`** mirroring patterns) rather than patching only one node.

---

## Rollback (`EXTRACTOR_ENABLED`)

Disable the extractor without editing workflow JSON (where the host allows):

- Self-hosted: set **`EXTRACTOR_ENABLED=false`** (or `0`, `no`, `off`) on n8n process. **`Code - Should Run Extractor`** sets **`extractor_skip_reason`** = **`extractor_disabled_env`**.

**n8n Cloud:** reading **`$env` / `process.env`** may throw; toggle is treated as unset → extractor **enabled**. Bypass extractor nodes in the graph if you must disable.

---

## Extractor LLM design contract

- **Closed-world JSON:** **`Code - Validate Extractor Output`** permits only top-level keys in its **`ALLOWED`** set (**`target_total`**, **`per_band_caps`**, **`accept_nearby_bands`**, **`commitment_flag`**, **`confidence`**, **`evidence_quote`**, **`extractor_notes`**); any other keys fail validation (**`unknown_keys:*`** violations).
- **When it runs:** **`Code - Should Run Extractor`** requires **`AUTO`**, human-exposed draft context, non-empty **`last_agent_offer.caps`**, **`EXTRACTOR_ENABLED`** not disabling, **`pending_action`** not **`cancel_order`**, and other skip reasons documented in **`Code - Should Run Extractor`**. When skipped, deterministic **`sam_text_parse`** + **Build Order** paths still operate.
- **Merge:** **`Code - Merge Extractor Into Order State`** maps validated **`per_band_caps`** onto **`order_state.requested_items`** as **`extractor_band_*`** and sets follow-through flags so **`Build Order State`** / sync nodes can align with Steward and transcript caps.

---

## Live test checklist (partial stock · multi-band)

1. Import repo **`workflow.json`** into **n8n 1.0**.
2. Thread: customer orders **Q** weaners in primary band → Sam explains **partial** + **nearby** bands with countable lines (see Sam **PARTIAL-STOCK BULLET FORMAT**).
3. Customer short confirm: **“Yes, please make it total Q.”**
4. On the item downstream of **`Code - Build Extractor Inputs`**, **`last_agent_offer.caps`** must list **every** alternate band Sam quoted (**`7_to_9_Kg`**, **`15_to_19_Kg`**, **`10_to_14_Kg`** cap as relevant).
5. **`order_state.requested_items`**: **`primary_1`** + **`nearby_band_1`** + **`nearby_band_2`** … with **remainder** split across bands (typically lighter band first).
6. **`sync_payload.requested_items`** matches **step 5** after **`Code - Build Sync Existing Draft Payload`** (watch **`sync_payload_nearby_items_enriched`** when signature changes).
7. **`Call 1.2 - Sync Order Lines`**: per-**`request_item_key`** rows; inventory may still **`partial_match`** if stock < cap.

**Extractor LLM path (optional):** if **`extractor_error`** (e.g. Cloud **`getCredentials`**), **`extractor_merge_applied`** may be false — **step 4–6** should still pass on regex + Build Order logic.
