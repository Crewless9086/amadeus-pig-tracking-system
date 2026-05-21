const form = document.getElementById("slaughter_sale_form");
const messageBox = document.getElementById("slaughter_sale_message");
const saleDateInput = document.getElementById("sale_date");
const pigSelect = document.getElementById("pig_id");
const pigHelper = document.getElementById("pig_helper");
const buyerNameInput = document.getElementById("buyer_name");
const destinationInput = document.getElementById("destination");
const paymentStatusSelect = document.getElementById("payment_status");
const paymentMethodSelect = document.getElementById("payment_method");
const saleStatusSelect = document.getElementById("sale_status");
const createdByInput = document.getElementById("created_by");
const unitPriceInput = document.getElementById("unit_price");
const carcassWeightInput = document.getElementById("carcass_weight_kg");
const notesInput = document.getElementById("notes");
const submitButtons = Array.from(document.querySelectorAll(".submit-button"));
const transactionsBody = document.getElementById("slaughter_transactions_body");
const transactionCount = document.getElementById("slaughter_transactions_count");
const transactionSearch = document.getElementById("slaughter_search");
const transactionStatusFilter = document.getElementById("slaughter_status_filter");
const transactionPaymentFilter = document.getElementById("slaughter_payment_filter");
const clearFiltersButton = document.getElementById("clear_slaughter_filters_button");

let allPigs = [];
let allTransactions = [];

function setTodayDate() {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  saleDateInput.value = `${yyyy}-${mm}-${dd}`;
}

function formatTagNumber(value) {
  const raw = String(value || "").trim();
  if (/^\d+$/.test(raw)) {
    return raw.padStart(3, "0");
  }
  return raw;
}

function pigSortKey(pig) {
  const tag = String(pig.tag_number || pig.pig_id || "").trim();
  const numericMatch = tag.match(/\d+/);
  const numericPart = numericMatch ? Number(numericMatch[0]) : Number.MAX_SAFE_INTEGER;
  return [
    String(pig.current_pen_name || pig.current_pen_id || "").toLowerCase(),
    numericPart,
    tag.toLowerCase(),
    String(pig.pig_id || "").toLowerCase(),
  ];
}

function sortPigsForDisplay(pigs) {
  return [...pigs].sort((a, b) => {
    const left = pigSortKey(a);
    const right = pigSortKey(b);
    for (let index = 0; index < left.length; index += 1) {
      if (left[index] < right[index]) return -1;
      if (left[index] > right[index]) return 1;
    }
    return 0;
  });
}

function showMessage(message, type = "success") {
  messageBox.classList.remove("hidden", "message-success", "message-error");
  messageBox.classList.add(type === "success" ? "message-success" : "message-error");
  messageBox.textContent = message;
}

function clearMessage() {
  messageBox.classList.add("hidden");
  messageBox.textContent = "";
  messageBox.classList.remove("message-success", "message-error");
}

function setSubmitting(isSubmitting) {
  submitButtons.forEach((button) => {
    button.disabled = isSubmitting;
    button.textContent = isSubmitting ? "Saving..." : "Save Slaughter Sale";
  });
}

function money(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "R0.00";
  }
  return `R${Number(value).toFixed(2)}`;
}

function updatePigHelper() {
  const selected = allPigs.find((pig) => pig.pig_id === pigSelect.value);
  if (!selected) {
    pigHelper.textContent = "Select the pig that went to slaughter.";
    return;
  }

  const tag = formatTagNumber(selected.tag_number || selected.pig_id);
  const pen = selected.current_pen_name || selected.current_pen_id || "No pen";
  const weight = selected.current_weight_kg ? `${selected.current_weight_kg} kg` : "no current weight";
  pigHelper.textContent = `${tag} - ${pen}, ${weight}`;
}

function renderPigOptions() {
  pigSelect.innerHTML = '<option value="">Select pig...</option>';
  sortPigsForDisplay(allPigs).forEach((pig) => {
    const option = document.createElement("option");
    const tag = formatTagNumber(pig.tag_number || pig.pig_id);
    const pen = pig.current_pen_name || pig.current_pen_id || "No pen";
    option.value = pig.pig_id;
    option.textContent = `${tag} - ${pen} (${pig.pig_id})`;
    pigSelect.appendChild(option);
  });
}

async function loadPigs() {
  try {
    const response = await fetch("/api/pig-weights/pigs");
    const data = await response.json();
    allPigs = data.pigs || [];
    renderPigOptions();
  } catch (error) {
    pigSelect.innerHTML = '<option value="">Could not load pigs</option>';
    showMessage("Could not load active pigs.", "error");
  }
}

function applyTransactionFilters() {
  const query = transactionSearch.value.trim().toLowerCase();
  const status = transactionStatusFilter.value;
  const payment = transactionPaymentFilter.value;

  const filtered = allTransactions.filter((item) => {
    const searchable = [
      item.sale_id,
      item.buyer_name,
      item.destination,
      item.sale_status,
      item.payment_status,
      item.net_total,
      item.sale_date,
    ].join(" ").toLowerCase();

    return (
      (!query || searchable.includes(query))
      && (!status || item.sale_status === status)
      && (!payment || item.payment_status === payment)
    );
  });

  renderTransactions(filtered);
}

function renderTransactions(rows) {
  if (!rows.length) {
    transactionsBody.innerHTML = '<tr><td colspan="8" class="table-empty">No slaughter transactions found.</td></tr>';
    transactionCount.textContent = allTransactions.length
      ? "No transactions match the selected filters."
      : "No slaughter transactions recorded yet.";
    return;
  }

  transactionCount.textContent = `Showing ${rows.length} of ${allTransactions.length} slaughter transactions.`;

  transactionsBody.innerHTML = rows.map((item) => {
    const isCancelled = item.sale_status === "Cancelled";
    const action = isCancelled
      ? '<span class="muted-text">Cancelled</span>'
      : `
        <div class="inline-action-group">
          <button type="button" class="small-action-button" data-update-sale-id="${item.sale_id}" data-current-total="${item.net_total ?? ""}">Update Payment</button>
          <button type="button" class="small-action-button" data-cancel-sale-id="${item.sale_id}">Cancel</button>
        </div>
      `;
    const rowClass = isCancelled ? ' class="muted-row"' : "";
    const statusClass = isCancelled ? "status-pill status-pill-muted" : "status-pill";
    return `
      <tr${rowClass}>
        <td>${formatDate(item.sale_date)}</td>
        <td>${item.sale_id || "-"}</td>
        <td>${item.buyer_name || "-"}</td>
        <td><span class="${statusClass}">${item.sale_status || "-"}</span></td>
        <td><span class="${statusClass}">${item.payment_status || "-"}</span></td>
        <td>${money(item.net_total)}</td>
        <td>${item.item_count ?? "-"}</td>
        <td>${action}</td>
      </tr>
    `;
  }).join("");
}

function formatDate(value) {
  if (!value) return "-";
  return String(value).slice(0, 10);
}

async function loadTransactions() {
  try {
    const response = await fetch("/api/sales-transactions?sale_stream=Slaughter&limit=25");
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.message || "Could not load transactions.");
    }
    allTransactions = data.sales_transactions || [];
    applyTransactionFilters();
  } catch (error) {
    transactionsBody.innerHTML = '<tr><td colspan="8" class="table-empty">Could not load slaughter transactions.</td></tr>';
  }
}

function buildPayload() {
  const selected = allPigs.find((pig) => pig.pig_id === pigSelect.value) || {};
  const tag = formatTagNumber(selected.tag_number || "");
  const carcassWeight = carcassWeightInput.value ? Number(carcassWeightInput.value) : null;

  return {
    sale_date: saleDateInput.value,
    sale_stream: "Slaughter",
    buyer_name: buyerNameInput.value.trim(),
    destination: destinationInput.value.trim(),
    payment_status: paymentStatusSelect.value,
    payment_method: paymentMethodSelect.value,
    sale_status: saleStatusSelect.value,
    created_by: createdByInput.value.trim(),
    notes: notesInput.value.trim(),
    items: [
      {
        item_type: "Pig",
        pig_id: pigSelect.value,
        tag_number: tag,
        description: `Slaughter pig ${tag || pigSelect.value}`,
        quantity: 1,
        unit_price: Number(unitPriceInput.value),
        pricing_basis: "Per_Pig",
        carcass_weight_kg: carcassWeight,
      },
    ],
  };
}

async function submitForm(event) {
  event.preventDefault();
  clearMessage();

  const selected = allPigs.find((pig) => pig.pig_id === pigSelect.value);
  const tag = formatTagNumber(selected?.tag_number || pigSelect.value);
  const confirmMessage = `Create slaughter sale for ${tag}?\n\nThis writes to Supabase and does not update Google Sheets.`;
  if (!window.confirm(confirmMessage)) {
    return;
  }

  setSubmitting(true);

  try {
    const response = await fetch("/api/sales-transactions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    const data = await response.json();

    if (!response.ok || !data.success) {
      const message = data.errors ? data.errors.join(" ") : (data.message || "Could not save slaughter sale.");
      throw new Error(message);
    }

    showMessage(`Slaughter sale saved: ${data.sale_id}`, "success");
    form.reset();
    setTodayDate();
    buyerNameInput.value = "JC Slaghuis";
    destinationInput.value = "Bartelsfontein";
    paymentStatusSelect.value = "Unpaid";
    paymentMethodSelect.value = "EFT";
    saleStatusSelect.value = "Confirmed";
    createdByInput.value = "Charl";
    updatePigHelper();
    await loadTransactions();
  } catch (error) {
    showMessage(error.message || "Could not save slaughter sale.", "error");
  } finally {
    setSubmitting(false);
  }
}

async function cancelTransaction(saleId) {
  const reason = window.prompt(`Reason for cancelling ${saleId}?`);
  if (!reason) return;

  try {
    const response = await fetch(`/api/sales-transactions/${encodeURIComponent(saleId)}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cancelled_by: createdByInput.value.trim() || "Charl",
        cancel_reason: reason,
      }),
    });
    const data = await response.json();

    if (!response.ok || !data.success) {
      const message = data.errors ? data.errors.join(" ") : (data.message || "Could not cancel transaction.");
      throw new Error(message);
    }

    showMessage(`Transaction cancelled: ${saleId}`, "success");
    await loadTransactions();
  } catch (error) {
    showMessage(error.message || "Could not cancel transaction.", "error");
  }
}

async function updatePayment(saleId, currentTotal) {
  const amount = window.prompt(`Final amount for ${saleId}?`, currentTotal || "");
  if (amount === null) return;

  const cleanAmount = Number(amount);
  if (Number.isNaN(cleanAmount) || cleanAmount < 0) {
    showMessage("Final amount must be a valid number.", "error");
    return;
  }

  const paymentStatus = window.prompt("Payment status: Unpaid, Part_Paid, or Paid", "Paid");
  if (paymentStatus === null) return;

  const saleStatus = window.prompt("Sale status: Confirmed or Completed", paymentStatus === "Paid" ? "Completed" : "Confirmed");
  if (saleStatus === null) return;

  const carcassWeight = window.prompt("Carcass weight in kg, if known. Leave blank if unknown.", "");
  if (carcassWeight === null) return;

  const reason = window.prompt("Reason / note for this update", "Butcher payment updated");
  if (!reason) return;

  const payload = {
    updated_by: createdByInput.value.trim() || "Charl",
    update_reason: reason,
    line_total: cleanAmount,
    payment_status: paymentStatus.trim(),
    payment_method: "EFT",
    sale_status: saleStatus.trim(),
    carcass_weight_kg: carcassWeight.trim() ? Number(carcassWeight) : null,
  };

  if (payload.carcass_weight_kg !== null && Number.isNaN(payload.carcass_weight_kg)) {
    showMessage("Carcass weight must be a valid number or blank.", "error");
    return;
  }

  try {
    const response = await fetch(`/api/sales-transactions/${encodeURIComponent(saleId)}/payment`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();

    if (!response.ok || !data.success) {
      const message = data.errors ? data.errors.join(" ") : (data.message || "Could not update payment.");
      throw new Error(message);
    }

    showMessage(`Payment updated: ${saleId}`, "success");
    await loadTransactions();
  } catch (error) {
    showMessage(error.message || "Could not update payment.", "error");
  }
}

transactionsBody.addEventListener("click", (event) => {
  const updateButton = event.target.closest("[data-update-sale-id]");
  if (updateButton) {
    updatePayment(updateButton.dataset.updateSaleId, updateButton.dataset.currentTotal);
    return;
  }

  const button = event.target.closest("[data-cancel-sale-id]");
  if (!button) return;
  cancelTransaction(button.dataset.cancelSaleId);
});

pigSelect.addEventListener("change", updatePigHelper);
form.addEventListener("submit", submitForm);
transactionSearch.addEventListener("input", applyTransactionFilters);
transactionStatusFilter.addEventListener("change", applyTransactionFilters);
transactionPaymentFilter.addEventListener("change", applyTransactionFilters);
clearFiltersButton.addEventListener("click", () => {
  transactionSearch.value = "";
  transactionStatusFilter.value = "";
  transactionPaymentFilter.value = "";
  applyTransactionFilters();
});

setTodayDate();
loadPigs();
loadTransactions();
