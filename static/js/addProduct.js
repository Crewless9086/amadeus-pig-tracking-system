document.addEventListener("DOMContentLoaded", function () {
  setupProductFormSubmit();
});

function setupProductFormSubmit() {
  const form = document.getElementById("addProductForm");
  const messageBox = document.getElementById("add_product_message");

  if (!form) return;

  form.addEventListener("submit", async function (e) {
      e.preventDefault();

      const formData = new FormData(form);

      const payload = {
          product_name: formData.get("product_name") || "",
          product_category: formData.get("product_category") || "",
          default_dose: formData.get("default_dose") || "",
          dose_unit: formData.get("dose_unit") || "",
          default_withdrawal_days: formData.get("default_withdrawal_days") || "",
          supplier: formData.get("supplier") || "",
          batch_tracking_required: formData.get("batch_tracking_required") || "No",
          is_active: formData.get("is_active") || "Yes",
          product_notes: formData.get("product_notes") || ""
      };

      try {
          const response = await fetch("/api/pig-weights/master/products", {
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
              messageBox.textContent = "Product saved successfully.";

              form.reset();

              document.querySelector('input[name="batch_tracking_required"][value="No"]').checked = true;
              document.querySelector('input[name="is_active"][value="Yes"]').checked = true;
          } else {
              messageBox.classList.add("message-error");
              messageBox.textContent = (result.errors || ["Failed to save product."]).join(" ");
          }
      } catch (error) {
          console.error("Save product error:", error);

          messageBox.classList.remove("hidden", "message-success", "message-error");
          messageBox.classList.add("message-error");
          messageBox.textContent = "Failed to save product.";
      }
  });
}