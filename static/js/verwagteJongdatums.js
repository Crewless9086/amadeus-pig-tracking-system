const body = document.getElementById("vjd_rows");
const note = document.getElementById("vjd_note");
const safe = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
async function loadExpectedDates() {
  try {
    const response = await fetch("/api/pig-weights/matings");
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error("Parings kon nie gelaai word nie.");
    const rows = (data.records || []).filter(row => row.is_open === "Yes" && row.expected_farrowing_date).sort((a,b) => String(a.expected_farrowing_date).localeCompare(String(b.expected_farrowing_date)) || String(a.sow_tag_number).localeCompare(String(b.sow_tag_number)));
    body.innerHTML = rows.length ? rows.map(row => `<tr><td>${safe(row.sow_tag_number || row.sow_pig_id || "-")}</td><td>${safe(row.expected_farrowing_date)}</td><td>${safe(row.boar_tag_number || row.boar_pig_id || "-")}</td><td class="vjd-check">&#9633;</td></tr>`).join("") : '<tr><td colspan="4">Geen aktiewe parings met ’n verwagte jongdatum nie.</td></tr>';
    note.textContent = `${rows.length} aktiewe paring${rows.length === 1 ? "" : "s"}. Verwagte jongdatum = paringsdatum + 114 dae wanneer geen afsonderlike datum aangeteken is nie.`;
  } catch (error) { body.innerHTML = `<tr><td colspan="3">${safe(error.message)}</td></tr>`; note.textContent = ""; }
}
document.getElementById("vjd_print_button").addEventListener("click", () => window.print());
loadExpectedDates();
