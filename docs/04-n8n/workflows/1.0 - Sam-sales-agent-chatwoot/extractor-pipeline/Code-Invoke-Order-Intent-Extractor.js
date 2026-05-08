const itemIn = $input.first().json || {};

function clean(value) {
  return String(value || "").trim();
}

const SYSTEM_PROMPT = `You are the Order Intent Extractor for Amadeus Pig Sales.

Your only job: read the customer's latest message together with the most recent offer that the sales agent made, and emit ONE strict JSON object describing what the customer is committing to. You do not ask questions. You produce no prose. You invent nothing.

You will receive these inputs in the user message JSON:
- last_agent_offer: structured summary of the last stock offer (caps: weight_range keys must match verbatim).
- customer_message
- short_thread
- existing_draft_summary

Emit exactly one JSON object with keys: target_total (int|null), per_band_caps ([]), accept_nearby_bands (boolean), commitment_flag ("commit"|"tentative"|"cancel"|"none"), confidence (0-1), evidence_quote (string), extractor_notes (string max 200).

Hard rules:
1. Every per_band_caps[].weight_range MUST appear verbatim in last_agent_offer.caps. Never rename bands.
2. per_band_caps[].qty <= matching cap.max_qty from last_agent_offer.caps.
3. target_total <= last_agent_offer.offered_total when offered_total is not null.
4. Sum per_band_caps qty <= target_total when target_total is set.
5. If not order-related, commitment_flag = "none" and leave numerics empty/null.
6. evidence_quote MUST be a verbatim substring of customer_message supporting the extraction or "".

Language: English or Afrikaans. Keep evidence_quote verbatim.

Return JSON only — no markdown, no extra text.`;

if (itemIn.extractor_should_run !== true) {
  return [
    {
      json: {
        ...itemIn,
        extractor_call_skipped: true,
        extractor_raw_output: null,
        extractor_latency_ms: 0
      }
    }
  ];
}

async function runExtractor(ctx, item) {
  const userPayload = {
    last_agent_offer: item.last_agent_offer,
    customer_message: clean(item.customer_message || item.CustomerMessage),
    short_thread: item.extractor_short_thread || "",
    existing_draft_summary: item.existing_draft_summary || null
  };

  const started = Date.now();
  let credentials;
  try {
    if (typeof ctx.getCredentials === "function") {
      credentials = await ctx.getCredentials("openAiApi");
    } else if (ctx.helpers && typeof ctx.helpers.getCredentials === "function") {
      credentials = await ctx.helpers.getCredentials("openAiApi");
    } else {
      throw new Error("No getCredentials helper on execution context");
    }
  } catch (err) {
    return {
      ...item,
      extractor_raw_output: null,
      extractor_error: String(err && err.message ? err.message : err),
      extractor_latency_ms: Date.now() - started
    };
  }

  const apiKey = credentials.apiKey || credentials.secret || credentials.openAiApi;
  if (!apiKey) {
    return {
      ...item,
      extractor_raw_output: null,
      extractor_error: "openAiApi credential missing apiKey",
      extractor_latency_ms: Date.now() - started
    };
  }

  const body = {
    model: "gpt-4.1-mini",
    temperature: 0.1,
    max_tokens: 500,
    response_format: { type: "json_object" },
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: JSON.stringify(userPayload) }
    ]
  };

  let rawText = "";
  try {
    const res = await ctx.helpers.httpRequest({
      method: "POST",
      url: "https://api.openai.com/v1/chat/completions",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json"
      },
      body,
      json: true
    });
    rawText = clean(res?.choices?.[0]?.message?.content || "");
  } catch (err) {
    return {
      ...item,
      extractor_raw_output: null,
      extractor_error: String(err && err.message ? err.message : err),
      extractor_latency_ms: Date.now() - started
    };
  }

  return {
    ...item,
    extractor_raw_output: rawText,
    extractor_latency_ms: Date.now() - started,
    extractor_error: ""
  };
}

return runExtractor(this, itemIn).then((out) => [{ json: out }]);
