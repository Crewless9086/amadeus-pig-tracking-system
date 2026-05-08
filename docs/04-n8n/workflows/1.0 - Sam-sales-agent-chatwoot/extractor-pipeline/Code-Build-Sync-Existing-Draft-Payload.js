const item = $json || {};

function clean(value) {
  return String(value || "").trim();
}

function canonBand(lo, hi) {
  const a = Number(String(lo).trim());
  const b = Number(String(hi).trim());
  if (!(a > 0) || !(b > 0)) return "";
  return `${a}_to_${b}_Kg`;
}

function normalizeDashes(rawText) {
  return String(rawText || "")
    .replace(/\u2013/g, "-")
    .replace(/\u2014/g, "-")
    .replace(/\u2212/g, "-")
    .replace(/[\u2010\u2015\uFE58\uFE63\uFF0D]/g, "-");
}

function bandLowBoundForMix(wr) {
  const m = String(wr || "").match(/^(\d+)_to_(\d+)/i);
  return m ? Number(m[1]) : 9999;
}

/**
 * Merge transcript parses with last_agent_offer.caps (from Code - Build Extractor Inputs).
 * Drops the customer's primary band; sorts lighter bands first for stable fill order.
 */
function mergeAdjacentBandsWithOfferCaps(parsedBands, caps, prefWr) {
  const pref = clean(prefWr || "");
  const map = new Map();

  const rows = Array.isArray(parsedBands) ? parsedBands : [];
  for (const b of rows) {
    if (!b || !b.weight_range || clean(b.weight_range) === pref) continue;
    const wr = clean(b.weight_range);
    const q = Number(b.quantity || 0);
    if (!(q > 0)) continue;
    map.set(wr, Math.max(map.get(wr) || 0, q));
  }

  const capRows = Array.isArray(caps) ? caps : [];
  for (const c of capRows) {
    const wr = clean(String(c.weight_range || ""));
    if (!wr || wr === pref) continue;
    const mq = Number(c.max_qty);
    if (!(mq > 0)) continue;
    map.set(wr, Math.max(map.get(wr) || 0, mq));
  }

  return [...map.entries()]
    .map(([weight_range, quantity]) => ({ weight_range, quantity }))
    .sort((a, b) => bandLowBoundForMix(a.weight_range) - bandLowBoundForMix(b.weight_range));
}

/**
 * Same intent as Build Order State `extractAdjacentBandOffersFromTranscript`:
 * recover Sam's band/qty offers ("N available in the X-Y kg", "N in the X-Y kg range").
 * Does not use "N weaners X-Y kg" (that pattern matches the customer's primary line).
 */
function extractAdjacentBandOffersFromTranscript(raw) {
  const rawText = clean(raw);
  if (!rawText) return [];

  const normalized = normalizeDashes(rawText);
  const out = [];

  function pushQty(low, high, qty) {
    const lowN = Number(low);
    const highN = Number(high);
    const qtyN = Number(qty);
    if (!(lowN > 0) || !(highN > 0) || !(qtyN > 0)) return;
    const wr = canonBand(lowN, highN);
    if (!wr) return;
    const existingIndex = out.findIndex((entry) => entry.weight_range === wr);
    if (existingIndex >= 0) out[existingIndex].quantity += qtyN;
    else out.push({ weight_range: wr, quantity: qtyN });
  }

  let mm;
  const reAvail =
    /(\d+)\s+available\s+in\s+(?:the\s+)?(\d+)\s*-\s*(\d+)\s*kg(?:\s+range)?\b/gi;
  while ((mm = reAvail.exec(normalized)) !== null) {
    pushQty(mm[2], mm[3], mm[1]);
  }

  const rx2 = /\band\s+(\d+)\s+at\s+(\d+)\s*-\s*(\d+)\s*kg/gi;
  while ((mm = rx2.exec(normalized)) !== null) {
    pushQty(mm[2], mm[3], mm[1]);
  }

  const rx3 = /\b(\d+)\s+pigs?\s+in\s+(?:the\s+)?(\d+)\s*-\s*(\d+)\s*kg\b/gi;
  while ((mm = rx3.exec(normalized)) !== null) {
    pushQty(mm[2], mm[3], mm[1]);
  }

  const rxBareInKg =
    /\b(\d+)\s+in\s+(?:the\s+)?(\d+)\s*-\s*(\d+)\s*kg(?:\s+range)?\b/gi;
  while ((mm = rxBareInKg.exec(normalized)) !== null) {
    pushQty(mm[2], mm[3], mm[1]);
  }

  return out;
}

function draftActiveLineCount(existingOrderContext) {
  const bundle = existingOrderContext || {};
  const lines = Array.isArray(bundle.lines) ? bundle.lines : [];
  let n = 0;
  for (const line of lines) {
    const ls = clean(line.line_status);
    if (ls === "Cancelled" || ls === "Collected") continue;
    n += 1;
  }
  if (n === 0 && bundle.order != null && bundle.order.active_line_count != null) {
    const a = Number(bundle.order.active_line_count);
    if (!Number.isNaN(a) && a >= 0) n = Math.floor(a);
  }
  return n;
}

/**
 * Last-mile safety: rebuild nearby_band_* from transcript+caps when the draft has a
 * line shortfall and the customer confirms a mix — even if Build Order State already
 * appended a malformed single nearby row (e.g. double-count from overlapping regex).
 */
function enrichPartialMixItems(item, requestedItems) {
  const base = Array.isArray(requestedItems) ? requestedItems : [];
  const primaryRows = base.filter((row) =>
    /^primary_\d+$/i.test(clean(row.request_item_key || ""))
  );
  const nearbyExisting = base.filter((row) =>
    /^nearby_band_\d+$/i.test(clean(row.request_item_key || ""))
  );

  if (primaryRows.length !== 1 || clean(primaryRows[0].request_item_key || "") !== "primary_1") {
    return base;
  }

  const primary = primaryRows[0];

  const category = clean(primary.category || "");
  const prefWr = clean(primary.weight_range || "");
  const sex = clean(primary.sex || "") || "Any";
  let reqQty = Number(primary.quantity);
  if (!(reqQty > 0)) reqQty = 0;

  const bundle = item.existing_order_context || {};
  if (bundle.order && bundle.order.requested_quantity != null && !(reqQty > 0)) {
    const rq = Number(bundle.order.requested_quantity);
    if (!Number.isNaN(rq) && rq > 0) reqQty = rq;
  }

  const draftLines = draftActiveLineCount(bundle);
  const ctxOk = item.order_context_fetch_ok === true;
  const hasDraftId = clean(
    (item.order_state || {}).existing_order_id || item.existing_order_id || ""
  );
  const shortfall =
    ctxOk === true &&
    hasDraftId !== "" &&
    reqQty > 0 &&
    draftLines > 0 &&
    draftLines < reqQty;

  if (!shortfall) return base;

  const msg = clean(item.customer_message || item.CustomerMessage || "");
  const mixConsent =
    /\b(make\s+it\s+up|make\s+up(?:\s+the\s+\d+)?|you\s+can\s+(?:pick|choose|allocate|mix)|\bmix\b|\bmixing\b|\bnearest\s+bands?\b|\bnearest\s+(?:weights?|sizes?)|\bcombined?\b|\bwhatever\s+works\b|\bnearby\s+(?:bands?|weights?|sizes?)|\bfill\s+(?:the\s+)?(?:rest|gap)\b|\bother\s+bands?\b|\bdifferent\s+bands?\b)\b/i.test(
      msg
    );
  const proceedSignal =
    /(\byes\b|\byes please\b|\bplease proceed\b|\bgo ahead\b|\bthat's fine\b|\bthats fine\b|\bokay proceed\b|\bdo it\b|\bcorrect\b|\bconfirmed\b)/i.test(msg);
  const shortConfirm =
    /^(yes|yes please|correct|confirmed|confirm|okay|ok|yep|yup|that's right|thats right|right|correct yes)$/i.test(msg);

  if (!(mixConsent || proceedSignal || shortConfirm)) return base;

  const chunks = [
    clean(item.ConversationHistory || ""),
    clean(item.conversation_notes || ""),
    clean(item.ai_output || "")
  ].filter(Boolean);

  const mergedTranscript = chunks.join("\n");
  const adjacentBands = mergeAdjacentBandsWithOfferCaps(
    extractAdjacentBandOffersFromTranscript(mergedTranscript),
    (item.last_agent_offer || {}).caps,
    prefWr
  );

  if (adjacentBands.length === 0) return base;

  let remainder = Math.max(0, reqQty - draftLines);
  let nearbyIndex = 0;
  const rebuilt = [primary];

  for (const band of adjacentBands) {
    if (remainder <= 0) break;
    if (!band.weight_range || band.weight_range === prefWr) continue;
    const offerQty = Number(band.quantity || 0);
    if (!(offerQty > 0)) continue;
    const takeQty = Math.min(offerQty, remainder);
    if (!(takeQty > 0)) continue;
    nearbyIndex += 1;
    remainder -= takeQty;
    rebuilt.push({
      request_item_key: `nearby_band_${nearbyIndex}`,
      category,
      weight_range: band.weight_range,
      sex,
      quantity: String(takeQty),
      intent_type: "nearby_addon",
      status: "active",
      notes: ""
    });
  }

  if (rebuilt.length <= 1) return base;

  const capRows = Array.isArray((item.last_agent_offer || {}).caps)
    ? (item.last_agent_offer || {}).caps
    : [];
  const capByWr = new Map();
  for (const c of capRows) {
    const wr = clean(String(c.weight_range || ""));
    const mq = Number(c.max_qty);
    if (!wr || wr === prefWr || !(mq > 0)) continue;
    capByWr.set(wr, mq);
  }

  let legacyOversized = false;
  for (const row of nearbyExisting) {
    const wr = clean(row.weight_range || "");
    const q = Number(row.quantity || 0);
    const cap = capByWr.get(wr);
    if (cap > 0 && q > cap) legacyOversized = true;
  }

  function nearbyTierSignature(rows) {
    return rows
      .map((r) => `${clean(r.weight_range || "")}:${clean(String(r.quantity || ""))}`)
      .join("|");
  }

  const rebuiltNearby = rebuilt.slice(1);
  if (
    legacyOversized ||
    nearbyTierSignature(rebuiltNearby) !== nearbyTierSignature(nearbyExisting)
  ) {
    return rebuilt;
  }

  return base;
}

const state = item.order_state || {};
const existingOrderId = String(state.existing_order_id || "").trim();

if (!existingOrderId) {
  throw new Error("existing_order_id is required for sync order lines.");
}

if (!Array.isArray(state.requested_items) || state.requested_items.length === 0) {
  throw new Error("requested_items is required for sync order lines.");
}

const baseLen = state.requested_items.length;
const requestedItemsBefore = JSON.stringify(state.requested_items);
const requestedItemsFinal = enrichPartialMixItems(item, state.requested_items);

if (!Array.isArray(requestedItemsFinal) || requestedItemsFinal.length === 0) {
  throw new Error("requested_items is required for sync order lines.");
}

const syncPayload = {
  action: "sync_order_lines_from_request",
  order_id: existingOrderId,
  changed_by: "Sam",
  requested_items: requestedItemsFinal
};

return [
  {
    json: {
      ...item,
      sync_payload_requested_items_before_enrich: baseLen,
      sync_payload_nearby_items_enriched: JSON.stringify(requestedItemsFinal) !== requestedItemsBefore,
      order_state: {
        ...(typeof state === "object" && state !== null ? state : {}),
        requested_items: requestedItemsFinal
      },
      sync_payload: syncPayload
    }
  }
];
