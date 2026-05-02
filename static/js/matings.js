document.addEventListener("DOMContentLoaded", function () {
    setupMatingBoardEvents();
    loadMatingBoard();
});

let allMatingRecords = [];
let allPens = [];
let selectedSowId = "";
let activeAssumePregnantId = null;
const expandedMatingIds = new Set();

const SECTION_DEFINITIONS = [
    {
        id: "needs_action",
        title: "Needs Action Now",
        description: "Overdue pregnancy checks, overdue farrowing, or records needing a decision."
    },
    {
        id: "move_soon",
        title: "Move Soon / Prepare",
        description: "Open or pregnant sows approaching expected farrowing."
    },
    {
        id: "check_soon",
        title: "Upcoming Pregnancy Checks",
        description: "Open matings approaching the pregnancy check window."
    },
    {
        id: "open",
        title: "All Open Matings",
        description: "Other active breeding records still in progress."
    },
    {
        id: "closed",
        title: "Closed / Farrowed",
        description: "Completed, not pregnant, or linked litter records."
    }
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

        allMatingRecords = (data.records || []).map(record => {
            const classification = classifyMating(record);
            return {
                ...record,
                action_section: classification.section,
                action_text: classification.actionText,
                action_class: classification.actionClass,
                sort_date: classification.sortDate
            };
        });

        renderSummary(summary, allMatingRecords);
        renderControls(controls, allMatingRecords);
        renderBoard(board, getVisibleRecords());
    } catch (error) {
        console.error("Matings load error:", error);
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
        renderBoard(document.getElementById("matings_board"), getVisibleRecords());
        renderControls(document.getElementById("mating_controls"), allMatingRecords);
    });

    document.addEventListener("click", async function (event) {
        const cardToggle = event.target.closest("[data-mating-toggle]");
        if (cardToggle) {
            const matingId = cardToggle.getAttribute("data-mating-toggle");
            if (expandedMatingIds.has(matingId)) {
                expandedMatingIds.delete(matingId);
                if (activeAssumePregnantId === matingId) activeAssumePregnantId = null;
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

        if (event.target.id !== "toggle_all_mating_details") return;

        const visibleRecords = getVisibleRecords();
        const allVisibleExpanded = visibleRecords.length > 0 && visibleRecords.every(record => expandedMatingIds.has(record.mating_id));

        if (allVisibleExpanded) {
            visibleRecords.forEach(record => expandedMatingIds.delete(record.mating_id));
            activeAssumePregnantId = null;
        } else {
            visibleRecords.forEach(record => expandedMatingIds.add(record.mating_id));
        }

        renderBoard(document.getElementById("matings_board"), visibleRecords);
        renderControls(document.getElementById("mating_controls"), allMatingRecords);
    });
}

async function handleAssumePregnant(matingId) {
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

function renderSummary(container, records) {
    const counts = countSections(records);
    const openCount = records.filter(record => record.is_open === "Yes").length;

    container.innerHTML = `
        <div class="info-card">
          <div class="info-title">Needs Action</div>
          <div class="info-value ${counts.needs_action > 0 ? "bad-text" : "good-text"}">${counts.needs_action}</div>
        </div>
        <div class="info-card">
          <div class="info-title">Move Soon / Prepare</div>
          <div class="info-value ${counts.move_soon > 0 ? "neutral-text" : "good-text"}">${counts.move_soon}</div>
        </div>
        <div class="info-card">
          <div class="info-title">Upcoming Checks</div>
          <div class="info-value">${counts.check_soon}</div>
        </div>
        <div class="info-card">
          <div class="info-title">Open Matings</div>
          <div class="info-value">${openCount}</div>
        </div>
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
            <label for="mating_sow_filter">Filter by sow</label>
            <select id="mating_sow_filter" name="mating_sow_filter">
              <option value="">All sows</option>
              ${sowOptions}
            </select>
          </div>
          <div class="form-group">
            <label>Card details</label>
            <button id="toggle_all_mating_details" type="button" class="button-link">
              ${allVisibleExpanded ? "Hide all details" : "Show all details"}
            </button>
          </div>
        </div>
        <div class="pig-list-meta">
          Showing ${visibleRecords.length} of ${records.length} mating records${selectedSowId ? " for selected sow" : ""}.
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
            .sort(compareByActionDate);

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
    const sowLabel = formatAnimalLabel(record.sow_tag_number, record.sow_pig_id, "Unknown Sow");
    const boarLabel = formatAnimalLabel(record.boar_tag_number, record.boar_pig_id, "Unknown Boar");
    const sowPen = formatPen(record.sow_current_pen_name, record.sow_current_pen_id);
    const boarPen = formatPen(record.boar_current_pen_name, record.boar_current_pen_id);
    const litterLink = record.linked_litter_id
        ? `<a class="detail-link" href="/litter/${encodeURIComponent(record.linked_litter_id)}">${escapeHtml(record.linked_litter_id)}</a>`
        : "-";

    const showAssumeButton = isEligibleForAssumePregnant(record);
    const assumeButtonHtml = showAssumeButton
        ? `<button type="button" class="button-link${isAssumeFormOpen ? " button-link-secondary" : ""}" data-assume-pregnant="${escapeHtml(record.mating_id)}">
             ${isAssumeFormOpen ? "Cancel" : "Move to Farrowing / Assume Pregnant"}
           </button>`
        : "";

    const assumeFormHtml = isAssumeFormOpen ? renderAssumePregnantForm(record.mating_id) : "";

    return `
        <div class="history-item mating-card ${isExpanded ? "mating-card-expanded" : ""}">
          <div class="history-item-top">
            <div>
              <div class="history-item-date">${sowLabel} x ${boarLabel}</div>
              <div class="pig-list-meta">Mating ID: ${escapeHtml(record.mating_id || "-")}</div>
            </div>
            <div class="mating-card-actions">
              <div class="history-item-weight ${record.action_class}">${escapeHtml(record.action_text)}</div>
              <button
                type="button"
                class="mating-toggle-button"
                data-mating-toggle="${escapeHtml(record.mating_id || "")}"
                aria-expanded="${isExpanded ? "true" : "false"}"
              >
                ${isExpanded ? "Hide details ▲" : "Show details ▼"}
              </button>
            </div>
          </div>

          <div class="history-item-grid mating-card-compact">
            <div>
              <div class="history-label">Sow</div>
              <div class="history-value">${renderPigLink(record.sow_pig_id, record.sow_tag_number)}</div>
              <div class="pig-list-meta">Pen: ${escapeHtml(sowPen)}</div>
            </div>
            <div>
              <div class="history-label">Expected Farrowing</div>
              <div class="history-value ${record.is_overdue_farrowing === "Yes" ? "bad-text" : "neutral-text"}">${escapeHtml(record.expected_farrowing_date || "-")}</div>
            </div>
            <div>
              <div class="history-label">Status / Outcome</div>
              <div class="history-value">${escapeHtml(record.mating_status || "-")} / ${escapeHtml(record.outcome || "-")}</div>
            </div>
          </div>

          <div class="mating-card-details ${isExpanded ? "" : "hidden"}">
            <div class="history-item-grid">
              <div>
                <div class="history-label">Boar</div>
                <div class="history-value">${renderPigLink(record.boar_pig_id, record.boar_tag_number) || "-"}</div>
                <div class="pig-list-meta">Pen: ${escapeHtml(boarPen)}</div>
              </div>
              <div>
                <div class="history-label">Mating Date</div>
                <div class="history-value">${escapeHtml(record.mating_date || "-")}</div>
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
    const blocked = new Set(["Farrowed", "Cancelled", "Closed"]);
    return record.is_open === "Yes"
        && !blocked.has(record.mating_status)
        && !record.linked_litter_id;
}

function classifyMating(record) {
    const isClosed = record.is_open === "No" || Boolean(record.linked_litter_id);
    const expectedFarrowing = parseDate(record.expected_farrowing_date);
    const expectedCheck = parseDate(record.expected_pregnancy_check_date);
    const checkResult = String(record.pregnancy_check_result || "").toLowerCase();
    const today = startOfDay(new Date());
    const daysToFarrowing = daysBetween(today, expectedFarrowing);
    const daysToCheck = daysBetween(today, expectedCheck);

    if (record.is_overdue_farrowing === "Yes") {
        // Feature C: no litter recorded more than 21 days past expected farrowing
        if (!record.linked_litter_id && !record.actual_farrowing_date
                && daysToFarrowing !== null && daysToFarrowing < -21) {
            return {
                section: "needs_action",
                actionText: "No litter after 3 weeks — review",
                actionClass: "bad-text",
                sortDate: expectedFarrowing
            };
        }
        return {
            section: "needs_action",
            actionText: "Overdue farrowing",
            actionClass: "bad-text",
            sortDate: expectedFarrowing
        };
    }

    if (record.is_overdue_check === "Yes") {
        return {
            section: "needs_action",
            actionText: "Check pregnancy",
            actionClass: "bad-text",
            sortDate: expectedCheck
        };
    }

    if (isClosed) {
        return {
            section: "closed",
            actionText: record.linked_litter_id ? "Litter linked" : "Closed",
            actionClass: "neutral-text",
            sortDate: expectedFarrowing || parseDate(record.mating_date)
        };
    }

    if (expectedFarrowing && daysToFarrowing !== null && daysToFarrowing >= 0 && daysToFarrowing <= 14) {
        return {
            section: "move_soon",
            actionText: "Prepare farrowing pen",
            actionClass: "neutral-text",
            sortDate: expectedFarrowing
        };
    }

    if (expectedCheck && daysToCheck !== null && daysToCheck >= 0 && daysToCheck <= 7 && (!checkResult || checkResult === "pending")) {
        return {
            section: "check_soon",
            actionText: "Pregnancy check soon",
            actionClass: "neutral-text",
            sortDate: expectedCheck
        };
    }

    return {
        section: "open",
        actionText: "No movement needed yet",
        actionClass: "good-text",
        sortDate: expectedCheck || expectedFarrowing || parseDate(record.mating_date)
    };
}

function buildMovementGuidance(record, sowPen) {
    if (record.is_overdue_farrowing === "Yes") {
        if (!record.linked_litter_id && !record.actual_farrowing_date) {
            return `Sow is ${Math.abs(daysBetween(startOfDay(new Date()), parseDate(record.expected_farrowing_date)) || 0)} days past expected farrowing with no litter recorded. Check whether she has farrowed or if repeat service is needed. Current sow pen: ${sowPen}.`;
        }
        return `Overdue farrowing. Check sow and record the litter if she has farrowed. Current sow pen: ${sowPen}.`;
    }

    if (record.is_overdue_check === "Yes") {
        return `Pregnancy check is overdue. Check result before planning farrowing movement. Current sow pen: ${sowPen}.`;
    }

    if (record.action_section === "move_soon") {
        return `Prepare farrowing pen. Expected farrowing date: ${record.expected_farrowing_date || "unknown"}. Current sow pen: ${sowPen}.`;
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
    if (!selectedSowId) return allMatingRecords;

    return allMatingRecords.filter(record => record.sow_pig_id === selectedSowId);
}

function getSowOptions(records) {
    const sowMap = new Map();

    records.forEach(record => {
        if (!record.sow_pig_id) return;

        const label = record.sow_tag_number
            ? `${record.sow_tag_number} (${record.sow_pig_id})`
            : record.sow_pig_id;

        sowMap.set(record.sow_pig_id, {
            sow_pig_id: record.sow_pig_id,
            label
        });
    });

    return Array.from(sowMap.values()).sort((a, b) => a.label.localeCompare(b.label));
}

function compareByActionDate(a, b) {
    const aDate = a.sort_date ? a.sort_date.getTime() : Number.MAX_SAFE_INTEGER;
    const bDate = b.sort_date ? b.sort_date.getTime() : Number.MAX_SAFE_INTEGER;

    if (aDate !== bDate) return aDate - bDate;

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
    return `<a class="detail-link" href="/pig/${encodeURIComponent(pigId)}">${escapeHtml(label)}</a>`;
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
