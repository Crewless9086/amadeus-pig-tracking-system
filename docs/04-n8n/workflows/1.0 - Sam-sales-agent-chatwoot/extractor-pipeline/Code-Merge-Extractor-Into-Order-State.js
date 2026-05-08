const item = $input.first().json || {};

function clean(value) {
  return String(value || "").trim();
}

const validation = item.extractor_validation || {};
const data = validation.data;
const ok = validation.ok === true && data && Array.isArray(data.per_band_caps);

const next = { ...item };
let os = next.order_state && typeof next.order_state === "object" ? { ...next.order_state } : {};

if (!ok) {
  next.order_state = os;
  next.extractor_merge_applied = false;
  return [{ json: next }];
}

const category =
  clean((item.last_agent_offer || {}).offered_category || "") || os.requested_category || "Weaner";
const sexPref = os.requested_sex ? clean(os.requested_sex) : "Any";

const newItems = data.per_band_caps.map((row, idx) => ({
  request_item_key: `extractor_band_${idx + 1}`,
  category,
  weight_range: row.weight_range,
  sex: sexPref || "Any",
  quantity: String(row.qty),
  intent_type: "extractor_slot",
  status: "active",
  notes: ""
}));

os.requested_items = newItems;
if (data.target_total != null && !Number.isNaN(Number(data.target_total))) {
  os.requested_quantity = String(data.target_total);
}

os.should_enrich_existing_draft = true;
os.partial_stock_mix_follow_through = true;

os.has_minimum_line_sync_fields = Array.isArray(newItems) && newItems.length > 0;
const dm = clean(os.decision_mode || item.decision_mode || "AUTO").toUpperCase();
os.should_sync_order_lines =
  os.has_existing_draft === true && dm === "AUTO" && os.has_minimum_line_sync_fields === true;

os.extractor_slots_applied_at = Date.now();

next.order_state = os;
next.extractor_merge_applied = true;

return [{ json: next }];
