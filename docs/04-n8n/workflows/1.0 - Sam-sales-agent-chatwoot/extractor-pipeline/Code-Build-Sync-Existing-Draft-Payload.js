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

/**
 * Same intent as Build Order State `extractAdjacentBandOffersFromTranscript`:
 * recover band/qty offers from Sam transcript (weaners / pigs / "N in X-Y kg").
 */
function extractAdjacentBandOffersFromTranscript(raw) {
  const rawText = clean(raw);
  if (!rawText) return [];

  const normalized = rawText.replace(/\u2013/g, "-").replace(/\u2014/g, "-");
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
  const rx1 =
    /\b(\d+)\s+(?:weaners?|piglets?|pigs)\s+(?:each\s+(?:around|about)\s*)?(?:around\s+|at\s+)?(\d+)\s*-\s*(\d+)\s*kg/gi;
  while ((mm = rx1.exec(normalized)) !== null) {
    pushQty(mm[2], mm[3], mm[1]);
  }

  const rx2 = /\band\s+(\d+)\s+at\s+(\d+)\s*-\s*(\d+)\s*kg/gi;
  while ((mm = rx2.exec(normalized)) !== null) {
    pushQty(mm[2], mm[3], mm[1]);
  }

  const rx3 = /\b(\d+)\s+pigs?\s+in\s+(\d+)\s*-\s*(\d+)\s*kg\b/gi;
  while ((mm = rx3.exec(normalized)) !== null) {
    pushQty(mm[2], mm[3], mm[1]);
  }

  const rx4 = /\b(\d+)\s+in\s+(\d+)\s*-\s*(\d+)\s*kg\b/gi;
  while ((mm = rx4.exec(normalized)) !== null) {
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
 * Last-mile safety: if only `primary_1` was built but transcript shows other bands,
 * rebuild same nearby_band_* items as Build Order State would (shortfall + consent).
 */
function enrichPartialMixItems(item, requestedItems) {
  const base = Array.isArray(requestedItems) ? requestedItems : [];
  if (base.length !== 1) return base;

  const primary = base[0];
  if (clean(primary.request_item_key || "") !== "primary_1") return base;

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

  let adjacentBands = [];
  for (const chunk of chunks) {
    adjacentBands = extractAdjacentBandOffersFromTranscript(chunk);
    if (adjacentBands.length > 0) break;
  }
  if (adjacentBands.length === 0) return base;

  let remainder = Math.max(0, reqQty - draftLines);
  let nearbyIndex = 0;
  const out = [...base];

  for (const band of adjacentBands) {
    if (remainder <= 0) break;
    if (!band.weight_range || band.weight_range === prefWr) continue;
    const offerQty = Number(band.quantity || 0);
    if (!(offerQty > 0)) continue;
    const takeQty = Math.min(offerQty, remainder);
    if (!(takeQty > 0)) continue;
    nearbyIndex += 1;
    remainder -= takeQty;
    out.push({
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

  return out.length > base.length ? out : base;
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
      sync_payload_nearby_items_enriched: requestedItemsFinal.length > baseLen,
      order_state: {
        ...(typeof state === "object" && state !== null ? state : {}),
        requested_items: requestedItemsFinal
      },
      sync_payload: syncPayload
    }
  }
];
