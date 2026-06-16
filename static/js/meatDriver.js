(() => {
  const byId = (id) => document.getElementById(id);
  const elements = {
    driver: byId("driver_name"),
    date: byId("driver_date"),
    load: byId("driver_load"),
    message: byId("driver_message"),
    route: byId("driver_route"),
  };

  const params = new URLSearchParams(window.location.search);
  elements.driver.value = params.get("driver") || "";
  elements.date.value = params.get("date") || new Date().toISOString().slice(0, 10);

  const safe = (value, fallback = "--") => {
    const text = String(value || "").trim();
    return text || fallback;
  };

  const setMessage = (text, tone = "") => {
    elements.message.textContent = text || "";
    elements.message.classList.toggle("hidden", !text);
    elements.message.dataset.tone = tone;
  };

  const fetchJson = async (url, options = {}) => {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.status || payload.error || `HTTP ${response.status}`);
      error.payload = payload;
      throw error;
    }
    return payload;
  };

  const renderStops = (stops) => {
    elements.route.innerHTML = "";
    if (!stops.length) {
      elements.route.innerHTML = '<div class="table-empty">No delivery stops for this driver/date.</div>';
      return;
    }
    stops.forEach((stop) => {
      const address = stop.address || {};
      const card = document.createElement("article");
      card.className = "driver-stop";
      card.innerHTML = `
        <header>
          <div>
            <strong>${safe(stop.location_label || address.town, "Delivery stop")}</strong>
            <p>${safe(address.address_line_1, "Address not captured")}</p>
            <small>${safe(stop.scheduled_date, "")} ${safe(stop.scheduled_window, "")}</small>
          </div>
          <small>${safe(stop.state)}</small>
        </header>
        <div class="driver-actions">
          <button type="button" class="button-link button-link-secondary" data-lead-id="${safe(stop.lead_id, "")}" data-event-type="delivery_on_way">On Way</button>
          <button type="button" class="button-link button-link-secondary" data-lead-id="${safe(stop.lead_id, "")}" data-event-type="delivery_arrived">Arrived</button>
          <button type="button" class="button-link" data-lead-id="${safe(stop.lead_id, "")}" data-event-type="delivery_completed">Delivered</button>
          <button type="button" class="button-link button-link-secondary" data-lead-id="${safe(stop.lead_id, "")}" data-event-type="delivery_failed">Issue</button>
        </div>
      `;
      elements.route.appendChild(card);
    });
  };

  const loadRoute = async () => {
    setMessage("");
    elements.load.disabled = true;
    try {
      const query = new URLSearchParams({
        driver: elements.driver.value.trim(),
        date: elements.date.value,
      });
      const payload = await fetchJson(`/api/sales/meat-deliveries/driver-route?${query.toString()}`);
      renderStops(Array.isArray(payload.stops) ? payload.stops : []);
    } catch (error) {
      setMessage(`Could not load route: ${error.message}`, "error");
    } finally {
      elements.load.disabled = false;
    }
  };

  const recordDriverEvent = async (button) => {
    const leadId = button.dataset.leadId || "";
    const eventType = button.dataset.eventType || "";
    if (!leadId || !eventType) return;
    setMessage("");
    button.disabled = true;
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(leadId)}/driver-events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_type: eventType,
          scheduled_date: elements.date.value,
          assigned_to: elements.driver.value.trim(),
          actor_label: elements.driver.value.trim() || "Driver",
          reason: eventType === "delivery_failed" ? "Driver marked delivery issue" : "",
        }),
      });
      await loadRoute();
      setMessage("Delivery update recorded.", "success");
    } catch (error) {
      setMessage(`Could not record update: ${error.message}`, "error");
    } finally {
      button.disabled = false;
    }
  };

  elements.load.addEventListener("click", loadRoute);
  elements.route.addEventListener("click", (event) => {
    const button = event.target.closest("[data-event-type]");
    if (button) recordDriverEvent(button);
  });

  loadRoute();
})();
