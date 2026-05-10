document.addEventListener("DOMContentLoaded", function () {
  const orderId = window.location.pathname.split("/").pop();

  loadOrderDetail(orderId);
  loadAvailablePigs();
  setupEditOrderForm(orderId);
  setupOrderLineForm(orderId);
  setupOrderActions(orderId);
  setupDocumentActions(orderId);
});

function showElement(element) {
  if (!element) return;
  element.classList.remove("hidden");
  element.style.display = "";
}

function hideElement(element) {
  if (!element) return;
  element.classList.add("hidden");
  element.style.display = "none";
}

function applyOrderActionVisibility(order) {
  const reserveBtn = document.getElementById("reserve_order_btn");
  const releaseBtn = document.getElementById("release_order_btn");
  const sendForApprovalBtn = document.getElementById("send_for_approval_btn");
  const approveBtn = document.getElementById("approve_order_btn");
  const rejectBtn = document.getElementById("reject_order_btn");
  const completeBtn = document.getElementById("complete_order_btn");
  const addOrderLineForm = document.getElementById("addOrderLineForm");

  const orderStatus = (order.order_status || "").trim();
  const approvalStatus = (order.approval_status || "").trim();

  const isDraft = orderStatus === "Draft";
  const isPendingApproval = orderStatus === "Pending_Approval";
  const isApproved = orderStatus === "Approved" || approvalStatus === "Approved";
  const isCancelled = orderStatus === "Cancelled" || approvalStatus === "Rejected";

  // Default hide everything first
  hideElement(reserveBtn);
  hideElement(releaseBtn);
  hideElement(sendForApprovalBtn);
  hideElement(approveBtn);
  hideElement(rejectBtn);
  hideElement(completeBtn);
  hideElement(addOrderLineForm);

  if (isDraft) {
    showElement(reserveBtn);
    showElement(releaseBtn);
    showElement(sendForApprovalBtn);
    showElement(addOrderLineForm);
    return;
  }

  if (isPendingApproval) {
    showElement(approveBtn);
    showElement(rejectBtn);
    showElement(releaseBtn);
    return;
  }

  if (isApproved) {
    showElement(releaseBtn);
    showElement(completeBtn);
    return;
  }

  if (isCancelled) {
    return;
  }
}

function populateOrderHeaderForm(order) {
  setFieldValue("requested_quantity", order.requested_quantity || "");
  setFieldValue("requested_category", order.requested_category || "");
  setFieldValue("requested_weight_range", order.requested_weight_range || "");
  setFieldValue("requested_sex", order.requested_sex || "");
  setFieldValue("collection_location", order.collection_location || "");
  setFieldValue("payment_method", order.payment_method || "");
  setFieldValue("order_notes", order.notes || "");

  const paymentMethod = document.getElementById("payment_method");
  if (paymentMethod) {
    paymentMethod.disabled = (order.order_status || "").trim() !== "Draft";
  }

  const saveBtn = document.getElementById("save_order_btn");
  if (saveBtn) {
    const terminal = ["Cancelled", "Completed"].includes((order.order_status || "").trim());
    saveBtn.disabled = terminal;
  }
}

function setFieldValue(id, value) {
  const element = document.getElementById(id);
  if (element) element.value = value === null || value === undefined ? "" : value;
}

function applyDocumentActionVisibility(order, documents) {
  const quoteBtn = document.getElementById("generate_quote_btn");
  const invoiceBtn = document.getElementById("generate_invoice_btn");
  const conversationInput = document.getElementById("document_conversation_id");
  const orderStatus = (order.order_status || "").trim();
  const terminal = orderStatus === "Cancelled" || orderStatus === "Completed";
  const hasQuote = documents.some(doc => doc.document_type === "Quote" && doc.document_status !== "Voided");
  const invoiceEligible = orderStatus === "Approved" || orderStatus === "Completed";

  if (conversationInput && !conversationInput.value) {
    conversationInput.value = order.conversation_id || "";
  }

  if (quoteBtn) quoteBtn.disabled = terminal;
  if (invoiceBtn) invoiceBtn.disabled = !invoiceEligible || !hasQuote;
}

async function loadOrderDetail(orderId) {
  const messageBox = document.getElementById("order_detail_message");
  const summaryContainer = document.getElementById("order_summary");
  const linesContainer = document.getElementById("order_lines_list");

  try {
    const response = await fetch(`/api/orders/${orderId}`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error("Failed to load order detail.");
    }

    const order = data.order;
    const lines = data.lines || [];
    const documents = data.documents || [];

    applyOrderActionVisibility(order);
    populateOrderHeaderForm(order);
    applyDocumentActionVisibility(order, documents);
    renderDraftLinesSummary(lines);
    renderOrderDocuments(documents);
    renderOrderSummary(order, lines, documents);

    if (lines.length === 0) {
      linesContainer.innerHTML = `
        <div class="empty-state">
          <div>No order lines yet.</div>
          <div>Add the first draft line above.</div>
        </div>
      `;
      return;
    }

    linesContainer.innerHTML = lines.map(line => {
      const canDelete = line.line_status === "Draft" && line.reserved_status !== "Reserved";
      const canEdit = line.line_status === "Draft";
      const editPrice = line.unit_price || "";
      const editNotes = line.notes || "";
      const cardId = `line_details_${escapeDomId(line.order_line_id)}`;
      const price = formatMoney(line.unit_price);

      return `
        <div class="history-item compact-record">
          <button type="button" class="corner-toggle" onclick="toggleCompactCard('${cardId}', this)">Expand</button>

          <div class="compact-record-main">
            <div>
              <div class="history-item-date">${escapeHtml(line.tag_number || line.pig_id || "-")}</div>
              <div class="compact-subtitle">${escapeHtml(line.sale_category || "-")} | ${escapeHtml(line.weight_band || "-")} | ${escapeHtml(line.sex || "-")}</div>
            </div>
            <div class="compact-record-status">
              <span class="status-pill">${escapeHtml(line.line_status || "-")}</span>
              <span>${price}</span>
            </div>
          </div>

          <div class="compact-meta-row">
            <span>Pig ${escapeHtml(line.pig_id || "-")}</span>
            <span>${escapeHtml(line.current_weight_kg || "-")} kg</span>
            <span>${escapeHtml(line.reserved_status || "-")}</span>
          </div>

          <div id="${cardId}" class="compact-details hidden">
            <div class="history-item-grid">
            <div>
              <div class="history-label">Pig ID</div>
              <div class="history-value">${escapeHtml(line.pig_id || "-")}</div>
            </div>

            <div>
              <div class="history-label">Category</div>
              <div class="history-value">${escapeHtml(line.sale_category || "-")}</div>
            </div>

            <div>
              <div class="history-label">Weight Band</div>
              <div class="history-value">${escapeHtml(line.weight_band || "-")}</div>
            </div>

            <div>
              <div class="history-label">Sex</div>
              <div class="history-value">${escapeHtml(line.sex || "-")}</div>
            </div>

            <div>
              <div class="history-label">Current Weight</div>
              <div class="history-value">${escapeHtml(line.current_weight_kg || "-")}</div>
            </div>

            <div>
              <div class="history-label">Reserved Status</div>
              <div class="history-value">${escapeHtml(line.reserved_status || "-")}</div>
            </div>

            <div>
              <div class="history-label">Created</div>
              <div class="history-value">${escapeHtml(line.created_at || "-")}</div>
            </div>

            <div>
              <div class="history-label">Updated</div>
              <div class="history-value">${escapeHtml(line.updated_at || "-")}</div>
            </div>
          </div>

          <div class="form-grid" style="margin-top: 14px;">
            <div class="form-group">
              <label>Unit Price</label>
              <input
                type="number"
                step="0.01"
                id="unit_price_${line.order_line_id}"
                value="${editPrice}"
                ${canEdit ? "" : "disabled"}
              >
            </div>

            <div class="form-group">
              <label>Notes</label>
              <input
                type="text"
                id="notes_${line.order_line_id}"
                value="${escapeHtml(editNotes)}"
                ${canEdit ? "" : "disabled"}
              >
            </div>
          </div>

          <div class="form-actions compact-actions" style="margin-top: 12px;">
            <button type="button" ${canEdit ? "" : "disabled"} onclick="updateOrderLine('${escapeJsValue(line.order_line_id)}')">Edit</button>
            <button type="button" ${canDelete ? "" : "disabled"} onclick="deleteOrderLine('${escapeJsValue(line.order_line_id)}')">Delete</button>
          </div>
          </div>
        </div>
      `;
    }).join("");

  } catch (error) {
    console.error("Order detail error:", error);
    messageBox.classList.remove("hidden", "message-success", "message-error");
    messageBox.classList.add("message-error");
    messageBox.textContent = "Something went wrong while loading the order.";
    summaryContainer.innerHTML = "";
    linesContainer.innerHTML = "";
  }
}

function renderDraftLinesSummary(lines) {
  const container = document.getElementById("draft_lines_summary");
  if (!container) return;

  const active = lines.filter(l => l.line_status !== "Cancelled");

  if (active.length === 0) {
    container.innerHTML = "";
    return;
  }

  const statusCounts = {};
  active.forEach(l => {
    const s = l.line_status || "Unknown";
    statusCounts[s] = (statusCounts[s] || 0) + 1;
  });

  const categoryCounts = {};
  active.forEach(l => {
    const c = l.sale_category || "Uncategorised";
    categoryCounts[c] = (categoryCounts[c] || 0) + 1;
  });

  const statusCards = Object.entries(statusCounts).map(([status, count]) => `
    <div class="detail-card">
      <div class="detail-label">${status}</div>
      <div class="detail-value">${count}</div>
    </div>
  `).join("");

  const categoryCards = Object.entries(categoryCounts).map(([cat, count]) => `
    <div class="detail-card">
      <div class="detail-label">${cat}</div>
      <div class="detail-value">${count}</div>
    </div>
  `).join("");

  container.innerHTML = `
    <div class="page-header" style="margin-top: 28px; margin-bottom: 16px;">
      <div>
        <h2 style="margin: 0 0 8px 0;">Lines Summary</h2>
        <p style="margin: 0; color: var(--text-soft);">${active.length} line${active.length !== 1 ? "s" : ""} on this order.</p>
      </div>
    </div>
    <div class="detail-grid" style="margin-bottom: 14px;">
      ${statusCards}
    </div>
    <div class="detail-grid">
      ${categoryCards}
    </div>
  `;
}

function renderOrderDocuments(documents) {
  const container = document.getElementById("order_documents_list");
  if (!container) return;

  if (!documents || documents.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div>No documents generated yet.</div>
        <div>Generate a quote first, then generate an invoice after approval.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = documents.map(doc => {
    const canSend = doc.document_status !== "Voided" && doc.google_drive_file_id;
    const cardId = `document_details_${escapeDomId(doc.document_id)}`;
    const sentMeta = doc.sent_at
      ? `Sent ${escapeHtml(doc.sent_at)}${doc.sent_by ? ` by ${escapeHtml(doc.sent_by)}` : ""}`
      : "Not sent";
    const driveLink = doc.google_drive_url
      ? `<a class="secondary-link" href="${escapeHtml(doc.google_drive_url)}" target="_blank" rel="noopener">Open PDF</a>`
      : "";

    return `
      <div class="history-item document-item compact-record">
        <button type="button" class="corner-toggle" onclick="toggleCompactCard('${cardId}', this)">Expand</button>

        <div class="compact-record-main">
          <div>
            <div class="history-item-date">${escapeHtml(doc.document_ref || doc.document_id || "-")}</div>
            <div class="compact-subtitle">${escapeHtml(doc.document_type || "-")} | ${formatMoney(doc.total)} | ${escapeHtml(doc.payment_method || "-")}</div>
          </div>
          <div class="compact-record-status">
            <span class="status-pill">${escapeHtml(doc.document_status || "-")}</span>
            <span>${doc.sent_at ? "Sent" : "Not sent"}</span>
          </div>
        </div>

        <div class="compact-meta-row">
          <span>${escapeHtml(doc.file_name || "-")}</span>
        </div>

        <div id="${cardId}" class="compact-details hidden">
          <div class="history-item-grid">
          <div>
            <div class="history-label">Total</div>
            <div class="history-value">${formatMoney(doc.total)}</div>
          </div>
          <div>
            <div class="history-label">Payment</div>
            <div class="history-value">${escapeHtml(doc.payment_method || "-")}</div>
          </div>
          <div>
            <div class="history-label">Created</div>
            <div class="history-value">${escapeHtml(doc.created_at || "-")}</div>
          </div>
          <div>
            <div class="history-label">Delivery</div>
            <div class="history-value">${sentMeta}</div>
          </div>
          <div>
            <div class="history-label">Payment Ref</div>
            <div class="history-value">${escapeHtml(doc.payment_ref || "-")}</div>
          </div>
          <div>
            <div class="history-label">Version</div>
            <div class="history-value">${escapeHtml(doc.version || "-")}</div>
          </div>
        </div>

        ${doc.notes ? `<div class="history-notes"><div class="history-label">Notes</div><div>${escapeHtml(doc.notes)}</div></div>` : ""}

        <div class="form-actions compact-actions document-card-actions">
          ${driveLink}
          <button type="button" ${canSend ? "" : "disabled"} onclick="sendDocument('${escapeJsValue(doc.document_id)}', '${escapeJsValue(doc.document_ref)}')">Send</button>
        </div>
        </div>
      </div>
    `;
  }).join("");
}

function setupEditOrderForm(orderId) {
  const form = document.getElementById("editOrderForm");
  const messageBox = document.getElementById("edit_order_message");
  if (!form) return;

  form.addEventListener("submit", async function (event) {
    event.preventDefault();

    const payload = {
      requested_quantity: document.getElementById("requested_quantity")?.value || "",
      requested_category: document.getElementById("requested_category")?.value || "",
      requested_weight_range: document.getElementById("requested_weight_range")?.value || "",
      requested_sex: document.getElementById("requested_sex")?.value || "",
      collection_location: document.getElementById("collection_location")?.value || "",
      notes: document.getElementById("order_notes")?.value || "",
      changed_by: "App"
    };

    const paymentMethod = document.getElementById("payment_method");
    if (paymentMethod && !paymentMethod.disabled) {
      payload.payment_method = paymentMethod.value || "";
    }

    try {
      const response = await fetch(`/api/master/orders/${orderId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const result = await response.json();

      messageBox.classList.remove("hidden", "message-success", "message-error");
      if (response.ok && result.success) {
        messageBox.classList.add("message-success");
        messageBox.textContent = "Order header saved.";
        await loadOrderDetail(orderId);
      } else {
        messageBox.classList.add("message-error");
        messageBox.textContent = (result.errors || [result.message || "Failed to save order header."]).join(" ");
      }
    } catch (error) {
      console.error("Edit order error:", error);
      messageBox.classList.remove("hidden", "message-success", "message-error");
      messageBox.classList.add("message-error");
      messageBox.textContent = "Failed to save order header.";
    }
  });
}

function toggleCompactCard(targetId, button) {
  const target = document.getElementById(targetId);
  if (!target) return;

  const isHidden = target.classList.contains("hidden");
  target.classList.toggle("hidden", !isHidden);
  if (button) {
    button.textContent = isHidden ? "Collapse" : "Expand";
  }
}

async function loadAvailablePigs() {
  const pigSelect = document.getElementById("pig_id");
  if (!pigSelect) return;

  try {
    const response = await fetch("/api/orders/available-pigs");
    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error("Failed to load available pigs.");
    }

    pigSelect.innerHTML = `<option value="">Select pig</option>`;

    (data.pigs || []).forEach(pig => {
      const option = document.createElement("option");
      option.value = pig.pig_id;
      option.textContent = `${pig.tag_number} · ${pig.sale_category} · ${pig.weight_band} · ${pig.current_weight_kg || "-"}kg`;
      pigSelect.appendChild(option);
    });

  } catch (error) {
    console.error("Available pigs error:", error);
  }
}

function setupOrderLineForm(orderId) {
  const form = document.getElementById("addOrderLineForm");
  const messageBox = document.getElementById("add_order_line_message");

  if (!form) return;

  form.addEventListener("submit", async function (e) {
    e.preventDefault();

    const formData = new FormData(form);

    const payload = {
      order_id: orderId,
      pig_id: formData.get("pig_id") || "",
      unit_price: formData.get("unit_price") || "",
      notes: formData.get("line_notes") || ""
    };

    try {
      const response = await fetch("/api/master/order-lines", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });

      const result = await response.json();

      messageBox.classList.remove("hidden", "message-success", "message-error");

      if (response.ok && result.success) {
        messageBox.classList.add("message-success");
        messageBox.textContent = "Order line added successfully.";

        form.reset();

        await loadOrderDetail(orderId);
        await loadAvailablePigs();
      } else {
        messageBox.classList.add("message-error");
        messageBox.textContent = (result.errors || ["Failed to add order line."]).join(" ");
      }

    } catch (error) {
      console.error("Add order line error:", error);
      messageBox.classList.remove("hidden", "message-success", "message-error");
      messageBox.classList.add("message-error");
      messageBox.textContent = "Failed to add order line.";
    }
  });
}

function setupOrderActions(orderId) {
  const reserveBtn = document.getElementById("reserve_order_btn");
  const releaseBtn = document.getElementById("release_order_btn");
  const sendForApprovalBtn = document.getElementById("send_for_approval_btn");
  const approveBtn = document.getElementById("approve_order_btn");
  const rejectBtn = document.getElementById("reject_order_btn");
  const completeBtn = document.getElementById("complete_order_btn");
  const actionMessage = document.getElementById("order_action_message");

  if (reserveBtn) {
    reserveBtn.addEventListener("click", async function () {
      await runOrderAction(
        `/api/orders/${orderId}/reserve`,
        actionMessage,
        orderId,
        "Order lines reserved successfully.",
        "reserve",
      );
    });
  }

  if (releaseBtn) {
    releaseBtn.addEventListener("click", async function () {
      await runOrderAction(
        `/api/orders/${orderId}/release`,
        actionMessage,
        orderId,
        "Order reservations released successfully.",
        "release",
      );
    });
  }

  if (sendForApprovalBtn) {
    sendForApprovalBtn.addEventListener("click", async function () {
      await runOrderAction(`/api/orders/${orderId}/send-for-approval`, actionMessage, orderId, "Order sent for approval.");
    });
  }

  if (approveBtn) {
    approveBtn.addEventListener("click", async function () {
      await runOrderAction(`/api/orders/${orderId}/approve`, actionMessage, orderId, "Order approved successfully.", "approve");
    });
  }

  if (rejectBtn) {
    rejectBtn.addEventListener("click", async function () {
      await runOrderAction(`/api/orders/${orderId}/reject`, actionMessage, orderId, "Order rejected successfully.");
    });
  }

  if (completeBtn) {
    completeBtn.addEventListener("click", async function () {
      const confirmed = window.confirm(
        "Complete this order?\n\nThis will mark all pigs as Sold, update their records, and cannot be undone."
      );
      if (!confirmed) return;
      await runOrderAction(`/api/orders/${orderId}/complete`, actionMessage, orderId, "Order completed successfully. All pigs marked as sold.");
    });
  }
}

function renderOrderSummary(order, lines, documents) {
  const summaryContainer = document.getElementById("order_summary");
  if (!summaryContainer) return;

  const activeLines = lines.filter(line => line.line_status !== "Cancelled");
  const reservedLines = activeLines.filter(line => line.reserved_status === "Reserved" || line.line_status === "Reserved");
  const sentDocs = documents.filter(doc => doc.document_status === "Sent");
  const latestQuote = documents.find(doc => doc.document_type === "Quote" && doc.document_status !== "Voided");
  const latestInvoice = documents.find(doc => doc.document_type === "Invoice" && doc.document_status !== "Voided");

  summaryContainer.className = "order-summary-panel";
  summaryContainer.innerHTML = `
    <div class="summary-hero">
      <div>
        <div class="summary-kicker">${escapeHtml(order.order_id || "-")}</div>
        <div class="summary-title">${escapeHtml(order.customer_name || "Unknown customer")}</div>
        <div class="summary-subtitle">${escapeHtml(order.customer_channel || "-")} | ${escapeHtml(order.customer_phone || "-")}</div>
      </div>
      <div class="summary-status-stack">
        <span class="status-pill">${escapeHtml(order.order_status || "-")}</span>
        <span class="status-pill status-pill-muted">${escapeHtml(order.approval_status || "-")}</span>
      </div>
    </div>

    <div class="summary-metric-grid">
      <div class="summary-metric">
        <span>Total</span>
        <strong>${formatMoney(order.final_total || latestInvoice?.total || latestQuote?.total || 0)}</strong>
      </div>
      <div class="summary-metric">
        <span>Lines</span>
        <strong>${activeLines.length}</strong>
      </div>
      <div class="summary-metric">
        <span>Reserved</span>
        <strong>${reservedLines.length}</strong>
      </div>
      <div class="summary-metric">
        <span>Documents</span>
        <strong>${documents.length}</strong>
      </div>
    </div>

    <div class="summary-detail-strip">
      <span>Payment: <strong>${escapeHtml(order.payment_method || "-")}</strong></span>
      <span>Collection: <strong>${escapeHtml(order.collection_location || "-")}</strong></span>
      <span>Request: <strong>${escapeHtml(formatRequestSummary(order))}</strong></span>
      <span>Sent docs: <strong>${sentDocs.length}</strong></span>
    </div>

    ${order.notes ? `<div class="summary-notes">${escapeHtml(order.notes)}</div>` : ""}
  `;
}

function formatRequestSummary(order) {
  const parts = [
    order.requested_quantity ? `${order.requested_quantity}x` : "",
    order.requested_category || "",
    order.requested_weight_range || "",
    order.requested_sex || ""
  ].filter(Boolean);
  return parts.length ? parts.join(" ") : "-";
}

function setupDocumentActions(orderId) {
  const quoteBtn = document.getElementById("generate_quote_btn");
  const invoiceBtn = document.getElementById("generate_invoice_btn");

  if (quoteBtn) {
    quoteBtn.addEventListener("click", async function () {
      await runDocumentGeneration(`/api/orders/${orderId}/quote`, orderId, "Quote generated.");
    });
  }

  if (invoiceBtn) {
    invoiceBtn.addEventListener("click", async function () {
      await runDocumentGeneration(`/api/orders/${orderId}/invoice`, orderId, "Invoice generated.");
    });
  }
}

async function runDocumentGeneration(url, orderId, successText) {
  const messageBox = document.getElementById("document_action_message");

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ created_by: "App" })
    });
    const result = await response.json();

    messageBox.classList.remove("hidden", "message-success", "message-error");
    if (response.ok && result.success) {
      messageBox.classList.add("message-success");
      messageBox.textContent = `${successText} ${result.document_ref || ""}`.trim();
      await loadOrderDetail(orderId);
    } else {
      messageBox.classList.add("message-error");
      messageBox.textContent = (result.errors || [result.message || "Document generation failed."]).join(" ");
    }
  } catch (error) {
    console.error("Document generation error:", error);
    messageBox.classList.remove("hidden", "message-success", "message-error");
    messageBox.classList.add("message-error");
    messageBox.textContent = "Document generation failed.";
  }
}

async function sendDocument(documentId, documentRef) {
  const orderId = window.location.pathname.split("/").pop();
  const messageBox = document.getElementById("document_action_message");
  const conversationInput = document.getElementById("document_conversation_id");
  const conversationId = (conversationInput?.value || "").trim();

  if (!conversationId) {
    messageBox.classList.remove("hidden", "message-success", "message-error");
    messageBox.classList.add("message-error");
    messageBox.textContent = "Conversation ID is required before sending a document.";
    return;
  }

  const confirmed = window.confirm(
    `Send ${documentRef || documentId} to Chatwoot conversation ${conversationId}?`
  );
  if (!confirmed) return;

  try {
    const response = await fetch(`/api/order-documents/${documentId}/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: conversationId,
        sent_by: "App"
      })
    });
    const result = await response.json();

    messageBox.classList.remove("hidden", "message-success", "message-error");
    if (response.ok && result.success) {
      messageBox.classList.add("message-success");
      messageBox.textContent = "Document sent successfully.";
      await loadOrderDetail(orderId);
    } else {
      messageBox.classList.add("message-error");
      messageBox.textContent = (result.errors || [result.error || result.message || "Document send failed."]).join(" ");
    }
  } catch (error) {
    console.error("Document send error:", error);
    messageBox.classList.remove("hidden", "message-success", "message-error");
    messageBox.classList.add("message-error");
    messageBox.textContent = "Document send failed.";
  }
}

async function runOrderAction(url, messageBox, orderId, successText, reserveReleaseKind) {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        changed_by: "App"
      })
    });

    const result = await response.json();

    messageBox.classList.remove("hidden", "message-success", "message-error");

    if (response.ok && result.success) {
      messageBox.classList.add("message-success");

      let message =
        reserveReleaseKind === "reserve" || reserveReleaseKind === "release"
          ? (result.message || successText || "").trim() || successText
          : successText;

      if (reserveReleaseKind === "reserve" || reserveReleaseKind === "release") {
        const cc = result.changed_count;
        if (typeof cc === "number") {
          if (cc === 0) {
            message += /\.\s*$/.test(message)
              ? " No ORDER_LINES rows were updated (nothing to write)."
              : ". No ORDER_LINES rows were updated (nothing to write).";
          } else {
            message += /\.\s*$/.test(message)
              ? ` ${cc} order line sheet row${cc !== 1 ? "s were" : " was"} updated.`
              : `. ${cc} order line sheet row${cc !== 1 ? "s were" : " was"} updated.`;
          }
        }
      }

      if (result.warning) {
        message += ` ${result.warning}`;
      }

      if (reserveReleaseKind === "approve" && result.reserve_warning && result.reserve_warning !== result.warning) {
        message += ` ${result.reserve_warning}`;
      }

      messageBox.textContent = message;

      await loadOrderDetail(orderId);
      await loadAvailablePigs();
    } else {
      messageBox.classList.add("message-error");
      messageBox.textContent = (result.errors || [result.message || "Order action failed."]).join(" ");
    }
  } catch (error) {
    console.error("Order action error:", error);
    messageBox.classList.remove("hidden", "message-success", "message-error");
    messageBox.classList.add("message-error");
    messageBox.textContent = "Order action failed.";
  }
}

async function updateOrderLine(orderLineId) {
  const orderId = window.location.pathname.split("/").pop();
  const messageBox = document.getElementById("order_action_message");

  const unitPrice = document.getElementById(`unit_price_${orderLineId}`)?.value || "";
  const notes = document.getElementById(`notes_${orderLineId}`)?.value || "";

  try {
    const response = await fetch(`/api/master/order-lines/${orderLineId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        unit_price: unitPrice,
        notes: notes
      })
    });

    const result = await response.json();

    messageBox.classList.remove("hidden", "message-success", "message-error");

    if (response.ok && result.success) {
      messageBox.classList.add("message-success");
      messageBox.textContent = "Order line updated successfully.";
      await loadOrderDetail(orderId);
    } else {
      messageBox.classList.add("message-error");
      messageBox.textContent = (result.errors || ["Failed to update order line."]).join(" ");
    }
  } catch (error) {
    console.error("Update order line error:", error);
    messageBox.classList.remove("hidden", "message-success", "message-error");
    messageBox.classList.add("message-error");
    messageBox.textContent = "Failed to update order line.";
  }
}

async function deleteOrderLine(orderLineId) {
  const orderId = window.location.pathname.split("/").pop();
  const messageBox = document.getElementById("order_action_message");

  const confirmed = window.confirm("Are you sure you want to remove this draft line?");
  if (!confirmed) return;

  try {
    const response = await fetch(`/api/master/order-lines/${orderLineId}`, {
      method: "DELETE"
    });

    const result = await response.json();

    messageBox.classList.remove("hidden", "message-success", "message-error");

    if (response.ok && result.success) {
      messageBox.classList.add("message-success");
      messageBox.textContent = "Order line removed successfully.";
      await loadOrderDetail(orderId);
      await loadAvailablePigs();
    } else {
      messageBox.classList.add("message-error");
      messageBox.textContent = (result.errors || ["Failed to remove order line."]).join(" ");
    }
  } catch (error) {
    console.error("Delete order line error:", error);
    messageBox.classList.remove("hidden", "message-success", "message-error");
    messageBox.classList.add("message-error");
    messageBox.textContent = "Failed to remove order line.";
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeJsValue(value) {
  return String(value || "")
    .replaceAll("\\", "\\\\")
    .replaceAll("'", "\\'")
    .replaceAll("\n", " ");
}

function escapeDomId(value) {
  return String(value || "item").replace(/[^a-zA-Z0-9_-]/g, "_");
}

function formatMoney(value) {
  const amount = Number(value || 0);
  if (Number.isNaN(amount)) return "R0.00";
  return `R${amount.toLocaleString("en-ZA", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`;
}
