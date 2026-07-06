(function () {
  const state = {
    live: [],
    meat: [],
  };

  const els = {
    message: document.getElementById("sam_pricing_message"),
    liveStatus: document.getElementById("live_pricing_status"),
    meatStatus: document.getElementById("meat_pricing_status"),
    liveEntries: document.getElementById("live_price_entries"),
    meatEntries: document.getElementById("meat_price_entries"),
    liveForm: document.getElementById("live_price_form"),
    meatForm: document.getElementById("meat_price_form"),
  };

  const safe = (value) => String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

  const money = (value) => {
    const number = Number(value);
    return Number.isFinite(number) ? `R${number.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "";
  };

  const setMessage = (text, type = "") => {
    if (!els.message) return;
    els.message.textContent = text || "";
    els.message.className = `message-box ${text ? "" : "hidden"} ${type}`.trim();
  };

  const fetchJson = async (url, options) => {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
      const error = new Error(payload.status || payload.message || `HTTP ${response.status}`);
      error.payload = payload;
      throw error;
    }
    return payload;
  };

  const renderLive = () => {
    els.liveStatus.textContent = `${state.live.length} live-stock price rows. Latest effective row wins for SAM.`;
    els.liveEntries.innerHTML = table(
      ["Category", "Weight Band", "Price", "Effective", "Reason", "By"],
      state.live.map((entry) => [
        entry.sale_category,
        entry.weight_band,
        money(entry.unit_price),
        dateText(entry.effective_from),
        entry.change_reason,
        entry.created_by,
      ])
    );
  };

  const renderMeat = () => {
    els.meatStatus.textContent = `${state.meat.length} meat price rows. Latest effective entry is used by quote estimates.`;
    els.meatEntries.innerHTML = table(
      ["Product", "Cut Set", "Price", "Unit", "Effective", "By"],
      state.meat.map((entry) => [
        entry.product_type,
        entry.cut_set,
        money(entry.price_amount),
        entry.price_unit,
        dateText(entry.effective_from),
        entry.created_by,
      ])
    );
  };

  const table = (headers, rows) => {
    if (!rows.length) {
      return '<div class="empty-state">No price rows loaded.</div>';
    }
    return `
      <table class="pricing-table">
        <thead><tr>${headers.map((header) => `<th>${safe(header)}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows.map((row) => `<tr>${row.map((cell) => `<td>${safe(cell)}</td>`).join("")}</tr>`).join("")}
        </tbody>
      </table>
    `;
  };

  const dateText = (value) => String(value || "").slice(0, 10);

  const loadLive = async () => {
    const payload = await fetchJson("/api/sales/live-stock-pricing?limit=200");
    state.live = Array.isArray(payload.price_entries) ? payload.price_entries : [];
    renderLive();
  };

  const loadMeat = async () => {
    const payload = await fetchJson("/api/sales/meat-pricing?limit=100");
    state.meat = Array.isArray(payload.price_entries) ? payload.price_entries : [];
    renderMeat();
  };

  const saveLive = async (event) => {
    event.preventDefault();
    setMessage("");
    const effectiveDate = document.getElementById("live_effective_from").value;
    try {
      await fetchJson("/api/sales/live-stock-pricing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sale_category: document.getElementById("live_sale_category").value,
          weight_band: document.getElementById("live_weight_band").value,
          unit_price: document.getElementById("live_unit_price").value,
          effective_from: effectiveDate ? `${effectiveDate}T00:00:00+02:00` : "",
          change_reason: document.getElementById("live_change_reason").value,
          created_by: "Farm App",
        }),
      });
      document.getElementById("live_unit_price").value = "";
      document.getElementById("live_change_reason").value = "";
      await loadLive();
      setMessage("Live-stock price entry added. SAM will use it from the effective date.", "success");
    } catch (error) {
      setMessage(`Could not add live-stock price: ${error.message}`, "error");
    }
  };

  const saveMeat = async (event) => {
    event.preventDefault();
    setMessage("");
    try {
      await fetchJson("/api/sales/meat-pricing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_type: document.getElementById("meat_product_type").value,
          cut_set: document.getElementById("meat_cut_set").value,
          price_amount: document.getElementById("meat_price_amount").value,
          price_unit: document.getElementById("meat_price_unit").value,
          created_by: "Farm App",
        }),
      });
      document.getElementById("meat_price_amount").value = "";
      await loadMeat();
      setMessage("Meat price entry added. SAM Meat estimates will use the latest active entry.", "success");
    } catch (error) {
      setMessage(`Could not add meat price: ${error.message}`, "error");
    }
  };

  const init = async () => {
    const today = new Date().toISOString().slice(0, 10);
    const liveDate = document.getElementById("live_effective_from");
    if (liveDate) liveDate.value = today;
    els.liveForm.addEventListener("submit", saveLive);
    els.meatForm.addEventListener("submit", saveMeat);
    try {
      await Promise.all([loadLive(), loadMeat()]);
    } catch (error) {
      setMessage(`Could not load pricing: ${error.message}`, "error");
    }
  };

  init();
})();
