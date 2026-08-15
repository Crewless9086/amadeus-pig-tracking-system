const body = document.getElementById("vjd_rows");
const note = document.getElementById("vjd_note");
const safe = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
const meaningfulTag = (tag, pigId) => {
  const cleanTag = String(tag || "").trim();
  const cleanId = String(pigId || "").trim();
  return cleanTag && cleanTag !== cleanId ? cleanTag : "";
};
const ownerIdentity = (name, tag, pigId) => String(name || "").trim() || meaningfulTag(tag, pigId) || String(pigId || "").trim() || "-";
const dateLabel = row => row.expected_farrowing_date || ((row.expected_farrowing_window_start && row.expected_farrowing_window_end) ? `${row.expected_farrowing_window_start} – ${row.expected_farrowing_window_end}` : "");
const compareExpectedRows = (a, b) =>
  dateLabel(a).localeCompare(dateLabel(b))
  || ownerIdentity(a.sow_name, a.sow_tag_number, a.sow_pig_id).localeCompare(ownerIdentity(b.sow_name, b.sow_tag_number, b.sow_pig_id))
  || String(a.sow_pig_id || "").localeCompare(String(b.sow_pig_id || ""))
  || ownerIdentity(a.boar_name, a.boar_tag_number, a.boar_pig_id).localeCompare(ownerIdentity(b.boar_name, b.boar_tag_number, b.boar_pig_id))
  || String(a.boar_pig_id || "").localeCompare(String(b.boar_pig_id || ""));
async function loadExpectedDates() {
  try {
    const response = await fetch("/api/pig-weights/matings");
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error("Parings kon nie gelaai word nie.");
    const rows = (data.records || []).filter(row => row.is_open === "Yes" && dateLabel(row)).sort(compareExpectedRows);
    body.innerHTML = rows.length ? rows.map(row => `<tr><td>${safe(ownerIdentity(row.sow_name, row.sow_tag_number, row.sow_pig_id))}</td><td>${safe(dateLabel(row))}</td><td>${safe(ownerIdentity(row.boar_name, row.boar_tag_number, row.boar_pig_id))}</td><td class="vjd-check">&#9633;</td></tr>`).join("") : '<tr><td colspan="4">Geen aktiewe teelsiklusse met ’n verwagte jongdatum of -venster nie.</td></tr>';
    note.textContent = `${rows.length} aktiewe teelsiklus${rows.length === 1 ? "" : "se"}. ’n Reeks kom van die blootstellingsvenster; dit is nie ’n presiese diens- of bevrugtingsdatum nie.`;
  } catch (error) { body.innerHTML = `<tr><td colspan="3">${safe(error.message)}</td></tr>`; note.textContent = ""; }
}
document.getElementById("vjd_print_button").addEventListener("click", () => window.print());
loadExpectedDates();
if (typeof module !== "undefined") module.exports = { ownerIdentity, dateLabel, compareExpectedRows };
