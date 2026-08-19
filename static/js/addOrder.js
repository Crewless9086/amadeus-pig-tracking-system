document.addEventListener("DOMContentLoaded", () => {
  const date = document.getElementById("order_date");
  if (date && !date.value) date.value = new Date().toISOString().split("T")[0];
  const initial = [
    { quantity: 10, sex: "Female", weight_range: "5_to_6_Kg" },
    { quantity: 10, sex: "Male", weight_range: "5_to_6_Kg" },
    { quantity: 1, sex: "Female", weight_range: "15_to_19_Kg" },
    { quantity: 1, sex: "Male", weight_range: "15_to_19_Kg" }
  ];
  initial.forEach(addRequestLine);
  document.getElementById("add_request_line")?.addEventListener("click", () => addRequestLine({ quantity: 1, sex: "Any", weight_range: "5_to_6_Kg" }));
  document.getElementById("addOrderForm")?.addEventListener("submit", previewRequest);
  document.getElementById("alreadySoldForm")?.addEventListener("submit", previewAlreadySold);
});

async function previewAlreadySold(event) {
  event.preventDefault();
  const value = id => document.getElementById(id).value;
  const payload = {tag_numbers:value("sold_tags").split(",").map(v=>v.trim()).filter(Boolean), sold_date:value("sold_date"), buyer_name:value("sold_buyer"), sale_channel:value("sold_channel"), movement_destination:value("sold_destination"), owner_reported_evidence:value("sold_owner_report")};
  const message=document.getElementById("already_sold_message");
  try {
    const response=await fetch("/api/orders/already-sold-preview",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}); const result=await response.json();
    if(!response.ok) throw new Error((result.errors||["Preview failed."]).join(" "));
    message.className="message-box message-success"; message.textContent="Protected preview built. No sale, order, allocation, reservation, pig-state change, document, or message was created.";
    const host=document.getElementById("already_sold_preview"); host.classList.remove("hidden");
    const pigs=result.selected_pigs.map(p=>`<li><strong>Tag ${esc(p.tag_number)}</strong> · ${esc(p.current_weight_kg)} kg · purpose ${esc(p.purpose)}${treatmentDisclosure(p)}</li>`).join("");
    const gaps=result.errors.map(v=>`<li>${esc(v)}</li>`).join("");
    const next=result.next_protected_action||{};
    host.innerHTML=`<h3>Canonical action still required</h3><p>${esc(result.authority_boundary)}</p><ul>${pigs}</ul>${gaps?`<h4>Known evidence still missing</h4><ul>${gaps}</ul>`:""}<p><strong>Use:</strong> ${esc(next.surface||"Orders")}.</p><p>${esc(next.action||"")}</p><p class="field-helper">Preview ${esc(result.preview_digest)} · writes performed: no · customer send: no</p>`;
  } catch(error) { message.className="message-box message-error"; message.textContent=error.message; }
}

function addRequestLine(value) {
  const host = document.getElementById("requested_items_editor");
  const index = host.children.length + 1;
  const row = document.createElement("div");
  row.className = "form-grid livestock-request-line";
  row.innerHTML = `<div class="form-group"><label>Quantity</label><input data-field="quantity" type="number" min="1" step="1" value="${value.quantity}" required></div>
    <div class="form-group"><label>Sex</label><select data-field="sex"><option>Female</option><option>Male</option><option>Any</option></select></div>
    <div class="form-group"><label>Weight range</label><select data-field="weight_range"><option value="2_to_4_Kg">2–4 kg</option><option value="5_to_6_Kg">5–6 kg</option><option value="7_to_9_Kg">7–9 kg</option><option value="10_to_14_Kg">10–14 kg</option><option value="15_to_19_Kg">Around 15 kg (15–19 kg)</option><option value="20_to_24_Kg">20–24 kg</option></select></div>
    <div class="form-group"><label>Line</label><button type="button" class="small-action-button remove-line">Remove</button></div>`;
  row.querySelector('[data-field="sex"]').value = value.sex;
  row.querySelector('[data-field="weight_range"]').value = value.weight_range;
  row.querySelector(".remove-line").addEventListener("click", () => row.remove());
  host.appendChild(row);
}

async function previewRequest(event) {
  event.preventDefault();
  const message = document.getElementById("add_order_message");
  const requested_items = [...document.querySelectorAll(".livestock-request-line")].map((row, index) => ({
    request_item_key: `manual_${index + 1}`, category: "Piglet", intent_type: "primary", status: "active",
    quantity: Number(row.querySelector('[data-field="quantity"]').value), sex: row.querySelector('[data-field="sex"]').value,
    weight_range: row.querySelector('[data-field="weight_range"]').value, notes: ""
  }));
  try {
    const response = await fetch("/api/orders/livestock-quote-preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ requested_items }) });
    const result = await response.json();
    if (!response.ok) throw new Error((result.errors || ["Preview failed."]).join(" "));
    message.className = "message-box message-success";
    message.textContent = "Local preview ready. No order, reservation, allocation or customer message was created.";
    renderPreview(result);
  } catch (error) {
    message.className = "message-box message-error";
    message.textContent = error.message;
  }
}

function renderPreview(result) {
  const host = document.getElementById("livestock_preview");
  host.classList.remove("hidden");
  const recommended = result.recommendations.flatMap(line => line.candidates || []);
  const lines = result.recommendations.map(line => {
    const candidates = line.candidates.map(pig => `<li><strong>Tag ${esc(pig.tag_number || pig.pig_id)}</strong> · ${esc(pig.sex)} · ${pig.current_weight_kg} kg · weighed ${esc(pig.weight_date || "unknown")} · ${pig.unit_price == null ? "price unavailable" : `R${Number(pig.unit_price).toFixed(2)}`}${pig.weight_confidence === "fresh_weight_requested" ? " · fresh weight requested" : ""}</li>`).join("");
    return `<article class="detail-card"><h3>${line.requested_quantity} ${esc(line.sex)} · ${esc(weightLabel(line.weight_range))}</h3><p><strong>${esc(line.status)}</strong> · available ${line.available_quantity} · shortfall ${line.shortfall_quantity}${line.recommended_subtotal == null ? "" : ` · recommended subtotal R${Number(line.recommended_subtotal).toFixed(2)}`}</p><ul>${candidates || "<li>No current recommendation; the requested line remains Unavailable.</li>"}</ul></article>`;
  }).join("");
  const medicine = consolidatedMedicineDisclosure(recommended);
  const review = (result.purpose_or_evidence_review || []).map(group => `<article class="detail-card"><h3>${esc(group.blocking_axis)} · ${esc(group.state)}</h3><p>${esc(group.reason)}</p><ul>${group.candidates.map(pig => `<li>Tag ${esc(pig.tag_number || pig.pig_id)} · ${pig.current_weight_kg} kg · purpose ${esc(pig.purpose)}</li>`).join("")}</ul></article>`).join("");
  host.innerHTML = `<div class="section-title-row"><div><h2>Draft quote preview</h2><p>${esc(result.authority_boundary)}</p></div></div>${lines}${medicine}${review ? `<details><summary>Why some animals were excluded</summary>${review}</details>` : ""}<p class="field-helper">Customer request: captured · recommendation: advisory · reservation: none · final fulfilment: none.</p>`;
}

function consolidatedMedicineDisclosure(pigs) {
  const restricted = pigs.filter(pig => pig.treatment_disclosure);
  const clear = pigs.filter(pig => !pig.treatment_disclosure && pig.medicine_indicator === "No current recorded food-chain restriction");
  const unknown = pigs.length - restricted.length - clear.length;
  const restrictions = new Map();
  restricted.forEach(pig => {
    const disclosure = pig.treatment_disclosure;
    const key = [disclosure.product || "Recorded treatment", disclosure.withdrawal_end_date || "date unavailable"].join("|");
    if (!restrictions.has(key)) restrictions.set(key, { disclosure, tags: [] });
    restrictions.get(key).tags.push(pig.tag_number || pig.pig_id);
  });
  const rows = [...restrictions.values()].map(({ disclosure, tags }) =>
    `<li><strong>Tags ${tags.map(esc).join(", ")}</strong> · ${esc(disclosure.product || "Recorded treatment")} · food-chain withdrawal through ${esc(disclosure.withdrawal_end_date || "date unavailable")}.</li>`
  ).join("");
  return `<aside class="detail-card" aria-label="Consolidated medicine disclosure"><h3>Consolidated medicine disclosure</h3><p>This disclosure does not reserve pigs or certify veterinary, quarantine or transport clearance.</p><ul>${rows || ""}<li>${clear.length} recommended animal${clear.length === 1 ? "" : "s"}: no current recorded food-chain restriction.</li>${unknown ? `<li>${unknown} recommended animal${unknown === 1 ? "" : "s"}: recorded food-chain status unavailable.</li>` : ""}</ul></aside>`;
}

function treatmentDisclosure(pig) {
  const disclosure = pig.treatment_disclosure;
  if (!disclosure) return "";
  const end = disclosure.withdrawal_end_date ? ` Withdrawal through ${esc(disclosure.withdrawal_end_date)}.` : "";
  return `<br><strong>Livestock treatment disclosure:</strong> ${esc(disclosure.safe_buyer_wording || "Food-chain withdrawal applies.")}${end}`;
}

function esc(value) { const node = document.createElement("div"); node.textContent = String(value ?? ""); return node.innerHTML; }
function weightLabel(value) { return String(value || "").replace(/_to_/g, "–").replace(/_Kg$/i, " kg"); }
function evidenceLabel(value) { return value === "authenticated_local_owner_preview_fixture" ? "authenticated local preview fixture (not production availability)" : String(value || "bounded allocation snapshot").replaceAll("_", " "); }
