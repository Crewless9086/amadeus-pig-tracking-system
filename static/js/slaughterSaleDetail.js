const saleId = window.SLAUGHTER_SALE_ID || "";
const title = document.getElementById("sale_detail_title");
const subtitle = document.getElementById("sale_detail_subtitle");
const messageBox = document.getElementById("sale_detail_message");
const backButton = document.getElementById("sale_detail_back");
const summaryList = document.getElementById("sale_detail_summary");
const paymentList = document.getElementById("sale_detail_payment");
const itemsCount = document.getElementById("sale_items_count");
const itemsBody = document.getElementById("sale_items_body");
const exitConfirmPanel = document.getElementById("sale_exit_confirm_panel");
const exitConfirmForm = document.getElementById("sale_exit_confirm_form");
const exitDateInput = document.getElementById("sale_exit_date");
const exitChangedByInput = document.getElementById("sale_exit_changed_by");
const exitNotesInput = document.getElementById("sale_exit_notes");
const exitConfirmButton = document.getElementById("sale_exit_confirm_button");
const paymentForm = document.getElementById("sale_payment_form");
const paymentAmountInput = document.getElementById("sale_payment_received_amount");
const paymentMethodInput = document.getElementById("sale_payment_method");
const paymentDateInput = document.getElementById("sale_payment_date");
const paymentPreviewButton = document.getElementById("sale_payment_preview_button");
const paymentConfirmButton = document.getElementById("sale_payment_confirm_button");
const paymentPreviewBox = document.getElementById("sale_payment_preview");
const charityForm = document.getElementById("sale_charity_form");
const charityReasonInput = document.getElementById("sale_charity_reason");
const charityCorrectionInput = document.getElementById("sale_charity_correction_reason");
const charityPreviewButton = document.getElementById("sale_charity_preview_button");
const charityConfirmButton = document.getElementById("sale_charity_confirm_button");
const charityPreviewBox = document.getElementById("sale_charity_preview");
let loadedSale = null;
let pendingPaymentPreview = null;
let pendingCharityPreview = null;
let paymentPreviewGeneration = 0;

function showMessage(message, type = "error") {
  messageBox.classList.remove("hidden", "message-success", "message-error");
  messageBox.classList.add(type === "success" ? "message-success" : "message-error");
  messageBox.textContent = message;
}

function money(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return `R${Number(value).toFixed(2)}`;
}

function dateOnly(value) {
  if (!value) return "-";
  return String(value).slice(0, 10);
}

function valueOrDash(value) {
  const text = String(value ?? "").trim();
  return text || "-";
}

function safeInternalReturnPath(value) {
  const path = String(value || "").trim();
  if (!path.startsWith("/") || path.startsWith("//")) {
    return "";
  }
  return path;
}

function saleDetailFallbackPath() {
  if (window.location.pathname.startsWith("/sales/transactions/")) {
    return "/sales-dashboard";
  }
  return "/sales/slaughter";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

function transactionLabel(sale) {
  const channel = String(sale.sale_channel || "").trim().toLowerCase();
  if (channel === "auction") return "Livestock — Auction";
  const stream = String(sale.sale_stream || "Livestock").trim();
  return `Livestock — ${stream}`;
}

function isAuction(sale) {
  return String(sale?.sale_channel || "").trim().toLowerCase() === "auction";
}

function updateBackButtonFromQuery() {
  if (!backButton) return;
  const params = new URLSearchParams(window.location.search);
  const returnTo = safeInternalReturnPath(params.get("return_to"));
  const returnLabel = String(params.get("return_label") || "").trim();
  backButton.dataset.returnTo = returnTo || saleDetailFallbackPath();
  backButton.textContent = returnLabel || "Back";
}

function renderDetailList(element, rows) {
  element.innerHTML = rows.map(([label, value]) => `
    <div>
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(valueOrDash(value))}</dd>
    </div>
  `).join("");
}

function setExitSubmitting(isSubmitting) {
  if (!exitConfirmButton) return;
  exitConfirmButton.disabled = isSubmitting;
  exitConfirmButton.textContent = isSubmitting ? "Saving..." : "Confirm Pig Exits";
}

function updateExitConfirmPanel(sale, items) {
  if (!exitConfirmPanel) return;
  const hasPigItems = items.some((item) => item.pig_id);
  const saleStatus = String(sale.sale_status || "").trim();
  const paymentStatus = String(sale.payment_status || "").trim();
  const isClosed = ["Completed", "Cancelled"].includes(saleStatus) || paymentStatus === "Paid";
  const canConfirm = sale.sale_stream === "Slaughter" && !isClosed && hasPigItems;
  exitConfirmPanel.classList.toggle("hidden", !canConfirm);
  if (canConfirm && exitDateInput && !exitDateInput.value) {
    exitDateInput.value = dateOnly(sale.sale_date);
  }
}

function renderItems(items) {
  if (!items.length) {
    itemsBody.innerHTML = '<tr><td colspan="5" class="table-empty">No sale items found.</td></tr>';
    itemsCount.textContent = "No items linked to this sale.";
    return;
  }

  itemsCount.textContent = `${items.length} item${items.length === 1 ? "" : "s"} linked to this sale.`;
  itemsBody.innerHTML = items.map((item) => `
    <tr>
      <td>
        <strong>${escapeHtml(valueOrDash(item.description || item.item_type))}</strong>
        <span class="table-subtext">${escapeHtml(valueOrDash(item.sale_item_id))}</span>
      </td>
      <td>
        <strong>${escapeHtml(valueOrDash(item.tag_number || item.pig_id))}</strong>
        <span class="table-subtext">${escapeHtml(valueOrDash(item.pig_id))}</span>
      </td>
      <td>
        <span class="table-subtext">Live: ${escapeHtml(item.live_weight_kg ?? "-")}</span>
        <span class="table-subtext">Carcass: ${escapeHtml(item.carcass_weight_kg ?? "-")}</span>
        <span class="table-subtext">Packed: ${escapeHtml(item.packed_weight_kg ?? "-")}</span>
      </td>
      <td>
        <strong>${money(item.line_total)}</strong>
        <span class="table-subtext">${escapeHtml(valueOrDash(item.pricing_basis))}</span>
      </td>
      <td>${escapeHtml(valueOrDash(item.notes))}</td>
    </tr>
  `).join("");
}

async function loadSaleDetail() {
  try {
    const response = await fetch(`/api/sales-transactions/${encodeURIComponent(saleId)}`);
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.message || "Could not load sale detail.");
    }

    const sale = data.sales_transaction || {};
    loadedSale = sale;
    const items = data.items || [];
    title.textContent = transactionLabel(sale);
    subtitle.textContent = `${sale.sale_id || saleId} · ${valueOrDash(sale.buyer_name)} · ${dateOnly(sale.sale_date)}`;

    renderDetailList(summaryList, [
      ["Sale Date", dateOnly(sale.sale_date)],
      ["Buyer", sale.buyer_name],
      ["Destination", sale.destination],
      ["Stream", sale.sale_stream],
      ["Sale Status", sale.sale_status],
      [isAuction(sale) ? "Auction completed" : "Sale completed", sale.sale_status === "Completed" ? "Yes" : "No"],
      ["Pig Count", sale.pig_count],
      ["Created By", sale.created_by],
      ["Notes", sale.notes],
    ]);

    renderDetailList(paymentList, [
      ["Payment Status", sale.payment_status],
      ["Payment Method", sale.payment_method],
      ["Payment Date", dateOnly(sale.payment_date)],
      ["Financial disposition", sale.financial_disposition || "Commercial"],
      ["Amount receivable", money(sale.receivable_total ?? sale.net_settlement_payable ?? sale.net_total)],
      ["Settlement received", sale.payment_status === "Paid" ? "Yes" : sale.payment_status === "Not_Applicable" ? "Not applicable" : "No"],
      ["Fully reconciled", sale.sale_status === "Completed" && ["Paid", "Not_Applicable"].includes(sale.payment_status) ? "Yes" : "No"],
      ["Gross Total", money(sale.gross_total)],
      ["Deductions", money(sale.deductions_total)],
      ["Net Total", money(sale.net_total)],
      ["Currency", sale.currency],
      ["Updated", dateOnly(sale.updated_at)],
    ]);

    renderItems(items);
    updateExitConfirmPanel(sale, items);
    updatePaymentPanel(sale);
  } catch (error) {
    showMessage(error.message || "Could not load sale detail.");
    itemsBody.innerHTML = '<tr><td colspan="5" class="table-empty">Could not load sale items.</td></tr>';
  }
}

function updatePaymentPanel(sale) {
  if (!paymentForm) return;
  const canRecord = sale.sale_status !== "Cancelled" && !["Paid", "Not_Applicable"].includes(sale.payment_status);
  paymentForm.classList.toggle("hidden", !canRecord);
  if (charityForm) {
    charityForm.classList.toggle("hidden", !canRecord || sale.sale_stream !== "Livestock" || sale.sale_status !== "Completed");
  }
  if (!canRecord) return;
  const due = sale.net_settlement_payable ?? sale.net_total;
  const currentReceived = Number(sale.received_total || 0);
  if (!paymentAmountInput.value && due !== null && due !== undefined) {
    paymentAmountInput.value = Math.max(0, Number(due) - currentReceived).toFixed(2);
  }
  paymentMethodInput.value = sale.payment_method === "Cash" ? "Cash" : "EFT";
}

async function previewCharity(event) {
  event.preventDefault();
  pendingCharityPreview = null;
  charityConfirmButton.classList.add("hidden");
  const payload = { reason: charityReasonInput.value.trim(),
    correction_reason: charityCorrectionInput.value.trim() };
  charityPreviewButton.disabled = true;
  try {
    const response = await fetch(`/api/sales-transactions/${encodeURIComponent(saleId)}/charitable-disposition/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error((data.errors || []).join(" ") || data.status || "Could not preview charitable disposition.");
    charityPreviewBox.textContent = data.preview.human_readable;
    charityPreviewBox.classList.remove("hidden");
    pendingCharityPreview = { payload, digest: data.preview_digest, token: data.confirmation_token };
    charityConfirmButton.classList.remove("hidden");
  } catch (error) { showMessage(error.message); }
  finally { charityPreviewButton.disabled = false; }
}

async function confirmCharity() {
  if (!pendingCharityPreview) return;
  charityConfirmButton.disabled = true;
  try {
    const response = await fetch(`/api/sales-transactions/${encodeURIComponent(saleId)}/charitable-disposition/confirm`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        ...pendingCharityPreview.payload, confirmed_preview_digest: pendingCharityPreview.digest,
        confirmation_token: pendingCharityPreview.token,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error((data.errors || []).join(" ") || data.status || "Could not record charitable disposition.");
    pendingCharityPreview = null;
    showMessage("Charitable giveaway recorded with no payment due.", "success");
    await loadSaleDetail();
  } catch (error) { showMessage(error.message); }
  finally { charityConfirmButton.disabled = false; }
}

function paymentRequestPayload() {
  const receiptCents = Math.round(Number(paymentAmountInput.value) * 100);
  const currentCents = Math.round(Number(loadedSale?.received_total || 0) * 100);
  const dueCents = Math.round(Number(loadedSale?.net_settlement_payable ?? loadedSale?.net_total) * 100);
  if (!Number.isFinite(receiptCents) || receiptCents <= 0) throw new Error("Enter the amount received in this receipt.");
  if (!paymentDateInput.value) throw new Error("Bank receipt date is required.");
  const cumulativeCents = currentCents + receiptCents;
  return { payment_status: cumulativeCents === dueCents ? "Paid" : "Part_Paid",
    received_amount: (cumulativeCents / 100).toFixed(2),
    payment_method: paymentMethodInput.value, payment_date: paymentDateInput.value };
}

function invalidateSettlementPreview() {
  paymentPreviewGeneration += 1;
  pendingPaymentPreview = null;
  paymentConfirmButton.classList.add("hidden");
  paymentPreviewBox.classList.add("hidden");
  paymentPreviewBox.textContent = "";
}

async function previewSettlement(event) {
  event.preventDefault();
  pendingPaymentPreview = null;
  paymentConfirmButton.classList.add("hidden");
  let payload;
  try { payload = paymentRequestPayload(); } catch (error) { showMessage(error.message); return; }
  const generation = ++paymentPreviewGeneration;
  paymentPreviewButton.disabled = true;
  try {
    const response = await fetch(`/api/sales-transactions/${encodeURIComponent(saleId)}/payment-state/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (generation !== paymentPreviewGeneration) return;
    if (!response.ok || !data.success) throw new Error((data.errors || []).join(" ") || data.status || "Could not preview settlement.");
    const preview = data.preview || {};
    paymentPreviewBox.textContent = `${preview.human_readable} ${isAuction(loadedSale) ? "Auction" : "Sale"} completion remains unchanged.`;
    paymentPreviewBox.classList.remove("hidden");
    if (data.confirmation_required) {
      pendingPaymentPreview = { payload, digest: data.preview_digest, token: data.confirmation_token };
      paymentConfirmButton.classList.remove("hidden");
    }
  } catch (error) { showMessage(error.message || "Could not preview settlement."); }
  finally { paymentPreviewButton.disabled = false; }
}

async function confirmSettlement() {
  if (!pendingPaymentPreview) return;
  paymentConfirmButton.disabled = true;
  try {
    const response = await fetch(`/api/sales-transactions/${encodeURIComponent(saleId)}/payment-state/confirm`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        ...pendingPaymentPreview.payload, confirmed_preview_digest: pendingPaymentPreview.digest,
        confirmation_token: pendingPaymentPreview.token,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error((data.errors || []).join(" ") || data.status || "Could not confirm settlement.");
    pendingPaymentPreview = null;
    showMessage("Settlement receipt recorded once in Supabase.", "success");
    await loadSaleDetail();
  } catch (error) { pendingPaymentPreview = null; paymentConfirmButton.classList.add("hidden"); showMessage(error.message); }
  finally { paymentConfirmButton.disabled = false; }
}

async function submitExitConfirmation(event) {
  event.preventDefault();
  if (!window.confirm("Confirm linked pigs exited for slaughter? This updates pig records and keeps their history.")) {
    return;
  }

  setExitSubmitting(true);
  try {
    const response = await fetch(`/api/sales-transactions/${encodeURIComponent(saleId)}/confirm-pig-exits`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        exit_date: exitDateInput.value,
        changed_by: exitChangedByInput.value,
        notes: exitNotesInput.value,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || []).join(" ") || data.message || "Could not confirm pig exits.");
    }
    showMessage(`Pig exits confirmed: ${data.pigs_updated || 0}`, "success");
    await loadSaleDetail();
  } catch (error) {
    showMessage(error.message || "Could not confirm pig exits.");
  } finally {
    setExitSubmitting(false);
  }
}

backButton.addEventListener("click", () => {
  window.location.href = safeInternalReturnPath(backButton.dataset.returnTo) || saleDetailFallbackPath();
});

if (exitConfirmForm) {
  exitConfirmForm.addEventListener("submit", submitExitConfirmation);
}
if (paymentForm) paymentForm.addEventListener("submit", previewSettlement);
if (paymentConfirmButton) paymentConfirmButton.addEventListener("click", confirmSettlement);
if (charityForm) charityForm.addEventListener("submit", previewCharity);
if (charityConfirmButton) charityConfirmButton.addEventListener("click", confirmCharity);
[paymentAmountInput, paymentMethodInput, paymentDateInput].forEach((element) => {
  if (element) element.addEventListener("input", invalidateSettlementPreview);
});

updateBackButtonFromQuery();
loadSaleDetail();
