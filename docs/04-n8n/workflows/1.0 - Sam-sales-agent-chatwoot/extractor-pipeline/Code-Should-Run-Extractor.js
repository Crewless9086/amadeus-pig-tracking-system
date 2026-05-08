const item = $input.first().json || {};

function clean(value) {
  return String(value || "").trim();
}

const decisionMode = clean(item.effective_decision_mode || item.decision_mode || "").toUpperCase();
const conversationMode = clean((item.order_state || {}).conversation_mode || item.ConversationMode || "").toUpperCase();
const pendingAction = clean((item.order_state || {}).pending_action || item.pending_action || "");
const msg = clean(item.customer_message || item.CustomerMessage || "");

const fromProcess =
  typeof process !== "undefined" && process.env ? process.env.EXTRACTOR_ENABLED : undefined;
const fromEnvBuiltin = typeof $env !== "undefined" ? $env.EXTRACTOR_ENABLED : undefined;

const extractorEnabledRaw = fromProcess !== undefined ? fromProcess : fromEnvBuiltin;

const extractorEnabled =
  extractorEnabledRaw === undefined ||
  extractorEnabledRaw === null ||
  extractorEnabledRaw === "" ||
  !["false", "0", "no", "off"].includes(String(extractorEnabledRaw).toLowerCase());

const lastOffer = item.last_agent_offer || {};
const offerOk = lastOffer.reconstructable === true && Array.isArray(lastOffer.caps) && lastOffer.caps.length > 0;

const existingStatus = clean((item.order_state || {}).existing_order_status || item.ExistingOrderStatus || "");
const beyondDraft = existingStatus && !["", "Draft"].includes(existingStatus);

let run = true;
let reason = "proceed";

if (!extractorEnabled) {
  run = false;
  reason = "extractor_disabled_env";
} else if (decisionMode !== "AUTO") {
  run = false;
  reason = "decision_mode_not_auto";
} else if (conversationMode === "HUMAN") {
  run = false;
  reason = "conversation_mode_human";
} else if (pendingAction === "cancel_order") {
  run = false;
  reason = "pending_cancel_flow";
} else if (!msg) {
  run = false;
  reason = "empty_customer_message";
} else if (!offerOk) {
  run = false;
  reason = "no_reconstructable_last_agent_offer";
} else if (beyondDraft) {
  run = false;
  reason = "order_not_draft";
} else {
  const shortGreet = /^(hi|hello|hey|good morning|good afternoon|howzit|haai)\b[!.\s]*$/i.test(msg);
  if (msg.length < 24 && shortGreet) {
    run = false;
    reason = "short_greeting_only";
  }
}

return [
  {
    json: {
      ...item,
      extractor_should_run: run,
      extractor_skip_reason: run ? "" : reason
    }
  }
];
