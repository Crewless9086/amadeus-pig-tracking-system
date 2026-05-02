document.addEventListener("DOMContentLoaded", function () {
    setTodayDate();
    loadPens().then(loadBreedingOptions);
    loadMatingList();
    setupMatingFormSubmit();
});

let allPens = [];
let sowPenMap = {};
let boarPenMap = {};

function setTodayDate() {
    const input = document.getElementById("mating_date");
    if (!input) return;
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0");
    const dd = String(today.getDate()).padStart(2, "0");
    input.value = `${yyyy}-${mm}-${dd}`;
}

async function loadPens() {
    try {
        const response = await fetch("/api/pig-weights/pens");
        const data = await response.json();
        allPens = data.pens || [];
        populatePenDropdown("sow_move_to_pen_id", allPens);
        populatePenDropdown("boar_move_to_pen_id", allPens);
    } catch (error) {
        console.error("Error loading pens:", error);
    }
}

function populatePenDropdown(selectId, pens) {
    const select = document.getElementById(selectId);
    if (!select) return;
    select.innerHTML = `<option value="">No pen change</option>`;
    pens.forEach(pen => {
        const label = pen.pen_name ? `${pen.pen_name} (${pen.pen_id})` : pen.pen_id;
        const option = document.createElement("option");
        option.value = pen.pen_id;
        option.textContent = label;
        select.appendChild(option);
    });
}

async function loadBreedingOptions() {
    try {
        const response = await fetch("/api/pig-weights/breeding-options");
        const data = await response.json();

        const sowSelect = document.getElementById("sow_pig_id");
        const boarSelect = document.getElementById("boar_pig_id");

        sowSelect.innerHTML = `<option value="">Select sow</option>`;
        boarSelect.innerHTML = `<option value="">Unknown</option>`;

        sowPenMap = {};
        boarPenMap = {};

        (data.options?.sows || []).forEach(item => {
            sowPenMap[item.pig_id] = {
                pen_id: item.current_pen_id || "",
                pen_name: item.current_pen_name || "",
            };
            const option = document.createElement("option");
            option.value = item.pig_id;
            option.textContent = `${item.tag_number} (${item.pig_id})`;
            sowSelect.appendChild(option);
        });

        (data.options?.boars || []).forEach(item => {
            boarPenMap[item.pig_id] = {
                pen_id: item.current_pen_id || "",
                pen_name: item.current_pen_name || "",
            };
            const option = document.createElement("option");
            option.value = item.pig_id;
            option.textContent = `${item.tag_number} (${item.pig_id})`;
            boarSelect.appendChild(option);
        });

        sowSelect.addEventListener("change", function () {
            updatePenInfo("sow_pen_info", "sow_move_to_pen_id", sowPenMap[this.value]);
        });

        boarSelect.addEventListener("change", function () {
            updatePenInfo("boar_pen_info", "boar_move_to_pen_id", boarPenMap[this.value]);
        });

    } catch (error) {
        console.error("Error loading breeding options:", error);
    }
}

function updatePenInfo(infoId, moveSelectId, penInfo) {
    const infoEl = document.getElementById(infoId);
    const moveSelect = document.getElementById(moveSelectId);

    if (!infoEl) return;

    if (!penInfo || !penInfo.pen_id) {
        infoEl.textContent = "";
        if (moveSelect) moveSelect.value = "";
        return;
    }

    const label = penInfo.pen_name
        ? `Current pen: ${penInfo.pen_name} (${penInfo.pen_id})`
        : `Current pen: ${penInfo.pen_id}`;
    infoEl.textContent = label;

    if (moveSelect) moveSelect.value = "";
}

async function loadMatingList() {
    const container = document.getElementById("mating_list");

    try {
        const response = await fetch("/api/pig-weights/matings");
        const data = await response.json();

        if (!response.ok || !data.success) {
            container.innerHTML = `
                <div class="empty-state">
                  <div>Could not load mating records.</div>
                </div>
            `;
            return;
        }

        const records = data.records || [];

        if (records.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                  <div>No mating records yet.</div>
                  <div>Create the first mating record above.</div>
                </div>
            `;
            return;
        }

        container.innerHTML = records.slice(0, 12).map(record => {
            const overdueCheckClass = record.is_overdue_check === "Yes" ? "bad-text" : "neutral-text";
            const overdueFarrowingClass = record.is_overdue_farrowing === "Yes" ? "bad-text" : "neutral-text";
            const openClass = record.is_open === "Yes" ? "good-text" : "neutral-text";

            return `
                <div class="history-item">
                  <div class="history-item-top">
                    <div class="history-item-date">${record.sow_tag_number || "Unknown Sow"} × ${record.boar_tag_number || "Unknown Boar"}</div>
                    <div class="history-item-weight">${record.mating_status || "Open"}</div>
                  </div>

                  <div class="history-item-grid">
                    <div>
                      <div class="history-label">Mating Date</div>
                      <div class="history-value">${record.mating_date || "-"}</div>
                    </div>
                    <div>
                      <div class="history-label">Method</div>
                      <div class="history-value">${record.mating_method || "-"}</div>
                    </div>
                    <div>
                      <div class="history-label">Expected Check</div>
                      <div class="history-value">${record.expected_pregnancy_check_date || "-"}</div>
                    </div>
                    <div>
                      <div class="history-label">Expected Farrowing</div>
                      <div class="history-value">${record.expected_farrowing_date || "-"}</div>
                    </div>
                    <div>
                      <div class="history-label">Outcome</div>
                      <div class="history-value">${record.outcome || "-"}</div>
                    </div>
                    <div>
                      <div class="history-label">Days Since Mating</div>
                      <div class="history-value">${record.days_since_mating || "-"}</div>
                    </div>
                    <div>
                      <div class="history-label">Open</div>
                      <div class="history-value ${openClass}">${record.is_open || "-"}</div>
                    </div>
                    <div>
                      <div class="history-label">Overdue Check</div>
                      <div class="history-value ${overdueCheckClass}">${record.is_overdue_check || "-"}</div>
                    </div>
                    <div>
                      <div class="history-label">Overdue Farrowing</div>
                      <div class="history-value ${overdueFarrowingClass}">${record.is_overdue_farrowing || "-"}</div>
                    </div>
                    <div>
                      <div class="history-label">Linked Litter</div>
                      <div class="history-value">${record.linked_litter_id || "-"}</div>
                    </div>
                  </div>

                  <div class="history-notes">
                    <div class="history-label">Notes</div>
                    <div>${record.service_notes || "-"}</div>
                  </div>
                </div>
            `;
        }).join("");
    } catch (error) {
        console.error("Error loading mating records:", error);

        container.innerHTML = `
            <div class="empty-state">
              <div>Could not load mating records.</div>
            </div>
        `;
    }
}

function setupMatingFormSubmit() {
    const form = document.getElementById("addMatingForm");
    const messageBox = document.getElementById("add_mating_message");

    if (!form) return;

    form.addEventListener("submit", async function (e) {
        e.preventDefault();

        const formData = new FormData(form);

        const payload = {
            sow_pig_id: formData.get("sow_pig_id") || "",
            boar_pig_id: formData.get("boar_pig_id") || "",
            mating_date: formData.get("mating_date") || "",
            mating_method: formData.get("mating_method") || "",
            exposure_group: formData.get("exposure_group") || "",
            service_notes: formData.get("service_notes") || "",
            sow_move_to_pen_id: formData.get("sow_move_to_pen_id") || "",
            boar_move_to_pen_id: formData.get("boar_move_to_pen_id") || "",
        };

        try {
            const response = await fetch("/api/pig-weights/master/matings", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            messageBox.classList.remove("hidden", "message-success", "message-error");

            if (response.ok && result.success) {
                messageBox.classList.add("message-success");
                messageBox.textContent = result.message || "Mating saved successfully.";

                form.reset();
                setTodayDate();
                document.getElementById("boar_pig_id").value = "";
                document.getElementById("sow_pen_info").textContent = "";
                document.getElementById("boar_pen_info").textContent = "";
                await loadMatingList();
            } else {
                messageBox.classList.add("message-error");
                messageBox.textContent = (result.errors || ["Failed to save mating."]).join(" ");
            }
        } catch (error) {
            console.error("Save mating error:", error);

            messageBox.classList.remove("hidden", "message-success", "message-error");
            messageBox.classList.add("message-error");
            messageBox.textContent = "Failed to save mating.";
        }
    });
}
