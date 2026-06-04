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
      <dt>${label}</dt>
      <dd>${valueOrDash(value)}</dd>
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
        <strong>${valueOrDash(item.description || item.item_type)}</strong>
        <span class="table-subtext">${valueOrDash(item.sale_item_id)}</span>
      </td>
      <td>
        <strong>${valueOrDash(item.tag_number || item.pig_id)}</strong>
        <span class="table-subtext">${valueOrDash(item.pig_id)}</span>
      </td>
      <td>
        <span class="table-subtext">Live: ${item.live_weight_kg ?? "-"}</span>
        <span class="table-subtext">Carcass: ${item.carcass_weight_kg ?? "-"}</span>
        <span class="table-subtext">Packed: ${item.packed_weight_kg ?? "-"}</span>
      </td>
      <td>
        <strong>${money(item.line_total)}</strong>
        <span class="table-subtext">${valueOrDash(item.pricing_basis)}</span>
      </td>
      <td>${valueOrDash(item.notes)}</td>
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
    const items = data.items || [];
    title.textContent = sale.sale_id || saleId;
    subtitle.textContent = `${valueOrDash(sale.buyer_name)} - ${dateOnly(sale.sale_date)}`;

    renderDetailList(summaryList, [
      ["Sale Date", dateOnly(sale.sale_date)],
      ["Buyer", sale.buyer_name],
      ["Destination", sale.destination],
      ["Stream", sale.sale_stream],
      ["Sale Status", sale.sale_status],
      ["Pig Count", sale.pig_count],
      ["Created By", sale.created_by],
      ["Notes", sale.notes],
    ]);

    renderDetailList(paymentList, [
      ["Payment Status", sale.payment_status],
      ["Payment Method", sale.payment_method],
      ["Payment Date", dateOnly(sale.payment_date)],
      ["Gross Total", money(sale.gross_total)],
      ["Deductions", money(sale.deductions_total)],
      ["Net Total", money(sale.net_total)],
      ["Currency", sale.currency],
      ["Updated", dateOnly(sale.updated_at)],
    ]);

    renderItems(items);
    updateExitConfirmPanel(sale, items);
  } catch (error) {
    showMessage(error.message || "Could not load sale detail.");
    itemsBody.innerHTML = '<tr><td colspan="5" class="table-empty">Could not load sale items.</td></tr>';
  }
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

updateBackButtonFromQuery();
loadSaleDetail();
