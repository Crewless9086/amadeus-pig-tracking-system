document.addEventListener("DOMContentLoaded", function () {
    const orderId = window.location.pathname.split("/").pop();

    loadOrderDetail(orderId);
    loadAvailablePigs();
    setupOrderLineForm(orderId);
});

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
                      <div class="history-label">Unit Price</div>
                      <div class="history-value">${line.unit_price || 0}</div>
                    </div>
                    <div>
                      <div class="history-label">Reserved Status</div>
                      <div class="history-value">${line.reserved_status || "-"}</div>
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