document.addEventListener("DOMContentLoaded", function () {
  const orderId = window.location.pathname.split("/").pop();

  loadOrderDetail(orderId);
  loadAvailablePigs();
  setupOrderLineForm(orderId);
  setupOrderActions(orderId);
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
    showElement(approveBtn);
    showElement(rejectBtn);
    showElement(addOrderLineForm);
    return;
  }

  if (isApproved) {
    showElement(completeBtn);
    return;
  }

  if (isPendingApproval || isCancelled) {
    return;
  }
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

    applyOrderActionVisibility(order);
    renderDraftLinesSummary(lines);

    summaryContainer.innerHTML = `
      <div class="detail-card">
        <div class="detail-label">Order ID</div>
        <div class="detail-value">${order.order_id || "-"}</div>
      </div>

      <div class="detail-card">
        <div class="detail-label">Customer</div>
        <div class="detail-value">${order.customer_name || "-"}</div>
      </div>

      <div class="detail-card">
        <div class="detail-label">Channel</div>
        <div class="detail-value">${order.customer_channel || "-"}</div>
      </div>

      <div class="detail-card">
        <div class="detail-label">Order Status</div>
        <div class="detail-value">${order.order_status || "-"}</div>
      </div>

      <div class="detail-card">
        <div class="detail-label">Approval Status</div>
        <div class="detail-value">${order.approval_status || "-"}</div>
      </div>

      <div class="detail-card">
        <div class="detail-label">Reserved Pig Count</div>
        <div class="detail-value">${order.reserved_pig_count || 0}</div>
      </div>

      <div class="detail-card">
        <div class="detail-label">Final Total</div>
        <div class="detail-value">${order.final_total || 0}</div>
      </div>

      <div class="detail-card detail-card-wide">
        <div class="detail-label">Notes</div>
        <div class="detail-value">${order.notes || "-"}</div>
      </div>
    `;

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

      return `
        <div class="history-item">
          <div class="history-item-top">
            <div class="history-item-date">${line.tag_number || line.pig_id}</div>
            <div class="history-item-weight">${line.line_status || "-"}</div>
          </div>

          <div class="history-item-grid">
            <div>
              <div class="history-label">Pig ID</div>
              <div class="history-value">${line.pig_id || "-"}</div>
            </div>

            <div>
              <div class="history-label">Category</div>
              <div class="history-value">${line.sale_category || "-"}</div>
            </div>

            <div>
              <div class="history-label">Weight Band</div>
              <div class="history-value">${line.weight_band || "-"}</div>
            </div>

            <div>
              <div class="history-label">Sex</div>
              <div class="history-value">${line.sex || "-"}</div>
            </div>

            <div>
              <div class="history-label">Current Weight</div>
              <div class="history-value">${line.current_weight_kg || "-"}</div>
            </div>

            <div>
              <div class="history-label">Reserved Status</div>
              <div class="history-value">${line.reserved_status || "-"}</div>
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
            <button type="button" ${canEdit ? "" : "disabled"} onclick="updateOrderLine('${line.order_line_id}')">Edit</button>
            <button type="button" ${canDelete ? "" : "disabled"} onclick="deleteOrderLine('${line.order_line_id}')">Delete</button>
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
      await runOrderAction(`/api/orders/${orderId}/approve`, actionMessage, orderId, "Order approved successfully.");
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