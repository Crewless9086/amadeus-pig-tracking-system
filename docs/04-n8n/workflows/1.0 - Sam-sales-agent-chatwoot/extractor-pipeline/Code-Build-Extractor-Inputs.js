const item = $input.first().json || {};

function cleanText(value) {
  return String(value || "").trim();
}

function canonBand(lo, hi) {
  const a = Number(String(lo).trim());
  const b = Number(String(hi).trim());
  if (!(a > 0) || !(b > 0)) return "";
  return `${a}_to_${b}_Kg`;
}

function lastSamMessage(conversationHistory) {
  const lines = cleanText(conversationHistory)
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i];
    if (line.startsWith("Sam:")) return line.slice(4).trim();
  }
  return "";
}

function shortThread(history, maxLines) {
  const lines = cleanText(history)
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  return lines.slice(-maxLines).join("\n");
}

/** Build caps from steward sync_results / results alternatives (preferred). */
function capsFromSyncResults(syncRes, requestedWeightRange) {
  const capsMap = new Map();
  const rows = Array.isArray(syncRes) ? syncRes : [];
  for (const r of rows) {
    if (!r || r.match_status !== "partial_match") continue;
    const wrReq = requestedWeightRange;
    const matched = Number(r.matched_quantity);
    if (wrReq && !Number.isNaN(matched) && matched > 0) {
      capsMap.set(wrReq, Math.max(capsMap.get(wrReq) || 0, matched));
    }
    const alts = Array.isArray(r.alternatives) ? r.alternatives : [];
    for (const a of alts) {
      const band = cleanText(a.weight_band || "");
      const avail = Number(a.available_count);
      if (band && !Number.isNaN(avail) && avail > 0) {
        capsMap.set(band, Math.max(capsMap.get(band) || 0, avail));
      }
    }
  }
  const caps = [];
  for (const [weight_range, max_qty] of capsMap.entries()) {
    caps.push({ weight_range, max_qty });
  }
  return caps;
}

/** Fallback: parse partial-stock wording from Sam's last bot turn. */
function capsFromSamText(samText, preferredWeightRange) {
  const text = samText.replace(/\u2013/g, "-").replace(/\u2014/g, "-");
  const capsMap = new Map();

  const mExact = text.match(/only\s+(\d+)\s+available\s+in\s+that\s+exact\s+band/i);
  if (mExact && preferredWeightRange) {
    capsMap.set(preferredWeightRange, Math.max(capsMap.get(preferredWeightRange) || 0, Number(mExact[1])));
  }

  const reAvail = /(\d+)\s+available\s+in\s+(?:the\s+)?(\d+)\s*-\s*(\d+)\s*kg/gi;
  let mm;
  while ((mm = reAvail.exec(text)) !== null) {
    const band = canonBand(mm[2], mm[3]);
    if (band) capsMap.set(band, Math.max(capsMap.get(band) || 0, Number(mm[1])));
  }

  const reThereAre = /there\s+are\s+(\d+)\s+available\s+in\s+the\s+(\d+)\s*-\s*(\d+)\s*kg/gi;
  while ((mm = reThereAre.exec(text)) !== null) {
    const band = canonBand(mm[2], mm[3]);
    if (band) capsMap.set(band, Math.max(capsMap.get(band) || 0, Number(mm[1])));
  }

  const reInBand = /(\d+)\s+in\s+the\s+(\d+)\s*-\s*(\d+)\s*kg\s+band/gi;
  while ((mm = reInBand.exec(text)) !== null) {
    const band = canonBand(mm[2], mm[3]);
    if (band) capsMap.set(band, Math.max(capsMap.get(band) || 0, Number(mm[1])));
  }

  // "we have 3 available in that weight range" (refers to requested band on the draft)
  const mRangeRef = text.match(
    /\b(?:we\s+)?have\s+(\d+)\s+available\s+in\s+(?:that|the)\s+weight\s+range\b/i
  );
  if (mRangeRef && preferredWeightRange) {
    const n = Number(mRangeRef[1]);
    if (!Number.isNaN(n) && n > 0) {
      capsMap.set(
        preferredWeightRange,
        Math.max(capsMap.get(preferredWeightRange) || 0, n)
      );
    }
  }

  // Bullets or inline: "- 2 pigs in 7–9kg" / "2 pigs in 7-9 kg"
  const rePigsInBand = /\b(\d+)\s+pigs?\s+in\s+(\d+)\s*[-–]\s*(\d+)\s*kg\b/gi;
  while ((mm = rePigsInBand.exec(text)) !== null) {
    const band = canonBand(mm[2], mm[3]);
    if (band) capsMap.set(band, Math.max(capsMap.get(band) || 0, Number(mm[1])));
  }

  // "keep the 3 from 10–14kg" anchors primary-band cap when offered alongside mix
  const mKeep = text.match(
    /\bkeep\s+(?:the\s+)?(\d+)\s+(?:from|in)\s+(\d+)\s*[-–]\s*(\d+)\s*kg\b/i
  );
  if (mKeep) {
    const band = canonBand(mKeep[2], mKeep[3]);
    const wr = band || preferredWeightRange;
    if (wr) {
      const n = Number(mKeep[1]);
      if (!Number.isNaN(n) && n > 0) {
        capsMap.set(wr, Math.max(capsMap.get(wr) || 0, n));
      }
    }
  }

  const caps = [];
  for (const [weight_range, max_qty] of capsMap.entries()) {
    caps.push({ weight_range, max_qty });
  }
  return caps;
}

const state = item.order_state || {};
const conversationHistory = cleanText(item.ConversationHistory || "");
const samLine = lastSamMessage(conversationHistory);
const osReqQty = state.requested_quantity !== "" && state.requested_quantity != null
  ? Number(state.requested_quantity)
  : null;
const offeredTotal = !Number.isNaN(osReqQty) && osReqQty > 0 ? osReqQty : null;
const preferredWr = cleanText(state.requested_weight_range || "");

const syncRes =
  (Array.isArray(item.results) && item.results.length ? item.results : null) ||
  (Array.isArray(item.sync_results) && item.sync_results.length ? item.sync_results : null);

let source = "none";
let caps = capsFromSyncResults(syncRes || [], preferredWr);
if (caps.length > 0) source = "sync_results";
else {
  caps = capsFromSamText(samLine, preferredWr);
  if (caps.length > 0) source = "sam_text_parse";
}

const bundle = item.existing_order_context;
const draftSummary =
  bundle && bundle.order
    ? {
        order_id: cleanText(bundle.order.order_id || ""),
        order_status: cleanText(bundle.order.order_status || ""),
        requested_quantity: bundle.order.requested_quantity,
        active_line_count: bundle.order.active_line_count,
        line_count: bundle.order.line_count
      }
    : null;

const last_agent_offer = {
  offered_total: offeredTotal,
  offered_category: cleanText(state.requested_category || "") || null,
  caps,
  reconstructable: caps.length > 0,
  envelope_source: source
};

const existing_draft_summary = draftSummary;

return [
  {
    json: {
      ...item,
      extractor_short_thread: shortThread(conversationHistory, 8),
      last_agent_offer,
      extractor_inputs_built_at: source
    }
  }
];
