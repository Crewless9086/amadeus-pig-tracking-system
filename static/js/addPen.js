document.addEventListener("DOMContentLoaded", function () {
  setupPenFormSubmit();
});

function setupPenFormSubmit() {
  const form = document.getElementById("addPenForm");
  const messageBox = document.getElementById("add_pen_message");

  if (!form) return;

  form.addEventListener("submit", async function (e) {
      e.preventDefault();

      const formData = new FormData(form);

      const payload = {
          pen_name: formData.get("pen_name") || "",
          pen_type: formData.get("pen_type") || "",
          capacity: formData.get("capacity") || "",
          is_active: formData.get("is_active") || "Yes",
          pen_notes: formData.get("pen_notes") || ""
      };

      try {
          const response = await fetch("/api/pig-weights/master/pens", {
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
              messageBox.textContent = "Pen saved successfully.";

              form.reset();
              document.querySelector('input[name="is_active"][value="Yes"]').checked = true;
          } else {
              messageBox.classList.add("message-error");
              messageBox.textContent = (result.errors || ["Failed to save pen."]).join(" ");
          }
      } catch (error) {
          console.error("Save pen error:", error);

          messageBox.classList.remove("hidden", "message-success", "message-error");
          messageBox.classList.add("message-error");
          messageBox.textContent = "Failed to save pen.";
      }
  });
}