(() => {
  const state = {
    leads: [],
    selectedLeadId: "",
    contract: null,
    draft: null,
    messageApproved: false,
    priceEntries: [],
    pricingEstimate: null,
    meatMatch: null,
    meatOps: null,
    meatFulfillment: null,
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
    priceRefresh: byId("meat_price_refresh"),
    priceForm: byId("meat_price_form"),
    priceStatus: byId("meat_price_book_status"),
    priceProductType: byId("meat_price_product_type"),
    priceCutSet: byId("meat_price_cut_set"),
    priceAmount: byId("meat_price_amount"),
    priceUnit: byId("meat_price_unit"),
    priceList: byId("meat_price_book_list"),
    detailTitle: byId("meat_lead_detail_title"),
    detailStatus: byId("meat_lead_detail_status"),
    facts: byId("meat_lead_facts"),
    guidedStatus: byId("meat_guided_status"),
    guidedNext: byId("meat_guided_next"),
    guidedResult: byId("meat_guided_result"),
    matchStatus: byId("meat_lead_match_status"),
    matchPreference: byId("meat_match_preference"),
    matchTargetKg: byId("meat_match_target_kg"),
    matchBudget: byId("meat_match_budget"),
    buildMatch: byId("meat_lead_build_match"),
    useMatch: byId("meat_lead_use_match"),
    matchResult: byId("meat_lead_match_result"),
    opsStatus: byId("meat_ops_status"),
    reserveMatch: byId("meat_ops_reserve_match"),
    depositAmount: byId("meat_deposit_amount"),
    depositReference: byId("meat_deposit_reference"),
    recordDeposit: byId("meat_ops_record_deposit"),
    buildInstructions: byId("meat_ops_build_instructions"),
    opsResult: byId("meat_ops_result"),
    fulfillmentStatus: byId("meat_fulfillment_status"),
    fulfillmentEventType: byId("meat_fulfillment_event_type"),
    fulfillmentDate: byId("meat_fulfillment_date"),
    fulfillmentWindow: byId("meat_fulfillment_window"),
    fulfillmentLocation: byId("meat_fulfillment_location"),
    deliveryAddress: byId("meat_delivery_address"),
    deliveryTown: byId("meat_delivery_town"),
    deliveryDriver: byId("meat_delivery_driver"),
    fulfillmentNotes: byId("meat_fulfillment_notes"),
    recordFulfillment: byId("meat_fulfillment_record"),
    buildJourneyDraft: byId("meat_journey_build_draft"),
    approveJourney: byId("meat_journey_approve"),
    sendJourney: byId("meat_journey_send"),
    journeyMessage: byId("meat_journey_message"),
    fulfillmentResult: byId("meat_fulfillment_result"),
    form: byId("meat_lead_approval_form"),
    pricePerKg: byId("meat_lead_price_per_kg"),
    availableWeek: byId("meat_lead_available_week"),
    weightSize: byId("meat_lead_weight_size"),
    depositRule: byId("meat_lead_deposit_rule"),
    paymentMethod: byId("meat_lead_payment_method"),
    deliveryCollection: byId("meat_lead_delivery_collection"),
    ownerApproval: byId("meat_lead_owner_approval"),
    usePricing: byId("meat_lead_use_pricing"),
    estimateStatus: byId("meat_lead_estimate_status"),
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

  const guidedState = () => {
    const contract = state.contract?.contract || {};
    const missing = Array.isArray(contract.missing_fields) ? contract.missing_fields : [];
    const sent = hasLoadedEvent("customer_followup_sent");
    const customerYes = hasLoadedEvent("customer_booking_confirmed");
    const draftOrder = latestDraftOrderEvent();
    if (!state.selectedLeadId || !state.contract?.lead) {
      return { label: "Select a lead", detail: "Choose a lead first.", disabled: true };
    }
    if (draftOrder.order_id) {
      return { label: "Draft order created", detail: `Draft order ${draftOrder.order_id} exists.`, disabled: true };
    }
    if (customerYes) {
      return { label: "Create Draft Order", detail: "Customer confirmation is recorded. Create the draft order next.", disabled: false };
    }
    if (sent) {
      return { label: "Waiting For Customer Yes", detail: "The approved follow-up was sent. Sam/customer must confirm before an order is created.", disabled: true };
    }
    if (missing.length) {
      return {
        label: "Approve And Send Price",
        detail: `Uses active pricing rules, records owner approval, then sends the approved follow-up. Missing now: ${missing.join(", ")}.`,
        disabled: false,
      };
    }
    return { label: "Send Approved Follow-Up", detail: "Owner money path is ready. Build, approve, and send the follow-up.", disabled: false };
  };

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

  const latestReservation = () => {
    const reservations = Array.isArray(state.meatOps?.reservations) ? state.meatOps.reservations : [];
    for (let index = reservations.length - 1; index >= 0; index -= 1) {
      if (reservations[index].reservation_id) return reservations[index];
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
      elements.priceRefresh,
      elements.priceForm?.querySelector("button"),
      elements.usePricing,
      elements.guidedNext,
      elements.buildMatch,
      elements.useMatch,
      elements.reserveMatch,
      elements.recordDeposit,
      elements.buildInstructions,
      elements.recordFulfillment,
      elements.buildJourneyDraft,
      elements.approveJourney,
      elements.sendJourney,
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

  const renderPriceBook = () => {
    if (!elements.priceList) return;
    const entries = Array.isArray(state.priceEntries) ? state.priceEntries.slice(0, 8) : [];
    elements.priceList.innerHTML = "";
    elements.priceStatus.textContent = `${entries.length} latest price ${entries.length === 1 ? "entry" : "entries"} loaded. New entries become active from their effective time.`;
    if (!entries.length) {
      elements.priceList.innerHTML = '<div class="table-empty">No price entries loaded.</div>';
      return;
    }
    entries.forEach((entry) => {
      const item = document.createElement("div");
      item.className = "ops-list-item";
      const unit = entry.price_unit === "per_pig_fee" ? "fee" : "/kg";
      item.innerHTML = `
        <strong>${safe(entry.product_type).replaceAll("_", " ")} ${safe(entry.cut_set, "")}</strong>
        <small>R${Number(entry.price_amount || 0).toFixed(2)}${unit} | ${safe(entry.deposit_rule)} | from ${safe(entry.effective_from, "now")}</small>
      `;
      elements.priceList.appendChild(item);
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

  const pigDisplay = (candidate) => {
    if (!candidate) return "No match";
    const tag = safe(candidate.tag_number || candidate.pig_id, "Unknown pig");
    const kg = candidate.latest_weight_kg === null || candidate.latest_weight_kg === undefined
      ? ""
      : ` | ${Number(candidate.latest_weight_kg).toFixed(1)}kg live`;
    return `${tag}${kg}`;
  };

  const renderMeatMatch = () => {
    if (!elements.matchResult) return;
    const match = state.meatMatch || {};
    const recommendation = match.recommendation || {};
    const alternatives = Array.isArray(match.alternatives) ? match.alternatives : [];
    elements.matchResult.innerHTML = "";
    if (!recommendation.pig_id && !recommendation.tag_number) {
      elements.matchStatus.textContent = "No Butcher match loaded. Build a match after selecting a lead.";
      elements.useMatch.disabled = true;
      return;
    }
    elements.matchStatus.textContent = safe(match.customer_safe_summary, "Match built. Owner review still required.");
    const primary = document.createElement("div");
    primary.className = "ops-list-item";
    primary.innerHTML = `
      <strong>${pigDisplay(recommendation)} | ${safe(recommendation.estimated_total_label, "estimate pending")}</strong>
      <small>${safe(recommendation.pricing_estimate?.yield_estimate?.display, "")}</small>
      <small>${(recommendation.match_reasons || []).map(safe).join(" | ")}</small>
    `;
    elements.matchResult.appendChild(primary);
    alternatives.forEach((candidate) => {
      const item = document.createElement("div");
      item.className = "ops-list-item";
      item.innerHTML = `
        <strong>Alternative: ${pigDisplay(candidate)} | ${safe(candidate.estimated_total_label, "estimate pending")}</strong>
        <small>${safe(candidate.pricing_estimate?.yield_estimate?.display, "")}</small>
      `;
      elements.matchResult.appendChild(item);
    });
    elements.useMatch.disabled = false;
  };

  const renderMeatOps = () => {
    if (!elements.opsResult) return;
    const ops = state.meatOps || {};
    const assembly = ops.assembly || {};
    const reservations = Array.isArray(ops.reservations) ? ops.reservations : [];
    const deposits = Array.isArray(ops.deposits) ? ops.deposits : [];
    const drafts = Array.isArray(ops.instruction_drafts) ? ops.instruction_drafts : [];
    const reservation = latestReservation();
    const hasLead = Boolean(state.selectedLeadId);
    const hasRecommendation = Boolean(state.meatMatch?.recommendation?.pig_id || state.meatMatch?.recommendation?.tag_number);
    const hasReservation = Boolean(reservation.reservation_id);
    const depositConfirmed = Boolean(assembly.deposit_confirmed);
    const readyForDrafts = Boolean(assembly.ready_for_instruction_drafts);

    elements.opsResult.innerHTML = "";
    elements.opsStatus.textContent = hasLead
      ? `Gate: ${safe(assembly.status, "interest_only")}. Full carcass: ${assembly.full_carcass_committed ? "yes" : "no"}. Deposit: ${depositConfirmed ? "confirmed" : "pending"}.`
      : "Reserve halves, confirm deposit, then prepare abattoir and butcher drafts.";

    reservations.forEach((item) => {
      const row = document.createElement("div");
      row.className = "ops-list-item";
      row.innerHTML = `
        <strong>${safe(item.tag_number || item.pig_id)} | ${safe(item.carcass_side)} | ${safe(item.status)}</strong>
        <small>${safe(item.cut_set, "cut set pending")} ${safe(item.estimated_packed_weight, "")}</small>
      `;
      elements.opsResult.appendChild(row);
    });

    deposits.forEach((item) => {
      const row = document.createElement("div");
      row.className = "ops-list-item";
      row.innerHTML = `
        <strong>${safe(item.event_type)} | ${item.amount ? `R${Number(item.amount).toFixed(2)}` : "amount not recorded"}</strong>
        <small>${safe(item.payment_method, "EFT")} ${safe(item.payment_reference, "")}</small>
      `;
      elements.opsResult.appendChild(row);
    });

    drafts.forEach((item) => {
      const row = document.createElement("div");
      row.className = "ops-list-item";
      const effectiveStatus = safe(item.effective_status || item.status, "draft");
      const isApproved = effectiveStatus === "approved_to_send" || effectiveStatus === "send_failed";
      const isSent = effectiveStatus === "sent";
      const isException = effectiveStatus === "exception_review_required";
      row.innerHTML = `
        <strong>${safe(item.instruction_type)} | ${effectiveStatus}</strong>
        <small>${safe(item.recipient_label)}: ${safe(item.draft_message)}</small>
        <div class="meat-lead-actions">
          <button type="button" class="button-link button-link-secondary" data-instruction-action="approve" data-instruction-id="${safe(item.instruction_draft_id, "")}" ${isApproved || isSent || isException ? "disabled" : ""}>Approve Exact Draft</button>
          <button type="button" class="button-link" data-instruction-action="send" data-instruction-id="${safe(item.instruction_draft_id, "")}" ${!isApproved || isSent || isException ? "disabled" : ""}>Send Approved</button>
          <button type="button" class="button-link button-link-secondary" data-instruction-action="exception" data-instruction-id="${safe(item.instruction_draft_id, "")}" ${isSent || isException ? "disabled" : ""}>Flag Exception</button>
          <button type="button" class="button-link button-link-secondary" data-instruction-action="resolve_exception" data-instruction-id="${safe(item.instruction_draft_id, "")}" ${!isException ? "disabled" : ""}>Resolve Exception</button>
        </div>
      `;
      elements.opsResult.appendChild(row);
    });

    if (!reservations.length && !deposits.length && !drafts.length) {
      elements.opsResult.innerHTML = '<div class="table-empty">No carcass reservation, deposit, or instruction drafts yet.</div>';
    }

    elements.reserveMatch.disabled = !hasLead || !hasRecommendation;
    elements.recordDeposit.disabled = !hasLead || !hasReservation || depositConfirmed;
    elements.buildInstructions.disabled = !hasLead || !readyForDrafts;
  };

  const renderMeatFulfillment = () => {
    if (!elements.fulfillmentResult) return;
    const payload = state.meatFulfillment || {};
    const fulfillment = payload.fulfillment || {};
    const journey = payload.journey_plan || {};
    const timeline = Array.isArray(payload.timeline) ? payload.timeline : [];
    const hasLead = Boolean(state.selectedLeadId);
    elements.fulfillmentResult.innerHTML = "";
    elements.fulfillmentStatus.textContent = hasLead
      ? `Status: ${safe(fulfillment.status, "not loaded")}. Next: ${safe(fulfillment.next_gate, "select a lead")}. Customer update: ${safe(journey.customer_message_state, "not planned")}.`
      : "Track waiting halves, abattoir, butcher, delivery, driver, and customer journey gates.";
    if (journey.summary) {
      const item = document.createElement("div");
      item.className = "ops-list-item";
      item.innerHTML = `
        <strong>${safe(journey.stage, "journey")}</strong>
        <small>${safe(journey.summary)}</small>
      `;
      elements.fulfillmentResult.appendChild(item);
    }
    timeline.forEach((event) => {
      const item = document.createElement("div");
      item.className = "ops-list-item";
      item.innerHTML = `
        <strong>${safe(event.event_type)} ${event.requires_template ? "| template required" : ""}</strong>
        <small>${safe(event.scheduled_date, "")} ${safe(event.scheduled_window, "")} ${safe(event.location_label, "")}</small>
        <small>${safe(event.actor_label || event.assigned_to, "")} ${safe(event.notes?.reason || event.notes?.notes, "")}</small>
      `;
      elements.fulfillmentResult.appendChild(item);
    });
    if (!timeline.length && !journey.summary) {
      elements.fulfillmentResult.innerHTML = '<div class="table-empty">No fulfilment events recorded yet.</div>';
    }
    elements.recordFulfillment.disabled = !hasLead;
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
      elements.buildMatch.disabled = true;
      elements.useMatch.disabled = true;
      elements.reserveMatch.disabled = true;
      elements.recordDeposit.disabled = true;
      elements.buildInstructions.disabled = true;
      elements.recordFulfillment.disabled = true;
      elements.buildJourneyDraft.disabled = true;
      elements.approveJourney.disabled = true;
      elements.sendJourney.disabled = true;
      elements.guidedNext.disabled = true;
      elements.guidedStatus.textContent = "Select a lead to see the next useful action.";
      elements.guidedResult.innerHTML = "";
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
    if (state.pricingEstimate) {
      applyPricingEstimate(state.pricingEstimate, false);
    }
    elements.estimateStatus.textContent = state.pricingEstimate?.estimated_total_label
      ? `Estimate: ${state.pricingEstimate.estimated_total_label} from active pricing rules. Final amount uses actual packed weight.`
      : "Pricing rules can prefill price, weight estimate, and deposit terms.";

    elements.usePricing.disabled = !hasLead;
    elements.buildMatch.disabled = !hasLead;
    renderMeatOps();
    renderMeatFulfillment();
    elements.buildJourneyDraft.disabled = !hasLead;
    elements.approveJourney.disabled = !hasLead || !elements.journeyMessage.value.trim();
    elements.sendJourney.disabled = !hasLead || !elements.journeyMessage.value.trim();
    elements.approveDetails.disabled = !hasLead;
    elements.buildPreview.disabled = !hasLead;
    elements.approveMessage.disabled = !hasLead || !elements.preview.value.trim();
    elements.sendMessage.disabled = !hasLead || !elements.preview.value.trim() || !state.messageApproved;
    elements.recordCustomerYes.disabled = !hasLoadedContract || !elements.customerConfirmation.value.trim();
    elements.createDraftOrder.disabled = !hasLoadedContract || !hasLoadedEvent("customer_booking_confirmed");
    const guide = guidedState();
    elements.guidedNext.textContent = guide.label;
    elements.guidedNext.disabled = guide.disabled;
    elements.guidedStatus.textContent = guide.detail;
    elements.guidedResult.innerHTML = `
      <div class="ops-list-item">
        <strong>${safe(guide.label)}</strong>
        <small>${safe(guide.detail)}</small>
      </div>
    `;

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

  const loadPriceBook = async () => {
    try {
      const payload = await fetchJson("/api/sales/meat-pricing?limit=50");
      state.priceEntries = Array.isArray(payload.price_entries) ? payload.price_entries : [];
      renderPriceBook();
    } catch (error) {
      elements.priceStatus.textContent = `Could not load price book: ${error.message}`;
      elements.priceList.innerHTML = '<div class="table-empty">Price book could not be loaded.</div>';
    }
  };

  async function loadLeadDetail(leadId) {
    state.contract = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(leadId)}/contract`);
    state.draft = null;
    state.messageApproved = false;
    state.pricingEstimate = null;
    state.meatMatch = null;
    state.meatOps = null;
    state.meatFulfillment = null;
    elements.preview.value = "";
    elements.customerConfirmation.value = "";
    elements.sendStatus.textContent = "No order, quote, or stock change is made from this page.";
    elements.orderStatus.textContent = "Draft order only. No pig reservation or stock change.";
    renderDetail();
    renderMeatMatch();
    renderMeatOps();
    renderMeatFulfillment();
    await loadPricingEstimate(true);
    await loadMeatOps();
    await loadMeatFulfillment();
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

  const applyPricingEstimate = (estimate, overwrite = false) => {
    const approval = estimate?.recommended_owner_approval || {};
    const setValue = (input, value) => {
      if (!input || !value) return;
      if (overwrite || !input.value.trim()) input.value = value;
    };
    setValue(elements.pricePerKg, approval.price_per_kg);
    setValue(elements.availableWeek, approval.available_week);
    setValue(elements.weightSize, approval.estimated_weight_or_size);
    setValue(elements.depositRule, approval.deposit_rule);
    setValue(elements.paymentMethod, approval.payment_method);
    setValue(elements.deliveryCollection, approval.delivery_or_collection);
    setValue(elements.ownerApproval, approval.owner_final_approval);
    elements.estimateStatus.textContent = estimate?.estimated_total_label
      ? `Estimate: ${estimate.estimated_total_label}. ${safe(estimate.yield_estimate?.display, "")}. Final amount uses actual packed weight.`
      : "Pricing rules applied where available.";
  };

  const loadPricingEstimate = async (prefill = false) => {
    if (!state.selectedLeadId) return;
    try {
      const payload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/pricing-estimate`);
      state.pricingEstimate = payload.pricing_estimate || {};
      if (prefill) applyPricingEstimate(state.pricingEstimate, false);
    } catch (error) {
      elements.estimateStatus.textContent = `Could not load pricing estimate: ${error.message}`;
    } finally {
      renderDetail();
    }
  };

  const usePricingRules = async () => {
    if (!state.selectedLeadId) return;
    setBusy(true);
    setMessage("");
    try {
      await loadPricingEstimate(false);
      applyPricingEstimate(state.pricingEstimate, true);
      setMessage("Pricing rules applied to the approval fields.", "success");
    } catch (error) {
      setMessage(`Could not apply pricing rules: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
    }
  };

  const buildMeatMatch = async () => {
    if (!state.selectedLeadId) return;
    setBusy(true);
    setMessage("");
    try {
      const payload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/meat-match`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preference: elements.matchPreference.value,
          target_packed_kg: elements.matchTargetKg.value,
          budget_amount: elements.matchBudget.value,
        }),
      });
      state.meatMatch = payload.meat_match || {};
      renderMeatMatch();
      setMessage("Butcher match built. No reservation was made.", "success");
    } catch (error) {
      setMessage(`Could not build meat match: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
      renderMeatMatch();
    }
  };

  const useMeatMatch = () => {
    const estimate = state.meatMatch?.recommendation?.pricing_estimate;
    if (!estimate) return;
    state.pricingEstimate = estimate;
    applyPricingEstimate(estimate, true);
    setMessage("Butcher match estimate applied to approval fields. Owner approval is still required.", "success");
    renderDetail();
  };

  const loadMeatOps = async () => {
    if (!state.selectedLeadId) return;
    try {
      const payload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/meat-ops`);
      state.meatOps = payload || {};
    } catch (error) {
      elements.opsStatus.textContent = `Could not load meat ops gate: ${error.message}`;
    } finally {
      renderMeatOps();
    }
  };

  const loadMeatFulfillment = async () => {
    if (!state.selectedLeadId) return;
    try {
      const payload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/fulfillment`);
      state.meatFulfillment = payload || {};
    } catch (error) {
      elements.fulfillmentStatus.textContent = `Could not load fulfilment timeline: ${error.message}`;
    } finally {
      renderMeatFulfillment();
    }
  };

  const reserveMatchedCarcass = async () => {
    if (!state.selectedLeadId) return;
    const recommendation = state.meatMatch?.recommendation || {};
    if (!recommendation.pig_id) {
      setMessage("Build a Butcher match before reserving a carcass.", "error");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/carcass-reservations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pig_id: recommendation.pig_id,
          tag_number: recommendation.tag_number,
          cut_set: state.meatMatch?.criteria?.cut_set || "",
          created_by: "Farm App",
        }),
      });
      await loadMeatOps();
      setMessage("Matched carcass reserved. Slaughter stays blocked until the carcass is complete and deposit is confirmed.", "success");
    } catch (error) {
      setMessage(`Could not reserve carcass: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
      renderMeatOps();
    }
  };

  const recordDeposit = async () => {
    if (!state.selectedLeadId) return;
    const reservation = latestReservation();
    if (!reservation.reservation_id) return;
    if (!elements.depositAmount.value || !elements.depositReference.value.trim()) {
      setMessage("Deposit amount and payment reference are required before confirming the deposit gate.", "error");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/deposit-events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reservation_id: reservation.reservation_id,
          order_id: reservation.order_id || latestDraftOrderEvent().order_id || "",
          event_type: "deposit_confirmed",
          amount: elements.depositAmount.value,
          payment_reference: elements.depositReference.value,
          payment_method: elements.paymentMethod.value || "EFT",
          recorded_by: "Farm App",
        }),
      });
      elements.depositAmount.value = "";
      elements.depositReference.value = "";
      await loadMeatOps();
      setMessage("Deposit confirmation recorded. Instruction drafts unlock only when a full carcass is committed.", "success");
    } catch (error) {
      setMessage(`Could not record deposit: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
      renderMeatOps();
    }
  };

  const buildInstructionDrafts = async () => {
    if (!state.selectedLeadId) return;
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/instruction-drafts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          abattoir_label: "Abattoir",
          butcher_label: "Butcher",
        }),
      });
      await loadMeatOps();
      setMessage("Abattoir and butcher instruction drafts created. Nothing external was sent.", "success");
    } catch (error) {
      setMessage(`Could not build instruction drafts: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
      renderMeatOps();
    }
  };

  const instructionDraftById = (instructionId) => {
    const drafts = Array.isArray(state.meatOps?.instruction_drafts) ? state.meatOps.instruction_drafts : [];
    return drafts.find((item) => item.instruction_draft_id === instructionId) || {};
  };

  const approveInstructionDraft = async (instructionId) => {
    const draft = instructionDraftById(instructionId);
    if (!state.selectedLeadId || !draft.instruction_draft_id) return;
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/instruction-drafts/${encodeURIComponent(instructionId)}/approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approved_message: draft.draft_message,
          approved_by: "Farm App",
          target_channel: "webhook",
        }),
      });
      await loadMeatOps();
      setMessage("Instruction draft approved exactly. Send is now gated by backend env and this exact text.", "success");
    } catch (error) {
      setMessage(`Could not approve instruction draft: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderMeatOps();
    }
  };

  const sendInstructionDraft = async (instructionId) => {
    const draft = instructionDraftById(instructionId);
    if (!state.selectedLeadId || !draft.instruction_draft_id) return;
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/instruction-drafts/${encodeURIComponent(instructionId)}/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: draft.draft_message,
          target_channel: "webhook",
          recorded_by: "Farm App",
        }),
      });
      await loadMeatOps();
      setMessage("Approved instruction sent through the configured backend channel.", "success");
    } catch (error) {
      setMessage(`Could not send instruction: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderMeatOps();
    }
  };

  const markInstructionException = async (instructionId, eventType = "exception_review_required") => {
    const draft = instructionDraftById(instructionId);
    if (!state.selectedLeadId || !draft.instruction_draft_id) return;
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/instruction-drafts/${encodeURIComponent(instructionId)}/exception`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_type: eventType,
          reason: eventType === "exception_review_resolved" ? "Owner resolved exception in Farm App" : "Owner marked instruction for review",
          recorded_by: "Farm App",
        }),
      });
      await loadMeatOps();
      setMessage(eventType === "exception_review_resolved" ? "Instruction exception resolved." : "Instruction flagged for exception review.", "success");
    } catch (error) {
      setMessage(`Could not update instruction exception: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderMeatOps();
    }
  };

  const handleInstructionAction = (event) => {
    const button = event.target.closest("[data-instruction-action]");
    if (!button) return;
    const instructionId = button.dataset.instructionId || "";
    const action = button.dataset.instructionAction || "";
    if (action === "approve") approveInstructionDraft(instructionId);
    if (action === "send") sendInstructionDraft(instructionId);
    if (action === "exception") markInstructionException(instructionId, "exception_review_required");
    if (action === "resolve_exception") markInstructionException(instructionId, "exception_review_resolved");
  };

  const recordFulfillmentEvent = async () => {
    if (!state.selectedLeadId) return;
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/fulfillment-events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_type: elements.fulfillmentEventType.value,
          scheduled_date: elements.fulfillmentDate.value,
          scheduled_window: elements.fulfillmentWindow.value,
          location_label: elements.fulfillmentLocation.value,
          address_line_1: elements.deliveryAddress.value,
          town: elements.deliveryTown.value,
          assigned_to: elements.deliveryDriver.value,
          reason: elements.fulfillmentNotes.value,
          notes: elements.fulfillmentNotes.value,
          actor_label: "Farm App",
        }),
      });
      elements.fulfillmentNotes.value = "";
      await loadMeatFulfillment();
      setMessage("Fulfilment event recorded. No customer message or external action was sent.", "success");
    } catch (error) {
      setMessage(`Could not record fulfilment event: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderMeatFulfillment();
    }
  };

  const buildJourneyDraft = async () => {
    if (!state.selectedLeadId) return;
    setBusy(true);
    setMessage("");
    try {
      const payload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/journey-notification-draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recorded_by: "Farm App" }),
      });
      const event = payload.notification_event || {};
      elements.journeyMessage.value = safe(event.message, "");
      setMessage("Customer journey draft built. Approve the exact text before sending.", "success");
    } catch (error) {
      setMessage(`Could not build journey draft: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
    }
  };

  const approveJourneyDraft = async () => {
    const message = elements.journeyMessage.value.trim();
    if (!state.selectedLeadId || !message) return;
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/journey-notification-approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approved_message: message,
          approved_by: "Farm App",
        }),
      });
      setMessage("Customer journey draft approved exactly. Send remains backend-gated.", "success");
    } catch (error) {
      setMessage(`Could not approve journey draft: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
    }
  };

  const sendJourneyUpdate = async () => {
    const message = elements.journeyMessage.value.trim();
    if (!state.selectedLeadId || !message) return;
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/journey-notification-send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          recorded_by: "Farm App",
        }),
      });
      setMessage("Customer journey update sent through the configured backend channel.", "success");
    } catch (error) {
      setMessage(`Could not send journey update: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
    }
  };

  const savePriceEntry = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await fetchJson("/api/sales/meat-pricing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_type: elements.priceProductType.value,
          cut_set: elements.priceCutSet.value.trim(),
          price_amount: elements.priceAmount.value,
          price_unit: elements.priceUnit.value,
          created_by: "Farm App",
        }),
      });
      elements.priceAmount.value = "";
      await loadPriceBook();
      if (state.selectedLeadId) await loadPricingEstimate(true);
      setMessage("Price entry added. Future estimates use the latest active effective entry.", "success");
    } catch (error) {
      setMessage(`Could not add price entry: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
    }
  };

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

  const guidedNextStep = async () => {
    if (!state.selectedLeadId) return;
    const guide = guidedState();
    if (guide.disabled) return;
    setBusy(true);
    setMessage("");
    try {
      if (hasLoadedEvent("customer_booking_confirmed")) {
        await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/draft-order`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ created_by: "Farm App guided flow" }),
        });
        await loadLeadDetail(state.selectedLeadId);
        setMessage("Draft order created from confirmed customer booking.", "success");
        return;
      }

      if (!state.pricingEstimate) {
        await loadPricingEstimate(false);
      }
      applyPricingEstimate(state.pricingEstimate, true);
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/owner-money-path-approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...approvalPayload(),
          recorded_by: "Farm App guided flow",
        }),
      });

      const draftPayload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/customer-followup-draft`);
      state.draft = draftPayload.customer_followup_draft || {};
      const message = safe(state.draft.message || state.draft.text, "");
      elements.preview.value = message;
      if (!message) throw new Error("customer_followup_message_missing");

      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/customer-followup-send-approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          approved_by: "Farm App guided flow",
          owner_final_send_approval: "Approved by guided flow",
        }),
      });
      state.messageApproved = true;

      const sendPayload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/customer-followup-send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      await loadLeadDetail(state.selectedLeadId);
      const sentLabel = sendPayload.sent
        ? `Sent via Chatwoot. Message ID: ${safe(sendPayload.chatwoot_message_id || sendPayload.message_id, "")}`
        : safe(sendPayload.status, "Send handled.");
      elements.sendStatus.textContent = sentLabel;
      setMessage(sentLabel, sendPayload.sent ? "success" : "");
    } catch (error) {
      const missing = Array.isArray(error.payload?.missing_fields) ? ` Missing: ${error.payload.missing_fields.join(", ")}.` : "";
      setMessage(`Guided step stopped: ${error.message}.${missing}`, "error");
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
  elements.priceRefresh.addEventListener("click", loadPriceBook);
  elements.priceForm.addEventListener("submit", savePriceEntry);
  elements.form.addEventListener("submit", approveDetails);
  elements.guidedNext.addEventListener("click", guidedNextStep);
  elements.usePricing.addEventListener("click", usePricingRules);
  elements.buildMatch.addEventListener("click", buildMeatMatch);
  elements.useMatch.addEventListener("click", useMeatMatch);
  elements.reserveMatch.addEventListener("click", reserveMatchedCarcass);
  elements.recordDeposit.addEventListener("click", recordDeposit);
  elements.buildInstructions.addEventListener("click", buildInstructionDrafts);
  elements.opsResult.addEventListener("click", handleInstructionAction);
  elements.recordFulfillment.addEventListener("click", recordFulfillmentEvent);
  elements.buildJourneyDraft.addEventListener("click", buildJourneyDraft);
  elements.approveJourney.addEventListener("click", approveJourneyDraft);
  elements.sendJourney.addEventListener("click", sendJourneyUpdate);
  elements.journeyMessage.addEventListener("input", renderDetail);
  elements.buildPreview.addEventListener("click", buildPreview);
  elements.approveMessage.addEventListener("click", approveMessage);
  elements.sendMessage.addEventListener("click", sendMessage);
  elements.customerConfirmation.addEventListener("input", renderDetail);
  elements.recordCustomerYes.addEventListener("click", recordCustomerYes);
  elements.createDraftOrder.addEventListener("click", createDraftOrder);

  clearDetailFields();
  setDetailEnabled(false);
  renderDetail();
  renderMeatMatch();
  renderMeatOps();
  renderMeatFulfillment();
  loadPriceBook();
  loadLeads();
})();
