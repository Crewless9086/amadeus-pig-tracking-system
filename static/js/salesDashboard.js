document.addEventListener("DOMContentLoaded", function () {
    loadSalesDashboard();
});

async function loadSalesDashboard() {
    const messageBox = document.getElementById("sales_dashboard_message");
    const totalsGrid = document.getElementById("sales_totals_grid");
    const summaryList = document.getElementById("sales_summary_list");

    try {
        const response = await fetch("/api/pig-weights/sales-dashboard");
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error("Failed to load sales dashboard.");
        }

        const totals = data.totals || [];
        const summary = data.summary || [];

        if (totals.length === 0) {
            totalsGrid.innerHTML = `
                <div class="empty-state">
                  <div>No sales totals available.</div>
                </div>
            `;
        } else {
            totalsGrid.innerHTML = totals.map(item => {
                return `
                    <div class="dashboard-action-card">
                      <span class="detail-label">${item.sale_category}</span>
                      <span class="detail-value">${item.qty_available}</span>
                      <span class="pig-list-meta">Male: ${item.male_qty} | Female: ${item.female_qty} | Castrated: ${item.castrated_male_qty}</span>
                      <span class="pig-list-submeta">${item.price_range || "-"} · ${item.status || "-"}</span>
                    </div>
                `;
            }).join("");
        }

        if (summary.length === 0) {
            summaryList.innerHTML = `
                <div class="empty-state">
                  <div>No weight band summary available.</div>
                </div>
            `;
        } else {
            summaryList.innerHTML = summary.map(item => {
                const statusClass =
                    item.status === "Available" ? "good-text" :
                    item.status === "Low Stock" ? "neutral-text" :
                    "bad-text";

                return `
                    <div class="history-item">
                      <div class="history-item-top">
                        <div class="history-item-date">${item.sale_category}</div>
                        <div class="history-item-weight ${statusClass}">${item.status || "-"}</div>
                      </div>

                      <div class="history-item-grid">
                        <div>
                          <div class="history-label">Weight Band</div>
                          <div class="history-value">${item.weight_band || "-"}</div>
                        </div>
                        <div>
                          <div class="history-label">Qty Available</div>
                          <div class="history-value">${item.qty_available}</div>
                        </div>
                        <div>
                          <div class="history-label">Male</div>
                          <div class="history-value">${item.male_qty}</div>
                        </div>
                        <div>
                          <div class="history-label">Female</div>
                          <div class="history-value">${item.female_qty}</div>
                        </div>
                        <div>
                          <div class="history-label">Castrated Male</div>
                          <div class="history-value">${item.castrated_male_qty}</div>
                        </div>
                        <div>
                          <div class="history-label">Price Range</div>
                          <div class="history-value">${item.price_range || "-"}</div>
                        </div>
                      </div>
                    </div>
                `;
            }).join("");
        }

    } catch (error) {
        console.error("Sales dashboard error:", error);

        messageBox.classList.remove("hidden", "message-success", "message-error");
        messageBox.classList.add("message-error");
        messageBox.textContent = "Something went wrong while loading the sales dashboard.";

        totalsGrid.innerHTML = "";
        summaryList.innerHTML = "";
    }
}