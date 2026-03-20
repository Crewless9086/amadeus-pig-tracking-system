document.addEventListener("DOMContentLoaded", function () {
    loadFormOptions();
    setupFormSubmit();
});

async function loadFormOptions() {
    try {
        const parentRes = await fetch("/api/pig-weights/parent-options");
        const parentData = await parentRes.json();

        const penRes = await fetch("/api/pig-weights/pens");
        const penData = await penRes.json();

        populateParentSelect("mother", parentData.options?.mothers || []);
        populateParentSelect("father", parentData.options?.fathers || []);
        populatePenSelect("current_pen_id", penData.pens || []);
    } catch (error) {
        console.error("Error loading form options:", error);
    }
}

function populateParentSelect(elementId, items) {
    const select = document.getElementById(elementId);
    if (!select) return;

    select.innerHTML = `<option value="Unknown">Unknown</option>`;

    items.forEach(item => {
        if (item.pig_id === "Unknown") return;

        const option = document.createElement("option");
        option.value = item.pig_id;
        option.textContent = `${item.tag_number} (${item.pig_id})`;
        select.appendChild(option);
    });
}

function populatePenSelect(elementId, items) {
    const select = document.getElementById(elementId);
    if (!select) return;

    select.innerHTML = `<option value="">Select pen</option>`;

    items.forEach(item => {
        const option = document.createElement("option");
        option.value = item.pen_id;
        option.textContent = `${item.pen_name} (${item.pen_id})`;
        select.appendChild(option);
    });
}

function setupFormSubmit() {
    const form = document.getElementById("addPigForm");
    const messageBox = document.getElementById("add_pig_message");

    if (!form) return;

    form.addEventListener("submit", async function (e) {
        e.preventDefault();

        const formData = new FormData(form);

        const payload = {
            tag_number: formData.get("tag_number") || "",
            pig_name: formData.get("pig_name") || "",
            status: formData.get("status") || "",
            on_farm: formData.get("on_farm") || "Yes",
            animal_type: formData.get("animal_type") || "",
            sex: formData.get("sex") || "",
            date_of_birth: formData.get("date_of_birth") || "",
            breed_type: formData.get("breed_type") || "",
            colour_markings: formData.get("colour_markings") || "",
            purpose: formData.get("purpose") || "",
            source: formData.get("source") || "",
            current_pen_id: formData.get("current_pen_id") || "",
            litter_id: formData.get("litter_id") || "Unknown",
            mother_pig_id: formData.get("mother") || "Unknown",
            father_pig_id: formData.get("father") || "Unknown",
            acquisition_date: formData.get("acquisition_date") || "",
            birth_weight_kg: formData.get("birth_weight_kg") || "",
            general_notes: formData.get("general_notes") || ""
        };

        try {
            const response = await fetch("/api/pig-weights/master/pigs", {
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
                messageBox.textContent = "Pig saved successfully.";

                form.reset();

                document.querySelector('input[name="on_farm"][value="Yes"]').checked = true;
                document.getElementById("litter_id").value = "Unknown";
                document.getElementById("mother").value = "Unknown";
                document.getElementById("father").value = "Unknown";
            } else {
                messageBox.classList.add("message-error");
                messageBox.textContent = (result.errors || ["Failed to save pig."]).join(" ");
            }
        } catch (error) {
            console.error("Save error:", error);

            messageBox.classList.remove("hidden", "message-success", "message-error");
            messageBox.classList.add("message-error");
            messageBox.textContent = "Failed to save pig.";
        }
    });
}