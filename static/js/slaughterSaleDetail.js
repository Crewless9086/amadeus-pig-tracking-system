const saleId = window.SLAUGHTER_SALE_ID || "";
const title = document.getElementById("sale_detail_title");
const subtitle = document.getElementById("sale_detail_subtitle");
const messageBox = document.getElementById("sale_detail_message");
const backButton = document.getElementById("sale_detail_back");
const summaryList = document.getElementById("sale_detail_summary");
const paymentList = document.getElementById("sale_detail_payment");
const itemsCount = document.getElementById("sale_items_count");
const itemsBody = document.getElementById("sale_items_body");

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

function renderDetailList(element, rows) {
  element.innerHTML = rows.map(([label, value]) => `
    <div>
      <dt>${label}</dt>
      <dd>${valueOrDash(value)}</dd>
    </div>
  `).join("");
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
  } catch (error) {
    showMessage(error.message || "Could not load sale detail.");
    itemsBody.innerHTML = '<tr><td colspan="5" class="table-empty">Could not load sale items.</td></tr>';
  }
}

backButton.addEventListener("click", () => {
  if (document.referrer && document.referrer !== window.location.href) {
    window.history.back();
    return;
  }
  if (window.location.pathname.startsWith("/sales/transactions/")) {
    window.location.href = "/sales-dashboard";
    return;
  }
  window.location.href = "/sales/slaughter";
});

loadSaleDetail();
