const PWR_ROW_COUNT = 16;
const rows = document.getElementById("pwr_piglet_rows");
const notesRows = document.getElementById("pwr_notes_rows");
const params = new URLSearchParams(window.location.search);
const matingId = String(params.get("mating_id") || "").trim();
const litterId = String(params.get("litter_id") || "").trim();
const dateParts = Object.fromEntries(new Intl.DateTimeFormat("en", {timeZone:"Africa/Johannesburg",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date()).map(part => [part.type, part.value]));
const informationDate = `${dateParts.year}-${dateParts.month}-${dateParts.day}`;

const clean = value => value == null ? "" : String(value).trim();
const valueFor = (...values) => values.map(clean).find(Boolean) || "";
const setValue = (id, value) => { const field=document.getElementById(id); if(field)field.value=clean(value); };
const safeReturnPath = value => { const path=clean(value); return path.startsWith("/")&&!path.startsWith("//")&&!/[\\\u0000-\u001f]/.test(path)?path:""; };
const escapeAttribute = value => clean(value).replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]);

function setBackLink() {
  const requested=safeReturnPath(params.get("return_to"));
  document.getElementById("pwr_back_link").href=requested||(litterId?`/litter/${encodeURIComponent(litterId)}?return_to=${encodeURIComponent("/litters")}&return_label=${encodeURIComponent("Terug na Litters")}`:"/litters");
}
function renderRows(pigs=[]) {
  rows.innerHTML=Array.from({length:PWR_ROW_COUNT},(_,index)=>{const pig=pigs[index]||{};return `<tr><td>${index+1}</td><td><input class="pwr-row-input" aria-label="Ry ${index+1} tag" value="${escapeAttribute(pig.tag_number)}"></td><td><input class="pwr-row-input" aria-label="Ry ${index+1} geslag" value="${escapeAttribute(pig.sex)}"></td><td><input class="pwr-row-input" aria-label="Ry ${index+1} gewig" value="${escapeAttribute(pig.wean_weight_kg)}"></td></tr>`}).join("");
}
function renderNotes() {
  notesRows.innerHTML=Array.from({length:3},(_,index)=>`<tr><td class="pwr-editable" contenteditable="true" aria-label="Nota ${index+1} datum"><span class="pwr-date-guide">YYYY - MM - DD</span></td><td class="pwr-editable" contenteditable="true" aria-label="Nota ${index+1} tag of geslag"></td><td class="pwr-editable" contenteditable="true" aria-label="Nota ${index+1}"></td></tr>`).join("");
  notesRows.addEventListener("focusin",event=>{const guide=event.target.querySelector?.(".pwr-date-guide");if(guide)guide.remove();});
}
async function fetchJson(url) {
  const response=await fetch(url,{headers:{Accept:"application/json"}}),data=await response.json();
  if(!response.ok||!data.success)throw new Error(`Prefill read failed: ${response.status}`);
  return data;
}
function findMating(records, requestedMatingId, requestedLitterId) {
  if(requestedMatingId)return(records||[]).find(record=>clean(record.mating_id)===requestedMatingId);
  return(records||[]).find(record=>requestedLitterId&&clean(record.linked_litter_id)===requestedLitterId);
}
function fillMating(mating) {
  if(!mating)return;
  setValue("pwr_mating_id",mating.mating_id);setValue("pwr_sow",valueFor(mating.sow_name,mating.sow_canonical_tag_number,mating.sow_tag_number,mating.sow_pig_id));setValue("pwr_boar",valueFor(mating.boar_name,mating.boar_canonical_tag_number,mating.boar_tag_number,mating.boar_pig_id));setValue("pwr_mating_pen",valueFor(mating.mating_pen_name,mating.mating_pen_id));setValue("pwr_mating_date",mating.mating_date);setValue("pwr_mating_method",mating.mating_method);setValue("pwr_expected_from",valueFor(mating.expected_farrowing_window_start,mating.expected_farrowing_date));setValue("pwr_expected_to",mating.expected_farrowing_window_end);
  const currentPen=valueFor(mating.sow_current_pen_name,mating.sow_current_pen_id);setValue("pwr_current_pen",currentPen);if(currentPen)document.getElementById("pwr_current_pen_label").textContent=`Huidige hok · ${informationDate}`;
}
function fillLitter(litter) {
  if(!litter)return;const counts=litter.reconciliation||{};
  setValue("pwr_litter_id",litter.litter_id);setValue("pwr_farrowing_date",valueFor(litter.birth_date,litter.farrowing_date,litter.piglets?.[0]?.date_of_birth));setValue("pwr_farrowing_pen",valueFor(litter.farrowing_pen_name,litter.farrowing_pen_id,litter.litter_pen_name,litter.litter_pen_id));setValue("pwr_total_born",litter.total_born??counts.total_born);setValue("pwr_born_alive",litter.born_alive??counts.born_alive);setValue("pwr_stillborn",litter.stillborn_count??counts.stillborn_count);setValue("pwr_deaths",litter.lifecycle_outcomes?.dead);setValue("pwr_first_treatment_date",litter.first_treatment_date);setValue("pwr_first_male_total",litter.observed_male_count);setValue("pwr_first_female_total",litter.observed_female_count);setValue("pwr_expected_wean_date",valueFor(litter.expected_wean_date,litter.planned_wean_date));setValue("pwr_wean_date",litter.wean_date);setValue("pwr_weaned_total",litter.weaned_count);
  const male=clean(litter.weaned_male_count),female=clean(litter.weaned_female_count);setValue("pwr_weaned_sex_total",male||female?`${male||"-"} / ${female||"-"}`:"");renderRows((litter.piglets||[]).slice(0,PWR_ROW_COUNT));
}
async function prefill() {
  if(!matingId&&!litterId)return;
  try {
    const matingData=await fetchJson("/api/pig-weights/matings");let mating=findMating(matingData.records,matingId,litterId);
    const resolvedLitterId=litterId||clean(mating?.linked_litter_id);let litter=null;
    if(resolvedLitterId){const litterData=await fetchJson(`/api/pig-weights/litter/${encodeURIComponent(resolvedLitterId)}`);litter=litterData.litter||{};mating=mating||findMating(matingData.records,clean(litter.mating_id),resolvedLitterId);}
    if(!mating)throw new Error("Canonical mating not found");
    if(litterId&&clean(mating.linked_litter_id)&&clean(mating.linked_litter_id)!==litterId)throw new Error("Mating and litter identifiers do not match");
    if(litter&&clean(litter.mating_id)&&clean(litter.mating_id)!==clean(mating.mating_id))throw new Error("Litter resolves to another mating");
    fillMating(mating);fillLitter(litter);document.getElementById("pwr_entry_source").textContent=litter?"Paring / gekoppelde werpsel":"Ingang: Paring-ID";
  } catch(error) { document.getElementById("pwr_entry_source").textContent="Vooraf-invul nie beskikbaar nie";console.warn("Kon nie die vorm vooraf invul nie.",error); }
}
document.getElementById("pwr_information_date").textContent=informationDate;document.getElementById("pwr_print_button").addEventListener("click",()=>window.print());setBackLink();renderRows();renderNotes();prefill();
