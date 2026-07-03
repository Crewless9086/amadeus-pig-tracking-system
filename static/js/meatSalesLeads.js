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
    meatReconciliation: null,
    pilotReadiness: null,
    launchGate: null,
    showAllTools: false,
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
    pilotPercent: byId("meat_pilot_percent"),
    pilotNextGate: byId("meat_pilot_next_gate"),
    pilotMetrics: byId("meat_pilot_metrics"),
    pilotChecklist: byId("meat_pilot_checklist"),
    launchGateStatus: byId("meat_launch_gate_status"),
    launchGate: byId("meat_launch_gate"),
    detailPanel: byId("meat_leads_detail_panel"),
    toggleTools: byId("meat_toggle_tools"),
    detailTitle: byId("meat_lead_detail_title"),
    detailStatus: byId("meat_lead_detail_status"),
    operatorStrip: byId("meat_operator_strip"),
    commandNextLabel: byId("sam_command_next_label"),
    commandNextReason: byId("sam_command_next_reason"),
    commandDraftState: byId("sam_command_draft_state"),
    commandDraftReason: byId("sam_command_draft_reason"),
    commandOwnerState: byId("sam_command_owner_state"),
    commandOwnerReason: byId("sam_command_owner_reason"),
    gateStack: byId("sam_gate_stack"),
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
    paymentSummary: byId("meat_payment_state_summary"),
    depositAmount: byId("meat_deposit_amount"),
    depositReference: byId("meat_deposit_reference"),
    recordPop: byId("meat_ops_record_pop"),
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
    slotQuickActions: byId("meat_slot_quick_actions"),
    recordFulfillment: byId("meat_fulfillment_record"),
    buildDadPacket: byId("meat_dad_booking_packet"),
    buildJourneyDraft: byId("meat_journey_build_draft"),
    approveJourney: byId("meat_journey_approve"),
    sendJourney: byId("meat_journey_send"),
    journeyMessage: byId("meat_journey_message"),
    fulfillmentResult: byId("meat_fulfillment_result"),
    reconciliationStatus: byId("meat_reconciliation_status"),
    reconciliationWeight: byId("meat_reconciliation_weight"),
    reconciliationPrice: byId("meat_reconciliation_price"),
    reconciliationReference: byId("meat_reconciliation_reference"),
    recordPackedWeight: byId("meat_reconciliation_record_weight"),
    confirmBalance: byId("meat_reconciliation_confirm_balance"),
    reconciliationResult: byId("meat_reconciliation_result"),
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

  const isSmokeLead = (lead) => {
    const label = `${lead?.contact_label || ""} ${lead?.lead_label || ""}`.toLowerCase();
    const conversation = String(lead?.chatwoot_conversation_id || "").toLowerCase();
    return label.includes("codex test customer")
      || conversation.startsWith("codex-smoke-")
      || conversation.startsWith("sam-contract-smoke-");
  };

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

  const eventsOf = (lead) => (Array.isArray(lead?.events) ? lead.events : []);

  const eventExists = (lead, type) => {
    if (lead?.latest_event?.event_type === type) return true;
    return eventsOf(lead).some((event) => event.event_type === type);
  };

  const latestEventForLead = (lead, type) => {
    const events = eventsOf(lead);
    for (let index = events.length - 1; index >= 0; index -= 1) {
      if (events[index].event_type === type) return events[index];
    }
    return lead?.latest_event?.event_type === type ? lead.latest_event : {};
  };

  const computeLeadNextAction = (lead, relatedState = {}) => {
    const item = lead && typeof lead === "object" ? lead : {};
    const contract = relatedState.contract && typeof relatedState.contract === "object" ? relatedState.contract : {};
    const meatOps = relatedState.meatOps && typeof relatedState.meatOps === "object" ? relatedState.meatOps : {};
    const fulfillment = relatedState.meatFulfillment?.fulfillment || {};
    const reconciliation = relatedState.meatReconciliation?.reconciliation || {};
    const interest = interestOf(item);
    const events = eventsOf(item);
    const missing = Array.isArray(contract.missing_fields)
      ? contract.missing_fields
      : ["product_type", "cut_set", "location", "timing", "delivery_or_collection"].filter((key) => {
          if (key === "product_type") return !interest.product_type || interest.product_type === "unknown";
          return !String(interest[key] || "").trim();
        });
    const assembly = meatOps.assembly || {};
    const paymentGate = meatOps.payment_gate || {};
    const reservations = Array.isArray(meatOps.reservations) ? meatOps.reservations : [];
    const instructionDrafts = Array.isArray(meatOps.instruction_drafts) ? meatOps.instruction_drafts : [];
    const activeReservation = reservations.find((reservation) => reservation.effective_status !== "cancelled") || {};
    const approvedInstruction = instructionDrafts.find((draft) => draft.effective_status === "approved_to_send" || draft.effective_status === "send_failed");
    const openInstruction = instructionDrafts.find((draft) => !["sent", "exception_review_required"].includes(draft.effective_status || draft.status));
    const hasLead = Boolean(item.lead_id);
    const hasMoneyApproval = contract.contract_status === "owner_money_path_ready" || eventExists(item, "owner_money_path_approved");
    const hasCustomerDraft = Boolean(relatedState.draft?.message || relatedState.draft?.text);
    const hasSendApproval = Boolean(relatedState.messageApproved || eventExists(item, "owner_customer_followup_send_approved"));
    const customerSent = eventExists(item, "customer_followup_sent");
    const customerYes = eventExists(item, "customer_booking_confirmed");
    const draftOrder = latestEventForLead(item, "draft_order_created");
    const popOnly = paymentGate.state === "pop_received_unverified" || assembly.payment_review_status === "pop_received_unverified";
    const moneyConfirmed = Boolean(paymentGate.deposit_confirmed_in_bank || assembly.deposit_confirmed);
    const readyForInstructions = Boolean(assembly.ready_for_instruction_drafts);
    const finalBalanceReady = reconciliation.next_gate === "delivery_release_ready" || reconciliation.balance_confirmed;

    if (!hasLead) {
      return {
        key: "missing_facts",
        label: "Select a lead",
        reason: "Choose a SAM meat lead before taking action.",
        risk: "idle",
        moneyState: "not_loaded",
        blockedReasons: ["no lead selected"],
        canPrepare: false,
      };
    }
    if (missing.length) {
      return {
        key: "missing_facts",
        label: "Capture Missing Facts",
        reason: `Sam still needs: ${missing.slice(0, 5).join(", ")}.`,
        risk: "medium",
        moneyState: "not_ready",
        blockedReasons: ["approval missing", "price/deposit facts incomplete"],
        canPrepare: false,
      };
    }
    if (!hasMoneyApproval) {
      return {
        key: "owner_price_deposit_review",
        label: "Review Price And Deposit",
        reason: "Owner must approve price, timing, deposit rule, payment method, and delivery/collection before any customer-facing draft is sent.",
        risk: "high",
        moneyState: "owner_review",
        blockedReasons: ["approval missing", "no price/deposit promise allowed"],
        canPrepare: true,
      };
    }
    if (!hasCustomerDraft) {
      return {
        key: "build_draft_reply",
        label: "Build Draft Reply",
        reason: "Money path is approved. Build a draft for owner review only; this does not send.",
        risk: "medium",
        moneyState: "approved",
        blockedReasons: [],
        canPrepare: true,
      };
    }
    if (!hasSendApproval) {
      return {
        key: "approve_exact_reply",
        label: "Approve Exact Reply",
        reason: "The reply draft exists. Owner must approve this exact text before any send endpoint can accept it.",
        risk: "high",
        moneyState: "approved",
        blockedReasons: ["approval missing", "hash approval required"],
        canPrepare: false,
      };
    }
    if (!customerSent) {
      const windowOpen = item.whatsapp_window_state === "open";
      return {
        key: "ready_for_owner_send_review",
        label: "Final Send Review",
        reason: windowOpen
          ? "Exact reply is approved. Use the existing gated send button only after final owner review."
          : "Exact reply is approved, but the WhatsApp window is closed or unknown.",
        risk: "critical",
        moneyState: "approved",
        blockedReasons: windowOpen ? [] : ["WhatsApp window closed"],
        canPrepare: false,
      };
    }
    if (!customerYes) {
      return {
        key: "wait_for_customer_yes",
        label: "Wait For Customer Yes",
        reason: "The approved follow-up was sent. Record customer confirmation only after the buyer clearly accepts.",
        risk: "medium",
        moneyState: "customer_review",
        blockedReasons: ["customer confirmation missing"],
        canPrepare: false,
      };
    }
    if (customerYes && !activeReservation.reservation_id && !draftOrder.event_type) {
      return {
        key: "reserve_or_pair_carcass",
        label: "Reserve Or Pair Carcass",
        reason: "Customer accepted. Butcher match and explicit owner reservation are needed before operations can continue.",
        risk: "high",
        moneyState: "awaiting_reservation",
        blockedReasons: ["no Butcher reservation"],
        canPrepare: false,
      };
    }
    if (popOnly) {
      return {
        key: "confirm_money_in_bank",
        label: "Confirm Money In Bank",
        reason: "POP is evidence only. Slaughter, fulfilment, and instruction gates stay blocked until money reflects in the farm account.",
        risk: "critical",
        moneyState: "pop_only",
        blockedReasons: ["POP only", "money not confirmed"],
        canPrepare: false,
      };
    }
    if (activeReservation.reservation_id && !moneyConfirmed) {
      return {
        key: "record_pop_evidence",
        label: "Record POP Or Wait",
        reason: "A reservation exists, but money is not confirmed. POP can be logged as evidence only.",
        risk: "high",
        moneyState: "deposit_not_confirmed",
        blockedReasons: ["money not confirmed"],
        canPrepare: false,
      };
    }
    if (moneyConfirmed && readyForInstructions && !instructionDrafts.length) {
      return {
        key: "create_instruction_drafts",
        label: "Create Instruction Drafts",
        reason: "Full carcass and bank-confirmed money are ready. Build internal abattoir and butcher drafts; nothing external is sent.",
        risk: "high",
        moneyState: "confirmed",
        blockedReasons: [],
        canPrepare: false,
      };
    }
    if (openInstruction && !approvedInstruction) {
      return {
        key: "approve_external_instruction",
        label: "Approve External Instruction",
        reason: "Instruction drafts exist. Approve exact draft text before any backend-gated external send.",
        risk: "critical",
        moneyState: "confirmed",
        blockedReasons: ["Gatekeeper approval required"],
        canPrepare: false,
      };
    }
    if (fulfillment.next_gate && fulfillment.next_gate !== "record_final_packed_weight") {
      return {
        key: "record_fulfillment",
        label: "Record Fulfilment",
        reason: `Fulfilment is at ${safe(fulfillment.next_gate, "the next operational gate")}. Record real events only.`,
        risk: "medium",
        moneyState: moneyConfirmed ? "confirmed" : "not_confirmed",
        blockedReasons: moneyConfirmed ? [] : ["money not confirmed"],
        canPrepare: false,
      };
    }
    if (!finalBalanceReady) {
      return {
        key: "reconcile_final_invoice",
        label: "Reconcile Final Invoice",
        reason: "Actual packed weight and final balance must be reconciled before delivery release.",
        risk: "high",
        moneyState: moneyConfirmed ? "confirmed" : "not_confirmed",
        blockedReasons: finalBalanceReady ? [] : ["final balance not confirmed"],
        canPrepare: false,
      };
    }
    return {
      key: "close_or_follow_up",
      label: "Close Or Follow Up",
      reason: "The main gates are complete. Review history and decide whether to close or follow up.",
      risk: "low",
      moneyState: "complete",
      blockedReasons: [],
      canPrepare: false,
    };
  };

  const guidedState = () => {
    const action = computeLeadNextAction(state.contract?.lead || selectedLead(), {
      contract: state.contract?.contract || {},
      meatOps: state.meatOps,
      meatFulfillment: state.meatFulfillment,
      meatReconciliation: state.meatReconciliation,
      draft: state.draft,
      messageApproved: state.messageApproved,
    });
    return {
      ...action,
      detail: action.reason,
      disabled: !state.selectedLeadId || !action.canPrepare,
    };
  };

  if (typeof window !== "undefined") {
    window.SamMeatCommandRoom = Object.freeze({
      computeLeadNextAction,
    });
  }

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

  const selectedLead = () => state.contract?.lead || state.leads.find((item) => item.lead_id === state.selectedLeadId) || {};

  const selectedStage = () => {
    const readinessRows = Array.isArray(state.pilotReadiness?.lead_stages) ? state.pilotReadiness.lead_stages : [];
    const row = readinessRows.find((item) => item.lead_id === state.selectedLeadId);
    if (row?.stage) return row.stage;
    const lead = selectedLead();
    const latest = latestEventType(lead);
    const assembly = state.meatOps?.assembly || {};
    const paymentGate = state.meatOps?.payment_gate || {};
    if (assembly.ready_for_slaughter_booking) return "slaughter_ready";
    if (paymentGate.state === "deposit_confirmed_in_bank" || assembly.deposit_confirmed) return "deposit_confirmed";
    if (paymentGate.state === "pop_received_unverified" || assembly.pop_received_unverified) return "pop_review";
    if (latest === "customer_followup_sent") return "quote_delivered";
    if (latest === "owner_customer_followup_send_approved") return "quote_ready";
    if (latest === "owner_money_path_approved") return "document_gate";
    return state.selectedLeadId ? "intake" : "";
  };

  const latestReservation = () => {
    const reservations = Array.isArray(state.meatOps?.reservations) ? state.meatOps.reservations : [];
    for (let index = reservations.length - 1; index >= 0; index -= 1) {
      if (reservations[index].reservation_id) return reservations[index];
    }
    return {};
  };

  const latestDepositEvent = (eventType) => {
    const deposits = Array.isArray(state.meatOps?.deposits) ? state.meatOps.deposits : [];
    for (let index = deposits.length - 1; index >= 0; index -= 1) {
      if (deposits[index].event_type === eventType) return deposits[index];
    }
    return {};
  };

  const latestDepositInstructionEvent = () => {
    const events = leadEvents();
    for (let index = events.length - 1; index >= 0; index -= 1) {
      const event = events[index];
      if (event.event_type !== "deposit_followup_needed") continue;
      const notes = eventNotesOf(event);
      if (notes.kind === "deposit_payment_instruction_prepared") return { ...notes, created_at: event.created_at };
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
      elements.recordPop,
      elements.recordDeposit,
      elements.buildInstructions,
      elements.recordFulfillment,
      elements.recordPackedWeight,
      elements.confirmBalance,
      ...Array.from(elements.slotQuickActions?.querySelectorAll("button") || []),
      elements.buildDadPacket,
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

  const formatGate = (value) => safe(value, "review").replaceAll("_", " ");

  const renderPilotReadiness = () => {
    const readiness = state.pilotReadiness || {};
    const summary = readiness.summary || {};
    const checklist = Array.isArray(readiness.checklist) ? readiness.checklist : [];
    elements.pilotPercent.textContent = `${Number(readiness.pilot_percent || 0)}%`;
    elements.pilotNextGate.textContent = formatGate(readiness.next_gate || summary.next_gate || "Loading pilot readiness");
    elements.pilotMetrics.innerHTML = [
      ["Active", summary.active_lead_count],
      ["Quote ready", summary.quote_ready_count],
      ["POP review", summary.pop_review_count],
      ["Money confirmed", summary.deposit_confirmed_count],
    ].map(([label, value]) => `
      <div>
        <span>${label}</span>
        <strong>${value ?? "--"}</strong>
      </div>
    `).join("");
    elements.pilotChecklist.innerHTML = checklist.slice(0, 4).map((item) => `
      <div class="meat-check-item" data-complete="${item.complete ? "true" : "false"}">
        <strong>${item.complete ? "Done" : "Open"}</strong>
        <span>${safe(item.label)}</span>
      </div>
    `).join("");
  };

  const gateItem = (label, ready, detail) => `
    <div class="meat-launch-gate-item" data-ready="${ready ? "true" : "false"}">
      <strong>${ready ? "Ready" : "Check"}</strong>
      <span>${safe(label)}</span>
      <small>${safe(detail)}</small>
    </div>
  `;

  const renderLaunchGate = () => {
    const gate = state.launchGate || {};
    const sam = gate.samPolicy?.policy || {};
    const facebook = gate.facebookPolicy?.policy || {};
    const planning = gate.planning || {};
    const planningSummary = planning.summary || {};
    const readiness = state.pilotReadiness || {};
    const templatePack = readiness.template_pack || {};
    const checklist = Array.isArray(readiness.checklist) ? readiness.checklist : [];
    const mediaReady = checklist.some((item) => item.key === "beacon_media" && item.complete);
    const stockReady = Number(planningSummary.ready_now || 0) > 0;
    const samReady = Boolean(
      sam.enabled
      && sam.token_configured
      && sam.autoreply_enabled
      && sam.llm_enabled
      && sam.agent_v3_enabled
      && sam.chatwoot_hygiene_enabled
      && sam.bank_details_configured
    );
    const beaconReady = Boolean(
      facebook.enabled
      && facebook.page_id_configured
      && facebook.page_access_token_configured
    );
    const templateReady = Boolean(templatePack.all_configured);
    const allReady = samReady && beaconReady && templateReady && stockReady && mediaReady;
    elements.launchGateStatus.textContent = allReady
      ? "Live gate is ready for an owner-reviewed, capped first post."
      : "Live gate still has checks before the first public post.";
    elements.launchGate.innerHTML = [
      gateItem("SAM V3 live agent", samReady, samReady ? "V3, LLM, autoreply, hygiene, token, and bank details are configured." : "Check SAM V3, LLM, autoreply, hygiene, token, and bank details."),
      gateItem("Beacon Facebook gate", beaconReady, beaconReady ? "Posting gate has page credentials and remains owner-confirmed." : "Check Facebook posting envs/page credentials."),
      gateItem("WhatsApp templates", templateReady, templateReady ? `${templatePack.configured_count || 0}/${templatePack.required_count || 0} templates configured.` : `${templatePack.configured_count || 0}/${templatePack.required_count || 0} templates configured.`),
      gateItem("Ready meat stock", stockReady, `${planningSummary.ready_now || 0} ready now, ${planningSummary.next_14_days || 0} in next 14 days.`),
      gateItem("Approved Beacon media", mediaReady, mediaReady ? "At least one approved image is ready for launch." : "Approve/select a launch image before posting."),
    ].join("");
  };

  const loadLaunchGate = async () => {
    try {
      const [samPolicy, facebookPolicy, planning] = await Promise.all([
        fetchJson("/api/sales/channels/chatwoot/sam-meat/policy"),
        fetchJson("/api/beacon/facebook-posting-policy"),
        fetchJson("/api/pig-weights/meat-planning"),
      ]);
      state.launchGate = { samPolicy, facebookPolicy, planning };
      renderLaunchGate();
    } catch (error) {
      elements.launchGateStatus.textContent = `Launch gate unavailable: ${error.message}`;
      elements.launchGate.innerHTML = "";
    }
  };

  const loadPilotReadiness = async () => {
    try {
      state.pilotReadiness = await fetchJson("/api/sales/meat-pilot-readiness?limit=50&status=launch_test");
      renderPilotReadiness();
      renderLaunchGate();
      renderToolVisibility();
    } catch (error) {
      elements.pilotNextGate.textContent = `Pilot readiness unavailable: ${error.message}`;
      elements.pilotMetrics.innerHTML = "";
      elements.pilotChecklist.innerHTML = "";
    }
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
    const urgency = {
      confirm_money_in_bank: 10,
      ready_for_owner_send_review: 9,
      approve_exact_reply: 8,
      owner_price_deposit_review: 7,
      reserve_or_pair_carcass: 6,
      create_instruction_drafts: 5,
      approve_external_instruction: 5,
      build_draft_reply: 4,
      missing_facts: 3,
      record_pop_evidence: 3,
      wait_for_customer_yes: 2,
      record_fulfillment: 2,
      reconcile_final_invoice: 2,
      close_or_follow_up: 1,
    };
    state.leads
      .slice()
      .sort((left, right) => {
        const leftAction = computeLeadNextAction(left, {});
        const rightAction = computeLeadNextAction(right, {});
        return (urgency[rightAction.key] || 0) - (urgency[leftAction.key] || 0);
      })
      .forEach((lead) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "meat-lead-row";
      button.classList.toggle("is-selected", lead.lead_id === state.selectedLeadId);
      button.dataset.leadId = lead.lead_id;
      const action = computeLeadNextAction(lead, {});
      button.innerHTML = `
        <span class="meat-lead-row-head">
          <strong>${safe(lead.contact_label || lead.lead_label, "Unknown buyer")}</strong>
          <em data-risk="${safe(action.risk, "idle")}">${safe(action.risk, "idle")}</em>
        </span>
        <span>${leadSummaryText(lead)}</span>
        <small>${safe(lead.status)} / ${safe(latestEventType(lead), "no event")} / ${safe(lead.whatsapp_window_state, "window unknown")}</small>
        <span class="meat-lead-next-action">${safe(action.label)}<small>${safe(action.moneyState)}</small></span>
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

  const renderCommandPanel = (lead, contract) => {
    if (!elements.commandNextLabel) return;
    const action = computeLeadNextAction(lead, {
      contract,
      meatOps: state.meatOps,
      meatFulfillment: state.meatFulfillment,
      meatReconciliation: state.meatReconciliation,
      draft: state.draft,
      messageApproved: state.messageApproved,
    });
    const draftMessage = safe(state.draft?.message || state.draft?.text, "");
    const hasSendApproval = Boolean(state.messageApproved || eventExists(lead, "owner_customer_followup_send_approved"));
    elements.commandNextLabel.textContent = action.label;
    elements.commandNextReason.textContent = action.reason;
    elements.commandDraftState.textContent = draftMessage ? "Draft ready for review" : "No draft loaded";
    elements.commandDraftReason.textContent = draftMessage
      ? "Draft is local review text only until exact owner approval and backend send gates pass."
      : "Build a draft only after owner money facts are ready.";
    elements.commandOwnerState.textContent = hasSendApproval
      ? "Exact reply approved"
      : contract?.contract_status === "owner_money_path_ready" ? "Money facts approved" : "Owner review needed";
    elements.commandOwnerReason.textContent = action.blockedReasons.length
      ? `Blocked by: ${action.blockedReasons.join(", ")}.`
      : "No frontend block detected; backend gates remain final.";
  };

  const renderGateStack = (lead, contract) => {
    if (!elements.gateStack) return;
    const action = computeLeadNextAction(lead, {
      contract,
      meatOps: state.meatOps,
      meatFulfillment: state.meatFulfillment,
      meatReconciliation: state.meatReconciliation,
      draft: state.draft,
      messageApproved: state.messageApproved,
    });
    const assembly = state.meatOps?.assembly || {};
    const paymentGate = state.meatOps?.payment_gate || {};
    const reservation = latestReservation();
    const events = Array.isArray(lead?.events) ? lead.events : [];
    const hasDraft = Boolean(state.draft?.message || state.draft?.text);
    const hasSendApproval = Boolean(state.messageApproved || eventExists(lead, "owner_customer_followup_send_approved"));
    const gateCards = [
      {
        label: "Ledger Money Gate",
        state: contract?.contract_status === "owner_money_path_ready" ? "ready" : "blocked",
        title: contract?.contract_status === "owner_money_path_ready" ? "Money facts approved" : "Owner approval needed",
        detail: contract?.missing_fields?.length ? `Missing ${contract.missing_fields.join(", ")}` : "Price, deposit, payment, timing, and delivery are controlled by existing rails.",
      },
      {
        label: "Butcher Availability Gate",
        state: reservation.reservation_id ? (assembly.ready_for_instruction_drafts ? "ready" : "wait") : "idle",
        title: reservation.reservation_id ? safe(reservation.status, "Reservation exists") : "No reservation",
        detail: reservation.reservation_id ? "Reservation exists; slaughter still needs full carcass and bank-confirmed money." : "Build match is read-only. Reservation requires explicit owner action.",
      },
      {
        label: "Beacon Demand Draft",
        state: "idle",
        title: "Draft-only from this room",
        detail: "No public post button is exposed here. Beacon publishing remains separate and gated.",
      },
      {
        label: "Gatekeeper Approval/Block",
        state: action.blockedReasons.length ? "blocked" : hasSendApproval ? "ready" : "wait",
        title: action.blockedReasons.length ? "Blocked" : hasSendApproval ? "Exact send approval exists" : "Review required",
        detail: action.blockedReasons.length ? action.blockedReasons.join(", ") : "Exact-message approval and backend send rules remain final.",
      },
      {
        label: "Supabase History",
        state: events.length ? "ready" : "idle",
        title: `${events.length} event${events.length === 1 ? "" : "s"}`,
        detail: hasDraft ? "Draft exists in browser state; persisted actions are append-only lead events." : "Lead events are loaded from the existing Supabase-backed rail.",
      },
    ];
    elements.gateStack.innerHTML = gateCards.map((card) => `
      <article class="sam-gate-card" data-state="${card.state}">
        <span>${card.label}</span>
        <strong>${card.title}</strong>
        <p>${card.detail}</p>
      </article>
    `).join("");
  };

  const renderOperatorStrip = (lead, contract) => {
    if (!elements.operatorStrip) return;
    if (!lead) {
      elements.operatorStrip.innerHTML = `
        <div class="meat-operator-empty">
          <strong>Select a lead</strong>
          <span>Sam's facts, money gate, and next click will appear here.</span>
        </div>
      `;
      return;
    }
    const interest = interestOf(lead);
    const missing = Array.isArray(contract?.missing_fields) ? contract.missing_fields : [];
    const guide = guidedState();
    const customerSent = hasLoadedEvent("customer_followup_sent");
    const customerYes = hasLoadedEvent("customer_booking_confirmed");
    const reservation = latestReservation();
    const assembly = state.meatOps?.assembly || {};
    const depositConfirmed = Boolean(assembly.deposit_confirmed);
    const factsReady = !missing.length;
    const opsReady = Boolean(assembly.ready_for_instruction_drafts);
    const cards = [
      {
        label: "Sam facts",
        state: factsReady ? "ready" : "warn",
        detail: factsReady ? "Complete enough for review" : `Missing ${missing.slice(0, 3).join(", ")}`,
      },
      {
        label: "Customer",
        state: customerYes ? "ready" : customerSent ? "wait" : "idle",
        detail: customerYes ? "Confirmed booking review" : customerSent ? "Waiting for yes" : "Follow-up not sent",
      },
      {
        label: "Money",
        state: depositConfirmed ? "ready" : "locked",
        detail: depositConfirmed ? "Money confirmed in bank" : "Do not proceed on POP alone",
      },
      {
        label: "Carcass",
        state: reservation.reservation_id ? (opsReady ? "ready" : "wait") : "idle",
        detail: reservation.reservation_id ? safe(reservation.status, "reserved") : "No reservation yet",
      },
      {
        label: "Next click",
        state: guide.disabled ? "locked" : "action",
        detail: guide.label,
      },
    ];
    elements.operatorStrip.innerHTML = `
      <div class="meat-operator-head">
        <div>
          <span>Current lead</span>
          <strong>${safe(lead.contact_label || lead.lead_label, "Customer")}</strong>
        </div>
        <small>${safe(interest.product || interest.product_type, "Product pending")} | ${safe(interest.cut_set, "cut pending")} | ${safe(interest.location, "area pending")}</small>
      </div>
      <div class="meat-operator-rail">
        ${cards.map((card) => `
          <div class="meat-operator-card" data-state="${card.state}">
            <span>${card.label}</span>
            <strong>${card.detail}</strong>
          </div>
        `).join("")}
      </div>
    `;
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
    const paymentStatus = safe(assembly.payment_review_status, depositConfirmed ? "confirmed_in_bank" : "not_received");
    const readyForDrafts = Boolean(assembly.ready_for_instruction_drafts);
    const instruction = latestDepositInstructionEvent();
    const latestPop = latestDepositEvent("pop_received_unverified");
    const latestBankInBank = latestDepositEvent("deposit_confirmed_in_bank");
    const latestBank = latestBankInBank.payment_reference ? latestBankInBank : latestDepositEvent("deposit_confirmed");
    const popReceived = Boolean(latestPop.payment_reference);

    elements.opsResult.innerHTML = "";
    elements.opsStatus.textContent = hasLead
      ? `Gate: ${safe(assembly.status, "interest_only")}. Full carcass: ${assembly.full_carcass_committed ? "yes" : "no"}. Payment: ${paymentStatus}.`
      : "Reserve halves, confirm money in bank, then prepare abattoir and butcher drafts.";

    if (elements.paymentSummary) {
      const paymentCards = [
        {
          label: "Payment Instruction",
          value: instruction.payment_reference ? "Prepared" : "Not prepared",
          detail: instruction.payment_reference ? `Reference ${instruction.payment_reference}` : "Sam sends this after customer acceptance and bank envs are configured.",
          state: instruction.payment_reference ? "ready" : "idle",
        },
        {
          label: "POP",
          value: latestPop.payment_reference ? "Received, unverified" : "Not received",
          detail: latestPop.payment_reference ? latestPop.payment_reference : "POP is evidence only; it does not unlock operations.",
          state: latestPop.payment_reference ? "warn" : "idle",
        },
        {
          label: "Money In Bank",
          value: depositConfirmed ? "Confirmed" : "Not confirmed",
          detail: latestBank.payment_reference ? `${latestBank.payment_reference}${latestBank.amount ? ` | R${Number(latestBank.amount).toFixed(2)}` : ""}` : "Requires bank notification or account confirmation.",
          state: depositConfirmed ? "ready" : "locked",
        },
        {
          label: "Ops Gate",
          value: readyForDrafts ? "Unlocked" : "Locked",
          detail: readyForDrafts ? "Instruction drafts can be built." : "Needs full carcass plus money confirmed in bank.",
          state: readyForDrafts ? "ready" : "locked",
        },
      ];
      elements.paymentSummary.innerHTML = paymentCards.map((card) => `
        <div class="meat-payment-state-item" data-state="${card.state}">
          <span>${card.label}</span>
          <strong>${card.value}</strong>
          <small>${card.detail}</small>
        </div>
      `).join("");
    }

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
    elements.recordPop.disabled = !hasLead || !hasReservation || depositConfirmed || popReceived;
    elements.recordDeposit.disabled = !hasLead || !hasReservation || depositConfirmed;
    elements.buildInstructions.disabled = !hasLead || !readyForDrafts;
  };

  const setPanelCurrent = (selector, isCurrent) => {
    const panel = document.querySelector(selector);
    if (panel) panel.classList.toggle("is-current", Boolean(isCurrent));
  };

  const renderToolVisibility = () => {
    const stage = selectedStage();
    const hasLead = Boolean(state.selectedLeadId);
    if (elements.detailPanel) {
      elements.detailPanel.classList.toggle("show-all", state.showAllTools);
      elements.detailPanel.dataset.stage = stage || "none";
    }
    if (elements.toggleTools) {
      elements.toggleTools.textContent = state.showAllTools ? "Hide Tools" : "Show Tools";
      elements.toggleTools.disabled = !hasLead;
    }
    setPanelCurrent(".meat-lead-match-panel", hasLead && ["intake", "document_gate", "quote_ready"].includes(stage));
    setPanelCurrent(".meat-lead-ops-panel", hasLead);
    setPanelCurrent(".meat-lead-fulfillment-panel", hasLead && ["deposit_confirmed", "slaughter_ready"].includes(stage));
    setPanelCurrent(".meat-lead-reconciliation-panel", hasLead && ["slaughter_ready"].includes(stage));
    setPanelCurrent("#meat_lead_approval_form", hasLead && ["intake", "document_gate", "quote_ready"].includes(stage));
    setPanelCurrent(".meat-lead-preview", hasLead && ["document_gate", "quote_ready"].includes(stage));
    setPanelCurrent(".meat-lead-order-gate", hasLead && ["quote_delivered", "pop_review"].includes(stage));
    setPanelCurrent(".meat-lead-events", false);
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
    elements.buildDadPacket.disabled = !hasLead;
  };

  const latestReconciliationEvent = (eventType) => {
    const events = Array.isArray(state.meatReconciliation?.reconciliation_events)
      ? state.meatReconciliation.reconciliation_events
      : [];
    for (let index = events.length - 1; index >= 0; index -= 1) {
      if (events[index].event_type === eventType) return events[index];
    }
    return {};
  };

  const renderMeatReconciliation = () => {
    if (!elements.reconciliationResult) return;
    const payload = state.meatReconciliation || {};
    const reconciliation = payload.reconciliation || {};
    const events = Array.isArray(payload.reconciliation_events) ? payload.reconciliation_events : [];
    const hasLead = Boolean(state.selectedLeadId);
    const reservation = latestReservation();
    const hasReservation = Boolean(reservation.reservation_id);
    const latestPacked = latestReconciliationEvent("packed_weight_recorded");
    const ready = Boolean(reconciliation.ready_for_delivery_release);

    elements.reconciliationResult.innerHTML = "";
    elements.reconciliationStatus.textContent = hasLead
      ? `Status: ${safe(reconciliation.status, "not loaded")}. Next: ${safe(reconciliation.next_gate, "record packed weight")}.`
      : "Record actual packed weight, calculate final amount, then confirm balance in bank before delivery release.";

    if (latestPacked.actual_packed_weight_kg && !elements.reconciliationWeight.value) {
      elements.reconciliationWeight.value = latestPacked.actual_packed_weight_kg;
    }
    if (latestPacked.price_per_kg && !elements.reconciliationPrice.value) {
      elements.reconciliationPrice.value = latestPacked.price_per_kg;
    }

    if (reconciliation.final_amount !== null && reconciliation.final_amount !== undefined) {
      const summary = document.createElement("div");
      summary.className = "ops-list-item";
      summary.innerHTML = `
        <strong>Final R${Number(reconciliation.final_amount || 0).toFixed(2)} | Balance R${Number(reconciliation.balance_due || 0).toFixed(2)}</strong>
        <small>${Number(reconciliation.actual_packed_weight_kg || 0).toFixed(2)}kg at R${Number(reconciliation.price_per_kg || 0).toFixed(2)}/kg. Deposit in bank R${Number(reconciliation.deposit_confirmed_amount || 0).toFixed(2)}.</small>
        <small>${ready ? "Delivery release allowed." : "Delivery release waits for final balance confirmed in bank."}</small>
      `;
      elements.reconciliationResult.appendChild(summary);
    }

    if (reconciliation.customer_balance_message) {
      const message = document.createElement("div");
      message.className = "ops-list-item";
      message.innerHTML = `
        <strong>Customer balance message draft</strong>
        <small>${safe(reconciliation.customer_balance_message)}</small>
      `;
      elements.reconciliationResult.appendChild(message);
    }

    events.slice().reverse().forEach((event) => {
      const item = document.createElement("div");
      item.className = "ops-list-item";
      item.innerHTML = `
        <strong>${safe(event.event_type)} ${event.balance_confirmed_amount ? `| R${Number(event.balance_confirmed_amount).toFixed(2)}` : ""}</strong>
        <small>${safe(event.payment_reference, "")} ${safe(event.created_at, "")}</small>
      `;
      elements.reconciliationResult.appendChild(item);
    });

    if (!events.length) {
      elements.reconciliationResult.innerHTML = '<div class="table-empty">No final packed-weight reconciliation recorded yet.</div>';
    }

    elements.recordPackedWeight.disabled = !hasLead || !hasReservation;
    elements.confirmBalance.disabled = !hasLead || !hasReservation || !latestPacked.actual_packed_weight_kg || ready;
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
    renderOperatorStrip(hasLead ? lead : null, contract);
    renderCommandPanel(hasLead ? lead : {}, contract);
    renderGateStack(hasLead ? lead : {}, contract);
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
      elements.recordPackedWeight.disabled = true;
      elements.confirmBalance.disabled = true;
      elements.buildDadPacket.disabled = true;
      elements.buildJourneyDraft.disabled = true;
      elements.approveJourney.disabled = true;
      elements.sendJourney.disabled = true;
      elements.guidedNext.disabled = true;
      elements.guidedStatus.textContent = "Select a lead to see the next useful action.";
      elements.guidedResult.innerHTML = "";
      renderCommandPanel({}, {});
      renderGateStack({}, {});
      renderToolVisibility();
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
    renderMeatReconciliation();
    elements.buildJourneyDraft.disabled = !hasLead;
    elements.buildDadPacket.disabled = !hasLead;
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
    renderToolVisibility();
    renderCommandPanel(lead, contract);
    renderGateStack(lead, contract);
  };

  const loadLeads = async () => {
    setBusy(true);
    setMessage("");
    try {
      const payload = await fetchJson("/api/sales/meat-leads?limit=50&status=launch_test");
      const leads = Array.isArray(payload.sales_leads) ? payload.sales_leads : [];
      state.leads = leads.filter((lead) => !isSmokeLead(lead));
      if (!state.leads.some((lead) => lead.lead_id === state.selectedLeadId)) {
        state.selectedLeadId = state.leads.length ? state.leads[0].lead_id : "";
      }
      renderSummary();
      renderLeadList();
      if (state.selectedLeadId) await loadLeadDetail(state.selectedLeadId);
      await loadPilotReadiness();
      await loadLaunchGate();
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
    state.meatReconciliation = null;
    elements.preview.value = "";
    elements.customerConfirmation.value = "";
    elements.sendStatus.textContent = "No order, quote, or stock change is made from this page.";
    elements.orderStatus.textContent = "Draft order only. No pig reservation or stock change.";
    renderDetail();
    renderMeatMatch();
    renderMeatOps();
    renderMeatFulfillment();
    renderMeatReconciliation();
    await loadPricingEstimate(true);
    await loadMeatOps();
    await loadMeatFulfillment();
    await loadMeatReconciliation();
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

  const loadMeatReconciliation = async () => {
    if (!state.selectedLeadId) return;
    try {
      const payload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/reconciliation`);
      state.meatReconciliation = payload || {};
    } catch (error) {
      elements.reconciliationStatus.textContent = `Could not load final balance gate: ${error.message}`;
    } finally {
      renderMeatReconciliation();
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
      setMessage("Matched carcass reserved. Slaughter stays blocked until the carcass is complete and money is confirmed in bank.", "success");
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
      setMessage("Deposit amount and bank reference are required before confirming money in bank.", "error");
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
          event_type: "deposit_confirmed_in_bank",
          amount: elements.depositAmount.value,
          payment_reference: elements.depositReference.value,
          payment_method: elements.paymentMethod.value || "EFT",
          recorded_by: "Farm App",
        }),
      });
      elements.depositAmount.value = "";
      elements.depositReference.value = "";
      await loadMeatOps();
      await loadPilotReadiness();
      setMessage("Money-in-bank confirmation recorded. Instruction drafts unlock only when a full carcass is committed.", "success");
    } catch (error) {
      setMessage(`Could not record deposit: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
      renderMeatOps();
    }
  };

  const recordPop = async () => {
    if (!state.selectedLeadId) return;
    const reservation = latestReservation();
    if (!reservation.reservation_id) return;
    if (!elements.depositReference.value.trim()) {
      setMessage("Bank reference is required before logging POP received.", "error");
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
          event_type: "pop_received_unverified",
          amount: elements.depositAmount.value || "",
          payment_reference: elements.depositReference.value,
          payment_method: elements.paymentMethod.value || "EFT",
          recorded_by: "Farm App",
        }),
      });
      elements.depositAmount.value = "";
      elements.depositReference.value = "";
      await loadMeatOps();
      await loadPilotReadiness();
      setMessage("POP received was logged. Operations remain blocked until money is confirmed in bank.", "success");
    } catch (error) {
      setMessage(`Could not record POP: ${error.message}`, "error");
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

  const recordSlotQuickAction = async (eventType) => {
    if (!state.selectedLeadId || !eventType) return;
    if (eventType.endsWith("_confirmed") && !elements.fulfillmentDate.value) {
      setMessage("Confirmed abattoir/butcher slots need a date before recording.", "error");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/fulfillment-events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_type: eventType,
          scheduled_date: elements.fulfillmentDate.value,
          scheduled_window: elements.fulfillmentWindow.value,
          location_label: elements.fulfillmentLocation.value,
          reason: elements.fulfillmentNotes.value,
          notes: elements.fulfillmentNotes.value || `Quick logged ${eventType.replaceAll("_", " ")}`,
          actor_label: "Farm App",
        }),
      });
      elements.fulfillmentEventType.value = eventType;
      elements.fulfillmentNotes.value = "";
      await loadMeatFulfillment();
      setMessage(`${eventType.replaceAll("_", " ")} recorded. Nothing was sent externally.`, "success");
    } catch (error) {
      setMessage(`Could not record slot update: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderMeatFulfillment();
    }
  };

  const activeReconciliationReservation = () => {
    const reconciliationReservation = state.meatReconciliation?.reconciliation?.reservation_id || "";
    if (reconciliationReservation) {
      const reservations = Array.isArray(state.meatOps?.reservations) ? state.meatOps.reservations : [];
      const found = reservations.find((item) => item.reservation_id === reconciliationReservation);
      if (found) return found;
    }
    return latestReservation();
  };

  const recordPackedWeight = async () => {
    if (!state.selectedLeadId) return;
    const reservation = activeReconciliationReservation();
    if (!reservation.reservation_id) {
      setMessage("Reserve a carcass before recording packed weight.", "error");
      return;
    }
    if (!elements.reconciliationWeight.value || !elements.reconciliationPrice.value) {
      setMessage("Packed kg and price/kg are required for final reconciliation.", "error");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/reconciliation-events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reservation_id: reservation.reservation_id,
          order_id: reservation.order_id || latestDraftOrderEvent().order_id || "",
          event_type: "packed_weight_recorded",
          actual_packed_weight_kg: elements.reconciliationWeight.value,
          price_per_kg: elements.reconciliationPrice.value,
          payment_reference: elements.reconciliationReference.value,
          recorded_by: "Farm App",
        }),
      });
      await loadMeatReconciliation();
      setMessage("Packed weight recorded and final balance calculated.", "success");
    } catch (error) {
      setMessage(`Could not record packed weight: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderMeatReconciliation();
    }
  };

  const confirmFinalBalance = async () => {
    if (!state.selectedLeadId) return;
    const reservation = activeReconciliationReservation();
    const reconciliation = state.meatReconciliation?.reconciliation || {};
    const balanceDue = Number(reconciliation.balance_due || 0);
    if (!reservation.reservation_id) return;
    if (!elements.reconciliationReference.value.trim()) {
      setMessage("Bank reference is required before confirming final balance in bank.", "error");
      return;
    }
    if (!reconciliation.actual_packed_weight_kg) {
      setMessage("Record actual packed weight before confirming final balance.", "error");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/reconciliation-events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reservation_id: reservation.reservation_id,
          order_id: reservation.order_id || latestDraftOrderEvent().order_id || "",
          event_type: "balance_confirmed_in_bank",
          balance_confirmed_amount: balanceDue,
          payment_reference: elements.reconciliationReference.value,
          recorded_by: "Farm App",
        }),
      });
      await loadMeatReconciliation();
      setMessage("Final balance confirmed in bank. Delivery release gate is now unlocked when the amount covers the balance.", "success");
    } catch (error) {
      setMessage(`Could not confirm final balance: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderMeatReconciliation();
    }
  };

  const handleSlotQuickAction = (event) => {
    const button = event.target.closest("[data-slot-action]");
    if (!button) return;
    recordSlotQuickAction(button.dataset.slotAction || "");
  };

  const buildDadBookingPacket = async () => {
    if (!state.selectedLeadId) return;
    setBusy(true);
    setMessage("");
    try {
      const payload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/dad-booking-packet`);
      const packet = payload.dad_booking_packet || {};
      const facts = packet.facts || {};
      elements.fulfillmentResult.innerHTML = `
        <div class="ops-list-item">
          <strong>Dad booking packet | ${safe(packet.readiness)}</strong>
          <small>${safe(packet.dad_action)}</small>
        </div>
        <div class="ops-list-item">
          <strong>${safe(facts.pig_or_tag, "Pig pending")} | ${safe(facts.product)} ${safe(facts.cut_set, "")}</strong>
          <small>${safe(facts.town, "Town pending")} | ${safe(facts.deposit_state)} | ${safe(facts.desired_timing, "timing pending")}</small>
        </div>
        <div class="ops-list-item">
          <strong>Draft message for Dad</strong>
          <small>${safe(packet.dad_message)}</small>
        </div>
      `;
      setMessage("Dad booking packet built. Nothing was sent or booked.", "success");
    } catch (error) {
      setMessage(`Could not build Dad booking packet: ${error.message}`, "error");
    } finally {
      setBusy(false);
      renderDetail();
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
      elements.fulfillmentResult.innerHTML = `
        <div class="ops-list-item">
          <strong>Journey draft | ${safe(event.stage)}</strong>
          <small>${event.requires_template ? "WhatsApp template required" : "Service-window reply allowed"}</small>
        </div>
        <div class="ops-list-item">
          <strong>Draft customer message</strong>
          <small>${safe(event.message)}</small>
        </div>
      `;
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
      if (guide.key === "owner_price_deposit_review") {
        await loadPricingEstimate(false);
        applyPricingEstimate(state.pricingEstimate, true);
        setMessage("Pricing estimate prepared in the owner review fields. Review and approve details separately.", "success");
        return;
      }

      if (guide.key === "build_draft_reply") {
        const draftPayload = await fetchJson(`/api/sales/meat-leads/${encodeURIComponent(state.selectedLeadId)}/customer-followup-draft`);
        state.draft = draftPayload.customer_followup_draft || {};
        const message = safe(state.draft.message || state.draft.text, "");
        elements.preview.value = message;
        state.messageApproved = false;
        elements.sendStatus.textContent = message
          ? "Draft built. Approve the exact message separately before any send."
          : "Draft endpoint returned no message.";
        setMessage("Draft reply built for owner review only. Nothing was approved or sent.", "success");
        return;
      }

      setMessage(`${guide.label}: ${guide.reason} Use the named gated control for this action.`, guide.blockedReasons?.length ? "error" : "");
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
  elements.toggleTools.addEventListener("click", () => {
    state.showAllTools = !state.showAllTools;
    renderToolVisibility();
  });
  elements.priceRefresh.addEventListener("click", loadPriceBook);
  elements.priceForm.addEventListener("submit", savePriceEntry);
  elements.form.addEventListener("submit", approveDetails);
  elements.guidedNext.addEventListener("click", guidedNextStep);
  elements.usePricing.addEventListener("click", usePricingRules);
  elements.buildMatch.addEventListener("click", buildMeatMatch);
  elements.useMatch.addEventListener("click", useMeatMatch);
  elements.reserveMatch.addEventListener("click", reserveMatchedCarcass);
  elements.recordPop.addEventListener("click", recordPop);
  elements.recordDeposit.addEventListener("click", recordDeposit);
  elements.buildInstructions.addEventListener("click", buildInstructionDrafts);
  elements.opsResult.addEventListener("click", handleInstructionAction);
  elements.slotQuickActions.addEventListener("click", handleSlotQuickAction);
  elements.recordFulfillment.addEventListener("click", recordFulfillmentEvent);
  elements.recordPackedWeight.addEventListener("click", recordPackedWeight);
  elements.confirmBalance.addEventListener("click", confirmFinalBalance);
  elements.buildDadPacket.addEventListener("click", buildDadBookingPacket);
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
  renderMeatReconciliation();
  loadPriceBook();
  loadPilotReadiness();
  loadLaunchGate();
  loadLeads();
})();
