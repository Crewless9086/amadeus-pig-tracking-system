(function () {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const set = (id, value) => { const node = byId(id); if (node) node.textContent = value; };
  const number = (value, suffix = "") => Number.isFinite(Number(value))
    ? `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}`
    : "--";
  const label = (value, fallback) => value
    ? String(value).replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
    : fallback;
  const today = () => {
    const value = new Date();
    return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
  };

  async function json(url, timeoutMs = 25000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, { signal: controller.signal, headers: { Accept: "application/json" } });
      const data = await response.json();
      if (!response.ok || data.success === false) throw new Error(data.message || data.status || `HTTP ${response.status}`);
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  async function weather() {
    try {
      const data = await json("/api/telemetry/weather/current");
      const current = data.current || {};
      const raining = Number(current.rain_rate_mm_h || 0) > 0;
      set("oom_live_weather", raining ? `Rain ${number(current.rain_rate_mm_h, " mm/h")}` : `${number(current.temperature_c, " °C")} · Dry`);
      set("oom_live_weather_detail", `${number(current.rain_today_mm, " mm today")} · ${number(current.humidity_pct, "% RH")}`);
    } catch (_) {
      set("oom_live_weather", "Unavailable");
      set("oom_live_weather_detail", "Open weather for detail");
    }
  }

  async function power() {
    try {
      const data = await json("/api/telemetry/power/current");
      const current = data.current || {};
      set("oom_live_power", `${number(current.battery_soc_pct, "%")} battery`);
      set("oom_live_power_detail", `${number(Number(current.solar_power_w) / 1000, " kW solar")} · ${number(Number(current.load_power_w) / 1000, " kW load")}`);
    } catch (_) {
      set("oom_live_power", "Unavailable");
      set("oom_live_power_detail", "Open power for detail");
    }
  }

  async function irrigation() {
    try {
      const data = await json(`/api/telemetry/irrigation/status?date=${today()}`, 35000);
      const current = data.current || {};
      const plan = (data.today || {}).plan || [];
      const b = plan.find((item) => item.zone_id === "B12345");
      const c = plan.find((item) => item.zone_id === "C12345");
      set("oom_live_irrigation", label(current.status, "No active run"));
      set("oom_live_irrigation_detail", `B ${label(b && b.status, "--")} · C ${label(c && c.status, "--")}`);
    } catch (_) {
      set("oom_live_irrigation", "Unavailable");
      set("oom_live_irrigation_detail", "Open ROOTLINE for detail");
    }
  }

  async function herd() {
    try {
      const data = await json("/api/pig-weights/dashboard", 40000);
      const items = (data.litter_attention || {}).items || [];
      const summary = data.summary || {};
      set("oom_live_attention", items.length ? `${items.length} litter item${items.length === 1 ? "" : "s"}` : "No litter alert");
      set("oom_live_attention_detail", `${number(summary.on_farm_pigs)} pigs on farm`);
    } catch (_) {
      set("oom_live_attention", "Unavailable");
      set("oom_live_attention_detail", "Open herd for detail");
    }
  }

  [weather, power, irrigation, herd].forEach((load) => load());
  window.setInterval(() => [weather, power, irrigation, herd].forEach((load) => load()), 5 * 60 * 1000);
}());
