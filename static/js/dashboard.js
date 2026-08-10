const dashboardState = { attention: new Map(), priorities: new Map(), loaded: 0 };

const byId = (id) => document.getElementById(id);
const setText = (id, value) => { const el = byId(id); if (el) el.textContent = value ?? "--"; };
const number = (value, suffix = "") => Number.isFinite(Number(value)) ? `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}` : "--";
const money = (value) => Number.isFinite(Number(value)) ? `R${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "--";
const label = (value, fallback = "--") => value ? String(value).replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) : fallback;
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; };

async function fetchJson(url, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal, headers: { Accept: "application/json" } });
    const data = await response.json();
    if (!response.ok || data.success === false) throw new Error(data.message || data.status || `HTTP ${response.status}`);
    return data;
  } finally { clearTimeout(timer); }
}

function finish(panelId, ok = true) {
  const panel = byId(panelId);
  if (!panel) return;
  panel.classList.remove("is-loading");
  panel.classList.toggle("is-unavailable", !ok);
}

function weatherSymbol(current) {
  const rain = Number(current?.rain_rate_mm_h || 0);
  if (rain > 0) return "☂";
  const temperature = Number(current?.temperature_c);
  return Number.isFinite(temperature) && temperature >= 26 ? "☀" : "◌";
}

function addAttention(key, title, detail, href, priority = 20) {
  dashboardState.attention.set(key, { title, detail, href, priority });
  renderAttention();
}

function removeAttention(key) { dashboardState.attention.delete(key); renderAttention(); }
function addPriority(key, text) { dashboardState.priorities.set(key, text); renderPriorities(); }
function removePriority(key) { dashboardState.priorities.delete(key); renderPriorities(); }

function renderAttention() {
  const items = [...dashboardState.attention.values()].sort((a,b) => a.priority - b.priority).slice(0, 3);
  setText("status_attention", items.length ? `${items.length} item${items.length === 1 ? "" : "s"}` : dashboardState.loaded ? "Clear" : "Checking");
  setText("attention_state", items.length ? "Act on the important work first" : dashboardState.loaded ? "No urgent item found" : "Checking the farm");
  const list = byId("attention_list");
  if (!list) return;
  list.innerHTML = items.length ? items.map(item => `<a class="attention-item" href="${item.href}"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.detail)}</small></a>`).join("") : `<div class="attention-placeholder">${dashboardState.loaded ? "No urgent item is supported by the available farm evidence." : "Current priorities will appear independently as each farm source responds."}</div>`;
}

function renderPriorities() {
  const items = [...dashboardState.priorities.values()].slice(0, 3);
  byId("manager_priorities").innerHTML = items.length ? items.map(item => `<li>${escapeHtml(item)}</li>`).join("") : `<li>No supported priority has loaded yet.</li>`;
}

function escapeHtml(value) { return String(value ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;"); }

async function loadWeather() {
  try {
    const data = await fetchJson("/api/telemetry/weather/current");
    const current = data.current || {};
    const summary = data.summary || {};
    const icon = weatherSymbol(current);
    setText("weather_symbol", icon); setText("status_weather_icon", icon);
    setText("weather_temperature", `${number(current.temperature_c)} °C`);
    setText("weather_headline", summary.headline || "Current local conditions available.");
    setText("weather_rain", number(current.rain_today_mm, " mm"));
    setText("weather_age", Number.isFinite(Number(data.source?.data_age_minutes)) ? `${number(data.source.data_age_minutes)} min old` : "Live station");
    setText("status_weather", Number(current.rain_rate_mm_h) > 0 ? `Rain ${number(current.rain_rate_mm_h, " mm/h")}` : `${number(current.temperature_c)} °C · Dry`);
    if (Number(current.rain_rate_mm_h) > 0) addPriority("weather", "Observed rain is active; ROOTLINE should keep irrigation on Hold.");
    else removePriority("weather");
    finish("weather_panel");
  } catch (_) { setText("weather_headline", "Weather is temporarily unavailable."); setText("weather_age", "Unavailable"); setText("status_weather", "Unavailable"); finish("weather_panel", false); }
}

async function loadForecast() {
  try {
    const data = await fetchJson("/api/telemetry/weather/forecast?days=3");
    const next = (data.days || [])[0];
    setText("weather_next", next ? `${number(next.rain_sum_mm, " mm")} rain` : "No forecast");
  } catch (_) { setText("weather_next", "Unavailable"); }
}

async function loadPower() {
  try {
    const data = await fetchJson("/api/telemetry/power/current");
    const current = data.current || {};
    setText("power_battery", number(current.battery_soc_pct, "%"));
    setText("power_solar", number(Number(current.solar_power_w) / 1000, " kW"));
    setText("power_load", number(Number(current.load_power_w) / 1000, " kW"));
    setText("power_headline", data.summary?.headline || "Current electrical state available.");
    setText("power_age", Number.isFinite(Number(data.source?.data_age_minutes)) ? `${number(data.source.data_age_minutes)} min old` : "Current");
    setText("status_power", `${number(current.battery_soc_pct, "%")} battery`);
    finish("power_panel");
  } catch (_) { setText("power_headline", "Power is temporarily unavailable."); setText("power_age", "Unavailable"); setText("status_power", "Unavailable"); finish("power_panel", false); }
}

async function loadIrrigation() {
  try {
    const data = await fetchJson(`/api/telemetry/irrigation/status?date=${today()}`);
    const current = data.current || {}; const day = data.today || {};
    const status = label(current.status, "No active run");
    setText("irrigation_status", status);
    setText("irrigation_note", (data.operator_summary?.notes || [])[0] || "Current irrigation position available.");
    setText("irrigation_source", label(data.source?.source, "Canonical"));
    setText("irrigation_current_zone", current.zone_name || current.zone_id || "None");
    setText("irrigation_next_zone", day.next_zone_name || day.next_zone_id || "Reassess");
    setText("status_irrigation", current.zone_name ? `${current.zone_name} · ${status}` : status);
    if (["needs data", "recovery required"].includes(status.toLowerCase())) addAttention("irrigation", "Irrigation needs evidence", data.operator_summary?.notes?.[0] || status, "/irrigation", 10);
    else removeAttention("irrigation");
    finish("irrigation_panel");
  } catch (_) { setText("irrigation_note", "Irrigation is temporarily unavailable."); setText("irrigation_source", "Unavailable"); setText("status_irrigation", "Unavailable"); finish("irrigation_panel", false); }
}

function litterAttentionHref(item) {
  const id = encodeURIComponent(item.litter_id || "");
  if (item.action_type === "review_purpose") return `/purpose-review?litter_id=${id}`;
  if (item.action_type === "record_post_wean_weight") return `/bulk-weights?return_to=${encodeURIComponent(`/purpose-review?litter_id=${item.litter_id || ""}`)}&return_label=${encodeURIComponent("Back to Purpose Review")}`;
  return `/litter/${id}`;
}

async function loadFarm() {
  try {
    const data = await fetchJson("/api/pig-weights/dashboard");
    const summary = data.summary || {};
    setText("herd_total", number(summary.on_farm_pigs)); setText("herd_sows", number(summary.sows)); setText("herd_piglets", number(summary.piglets)); setText("herd_boars", number(summary.boars));
    const outcomes = [summary.lifecycle_sold_this_month, summary.lifecycle_dead_this_month, summary.lifecycle_removed_this_month].reduce((sum, value) => sum + (Number(value) || 0), 0);
    setText("herd_outcomes", number(outcomes)); finish("herd_panel");
    const litters = data.litter_attention?.items || [];
    setText("breeding_attention", number(litters.length)); setText("breeding_headline", litters.length ? `${litters.length} litter or breeding item${litters.length === 1 ? "" : "s"} need review.` : "No litter reminder is currently due."); finish("breeding_panel");
    if (litters.length) {
      const first = litters[0];
      addAttention("litter", `${first.litter_id || "Litter"} needs attention`, first.reason || "Review current litter work", litterAttentionHref(first), 5);
      addPriority("litter", `${first.litter_id || "A litter"}: ${first.reason || "review current work"}.`);
    } else { removeAttention("litter"); removePriority("litter"); }
    const sales = summary.sales_metrics || data.sales_metrics || {};
    setText("sales_recent_value", money(sales.recent_sales_value));
  } catch (_) { setText("breeding_headline", "Herd evidence is temporarily unavailable."); finish("herd_panel", false); finish("breeding_panel", false); }
}

async function loadOrders() {
  try {
    const data = await fetchJson(`/api/reports/daily-summary?date=${today()}`);
    const counts = data.counts || {}; const items = data.sections?.orders_needing_attention || [];
    const needing = Number(counts.orders_needing_attention || items.length || 0);
    setText("orders_attention", number(needing)); setText("orders_pending", number(counts.pending_approval || 0));
    setText("orders_headline", needing ? `${needing} order${needing === 1 ? "" : "s"} need a decision.` : "No order currently needs attention.");
    if (needing) { const first = items[0] || {}; addAttention("orders", "Sales decision needed", first.customer_name ? `${first.customer_name} · ${(first.reasons || []).join(", ") || "Review order"}` : `${needing} order review`, first.order_id ? `/orders/${encodeURIComponent(first.order_id)}` : "/orders", 8); addPriority("orders", `${needing} sales order${needing === 1 ? "" : "s"} need review.`); }
    else { removeAttention("orders"); removePriority("orders"); }
    finish("orders_panel");
  } catch (_) { setText("orders_headline", "Sales evidence is temporarily unavailable."); finish("orders_panel", false); }
}

function start(job) { job().finally(() => { dashboardState.loaded += 1; renderAttention(); setText("dashboard_timestamp", `Updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · sections refresh independently`); }); }

renderAttention(); renderPriorities();
[loadWeather, loadForecast, loadPower, loadIrrigation, loadFarm, loadOrders].forEach(start);
