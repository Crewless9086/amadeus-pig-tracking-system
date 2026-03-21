document.addEventListener("DOMContentLoaded", function () {
    const orderDateInput = document.getElementById("order_date");
    if (orderDateInput && !orderDateInput.value) {
        orderDateInput.value = new Date().toISOString().split("T")[0];
    }

    setupAddOrderForm();
});

function setupAddOrderForm() {
    const form = document.getElementById("addOrderForm");
    const messageBox = document.getElementById("add_order_message");

    if (!form) return;

    form.addEventListener("submit", async function (e) {
        e.preventDefault();

        const formData = new FormData(form);

        const payload = {
            order_date: formData.get("order_date") || "",
            customer_name: formData.get("customer_name") || "",
            customer_phone: formData.get("customer_phone") || "",
            customer_channel: formData.get("customer_channel") || "",
            customer_language: formData.get("customer_language") || "",
            order_source: formData.get("order_source") || "",
            requested_category: formData.get("requested_category") || "",
            requested_weight_range: formData.get("requested_weight_range") || "",
            requested_sex: formData.get("requested_sex") || "",
            requested_quantity: formData.get("requested_quantity") || "",
            quoted_total: formData.get("quoted_total") || "",
            notes: formData.get("notes") || "",
            created_by: formData.get("created_by") || "App"
        };

        try {
            const response = await fetch("/api/master/orders", {
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
                messageBox.textContent = "Order created successfully. Redirecting...";
                setTimeout(() => {
                    window.location.href = `/orders/${result.order_id}`;
                }, 700);
            } else {
                messageBox.classList.add("message-error");
                messageBox.textContent = (result.errors || ["Failed to create order."]).join(" ");
            }
        } catch (error) {
            console.error("Create order error:", error);
            messageBox.classList.remove("hidden", "message-success", "message-error");
            messageBox.classList.add("message-error");
            messageBox.textContent = "Failed to create order.";
        }
    });
}