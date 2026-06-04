const detailTitle = document.getElementById("breeding_detail_title");
const detailSubtitle = document.getElementById("breeding_detail_subtitle");
const messageBox = document.getElementById("breeding_detail_message");
const animalValue = document.getElementById("breeding_detail_animal");
const matingsValue = document.getElementById("breeding_detail_matings");
const littersValue = document.getElementById("breeding_detail_litters");
const flagsValue = document.getElementById("breeding_detail_flags");
const qualityList = document.getElementById("breeding_quality_list");
const matingsBody = document.getElementById("breeding_detail_matings_body");
const littersBody = document.getElementById("breeding_detail_litters_body");
const breedingDetailBackLink = document.getElementById("breeding_detail_back_link");

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

function formatNumber(value, decimals = 0, suffix = "") {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(decimals)}${suffix}`;
}

function formatPercent(value) {
  return formatNumber(value, 1, "%");
}

function formatDate(value) {
  return value || "-";
}

function safeInternalReturnPath(value) {
  const path = String(value || "").trim();
  if (!path.startsWith("/") || path.startsWith("//")) {
    return "";
  }
  return path;
}

function updateBackLinkFromQuery() {
  if (!breedingDetailBackLink) return;
  const params = new URLSearchParams(window.location.search);
  const returnTo = safeInternalReturnPath(params.get("return_to"));
  const returnLabel = String(params.get("return_label") || "").trim();
  if (!returnTo) return;
  breedingDetailBackLink.href = returnTo;
  breedingDetailBackLink.textContent = returnLabel || "Back";
}

function litterDetailHref(litterId) {
  const params = new URLSearchParams({
    return_to: window.location.pathname,
    return_label: "Back to Breeding Detail",
  });
  return `/litter/${encodeURIComponent(litterId)}?${params.toString()}`;
}

function animalLabel(pigId, tagNumber) {
  const tag = formatTagNumber(tagNumber || pigId || "-");
  return pigId && pigId !== tagNumber ? `${tag} (${pigId})` : tag;
}

function pairLabel(row) {
  const sow = animalLabel(row.sow_pig_id, row.sow_tag_number);
  const boar = animalLabel(row.boar_pig_id, row.boar_tag_number);
  return `${sow} x ${boar}`;
}

function flagListHtml(flags) {
  if (!flags || !flags.length) {
    return '<span class="quality-flag-muted">Clear</span>';
  }
  return flags.map((flag) => `<span class="quality-flag">${escapeHtml(flag)}</span>`).join("");
}

function setMessage(message) {
  messageBox.classList.remove("hidden", "message-success");
  messageBox.classList.add("message-error");
  messageBox.textContent = message;
}

function renderQuality(dataQuality) {
  const flags = dataQuality?.flags || [];
  if (!flags.length) {
    qualityList.innerHTML = '<span class="quality-flag-muted">No data-quality flags found for this breeding animal.</span>';
    return;
  }
  qualityList.innerHTML = flags.map((flag) => `<span class="quality-flag">${escapeHtml(flag)}</span>`).join("");
}

function renderMatings(rows) {
  if (!rows.length) {
    matingsBody.innerHTML = '<tr><td colspan="7" class="table-empty">No matings found for this animal.</td></tr>';
    return;
  }

  matingsBody.innerHTML = rows.map((row) => {
    const litter = row.linked_litter_id
      ? `<a class="detail-link" href="${litterDetailHref(row.linked_litter_id)}">${escapeHtml(row.linked_litter_id)}</a>`
      : "-";
    return `
      <tr>
        <td>${escapeHtml(formatDate(row.mating_date))}</td>
        <td>${escapeHtml(row.mating_id || "-")}</td>
        <td>${escapeHtml(pairLabel(row))}</td>
        <td>${escapeHtml(row.mating_status || row.outcome || "-")}</td>
        <td>${escapeHtml(row.pregnancy_check_result || "-")}</td>
        <td>${litter}</td>
        <td class="quality-cell">${flagListHtml(row.quality_flags)}</td>
      </tr>
    `;
  }).join("");
}

function renderLitters(rows) {
  if (!rows.length) {
    littersBody.innerHTML = '<tr><td colspan="9" class="table-empty">No litters found for this animal.</td></tr>';
    return;
  }

  littersBody.innerHTML = rows.map((row) => {
    const litter = row.litter_id
      ? `<a class="detail-link" href="${litterDetailHref(row.litter_id)}">${escapeHtml(row.litter_id)}</a>`
      : "-";
    return `
      <tr>
        <td>${escapeHtml(formatDate(row.farrowing_date))}</td>
        <td>${litter}</td>
        <td>${escapeHtml(pairLabel(row))}</td>
        <td>${escapeHtml(formatNumber(row.born_alive))}</td>
        <td>${escapeHtml(formatNumber(row.weaned_count))}</td>
        <td>${escapeHtml(formatPercent(row.survival_pct))}</td>
        <td>${escapeHtml(formatNumber(row.active_pig_count))} / ${escapeHtml(formatNumber(row.exited_pig_count))}</td>
        <td>${escapeHtml(formatNumber(row.average_current_weight_kg, 1, " kg"))}</td>
        <td class="quality-cell">${flagListHtml(row.quality_flags)}</td>
      </tr>
    `;
  }).join("");
}

async function loadBreedingAnimalDetail() {
  const pigId = decodeURIComponent(window.location.pathname.split("/").filter(Boolean).pop() || "");
  if (!pigId) {
    setMessage("Pig ID is missing from the page URL.");
    return;
  }

  try {
    const response = await fetch(`/api/pig-weights/breeding-analytics/${encodeURIComponent(pigId)}`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error((data.errors || []).join(" ") || "Failed to load breeding analytics detail.");
    }

    const animal = data.animal || {};
    const label = animalLabel(animal.pig_id, animal.tag_number);
    detailTitle.textContent = `Breeding Analytics: ${label}`;
    detailSubtitle.textContent = `${data.animal_type || "breeding animal"} record from current matings and litters.`;
    animalValue.textContent = label;
    matingsValue.textContent = String((data.matings || []).length);
    littersValue.textContent = String((data.litters || []).length);
    flagsValue.textContent = String(data.data_quality?.flag_count ?? 0);

    renderQuality(data.data_quality || {});
    renderMatings(data.matings || []);
    renderLitters(data.litters || []);
  } catch (error) {
    console.error("breeding animal detail error:", error);
    setMessage(error.message || "Something went wrong while loading breeding detail.");
    matingsBody.innerHTML = '<tr><td colspan="7" class="table-empty">Could not load matings.</td></tr>';
    littersBody.innerHTML = '<tr><td colspan="9" class="table-empty">Could not load litters.</td></tr>';
  }
}

document.addEventListener("DOMContentLoaded", () => {
  updateBackLinkFromQuery();
  loadBreedingAnimalDetail();
});
