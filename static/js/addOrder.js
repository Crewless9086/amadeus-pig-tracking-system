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
});

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
  host.innerHTML = `<div class="section-title-row"><div><h2>Draft quote availability</h2><p>${esc(result.authority_boundary)}</p><p class="field-helper">Evidence: ${esc(evidenceLabel(result.evidence_source))} · observed ${esc(result.observed_at || "time unknown")}</p></div></div>` + result.recommendations.map(line => {
    const candidates = line.candidates.map(pig => `<li><strong>Tag ${esc(pig.tag_number || pig.pig_id)}</strong> · ${pig.current_weight_kg} kg (${esc(pig.weight_date || "weight date unknown")}) · ${esc(pig.match_state)} · purpose ${esc(pig.purpose)}${pig.warnings.length ? `<br><span class="field-helper">${pig.warnings.map(esc).join(" ")}</span>` : ""}${pig.blocking_restrictions.length ? `<br><span class="message-error">${pig.blocking_restrictions.map(esc).join(" ")}</span>` : ""}</li>`).join("");
    return `<article class="detail-card"><h3>${line.requested_quantity} ${esc(line.sex)} · ${esc(weightLabel(line.weight_range))}</h3><p><strong>${esc(line.status)}</strong> · exact ${line.exact_match_count} · projected ${line.projected_count} · shortfall ${line.shortfall_quantity}</p><ul>${candidates || "<li>No bounded candidate found.</li>"}</ul></article>`;
  }).join("") + `<p class="field-helper">Customer request: captured · HERDMASTER recommendation: advisory · Reservation: none · Final fulfilment: none.</p>`;
}

function esc(value) { const node = document.createElement("div"); node.textContent = String(value ?? ""); return node.innerHTML; }
function weightLabel(value) { return String(value || "").replace(/_to_/g, "–").replace(/_Kg$/i, " kg"); }
function evidenceLabel(value) { return value === "authenticated_local_owner_preview_fixture" ? "authenticated local preview fixture (not production availability)" : String(value || "bounded allocation snapshot").replaceAll("_", " "); }
