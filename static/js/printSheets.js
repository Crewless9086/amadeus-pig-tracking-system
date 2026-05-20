const sheetDateInput = document.getElementById("sheet_date");
const penFilterSelect = document.getElementById("pen_filter");
const clearPensButton = document.getElementById("clear_pens_button");
const printSheetButton = document.getElementById("print_sheet_button");
const messageBox = document.getElementById("print_sheets_message");
const printSheetBody = document.getElementById("print_sheet_body");
const printSheetMeta = document.getElementById("print_sheet_meta");

let allPigs = [];
let allPens = [];

function todayIso() {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

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

function tagSortKey(pig) {
  const raw = String(pig.tag_number || pig.pig_id || "").trim();
  const numeric = /^\d+$/.test(raw) ? raw.padStart(8, "0") : raw.toLowerCase();
  return `${numeric}|${String(pig.tag_number || pig.pig_id || "").toLowerCase()}|${pig.pig_id || ""}`;
}

function penLabelForPig(pig) {
  return pig.current_pen_name || pig.current_pen_id || "-";
}

function penSortKey(pig) {
  return String(penLabelForPig(pig)).toLowerCase();
}

function formatKg(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(2)} kg`;
}

function setMessage(message, type = "error") {
  messageBox.classList.remove("hidden", "message-success", "message-error");
  messageBox.classList.add(type === "success" ? "message-success" : "message-error");
  messageBox.textContent = message;
}

function clearMessage() {
  messageBox.classList.add("hidden");
  messageBox.textContent = "";
  messageBox.classList.remove("message-success", "message-error");
}

function selectedPenIds() {
  return Array.from(penFilterSelect.selectedOptions).map((option) => option.value).filter(Boolean);
}

function populatePens() {
  penFilterSelect.innerHTML = "";
  allPens.forEach((pen) => {
    const option = document.createElement("option");
    option.value = pen.pen_id || "";
    option.textContent = pen.pen_name ? `${pen.pen_name} (${pen.pen_id})` : (pen.pen_id || "");
    penFilterSelect.appendChild(option);
  });
}

function filteredRows() {
  const pens = selectedPenIds();
  const rows = pens.length
    ? allPigs.filter((pig) => pens.includes(pig.current_pen_id || ""))
    : [...allPigs];

  return rows.sort((a, b) => {
    const penCompare = penSortKey(a).localeCompare(penSortKey(b));
    if (penCompare !== 0) return penCompare;
    return tagSortKey(a).localeCompare(tagSortKey(b));
  });
}

function renderSheet() {
  clearMessage();
  const rows = filteredRows();
  const penCount = selectedPenIds().length;
  const penText = penCount ? `${penCount} selected pen${penCount === 1 ? "" : "s"}` : "All active pigs";
  printSheetMeta.textContent = `Date: ${sheetDateInput.value || "-"} | ${penText} | ${rows.length} pig${rows.length === 1 ? "" : "s"}`;

  if (!rows.length) {
    printSheetBody.innerHTML = `<tr><td colspan="7" class="table-empty">No active pigs found for this selection.</td></tr>`;
    return;
  }

  printSheetBody.innerHTML = rows.map((pig) => `
    <tr>
      <td>${escapeHtml(formatTagNumber(pig.tag_number || pig.pig_id || "-"))}</td>
      <td>${escapeHtml(pig.last_weight_date || "-")}</td>
      <td>${escapeHtml(formatKg(pig.current_weight_kg))}</td>
      <td class="blank-write-cell"></td>
      <td>${escapeHtml(penLabelForPig(pig))}</td>
      <td class="blank-write-cell"></td>
      <td class="blank-notes-cell"></td>
    </tr>
  `).join("");
}

async function loadData() {
  try {
    const [pigsResponse, pensResponse] = await Promise.all([
      fetch("/api/pig-weights/pigs"),
      fetch("/api/pig-weights/pens"),
    ]);
    const pigsData = await pigsResponse.json();
    const pensData = await pensResponse.json();

    if (!pigsResponse.ok || !pensResponse.ok) {
      throw new Error("Failed to load printable sheet data.");
    }

    allPigs = pigsData.pigs || [];
    allPens = pensData.pens || [];
    populatePens();
    renderSheet();
  } catch (error) {
    console.error("Printable sheet error:", error);
    setMessage(error.message || "Something went wrong while loading printable sheets.");
    printSheetBody.innerHTML = `<tr><td colspan="7" class="table-empty">Could not load printable sheet rows.</td></tr>`;
  }
}

penFilterSelect.addEventListener("change", renderSheet);
sheetDateInput.addEventListener("change", renderSheet);

clearPensButton.addEventListener("click", () => {
  Array.from(penFilterSelect.options).forEach((option) => {
    option.selected = false;
  });
  renderSheet();
});

printSheetButton.addEventListener("click", () => {
  window.print();
});

(async function initPage() {
  sheetDateInput.value = todayIso();
  await loadData();
})();
