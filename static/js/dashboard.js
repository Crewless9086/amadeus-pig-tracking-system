const dashboardState = { attention: new Map(), priorities: new Map(), loaded: 0 };
const byId = id => document.getElementById(id);
const setText = (id, value) => { const el = byId(id); if (el) el.textContent = value ?? "--"; };
const number = (value, suffix = "") => Number.isFinite(Number(value)) ? `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}` : "--";
const money = value => Number.isFinite(Number(value)) ? `R${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "--";
const label = (value, fallback = "--") => value ? String(value).replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) : fallback;
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; };
const escapeHtml = value => String(value ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");

async function fetchJson(url, timeoutMs = 20000) {
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
function addAttention(key, title, detail, href, priority = 20) { dashboardState.attention.set(key, { title, detail, href, priority }); renderAttention(); }
function removeAttention(key) { dashboardState.attention.delete(key); renderAttention(); }
function addPriority(key, text) { dashboardState.priorities.set(key, text); renderPriorities(); }
function removePriority(key) { dashboardState.priorities.delete(key); renderPriorities(); }
function renderAttention() {
  const items = [...dashboardState.attention.values()].sort((a,b) => a.priority - b.priority).slice(0, 3);
  setText("status_attention", items.length ? `${items.length} item${items.length === 1 ? "" : "s"}` : dashboardState.loaded ? "Clear" : "Checking");
  setText("attention_state", items.length ? "Act on the important work first" : dashboardState.loaded ? "No urgent item found" : "Checking the farm");
  const list = byId("attention_list");
  if (list) list.innerHTML = items.length ? items.map(item => `<a class="attention-item" href="${item.href}"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.detail)}</small></a>`).join("") : `<div class="attention-placeholder">${dashboardState.loaded ? "No urgent item is supported by the available farm evidence." : "Current priorities will appear independently as each farm source responds."}</div>`;
}
function renderPriorities() {
  const items = [...dashboardState.priorities.values()].slice(0, 3);
  byId("manager_priorities").innerHTML = items.length ? items.map(item => `<li>${escapeHtml(item)}</li>`).join("") : "<li>No supported priority has loaded yet.</li>";
}
function weatherSymbol(current) {
  if (Number(current?.rain_rate_mm_h || 0) > 0) return "Rain";
  if (Number(current?.temperature_c) >= 26) return "Sun";
  return "Cloud";
}
function planState(item) {
  if (!item) return "No plan";
  const status = label(item.status, "Hold");
  return item.planned_minutes ? `${status} · ${number(item.planned_minutes, " min")}` : status;
}

async function loadWeather() {
  try {
    const data = await fetchJson("/api/telemetry/weather/current");
    const current = data.current || {};
    const icon = weatherSymbol(current);
    setText("weather_symbol", icon); setText("status_weather_icon", icon);
    setText("weather_temperature", `${number(current.temperature_c)} °C`);
    setText("weather_headline", data.summary?.headline || "Current local conditions available.");
    setText("weather_rain", number(current.rain_today_mm, " mm"));
    setText("weather_humidity", number(current.humidity_pct, "%"));
    setText("weather_wind", number(current.wind_speed_kmh, " km/h"));
    setText("weather_age", Number.isFinite(Number(data.source?.data_age_minutes)) ? `${number(data.source.data_age_minutes)} min old` : "Live station");
    setText("status_weather", Number(current.rain_rate_mm_h) > 0 ? `Rain ${number(current.rain_rate_mm_h, " mm/h")}` : `${number(current.temperature_c)} °C · ${current.rain_today_mm ? number(current.rain_today_mm, " mm today") : "Dry"}`);
    if (data.flags?.irrigation_caution) addPriority("weather", `Weather caution: ${number(current.rain_today_mm, " mm")} rain today and ${number(current.wind_speed_kmh, " km/h")} wind.`); else removePriority("weather");
    finish("weather_panel");
  } catch (_) { setText("weather_headline", "Weather is temporarily unavailable."); setText("weather_age", "Unavailable"); setText("status_weather", "Unavailable"); finish("weather_panel", false); }
}
async function loadForecast() {
  try {
    const data = await fetchJson("/api/telemetry/weather/forecast?days=3");
    const next = (data.days || []).find(day => Number(day.offset_days) === 1) || (data.days || [])[0];
    setText("weather_next", next ? `${number(next.temp_min_c)}-${number(next.temp_max_c)} °C · ${number(next.rain_sum_mm, " mm")}` : "No forecast");
    if (next?.flags?.work_caution) addPriority("forecast", `Tomorrow: ${number(next.rain_sum_mm, " mm")} rain and ${number(next.wind_max_kmh, " km/h")} wind forecast.`); else removePriority("forecast");
  } catch (_) { setText("weather_next", "Unavailable"); }
}
async function loadPower() {
  try {
    const data = await fetchJson("/api/telemetry/power/current");
    const current = data.current || {};
    setText("power_battery", number(current.battery_soc_pct, "%"));
    setText("power_solar", number(Number(current.solar_power_w) / 1000, " kW"));
    setText("power_load", number(Number(current.load_power_w) / 1000, " kW"));
    setText("power_grid", number(Number(current.grid_power_w) / 1000, " kW"));
    setText("power_state", label(current.battery_state, "Unknown"));
    setText("power_headline", (data.summary?.operator_notes || []).join(" ") || data.summary?.headline || "Current electrical state available.");
    setText("power_age", Number.isFinite(Number(data.source?.data_age_minutes)) ? `${number(data.source.data_age_minutes)} min old` : "Current");
    setText("status_power", `${number(current.battery_soc_pct, "%")} · ${number(Number(current.load_power_w) / 1000, " kW load")}`);
    if (data.flags?.low_battery || data.flags?.high_load) addAttention("power", "Power needs attention", data.summary?.headline || "Review power state", "/power", 7); else removeAttention("power");
    finish("power_panel");
  } catch (_) { setText("power_headline", "Power is temporarily unavailable."); setText("power_age", "Unavailable"); setText("status_power", "Unavailable"); finish("power_panel", false); }
}
async function loadIrrigation() {
  try {
    const data = await fetchJson(`/api/telemetry/irrigation/status?date=${today()}`, 30000);
    const current = data.current || {}; const day = data.today || {}; const plan = day.plan || [];
    const status = label(current.status, "No active run");
    const b = plan.find(item => item.zone_id === "B12345"); const c = plan.find(item => item.zone_id === "C12345");
    setText("irrigation_status", status);
    setText("irrigation_source", label(data.source?.source, "Canonical"));
    const bz=(data.zones||[]).find(item=>item.zone_id==="B12345"); const cz=(data.zones||[]).find(item=>item.zone_id==="C12345");
    setText("irrigation_b_status", bz?.operational_state||planState(b)); setText("irrigation_c_status", cz?.operational_state||planState(c));
    setText("irrigation_done", `${number(day.done_count || 0)} · ${number(day.completed_minutes || 0, " min")}`);
    setText("irrigation_held", number((day.skipped_count || 0) + (day.paused_count || 0)));
    const sharedReason = b?.reason && b.reason === c?.reason ? b.reason : [b?.reason, c?.reason].filter(Boolean).join(" · ");
    setText("irrigation_note", sharedReason || (data.operator_summary?.notes || [])[0] || data.operator_summary?.headline || "Current irrigation position available.");
    setText("status_irrigation", current.status === "RUNNING" ? `${current.zone_name || current.zone_id} · Running` : `${status} · ${day.skipped_count || 0} held`);
    if (["needs data", "recovery required"].includes(status.toLowerCase())) addAttention("irrigation", "Irrigation needs evidence", data.operator_summary?.notes?.[0] || status, "/irrigation", 10); else removeAttention("irrigation");
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
    const data = await fetchJson("/api/pig-weights/dashboard", 45000);
    const summary = data.summary || {}; const litters = data.litter_attention?.items || [];
    setText("herd_total", number(summary.on_farm_pigs)); setText("herd_sows", number(summary.sows)); setText("herd_piglets", number(summary.piglets)); setText("herd_boars", number(summary.boars));
    setText("herd_available", number(summary.available_for_sale_pigs)); setText("herd_reserved", number(summary.reserved_pigs));
    setText("breeding_litters", number(litters.length));
    if (litters.length) {
      const first = litters[0];
      addAttention("litter", `${first.litter_id || "Litter"} needs attention`, first.reason || "Review current litter work", litterAttentionHref(first), 5);
      addPriority("litter", `${first.litter_id || "A litter"}: ${first.reason || "review current work"}.`);
    } else { removeAttention("litter"); removePriority("litter"); }
    finish("herd_panel");
  } catch (_) { finish("herd_panel", false); setText("herd_total", "Unavailable"); }
}
async function loadBreeding() {
  try {
    const data = await fetchJson("/api/pig-weights/matings", 30000);
    const open = (data.records || []).filter(item => item.is_open === "Yes");
    const overdue = open.filter(item => item.is_overdue_farrowing === "Yes");
    const due = open.filter(item => { if (!item.expected_farrowing_date) return false; const days = Math.ceil((new Date(`${item.expected_farrowing_date}T12:00:00`) - new Date(`${today()}T12:00:00`)) / 86400000); return days >= 0 && days <= 14; });
    const next = [...due].sort((a,b) => String(a.expected_farrowing_date).localeCompare(String(b.expected_farrowing_date)))[0];
    setText("breeding_open", number(open.length)); setText("breeding_due", number(due.length)); setText("breeding_overdue", number(overdue.length));
    setText("breeding_attention", number(overdue.length + due.length));
    setText("breeding_headline", overdue.length ? `${overdue.length} mating record${overdue.length === 1 ? "" : "s"} show overdue farrowing evidence.` : next ? `${next.sow_tag_number || "Sow"} is next around ${next.expected_farrowing_date}.` : `${open.length} open mating${open.length === 1 ? "" : "s"} under monitoring.`);
    if (overdue.length) addAttention("breeding", "Breeding chronology needs review", `${overdue.map(item => item.sow_tag_number).filter(Boolean).join(", ")} show overdue farrowing evidence.`, "/matings", 6); else removeAttention("breeding");
    if (next) addPriority("breeding", `${next.sow_tag_number || "Sow"}: expected farrowing around ${next.expected_farrowing_date}.`); else removePriority("breeding");
    finish("breeding_panel");
  } catch (_) { setText("breeding_headline", "Breeding chronology is temporarily unavailable."); finish("breeding_panel", false); }
}
async function loadSales() {
  try {
    const data = await fetchJson("/api/pig-weights/sales-dashboard", 40000); const summary = data.summary || {}; const sales = data.sales_metrics || summary.sales_metrics || {};
    setText("sales_recent_value", money(sales.recent_sales_value)); setText("sales_ready", number(sales.live_sale_ready));
  } catch (_) { setText("sales_recent_value", "Unavailable"); setText("sales_ready", "--"); }
}
async function loadOrders() {
  try {
    const data = await fetchJson(`/api/reports/daily-summary?date=${today()}`, 30000);
    const counts = data.counts || {}; const items = data.sections?.orders_needing_attention || []; const needing = Number(counts.orders_needing_attention || items.length || 0);
    setText("orders_attention", number(needing)); setText("orders_pending", number(counts.pending_approval || 0)); setText("orders_completed", number(counts.completed_today || 0));
    setText("orders_headline", needing ? `${needing} order${needing === 1 ? "" : "s"} need a decision.` : `${number(counts.completed_today || 0)} completed today · no order currently needs attention.`);
    if (needing) { const first = items[0] || {}; addAttention("orders", "Sales decision needed", first.customer_name ? `${first.customer_name} · ${(first.reasons || []).join(", ") || "Review order"}` : `${needing} order review`, first.order_id ? `/orders/${encodeURIComponent(first.order_id)}` : "/orders", 8); addPriority("orders", `${needing} sales order${needing === 1 ? "" : "s"} need review.`); } else { removeAttention("orders"); removePriority("orders"); }
    finish("orders_panel");
  } catch (_) { setText("orders_headline", "Sales evidence is temporarily unavailable."); finish("orders_panel", false); }
}
function start(job) { job().finally(() => { dashboardState.loaded += 1; renderAttention(); setText("dashboard_timestamp", `Updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · sections refresh independently`); }); }
renderAttention(); renderPriorities();
[loadWeather, loadForecast, loadPower, loadIrrigation, loadFarm, loadBreeding, loadSales, loadOrders].forEach(start);
