document.addEventListener("DOMContentLoaded", function () {
    loadOrders();
});

async function loadOrders() {
    const messageBox = document.getElementById("orders_message");
    const listContainer = document.getElementById("orders_list");

    try {
        const response = await fetch("/api/orders");
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error("Failed to load orders.");
        }

        const orders = data.orders || [];

        if (orders.length === 0) {
            listContainer.innerHTML = `
                <div class="empty-state">
                  <div>No orders yet.</div>
                  <div>Create the first draft order to begin.</div>
                </div>
            `;
            return;
        }

        listContainer.innerHTML = orders.map(order => {
            return `
                <a href="/orders/${order.order_id}" class="pig-list-card">
                  <div class="pig-list-top">
                    <div class="pig-list-tag">${order.order_id}</div>
                    <div class="pig-list-action">Open Order →</div>
                  </div>
                  <div class="pig-list-meta">${order.customer_name || "-"} · ${order.customer_channel || "-"} · ${order.order_date || "-"}</div>
                  <div class="pig-list-submeta">
                    Status: ${order.order_status || "-"} |
                    Approval: ${order.approval_status || "-"} |
                    Active lines: ${order.active_line_count || 0} |
                    Cancelled: ${order.cancelled_line_count || 0} |
                    Active Total: ${formatMoney(order.active_line_total || 0)}
                  </div>
                </a>
            `;
        }).join("");

    } catch (error) {
        console.error("Orders load error:", error);
        messageBox.classList.remove("hidden", "message-success", "message-error");
        messageBox.classList.add("message-error");
        messageBox.textContent = "Something went wrong while loading orders.";
        listContainer.innerHTML = "";
    }
}

function formatMoney(value) {
    const amount = Number(value || 0);
    if (Number.isNaN(amount)) return "R0.00";
    return `R${amount.toLocaleString("en-ZA", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    })}`;
}
