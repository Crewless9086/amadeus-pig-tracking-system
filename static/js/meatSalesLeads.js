(() => {
  const state = {
    leads: [],
    selectedLeadId: "",
    contract: null,
    draft: null,
    messageApproved: false,
  };

  const byId = (id) => document.getElementById(id);

  const elements = {
    message: byId("meat_leads_message"),
    list: byId("meat_leads_list"),
    count: byId("meat_leads_count"),
    refresh: byId("meat_leads_refresh"),
    openCount: byId("meat_leads_open_count"),
    needPriceCount: byId("meat_leads_need_price_count"),
    readyCount: byId("meat_leads_ready_count"),
    sentCount: byId("meat_leads_sent_count"),
    detailTitle: byId("meat_lead_detail_title"),
    detailStatus: byId("meat_lead_detail_status"),
    facts: byId("meat_lead_facts"),
    form: byId("meat_lead_approval_form"),
    pricePerKg: byId("meat_lead_price_per_kg"),
    availableWeek: byId("meat_lead_available_week"),
    weightSize: byId("meat_lead_weight_size"),
    depositRule: byId("meat_lead_deposit_rule"),
    paymentMethod: byId("meat_lead_payment_method"),
    deliveryCollection: byId("meat_lead_delivery_collection"),
    ownerApproval: byId("meat_lead_owner_approval"),
    approveDetails: byId("meat_lead_approve_details"),
    buildPreview: byId("meat_lead_build_preview"),
    preview: byId("meat_lead_message_preview"),
    approveMessage: byId("meat_lead_approve_message"),
    sendMessage: byId("meat_lead_send_message"),
    sendStatus: byId("meat_lead_send_status"),
    customerConfirmation: byId("meat_lead_customer_confirmation"),
    recordCustomerYes: byId("meat_lead_record_customer_yes"),
    createDraftOrder: byId("meat_lead_create_draft_order"),
    orderStatus: byId("meat_lead_order_status"),
    events: byId("meat_lead_events"),
  };

  const safe = (value, fallback = "--") => {
    const text = String(value || "").trim();
    return text || fallback;
  };

  const interestOf = (lead) => (lead && typeof lead.interest === "object" && lead.interest ? lead.interest : {});

  const eventNotesOf = (event) => {
    if (!event || typeof event.notes !== "object" || !event.notes) return {};
    return event.notes;
  };

  const hasEvent = (lead, type) => {
    const events = Array.isArray(lead?.events) ? lead.events : [];
    return events.some((event) => event.event_type === type);
  };

  const latestEventType = (lead) => safe(lead?.latest_event?.event_type, "");

  const leadEvents = () => {
    const lead = state.contract?.lead || {};
    return Array.isArray(lead.events) ? lead.events : [];
  };

  const hasLoadedEvent = (type) => leadEvents().some((event) => event.event_type === type);

  const latestDraftOrderEvent = () => {
    const events = leadEvents();
    for (let index = events.length - 1; index >= 0; index -= 1) {
      const event = events[index];
      if (event.event_type !== "draft_order_created") continue;
      const notes = typeof event.notes === "object" && event.notes ? event.notes : {};
      if (notes.order_id) return notes;
    }
    return {};
  };

  const setMessage = (text, tone = "") => {
    elements.message.textContent = text || "";
    elements.message.classList.toggle("hidden", !text);
    elements.message.dataset.tone = tone;
  };

  const setBusy = (busy) => {
    [
      elements.refresh,
      elements.approveDetails,
      elements.buildPreview,
      elements.approveMessage,
      elements.sendMessage,
      elements.recordCustomerYes,
      elements.createDraftOrder,
    ].forEach((button) => {
      if (button) button.disabled = busy;
    });
  };

  const approvalInputs = () => [
    elements.pricePerKg,
    elements.availableWeek,
    elements.weightSize,
    elements.depositRule,
    elements.paymentMethod,
    elements.deliveryCollection,
    elements.ownerApproval,
    elements.customerConfirmation,
  ];

  const setDetailEnabled = (enabled) => {
    approvalInputs().forEach((input) => {
      if (input) input.disabled = !enabled;
    });
    elements.preview.disabled = !enabled;
  };

  const clearDetailFields = () => {
    approvalInputs().forEach((input) => {
      if (input) input.value = "";
    });
    elements.preview.value = "";
    elements.orderStatus.textContent = "Draft order only. No pig reservation or stock change.";
  };

  const fetchJson = async (url, options = {}) => {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
      const error = new Error(payload.status || `Request failed: ${response.status}`);
      error.payload = payload;
      error.status = response.status;
      throw error;
    }
    return payload;
  };

  const renderSummary = () => {
    const openLeads = state.leads.filter((lead) => !["closed", "not_interested"].includes(lead.status));
    const needOwner = state.leads.filter((lead) => ![
      "owner_money_path_approved",
      "owner_customer_followup_send_approved",
      "customer_followup_sent",
    ].includes(latestEventType(lead)));
    const readyToSend = state.leads.filter((lead) => latestEventType(lead) === "owner_customer_followup_send_approved");
    const sent = state.leads.filter((lead) => latestEventType(lead) === "customer_followup_sent");
    elements.openCount.textContent = String(openLeads.length);
    elements.needPriceCount.textContent = String(needOwner.length);
    elements.readyCount.textContent = String(readyToSend.length);
    elements.sentCount.textContent = String(sent.length);
  };

  const leadSummaryText = (lead) => {
    const interest = interestOf(lead);
    return [
      safe(interest.product || interest.product_type, "Product pending"),
      safe(interest.cut_set, "Cut pending"),
      safe(interest.location, "Area pending"),
    ].join(" / ");
  };

  const renderLeadList = () => {
    elements.list.innerHTML = "";
    elements.count.textContent = `${state.leads.length} lead${state.leads.length === 1 ? "" : "s"} loaded`;
    if (!state.leads.length) {
      elements.list.innerHTML = '<div class="table-empty">No active meat leads found.</div>';
      return;
    }
    state.leads.forEach((lead) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "meat-lead-row";
      button.classList.toggle("is-selected", lead.lead_id === state.selectedLeadId);
      button.dataset.leadId = lead.lead_id;
      button.innerHTML = `
        <strong>${safe(lead.contact_label || lead.lead_label, "Unknown buyer")}</strong>
        <span>${leadSummaryText(lead)}</span>
        <small>${safe(lead.status)} / ${safe(lead.whatsapp_window_state, "window unknown")}</small>
      `;
      button.addEventListener("click", () => selectLead(lead.lead_id));
      elements.list.appendChild(button);
    });
  };

  const renderFacts = (lead, contract) => {
    const interest = interestOf(lead);
    const missing = Array.isArray(contract?.missing_fields) ? contract.missing_fields : [];
    const facts = [
      ["Product", interest.product || interest.product_type],
      ["Cut", interest.cut_set],
      ["Area", interest.location],
      ["Timing", interest.timing],
      ["Delivery", interest.delivery_or_collection],
      ["Payment", interest.payment_method],
      ["Missing", missing.length ? missing.join(", ") : "None"],
      ["Window", lead.whatsapp_window_state],
    ];
    elements.facts.innerHTML = facts.map(([label, value]) => `
      <div class="meat-lead-fact">
        <span>${label}</span>
        <strong>${safe(value)}</strong>
      </div>
    `).join("");
  };

  const renderEvents = (lead) => {
    const events = Array.isArray(lead?.events) ? lead.events.slice().reverse() : [];
    elements.events.innerHTML = "";
    if (!events.length) {
      elements.events.innerHTML = '<div class="table-empty">No lead history yet.</div>';
      return;
    }
    events.forEach((event) => {
      const notes = eventNotesOf(event);
      const item = document.createElement("div");
      item.className = "ops-list-item";
      item.innerHTML = `
        <strong>${safe(event.event_type)}</strong>
        <small>${safe(event.created_at || notes.created_at, "")} ${safe(event.recorded_by, "")}</small>
      `;
      elements.events.appendChild(item);
    });
  };

  const renderDetail = () => {
    const lead = state.contract?.lead || state.leads.find((item) => item.lead_id === state.selectedLeadId) || {};
    const contract = state.contract?.contract || {};
    const interest = interestOf(lead);
    const hasLead = Boolean(state.selectedLeadId);
    const hasLoadedContract = hasLead && Boolean(state.contract?.lead);

    elements.detailTitle.textContent = hasLead
      ? safe(lead.contact_label || lead.lead_label, "Loading lead...")
      : "Select a lead";
    elements.detailStatus.textContent = hasLead
      ? `${safe(lead.status)} / ${safe(contract.contract_status, "contract pending")}`
      : "Lead details will show here.";
    renderFacts(lead, contract);
    renderEvents(lead);

    if (!hasLoadedContract) {
      clearDetailFields();
      setDetailEnabled(false);
      elements.approveDetails.disabled = true;
      elements.buildPreview.disabled = true;
      elements.approveMessage.disabled = true;
      elements.sendMessage.disabled = true;
      elements.recordCustomerYes.disabled = true;
      elements.createDraftOrder.disabled = true;
      return;
    }

    setDetailEnabled(true);
    elements.pricePerKg.value = safe(interest.price_per_kg, "");
    elements.availableWeek.value = safe(interest.timing, "");
    elements.weightSize.value = safe(interest.estimated_weight_or_size, "");
    elements.depositRule.value = safe(interest.deposit_rule, "");
    elements.paymentMethod.value = safe(interest.payment_method, "");
    elements.deliveryCollection.value = safe(interest.delivery_or_collection, "");
    elements.ownerApproval.value = "Yes";

    elements.approveDetails.disabled = !hasLead;
    elements.buildPreview.disabled = !hasLead;
    elements.approveMessage.disabled = !hasLead || !elements.preview.value.trim();
    elements.sendMessage.disabled = !hasLead || !elements.preview.value.trim() || !state.messageApproved;
    elements.recordCustomerYes.disabled = !hasLoadedContract || !elements.customerConfirmation.value.trim();
    elements.createDraftOrder.disabled = !hasLoadedContract || !hasLoadedEvent("customer_booking_confirmed");

    const draftOrder = latestDraftOrderEvent();
    if (draftOrder.order_id) {
      elements.orderStatus.innerHTML = `Draft order created: <a href="/orders/${encodeURIComponent(draftOrder.order_id)}">${draftOrder.order_id}</a>`;
      elements.createDraftOrder.disabled = true;
    }
  };

  const loadLeads = async () => {
    setBusy(true);
    setMessage("");
    try {
      const payload = await fetchJson("/api/sales/meat-leads?limit=50&status=launch_test");
      state.leads = Array.isArray(payload.sales_leads) ? payload.sales_leads : [];
      if (!state.selectedLeadId && state.leads.length) state.selectedLeadId = state.leads[0].lead_id;
      renderSummary();
      renderLeadList();
      if (state.selectedLeadId) await loadLeadDetail(state.selectedLeadId);
    } catch (error) {
      setMessage(`Could not load meat leads: ${error.message}`, "error");
      elements.list.innerHTML = '<div class="table-empty">Meat leads could not be loaded.</div>';
    } finally {
      setBusy(false);
      renderDetail();
    }
  };

  async function loadLeadDetail(leadId) {
    state.contract = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(leadId)}/contract`);
    state.draft = null;
    state.messageApproved = false;
    elements.preview.value = "";
    elements.customerConfirmation.value = "";
    elements.sendStatus.textContent = "No order, quote, or stock change is made from this page.";
    elements.orderStatus.textContent = "Draft order only. No pig reservation or stock change.";
    renderDetail();
  }

  async function selectLead(leadId) {
    state.selectedLeadId = leadId;
    renderLeadList();
    setBusy(true);
    setMessage("");
    try {
      await loadLeadDetail(leadId);
    } catch (error) {
      setMessage(`Could not load lead details: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
    }
  }

  const approvalPayload = () => ({
    price_per_kg: elements.pricePerKg.value.trim(),
    available_week: elements.availableWeek.value.trim(),
    estimated_weight_or_size: elements.weightSize.value.trim(),
    deposit_rule: elements.depositRule.value.trim(),
    payment_method: elements.paymentMethod.value.trim(),
    delivery_or_collection: elements.deliveryCollection.value.trim(),
    owner_final_approval: elements.ownerApproval.value.trim(),
    recorded_by: "Farm App",
  });

  const approveDetails = async (event) => {
    event.preventDefault();
    if (!state.selectedLeadId) return;
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/owner-money-path-approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(approvalPayload()),
      });
      await loadLeadDetail(state.selectedLeadId);
      setMessage("Details approved. Build the preview next.", "success");
    } catch (error) {
      const missing = Array.isArray(error.payload?.missing_fields) ? ` Missing: ${error.payload.missing_fields.join(", ")}.` : "";
      setMessage(`Could not approve details: ${error.message}.${missing}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
    }
  };

  const buildPreview = async () => {
    if (!state.selectedLeadId) return;
    setBusy(true);
    setMessage("");
    try {
      const payload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/customer-followup-draft`);
      state.draft = payload.customer_followup_draft || {};
      elements.preview.value = safe(state.draft.message || state.draft.text, "");
      state.messageApproved = false;
      elements.sendStatus.textContent = "Preview built. Approve the exact message before sending.";
    } catch (error) {
      setMessage(`Could not build preview: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
    }
  };

  const approveMessage = async () => {
    const message = elements.preview.value.trim();
    if (!state.selectedLeadId || !message) return;
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/customer-followup-send-approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          approved_by: "Farm App",
          owner_final_send_approval: "Approved in Farm App",
        }),
      });
      state.messageApproved = true;
      elements.sendStatus.textContent = "Message approved. Chatwoot send is unlocked for this exact text.";
      setMessage("Message approved.", "success");
    } catch (error) {
      setMessage(`Could not approve message: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
    }
  };

  const sendMessage = async () => {
    const message = elements.preview.value.trim();
    if (!state.selectedLeadId || !message || !state.messageApproved) return;
    setBusy(true);
    setMessage("");
    try {
      const payload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/customer-followup-send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      elements.sendStatus.textContent = payload.sent
        ? `Sent via Chatwoot. Message ID: ${safe(payload.chatwoot_message_id || payload.message_id, "")}`
        : safe(payload.status, "Send skipped.");
      await loadLeadDetail(state.selectedLeadId);
      setMessage("Chatwoot follow-up handled.", "success");
    } catch (error) {
      setMessage(`Could not send through Chatwoot: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
    }
  };

  const recordCustomerYes = async () => {
    const customerConfirmation = elements.customerConfirmation.value.trim();
    if (!state.selectedLeadId || !customerConfirmation) return;
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/customer-booking-confirmation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_confirmation: customerConfirmation,
          confirmed_by: "Farm App",
          confirmation_channel: "chatwoot",
        }),
      });
      await loadLeadDetail(state.selectedLeadId);
      elements.orderStatus.textContent = "Customer yes recorded. Draft order can now be created.";
      setMessage("Customer booking confirmation recorded.", "success");
    } catch (error) {
      setMessage(`Could not record customer yes: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
    }
  };

  const createDraftOrder = async () => {
    if (!state.selectedLeadId) return;
    setBusy(true);
    setMessage("");
    try {
      const payload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/draft-order`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ created_by: "Farm App" }),
      });
      elements.orderStatus.innerHTML = payload.order_id
        ? `Draft order created: <a href="/orders/${encodeURIComponent(payload.order_id)}">${payload.order_id}</a>`
        : safe(payload.status, "Draft order handled.");
      await loadLeadDetail(state.selectedLeadId);
      setMessage("Draft order created.", "success");
    } catch (error) {
      setMessage(`Could not create draft order: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
    }
  };

  elements.refresh.addEventListener("click", loadLeads);
  elements.form.addEventListener("submit", approveDetails);
  elements.buildPreview.addEventListener("click", buildPreview);
  elements.approveMessage.addEventListener("click", approveMessage);
  elements.sendMessage.addEventListener("click", sendMessage);
  elements.customerConfirmation.addEventListener("input", renderDetail);
  elements.recordCustomerYes.addEventListener("click", recordCustomerYes);
  elements.createDraftOrder.addEventListener("click", createDraftOrder);

  clearDetailFields();
  setDetailEnabled(false);
  renderDetail();
  loadLeads();
})();
