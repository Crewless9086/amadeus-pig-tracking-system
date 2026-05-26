const dashboardMessage = document.getElementById("dashboard_message");
const dashboardTimestamp = document.getElementById("dashboard_timestamp");

const state = {
  weatherCurrent: null,
  weatherToday: null,
  forecast: null,
  powerCurrent: null,
  irrigation: null,
  rollup: null,
  farm: null,
  orders: null,
};

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const element = byId(id);
  if (element) {
    element.textContent = value ?? "--";
  }
}

function showDashboardMessage(message, type = "error") {
  dashboardMessage.classList.remove("hidden", "message-success", "message-error");
  dashboardMessage.classList.add(type === "success" ? "message-success" : "message-error");
  dashboardMessage.textContent = message;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function numberOrDash(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "--";
  const number = Number(value);
  if (!Number.isFinite(number)) return escapeHtml(value);
  return `${number.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
}

function displayLabel(value, fallback = "--") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value)
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, char => char.toUpperCase());
}

function kw(value) {
  if (value === null || value === undefined || value === "") return "--";
  return `${(Number(value) / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} kW`;
}

function pct(value) {
  return numberOrDash(value, "%");
}

function mm(value) {
  return numberOrDash(value, " mm");
}

function kmh(value) {
  return numberOrDash(value, " km/h");
}

function minutesAge(value) {
  const minutes = Number(value);
  if (!Number.isFinite(minutes)) return "No age";
  if (minutes < 1) return "Now";
  if (minutes === 1) return "1 min";
  return `${minutes} min`;
}

function localISODate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function todayISO() {
  return localISODate(new Date());
}

function yesterdayISO() {
  const date = new Date();
  date.setDate(date.getDate() - 1);
  return localISODate(date);
}

function formatDateLabel(value) {
  if (!value) return "--";
  const date = new Date(`${value}T00:00:00`);
  return date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

async function fetchJson(url) {
  const response = await fetch(url);
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error(`Expected JSON from ${url}, got HTTP ${response.status}. Restart the local Flask server if this is a local review.`);
  }
  const data = await response.json();
  if (!response.ok || data.success === false) {
    const message = data.message || data.errors?.[0] || `Request failed: ${url}`;
    throw new Error(message);
  }
  return data;
}

function renderError(panelId, message) {
  const panel = byId(panelId);
  if (!panel) return;
  panel.classList.add("ops-panel-warning");
  const warning = document.createElement("p");
  warning.className = "ops-error-text";
  warning.textContent = message;
  panel.appendChild(warning);
}

function renderWeather() {
  const current = state.weatherCurrent || {};
  const weather = current.current || {};
  const source = current.source || {};
  const summary = current.summary || {};

  setText("weather_temperature", `${numberOrDash(weather.temperature_c)} C`);
  setText("weather_headline", summary.headline || "Current weather loaded.");
  setText("weather_age", minutesAge(source.data_age_minutes));
  setText("weather_humidity", pct(weather.humidity_pct));
  setText("weather_wind", `${kmh(weather.wind_speed_kmh)} / gust ${kmh(weather.wind_gust_kmh)}`);
  setText("weather_rain", mm(weather.rain_today_mm));
  setText("weather_pressure", `${numberOrDash(weather.pressure_hpa)} hPa`);
  setText("alert_weather", summary.status === "ok" ? "Clear" : (summary.status || "Review"));

  const today = state.weatherToday || {};
  setText("today_temperature", `${numberOrDash(today.temperature?.min_c)} - ${numberOrDash(today.temperature?.max_c)} C`);
  setText("today_rain", mm(today.rain?.total_mm));
  setText("today_wind", kmh(today.wind?.max_speed_kmh));
  setText("today_coverage", pct(today.window?.coverage_pct));

  const forecast = state.forecast?.days || [];
  const forecastStrip = byId("forecast_strip");
  forecastStrip.innerHTML = forecast.length
    ? forecast.map(day => `
      <div class="forecast-day">
        <span>${escapeHtml(formatDateLabel(day.forecast_date))}</span>
        <strong>${numberOrDash(day.temp_min_c)} - ${numberOrDash(day.temp_max_c)} C</strong>
        <small>${mm(day.rain_sum_mm)} rain</small>
      </div>
    `).join("")
    : `<div class="ops-empty-inline">No forecast loaded.</div>`;
}

function renderPower() {
  const current = state.powerCurrent || {};
  const power = current.current || {};
  const source = current.source || {};
  const summary = current.summary || {};
  const rollup = state.rollup?.stored_rollups?.power || {};

  setText("power_battery", pct(power.battery_soc_pct));
  setText("power_headline", summary.headline || "Power data loaded.");
  setText("power_age", minutesAge(source.data_age_minutes));
  setText("power_solar", kw(power.solar_power_w));
  setText("power_load", kw(power.load_power_w));
  setText("power_grid", power.grid_state ? displayLabel(power.grid_state) : kw(power.grid_power_w));
  setText("power_generator", power.generator_state ? displayLabel(power.generator_state) : kw(power.generator_power_w));
  setText("alert_power", summary.status === "ok" ? "Normal" : (summary.status || "Review"));

  setText("rollup_load_kwh", numberOrDash(rollup.estimated_load_kwh, " kWh"));
  setText("rollup_solar_kwh", numberOrDash(rollup.estimated_solar_kwh, " kWh"));
  setText("rollup_value", rollup.estimated_value_zar === undefined ? "--" : `R${numberOrDash(rollup.estimated_value_zar)}`);
  setText("rollup_power_quality", displayLabel(rollup.quality));
}

function renderIrrigation() {
  const irrigation = state.irrigation || {};
  const current = irrigation.current || {};
  const today = irrigation.today || {};
  const notes = irrigation.operator_summary?.notes || [];

  setText("irrigation_status", current.status || "--");
  setText("irrigation_note", notes[0] || "Read-only irrigation status loaded.");
  setText("irrigation_source", displayLabel(irrigation.source?.source, "source"));
  setText("irrigation_current_zone", current.zone_name || current.zone_id || "--");
  setText("irrigation_next_zone", today.next_zone_name || today.next_zone_id || "--");
  setText("irrigation_planned", numberOrDash(today.planned_count));
  setText("irrigation_completed", numberOrDash(today.done_count));
  setText("alert_irrigation", displayLabel(current.status, "Review"));

  const plan = today.plan || [];
  byId("irrigation_plan_list").innerHTML = plan.length
    ? plan.slice(0, 4).map(item => `
      <div class="ops-list-row">
        <strong>${escapeHtml(item.zone_name || item.zone_id || "Zone")}</strong>
        <span>${escapeHtml(displayLabel(item.status))} - ${numberOrDash(item.planned_minutes, " min")}</span>
      </div>
    `).join("")
    : `<div class="ops-empty-inline">No plan rows for today.</div>`;
}

function renderFarmSummary() {
  const summary = state.farm?.summary || {};
  setText("herd_total", numberOrDash(summary.on_farm_pigs));
  setText("herd_sows", numberOrDash(summary.sows));
  setText("herd_boars", numberOrDash(summary.boars));
  setText("herd_weaners", numberOrDash(summary.weaners));
  setText("herd_finishers", numberOrDash(summary.finishers));
  setText("sales_available", numberOrDash(summary.available_for_sale_pigs));
  setText("sales_reserved", numberOrDash(summary.reserved_pigs));
  setText("sales_livestock", numberOrDash(summary.livestock_sold_this_month ?? 0));
  setText("sales_slaughter", numberOrDash(summary.slaughter_sold_this_month ?? 0));
  setText("sales_meat", numberOrDash(summary.meat_sold_this_month ?? 0));

  const litterItems = state.farm?.litter_attention?.items || [];
  byId("litter_attention_list").innerHTML = litterItems.length
    ? litterItems.slice(0, 4).map(item => `
      <a class="ops-list-row ops-list-link" href="/litter/${encodeURIComponent(item.litter_id)}">
        <strong>${escapeHtml(item.litter_id)}</strong>
        <span>${escapeHtml(item.reason || "Review")} - Sow ${escapeHtml(item.sow_tag_number || "--")}</span>
      </a>
    `).join("")
    : `<div class="ops-empty-inline">No litter reminders.</div>`;
}

function renderOrders() {
  const counts = state.orders?.counts || {};
  const items = state.orders?.sections?.orders_needing_attention || [];

  setText("orders_attention", numberOrDash(counts.orders_needing_attention || 0));
  setText("orders_pending", numberOrDash(counts.pending_approval || 0));
  setText("orders_approved", numberOrDash(counts.approved || 0));
  setText("orders_drafts", numberOrDash(counts.new_drafts || 0));
  setText("alert_orders", (counts.orders_needing_attention || 0) > 0 ? `${counts.orders_needing_attention} review` : "Clear");

  byId("orders_attention_list").innerHTML = items.length
    ? items.slice(0, 4).map(item => `
      <a class="ops-list-row ops-list-link" href="/orders/${encodeURIComponent(item.order_id)}">
        <strong>${escapeHtml(item.order_id)}</strong>
        <span>${escapeHtml(item.customer_name || "Customer")} - ${escapeHtml((item.reasons || []).join(", ") || "Review")}</span>
      </a>
    `).join("")
    : `<div class="ops-empty-inline">No order attention items.</div>`;
}

function renderTimestamp() {
  dashboardTimestamp.textContent = `Updated ${new Date().toLocaleString()}`;
}

async function loadDashboard() {
  const yesterday = yesterdayISO();
  const today = todayISO();
  const requests = [
    ["weatherCurrent", "/api/telemetry/weather/current", "weather_panel"],
    ["weatherToday", `/api/telemetry/weather/today?date=${today}`, "weather_panel"],
    ["forecast", "/api/telemetry/weather/forecast?days=3", "weather_panel"],
    ["powerCurrent", "/api/telemetry/power/current", "power_panel"],
    ["irrigation", `/api/telemetry/irrigation/status?date=${today}`, "irrigation_panel"],
    ["rollup", `/api/telemetry/rollups/daily?date=${yesterday}`, "power_panel"],
    ["farm", "/api/pig-weights/dashboard", "herd_panel"],
    ["orders", `/api/reports/daily-summary?date=${today}`, "orders_panel"],
  ];

  const results = await Promise.allSettled(requests.map(([key, url]) => fetchJson(url).then(data => [key, data])));
  let failures = 0;

  results.forEach((result, index) => {
    const [key, , panelId] = requests[index];
    if (result.status === "fulfilled") {
      state[result.value[0]] = result.value[1];
    } else {
      failures += 1;
      renderError(panelId, result.reason.message);
      state[key] = null;
    }
  });

  renderTimestamp();
  renderWeather();
  renderPower();
  renderIrrigation();
  renderFarmSummary();
  renderOrders();

  if (failures) {
    showDashboardMessage(`${failures} dashboard section(s) could not load.`, "error");
  }
}

loadDashboard().catch(() => {
  showDashboardMessage("Something went wrong while loading the dashboard.", "error");
});
