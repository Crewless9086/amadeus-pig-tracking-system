const form = document.getElementById("slaughter_sale_form");
const messageBox = document.getElementById("slaughter_sale_message");
const saleDateInput = document.getElementById("sale_date");
const pigRowsContainer = document.getElementById("slaughter_pig_rows");
const addPigButton = document.getElementById("add_slaughter_pig_button");
const batchTotalDisplay = document.getElementById("slaughter_batch_total");
const batchTotalHelper = document.getElementById("batch_total_helper");
const buyerNameInput = document.getElementById("buyer_name");
const destinationInput = document.getElementById("destination");
const paymentStatusSelect = document.getElementById("payment_status");
const paymentMethodSelect = document.getElementById("payment_method");
const saleStatusSelect = document.getElementById("sale_status");
const createdByInput = document.getElementById("created_by");
const notesInput = document.getElementById("notes");
const submitButtons = Array.from(document.querySelectorAll(".submit-button"));
const transactionsBody = document.getElementById("slaughter_transactions_body");
const transactionCount = document.getElementById("slaughter_transactions_count");
const transactionSearch = document.getElementById("slaughter_search");
const transactionStatusFilter = document.getElementById("slaughter_status_filter");
const transactionPaymentFilter = document.getElementById("slaughter_payment_filter");
const clearFiltersButton = document.getElementById("clear_slaughter_filters_button");
const updatePanel = document.getElementById("slaughter_update_panel");
const updateForm = document.getElementById("slaughter_update_form");
const updateSaleLabel = document.getElementById("slaughter_update_sale_label");
const updateSaleIdInput = document.getElementById("update_sale_id");
const updateItemCountInput = document.getElementById("update_item_count");
const updateLineTotalInput = document.getElementById("update_line_total");
const updatePaymentStatusSelect = document.getElementById("update_payment_status");
const updatePaymentMethodSelect = document.getElementById("update_payment_method");
const updatePaymentDateInput = document.getElementById("update_payment_date");
const updateSaleStatusSelect = document.getElementById("update_sale_status");
const updateCarcassWeightInput = document.getElementById("update_carcass_weight");
const updateCarcassHelper = document.getElementById("update_carcass_helper");
const updateByInput = document.getElementById("update_by");
const updateReasonInput = document.getElementById("update_reason");
const submitUpdateButton = document.getElementById("submit_slaughter_update");
const closeUpdatePanelButton = document.getElementById("close_slaughter_update_panel");

let allPigs = [];
let allTransactions = [];
let pigRowCounter = 0;

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

function setUpdateSubmitting(isSubmitting) {
  submitUpdateButton.disabled = isSubmitting;
  submitUpdateButton.textContent = isSubmitting ? "Saving..." : "Save Payment Update";
}

function money(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "R0.00";
  }
  return `R${Number(value).toFixed(2)}`;
}

function updatePigRowHelper(row) {
  const select = row.querySelector(".slaughter-pig-select");
  const helper = row.querySelector(".pig-row-helper");
  const selected = allPigs.find((pig) => pig.pig_id === select.value);
  if (!selected) {
    helper.textContent = "Select a pig for this slaughter batch.";
    return;
  }

  const tag = formatTagNumber(selected.tag_number || selected.pig_id);
  const pen = selected.current_pen_name || selected.current_pen_id || "No pen";
  const weight = selected.current_weight_kg ? `${selected.current_weight_kg} kg` : "no current weight";
  helper.textContent = `${tag} - ${pen}, ${weight}`;
}

function renderPigOptions(select, selectedValue = "") {
  select.innerHTML = '<option value="">Select pig...</option>';
  sortPigsForDisplay(allPigs).forEach((pig) => {
    const option = document.createElement("option");
    const tag = formatTagNumber(pig.tag_number || pig.pig_id);
    const pen = pig.current_pen_name || pig.current_pen_id || "No pen";
    option.value = pig.pig_id;
    option.textContent = `${tag} - ${pen} (${pig.pig_id})`;
    select.appendChild(option);
  });
  select.value = selectedValue;
}

function refreshPigOptions() {
  pigRowsContainer.querySelectorAll(".slaughter-pig-select").forEach((select) => {
    renderPigOptions(select, select.value);
  });
  pigRowsContainer.querySelectorAll(".slaughter-pig-row").forEach(updatePigRowHelper);
}

function addPigRow() {
  pigRowCounter += 1;
  const row = document.createElement("div");
  row.className = "slaughter-pig-row";
  row.dataset.rowId = String(pigRowCounter);
  row.innerHTML = `
    <div class="form-grid slaughter-pig-grid">
      <div class="form-group">
        <label for="slaughter_pig_${pigRowCounter}">Pig</label>
        <select id="slaughter_pig_${pigRowCounter}" class="slaughter-pig-select" required></select>
        <div class="field-helper pig-row-helper">Select a pig for this slaughter batch.</div>
      </div>

      <div class="form-group">
        <label for="slaughter_amount_${pigRowCounter}">Amount</label>
        <input type="number" step="0.01" inputmode="decimal" id="slaughter_amount_${pigRowCounter}" class="slaughter-line-total no-spinner" required />
      </div>

      <div class="form-group">
        <label for="slaughter_carcass_${pigRowCounter}">Carcass Weight (Optional)</label>
        <input type="number" step="0.001" inputmode="decimal" id="slaughter_carcass_${pigRowCounter}" class="slaughter-carcass-weight no-spinner" />
      </div>

      <div class="form-group">
        <label for="slaughter_note_${pigRowCounter}">Pig Note (Optional)</label>
        <input type="text" id="slaughter_note_${pigRowCounter}" class="slaughter-item-note" />
      </div>
    </div>

    <div class="form-actions compact-actions slaughter-row-actions">
      <button type="button" class="small-action-button" data-remove-pig-row>Remove Pig</button>
    </div>
  `;

  pigRowsContainer.appendChild(row);
  renderPigOptions(row.querySelector(".slaughter-pig-select"));
  updateBatchTotal();
}

async function loadPigs() {
  try {
    const response = await fetch("/api/pig-weights/pigs");
    const data = await response.json();
    allPigs = data.pigs || [];
    refreshPigOptions();
  } catch (error) {
    pigRowsContainer.querySelectorAll(".slaughter-pig-select").forEach((select) => {
      select.innerHTML = '<option value="">Could not load pigs</option>';
    });
    showMessage("Could not load active pigs.", "error");
  }
}

function selectedPigRows() {
  return Array.from(pigRowsContainer.querySelectorAll(".slaughter-pig-row"));
}

function updateBatchTotal() {
  const total = selectedPigRows().reduce((sum, row) => {
    const value = Number(row.querySelector(".slaughter-line-total").value || 0);
    return sum + (Number.isNaN(value) ? 0 : value);
  }, 0);

  batchTotalDisplay.textContent = money(total);
  batchTotalHelper.textContent = `${selectedPigRows().length} pig row${selectedPigRows().length === 1 ? "" : "s"} in this batch.`;
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
          <button type="button" class="small-action-button" data-update-sale-id="${item.sale_id}" data-current-total="${item.net_total ?? ""}" data-item-count="${item.item_count ?? 0}">Update Payment</button>
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

function todayIsoDate() {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
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
  const items = selectedPigRows().map((row) => {
    const select = row.querySelector(".slaughter-pig-select");
    const selected = allPigs.find((pig) => pig.pig_id === select.value) || {};
    const tag = formatTagNumber(selected.tag_number || "");
    const lineTotal = Number(row.querySelector(".slaughter-line-total").value);
    const carcassWeightValue = row.querySelector(".slaughter-carcass-weight").value;
    const carcassWeight = carcassWeightValue ? Number(carcassWeightValue) : null;
    const itemNote = row.querySelector(".slaughter-item-note").value.trim();

    return {
      item_type: "Pig",
      pig_id: select.value,
      tag_number: tag,
      description: `Slaughter pig ${tag || select.value}`,
      quantity: 1,
      line_total: lineTotal,
      pricing_basis: "Per_Pig",
      carcass_weight_kg: carcassWeight,
      notes: itemNote,
    };
  });

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
    items,
  };
}

function selectedPigLabels() {
  return selectedPigRows()
    .map((row) => {
      const pigId = row.querySelector(".slaughter-pig-select").value;
      const selected = allPigs.find((pig) => pig.pig_id === pigId);
      return formatTagNumber(selected?.tag_number || pigId);
    })
    .filter(Boolean);
}

function duplicateSelectedPigIds() {
  const seen = new Set();
  const duplicates = new Set();
  selectedPigRows().forEach((row) => {
    const pigId = row.querySelector(".slaughter-pig-select").value;
    if (!pigId) return;
    if (seen.has(pigId)) duplicates.add(pigId);
    seen.add(pigId);
  });
  return Array.from(duplicates);
}

async function submitForm(event) {
  event.preventDefault();
  clearMessage();

  const duplicates = duplicateSelectedPigIds();
  if (duplicates.length) {
    showMessage("The same pig is selected more than once in this batch.", "error");
    return;
  }

  const labels = selectedPigLabels();
  const confirmMessage = `Create slaughter sale for ${labels.join(", ")}?\n\nThis writes to Supabase and does not update Google Sheets.`;
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
    pigRowsContainer.innerHTML = "";
    addPigRow();
    buyerNameInput.value = "JC Slaghuis";
    destinationInput.value = "Bartelsfontein";
    paymentStatusSelect.value = "Unpaid";
    paymentMethodSelect.value = "EFT";
    saleStatusSelect.value = "Confirmed";
    createdByInput.value = "Charl";
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

function openUpdatePanel(saleId, currentTotal, itemCount = 1) {
  clearMessage();
  const transaction = allTransactions.find((item) => item.sale_id === saleId) || {};
  const count = Number(itemCount || transaction.item_count || 1);

  updateSaleIdInput.value = saleId;
  updateItemCountInput.value = String(count);
  updateLineTotalInput.value = currentTotal || transaction.net_total || "";
  updatePaymentStatusSelect.value = transaction.payment_status || "Paid";
  updatePaymentMethodSelect.value = transaction.payment_method || "EFT";
  updatePaymentDateInput.value = transaction.payment_date || (updatePaymentStatusSelect.value === "Paid" ? todayIsoDate() : "");
  updateSaleStatusSelect.value = transaction.sale_status || (updatePaymentStatusSelect.value === "Paid" ? "Completed" : "Confirmed");
  updateCarcassWeightInput.value = transaction.carcass_weight_kg || "";
  updateByInput.value = createdByInput.value.trim() || "Charl";
  updateReasonInput.value = "Butcher payment updated";
  updateSaleLabel.textContent = `${saleId} - ${transaction.buyer_name || "Slaughter sale"} (${count} pig${count === 1 ? "" : "s"})`;
  updateCarcassWeightInput.disabled = count > 1;
  updateCarcassHelper.textContent = count > 1
    ? "Carcass weight updates are only available for one-pig transactions in this slice."
    : "Optional actual carcass weight from the butcher.";
  if (count > 1) updateCarcassWeightInput.value = "";

  updatePanel.classList.remove("hidden");
  updateLineTotalInput.focus();
  updatePanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeUpdatePanel() {
  updatePanel.classList.add("hidden");
  updateForm.reset();
}

function buildUpdatePayload() {
  const lineTotal = Number(updateLineTotalInput.value);
  const carcassWeightValue = updateCarcassWeightInput.value.trim();
  const carcassWeight = carcassWeightValue ? Number(carcassWeightValue) : null;

  if (Number.isNaN(lineTotal) || lineTotal < 0) {
    throw new Error("Final amount must be a valid number.");
  }
  if (updatePaymentStatusSelect.value === "Paid" && !updatePaymentDateInput.value) {
    throw new Error("Payment date is required when payment status is Paid.");
  }
  if (carcassWeight !== null && Number.isNaN(carcassWeight)) {
    throw new Error("Carcass weight must be a valid number or blank.");
  }

  return {
    updated_by: updateByInput.value.trim() || "Charl",
    update_reason: updateReasonInput.value.trim(),
    line_total: lineTotal,
    payment_status: updatePaymentStatusSelect.value,
    payment_method: updatePaymentMethodSelect.value,
    payment_date: updatePaymentDateInput.value,
    sale_status: updateSaleStatusSelect.value,
    carcass_weight_kg: updateCarcassWeightInput.disabled ? null : carcassWeight,
  };
}

async function submitUpdatePayment(event) {
  event.preventDefault();
  clearMessage();
  const saleId = updateSaleIdInput.value;

  let payload;
  try {
    payload = buildUpdatePayload();
  } catch (error) {
    showMessage(error.message, "error");
    return;
  }

  setUpdateSubmitting(true);

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
    closeUpdatePanel();
    await loadTransactions();
  } catch (error) {
    showMessage(error.message || "Could not update payment.", "error");
  } finally {
    setUpdateSubmitting(false);
  }
}

transactionsBody.addEventListener("click", (event) => {
  const updateButton = event.target.closest("[data-update-sale-id]");
  if (updateButton) {
    openUpdatePanel(
      updateButton.dataset.updateSaleId,
      updateButton.dataset.currentTotal,
      updateButton.dataset.itemCount,
    );
    return;
  }

  const button = event.target.closest("[data-cancel-sale-id]");
  if (!button) return;
  cancelTransaction(button.dataset.cancelSaleId);
});

pigRowsContainer.addEventListener("change", (event) => {
  const row = event.target.closest(".slaughter-pig-row");
  if (row && event.target.classList.contains("slaughter-pig-select")) {
    updatePigRowHelper(row);
  }
  updateBatchTotal();
});

pigRowsContainer.addEventListener("input", updateBatchTotal);

pigRowsContainer.addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove-pig-row]");
  if (!button) return;
  if (selectedPigRows().length === 1) {
    showMessage("Keep at least one pig row in the batch.", "error");
    return;
  }
  button.closest(".slaughter-pig-row").remove();
  updateBatchTotal();
});

addPigButton.addEventListener("click", () => {
  addPigRow();
});

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
updateForm.addEventListener("submit", submitUpdatePayment);
closeUpdatePanelButton.addEventListener("click", closeUpdatePanel);
updatePaymentStatusSelect.addEventListener("change", () => {
  if (updatePaymentStatusSelect.value === "Paid") {
    updatePaymentDateInput.value = updatePaymentDateInput.value || todayIsoDate();
    updateSaleStatusSelect.value = "Completed";
  } else if (updateSaleStatusSelect.value === "Completed") {
    updateSaleStatusSelect.value = "Confirmed";
  }
});

setTodayDate();
addPigRow();
loadPigs();
loadTransactions();
