document.addEventListener("DOMContentLoaded", function () {
    setupMatingBoardEvents();
    loadMatingBoard();
    loadExposureRemovals();
});

let allMatingRecords = [];
let allPens = [];
let selectedSowId = "";
let selectedSectionId = "";
let activeAssumePregnantId = null;
let activeMarkNotPregnantId = null;
const expandedMatingIds = new Set();
let activeExposureGroups = new Map();
let pendingRemoval = null;

function isReadOnlyPreview() {
    return Boolean(new URLSearchParams(window.location.search).get("preview"));
}

async function loadExposureRemovals() {
    const workspace = document.getElementById("active_exposure_workspace");
    const board = document.getElementById("exposure_removal_board");
    if (!board) return;
    try {
        const previewMode = new URLSearchParams(window.location.search).get("preview");
        let data;
        if (previewMode === "active-exposure-v1") {
            data = {success:true, records:PREVIEW_EXPOSURES};
        } else if (previewMode === "active-exposure-empty-v1") {
            data = {success:true, records:[]};
        } else {
            const response = await fetch("/api/pig-weights/breeding-attention/exposures");
            data = await response.json();
            if (!response.ok || !data.success) throw new Error("Exposure evidence unavailable.");
        }
        activeExposureGroups = new Map();
        (data.records || []).forEach(row => {
            const key = [row.exposure_group_identity || row.exposure_identity, row.boar_pig_id]
                .filter(Boolean).join(":");
            if (!activeExposureGroups.has(key)) activeExposureGroups.set(key, []);
            activeExposureGroups.get(key).push(row);
        });
        if (!activeExposureGroups.size) {
            board.innerHTML = "";
            workspace?.classList.add("hidden");
            return;
        }
        workspace?.classList.remove("hidden");
        board.innerHTML = [...activeExposureGroups].map(([group, rows], groupIndex) => {
            const planned = formatDateOnly(rows.map(row => row.planned_removal_on).filter(Boolean).sort()[0]) || "";
            const started = formatDateOnly(rows.map(row => row.occurred_on).filter(Boolean).sort()[0]) || "Onbekend";
            const boars = [...new Set(rows.map(row => row.boar_label).filter(Boolean))].join(", ") || "Beer onbekend";
            const sows = rows.slice().sort((a,b) => String(a.sow_label).localeCompare(String(b.sow_label))).map(row => escapeHtml(row.sow_label)).join(", ");
            const pens = [...new Set(rows.map(row => row.current_pen_name || row.pen_name).filter(Boolean))].join(", ") || "Hok onbekend";
            const timing = exposureTiming(planned);
            return `<article class="active-exposure-card ${timing.cssClass}"><div class="active-exposure-main"><span class="exposure-state">${escapeHtml(timing.label)}</span><h3>${escapeHtml(boars)}</h3><p>${sows}</p></div>
              <dl class="active-exposure-facts"><div><dt>IN</dt><dd>${escapeHtml(started)}</dd></div><div><dt>Beplande UIT</dt><dd>${escapeHtml(planned || "Onbekend")}</dd></div><div><dt>Hok</dt><dd>${escapeHtml(pens)}</dd></div></dl>
              <div class="active-exposure-actions"><button type="button" class="secondary-action" data-open-removal="${escapeHtml(group)}" aria-expanded="false" aria-controls="removal-${groupIndex}">Teken werklike UIT aan</button><div id="removal-${groupIndex}" class="removal-action hidden" data-removal-action="${escapeHtml(group)}"><label>Werklike UIT-datum <input type="date" value="" data-removal-date="${escapeHtml(group)}"></label><button type="button" class="primary-action" data-preview-removal="${escapeHtml(group)}">Gaan voort</button></div></div></article>`;
        }).join("");
    } catch (error) {
        workspace?.classList.remove("hidden");
        board.innerHTML = `<p class="message-error">${escapeHtml(error.message)}</p>`;
    }
}

function exposureTiming(planned) {
    const days = daysBetween(startOfDay(new Date()), parseDate(planned));
    if (days === null) return {label: "UIT-datum onbekend", cssClass: "exposure-unknown"};
    if (days < 0) return {label: `${Math.abs(days)} dag(e) agterstallig`, cssClass: "exposure-overdue"};
    if (days === 0) return {label: "UIT vandag", cssClass: "exposure-due"};
    return {label: `UIT oor ${days} dag(e)`, cssClass: "exposure-upcoming"};
}

function formatDateOnly(value) {
    const parsed = parseDate(value);
    if (!parsed) return "";
    const year = parsed.getFullYear();
    const month = String(parsed.getMonth() + 1).padStart(2, "0");
    const day = String(parsed.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}

function removalRows(group, actualRemovedOn) {
    return (activeExposureGroups.get(group) || []).map(row => ({
        pig_id: row.sow_pig_id, label: row.sow_label, action: "exposure_removal",
        boar_pig_id: row.boar_pig_id, exposure_identity: row.exposure_identity,
        exposure_group_identity: row.exposure_group_identity,
        exposure_started_on: row.occurred_on, actual_removed_on: actualRemovedOn
    }));
}

async function previewExposureRemoval(group) {
    if (isReadOnlyPreview()) {
        throw new Error("Voorskoumodus is leesalleen.");
    }
    const dateInput = [...document.querySelectorAll("[data-removal-date]")]
        .find(input => input.getAttribute("data-removal-date") === group);
    const actualRemovedOn = dateInput?.value || "";
    const rows = removalRows(group, actualRemovedOn);
    const evidence_generation = `browser-removal:${group}:${actualRemovedOn}`;
    const response = await fetch("/api/pig-weights/breeding-attention/grouped-actions/preview", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({rows,evidence_generation})
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error((data.errors || [data.status]).join("; "));
    pendingRemoval = {rows,evidence_generation,confirmed_preview_sha256:data.preview_sha256};
    const box=document.getElementById("exposure_removal_preview");
    const lines=data.preview.rows.map(row => `<li><b>${escapeHtml(row.label)}</b>: ${escapeHtml(row.service_window_start)}–${escapeHtml(row.service_window_end)}; verwagte jong-venster ${escapeHtml(row.expected_farrowing_window_start)}–${escapeHtml(row.expected_farrowing_window_end)}</li>`).join("");
    box.classList.remove("hidden");
    box.innerHTML=`<b>Beskermde verwyderingsvoorskou</b><ul>${lines}</ul><p>Net blootstellingsverwydering en een oop teelsiklus per sog. Presiese diens, konsepsie en dragtigheid bly Onbekend. Geen skuif word voorgestel nie.</p><button type="button" class="primary-action" data-confirm-removal>Bevestig presiese voorskou</button>`;
}

async function confirmExposureRemoval() {
    if (isReadOnlyPreview()) throw new Error("Voorskoumodus is leesalleen.");
    if (!pendingRemoval) return;
    const response=await fetch("/api/pig-weights/breeding-attention/grouped-actions/execute",{
        method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(pendingRemoval)});
    const data=await response.json();
    if (!response.ok || !data.success) throw new Error(data.status || "Removal failed.");
    pendingRemoval=null;
    document.getElementById("exposure_removal_preview").innerHTML=`<b>${data.rows_changed} verwydering(s) en teelsiklus(se) presies een keer aangeteken.</b>`;
    await Promise.all([loadExposureRemovals(),loadMatingBoard()]);
}

const PREVIEW_EXPOSURES = [
    {exposure_group_identity:"PREVIEW-BOLA", exposure_identity:"PREVIEW-SOPHIE", sow_pig_id:"PIG-2026-5FA6", sow_label:"Sophie", boar_pig_id:"PIG-2026-8645", boar_label:"Bola", occurred_on:"2026-08-12", planned_removal_on:"2026-08-28", current_pen_name:"Kraam Saal 03"},
    {exposure_group_identity:"PREVIEW-TYSON", exposure_identity:"PREVIEW-OLIVE", sow_pig_id:"PIG-2026-069E", sow_label:"Olive", boar_pig_id:"PIG-2026-3B5F", boar_label:"Tyson", occurred_on:"2026-08-12", planned_removal_on:"2026-08-28", current_pen_name:"Kraam Saal 04"},
    {exposure_group_identity:"PREVIEW-TYSON", exposure_identity:"PREVIEW-SHUPE", sow_pig_id:"PIG-2026-34BF", sow_label:"Shupe", boar_pig_id:"PIG-2026-3B5F", boar_label:"Tyson", occurred_on:"2026-08-12", planned_removal_on:"2026-08-28", current_pen_name:"Kraam Saal 04"},
    {exposure_group_identity:"PREVIEW-TYSON", exposure_identity:"PREVIEW-LUCY", sow_pig_id:"PIG-2026-1248", sow_label:"Lucy", boar_pig_id:"PIG-2026-3B5F", boar_label:"Tyson", occurred_on:"2026-08-12", planned_removal_on:"2026-08-28", current_pen_name:"Kraam Saal 04"},
    {exposure_group_identity:"PREVIEW-PRINCE", exposure_identity:"PREVIEW-LOLLY", sow_pig_id:"PIG-2026-94B9", sow_label:"Lolly", boar_pig_id:"PIG-2026-E057", boar_label:"Prince", occurred_on:"2026-08-12", planned_removal_on:"2026-08-28", current_pen_name:"Kraam Saal 01"}
];

const SECTION_DEFINITIONS = [
    {
        id: "current_exposure",
        title: "Tans by beer",
        description: "Diere wat reeds saam geplaas is vir die huidige natuurlike blootstellingsvenster."
    },
    {
        id: "needs_action",
        title: "Aandag Nodig",
        description: "Agterstallige kontroles, verwagte jong datums of rekords wat 'n besluit nodig het."
    },
    {
        id: "move_soon",
        title: "Berei Voor",
        description: "Sôe wat hul verwagte jong datum nader."
    },
    {
        id: "check_soon",
        title: "Komende Kontroles",
        description: "Oop parings wat hul dragtigheidskontrole nader."
    },
    {
        id: "open",
        title: "Oop Parings",
        description: "Ander aktiewe teelrekords wat nog aan die gang is."
    },
    {
        id: "closed",
        title: "Afgesluit / Gejong",
        description: "Voltooide, nie-dragtige of gekoppelde werpselrekords."
    }
];

const PREVIEW_RECORDS = [
    {mating_id:"MAT-EXPOSURE-SOPHIE",source_exposure_identity:"EXPOSURE-SOPHIE",sow_pig_id:"PIG-2026-5FA6",sow_name:"Sophie",boar_pig_id:"PIG-2026-8645",boar_name:"Bola",sow_current_pen_name:"Kraam Saal 03",breeding_cycle_state:"Exposure Active",service_window_start:"2026-08-12",service_window_end:"2026-08-28",exposure_planned_removal_on:"2026-08-28",expected_farrowing_window_start:"2026-12-04",expected_farrowing_window_end:"2026-12-20",mating_status:"Open",outcome:"Pending",pregnancy_check_result:"Unknown",mating_method:"Natural",is_open:"Yes"},
    {mating_id:"MAT-EXPOSURE-OLIVE",source_exposure_identity:"EXPOSURE-OLIVE",sow_pig_id:"PIG-2026-069E",sow_name:"Olive",boar_pig_id:"PIG-2026-3B5F",boar_name:"Tyson",sow_current_pen_name:"Kraam Saal 04",breeding_cycle_state:"Exposure Active",service_window_start:"2026-08-12",service_window_end:"2026-08-28",exposure_planned_removal_on:"2026-08-28",expected_farrowing_window_start:"2026-12-04",expected_farrowing_window_end:"2026-12-20",mating_status:"Open",outcome:"Pending",pregnancy_check_result:"Unknown",mating_method:"Natural",is_open:"Yes"},
    {mating_id:"MAT-2026-MONA",sow_pig_id:"PIG-MONA",sow_tag_number:"Mona",boar_pig_id:"PIG-UNKNOWN",boar_tag_number:"Beer onbekend",sow_current_pen_name:"Kraamhok",mating_date:"2026-05-01",days_since_mating:"103",expected_pregnancy_check_date:"2026-05-22",expected_farrowing_date:"2026-08-23",mating_status:"Confirmed_Pregnant",outcome:"Pending",pregnancy_check_result:"Assumed_Pregnant",mating_method:"Natural",exposure_group:"-",is_open:"Yes"},
    {mating_id:"MAT-2026-CLOSED",sow_pig_id:"PIG-TEENA",sow_tag_number:"Teena",boar_pig_id:"PIG-BOLA",boar_tag_number:"Bola",sow_current_pen_name:"D3",mating_date:"2026-04-14",days_since_mating:"120",expected_pregnancy_check_date:"2026-05-05",expected_farrowing_date:"2026-08-06",actual_farrowing_date:"2026-07-07",linked_litter_id:"LIT-2026-1350",mating_status:"Completed",outcome:"Farrowed",pregnancy_check_result:"Confirmed_Pregnant",mating_method:"Natural",exposure_group:"-",is_open:"No"}
];

async function loadAllPens() {
    try {
        const response = await fetch("/api/pig-weights/pens");
        const data = await response.json();
        allPens = data.pens || [];
    } catch (error) {
        console.error("Could not load pens:", error);
    }
}

async function loadMatingBoard() {
    const messageBox = document.getElementById("matings_message");
    const board = document.getElementById("matings_board");
    const summary = document.getElementById("mating_summary");
    const controls = document.getElementById("mating_controls");

    try {
        await loadAllPens();

        const response = await fetch("/api/pig-weights/matings");
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error("Failed to load mating records.");
        }

        const previewMode = new URLSearchParams(window.location.search).get("preview");
        const sourceRecords = ["facelift-v3", "active-exposure-v1"].includes(previewMode) ? PREVIEW_RECORDS : (data.records || []);
        allMatingRecords = sourceRecords.map(record => {
            const classification = classifyMating(record);
            return {
                ...record,
                action_section: classification.section,
                action_text: classification.actionText,
                action_class: classification.actionClass,
                action_priority: classification.actionPriority,
                sort_date: classification.sortDate
            };
        });

        renderSummary(summary, allMatingRecords);
        renderControls(controls, allMatingRecords);
        renderBoard(board, getVisibleRecords());
        const count = document.getElementById("mating_record_count");
        if (count) count.textContent = `${allMatingRecords.length} rekords`;
    } catch (error) {
        console.error("Matings load error:", error);
        if (["facelift-v3", "active-exposure-v1"].includes(new URLSearchParams(window.location.search).get("preview"))) {
            allMatingRecords = PREVIEW_RECORDS.map(record => {
                const classification = classifyMating(record);
                return {...record, action_section: classification.section, action_text: classification.actionText, action_class: classification.actionClass, action_priority: classification.actionPriority, sort_date: classification.sortDate};
            });
            renderSummary(summary, allMatingRecords);
            renderControls(controls, allMatingRecords);
            renderBoard(board, getVisibleRecords());
            const count = document.getElementById("mating_record_count");
            if (count) count.textContent = `${allMatingRecords.length} rekords`;
            messageBox.classList.add("hidden");
            return;
        }
        messageBox.classList.remove("hidden", "message-success", "message-error");
        messageBox.classList.add("message-error");
        messageBox.textContent = "Something went wrong while loading the breeding board.";
        board.innerHTML = "";
        summary.innerHTML = "";
        controls.innerHTML = "";
    }
}

function setupMatingBoardEvents() {
    document.addEventListener("change", function (event) {
        if (event.target.id !== "mating_sow_filter") return;

        selectedSowId = event.target.value || "";
        expandedMatingIds.clear();
        activeAssumePregnantId = null;
        activeMarkNotPregnantId = null;
        renderBoard(document.getElementById("matings_board"), getVisibleRecords());
        renderControls(document.getElementById("mating_controls"), allMatingRecords);
    });

    document.addEventListener("click", async function (event) {
        if (isReadOnlyPreview() && event.target.closest("[data-assume-pregnant-confirm],[data-mark-not-pregnant-confirm],[data-confirm-removal]")) {
            alert("Voorskoumodus is leesalleen.");
            return;
        }
        const removalAction = event.target.closest("[data-open-removal]");
        if (removalAction) {
            const group = removalAction.getAttribute("data-open-removal");
            const panel = [...document.querySelectorAll("[data-removal-action]")]
                .find(item => item.getAttribute("data-removal-action") === group);
            panel?.classList.toggle("hidden");
            removalAction.setAttribute("aria-expanded", panel && !panel.classList.contains("hidden") ? "true" : "false");
            return;
        }
        const removalPreview=event.target.closest("[data-preview-removal]");
        if (removalPreview) {
            try { await previewExposureRemoval(removalPreview.getAttribute("data-preview-removal")); }
            catch(error) { alert(error.message); }
            return;
        }
        if (event.target.closest("[data-confirm-removal]")) {
            try { await confirmExposureRemoval(); } catch(error) { alert(error.message); }
            return;
        }
        const summaryFilter = event.target.closest("[data-mating-section]");
        if (summaryFilter) {
            const nextSection = summaryFilter.getAttribute("data-mating-section") || "";
            selectedSectionId = selectedSectionId === nextSection ? "" : nextSection;
            renderSummary(document.getElementById("mating_summary"), allMatingRecords);
            renderControls(document.getElementById("mating_controls"), allMatingRecords);
            renderBoard(document.getElementById("matings_board"), getVisibleRecords());
            return;
        }
        const cardToggle = event.target.closest("[data-mating-toggle]");
        if (cardToggle) {
            const matingId = cardToggle.getAttribute("data-mating-toggle");
            if (expandedMatingIds.has(matingId)) {
                expandedMatingIds.delete(matingId);
                if (activeAssumePregnantId === matingId) activeAssumePregnantId = null;
                if (activeMarkNotPregnantId === matingId) activeMarkNotPregnantId = null;
            } else {
                expandedMatingIds.add(matingId);
            }
            renderBoard(document.getElementById("matings_board"), getVisibleRecords());
            renderControls(document.getElementById("mating_controls"), allMatingRecords);
            return;
        }

        const assumeBtn = event.target.closest("[data-assume-pregnant]");
        if (assumeBtn) {
            const matingId = assumeBtn.getAttribute("data-assume-pregnant");
            if (activeAssumePregnantId === matingId) {
                activeAssumePregnantId = null;
            } else {
                activeAssumePregnantId = matingId;
                activeMarkNotPregnantId = null;
                expandedMatingIds.add(matingId);
            }
            renderBoard(document.getElementById("matings_board"), getVisibleRecords());
            return;
        }

        const markNotPregnantBtn = event.target.closest("[data-mark-not-pregnant]");
        if (markNotPregnantBtn) {
            const matingId = markNotPregnantBtn.getAttribute("data-mark-not-pregnant");
            if (activeMarkNotPregnantId === matingId) {
                activeMarkNotPregnantId = null;
            } else {
                activeMarkNotPregnantId = matingId;
                activeAssumePregnantId = null;
                expandedMatingIds.add(matingId);
            }
            renderBoard(document.getElementById("matings_board"), getVisibleRecords());
            return;
        }

        const confirmBtn = event.target.closest("[data-assume-pregnant-confirm]");
        if (confirmBtn) {
            const matingId = confirmBtn.getAttribute("data-assume-pregnant-confirm");
            await handleAssumePregnant(matingId);
            return;
        }

        const cancelBtn = event.target.closest("[data-assume-pregnant-cancel]");
        if (cancelBtn) {
            activeAssumePregnantId = null;
            renderBoard(document.getElementById("matings_board"), getVisibleRecords());
            return;
        }

        const markConfirmBtn = event.target.closest("[data-mark-not-pregnant-confirm]");
        if (markConfirmBtn) {
            const matingId = markConfirmBtn.getAttribute("data-mark-not-pregnant-confirm");
            await handleMarkNotPregnant(matingId);
            return;
        }

        const markCancelBtn = event.target.closest("[data-mark-not-pregnant-cancel]");
        if (markCancelBtn) {
            activeMarkNotPregnantId = null;
            renderBoard(document.getElementById("matings_board"), getVisibleRecords());
            return;
        }

        if (event.target.id !== "toggle_all_mating_details") return;

        const visibleRecords = getVisibleRecords();
        const allVisibleExpanded = visibleRecords.length > 0 && visibleRecords.every(record => expandedMatingIds.has(record.mating_id));

        if (allVisibleExpanded) {
            visibleRecords.forEach(record => expandedMatingIds.delete(record.mating_id));
            activeAssumePregnantId = null;
            activeMarkNotPregnantId = null;
        } else {
            visibleRecords.forEach(record => expandedMatingIds.add(record.mating_id));
        }

        renderBoard(document.getElementById("matings_board"), visibleRecords);
        renderControls(document.getElementById("mating_controls"), allMatingRecords);
    });
}

async function handleAssumePregnant(matingId) {
    if (isReadOnlyPreview()) throw new Error("Voorskoumodus is leesalleen.");
    const penSelect = document.getElementById(`assume_pen_${matingId}`);
    const msgDiv = document.getElementById(`assume_msg_${matingId}`);
    const targetPenId = penSelect ? penSelect.value : "";

    try {
        const response = await fetch(`/api/pig-weights/master/matings/${encodeURIComponent(matingId)}/assume-pregnant`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_pen_id: targetPenId, moved_by: "WebApp" })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            const msg = (data.errors || ["Failed to update mating."]).join(" ");
            if (msgDiv) {
                msgDiv.classList.remove("hidden", "message-success", "message-error");
                msgDiv.classList.add("message-error");
                msgDiv.textContent = msg;
            }
            return;
        }

        activeAssumePregnantId = null;
        await loadMatingBoard();
    } catch (error) {
        console.error("Assume pregnant error:", error);
        if (msgDiv) {
            msgDiv.classList.remove("hidden", "message-success", "message-error");
            msgDiv.classList.add("message-error");
            msgDiv.textContent = "Something went wrong.";
        }
    }
}

async function handleMarkNotPregnant(matingId) {
    if (isReadOnlyPreview()) throw new Error("Voorskoumodus is leesalleen.");
    const penSelect = document.getElementById(`repeat_service_pen_${matingId}`);
    const msgDiv = document.getElementById(`repeat_service_msg_${matingId}`);
    const targetPenId = penSelect ? penSelect.value : "";

    try {
        const response = await fetch(`/api/pig-weights/master/matings/${encodeURIComponent(matingId)}/mark-not-pregnant`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_pen_id: targetPenId, moved_by: "WebApp" })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            const msg = (data.errors || ["Failed to update mating."]).join(" ");
            if (msgDiv) {
                msgDiv.classList.remove("hidden", "message-success", "message-error");
                msgDiv.classList.add("message-error");
                msgDiv.textContent = msg;
            }
            return;
        }

        activeMarkNotPregnantId = null;
        await loadMatingBoard();
    } catch (error) {
        console.error("Mark not pregnant error:", error);
        if (msgDiv) {
            msgDiv.classList.remove("hidden", "message-success", "message-error");
            msgDiv.classList.add("message-error");
            msgDiv.textContent = "Something went wrong.";
        }
    }
}

function renderSummary(container, records) {
    const counts = countSections(records);
    const openCount = records.filter(record => record.is_open === "Yes").length;

    container.innerHTML = `
        <button type="button" class="info-card ${selectedSectionId === "needs_action" ? "is-active" : ""}" data-mating-section="needs_action">
          <div class="info-title">Aandag Nodig</div>
          <div class="info-value ${counts.needs_action > 0 ? "bad-text" : "good-text"}">${counts.needs_action}</div>
        </button>
        <button type="button" class="info-card ${selectedSectionId === "move_soon" ? "is-active" : ""}" data-mating-section="move_soon">
          <div class="info-title">Berei Voor</div>
          <div class="info-value ${counts.move_soon > 0 ? "neutral-text" : "good-text"}">${counts.move_soon}</div>
        </button>
        <button type="button" class="info-card ${selectedSectionId === "check_soon" ? "is-active" : ""}" data-mating-section="check_soon">
          <div class="info-title">Komende Kontroles</div>
          <div class="info-value">${counts.check_soon}</div>
        </button>
        <button type="button" class="info-card ${selectedSectionId === "open" ? "is-active" : ""}" data-mating-section="open">
          <div class="info-title">Oop Parings</div>
          <div class="info-value">${openCount}</div>
        </button>
    `;
}

function renderControls(container, records) {
    if (records.length === 0) {
        container.innerHTML = "";
        return;
    }

    const visibleRecords = getVisibleRecords();
    const allVisibleExpanded = visibleRecords.length > 0 && visibleRecords.every(record => expandedMatingIds.has(record.mating_id));
    const sowOptions = getSowOptions(records)
        .map(sow => `<option value="${escapeHtml(sow.sow_pig_id)}" ${sow.sow_pig_id === selectedSowId ? "selected" : ""}>${escapeHtml(sow.label)}</option>`)
        .join("");

    container.innerHTML = `
        <div class="form-grid">
          <div class="form-group">
            <label for="mating_sow_filter">Filtreer volgens sog</label>
            <select id="mating_sow_filter" name="mating_sow_filter">
              <option value="">Alle sôe</option>
              ${sowOptions}
            </select>
          </div>
          <div class="form-group">
            <label>Kaartbesonderhede</label>
            <button id="toggle_all_mating_details" type="button" class="button-link">
              ${allVisibleExpanded ? "Versteek alle besonderhede" : "Wys alle besonderhede"}
            </button>
          </div>
        </div>
        <div class="pig-list-meta">
          Wys ${visibleRecords.length} van ${records.length} paringsrekords${selectedSowId ? " vir die gekose sog" : ""}.
        </div>
    `;
}

function renderBoard(container, records) {
    if (records.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
              <div>No mating records found.</div>
              <div>${selectedSowId ? "Select All sows to return to the full list." : "Create the first mating record from Add Mating."}</div>
            </div>
        `;
        return;
    }

    const sections = SECTION_DEFINITIONS.map(section => {
        const sectionRecords = records
            .filter(record => record.action_section === section.id)
            .sort(compareMatingRecords);

        return renderSection(section, sectionRecords);
    });

    container.innerHTML = sections.join("");
}

function renderSection(section, records) {
    const cards = records.length > 0
        ? records.map(renderMatingCard).join("")
        : `
            <div class="empty-state">
              <div>No records in this section.</div>
            </div>
        `;

    return `
        <section class="history-list">
          <div class="page-header" style="margin: 8px 0 4px 0;">
            <h2 style="margin: 0 0 6px 0;">${section.title} (${records.length})</h2>
            <p>${section.description}</p>
          </div>
          ${cards}
        </section>
    `;
}

function renderMatingCard(record) {
    const isExpanded = expandedMatingIds.has(record.mating_id);
    const isAssumeFormOpen = activeAssumePregnantId === record.mating_id;
    const isMarkNotPregnantFormOpen = activeMarkNotPregnantId === record.mating_id;
    const sowLabel = escapeHtml(record.sow_name || record.sow_tag_number || record.sow_pig_id || "Sog onbekend");
    const boarLabel = escapeHtml(record.boar_name || record.boar_tag_number || record.boar_pig_id || "Beer onbekend");
    const sowPen = formatPen(record.sow_current_pen_name, record.sow_current_pen_id);
    const boarPen = formatPen(record.boar_current_pen_name, record.boar_current_pen_id);
    const isActiveExposure = record.breeding_cycle_state === "Exposure Active";
    const litterLink = record.linked_litter_id
        ? `<a class="detail-link" href="${withReturnContext(`/litter/${encodeURIComponent(record.linked_litter_id)}`, "/matings", "Back to Breeding Board")}">${escapeHtml(record.linked_litter_id)}</a>`
        : "-";

    const showAssumeButton = isEligibleForAssumePregnant(record);
    const assumeButtonHtml = showAssumeButton
        ? `<button type="button" class="button-link${isAssumeFormOpen ? " button-link-secondary" : ""}" data-assume-pregnant="${escapeHtml(record.mating_id)}">
             ${isAssumeFormOpen ? "Cancel" : "Move to Farrowing / Assume Pregnant"}
           </button>`
        : "";

    const assumeFormHtml = isAssumeFormOpen ? renderAssumePregnantForm(record.mating_id) : "";
    const showAddLitterButton = isEligibleForAddLitter(record);
    const addLitterButtonHtml = showAddLitterButton
        ? `<a class="button-link" href="/master/add-litter?mating_id=${encodeURIComponent(record.mating_id || "")}">Add Litter</a>`
        : "";
    const showMarkNotPregnantButton = isEligibleForMarkNotPregnant(record);
    const markNotPregnantButtonHtml = showMarkNotPregnantButton
        ? `<button type="button" class="button-link${isMarkNotPregnantFormOpen ? " button-link-secondary" : ""}" data-mark-not-pregnant="${escapeHtml(record.mating_id)}">
             ${isMarkNotPregnantFormOpen ? "Cancel" : "Mark Not Pregnant / Repeat Service"}
           </button>`
        : "";
    const markNotPregnantFormHtml = isMarkNotPregnantFormOpen ? renderMarkNotPregnantForm(record.mating_id) : "";

    return `
        <div class="history-item mating-card stage-${escapeHtml(record.action_section)} ${isExpanded ? "mating-card-expanded" : ""}" data-mating-toggle="${escapeHtml(record.mating_id || "")}" role="button" tabindex="0" aria-expanded="${isExpanded ? "true" : "false"}">
          <div class="history-item-top">
            <div>
              <div class="history-item-date">${sowLabel} x ${boarLabel}</div>
              ${isActiveExposure ? "" : `<div class="pig-list-meta">Mating ID: ${escapeHtml(record.mating_id || "-")}</div>`}
            </div>
            <div class="mating-card-actions">
              <div class="history-item-weight ${record.action_class}">${escapeHtml(record.action_text)}</div>
            </div>
          </div>

          <div class="history-item-grid mating-card-compact">
            <div>
              <div class="history-label">${isActiveExposure ? "IN" : "Parings / Plasings Datum"}</div>
              <div class="history-value">${escapeHtml(isActiveExposure ? (record.service_window_start || "-") : (record.mating_date || "-"))}</div>
              <div class="pig-list-meta">Hok: ${escapeHtml(sowPen)}</div>
            </div>
            <div>
              <div class="history-label">${isActiveExposure ? (record.exposure_actual_removal_on ? "Werklike UIT" : "Beplande UIT") : "Verwagte jong"}</div>
              <div class="history-value ${record.is_overdue_farrowing === "Yes" ? "bad-text" : "neutral-text"}">${escapeHtml(isActiveExposure ? (record.exposure_actual_removal_on || record.exposure_planned_removal_on || record.service_window_end || "-") : (record.expected_farrowing_date || "-"))}</div>
            </div>
            <div>
              <div class="history-label">${isActiveExposure ? "Verwagte jong" : "Status / Uitkoms"}</div>
              <div class="history-value">${isActiveExposure ? escapeHtml((record.expected_farrowing_window_start && record.expected_farrowing_window_end) ? `${record.expected_farrowing_window_start} – ${record.expected_farrowing_window_end}` : "-") : `${escapeHtml(record.mating_status || "-")} / ${escapeHtml(record.outcome || "-")}`}</div>
            </div>
          </div>

          <div class="mating-card-details ${isExpanded ? "" : "hidden"}">
            <div class="history-item-grid">
              <div>
                <div class="history-label">Boar</div>
                <div class="history-value">${renderPigLink(record.boar_pig_id, record.boar_name || record.boar_tag_number) || "-"}</div>
                <div class="pig-list-meta">Pen: ${escapeHtml(boarPen)}</div>
              </div>
              <div>
                <div class="history-label">Service evidence</div>
                <div class="history-value">${escapeHtml(record.mating_date || ((record.service_window_start && record.service_window_end) ? `${record.service_window_start} – ${record.service_window_end} (exposure estimate; exact service unknown)` : "Unknown"))}</div>
                ${record.source_exposure_identity ? (record.breeding_cycle_state ? `<div class="pig-list-meta">Status: ${escapeHtml(record.breeding_cycle_state)} · IN: ${escapeHtml(record.service_window_start || "Onbekend")} · ${record.exposure_actual_removal_on ? "Werklike UIT" : "Beplande UIT"}: ${escapeHtml(record.exposure_actual_removal_on || record.exposure_planned_removal_on || record.service_window_end || "Onbekend")}<br>Verwagte Jong Vanaf: ${escapeHtml(record.expected_farrowing_window_start || "Onbekend")} · Verwagte Jong Tot: ${escapeHtml(record.expected_farrowing_window_end || "Onbekend")}<br>Presiese diensdatum, konsepsie en dragtigheid: Onbekend</div>` : `<div class="pig-list-meta">Status: Ongeklassifiseerde historiese blootstelling · IN/UIT: Onbekend</div>`) : ""}
              </div>
              <div>
                <div class="history-label">Days Since Mating</div>
                <div class="history-value">${escapeHtml(record.days_since_mating || "-")}</div>
              </div>
              <div>
                <div class="history-label">Expected Check</div>
                <div class="history-value ${record.is_overdue_check === "Yes" ? "bad-text" : "neutral-text"}">${escapeHtml(record.expected_pregnancy_check_date || "-")}</div>
              </div>
              <div>
                <div class="history-label">Pregnancy Result</div>
                <div class="history-value">${escapeHtml(record.pregnancy_check_result || "-")}</div>
              </div>
              <div>
                <div class="history-label">Method</div>
                <div class="history-value">${escapeHtml(record.mating_method || "-")}</div>
              </div>
              <div>
                <div class="history-label">Exposure Group</div>
                <div class="history-value">${escapeHtml(record.exposure_group || "-")}</div>
              </div>
              <div>
                <div class="history-label">Actual Farrowing</div>
                <div class="history-value">${escapeHtml(record.actual_farrowing_date || "-")}</div>
              </div>
            <div>
              <div class="history-label">Linked Litter</div>
              <div class="history-value">${litterLink}</div>
            </div>
            <div>
              <div class="history-label">Open</div>
              <div class="history-value ${record.is_open === "Yes" ? "good-text" : "neutral-text"}">${escapeHtml(record.is_open || "-")}</div>
            </div>
            </div>

            <div class="history-notes">
              <div class="history-label">Movement Guidance</div>
              <div>${escapeHtml(buildMovementGuidance(record, sowPen))}</div>
            </div>

            ${showAssumeButton ? `
              <div class="history-notes" style="margin-top: 8px;">
                ${assumeButtonHtml}
                ${assumeFormHtml}
              </div>
            ` : ""}

            ${showAddLitterButton ? `
              <div class="history-notes" style="margin-top: 8px;">
                ${addLitterButtonHtml}
              </div>
            ` : ""}

            ${showMarkNotPregnantButton ? `
              <div class="history-notes" style="margin-top: 8px;">
                ${markNotPregnantButtonHtml}
                ${markNotPregnantFormHtml}
              </div>
            ` : ""}

            ${record.service_notes ? `
              <div class="history-notes">
                <div class="history-label">Notes</div>
                <div>${escapeHtml(record.service_notes)}</div>
              </div>
            ` : ""}
          </div>
        </div>
    `;
}

function renderMarkNotPregnantForm(matingId) {
    const preferredTypes = new Set(["Sow", "Gilt", "Holding", "Mixed"]);
    const preferredPens = allPens.filter(p => p.pen_type !== "Farrowing" && preferredTypes.has(p.pen_type));
    const otherPens = allPens.filter(p => p.pen_type !== "Farrowing" && !preferredTypes.has(p.pen_type));

    const preferredOptions = preferredPens.map(p =>
        `<option value="${escapeHtml(p.pen_id)}">[${escapeHtml(p.pen_type || "Pen")}] ${escapeHtml(p.pen_name || p.pen_id)}</option>`
    ).join("");
    const otherOptions = otherPens.map(p =>
        `<option value="${escapeHtml(p.pen_id)}">${escapeHtml(p.pen_name || p.pen_id)}</option>`
    ).join("");

    return `
        <div class="assume-pregnant-form" style="margin-top: 10px; padding: 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface-subtle, #f9f9f9);">
          <div class="history-label" style="margin-bottom: 8px;">Mark Not Pregnant / Repeat Service</div>
          <p style="margin: 0 0 10px 0; font-size: 0.9em;">This will set Pregnancy_Check_Result = Not_Pregnant, Mating_Status = Repeat_Service, and Outcome = Repeat_Required.</p>
          <div class="form-group" style="margin-bottom: 10px;">
            <label for="repeat_service_pen_${escapeHtml(matingId)}">Move sow to pen (optional)</label>
            <select id="repeat_service_pen_${escapeHtml(matingId)}">
              <option value="">No pen change</option>
              ${preferredOptions}
              ${otherOptions}
            </select>
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <button type="button" data-mark-not-pregnant-confirm="${escapeHtml(matingId)}">Confirm</button>
            <button type="button" class="button-link button-link-secondary" data-mark-not-pregnant-cancel>Cancel</button>
          </div>
          <div id="repeat_service_msg_${escapeHtml(matingId)}" class="message-box hidden"></div>
        </div>
    `;
}

function renderAssumePregnantForm(matingId) {
    const farrowingPens = allPens.filter(p => p.pen_type === "Farrowing");
    const otherPens = allPens.filter(p => p.pen_type !== "Farrowing");

    const farrowingOptions = farrowingPens.map(p =>
        `<option value="${escapeHtml(p.pen_id)}">[Farrowing] ${escapeHtml(p.pen_name || p.pen_id)}</option>`
    ).join("");
    const otherOptions = otherPens.map(p =>
        `<option value="${escapeHtml(p.pen_id)}">${escapeHtml(p.pen_name || p.pen_id)}</option>`
    ).join("");

    return `
        <div class="assume-pregnant-form" style="margin-top: 10px; padding: 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface-subtle, #f9f9f9);">
          <div class="history-label" style="margin-bottom: 8px;">Move to Farrowing / Assume Pregnant</div>
          <p style="margin: 0 0 10px 0; font-size: 0.9em;">This will set Pregnancy_Check_Result = Pregnant, Mating_Status = Confirmed_Pregnant. Litter creation remains a separate step.</p>
          <div class="form-group" style="margin-bottom: 10px;">
            <label for="assume_pen_${escapeHtml(matingId)}">Move sow to pen (optional)</label>
            <select id="assume_pen_${escapeHtml(matingId)}">
              <option value="">No pen change</option>
              ${farrowingOptions}
              ${otherOptions}
            </select>
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <button type="button" data-assume-pregnant-confirm="${escapeHtml(matingId)}">Confirm</button>
            <button type="button" class="button-link button-link-secondary" data-assume-pregnant-cancel>Cancel</button>
          </div>
          <div id="assume_msg_${escapeHtml(matingId)}" class="message-box hidden"></div>
        </div>
    `;
}

function isEligibleForAssumePregnant(record) {
    if (record.breeding_cycle_state === "Exposure Active") return false;
    const blocked = new Set(["Farrowed", "Cancelled", "Closed"]);
    return record.is_open === "Yes"
        && !blocked.has(record.mating_status)
        && record.mating_status !== "Confirmed_Pregnant"
        && !record.linked_litter_id;
}

function isEligibleForMarkNotPregnant(record) {
    if (record.breeding_cycle_state === "Exposure Active") return false;
    return record.mating_status === "Confirmed_Pregnant"
        && !record.linked_litter_id
        && !record.actual_farrowing_date;
}

function isEligibleForAddLitter(record) {
    if (record.breeding_cycle_state === "Exposure Active") return false;
    return record.is_open === "Yes"
        && record.mating_id
        && !record.linked_litter_id
        && !record.actual_farrowing_date
        && (record.mating_status === "Confirmed_Pregnant" || record.is_overdue_farrowing === "Yes");
}

function classifyMating(record) {
    if (record.breeding_cycle_state === "Exposure Active") {
        return {
            section: "current_exposure",
            actionText: record.owner_facing_cycle_meaning || "By beer",
            actionClass: "good-text",
            actionPriority: 0,
            sortDate: parseDate(record.service_window_start)
        };
    }
    const isClosed = record.is_open === "No" || Boolean(record.linked_litter_id);
    const expectedFarrowing = parseDate(record.expected_farrowing_date || record.expected_farrowing_window_end);
    const expectedFarrowingStart = parseDate(record.expected_farrowing_date || record.expected_farrowing_window_start);
    const actualFarrowing = parseDate(record.actual_farrowing_date);
    const expectedCheck = parseDate(record.expected_pregnancy_check_date);
    const checkResult = String(record.pregnancy_check_result || "").toLowerCase();
    const today = startOfDay(new Date());
    const daysToFarrowing = daysBetween(today, expectedFarrowing);
    const daysToCheck = daysBetween(today, expectedCheck);

    if (isClosed) {
        return {
            section: "closed",
            actionText: record.linked_litter_id ? "Litter linked" : "Closed",
            actionClass: "neutral-text",
            actionPriority: 0,
            sortDate: actualFarrowing || expectedFarrowing || parseDate(record.mating_date)
        };
    }

    if (record.is_overdue_farrowing === "Yes") {
        // Feature C: no litter recorded more than 21 days past expected farrowing
        if (!record.linked_litter_id && !record.actual_farrowing_date
                && daysToFarrowing !== null && daysToFarrowing < -21) {
            return {
                section: "needs_action",
                actionText: "No litter after 3 weeks — review",
                actionClass: "bad-text",
                actionPriority: 1,
                sortDate: expectedFarrowing
            };
        }
        return {
            section: "needs_action",
            actionText: "Overdue farrowing",
            actionClass: "bad-text",
            actionPriority: 2,
            sortDate: expectedFarrowing
        };
    }

    if (record.is_overdue_check === "Yes") {
        return {
            section: "needs_action",
            actionText: "Check pregnancy",
            actionClass: "bad-text",
            actionPriority: 3,
            sortDate: expectedCheck
        };
    }

    const daysToFarrowingStart = daysBetween(today, expectedFarrowingStart);
    if (expectedFarrowing && daysToFarrowing !== null && daysToFarrowing >= 0
            && ((daysToFarrowingStart !== null && daysToFarrowingStart <= 14) || daysToFarrowing <= 14)) {
        return {
            section: "move_soon",
            actionText: "Prepare farrowing pen",
            actionClass: "neutral-text",
            actionPriority: 4,
            sortDate: expectedFarrowing
        };
    }

    if (expectedCheck && daysToCheck !== null && daysToCheck >= 0 && daysToCheck <= 7 && (!checkResult || checkResult === "pending")) {
        return {
            section: "check_soon",
            actionText: "Pregnancy check soon",
            actionClass: "neutral-text",
            actionPriority: 5,
            sortDate: expectedCheck
        };
    }

    return {
        section: "open",
        actionText: "No movement needed yet",
        actionClass: "good-text",
        actionPriority: 6,
        sortDate: expectedCheck || expectedFarrowing || parseDate(record.mating_date)
    };
}

function buildMovementGuidance(record, sowPen) {
    if (record.is_overdue_farrowing === "Yes") {
        if (!record.linked_litter_id && !record.actual_farrowing_date) {
            return `Sow is ${Math.abs(daysBetween(startOfDay(new Date()), parseDate(record.expected_farrowing_date || record.expected_farrowing_window_end)) || 0)} days past the expected farrowing ${record.expected_farrowing_date ? "date" : "window"} with no litter recorded. Check whether she has farrowed or if reproductive-status review is needed. Current sow pen: ${sowPen}.`;
        }
        return `Overdue farrowing. Check sow and record the litter if she has farrowed. Current sow pen: ${sowPen}.`;
    }

    if (record.is_overdue_check === "Yes") {
        return `Pregnancy check is overdue. Check result before planning farrowing movement. Current sow pen: ${sowPen}.`;
    }

    if (record.action_section === "move_soon") {
        const expected = record.expected_farrowing_date || ((record.expected_farrowing_window_start && record.expected_farrowing_window_end)
            ? `${record.expected_farrowing_window_start}–${record.expected_farrowing_window_end} (exposure-derived window; exact service unknown)`
            : "unknown");
        return `Prepare farrowing pen. Expected farrowing: ${expected}. Current sow pen: ${sowPen}.`;
    }

    if (record.action_section === "check_soon") {
        return `Pregnancy check is coming up on ${record.expected_pregnancy_check_date || "the expected check date"}.`;
    }

    if (record.linked_litter_id) {
        return `Litter ${record.linked_litter_id} is linked. No movement action shown here.`;
    }

    return `Review only. Sow is currently in ${sowPen}.`;
}

function countSections(records) {
    return SECTION_DEFINITIONS.reduce((counts, section) => {
        counts[section.id] = records.filter(record => record.action_section === section.id).length;
        return counts;
    }, {});
}

function getVisibleRecords() {
    return allMatingRecords.filter(record => {
        if (selectedSowId && record.sow_pig_id !== selectedSowId) return false;
        if (selectedSectionId && record.action_section !== selectedSectionId) return false;
        return true;
    });
}

function getSowOptions(records) {
    const sowMap = new Map();

    records.forEach(record => {
        if (!record.sow_pig_id) return;

        const label = record.sow_tag_number || record.sow_pig_id;

        sowMap.set(record.sow_pig_id, {
            sow_pig_id: record.sow_pig_id,
            label
        });
    });

    return Array.from(sowMap.values()).sort((a, b) => a.label.localeCompare(b.label));
}

function compareMatingRecords(a, b) {
    if (a.action_section === "needs_action" && b.action_section === "needs_action") {
        const priorityCompare = Number(a.action_priority || 99) - Number(b.action_priority || 99);
        if (priorityCompare !== 0) return priorityCompare;
        return compareByActionDate(a, b, "asc");
    }

    if (a.action_section === "closed" && b.action_section === "closed") {
        return compareByActionDate(a, b, "desc");
    }

    return compareByActionDate(a, b, "asc");
}

function compareByActionDate(a, b, direction = "asc") {
    const aDate = a.sort_date ? a.sort_date.getTime() : Number.MAX_SAFE_INTEGER;
    const bDate = b.sort_date ? b.sort_date.getTime() : Number.MAX_SAFE_INTEGER;

    if (aDate !== bDate) {
        return direction === "desc" ? bDate - aDate : aDate - bDate;
    }

    return String(a.sow_tag_number || a.sow_pig_id || "").localeCompare(String(b.sow_tag_number || b.sow_pig_id || ""));
}

function parseDate(value) {
    if (!value) return null;

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return null;

    return startOfDay(parsed);
}

function startOfDay(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function daysBetween(start, end) {
    if (!start || !end) return null;
    return Math.round((end.getTime() - start.getTime()) / 86400000);
}

function formatAnimalLabel(tagNumber, pigId, fallback) {
    const tag = tagNumber || "";
    const id = pigId || "";

    if (tag && id) return `${escapeHtml(tag)} (${escapeHtml(id)})`;
    if (tag) return escapeHtml(tag);
    if (id) return escapeHtml(id);
    return fallback;
}

function renderPigLink(pigId, tagNumber) {
    if (!pigId) return "";

    const label = tagNumber || pigId;
    return `<a class="detail-link" href="${withReturnContext(`/pig/${encodeURIComponent(pigId)}`, "/matings", "Back to Breeding Board")}">${escapeHtml(label)}</a>`;
}

function withReturnContext(path, returnTo, returnLabel) {
    const params = new URLSearchParams({
        return_to: returnTo,
        return_label: returnLabel
    });
    return `${path}${path.includes("?") ? "&" : "?"}${params.toString()}`;
}

function formatPen(penName, penId) {
    if (penName && penId) return `${penName} (${penId})`;
    return penName || penId || "Unknown";
}

function escapeHtml(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
