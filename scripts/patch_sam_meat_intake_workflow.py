import json
from pathlib import Path


WORKFLOW_PATH = Path("docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/workflow.json")


BUILD_NODE = "Code - Build Sam Meat Intake Payload"
IF_NODE = "IF - Sam Meat Intake Ready"
HTTP_NODE = "HTTP - Sam Meat Intake Lead"
ATTACH_NODE = "Code - Attach Sam Meat Intake Result"


BUILD_JS = r'''const item = $json || {};
const os = item.order_state || {};

function clean(value) {
  return String(value || "").trim();
}

function n8nVar(name) {
  try {
    if (typeof $vars !== "undefined" && $vars && $vars[name] !== undefined) {
      return clean($vars[name]);
    }
  } catch (_) {}
  return "";
}

function truthy(value) {
  return ["1", "true", "yes", "on"].includes(clean(value).toLowerCase());
}

function firstNonEmpty(values) {
  for (const value of values) {
    const cleaned = clean(value);
    if (cleaned) return cleaned;
  }
  return "";
}

function channelFrom(value) {
  const v = clean(value).toLowerCase();
  if (v.includes("whatsapp")) return "chatwoot_whatsapp";
  if (v.includes("instagram")) return "chatwoot_instagram";
  if (v.includes("messenger") || v.includes("facebook")) return "chatwoot_facebook";
  if (v.includes("email")) return "chatwoot_email";
  return v ? "chatwoot" : "chatwoot_unknown";
}

function productTypeFrom(text) {
  const t = clean(text).toLowerCase();
  if (/\bhalf\s+(?:carcass|carcase)\b|\bhalwe\s+karkas\b/.test(t)) return "half_carcass";
  if (/\bfull\s+(?:carcass|carcase)\b|\bwhole\s+(?:carcass|carcase)\b|\bheel\s+karkas\b/.test(t)) return "full_carcass";
  if (/\bassisted\s+slaughter\b|\bslaughter\s+service\b/.test(t)) return "assisted_slaughter";
  if (/\bcut\s*set\b|\bset\s+[abc]\b|\bmeat\s+pack\b|\bpork\s+pack\b/.test(t)) return "custom_cut";
  if (/\bcarcass\b|\bcarcase\b|\bkarkas\b|\bpork\b|\bmeat\b|\bvleis\b/.test(t)) return "unknown";
  return "";
}

function cutSetFrom(text) {
  const t = clean(text);
  const m = t.match(/\bset\s*([abc])\b/i);
  if (m) return `Set ${m[1].toUpperCase()}`;
  const cut = t.match(/\bcut\s*set\s*([abc])\b/i);
  if (cut) return `Set ${cut[1].toUpperCase()}`;
  return "";
}

function locationFrom(text) {
  const t = clean(text).toLowerCase();
  if (/\briversdale\b|\briverdale\b/.test(t)) return "Riversdale";
  if (/\balbertinia\b/.test(t)) return "Albertinia";
  if (/\bmossel\s*bay\b/.test(t)) return "Mossel Bay";
  if (/\bgeorge\b/.test(t)) return "George";
  if (/\bcape\s*town\b/.test(t)) return "Cape Town";
  return "";
}

function timingFrom(text) {
  const t = clean(text);
  const lower = t.toLowerCase();
  if (/\bnext available week\b/.test(lower)) return "next available week";
  if (/\bnext week\b/.test(lower)) return "next week";
  if (/\bthis week\b/.test(lower)) return "this week";
  if (/\basap\b|\bas soon as possible\b/.test(lower)) return "as soon as possible";
  const weekday = t.match(/\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i);
  if (weekday) return weekday[1].charAt(0).toUpperCase() + weekday[1].slice(1).toLowerCase();
  return "";
}

function deliveryOrCollectionFrom(text) {
  const t = clean(text).toLowerCase();
  if (/\bcollect\b|\bcollection\b|\bpick\s*up\b|\bpickup\b/.test(t)) return "collection";
  if (/\bdeliver\b|\bdelivery\b|\bcourier\b/.test(t)) return "delivery_requested";
  return "";
}

function paymentFrom(text) {
  const t = clean(text).toLowerCase();
  if (/\beft\b|\bbank transfer\b|\btransfer\b/.test(t)) return "EFT";
  if (/\bcash\b/.test(t)) return "Cash";
  return "";
}

function withoutNegatedLivePigPhrases(text) {
  return clean(text)
    .replace(/\bnot\s+(?:a\s+)?live\s+pigs?\b/gi, "")
    .replace(/\bno\s+live\s+pigs?\b/gi, "")
    .replace(/\bnot\s+looking\s+for\s+(?:a\s+)?live\s+pigs?\b/gi, "")
    .replace(/\bdon'?t\s+want\s+(?:a\s+)?live\s+pigs?\b/gi, "");
}

function nextQuestion(missing) {
  if (missing.includes("customer_name")) return "May I quickly confirm your name for the meat preorder note?";
  if (missing.includes("product_type")) return "Are you interested in a half carcass, full carcass, or a specific cut set?";
  if (missing.includes("location")) return "Which town or area would collection be from?";
  return "I will note the interest and confirm price and timing with the farm before quoting.";
}

let normalized = {};
try {
  normalized = $("Code - Normalize Incoming Message").first().json || {};
} catch (_) {
  normalized = {};
}

const customerMessage = firstNonEmpty([
  os.customer_message,
  item.customer_message,
  item.CustomerMessage,
  normalized.CustomerMessage
]);
const lowerMessage = customerMessage.toLowerCase();
const conversationHistory = clean(item.ConversationHistory || item.conversation_history);
const extractionText = [conversationHistory, customerMessage].filter(Boolean).join("\n");
const liveIntentText = withoutNegatedLivePigPhrases(customerMessage);
const handoffEnabled = truthy(n8nVar("SAM_MEAT_INTAKE_HANDOFF_ENABLED"));
const tokenConfigured = n8nVar("SAM_MEAT_INTAKE_REMOTE_TOKEN").length >= 32;
const meatIntent = /\bhalf\s+(?:carcass|carcase)\b|\bfull\s+(?:carcass|carcase)\b|\bwhole\s+(?:carcass|carcase)\b|\bcarcass\b|\bcarcase\b|\bkarkas\b|\bpork\b|\bmeat\b|\bvleis\b|\bcut\s*set\b|\bset\s+[abc]\b|\bassisted\s+slaughter\b/i.test(extractionText);
const livePigIntent = /\bpiglet\b|\bpiglets\b|\bweaner\b|\bweaners\b|\bgrower\b|\bgrowers\b|\bfinisher\b|\bfinishers\b|\blive\s+pig\b|\blive\s+pigs\b/i.test(liveIntentText);

const productType = productTypeFrom(extractionText);
const customerName = firstNonEmpty([os.customer_name, item.CustomerName, item.customer_name, normalized.CustomerName]);
const location = firstNonEmpty([locationFrom(extractionText), os.collection_location]);
const missingCore = [];
if (!customerName || customerName.toLowerCase() === "unknown") missingCore.push("customer_name");
if (!productType || productType === "unknown") missingCore.push("product_type");
if (!location) missingCore.push("location");

const skipReasons = [];
if (!handoffEnabled) skipReasons.push("sam_meat_intake_handoff_disabled");
if (!tokenConfigured) skipReasons.push("sam_meat_intake_token_not_configured");
if (!meatIntent) skipReasons.push("no_meat_preorder_intent");
if (meatIntent && livePigIntent) skipReasons.push("mixed_live_pig_and_meat_intent");
if (missingCore.length > 0) skipReasons.push(`missing_core:${missingCore.join(",")}`);

const payload = {
  customer_name: customerName,
  conversation_id: firstNonEmpty([os.conversation_id, item.ConversationId, item.conversation_id, normalized.ConversationId]),
  contact_id: firstNonEmpty([os.contact_id, item.ContactId, item.contact_id, normalized.ContactId]),
  channel: channelFrom(firstNonEmpty([os.customer_channel, item.Channel, item.customer_channel, normalized.Channel])),
  whatsapp_window_state: "open",
  product_type: productType || "unknown",
  cut_set: cutSetFrom(extractionText),
  location,
  timing: timingFrom(extractionText),
  delivery_or_collection: deliveryOrCollectionFrom(extractionText),
  price_per_kg: "",
  deposit_rule: "",
  payment_method: paymentFrom(extractionText),
  notes: customerMessage,
  status: "interested"
};

const shouldCall = skipReasons.length === 0;
const instruction = meatIntent && handoffEnabled && missingCore.length > 0
  ? `INSTRUCTION: This is meat preorder intake, not live-pig ordering. Do not quote price, promise timing, request deposit, reserve stock, or create an order. Ask one question only: ${nextQuestion(missingCore)}`
  : "";

return [{
  json: {
    ...item,
    sam_meat_intake: {
      lane: meatIntent ? "meat_preorder" : "",
      detected: meatIntent,
      live_pig_intent_detected: livePigIntent,
      handoff_enabled: handoffEnabled,
      token_configured: tokenConfigured,
      should_call: shouldCall,
      skip_reasons: skipReasons,
      missing_core_fields: missingCore,
      next_safe_question: nextQuestion(missingCore)
    },
    sam_meat_intake_payload: payload,
    sam_meat_intake_should_call: shouldCall,
    meat_intake_reply_instruction: instruction,
    reply_instruction: item.reply_instruction || instruction
  }
}];'''


ATTACH_JS = r'''let original = {};
try {
  original = $("Code - Build Sam Meat Intake Payload").first().json || {};
} catch (_) {
  original = $json || {};
}

const response = $json || {};
const wasCalled = response.mode === "sam_meat_intake_tracking_only" || Boolean(response.remote_ingest);
const previous = original.sam_meat_intake || {};
const contract = response.contract || {};

const result = {
  ...previous,
  attempted: wasCalled,
  success: response.success === true,
  lead_id: response.lead_id || "",
  backend_status: response.status || "",
  missing_core_fields: Array.isArray(contract.missing_core_fields)
    ? contract.missing_core_fields
    : (previous.missing_core_fields || []),
  missing_before_money_path: Array.isArray(contract.missing_before_money_path)
    ? contract.missing_before_money_path
    : [],
  next_safe_question: contract.sam_next_question || previous.next_safe_question || "",
  authority: contract.authority || response.remote_ingest || {},
  raw_response: wasCalled ? response : null
};

let instruction = original.reply_instruction || original.meat_intake_reply_instruction || "";
if (wasCalled && result.next_safe_question) {
  instruction = `INSTRUCTION: Meat preorder lead ${result.lead_id || "tracking"} was saved for owner/Ledger review only. Do not quote price, promise timing, request deposit, reserve stock, or create an order. Ask one safe next question if needed: ${result.next_safe_question}`;
}

return [{
  json: {
    ...original,
    sam_meat_intake: result,
    sam_meat_intake_raw_response: wasCalled ? response : null,
    reply_instruction: instruction
  }
}];'''


def code_node(name, node_id, position, js_code):
    return {
        "parameters": {"jsCode": js_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": position,
        "id": node_id,
        "name": name,
    }


def if_node():
    return {
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 3,
                },
                "conditions": [
                    {
                        "id": "sam-meat-intake-ready",
                        "leftValue": "={{ $json.sam_meat_intake_should_call === true }}",
                        "rightValue": True,
                        "operator": {
                            "type": "boolean",
                            "operation": "equals",
                        },
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [92512, 19024],
        "id": "phase11c-if-sam-meat-intake-ready",
        "name": IF_NODE,
    }


def http_node():
    return {
        "parameters": {
            "method": "POST",
            "url": "={{ String($vars.SAM_MEAT_INTAKE_BASE_URL || \"https://amadeus-pig-tracking-system.onrender.com\").replace(/\\/$/, \"\") + \"/api/oom-sakkie/channels/chatwoot/sam-meat-intake\" }}",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {
                        "name": "Authorization",
                        "value": "={{ \"Bearer \" + $vars.SAM_MEAT_INTAKE_REMOTE_TOKEN }}",
                    },
                    {
                        "name": "Content-Type",
                        "value": "application/json",
                    },
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.sam_meat_intake_payload }}",
            "options": {
                "response": {
                    "response": {
                        "responseFormat": "json",
                    }
                }
            },
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.3,
        "position": [92736, 18896],
        "id": "phase11c-http-sam-meat-intake-lead",
        "name": HTTP_NODE,
    }


def main():
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8-sig"))
    nodes = workflow["nodes"]
    names = {node.get("name") for node in nodes}
    if BUILD_NODE in names or IF_NODE in names or HTTP_NODE in names or ATTACH_NODE in names:
        raise SystemExit("Sam meat intake nodes already exist; refusing duplicate patch.")

    nodes.extend([
        code_node(BUILD_NODE, "phase11c-code-build-sam-meat-intake", [92288, 19024], BUILD_JS),
        if_node(),
        http_node(),
        code_node(ATTACH_NODE, "phase11c-code-attach-sam-meat-intake", [92960, 19024], ATTACH_JS),
    ])

    connections = workflow.setdefault("connections", {})
    attach_targets = connections["Code - Attach Intake Result"]["main"][0]
    connections["Code - Attach Intake Result"] = {
        "main": [[{"node": BUILD_NODE, "type": "main", "index": 0}]]
    }
    connections[BUILD_NODE] = {
        "main": [[{"node": IF_NODE, "type": "main", "index": 0}]]
    }
    connections[IF_NODE] = {
        "main": [
            [{"node": HTTP_NODE, "type": "main", "index": 0}],
            [{"node": ATTACH_NODE, "type": "main", "index": 0}],
        ]
    }
    connections[HTTP_NODE] = {
        "main": [[{"node": ATTACH_NODE, "type": "main", "index": 0}]]
    }
    connections[ATTACH_NODE] = {"main": [attach_targets]}

    WORKFLOW_PATH.write_text(json.dumps(workflow, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
