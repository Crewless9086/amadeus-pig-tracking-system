document.addEventListener("DOMContentLoaded", function () {
    loadLitterFormOptions();
    loadPenOptions();
    loadMatingOptions();
    setupLitterFormSubmit();
});

async function loadMatingOptions() {
    try {
        const response = await fetch("/api/pig-weights/matings");
        const data = await response.json();

        const select = document.getElementById("mating_id");
        if (!select) return;

        select.innerHTML = `<option value="">Manual Entry</option>`;

        (data.records || []).forEach(item => {
            if (item.is_open !== "Yes") return;

            const option = document.createElement("option");
            option.value = item.mating_id;
            option.textContent = `${item.sow_tag_number || "Unknown Sow"} × ${item.boar_tag_number || "Unknown Boar"} (${item.mating_date || ""})`;

            option.dataset.sow = item.sow_pig_id || "";
            option.dataset.boar = item.boar_pig_id || "";
            option.dataset.farrow = item.expected_farrowing_date || "";

            select.appendChild(option);
        });

        select.addEventListener("change", handleMatingSelect);
    } catch (error) {
        console.error("Error loading mating options:", error);
    }
}

function handleMatingSelect(e) {
    const selected = e.target.selectedOptions[0];

    if (!selected || !selected.value) {
        return;
    }

    const motherSelect = document.getElementById("mother_pig_id");
    const fatherSelect = document.getElementById("father_pig_id");
    const farrowingDate = document.getElementById("farrowing_date");

    if (motherSelect) {
        motherSelect.value = selected.dataset.sow || "";
        handleMotherPenSuggestion();
    }

    if (fatherSelect) fatherSelect.value = selected.dataset.boar || "";
    if (farrowingDate) farrowingDate.value = selected.dataset.farrow || "";
}

async function loadLitterFormOptions() {
    try {
        const response = await fetch("/api/pig-weights/parent-options");
        const data = await response.json();

        const motherSelect = document.getElementById("mother_pig_id");
        const fatherSelect = document.getElementById("father_pig_id");

        if (!motherSelect || !fatherSelect) return;

        motherSelect.innerHTML = `<option value="">Select mother</option>`;
        fatherSelect.innerHTML = `<option value="">Unknown</option>`;

        (data.options?.mothers || []).forEach(item => {
            if (item.pig_id === "Unknown") return;

            const option = document.createElement("option");
            option.value = item.pig_id;
            option.textContent = `${item.tag_number} (${item.pig_id})`;
            option.dataset.currentPenId = item.current_pen_id || "";
            motherSelect.appendChild(option);
        });

        (data.options?.fathers || []).forEach(item => {
            if (item.pig_id === "Unknown") return;

            const option = document.createElement("option");
            option.value = item.pig_id;
            option.textContent = `${item.tag_number} (${item.pig_id})`;
            fatherSelect.appendChild(option);
        });

        motherSelect.addEventListener("change", handleMotherPenSuggestion);
    } catch (error) {
        console.error("Error loading litter form options:", error);
    }
}

async function loadPenOptions() {
    try {
        const response = await fetch("/api/pig-weights/pens");
        const data = await response.json();

        const penSelect = document.getElementById("current_pen_id");
        if (!penSelect) return;

        penSelect.innerHTML = `<option value="">Select pen</option>`;

        (data.pens || []).forEach(item => {
            const option = document.createElement("option");
            option.value = item.pen_id || "";
            option.textContent = item.pen_name
                ? `${item.pen_name} (${item.pen_id})`
                : (item.pen_id || "");
            penSelect.appendChild(option);
        });
    } catch (error) {
        console.error("Error loading pen options:", error);
    }
}

function handleMotherPenSuggestion() {
    const motherSelect = document.getElementById("mother_pig_id");
    const penSelect = document.getElementById("current_pen_id");

    if (!motherSelect || !penSelect) return;

    const selected = motherSelect.selectedOptions[0];
    if (!selected) return;

    const suggestedPenId = selected.dataset.currentPenId || "";
    if (!suggestedPenId) return;

    penSelect.value = suggestedPenId;
}

function setupLitterFormSubmit() {
    const form = document.getElementById("addLitterForm");
    const messageBox = document.getElementById("add_litter_message");

    if (!form || !messageBox) return;

    form.addEventListener("submit", async function (e) {
        e.preventDefault();

        const formData = new FormData(form);

        const payload = {
            mating_id: formData.get("mating_id") || "",
            mother_pig_id: formData.get("mother_pig_id") || "",
            father_pig_id: formData.get("father_pig_id") || "",
            farrowing_date: formData.get("farrowing_date") || "",
            total_born: formData.get("total_born") || "",
            born_alive: formData.get("born_alive") || "",
            stillborn_count: formData.get("stillborn_count") || "",
            mummified_count: formData.get("mummified_count") || "",
            male_count: formData.get("male_count") || "",
            female_count: formData.get("female_count") || "",
            fostered_in_count: formData.get("fostered_in_count") || "",
            fostered_out_count: formData.get("fostered_out_count") || "",
            weaned_count: formData.get("weaned_count") || "",
            wean_date: formData.get("wean_date") || "",
            average_wean_weight_kg: formData.get("average_wean_weight_kg") || "",
            notes: formData.get("notes") || "",
            current_pen_id: formData.get("current_pen_id") || ""
        };

        try {
            const response = await fetch("/api/pig-weights/master/litters", {
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

                const pigRowsCreated = Number(result.pig_rows_created || 0);
                if (pigRowsCreated > 0) {
                    messageBox.textContent = `Litter saved successfully. ${pigRowsCreated} pig rows created in PIG_MASTER.`;
                } else {
                    messageBox.textContent = "Litter saved successfully.";
                }

                form.reset();

                const matingField = document.getElementById("mating_id");
                const fatherField = document.getElementById("father_pig_id");
                const penField = document.getElementById("current_pen_id");

                if (matingField) matingField.value = "";
                if (fatherField) fatherField.value = "";
                if (penField) penField.value = "";
            } else {
                messageBox.classList.add("message-error");
                messageBox.textContent = (result.errors || ["Failed to save litter."]).join(" ");
            }
        } catch (error) {
            console.error("Save litter error:", error);

            messageBox.classList.remove("hidden", "message-success", "message-error");
            messageBox.classList.add("message-error");
            messageBox.textContent = "Failed to save litter.";
        }
    });
}