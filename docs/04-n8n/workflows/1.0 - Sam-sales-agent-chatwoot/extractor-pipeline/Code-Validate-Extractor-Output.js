const item = $input.first().json || {};

function clean(value) {
  return String(value || "").trim();
}

function stripFence(text) {
  let s = clean(text);
  if (s.startsWith("```")) {
    s = s.replace(/^```[a-zA-Z]*\n?/, "").replace(/\n```$/, "");
  }
  return clean(s);
}

function parseJsonFlexible(raw) {
  if (!raw) return null;
  const stripped = stripFence(raw);
  try {
    return JSON.parse(stripped);
  } catch (e1) {
    const start = stripped.indexOf("{");
    const end = stripped.lastIndexOf("}");
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(stripped.slice(start, end + 1));
      } catch (e2) {
        return null;
      }
    }
    return null;
  }
}

const ALLOWED = new Set([
  "target_total",
  "per_band_caps",
  "accept_nearby_bands",
  "commitment_flag",
  "confidence",
  "evidence_quote",
  "extractor_notes"
]);

if (item.extractor_should_run !== true || item.extractor_call_skipped === true || !clean(item.extractor_raw_output || "")) {
  return [
    {
      json: {
        ...item,
        extractor_validation: {
          ok: false,
          data: null,
          violations: item.extractor_should_run !== true ? ["extractor_not_run"] : ["no_model_output"],
          confidence_final: 0
        }
      }
    }
  ];
}

const raw = item.extractor_raw_output;
const parsed = parseJsonFlexible(raw);
if (!parsed || typeof parsed !== "object") {
  return [
    {
      json: {
        ...item,
        extractor_validation: { ok: false, data: null, violations: ["json_parse_failure"], confidence_final: 0 }
      }
    }
  ];
}

const unknownKeys = Object.keys(parsed).filter((k) => !ALLOWED.has(k));
if (unknownKeys.length > 0) {
  return [
    {
      json: {
        ...item,
        extractor_validation: {
          ok: false,
          data: null,
          violations: [`unknown_keys:${unknownKeys.join(",")}`],
          confidence_final: 0
        }
      }
    }
  ];
}

const violations = [];
const offer = item.last_agent_offer || {};
const capIndex = {};
for (const c of Array.isArray(offer.caps) ? offer.caps : []) {
  if (c && c.weight_range) capIndex[c.weight_range] = Number(c.max_qty) || 0;
}

let confidence = typeof parsed.confidence === "number" ? parsed.confidence : Number(parsed.confidence);
if (Number.isNaN(confidence)) confidence = 0;

const flagRaw = clean(parsed.commitment_flag || "").toLowerCase();
const flag = ["commit", "tentative", "cancel", "none"].includes(flagRaw) ? flagRaw : "none";

const customerMsg = clean(item.customer_message || item.CustomerMessage);
let evidenceQuote = clean(parsed.evidence_quote || "");

if (evidenceQuote !== "") {
  if (customerMsg.indexOf(evidenceQuote) === -1) {
    evidenceQuote = "";
    confidence -= 0.3;
    violations.push("evidence_quote_not_verbatim_substring");
  }
}

let targetTotal =
  parsed.target_total === null || parsed.target_total === undefined || parsed.target_total === ""
    ? null
    : Number(parsed.target_total);

if (targetTotal !== null && Number.isNaN(targetTotal)) {
  targetTotal = null;
}

const ot = offer.offered_total != null ? Number(offer.offered_total) : null;

const perBands = Array.isArray(parsed.per_band_caps) ? parsed.per_band_caps : [];

const cleanedBands = [];
for (let i = 0; i < perBands.length; i += 1) {
  const row = perBands[i] || {};
  const wr = clean(row.weight_range || "");
  const qtyRaw = Number(row.qty);
  if (!wr || Number.isNaN(qtyRaw)) continue;

  const capMax = capIndex[wr];
  if (!(capMax > 0)) {
    violations.push(`band_not_in_offer:${wr}`);
    continue;
  }

  let qty = qtyRaw;
  if (qty > capMax) {
    qty = capMax;
    confidence -= 0.2;
    violations.push(`clamped_qty:${wr}`);
  }
  if (qty > 0) cleanedBands.push({ weight_range: wr, qty });
}

const sumBands = cleanedBands.reduce((s, r) => s + r.qty, 0);

if (targetTotal !== null && sumBands > targetTotal) {
  targetTotal = sumBands;
  violations.push("target_total_coerced_to_sum_bands");
}

if (targetTotal !== null && !Number.isNaN(ot) && ot > 0 && targetTotal > ot) {
  targetTotal = ot;
  confidence -= 0.2;
  violations.push("target_total_clamped_to_offered_total");
}

if (targetTotal !== null && sumBands > 0 && sumBands < targetTotal) {
  violations.push("band_sum_below_target_total_ok");
}

if (confidence < 0) confidence = 0;
if (confidence > 1) confidence = 1;

const badBands = violations.filter((v) => v.startsWith("band_not_in_offer"));

let mergeOk =
  (flag === "commit" || flag === "tentative") &&
  cleanedBands.length > 0 &&
  badBands.length === 0;

if (confidence < 0.6) mergeOk = false;

const ok = mergeOk;

const dataOut =
  ok
    ? {
        target_total: targetTotal,
        per_band_caps: cleanedBands,
        accept_nearby_bands: Boolean(parsed.accept_nearby_bands),
        commitment_flag: flag,
        confidence,
        evidence_quote: evidenceQuote,
        extractor_notes: String(parsed.extractor_notes || "").slice(0, 200)
      }
    : null;

return [
  {
    json: {
      ...item,
      extractor_validation: {
        ok,
        data: dataOut,
        violations,
        confidence_final: confidence,
        commitment_flag: flag
      }
    }
  }
];
