const messageBox = document.getElementById("breeding_analytics_message");
const matingCount = document.getElementById("breeding_mating_count");
const litterCount = document.getElementById("breeding_litter_count");
const animalCount = document.getElementById("breeding_animal_count");
const sowBody = document.getElementById("sow_analytics_body");
const boarBody = document.getElementById("boar_analytics_body");

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatTagNumber(value) {
  const raw = String(value || "").trim();
  return /^\d+$/.test(raw) ? raw.padStart(3, "0") : raw;
}

function formatNumber(value, decimals = 0) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(decimals);
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(1)}%`;
}

function animalLabel(row) {
  const tag = formatTagNumber(row.tag_number || row.pig_id || "-");
  const id = row.pig_id || "";
  return id && id !== row.tag_number ? `${tag} (${id})` : tag;
}

function setMessage(message) {
  messageBox.classList.remove("hidden", "message-success");
  messageBox.classList.add("message-error");
  messageBox.textContent = message;
}

function renderRows(container, rows, animalType) {
  if (!rows.length) {
    container.innerHTML = `<tr><td colspan="9" class="table-empty">No ${animalType} analytics found.</td></tr>`;
    return;
  }

  container.innerHTML = rows.map((row) => `
    <tr>
      <td><a class="detail-link" href="/breeding-analytics/${encodeURIComponent(row.pig_id || "")}">${escapeHtml(animalLabel(row))}</a></td>
      <td>${escapeHtml(row.mating_count ?? 0)}</td>
      <td>${escapeHtml(row.confirmed_pregnant_count ?? 0)}</td>
      <td>${escapeHtml(row.repeat_service_count ?? 0)}</td>
      <td>${escapeHtml(row.farrowed_count ?? 0)}</td>
      <td>${escapeHtml(row.litter_count ?? 0)}</td>
      <td>${escapeHtml(formatNumber(row.average_born_alive, 2))}</td>
      <td>${escapeHtml(formatNumber(row.average_weaned, 2))}</td>
      <td>${escapeHtml(formatPercent(row.survival_pct))}</td>
    </tr>
  `).join("");
}

async function loadBreedingAnalytics() {
  try {
    const response = await fetch("/api/pig-weights/breeding-analytics");
    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error("Failed to load breeding analytics.");
    }

    const summary = data.summary || {};
    matingCount.textContent = String(summary.mating_count ?? 0);
    litterCount.textContent = String(summary.litter_count ?? 0);
    animalCount.textContent = `${summary.sow_count ?? 0} sows / ${summary.boar_count ?? 0} boars`;
    renderRows(sowBody, data.sows || [], "sow");
    renderRows(boarBody, data.boars || [], "boar");
  } catch (error) {
    console.error("breeding analytics error:", error);
    setMessage(error.message || "Something went wrong while loading breeding analytics.");
    sowBody.innerHTML = `<tr><td colspan="9" class="table-empty">Could not load sow analytics.</td></tr>`;
    boarBody.innerHTML = `<tr><td colspan="9" class="table-empty">Could not load boar analytics.</td></tr>`;
  }
}

document.addEventListener("DOMContentLoaded", loadBreedingAnalytics);
