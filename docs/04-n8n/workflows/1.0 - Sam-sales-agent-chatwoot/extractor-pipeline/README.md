# Order Intent Extractor pipeline (`1.0`)

Hybrid flow: **`gpt-4.1-mini`** proposes bounded JSON intent; **Code** validates and merges **`order_state.requested_items[]`** before **`Code - Decide Order Route`**.

## Files

| Workflow node | Source `.js` file |
|---|---|
| `Code - Build Extractor Inputs` | `Code-Build-Extractor-Inputs.js` |
| `Code - Should Run Extractor` | `Code-Should-Run-Extractor.js` |
| `Code - Invoke Order Intent Extractor` | `Code-Invoke-Order-Intent-Extractor.js` |
| `Code - Validate Extractor Output` | `Code-Validate-Extractor-Output.js` |
| `Code - Merge Extractor Into Order State` | `Code-Merge-Extractor-Into-Order-State.js` |

After editing any `.js` file above, regenerate embedded code in **`../workflow.json`**:

```bash
python apply_extractor_patch.py
```

(Graph positions are recreated on each patch; adjust in n8n if needed.)

## Rollback (`EXTRACTOR_ENABLED`)

Disable the extractor without editing the workflow JSON:

- Self-hosted n8n: set environment variable **`EXTRACTOR_ENABLED=false`** (or `0`, `no`, `off`) for the n8n process and restart if required.
- When disabled, **`Code - Should Run Extractor`** sets **`extractor_skip_reason`** = `extractor_disabled_env` and the LLM is not called.

## Live test (Charl / ops)

1. **Import** the repo’s **`1.0 - Sam-sales-agent-chatwoot/workflow.json`** into n8n (replace or version the active workflow).
2. **OpenAI API key — not a Google Sheet row.** n8n stores it in **Credentials**:
   - In n8n: **⋮ Menu → Credentials →** open your existing **`OpenAi_Sales Agent`** credential (same one **OpenAi - Transcribe a recording** and **Sales Brain ChatGPT** use).
   - Paste the secret into **API Key** (or whatever label that credential shows). You never type `openAiApi.apiKey` literally — that is only the **field name inside the credential object** the Code node reads in JavaScript (`getCredentials("openAiApi")` → `apiKey`).
   - **`Code - Invoke Order Intent Extractor`** must use that credential: on import, workflow JSON attaches **`credentials.openAiApi`** pointing at **`OpenAi_Sales Agent`**. If your n8n copy uses a **different credential name/ID**, open the Invoke node → **Credential for OpenAI** → select your working OpenAI credential (same API key).
3. Open the **latest execution** (or **pin** a test conversation) and ensure **`EXTRACTOR_ENABLED`** is **unset** or **`true`**.
4. **WhatsApp thread** (realistic partial stock):
   - Customer: *“I want 8 weaners 10–14kg, any sex, collect Riversdale, Friday.”*
   - Sam: partial offer (*“only 3 in that exact band… 2 in 7–9… 2 in 15–19… make up to 8?”*)
   - Customer: **“Yes, please make up the 8.”** (or Afrikaans variant).
5. In the execution JSON, verify in order downstream of **`Code - Align Order Logic`**:
   - **`extractor_should_run`** = `true` (if AUTO, Draft, reconstructable **`last_agent_offer`**).
   - **`last_agent_offer.caps`** non-empty (**`extractor_inputs_built_at`** = `sync_results` preferred, else `sam_text_parse`).
   - **`extractor_raw_output`** parses to JSON schema fields.
   - **`extractor_validation.ok`** = `true` (**`confidence_final`** ≥ 0.6, **`per_band_caps`** aligned to offer).
   - **`extractor_merge_applied`** = `true`.
   - **`order_route`** after **`Decide`** = **`UPDATE_HEADER_AND_LINES`** (not **`REPLY_ONLY`** only reassurance).
   - Sheets / steward: **`ORDER_LINES`** updated for **`extractor_band_*`** keys consistent with capped bands (respect actual availability; totals may remain &lt; 8 if inventory is capped).
6. **Failure triage:**
   - **`extractor_error`** populated → credential, network, or OpenAI quota; fix and retry.
   - **`extractor_skip_reason`** = `no_reconstructable_last_agent_offer` → improve Sam wording regex in **`Code-Build-Extractor-Inputs.js`** or ensure **`sync_results`** are still on the item when present.
   - **`extractor_validation.ok`** false → inspect **`extractor_validation.violations`** and tighten prompt or loosen validator only with care.

Design and promotion criteria: **`planning/EXTRACTOR_INTENT_FIX.md`**.
