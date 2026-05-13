# Sales Agent Chatwoot Workflow

## n8n Workflow Name

`1.0 - SAM - Sales Agent - Chatwoot`

## Purpose

Primary customer conversation workflow connected to Chatwoot. Sam is used to communicated with the clients an understadn their needs, he is the one answering all the questions he is allowed to answer based off the tools and data given to him. He can talk with clients and share details about the farm, what we do and also assist with building orders and order related task. 

The order section is what is causing us issues and difficulty at the moment. Sam is the one extracting info and giving the conversation centecta dn driving customers to buy from us, but not been pushy. 

The idea is that someone reach out to SAM and then the conversation flows, he answers stock related questions and then delegate tot he relevant tools so accomplsih these task. Sam is allowed to use as many tools possible to give the correct info to the client with the best answer possible. 

Sam should be able to act as a human doing sales and be able to have access to all tools that will help him accomplish the task. He never touches the order sheet, this is all done via tools. This is important to note, SAM has no direct access to data base he can only read from it and uses the tools to do the task for him. That said the correct data needs to be passed on in order for the correct tasks to be excecuted. 

The goals is not to over complicated it with adding new nodes for every problem we get, but rather to use what we have and make it work. Becuase this workflow will become more advance and we need to keep track of it. That said if we need to but only if needed we can make suggestions for different nodes but I rather keep them to a minimum. 

## Export File

The current n8n export is stored in `workflow.json`.

## Phase 5.6 Intake Shadow Mode

Status: complete and live-verified on 2026-05-12.

Shadow mode adds three nodes after `Code - Format Chat History` and before `Ai Agent - Escalation Classifier`:

- `Code - Build Intake Shadow Payload`
- `HTTP - Intake Shadow Update`
- `Code - Attach Intake Shadow Result`

Purpose:

- call backend `POST /api/order-intake/update` on each customer turn before AI classification and AUTO/ESCALATE routing
- persist confirmed intake facts in `ORDER_INTAKE_STATE` / `ORDER_INTAKE_ITEMS`
- attach `intake_shadow_result` and `intake_shadow_raw_response` for debugging/comparison
- leave existing draft creation, update, sync, cancel, approval, CLARIFY, and reply routing unchanged

Important rule:

Phase 5.6 does not use backend intake state as routing truth yet. Existing classifier route, `order_state`, Chatwoot attributes, and current route decisions still drive live behavior until shadow mode is verified.

Live verification:

- Safe Chatwoot conversation `1774` created intake `INTAKE-2026-4D7825`.
- Captured item: 1 Female Grower, `35_to_39_Kg`, Riversdale, Friday at 14:00, Cash.
- Follow-up `I want to proceed` updated the same intake to `Ready_For_Draft`, `next_action = create_draft`, `ready_for_draft = true`.
- No live draft order was created by shadow mode; existing route behavior remained unchanged.

## Phase 5.7 Intake-Driven Draft Creation

Status: complete and live-verified on 2026-05-12.

Phase 5.7 should use the verified intake result only for the first controlled route:

- when `intake_shadow_result.ready_for_draft = true`
- and `intake_shadow_result.next_action = create_draft`
- and no existing draft is linked yet

The preferred implementation is to pass backend-confirmed intake facts into the existing `1.2 - Amadeus Order Steward` create-with-lines route, then link the returned draft order ID back to intake state. Formal quote PDF generation remains Phase 5.8.

Repo implementation:

- `Code - Decide Order Route` promotes the verified intake-ready case to `CREATE_DRAFT`.
- `Set - Draft Order Payload` uses `intake_shadow_raw_response` and `intake_shadow_payload` for the create-with-lines payload when `debug_intake_ready_create_draft = true`.
- `Code - Build Intake Draft Link Payload` builds a `POST /api/order-intake/update` payload with the returned `order_id`.
- `HTTP - Link Intake Draft Order` patches `Draft_Order_ID` back to the intake state.
- The link branch outputs nothing unless the route was intake-driven, avoiding extra backend calls for legacy create behavior.
- `Code - Attach Intake Shadow Result` feeds both the escalation classifier and `Merge - Sales Agent Context A`; this is required because classifier output does not reliably preserve all incoming fields.

Live verification:

- Conversation `1774`, intake `INTAKE-2026-4D7825`.
- Created draft order `ORD-2026-A822D3`.
- Linked `Draft_Order_ID` back to intake and moved intake to `Draft_Created`.
- Synced one active line for Female Grower `35_to_39_Kg`.

Cleanup note:

The current 5.6/5.7 implementation intentionally keeps legacy route fallback while proving intake behavior. Once intake-driven update and quote flows are verified, simplify the workflow so intake state is the primary order-intake truth and remove duplicated shadow/legacy payload paths.

## Phase 5.8 Formal Quote Request Flow

Status: first controlled slice implemented in repo on 2026-05-13; live verification still required.

Implemented behavior:

- `Code - Decide Order Route` can route to `GENERATE_QUOTE` when backend intake returns `next_action = generate_quote`, or when Sam detects a quote request and there is an existing draft with a valid payment method.
- `Switch - Route Order Action` sends `GENERATE_QUOTE` to `Set - Build Generate Quote Payload`.
- `Call 1.2 - Generate Quote` calls the steward with `action = generate_quote`.
- `Merge - Quote Result With Reply Context` combines the steward result back into Sam's reply context.
- `Code - Slim Sales Agent User Context` includes a compact generated-document summary for Sam.
- Sam's system prompt now distinguishes Draft order, formal quote PDF, and approval.

Important boundary:

- This slice generates the quote PDF only. It must not tell the customer the quote was sent unless a later document-delivery action confirms sending.
- `create_draft_then_quote` is treated as a safe draft-create trigger so complete quote requests without a linked draft do not fall through to chat-only replies. Automatic quote generation immediately after creating that new draft is still pending.
- `HTTP - Get Conversation Messages` is non-blocking. If Chatwoot history lookup returns 404 or another API error, the workflow should continue with no history rather than dropping the current customer message before order/quote routing.
- `HTTP - Send Chatwoot Reply` should match the live-verified `1.4` send-message pattern: fixed account `147387`, normalized `ConversationId`, and explicit JSON body. A previous multi-source URL fallback still returned Chatwoot `404` in the Phase 5.8 test after the quote was generated, so this node should stay simple and consistent with the working outbound notification workflow.

Regression fix note:

- `Code - Build Intake Shadow Payload` recognizes broader natural commitment wording so intake reaches `Ready_For_Draft` for phrases such as `I would like to proceed`, `create a draft order`, and `prepare the next step`.
- `Code - Should Create Draft Order?` blocks legacy header-only draft creation unless legacy state contains line-ready `requested_items`. Intake-ready creation still uses the normal `create_order_with_lines` route.
- `Code - Build Intake Shadow Payload` also lets the latest explicit customer sex override stale `Any` values in existing `requested_items`, so messages like `2 male weaner pigs` do not keep an older generic sex preference.

## Migration Note

This folder is now the canonical home for the `1.0 - SAM - Sales Agent - Chatwoot` workflow notes and export.

## Note
I think we need to give more too access to Sam so he is able to view orders from the "ORDER_OVERVIEW" sheet if this is any help becuase I feel like the data logged or captured by the code in the flow is not always good, if he is able to follow a client and see if they have orders or any existing orders he can reference it and make use of it or at least cancel it should they choose to. Then start fresh with a new one or at least updated any orders that might be incorrect. Very important that we plan this accordinly.
Do we give him the sheet to read or do we give him a tool where he can then request "view_order" which one will be the best?
I wlaso want to know how can we keep record of the user if they have more than just one order? Is there a specific user field or ID we can use to add to the orders sheet to help identify returning customers and also when someone follows up on a order it easy to get all the orders. Weather it's open, cancelled or completed? This might just give sam more details? and make it more personal? What do you suggest or recommend how we do this? I just find that this will give it a better personal feeling. 
There can only be one active order at a time, but the user might have other old orders that they want to reference? What is you're take on this? 

## TOOLS
Sheets
Read SALES_STOCK_SUMMARY
Read SALES_STOCK_TOTALS
Read SALES_STOCK_DETAIL
Read SALES_AVAILABILITY
Farm_Info_Doc

Workflows
Send_Picture - is currently deactivated as this is not yet set up. 
Call 1.2 - Create Draft Order
Call 1.2 - Update Existing Draft
Call 1.2 - Sync Order Lines
These all call the workflow `1.2 - Amadeus Order Steward`, where the order action happens.

## Flow with Nodes & Explained
1. Webhook - Chatwoot Trigger
This is the trigger node that is linked to Chatwoot.

2. IF - Only Incoming Customer Messages
This node was added to ensure an endless loop was stopped. This only allowes customer messages through to the rest of the workflow. This has only the TRUE branch connected
Conditions:
{{
  // 1) only incoming contact messages
  ($json.body?.message_type === "incoming" || $json.body?.message_type === 0)
  &&
  // 2) allow ONLY if there is text OR audio (VN)
  (
    (String($json.body?.content || "").trim() !== "")
    ||
    (Array.isArray($json.body?.attachments) && $json.body.attachments.some(a => a?.file_type === "audio"))
  )
}} is equal to true

3. Code - Normalize Incoming Message
This node is used to normalize the messages to give the rest of the workflow meaning. This nodes extract all what is needed and ensures the correct fields get passed on.
// Normalize Incoming Message (Chatwoot webhook -> clean fields)
// Output: CustomerName, CustomerMessage, Channel, UserID, ConversationId, InboxId, etc.

const body = $json.body || {};
const conversation = body.conversation || {};
const inbox = body.inbox || {};
const sender = body.sender || {};
const msg = (conversation.messages && conversation.messages[0]) ? conversation.messages[0] : {};

const customerName =
  sender.name ||
  (msg.sender && msg.sender.name) ||
  'Unknown';

const customerMessage =
  body.content ||
  msg.content ||
  '';

const channel =
  inbox.name ||
  conversation.channel ||
  'Chatwoot';

const userId =
  (sender.id ?? sender.identifier ?? conversation.contact_inbox?.contact_id ?? null);

const existingOrderId =
  conversation.custom_attributes?.order_id ||
  '';

const existingOrderStatus =
  conversation.custom_attributes?.order_status ||
  '';

const conversationMode =
  conversation.custom_attributes?.conversation_mode ||
  'AUTO';

return [
  {
    json: {
      // Core
      CustomerName: customerName,
      CustomerMessage: customerMessage,
      Channel: channel,
      UserID: String(userId || ''),

      // Useful IDs
      AccountId: body.account?.id || null,
      InboxId: inbox.id || conversation.inbox_id || null,
      InboxName: inbox.name || null,

      ConversationId: conversation.id || null,
      ContactId: sender.id || conversation.contact_inbox?.contact_id || null,
      ContactInboxId: conversation.contact_inbox?.id || null,

      MessageId: body.id || msg.id || null,
      MessageType: body.message_type || null,
      SourceId: body.source_id || msg.source_id || null,

      CreatedAt: body.created_at || null,

      // Existing conversation custom attributes
      ExistingOrderId: existingOrderId,
      ExistingOrderStatus: existingOrderStatus,
      ConversationMode: conversationMode,

      // Raw for debugging if needed later
      Raw: body
    }
  }
];
Connects: this connects to two nodes
If - Has Audio Attachment?
Merge - Sales Agent Context B at input 2

4. If - Has Audio attachement?
This node was added to help with Voice notes. On the TRUE path this gets decoded to Text and on the FALSE path this just continues
Conditions: 
{{   Array.isArray($json.Raw?.attachments) && $json.Raw.attachments.some(a => a?.file_type === "audio") }} is true

4.T1 HTTP - Download Audio
This is just and HTTP to download the Audio file

4.T2 OpenAI - Transcribe a recording
This is to transcribe the voice note to text

4.T3 Edit - Apply Transcript
This nodes puts the messaged into fields
CustomerMessage = string = {{ $json.text }}
TranscribedText = string = {{ $json.text }}

5. IF - Has Final Text
Only the true path is connected
Conditions:
{{   String($json.CustomerMessage || "").trim() !== "" }} is true

6. (TRUE) Edit - Keep Chatwoot ID's
This node preserves key conversation fields so they are available downstream — including to the Escalation Classifier prompt and the ESCALATE path.
account_id = number = {{ $('Code - Normalize Incoming Message').item.json.AccountId }}
conversation_id = number = {{ $('Code - Normalize Incoming Message').item.json.ConversationId }}
inbox_name = string = {{ $('Code - Normalize Incoming Message').item.json.InboxName }}
contact_id = number = {{ $('Code - Normalize Incoming Message').item.json.ContactId }}
contact_name = string = {{ $('Code - Normalize Incoming Message').item.json.CustomerName }}
customer_message = string = {{ $json.CustomerMessage }}
pending_action = string = {{ $('Code - Normalize Incoming Message').item.json.PendingAction }}
existing_order_id = string = {{ $('Code - Normalize Incoming Message').item.json.ExistingOrderId }}
existing_order_status = string = {{ $('Code - Normalize Incoming Message').item.json.ExistingOrderStatus }}
conversation_mode = string = {{ $('Code - Normalize Incoming Message').item.json.ConversationMode }}
Connects: this node connects to
Code - Mode Gate

7. Code - Mode Gate
This node is to help set the mode
const attrs = $json.body?.conversation?.custom_attributes || {};
const mode = (attrs.conversation_mode || "AUTO").toUpperCase();

return [{ json: { ...$json, conversation_mode: mode, attrs } }];

8. If - Is human Lock Active
Only the FALSE path is connected, this was to help avoid ensless loops with AI I believe. 
Conditions:
{{ $json.conversation_mode }} is equal to HUMAN

9. (FALSE) HTTP - Get Conversation Messages
This node was added to get the conversation messages from chatwoot.
?? Can we make more use of this node to bring the context of the conversations down to a level that the Ai Agent - Escaltion Classifier can better use to decide the next path.

10. Code - Format Chat History
This node formats the messages and makes a better history for the Ai to use
const items = $input.all();

function clean(text) {
  return (text || "").replace(/\s+/g, " ").trim();
}

return items.map((item) => {
  // Accept either { payload: [...] } OR just [...]
  const payload = Array.isArray(item.json.payload)
    ? item.json.payload
    : (Array.isArray(item.json) ? item.json : []);

  if (!Array.isArray(payload) || payload.length === 0) {
    return { json: { ConversationHistory: "N/A", IsFirstTurn: true } };
  }

  const msgs = payload
    .filter(m => m && m.private === false)
    .map(m => ({
      created_at: m.created_at || 0,
      content: clean(m.content),
      senderType: m.sender?.type || (m.message_type === 0 ? "contact" : "user"),
      messageType: m.message_type,
    }))
    .filter(m => m.content.length > 0);

  msgs.sort((a, b) => a.created_at - b.created_at);

  const customerMsgs = msgs.filter(m => m.senderType === "contact" || m.messageType === 0);
  const isFirstTurn = customerMsgs.length <= 1;

  const lastN = msgs.slice(-25);
  const history = lastN.map(m => {
    const who = (m.senderType === "contact" || m.messageType === 0) ? "Customer" : "Sam";
    return `${who}: ${m.content}`;
  });

  return {
    json: {
      ConversationHistory: history.length ? history.join("\n") : "N/A",
      IsFirstTurn: isFirstTurn,
    },
  };
});
Connects:
Merge - Sales Agent Contect A input 1

11. Ai Agent - Escalation Classifier
This agent is used to classify the conversations and put it down the right path.
The chat mode is connected to ChatGPT.
Order context fields (existing_order_id, existing_order_status, pending_action) are now included in the prompt so the classifier has awareness of active orders. Cancel requests with an active order must route to AUTO, not ESCALATE.

Prompt (User Message)
UserName: {{ $('If - Is Human Lock Active?').item.json.contact_name }}
Channel: {{ $('If - Is Human Lock Active?').item.json.inbox_name }}
UserID: {{ $('If - Is Human Lock Active?').item.json.contact_id }}

ExistingOrderId: {{ $('If - Is Human Lock Active?').item.json.existing_order_id || 'none' }}
ExistingOrderStatus: {{ $('If - Is Human Lock Active?').item.json.existing_order_status || 'none' }}
PendingAction: {{ $('If - Is Human Lock Active?').item.json.pending_action || '' }}

ConversationHistory:
{{ $('Code - Format Chat History').item.json.ConversationHistory }}

CurrentMessage:
{{ $('If - Is Human Lock Active?').item.json.customer_message }}

System Message
You are an escalation decision engine for a livestock sales assistant.

Your job is to decide whether the assistant should:
- respond directly (AUTO)
- ask one clarifying question (CLARIFY)
- escalate to a human (ESCALATE)

## Core principle
Prefer AUTO or CLARIFY whenever the assistant can still help safely.
Use ESCALATE only when human judgment or human intervention is truly needed.

## Decision Rules

### AUTO
Choose AUTO when:
- the user intent is clear enough to answer directly
- the assistant can answer using available tools or known farm policies
- the message is about stock, pricing, availability, farm practices, collection, location wording, or general questions
- the message is about jobs, work, study, volunteering, contributing, farming advice, business advice, or learning more
- the user is asking harmless informational questions, even if they are not directly trying to buy yet
- If the customer clearly provides quantity plus a usable category or weight range, treat that as sufficient buying detail for AUTO. Do not ask unnecessary clarification questions just to narrow an already usable request.

IMPORTANT:
The following should normally stay AUTO and must not be escalated just because they are not immediate sales:
- job requests
- work opportunities
- study / learning questions
- volunteering / helping / contributing
- general farming advice
- general business advice

### CLARIFY
Choose CLARIFY when:
- the message is ambiguous or incomplete
- the user replies with short/unclear wording like “yes”, “ok”, “that one”
- key buying details are missing
- one specific question would likely resolve the issue
- Do not choose CLARIFY if the customer has already given a clear quantity and a clear usable pig type or weight range, unless a real contradiction or ambiguity remains.

IMPORTANT:
Prefer CLARIFY over ESCALATE whenever a single question can solve the uncertainty.

### ESCALATE
Choose ESCALATE only when:
- the user is upset, frustrated, or complaining
- the user explicitly asks for a human
- the request involves an exception, negotiation, or special deal
- the request needs human judgment or approval
- repeated clarification has failed
- the situation could create business risk or trust issues

Always choose ESCALATE if the customer explicitly asks to speak to a human person.

## Output Format (STRICT JSON ONLY)

{
  "decision": "AUTO | CLARIFY | ESCALATE",
  "reason": "short explanation",
  "confidence": 0.0-1.0,
  "summary": "short practical handoff summary for a human if escalation is needed"
}

## Summary Rules
- Keep it short but useful
- Include:
  - what the customer wants
  - what has already been answered
  - what is unclear or what caused escalation
  - the latest customer position
- Do not invent details

12. Code - Normalize Escalation Output
This nodes normalize the output from the Ai agent
const item = $json || {};

return [
  {
    json: {
      ...item,
      escalation_raw_output: item.output || ""
    }
  }
];

13. Code - Parse Escalation Decision
This node is to assist with parsing the decision
const items = $input.all();

const updatedItems = items.map((item) => {
  const raw = item?.json?.escalation_raw_output || "{}";

  let parsed = {};
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    parsed = {
      decision: "AUTO",
      reason: "Failed to parse escalation decision JSON",
      confidence: 0,
      summary: ""
    };
  }

  const decision = parsed.decision || "AUTO";
  const reason = parsed.reason || "";
  const confidence = parsed.confidence ?? 0;
  const summary = parsed.summary || "";

  const route = decision === "ESCALATE" ? "ESCALATE" : "AUTO";

  return {
    json: {
      ...item.json,
      decision,
      decision_mode: decision,
      route,
      reason,
      confidence,
      summary
    }
  };
});

return updatedItems;

14. Switch - Bot or Human
This node pick the path to take based of the decision this has two paths
{{ $json.route }} = AUTO
{{ $json.route }} = ESCALATE
Connected to:
AUTO -> Merge - Sales Agent Contect C input 1
ESCALATE -> Edit - Build Ticket Data

15. (AUTO)  Merge - Sales Agent Contect C
Combine by position 2 inputs

16. Code - Build Sales Agent Memory Summary
const item = $json || {};

function clean(value) {
  return String(value || "").trim();
}

function historyLines(text) {
  return String(text || "")
    .split("\n")
    .map(line => clean(line))
    .filter(Boolean);
}

function extractLastFromLines(lines, regex, groupIndex = 1) {
  for (let i = lines.length - 1; i >= 0; i--) {
    const match = lines[i].match(regex);
    if (match) {
      return clean(match[groupIndex] || match[0] || "");
    }
  }
  return "";
}

function hasAny(text, regex) {
  return regex.test(String(text || ""));
}

const history = clean(item.ConversationHistory);
const lines = historyLines(history);

// Only extract facts from customer messages — prevents Sam's suggestions
// (e.g. "we have 5-6kg") from leaking into known_facts as if confirmed
const customerLines = lines.filter(line => /^Customer:/i.test(line));

const isFirstTurn = item.IsFirstTurn === true;

const customerName = clean(item.CustomerName || item.contact_name);
const currentMessage = clean(item.customer_message || item.CustomerMessage);

const existingOrderId = clean(item.ExistingOrderId);
const existingOrderStatus = clean(item.ExistingOrderStatus);
const decisionMode = clean(item.decision_mode || "AUTO");

// -----------------------------
// Quantity
// -----------------------------
let knownQuantity =
  extractLastFromLines(customerLines, /\b(?:want|need|take|order|quote for|reserve|get)\s+(\d+)\b/i) ||
  extractLastFromLines(customerLines, /\b(\d+)\s+(?:pig|pigs|piglet|piglets|weaner|weaners|grower|growers|finisher|finishers)\b/i);

if (!knownQuantity) {
  const currentQty =
    currentMessage.match(/\b(?:want|need|take|order|quote for|reserve|get)\s+(\d+)\b/i) ||
    currentMessage.match(/\b(\d+)\s+(?:pig|pigs|piglet|piglets|weaner|weaners|grower|growers|finisher|finishers)\b/i);
  if (currentQty) knownQuantity = clean(currentQty[1]);
}

// -----------------------------
// Sex split
// -----------------------------
function extractLatestSexSplit(lines, currentMessage) {
  let totalMale = 0;
  let totalFemale = 0;
  let found = false;

  function parseText(text) {
    let localMale = 0;
    let localFemale = 0;
    let localFound = false;

    let match;
    const maleRegex = /(\d+)\s*(male|males|boar|boars)\b/gi;
    while ((match = maleRegex.exec(text)) !== null) {
      localMale += Number(match[1] || 0);
      localFound = true;
    }

    const femaleRegex = /(\d+)\s*(female|females|sow|sows)\b/gi;
    while ((match = femaleRegex.exec(text)) !== null) {
      localFemale += Number(match[1] || 0);
      localFound = true;
    }

    return { localMale, localFemale, localFound };
  }

  for (let i = lines.length - 1; i >= 0; i--) {
    const result = parseText(lines[i]);
    if (result.localFound) {
      totalMale = result.localMale;
      totalFemale = result.localFemale;
      found = true;
      break;
    }
  }

  if (!found) {
    const result = parseText(currentMessage);
    totalMale = result.localMale;
    totalFemale = result.localFemale;
    found = result.localFound;
  }

  return {
    found,
    male: totalMale,
    female: totalFemale,
    total: totalMale + totalFemale
  };
}

const sexSplit = extractLatestSexSplit(customerLines, currentMessage);

if (!knownQuantity && sexSplit.found && sexSplit.total > 0) {
  knownQuantity = String(sexSplit.total);
}

// -----------------------------
// Category
// -----------------------------
function categoryFromText(text) {
  const t = String(text || "");

  if (/\byoung piglet\b|\byoung piglets\b/i.test(t)) return "Piglet";
  if (/\bpiglet\b|\bpiglets\b/i.test(t)) return "Piglet";
  if (/\bweaner\b|\bweaners\b/i.test(t)) return "Weaner";
  if (/\bgrower\b|\bgrowers\b/i.test(t)) return "Grower";
  if (/\bfinisher\b|\bfinishers\b/i.test(t)) return "Finisher";
  if (/\bslaughter\b/i.test(t)) return "Slaughter";

  return "";
}

let knownCategory = "";
for (let i = customerLines.length - 1; i >= 0; i--) {
  const found = categoryFromText(customerLines[i]);
  if (found) {
    knownCategory = found;
    break;
  }
}
if (!knownCategory) {
  knownCategory = categoryFromText(currentMessage);
}

// -----------------------------
// Weight range
// -----------------------------
const weightPatterns = [
  { pattern: /\b90\s*(?:-|to|_|\u2013)?\s*94\s*kg\b|\b90_to_94_kg\b/i, value: "90_to_94_Kg" },
  { pattern: /\b85\s*(?:-|to|_|\u2013)?\s*89\s*kg\b|\b85_to_89_kg\b/i, value: "85_to_89_Kg" },
  { pattern: /\b80\s*(?:-|to|_|\u2013)?\s*84\s*kg\b|\b80_to_84_kg\b/i, value: "80_to_84_Kg" },
  { pattern: /\b75\s*(?:-|to|_|\u2013)?\s*79\s*kg\b|\b75_to_79_kg\b/i, value: "75_to_79_Kg" },
  { pattern: /\b70\s*(?:-|to|_|\u2013)?\s*74\s*kg\b|\b70_to_74_kg\b/i, value: "70_to_74_Kg" },
  { pattern: /\b65\s*(?:-|to|_|\u2013)?\s*69\s*kg\b|\b65_to_69_kg\b/i, value: "65_to_69_Kg" },
  { pattern: /\b60\s*(?:-|to|_|\u2013)?\s*64\s*kg\b|\b60_to_64_kg\b/i, value: "60_to_64_Kg" },
  { pattern: /\b55\s*(?:-|to|_|\u2013)?\s*59\s*kg\b|\b55_to_59_kg\b/i, value: "55_to_59_Kg" },
  { pattern: /\b50\s*(?:-|to|_|\u2013)?\s*54\s*kg\b|\b50_to_54_kg\b/i, value: "50_to_54_Kg" },
  { pattern: /\b45\s*(?:-|to|_|\u2013)?\s*49\s*kg\b|\b45_to_49_kg\b/i, value: "45_to_49_Kg" },
  { pattern: /\b40\s*(?:-|to|_|\u2013)?\s*44\s*kg\b|\b40_to_44_kg\b/i, value: "40_to_44_Kg" },
  { pattern: /\b35\s*(?:-|to|_|\u2013)?\s*39\s*kg\b|\b35_to_39_kg\b/i, value: "35_to_39_Kg" },
  { pattern: /\b30\s*(?:-|to|_|\u2013)?\s*34\s*kg\b|\b30_to_34_kg\b/i, value: "30_to_34_Kg" },
  { pattern: /\b25\s*(?:-|to|_|\u2013)?\s*29\s*kg\b|\b25_to_29_kg\b/i, value: "25_to_29_Kg" },
  { pattern: /\b20\s*(?:-|to|_|\u2013)?\s*24\s*kg\b|\b20_to_24_kg\b/i, value: "20_to_24_Kg" },
  { pattern: /\b15\s*(?:-|to|_|\u2013)?\s*19\s*kg\b|\b15_to_19_kg\b/i, value: "15_to_19_Kg" },
  { pattern: /\b10\s*(?:-|to|_|\u2013)?\s*14\s*kg\b|\b10_to_14_kg\b/i, value: "10_to_14_Kg" },
  { pattern: /(?:^|[^\d-])7\s*(?:-|to|_|\u2013)?\s*9\s*kg\b|\b7_to_9_kg\b/i, value: "7_to_9_Kg" },
  { pattern: /(?:^|[^\d-])5\s*(?:-|to|_|\u2013)?\s*6\s*kg\b|\b5_to_6_kg\b/i, value: "5_to_6_Kg" },
  { pattern: /(?:^|[^\d-])2\s*(?:-|to|_|\u2013)?\s*4\s*kg\b|\b2_to_4_kg\b/i, value: "2_to_4_Kg" }
];

let knownWeightRange = "";
for (let i = customerLines.length - 1; i >= 0; i--) {
  for (const entry of weightPatterns) {
    if (entry.pattern.test(customerLines[i])) {
      knownWeightRange = entry.value;
      break;
    }
  }
  if (knownWeightRange) break;
}
if (!knownWeightRange) {
  for (const entry of weightPatterns) {
    if (entry.pattern.test(currentMessage)) {
      knownWeightRange = entry.value;
      break;
    }
  }
}

// Category correction from weight range
if (!knownCategory && knownWeightRange) {
  if (["2-4kg", "5-6kg"].includes(knownWeightRange)) knownCategory = "Piglet";
  else if (["7-9kg", "10-14kg", "15-19kg"].includes(knownWeightRange)) knownCategory = "Weaner";
  else if (["20-24kg", "25-29kg", "30-34kg", "35-39kg", "40-44kg", "45-49kg"].includes(knownWeightRange)) knownCategory = "Grower";
}

if (knownWeightRange && ["2-4kg", "5-6kg"].includes(knownWeightRange)) {
  knownCategory = "Piglet";
}

// -----------------------------
// Collection location
// -----------------------------
let knownLocation = "";

for (let i = customerLines.length - 1; i >= 0; i--) {
  const line = customerLines[i];

  if (/\balbertinia please\b|\balbertinia\b/i.test(line) && !/\briversdale\b/i.test(line)) {
    knownLocation = "Albertinia";
    break;
  }

  if (/\briversdale please\b|\briversdale\b|\briverdale\b/i.test(line) && !/\balbertinia\b/i.test(line)) {
    knownLocation = "Riversdale";
    break;
  }

  if (
    /\briversdale or albertinia\b/i.test(line) ||
    /\balbertinia or riversdale\b/i.test(line) ||
    /\beither\b.*\briversdale\b.*\balbertinia\b/i.test(line)
  ) {
    if (!knownLocation) knownLocation = "Riversdale or Albertinia";
  }
}

if (!knownLocation) {
  if (/\balbertinia\b/i.test(currentMessage) && !/\briversdale\b|\briverdale\b/i.test(currentMessage)) {
    knownLocation = "Albertinia";
  } else if ((/\briversdale\b/i.test(currentMessage) || /\briverdale\b/i.test(currentMessage)) && !/\balbertinia\b/i.test(currentMessage)) {
    knownLocation = "Riversdale";
  }
}

// -----------------------------
// Timing
// -----------------------------
let knownTiming = "";

for (let i = customerLines.length - 1; i >= 0; i--) {
  const line = customerLines[i];

  if (/\bfriday morning\b/i.test(line)) { knownTiming = "Friday morning"; break; }
  if (/\bfriday\b/i.test(line)) { knownTiming = "Friday"; break; }
  if (/\bfirst week of may\b/i.test(line)) { knownTiming = "First week of May"; break; }
  if (/\bnext week\b/i.test(line)) { knownTiming = "Next week"; break; }
  if (/\btomorrow\b/i.test(line)) { knownTiming = "Tomorrow"; break; }
  if (/\btoday\b/i.test(line)) { knownTiming = "Today"; break; }
  if (/\basap\b/i.test(line)) { knownTiming = "ASAP"; break; }

  const dateMatch = line.match(/\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:january|february|march|april|may|june|july|august|september|october|november|december)\b/i);
  if (dateMatch) { knownTiming = clean(dateMatch[0]); break; }
}

if (!knownTiming) {
  if (/\bfriday morning\b/i.test(currentMessage)) knownTiming = "Friday morning";
  else if (/\bfriday\b/i.test(currentMessage)) knownTiming = "Friday";
  else if (/\bfirst week of may\b/i.test(currentMessage)) knownTiming = "First week of May";
  else if (/\bnext week\b/i.test(currentMessage)) knownTiming = "Next week";
  else if (/\btomorrow\b/i.test(currentMessage)) knownTiming = "Tomorrow";
  else if (/\btoday\b/i.test(currentMessage)) knownTiming = "Today";
  else if (/\basap\b/i.test(currentMessage)) knownTiming = "ASAP";
}

// -----------------------------
// Confirmations / commitment
// -----------------------------
const confirmationSignals =
  hasAny(history, /\bcorrect\b|\byes\b|\byes please\b|\bthat'?s right\b|\bthats right\b|\bit'?s ok for me\b|\bits ok for me\b|\bit'?s fine for me\b|\bits fine for me\b/i) ||
  hasAny(currentMessage, /\bcorrect\b|\byes\b|\byes please\b|\bthat'?s right\b|\bthats right\b|\bit'?s ok for me\b|\bits ok for me\b|\bit'?s fine for me\b|\bits fine for me\b/i);

// -----------------------------
// Photos / stage
// -----------------------------
const photoRequested =
  /\bphoto\b|\bphotos\b|\bpicture\b|\bpictures\b|\bimage\b|\bimages\b/i.test(history);

const quoteStage =
  /\bquote\b|\bquotation\b/i.test(history) &&
  !/\bi want to order\b|\bi would like to purchase\b|\bplace an order\b|\bgoing through with my order\b|\breserve\b/i.test(history);

const orderIntentStage =
  /\bi want to order\b|\bi would like to purchase\b|\bplace an order\b|\bgoing through with my order\b|\breserve\b/i.test(history) ||
  confirmationSignals;

let stage = "EARLY_INQUIRY";
if (existingOrderId) {
  stage = "DRAFT_IN_PROGRESS";
} else if (quoteStage) {
  stage = "QUOTE_STAGE";
} else if (
  orderIntentStage ||
  (
    knownCategory &&
    knownWeightRange &&
    knownLocation &&
    knownTiming &&
    knownQuantity
  )
) {
  stage = "ORDER_INTENT";
}

// -----------------------------
// Known facts
// -----------------------------
const knownFacts = [];
if (knownQuantity) knownFacts.push(`Quantity: ${knownQuantity}`);
if (knownCategory) knownFacts.push(`Category: ${knownCategory}`);
if (knownWeightRange) knownFacts.push(`Weight range: ${knownWeightRange}`);
if (sexSplit.found) {
  knownFacts.push(`Sex split: ${sexSplit.male} male, ${sexSplit.female} female`);
}
if (knownLocation) knownFacts.push(`Collection location: ${knownLocation}`);
if (knownTiming) knownFacts.push(`Timing: ${knownTiming}`);
if (photoRequested) knownFacts.push("Photos requested");
if (existingOrderId) knownFacts.push(`Existing draft order: ${existingOrderId}`);
if (existingOrderStatus) knownFacts.push(`Order status: ${existingOrderStatus}`);

// -----------------------------
// Missing facts
// -----------------------------
const missingFacts = [];

if (!knownCategory && !knownWeightRange) {
  missingFacts.push("Product direction still unclear");
}

if ((stage === "ORDER_INTENT" || stage === "DRAFT_IN_PROGRESS") && !knownQuantity) {
  missingFacts.push("Quantity not yet confirmed");
}

if ((stage === "ORDER_INTENT" || stage === "DRAFT_IN_PROGRESS") && !knownLocation) {
  missingFacts.push("Collection location not yet confirmed");
}

if ((stage === "ORDER_INTENT" || stage === "DRAFT_IN_PROGRESS") && !knownTiming) {
  missingFacts.push("Timing not yet confirmed");
}

if ((stage === "ORDER_INTENT" || stage === "DRAFT_IN_PROGRESS") && knownCategory && !knownWeightRange) {
  missingFacts.push("Weight range not yet confirmed");
}

// -----------------------------
// Memory summary
// -----------------------------
const memorySummary =
  `Stage: ${stage}. ` +
  (knownFacts.length
    ? `Known so far: ${knownFacts.join(" | ")}. `
    : `Known so far: no reliable carried facts yet. `) +
  (missingFacts.length
    ? `Still missing: ${missingFacts.join(" | ")}. `
    : `Still missing: nothing critical beyond normal confirmation. `) +
  `Use this to avoid repeating questions already answered in the conversation and prefer the latest confirmed fact over older broad context.`;

// -----------------------------
// Decision mode override (Bug 1 fix)
// If there is an existing draft and the escalation classifier said CLARIFY,
// override to AUTO so the order pipeline runs. The Sales Agent on the AUTO
// path can ask clarifying questions in its reply if needed.
// -----------------------------
const effectiveDecisionMode = (existingOrderId && decisionMode === "CLARIFY") ? "AUTO" : decisionMode;

// -----------------------------
// Output
// -----------------------------
return [
  {
    json: {
      ...item,
      decision_mode: effectiveDecisionMode,
      sales_agent_memory: {
        customer_name: customerName,
        decision_mode: effectiveDecisionMode,
        is_first_turn: isFirstTurn,
        existing_order_id: existingOrderId,
        existing_order_status: existingOrderStatus,
        conversation_stage: stage,
        known_facts: knownFacts,
        missing_facts: missingFacts,
        photo_requested: photoRequested,
        quote_stage: quoteStage,
        order_intent_stage: orderIntentStage,
        confirmation_signals: confirmationSignals,
        quantity: knownQuantity,
        category: knownCategory,
        weight_range: knownWeightRange,
        sex_split: sexSplit.found
          ? {
              male: sexSplit.male,
              female: sexSplit.female,
              total: sexSplit.total
            }
          : null,
        collection_location: knownLocation,
        timing: knownTiming,
        memory_summary: memorySummary,
        current_message: currentMessage
      }
    }
  }
];

17. Switch - Clarify or Auto
{{$json.decision_mode}} = CLARIFY
{{$json.decision_mode}} = AUTO
?? I feel this node is not this can just follow the now AUTO path as this will end at the same place. This was added to help avoid the removed LLM that messed up a few things. If this stays it does skip many nodes so not sure if this is a cleaner path. But it does feel like it's now redundent becuase we have an CLARIFY path and we have a REPLAY ONLY path later and they feel the same to me now.
Connects to
CLARIFY -> Code - Slim Sales Agent User Context
AUTO -> Code - Build Order State Inputs

18. (AUTO) Code - Build Order State Inputs
const item = $json || {};

function clean(value) {
  return String(value || "").trim();
}

return [
  {
    json: {
      ...item,

      ai_output: clean(item.output || item.ai_output || ""),
      decision_mode: clean(item.decision_mode || "AUTO"),

      customer_channel: clean(item.inbox_name || item.customer_channel || item.Channel),
      customer_language: clean(item.customer_language || ""),
      customer_message: clean(item.customer_message || item.CustomerMessage),
      conversation_id: clean(item.conversation_id || item.ConversationId),
      contact_id: clean(item.contact_id || item.ContactId),
      existing_order_id: clean(item.ExistingOrderId || item.existing_order_id),
      existing_order_status: clean(item.ExistingOrderStatus || item.existing_order_status),
      conversation_notes: clean(item.summary || item.conversation_notes || ""),
      customer_name: clean(item.contact_name || item.CustomerName || item.customer_name),
      conversation_mode: clean(item.ConversationMode || item.conversation_mode || "AUTO")
    }
  }
];

19. Code - Build Order State
const item = $json || {};

const currentMessage = String(item.customer_message || "").trim();
const lowerMessage = currentMessage.toLowerCase();
const salesAgentMemory = item.sales_agent_memory || {};

// -----------------------------
// Helpers
// -----------------------------
function cleanText(value) {
  return String(value || "").trim();
}

function normalizeCategory(value) {
  const v = cleanText(value).toLowerCase();
  if (!v) return "";
  if (v === "piglet" || v === "piglets") return "Piglet";
  if (v === "weaner" || v === "weaners") return "Weaner";
  if (v === "grower" || v === "growers") return "Grower";
  if (v === "finisher" || v === "finishers") return "Finisher";
  if (v === "slaughter") return "Slaughter";
  return cleanText(value);
}

function normalizeWeightRange(value) {
  const v = cleanText(value).toLowerCase().replace(/\s+/g, "");

  const map = {
    "2-4kg": "2_to_4_Kg",
    "2to4kg": "2_to_4_Kg",
    "2_4kg": "2_to_4_Kg",
    "2_to_4_kg": "2_to_4_Kg",

    "5-6kg": "5_to_6_Kg",
    "5to6kg": "5_to_6_Kg",
    "5_to_6_kg": "5_to_6_Kg",

    "7-9kg": "7_to_9_Kg",
    "7to9kg": "7_to_9_Kg",
    "7_to_9_kg": "7_to_9_Kg",

    "10-14kg": "10_to_14_Kg",
    "10to14kg": "10_to_14_Kg",
    "10_to_14_kg": "10_to_14_Kg",

    "15-19kg": "15_to_19_Kg",
    "15to19kg": "15_to_19_Kg",
    "15_to_19_kg": "15_to_19_Kg",

    "20-24kg": "20_to_24_Kg",
    "20to24kg": "20_to_24_Kg",
    "20_to_24_kg": "20_to_24_Kg",

    "25-29kg": "25_to_29_Kg",
    "25to29kg": "25_to_29_Kg",
    "25_to_29_kg": "25_to_29_Kg",

    "30-34kg": "30_to_34_Kg",
    "30to34kg": "30_to_34_Kg",
    "30_to_34_kg": "30_to_34_Kg",

    "35-39kg": "35_to_39_Kg",
    "35to39kg": "35_to_39_Kg",
    "35_to_39_kg": "35_to_39_Kg",

    "40-44kg": "40_to_44_Kg",
    "40to44kg": "40_to_44_Kg",
    "40_to_44_kg": "40_to_44_Kg",

    "45-49kg": "45_to_49_Kg",
    "45to49kg": "45_to_49_Kg",
    "45_to_49_kg": "45_to_49_Kg",

    "50-54kg": "50_to_54_Kg",
    "50to54kg": "50_to_54_Kg",
    "50_to_54_kg": "50_to_54_Kg",

    "55-59kg": "55_to_59_Kg",
    "55to59kg": "55_to_59_Kg",
    "55_to_59_kg": "55_to_59_Kg",

    "60-64kg": "60_to_64_Kg",
    "60to64kg": "60_to_64_Kg",
    "60_to_64_kg": "60_to_64_Kg",

    "65-69kg": "65_to_69_Kg",
    "65to69kg": "65_to_69_Kg",
    "65_to_69_kg": "65_to_69_Kg",

    "70-74kg": "70_to_74_Kg",
    "70to74kg": "70_to_74_Kg",
    "70_to_74_kg": "70_to_74_Kg",

    "75-79kg": "75_to_79_Kg",
    "75to79kg": "75_to_79_Kg",
    "75_to_79_kg": "75_to_79_Kg",

    "80-84kg": "80_to_84_Kg",
    "80to84kg": "80_to_84_Kg",
    "80_to_84_kg": "80_to_84_Kg",

    "85-89kg": "85_to_89_Kg",
    "85to89kg": "85_to_89_Kg",
    "85_to_89_kg": "85_to_89_Kg",

    "90-94kg": "90_to_94_Kg",
    "90to94kg": "90_to_94_Kg",
    "90_to_94_kg": "90_to_94_Kg"
  };

  return map[v] || "";
}

function normalizeLocation(value) {
  const v = cleanText(value).toLowerCase();
  if (!v) return "";
  if (v === "riverdale") return "Riversdale";
  if (v === "riversdale") return "Riversdale";
  if (v === "albertinia") return "Albertinia";
  if (v === "any") return "Any";
  if (v === "riversdale or albertinia" || v === "albertinia or riversdale") return "Any";
  return cleanText(value);
}

function normalizeSex(value) {
  const v = cleanText(value).toLowerCase();
  if (!v) return "";
  if (["female", "females", "sow", "sows"].includes(v)) return "Female";
  if (["male", "males", "boar", "boars"].includes(v)) return "Male";
  if (["any", "either"].includes(v)) return "Any";
  return "";
}

function parseMemorySexSplit(memory) {
  const raw = memory?.sex_split;
  if (!raw || typeof raw !== "object") return [];

  const items = [];
  const male = Number(raw.male || 0);
  const female = Number(raw.female || 0);

  if (male > 0) {
    items.push({ sex: "Male", quantity: String(male) });
  }
  if (female > 0) {
    items.push({ sex: "Female", quantity: String(female) });
  }

  return items;
}

function hasCoreMemory(memory) {
  return Boolean(
    cleanText(memory.quantity) ||
    cleanText(memory.category) ||
    cleanText(memory.weight_range) ||
    cleanText(memory.collection_location) ||
    cleanText(memory.timing) ||
    (memory.sex_split && typeof memory.sex_split === "object")
  );
}

// -----------------------------
// Quantity extraction
// -----------------------------
let msgQuantity = "";

const quantityPatterns = [
  /\bi want\s+(\d+)\b/i,
  /\bi need\s+(\d+)\b/i,
  /\bi(?:'| wi)ll take\s+(\d+)\b/i,
  /\bcan i get\s+(\d+)\b/i,
  /\bcan i order\s+(\d+)\b/i,
  /\bplease reserve\s+(\d+)\b/i,
  /\breserve\s+(\d+)\b/i,
  /\bgive me\s+(\d+)\b/i,
  /\bgimme\s+(\d+)\b/i,
  /\bget\s+(\d+)\b/i,
  /\btake\s+(\d+)\b/i,
  /\bmake it\s+(\d+)\b/i,
  /\bchange (?:it )?to\s+(\d+)\b/i,
  /\bchange (?:the )?quantity to\s+(\d+)\b/i,
  /\bupdate (?:it )?to\s+(\d+)\b/i,
  /\bactually\s+(\d+)\b/i,
  /\bnow\s+(\d+)\b/i,
  /\bchange\s+to\s+(\d+)\b/i,
  /\b(\d+)\s+(piglet|piglets|weaner|weaners|grower|growers|finisher|finishers|slaughter)\b/i
];

for (const pattern of quantityPatterns) {
  const match = currentMessage.match(pattern);
  if (match) {
    msgQuantity = match[1];
    break;
  }
}

// -----------------------------
// Split quantity + sex extraction
// -----------------------------
let splitSexItems = [];

const splitSexRegexGlobal =
  /(\d+)\s*(female|females|male|males|sow|sows|boar|boars)\b/gi;

let splitMatch;
while ((splitMatch = splitSexRegexGlobal.exec(currentMessage)) !== null) {
  const qty = String(splitMatch[1] || "").trim();
  const rawSex = String(splitMatch[2] || "").toLowerCase().trim();

  let normalizedSex = "";
  if (["female", "females", "sow", "sows"].includes(rawSex)) {
    normalizedSex = "Female";
  } else if (["male", "males", "boar", "boars"].includes(rawSex)) {
    normalizedSex = "Male";
  }

  if (qty && normalizedSex) {
    splitSexItems.push({
      sex: normalizedSex,
      quantity: qty
    });
  }
}

// -----------------------------
// Category extraction
// -----------------------------
let msgCategory = "";

if (/\bslaughter\b|\bslaughterer\b|\bslaughter pigs?\b|\bslaughter pig\b/i.test(currentMessage)) {
  msgCategory = "Slaughter";
} else if (/\bfinisher\b|\bfinishers\b/i.test(currentMessage)) {
  msgCategory = "Finisher";
} else if (/\bgrower\b|\bgrowers\b/i.test(currentMessage)) {
  msgCategory = "Grower";
} else if (/\bweaner\b|\bweaners\b/i.test(currentMessage)) {
  msgCategory = "Weaner";
} else if (/\bpiglet\b|\bpiglets\b/i.test(currentMessage)) {
  msgCategory = "Piglet";
}

// -----------------------------
// Weight range extraction
// -----------------------------
let msgWeightRange = "";

const weightPatterns = [
  { pattern: /\b2\s*(?:-|to|–|_)?\s*4\s*kg\b|\b2_to_4_kg\b/i, value: "2_to_4_Kg" },
  { pattern: /\b5\s*(?:-|to|–|_)?\s*6\s*kg\b|\b5_to_6_kg\b/i, value: "5_to_6_Kg" },
  { pattern: /\b7\s*(?:-|to|–|_)?\s*9\s*kg\b|\b7_to_9_kg\b/i, value: "7_to_9_Kg" },
  { pattern: /\b10\s*(?:-|to|–|_)?\s*14\s*kg\b|\b10_to_14_kg\b/i, value: "10_to_14_Kg" },
  { pattern: /\b15\s*(?:-|to|–|_)?\s*19\s*kg\b|\b15_to_19_kg\b/i, value: "15_to_19_Kg" },
  { pattern: /\b20\s*(?:-|to|–|_)?\s*24\s*kg\b|\b20_to_24_kg\b/i, value: "20_to_24_Kg" },
  { pattern: /\b25\s*(?:-|to|–|_)?\s*29\s*kg\b|\b25_to_29_kg\b/i, value: "25_to_29_Kg" },
  { pattern: /\b30\s*(?:-|to|–|_)?\s*34\s*kg\b|\b30_to_34_kg\b/i, value: "30_to_34_Kg" },
  { pattern: /\b35\s*(?:-|to|–|_)?\s*39\s*kg\b|\b35_to_39_kg\b/i, value: "35_to_39_Kg" },
  { pattern: /\b40\s*(?:-|to|–|_)?\s*44\s*kg\b|\b40_to_44_kg\b/i, value: "40_to_44_Kg" },
  { pattern: /\b45\s*(?:-|to|–|_)?\s*49\s*kg\b|\b45_to_49_kg\b/i, value: "45_to_49_Kg" },
  { pattern: /\b50\s*(?:-|to|–|_)?\s*54\s*kg\b|\b50_to_54_kg\b/i, value: "50_to_54_Kg" },
  { pattern: /\b55\s*(?:-|to|–|_)?\s*59\s*kg\b|\b55_to_59_kg\b/i, value: "55_to_59_Kg" },
  { pattern: /\b60\s*(?:-|to|–|_)?\s*64\s*kg\b|\b60_to_64_kg\b/i, value: "60_to_64_Kg" },
  { pattern: /\b65\s*(?:-|to|–|_)?\s*69\s*kg\b|\b65_to_69_kg\b/i, value: "65_to_69_Kg" },
  { pattern: /\b70\s*(?:-|to|–|_)?\s*74\s*kg\b|\b70_to_74_kg\b/i, value: "70_to_74_Kg" },
  { pattern: /\b75\s*(?:-|to|–|_)?\s*79\s*kg\b|\b75_to_79_kg\b/i, value: "75_to_79_Kg" },
  { pattern: /\b80\s*(?:-|to|–|_)?\s*84\s*kg\b|\b80_to_84_kg\b/i, value: "80_to_84_Kg" },
  { pattern: /\b85\s*(?:-|to|–|_)?\s*89\s*kg\b|\b85_to_89_kg\b/i, value: "85_to_89_Kg" },
  { pattern: /\b90\s*(?:-|to|–|_)?\s*94\s*kg\b|\b90_to_94_kg\b/i, value: "90_to_94_Kg" }
];

for (const entry of weightPatterns) {
  if (entry.pattern.test(lowerMessage)) {
    msgWeightRange = entry.value;
    break;
  }
}

// accept shorthand like "4k" or "2-4"
if (!msgWeightRange) {
  if (/\b15\s*(?:-|to|\u2013)?\s*19\b/i.test(currentMessage)) msgWeightRange = "15_to_19_Kg";
  else if (/\b10\s*(?:-|to|\u2013)?\s*14\b/i.test(currentMessage)) msgWeightRange = "10_to_14_Kg";
  else if (/(?:^|[^\d-])7\s*(?:-|to|\u2013)?\s*9\b/i.test(currentMessage)) msgWeightRange = "7_to_9_Kg";
  else if (/(?:^|[^\d-])5\s*(?:-|to|\u2013)?\s*6\b/i.test(currentMessage)) msgWeightRange = "5_to_6_Kg";
  else if (/(?:^|[^\d-])2\s*(?:-|to|\u2013)?\s*4\b/i.test(currentMessage)) msgWeightRange = "2_to_4_Kg";
  else if (/\b4k\b/i.test(currentMessage)) msgWeightRange = "2_to_4_Kg";
}

// -----------------------------
// Price-point extraction
// -----------------------------
let msgPricePoint = "";

const pricePatterns = [
  /\br\s*([0-9]{3,4})\b/i,
  /\bfor\s*r?\s*([0-9]{3,4})\b/i,
  /\bat\s*r?\s*([0-9]{3,4})\b/i,
  /\b([0-9]{3,4})\s*each\b/i
];

for (const pattern of pricePatterns) {
  const match = currentMessage.match(pattern);
  if (match) {
    msgPricePoint = match[1];
    break;
  }
}

const priceMap = {
  "350": { category: "Piglet", weight_range: "2_to_4_Kg" },
  "400": { category: "Piglet", weight_range: "5_to_6_Kg" },
  "450": { category: "Weaner", weight_range: "7_to_9_Kg" },
  "500": { category: "Weaner", weight_range: "10_to_14_Kg" },
  "600": { category: "Weaner", weight_range: "15_to_19_Kg" },
  "800":  { category: "Grower", weight_range: "20_to_24_Kg" },
  "1000": { category: "Grower", weight_range: "25_to_29_Kg" },
  "1200": { category: "Grower", weight_range: "30_to_34_Kg" },
  "1400": { category: "Grower", weight_range: "35_to_39_Kg" },
  "1600": { category: "Grower", weight_range: "40_to_44_Kg" },
  "1800": { category: "Grower", weight_range: "45_to_49_Kg" },
  "2200": { category: "Finisher", weight_range: "50_to_54_Kg" },
  "2300": { category: "Finisher", weight_range: "55_to_59_Kg" },
  "2400": { category: "Finisher", weight_range: "60_to_64_Kg" },
  "2500": { category: "Finisher", weight_range: "65_to_69_Kg" },
  "2600": { category: "Finisher", weight_range: "70_to_74_Kg" },
  "2700": { category: "Finisher", weight_range: "75_to_79_Kg" },
  "2800": { category: "Slaughter", weight_range: "80_to_84_Kg" },
  "2900": { category: "Slaughter", weight_range: "85_to_89_Kg" },
  "3000": { category: "Slaughter", weight_range: "90_to_94_Kg" }
};

const mappedFromPrice = msgPricePoint && priceMap[msgPricePoint]
  ? priceMap[msgPricePoint]
  : null;

// -----------------------------
// Sex extraction
// -----------------------------
let msgSex = "";

if (
  /\bany sex\b|\bany gender\b|\bno sex preference\b|\bno gender preference\b|\bmale or female\b|\bfemale or male\b|\beither male or female\b|\beither female or male\b|\bsex doesn't matter\b|\bsex does not matter\b|\bgender doesn't matter\b|\bgender does not matter\b/i.test(currentMessage)
) {
  msgSex = "Any";
} else if (/\bfemale\b|\bfemales\b|\bsow\b|\bsows\b/i.test(currentMessage) && splitSexItems.length === 0) {
  msgSex = "Female";
} else if (/\bmale\b|\bmales\b|\bboar\b|\bboars\b/i.test(currentMessage) && splitSexItems.length === 0) {
  msgSex = "Male";
}

// -----------------------------
// Timing extraction
// -----------------------------
let timingPreference = "";
let timingType = "";
let timingRaw = "";

const monthNames =
  "january|february|march|april|may|june|july|august|september|october|november|december";

const explicitDateMatch =
  currentMessage.match(new RegExp(`\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+of\\s+(${monthNames})\\b`, "i")) ||
  currentMessage.match(new RegExp(`\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+(${monthNames})\\b`, "i")) ||
  currentMessage.match(/\b(\d{1,2})[\/](\d{1,2})(?:[\/](\d{2,4}))?\b/i);

const firstWeekOfMonthMatch = currentMessage.match(new RegExp(`\\b(first|1st)\\s+week\\s+of\\s+(${monthNames})\\b`, "i"));
const endOfMonthMatch = /\bend of (the )?month\b|\bmonth end\b|\bmonth-end\b/i.test(currentMessage);
const startOfMonthMatch = /\bstart of (the )?month\b|\bbeginning of (the )?month\b|\bmonth start\b/i.test(currentMessage);
const thisWeekendMatch = /\bthis weekend\b/i.test(currentMessage);
const nextWeekendMatch = /\bnext weekend\b/i.test(currentMessage);
const nextWeekMatch = /\bnext week\b/i.test(currentMessage);
const thisWeekMatch = /\bthis week\b/i.test(currentMessage);
const tomorrowMatch = /\btomorrow\b/i.test(currentMessage);
const todayMatch = /\btoday\b/i.test(currentMessage);
const asapMatch = /\basap\b|\bas soon as possible\b/i.test(currentMessage);

const nextWeekdayMatch = currentMessage.match(/\bnext (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i);
const plainWeekdayMatch = currentMessage.match(/\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i);

const morningMatch = /\bmorning\b/i.test(currentMessage);
const afternoonMatch = /\bafternoon\b/i.test(currentMessage);
const eveningMatch = /\bevening\b/i.test(currentMessage);

if (explicitDateMatch) {
  timingType = "date";
  timingRaw = explicitDateMatch[0];
  timingPreference = explicitDateMatch[0];
} else if (firstWeekOfMonthMatch) {
  timingType = "date_range";
  timingRaw = firstWeekOfMonthMatch[0];
  timingPreference = `First week of ${firstWeekOfMonthMatch[2]}`;
} else if (endOfMonthMatch) {
  timingType = "relative_period";
  timingRaw = "end of month";
  timingPreference = "End of month";
} else if (startOfMonthMatch) {
  timingType = "relative_period";
  timingRaw = "start of month";
  timingPreference = "Start of month";
} else if (thisWeekendMatch) {
  timingType = "relative_period";
  timingRaw = "this weekend";
  timingPreference = "This weekend";
} else if (nextWeekendMatch) {
  timingType = "relative_period";
  timingRaw = "next weekend";
  timingPreference = "Next weekend";
} else if (nextWeekMatch) {
  timingType = "relative_period";
  timingRaw = "next week";
  timingPreference = "Next week";
} else if (thisWeekMatch) {
  timingType = "relative_period";
  timingRaw = "this week";
  timingPreference = "This week";
} else if (tomorrowMatch) {
  timingType = "relative_day";
  timingRaw = "tomorrow";
  timingPreference = "Tomorrow";
} else if (todayMatch) {
  timingType = "relative_day";
  timingRaw = "today";
  timingPreference = "Today";
} else if (asapMatch) {
  timingType = "priority";
  timingRaw = "ASAP";
  timingPreference = "ASAP";
} else if (nextWeekdayMatch) {
  timingType = "weekday";
  timingRaw = nextWeekdayMatch[0];
  timingPreference = `Next ${nextWeekdayMatch[1][0].toUpperCase()}${nextWeekdayMatch[1].slice(1).toLowerCase()}`;
} else if (plainWeekdayMatch) {
  const day = plainWeekdayMatch[1];
  timingType = "weekday";
  timingRaw = plainWeekdayMatch[0];
  timingPreference = `${day[0].toUpperCase()}${day.slice(1).toLowerCase()}`;
}

if (timingPreference) {
  const dayPart = morningMatch
    ? "morning"
    : afternoonMatch
    ? "afternoon"
    : eveningMatch
    ? "evening"
    : "";

  if (dayPart) {
    timingType = timingType || "day_part";
    timingRaw = timingRaw ? `${timingRaw} ${dayPart}` : dayPart;
    timingPreference = `${timingPreference} ${dayPart}`;
  }
}

// -----------------------------
// Collection location extraction
// -----------------------------
let collectionLocation = "";

const mentionsRiversdale = /\briversdale\b/i.test(currentMessage);
const mentionsAlbertinia = /\balbertinia\b/i.test(currentMessage);
const mentionsEither =
  /\beither\b/i.test(currentMessage) ||
  /\bany\b/i.test(currentMessage) ||
  /\bwhichever\b/i.test(currentMessage) ||
  /\bdoesn't matter\b|\bdoes not matter\b|\bno preference\b/i.test(currentMessage) ||
  /\bis fine\b|\bokay\b|\bok\b/i.test(currentMessage);

if (
  (mentionsRiversdale && mentionsAlbertinia) ||
  ((mentionsRiversdale || mentionsAlbertinia) && mentionsEither)
) {
  collectionLocation = "Any";
} else if (mentionsAlbertinia) {
  collectionLocation = "Albertinia";
} else if (mentionsRiversdale) {
  collectionLocation = "Riversdale";
}

if (!collectionLocation) {
  if (/\briverdale\b/i.test(currentMessage)) collectionLocation = "Riversdale";
}

// -----------------------------
// Final structured values from current message
// -----------------------------
let requestedQuantity = msgQuantity || "";

let requestedCategory =
  msgCategory ||
  (mappedFromPrice ? mappedFromPrice.category : "") ||
  "";

let requestedWeightRange =
  msgWeightRange ||
  (mappedFromPrice ? mappedFromPrice.weight_range : "") ||
  "";

let requestedSex = msgSex || "";

if (splitSexItems.length > 0) {
  const total = splitSexItems.reduce((sum, entry) => sum + Number(entry.quantity || 0), 0);
  if (total > 0) {
    requestedQuantity = String(total);
  }
  requestedSex = "Any";
}

// -----------------------------
// Message-only fact flags
// Capture what was actually provided in THIS message,
// before any memory hydration happens.
// -----------------------------
const msgHasSplitSex = splitSexItems.length > 0;
const msgHasTiming = timingPreference !== "";
const msgHasLocation = collectionLocation !== "";

// -----------------------------
// Memory fallback / hydration
// -----------------------------
const memoryQuantity = cleanText(salesAgentMemory.quantity);
const memoryCategory = normalizeCategory(salesAgentMemory.category);
const memoryWeightRange = normalizeWeightRange(salesAgentMemory.weight_range);
const memoryLocation = normalizeLocation(salesAgentMemory.collection_location);
const memoryTiming = cleanText(salesAgentMemory.timing);
const memorySexSplit = parseMemorySexSplit(salesAgentMemory);

const currentIsShortConfirmation =
  /^(yes|yes please|correct|confirmed|confirm|okay|ok|yep|yup|that'?s right|thats right|right|correct yes)$/i.test(currentMessage);

const shouldHydrateFromMemory =
  hasCoreMemory(salesAgentMemory) &&
  (
    currentIsShortConfirmation ||
    requestedQuantity === "" ||
    requestedCategory === "" ||
    requestedWeightRange === "" ||
    collectionLocation === "" ||
    timingPreference === ""
  );

if (shouldHydrateFromMemory) {
  if (requestedQuantity === "" && memoryQuantity !== "") {
    requestedQuantity = memoryQuantity;
  }

  if (requestedCategory === "" && memoryCategory !== "") {
    requestedCategory = memoryCategory;
  }

  if (requestedWeightRange === "" && memoryWeightRange !== "") {
    requestedWeightRange = memoryWeightRange;
  }

  if (collectionLocation === "" && memoryLocation !== "") {
    collectionLocation = memoryLocation;
  }

  if (timingPreference === "" && memoryTiming !== "") {
    timingPreference = memoryTiming;
    if (timingType === "") timingType = "memory";
    if (timingRaw === "") timingRaw = memoryTiming;
  }

  if (splitSexItems.length === 0 && memorySexSplit.length > 0) {
    splitSexItems = memorySexSplit;
    const total = splitSexItems.reduce((sum, entry) => sum + Number(entry.quantity || 0), 0);
    if (requestedQuantity === "" && total > 0) {
      requestedQuantity = String(total);
    }
    requestedSex = "Any";
  }
}

// -----------------------------
// Language inference
// -----------------------------
let customerLanguage = cleanText(item.customer_language);
if (!customerLanguage) {
  customerLanguage =
    /[áéíóúêôûëïöü]/i.test(currentMessage) ||
    /\b(ja|nee|asseblief|dankie|hoeveel)\b/i.test(lowerMessage)
      ? "Afrikaans"
      : "English";
}

// -----------------------------
// Intent detection
// -----------------------------
const strongIntent =
  /(\bi want\b|\bi need\b|\bi'll take\b|\bcan i order\b|\bcan i get\b|\bplease reserve\b|\bready to buy\b|\bplace an order\b|\bplease proceed\b|\bgo ahead\b|\byes please proceed\b)/i
    .test(currentMessage);

const proceedSignal =
  /(\byes\b|\byes please\b|\bplease proceed\b|\bgo ahead\b|\bthat's fine\b|\bthats fine\b|\bokay proceed\b|\bdo it\b|\bi'm going through with my order\b|\bi am going through with my order\b|\bit's ok for me\b|\bits ok for me\b|\bit is ok for me\b|\bit's fine for me\b|\bits fine for me\b|\bit is fine for me\b|\bcorrect\b|\bconfirmed\b)/i
    .test(currentMessage);

const quoteIntent =
  /\bquote\b|\bquotation\b|\bformal quote\b|\bwritten quote\b|\bprice quote\b/i.test(currentMessage);

const orderCommitmentIntent =
  /(\bi want\b|\bi need\b|\bi'll take\b|\bplease reserve\b|\breserve\b|\bplace an order\b|\bready to buy\b|\bgo ahead\b|\bplease proceed\b|\bi'm going through with my order\b|\bi am going through with my order\b|\bi would like to purchase\b|\bi want to order\b)/i
    .test(currentMessage);

const commitmentEvidence =
  requestedQuantity !== "" ||
  requestedCategory !== "" ||
  requestedWeightRange !== "" ||
  requestedSex !== "" ||
  splitSexItems.length > 0 ||
  timingPreference !== "" ||
  collectionLocation !== "";

const shortConfirmationalReply =
  currentMessage.length <= 40 &&
  (
    proceedSignal ||
    timingPreference !== "" ||
    collectionLocation !== "" ||
    splitSexItems.length > 0 ||
    requestedWeightRange !== "" ||
    requestedQuantity !== "" ||
    currentIsShortConfirmation
  );

const conversationCommitmentIntent =
  quoteIntent === false &&
  (
    orderCommitmentIntent === true ||
    strongIntent === true ||
    proceedSignal === true ||
    shortConfirmationalReply === true ||
    salesAgentMemory.order_intent_stage === true ||
    salesAgentMemory.confirmation_signals === true
  );

// -----------------------------
// Existing draft context
// -----------------------------
const existingOrderId = cleanText(item.existing_order_id);
const existingOrderStatus = cleanText(item.existing_order_status);

const hasExistingDraft =
  existingOrderId !== "" &&
  !["Cancelled", "Completed"].includes(existingOrderStatus);

// -----------------------------
// Enrichment detection
// Only factual detail in this message should trigger re-sync,
// OR a short proceed signal when there is not yet a fully built draft.
// -----------------------------
const messageHasNewUsefulInfo =
  msgQuantity !== "" ||
  msgWeightRange !== "" ||
  msgHasSplitSex === true ||
  msgHasTiming === true ||
  msgHasLocation === true ||
  // Category and sex only count when paired with explicit order intent
  (msgCategory !== "" && (strongIntent || orderCommitmentIntent || proceedSignal)) ||
  (msgSex !== "" && (strongIntent || orderCommitmentIntent || proceedSignal));

let hasNewUsefulInfo = messageHasNewUsefulInfo;

// -----------------------------
// Build requested_items
// -----------------------------
let requestedItems = [];

if (
  requestedQuantity !== "" &&
  requestedCategory !== "" &&
  requestedWeightRange !== ""
) {
  if (splitSexItems.length > 0) {
    requestedItems = splitSexItems.map((entry, index) => ({
      request_item_key: `primary_${index + 1}`,
      category: requestedCategory,
      weight_range: requestedWeightRange,
      sex: entry.sex,
      quantity: entry.quantity,
      intent_type: "primary",
      status: "active",
      notes: ""
    }));
  } else {
    requestedItems = [
      {
        request_item_key: "primary_1",
        category: requestedCategory,
        weight_range: requestedWeightRange,
        sex: requestedSex || "Any",
        quantity: requestedQuantity,
        intent_type: "primary",
        status: "active",
        notes: ""
      }
    ];
  }
}

if (!hasNewUsefulInfo && currentIsShortConfirmation && requestedItems.length > 0) {
  hasNewUsefulInfo = true;
}

// -----------------------------
// Sync readiness
// -----------------------------
const hasMinimumLineSyncFields = requestedItems.length > 0;

const shouldSyncOrderLines =
  hasExistingDraft === true &&
  cleanText(item.decision_mode || "AUTO") === "AUTO" &&
  hasMinimumLineSyncFields;

// -----------------------------
// Notes
// -----------------------------
const notesParts = [];

if (requestedQuantity) notesParts.push(`Qty=${requestedQuantity}`);
if (requestedCategory) notesParts.push(`Category=${requestedCategory}`);
if (requestedWeightRange) notesParts.push(`Weight=${requestedWeightRange}`);
if (requestedSex) notesParts.push(`Sex=${requestedSex}`);
if (timingPreference) notesParts.push(`Timing=${timingPreference}`);
if (collectionLocation) notesParts.push(`Location=${collectionLocation}`);

if (splitSexItems.length > 0) {
  const splitSummary = splitSexItems.map(entry => `${entry.quantity} ${entry.sex}`).join(", ");
  notesParts.push(`Split=${splitSummary}`);
}

const extraContext = cleanText(item.conversation_notes);
if (extraContext) notesParts.push(`Context=${extraContext}`);

const notes = notesParts.length > 0
  ? `Sales Summary: ${notesParts.join(" | ")}`
  : "";

// -----------------------------
// Structured state object
// -----------------------------
const orderState = {
  customer_name: cleanText(item.customer_name) === "Unknown" ? "" : cleanText(item.customer_name),
  customer_channel: cleanText(item.customer_channel),
  customer_language: customerLanguage,
  customer_message: currentMessage,
  conversation_id: cleanText(item.conversation_id),
  contact_id: cleanText(item.contact_id),
  existing_order_id: existingOrderId,
  existing_order_status: existingOrderStatus,
  conversation_mode: cleanText(item.conversation_mode || "AUTO"),
  requested_quantity: requestedQuantity,
  requested_category: requestedCategory,
  requested_weight_range: requestedWeightRange,
  requested_sex: requestedSex,
  timing_preference: timingPreference,
  timing_type: timingType,
  timing_raw: timingRaw,
  collection_location: collectionLocation,
  requested_items: requestedItems,
  split_sex_items: splitSexItems,
  has_minimum_line_sync_fields: hasMinimumLineSyncFields,
  should_sync_order_lines: shouldSyncOrderLines,
  notes,
  decision_mode: cleanText(item.decision_mode || "AUTO"),
  ai_output: cleanText(item.ai_output || ""),
  strong_intent: strongIntent,
  proceed_signal: proceedSignal,
  quote_intent: quoteIntent,
  order_commitment_intent: orderCommitmentIntent,
  conversation_commitment_intent: conversationCommitmentIntent,
  commitment_evidence: commitmentEvidence,
  short_confirmational_reply: shortConfirmationalReply,
  has_existing_draft: hasExistingDraft,
  should_enrich_existing_draft: hasExistingDraft && hasNewUsefulInfo
};

return [
  {
    json: {
      ...item,
      order_state: orderState
    }
  }
];

20. Code - Build Structured Conversation Memory
const item = $json || {};
const state = item.order_state || {};

function clean(value) {
  return String(value || "").trim();
}

const customerMessage = clean(state.customer_message || item.customer_message);
const lowerMessage = customerMessage.toLowerCase();

const requestedQuantity = clean(state.requested_quantity);
const requestedCategory = clean(state.requested_category);
const requestedWeightRange = clean(state.requested_weight_range);
const requestedSex = clean(state.requested_sex);
const timingPreference = clean(state.timing_preference);
const timingType = clean(state.timing_type);
const timingRaw = clean(state.timing_raw);
const collectionLocation = clean(state.collection_location);

const splitSexItems = Array.isArray(state.split_sex_items) ? state.split_sex_items : [];
const requestedItems = Array.isArray(state.requested_items) ? state.requested_items : [];

const existingOrderId = clean(state.existing_order_id);
const existingOrderStatus = clean(state.existing_order_status);
const hasExistingDraft = state.has_existing_draft === true;

const quoteIntent = state.quote_intent === true;
const orderCommitmentIntent = state.order_commitment_intent === true;
const proceedSignal = state.proceed_signal === true;
const strongIntent = state.strong_intent === true;

const conversationNotes = clean(item.conversation_notes || "");
const salesAgentMemory = item.sales_agent_memory || {};

// -----------------------------
// Detect common request types
// -----------------------------
const photoRequested =
  /\bphoto\b|\bphotos\b|\bpicture\b|\bpictures\b|\bimage\b|\bimages\b/i.test(lowerMessage) ||
  salesAgentMemory.photo_requested === true;

const locationAsked =
  /\bwhere are you\b|\bwhere you based\b|\blocation\b|\baddress\b|\bwhere are you located\b/i.test(lowerMessage);

const deliveryAsked =
  /\bdeliver\b|\bdelivery\b|\bcourier\b|\btransport\b/i.test(lowerMessage);

const adviceAsked =
  /\badvice\b|\bideas\b|\brecommend\b|\bsuggest\b|\bhelp me start\b|\bchecklist\b|\bfeed plan\b|\bhousing\b/i.test(lowerMessage);

const legalAsked =
  /\blegal\b|\billegal\b|\blaw\b|\bbylaw\b|\bby-law\b|\bregulation\b|\bpermit\b/i.test(lowerMessage);

const otherAnimalsAsked =
  /\bgoat\b|\bgoats\b|\bcow\b|\bcows\b|\bcattle\b|\bsheep\b|\bchicken\b|\bchickens\b/i.test(lowerMessage);

// -----------------------------
// Carried-forward known facts
// -----------------------------
const carriedKnownFacts = Array.isArray(salesAgentMemory.known_facts) ? salesAgentMemory.known_facts : [];
const carriedSummary = clean(salesAgentMemory.memory_summary);

// -----------------------------
// Conversation stage
// -----------------------------
let conversationStage = "EARLY_INQUIRY";

if (quoteIntent && !orderCommitmentIntent && !hasExistingDraft) {
  conversationStage = "QUOTE_STAGE";
} else if (hasExistingDraft) {
  conversationStage = "DRAFT_IN_PROGRESS";
} else if (orderCommitmentIntent || proceedSignal || strongIntent) {
  conversationStage = "ORDER_INTENT";
} else if (clean(salesAgentMemory.conversation_stage)) {
  conversationStage = clean(salesAgentMemory.conversation_stage);
}

// -----------------------------
// Known facts
// -----------------------------
const knownFacts = [...carriedKnownFacts];

function pushKnownFact(label, value) {
  if (!value) return;
  const entry = `${label}: ${value}`;
  if (!knownFacts.includes(entry)) {
    knownFacts.push(entry);
  }
}

pushKnownFact("Quantity", requestedQuantity);
pushKnownFact("Category", requestedCategory);
pushKnownFact("Weight range", requestedWeightRange);
pushKnownFact("Sex preference", requestedSex);

if (splitSexItems.length > 0) {
  const splitSummary = splitSexItems.map(x => `${x.quantity} ${x.sex}`).join(", ");
  const entry = `Sex split: ${splitSummary}`;
  if (!knownFacts.includes(entry)) knownFacts.push(entry);
}

pushKnownFact("Timing", timingPreference);
pushKnownFact("Collection location", collectionLocation);

if (quoteIntent && !knownFacts.includes("Customer asked for a quote")) {
  knownFacts.push("Customer asked for a quote");
}
if (photoRequested && !knownFacts.includes("Customer asked for photos")) {
  knownFacts.push("Customer asked for photos");
}
if (hasExistingDraft) {
  const draftEntry = `Existing order draft: ${existingOrderId || "yes"}`;
  if (!knownFacts.includes(draftEntry)) knownFacts.push(draftEntry);
}
if (existingOrderStatus) {
  const statusEntry = `Existing order status: ${existingOrderStatus}`;
  if (!knownFacts.includes(statusEntry)) knownFacts.push(statusEntry);
}

// -----------------------------
// Missing facts
// -----------------------------
const missingFacts = [];

const notesSuggestWeAlreadyKnowProductDirection =
  /\bweaner\b|\bpiglet\b|\bgrower\b|\bfinisher\b|\b\d+\s*(?:-|to|–)\s*\d+\s*kg\b/i.test(conversationNotes);

const hasProductDirection =
  requestedCategory !== "" ||
  requestedWeightRange !== "" ||
  notesSuggestWeAlreadyKnowProductDirection ||
  carriedKnownFacts.some(f => /Category:|Weight range:/i.test(f));

if (!hasProductDirection && !quoteIntent && !photoRequested) {
  missingFacts.push("Product direction still unclear");
}

if (
  requestedQuantity !== "" &&
  requestedCategory !== "" &&
  requestedWeightRange === "" &&
  !/\b\d+\s*(?:-|to|–)\s*\d+\s*kg\b/i.test(conversationNotes) &&
  !carriedKnownFacts.some(f => /Weight range:/i.test(f))
) {
  missingFacts.push("Weight range not yet confirmed");
}

if (
  requestedQuantity !== "" &&
  requestedWeightRange !== "" &&
  requestedCategory === "" &&
  !/\bweaner\b|\bpiglet\b|\bgrower\b|\bfinisher\b/i.test(conversationNotes) &&
  !carriedKnownFacts.some(f => /Category:/i.test(f))
) {
  missingFacts.push("Category not yet confirmed");
}

const locationKnown =
  collectionLocation !== "" ||
  carriedKnownFacts.some(f => /Collection location:/i.test(f)) ||
  /\balbertinia\b|\briversdale\b/i.test(conversationNotes);

if (
  (orderCommitmentIntent || hasExistingDraft || conversationStage === "DRAFT_IN_PROGRESS") &&
  !locationKnown
) {
  missingFacts.push("Collection location not yet confirmed");
}

const timingKnown =
  timingPreference !== "" ||
  carriedKnownFacts.some(f => /Timing:/i.test(f)) ||
  /\bnext week\b|\bfriday\b|\bfirst week of may\b|\basap\b|\b\d{1,2}\s+(?:of\s+)?(?:january|february|march|april|may|june|july|august|september|october|november|december)\b/i.test(conversationNotes);

if (
  (orderCommitmentIntent || hasExistingDraft || conversationStage === "DRAFT_IN_PROGRESS") &&
  !timingKnown
) {
  missingFacts.push("Timing not yet confirmed");
}

// -----------------------------
// Safe constraints
// -----------------------------
const behaviorConstraints = [];

behaviorConstraints.push("Do not repeat questions for facts already known.");
behaviorConstraints.push("Do not imply reservation unless backend truth later confirms it.");
behaviorConstraints.push("Do not offer delivery.");
behaviorConstraints.push("Do not offer advice, checklists, legal guidance, or outside-animal help unless explicitly allowed by policy.");
behaviorConstraints.push("If photos are requested, acknowledge the request but do not promise photos unless the media workflow/tool is actually active.");
behaviorConstraints.push("If the customer asked for a quote, treat it as quote-stage unless they clearly commit to ordering.");
behaviorConstraints.push("Keep to one next-step question maximum.");

if (deliveryAsked) behaviorConstraints.push("Customer asked about delivery; answer collection-only.");
if (legalAsked) behaviorConstraints.push("Customer asked a legal/regulatory question; do not give legal advice.");
if (otherAnimalsAsked) behaviorConstraints.push("Customer asked about animals other than pigs; state that Amadeus sells pigs only.");
if (adviceAsked) behaviorConstraints.push("Customer is asking for advice; do not drift into long educational guidance.");

// -----------------------------
// Memory summary
// -----------------------------
const memorySummaryParts = [];

memorySummaryParts.push(`Stage: ${conversationStage}.`);

if (knownFacts.length > 0) {
  memorySummaryParts.push(`Known so far: ${knownFacts.join(" | ")}.`);
} else {
  memorySummaryParts.push(`Known so far: no reliable structured facts yet.`);
}

if (missingFacts.length > 0) {
  memorySummaryParts.push(`Still missing: ${missingFacts.join(" | ")}.`);
} else {
  memorySummaryParts.push(`Still missing: nothing critical beyond normal confirmation.`);
}

memorySummaryParts.push(`Use this summary to avoid re-asking known details and to keep the reply tightly aligned to the current stage.`);

const structuredConversationMemory = {
  conversation_stage: conversationStage,
  known_facts: knownFacts,
  missing_facts: missingFacts,
  behavior_constraints: behaviorConstraints,
  photo_requested: photoRequested,
  location_asked: locationAsked,
  delivery_asked: deliveryAsked,
  legal_asked: legalAsked,
  advice_asked: adviceAsked,
  other_animals_asked: otherAnimalsAsked,
  memory_summary: memorySummaryParts.join(" ")
};

return [
  {
    json: {
      ...item,
      sales_agent_memory: salesAgentMemory,
      structured_conversation_memory: structuredConversationMemory
    }
  }
];

21. Code - Align Order Logic
const item = $json || {};
const state = item.order_state || {};
const memory = item.structured_conversation_memory || {};

function clean(value) {
  return String(value || "").trim();
}

const originalDecisionMode = clean(item.decision_mode || state.decision_mode || "AUTO");
const originalAiOutput = clean(item.ai_output || state.ai_output || "");

const requestedQuantity = clean(state.requested_quantity);
const requestedCategory = clean(state.requested_category);
const requestedWeightRange = clean(state.requested_weight_range);
const requestedSex = clean(state.requested_sex);
const timingPreference = clean(state.timing_preference);
const collectionLocation = clean(state.collection_location);

const hasExistingDraft = state.has_existing_draft === true;
const hasMinimumLineSyncFields = state.has_minimum_line_sync_fields === true;

const quoteIntent = state.quote_intent === true;
const orderCommitmentIntent = state.order_commitment_intent === true;
const conversationCommitmentIntent = state.conversation_commitment_intent === true;
const proceedSignal = state.proceed_signal === true;

const missingFacts = Array.isArray(memory.missing_facts) ? memory.missing_facts : [];
const missingWeight = missingFacts.includes("Weight range not yet confirmed");
const missingCategory = missingFacts.includes("Category not yet confirmed");
const missingTiming = missingFacts.includes("Timing not yet confirmed");
const missingLocation = missingFacts.includes("Collection location not yet confirmed");

const hasStrongStructuredRequest =
  requestedQuantity !== "" &&
  requestedCategory !== "" &&
  requestedWeightRange !== "";

const draftCoreReady =
  requestedQuantity !== "" &&
  requestedCategory !== "" &&
  requestedWeightRange !== "" &&
  timingPreference !== "" &&
  collectionLocation !== "";

let effectiveDecisionMode = originalDecisionMode;
let effectiveNeedsClarification = originalDecisionMode === "CLARIFY";
let effectiveOrderReady = false;
let replyActionType = "REPLY_INFO_ONLY";
let replyContextSummary = "";
let alignedReplySeed = clean(item.ai_output || state.ai_output || "");

if (
  originalDecisionMode === "CLARIFY" &&
  hasStrongStructuredRequest &&
  !hasExistingDraft
) {
  effectiveDecisionMode = "AUTO";
  effectiveNeedsClarification = false;
}

if (hasStrongStructuredRequest) {
  effectiveOrderReady = true;
}

if (!hasExistingDraft && quoteIntent && hasStrongStructuredRequest) {
  replyActionType = "REPLY_QUOTE_ONLY";
  replyContextSummary =
    `Customer wants quote only: Qty=${requestedQuantity}, Category=${requestedCategory}, Weight=${requestedWeightRange}` +
    (requestedSex ? `, Sex=${requestedSex}` : "") +
    (timingPreference ? `, Timing=${timingPreference}` : "") +
    (collectionLocation ? `, Location=${collectionLocation}` : "");
} else if (!hasExistingDraft && draftCoreReady && conversationCommitmentIntent) {
  replyActionType = "REPLY_DRAFT_CREATED_CANDIDATE";
  replyContextSummary =
    `Customer has draft-ready committed request: Qty=${requestedQuantity}, Category=${requestedCategory}, Weight=${requestedWeightRange}, Timing=${timingPreference}, Location=${collectionLocation}` +
    (requestedSex ? `, Sex=${requestedSex}` : "");
} else if (!hasExistingDraft && hasStrongStructuredRequest) {
  replyActionType = "REPLY_DRAFT_CREATED_CANDIDATE";
  replyContextSummary =
    `Customer has structured order request: Qty=${requestedQuantity}, Category=${requestedCategory}, Weight=${requestedWeightRange}` +
    (requestedSex ? `, Sex=${requestedSex}` : "") +
    (timingPreference ? `, Timing=${timingPreference}` : "") +
    (collectionLocation ? `, Location=${collectionLocation}` : "");
} else if (hasExistingDraft && hasMinimumLineSyncFields) {
  replyActionType = "REPLY_HEADER_AND_LINES_CANDIDATE";
  replyContextSummary =
    `Existing draft can be enriched/synced: Qty=${requestedQuantity}, Category=${requestedCategory}, Weight=${requestedWeightRange}` +
    (requestedSex ? `, Sex=${requestedSex}` : "") +
    (timingPreference ? `, Timing=${timingPreference}` : "") +
    (collectionLocation ? `, Location=${collectionLocation}` : "");
} else if (hasExistingDraft) {
  replyActionType = "REPLY_HEADER_UPDATED_CANDIDATE";
  replyContextSummary = "Existing draft present with partial new information.";
} else {
  replyActionType = "REPLY_INFO_ONLY";
  replyContextSummary = "General sales conversation or early-stage inquiry.";
}

if (replyActionType === "REPLY_QUOTE_ONLY") {
  alignedReplySeed =
    `Customer is asking for a quote only, not yet a confirmed order. Give a quote-style reply for ${requestedQuantity} ${requestedCategory} pig(s) in ${requestedWeightRange}` +
    (requestedSex ? `, sex preference ${requestedSex}` : "") +
    (timingPreference ? `, timing ${timingPreference}` : "") +
    (collectionLocation ? `, collection ${collectionLocation}` : "") +
    `. Do not imply reservation, draft confirmation, or order confirmation unless backend truth confirms it.`;
} else if (!hasExistingDraft && draftCoreReady && conversationCommitmentIntent) {
  alignedReplySeed =
    `Customer has now provided enough committed order details across the conversation to create a draft: ${requestedQuantity} ${requestedCategory} pig(s) in ${requestedWeightRange}, timing ${timingPreference}, collection ${collectionLocation}` +
    (requestedSex ? `, sex preference ${requestedSex}` : "") +
    `. Respond naturally as a committed order flow, but do not imply reservation unless backend truth later confirms it.`;
} else if (missingWeight) {
  alignedReplySeed =
    `The main missing detail is weight range. Ask only for the preferred weight range. Do not ask about sex, pricing, location, or next steps yet.`;
} else if (missingCategory) {
  alignedReplySeed =
    `The main missing detail is category/type. Ask only for the category or pig type.`;
} else if (missingTiming) {
  alignedReplySeed =
    `The main missing detail is timing. Ask only when they want to collect.`;
} else if (missingLocation) {
  alignedReplySeed =
    `The main missing detail is collection location. Ask only whether they prefer Riversdale or Albertinia.`;
}

return [
  {
    json: {
      ...item,
      structured_conversation_memory: memory,
      effective_decision_mode: effectiveDecisionMode,
      effective_needs_clarification: effectiveNeedsClarification,
      effective_order_ready: effectiveOrderReady,
      draft_core_ready: draftCoreReady,
      reply_action_type: replyActionType,
      reply_context_summary: replyContextSummary,
      aligned_reply_seed: alignedReplySeed,
      order_state: {
        ...state,
        decision_mode: effectiveDecisionMode
      }
    }
  }
];

22. Code - Should Create Draft Order?
const item = $json || {};
const state = item.order_state || {};
const memory = item.structured_conversation_memory || {};

function clean(value) {
  return String(value || "").trim();
}

const hasExistingDraft = state.has_existing_draft === true;

const requestedQuantity = clean(state.requested_quantity);
const requestedCategory = clean(state.requested_category);
const requestedWeightRange = clean(state.requested_weight_range);
const timingPreference = clean(state.timing_preference);
const collectionLocation = clean(state.collection_location);

const decisionMode = clean(
  item.effective_decision_mode ||
  item.decision_mode ||
  state.decision_mode ||
  "AUTO"
);

const quoteIntent = state.quote_intent === true;
const orderCommitmentIntent = state.order_commitment_intent === true;
const conversationCommitmentIntent = state.conversation_commitment_intent === true;
const proceedSignal = state.proceed_signal === true;
const strongIntent = state.strong_intent === true;

const missingFacts = Array.isArray(memory.missing_facts) ? memory.missing_facts : [];

const hasMinimumDraftInfo =
  requestedQuantity !== "" &&
  requestedCategory !== "" &&
  requestedWeightRange !== "";

const hasDraftCoreFields =
  requestedQuantity !== "" &&
  requestedCategory !== "" &&
  requestedWeightRange !== "" &&
  timingPreference !== "" &&
  collectionLocation !== "";

const noCriticalMissingCoreFields =
  !missingFacts.includes("Product direction still unclear") &&
  !missingFacts.includes("Weight range not yet confirmed") &&
  !missingFacts.includes("Category not yet confirmed") &&
  !missingFacts.includes("Timing not yet confirmed") &&
  !missingFacts.includes("Collection location not yet confirmed");

const hasCommitmentSignal =
  orderCommitmentIntent === true ||
  conversationCommitmentIntent === true ||
  proceedSignal === true ||
  strongIntent === true;

// Draft creation should only happen when the conversation is in AUTO mode.
// If another node says CLARIFY, do not create draft here.
const shouldCreateDraft =
  hasExistingDraft === false &&
  quoteIntent === false &&
  decisionMode === "AUTO" &&
  hasCommitmentSignal &&
  hasDraftCoreFields &&
  noCriticalMissingCoreFields;

return [
  {
    json: {
      ...item,
      should_create_draft: shouldCreateDraft,
      debug_has_existing_draft: hasExistingDraft,
      debug_has_minimum_draft_info: hasMinimumDraftInfo,
      debug_has_draft_core_fields: hasDraftCoreFields,
      debug_no_critical_missing_core_fields: noCriticalMissingCoreFields,
      debug_decision_mode: decisionMode,
      debug_quote_intent: quoteIntent,
      debug_order_commitment_intent: orderCommitmentIntent,
      debug_conversation_commitment_intent: conversationCommitmentIntent,
      debug_proceed_signal: proceedSignal,
      debug_strong_intent: strongIntent,
      debug_has_commitment_signal: hasCommitmentSignal
    }
  }
];

23. Code - Decide Order Route
const item = $json || {};
const state = item.order_state || {};

const hasExistingDraft = state.has_existing_draft === true;
const shouldCreateDraft = item.should_create_draft === true;
const shouldEnrichExistingDraft = state.should_enrich_existing_draft === true;
const shouldSyncOrderLines = state.should_sync_order_lines === true;

let orderRoute = "REPLY_ONLY";

if (shouldCreateDraft) {
  orderRoute = "CREATE_DRAFT";
} else if (hasExistingDraft && shouldEnrichExistingDraft && shouldSyncOrderLines) {
  orderRoute = "UPDATE_HEADER_AND_LINES";
} else if (hasExistingDraft && shouldEnrichExistingDraft) {
  orderRoute = "UPDATE_HEADER_ONLY";
} else {
  orderRoute = "REPLY_ONLY";
}

return [
  {
    json: {
      ...item,
      order_route: orderRoute,
      debug_should_create_draft: shouldCreateDraft,
      debug_has_existing_draft: hasExistingDraft,
      debug_should_enrich_existing_draft: shouldEnrichExistingDraft,
      debug_should_sync_order_lines: shouldSyncOrderLines
    }
  }
];
Connected to:
Switch - Route Order Action
Code - Classify Lead
Merge - Draft Result With Reply Context
Merge - Final Reply Context

24. Code - Classify Lead
This node is to help updated the labels in chatwoot so it easier to follow and filter clients. This needs to expand to ensure this is done properly and that the correct labels are added. 
const item = $json || {};
const state = item.order_state || {};

function clean(value) {
  return String(value || "").trim();
}

const currentMessage = clean(state.customer_message || item.customer_message).toLowerCase();

const hasExistingDraft = state.has_existing_draft === true;
const shouldCreateDraft = item.should_create_draft === true;
const shouldEnrichExistingDraft = state.should_enrich_existing_draft === true;
const shouldSyncOrderLines = state.should_sync_order_lines === true;

const requestedQuantity = clean(state.requested_quantity);
const requestedCategory = clean(state.requested_category);
const requestedWeightRange = clean(state.requested_weight_range);
const requestedSex = clean(state.requested_sex);
const timingPreference = clean(state.timing_preference);

const asksPrice =
  /\bprice\b|\bprices\b|\bhow much\b|\bcost\b|\bpricelist\b|\bprice list\b/i.test(currentMessage);

const asksLocation =
  /\bwhere are you\b|\bwhere you based\b|\blocation\b|\baddress\b|\bwhere are you located\b/i.test(currentMessage);

const asksAvailability =
  /\bavailability\b|\bavailable\b|\bwhat do you have\b|\bcurrent availability\b/i.test(currentMessage);

const asksPictures =
  /\bpicture\b|\bpictures\b|\bphotos\b|\bimages\b/i.test(currentMessage);

const mentionsFutureIntent =
  /\bnext week\b|\bin the week\b|\bi will come back\b|\bi'll come back\b|\bwill contact\b|\bwhen i'm ready\b|\bcome back to you\b|\blater\b/i.test(currentMessage);

const explicitProceedIntent =
  /\bi want\b|\bi need\b|\bi will order\b|\bi'll order\b|\bi'll take\b|\breserve\b|\bproceed\b|\bgo ahead\b|\byes please\b/i.test(currentMessage);

const hasSpecificProductSignal =
  requestedCategory !== "" ||
  requestedWeightRange !== "" ||
  requestedSex !== "";

const hasStrongCommercialSignal =
  requestedQuantity !== "" && (requestedCategory !== "" || requestedWeightRange !== "");

let lead_status = "NONE";

// Never label if the conversation is already actively moving through order routes
if (!hasExistingDraft && !shouldCreateDraft && !shouldEnrichExistingDraft && !shouldSyncOrderLines) {
  if (
    hasStrongCommercialSignal ||
    (explicitProceedIntent && hasSpecificProductSignal) ||
    (mentionsFutureIntent && hasSpecificProductSignal)
  ) {
    lead_status = "HOT";
  } else if (
    asksPrice ||
    asksLocation ||
    asksAvailability ||
    asksPictures ||
    mentionsFutureIntent
  ) {
    lead_status = "WARM";
  }
}

return [
  {
    json: {
      ...item,
      lead_status,
      debug_lead_has_existing_draft: hasExistingDraft,
      debug_lead_should_create_draft: shouldCreateDraft,
      debug_lead_should_enrich_existing_draft: shouldEnrichExistingDraft,
      debug_lead_should_sync_order_lines: shouldSyncOrderLines
    }
  }
];

25. Switch - Lead Type
{{$json.lead_status}} = WARM
{{$json.lead_status}} = HOT

26. (WARM) HTTP - Add Chatwoot Label - Warm
26. (HOT) HTTP - Add Chatwoot Label - Hot

27. Switch - Route Order Action
This is the route split switch node that pics the path to take. 
{{$json.order_route}} = CREATE_DRAFT
{{$json.order_route}} = UPDATE_HEADER_ONLY
{{$json.order_route}} = UPDATE_HEADER_AND_LINES
{{$json.order_route}} = CANCEL_ORDER
{{$json.order_route}} = CANCEL_PENDING
{{$json.order_route}} = CLEAR_PENDING
{{$json.order_route}} = REPLY_ONLY



Phase 1.2b Customer Cancel Wiring

Customer cancellation now uses a two-turn confirmation flow instead of cancelling on the first mention.

Chatwoot custom attribute:

- `pending_action = cancel_order` is set when the customer first asks to cancel an active order.
- `pending_action` is cleared when the customer does not confirm, when a new draft context is saved, or after the cancel backend call returns.

Routing rules in `Code - Decide Order Route`:

1. `CANCEL_ORDER` is evaluated first when `pending_action = cancel_order`, an active draft exists, and the customer gives a proceed/yes confirmation.
2. `CANCEL_PENDING` is used when the customer asks to cancel but has not confirmed yet.
3. `CLEAR_PENDING` is used when a previous cancel confirmation was pending and the customer sends a non-confirming message.
4. Create/update routes are evaluated only after the cancel guards.

Cancel branch nodes:

- `Set - Build Cancel Order Payload`
- `Call 1.2 - Cancel Order`
- `HTTP - Clear Pending After Cancel`
- `Set - Restore Cancel Result`

Pending/clear branch nodes:

- `HTTP - Set Pending Cancel Action`
- `HTTP - Clear Pending Action`

Sam response rule: Sam must only say an order is cancelled after `Call 1.2 - Cancel Order` returns `success = true`. If the backend returns an error, Sam must explain that the order was not changed.

---

## CHATWOOT ATTRIBUTE RULE (Standing Rule — Must Not Break)

Chatwoot's custom attributes API performs a **full object replace**, not a merge. Any write to `custom_attributes` that omits a field will erase that field for the rest of the conversation.

**Every node that writes to Chatwoot `custom_attributes` must include the core four order context fields every time:**

| Field | Value |
| --- | --- |
| `order_id` | current order ID (from order context or result) |
| `order_status` | current order status |
| `conversation_mode` | `AUTO` or `HUMAN` (never omit) |
| `pending_action` | `cancel_order` or `""` (never omit) |

Escalation-specific nodes may additionally include `escalation_ticket_id`, `last_escalated_at`, `last_human_replay` — but must still include the four core fields above.

**Nodes that write Chatwoot attributes in this workflow and what they must include:**

| Node | Trigger | order_id source | order_status source |
| --- | --- | --- | --- |
| `HTTP - Set Conversation Order Context` | After CREATE_DRAFT | `$json.order_id` (1.2 result) | `$json.order_status` |
| `HTTP - Set Pending Cancel Action` | CANCEL_PENDING route | `ExistingOrderId` from normalize | `ExistingOrderStatus` from normalize |
| `HTTP - Clear Pending Action` | CLEAR_PENDING route | `ExistingOrderId` from normalize | `ExistingOrderStatus` from normalize |
| `HTTP - Clear Pending After Cancel` | After cancel confirmed | `$json.order_id` (1.2 result) | `$json.order_status` (1.2 result) |
| `HTTP - Set Conversation Human Mode` | ESCALATE route | `ExistingOrderId` from normalize | `ExistingOrderStatus` from normalize |

**Before adding any new Chatwoot HTTP write node, verify it sends all four core fields. Before editing an existing write node, check the other three fields are not being removed.**

Root cause found (2026-04-28): `HTTP - Set Pending Cancel Action` was only writing `pending_action`, which erased `order_id` and `order_status` from Chatwoot. On the next customer turn, `ExistingOrderId` came back empty, so the cancel confirmation flow could not find the order to cancel and fell through to CREATE_DRAFT.

Root cause found (2026-04-29): `HTTP - Set Conversation Human Mode` was only writing `conversation_mode`, `escalation_ticket_id`, `last_escalated_at`, and `last_human_replay` — erasing `order_id`, `order_status`, and `pending_action`. After a customer was escalated and the human did not immediately reply, the customer's next message arrived with no order context.

Fix applied: all five Chatwoot write nodes now send full snapshots including order context.

---

## CREATE DRAFT Data Flow Rule (Standing Rule)

After `Call 1.2 - Create Draft Order` returns, the 1.2 result replaces `$json`. The full customer context (`order_state`, `customer_name`, etc.) is no longer in `$json` at that point.

**Rule: never route the 1.2 result directly through a Chatwoot HTTP node as the sole data path to the merge or AI agent.** The Chatwoot HTTP node's output is the Chatwoot API response, not the order context.

**Current approved pattern for CREATE DRAFT:**

```
Code - Store Draft Order Context
    ├── HTTP - Set Conversation Order Context   [Chatwoot write — leaf node, no merge connection]
    └── Merge - Draft Result With Reply Context [index 1]   [carries order_id to AI agent]

Code - Decide Order Route
    └── Merge - Draft Result With Reply Context [index 0]   [carries full customer context]

Merge - Draft Result With Reply Context (combineByPosition)
    [0] full customer context + [1] 1.2 result with order_id
    → Ai Agent - Sales Agent
```

The merge combines both: `order_id` comes from [1], all customer context comes from [0]. The AI agent receives the correct `order_id` in its prompt.

Root cause found (2026-04-29): The HTTP node was in the chain between `Code - Store Draft Order Context` and the merge, replacing `$json` with the Chatwoot API response. The order_id was never reaching the AI agent prompt (`OrderID: none`).

Fix applied (2026-04-29): `Code - Store Draft Order Context` now fans out to the Chatwoot HTTP node and directly to the reply merge. The Chatwoot write is a leaf node, so its API response cannot replace the created order context before Sam receives it.

Fix C Option B1 update (2026-04-29): first-turn line sync is no longer performed inside `1.0`. `Set - Draft Order Payload` sends `action = create_order_with_lines` when `order_state.requested_items[]` is non-empty. `1.2 - Order Steward` then owns the full create + sync operation and returns one combined result.

CREATE DRAFT
28. Set - Draft Order Payload
action = string = `create_order_with_lines` when `order_state.requested_items[]` is non-empty, otherwise `create_order`
customer_name = string = {{$json.order_state.customer_name}}
customer_channel = string = {{$json.order_state.customer_channel}}
customer_language = string = {{$json.order_state.customer_language}}
order_source = string = Sam
requested_category = string = {{$json.order_state.requested_category}}
requested_weight_range = string = {{$json.order_state.requested_weight_range}}
requested_sex = string = {{$json.order_state.requested_sex}}
requested_quantity = string = {{$json.order_state.requested_quantity}}
quoted_total = string = ""
collection_location = string = {{$json.order_state.collection_location}}
payment_method = string = {{$json.order_state.payment_method}}
notes = string = {{$json.order_state.notes}}
changed_by = string = Sam
conversation_id = string = {{$json.order_state.conversation_id}}
contact_id = string = {{$json.order_state.contact_id}}
customer_number = string = {{$json.order_state.customer_number}}
requested_items = array = {{$json.order_state.requested_items || []}}

Action expression:

```
{{ Array.isArray($json.order_state?.requested_items) && $json.order_state.requested_items.length > 0 ? 'create_order_with_lines' : 'create_order' }}
```

29. Call 1.2 - Create Draft Order

30. Code - Store Draft Order Context
Restores the full pre-create customer context after `Call 1.2 - Create Draft Order`, then patches the new `order_id` into the top-level item and `order_state`.

Important output fields:

- `order_id`
- `order_status`
- `order_route = CREATE_DRAFT`
- `action = create_order` or `create_order_with_lines`
- `success`
- `sync_success` when `create_order_with_lines` was used
- `sync_message` when `create_order_with_lines` was used

31. HTTP - Set Conversation Order Context
Writes the new order context to Chatwoot custom_attributes so the next customer turn can read it.
Must always send the full core snapshot (see CHATWOOT ATTRIBUTE RULE above), including `payment_method`.
{
  "custom_attributes": {
    "order_id": "{{ $json.order_id }}",
    "order_status": "{{ $json.order_status }}",
    "conversation_mode": "AUTO",
    "pending_action": "",
    "payment_method": "{{ $json.payment_method || $('Code - Normalize Incoming Message').item.json.PaymentMethod || '' }}"
  }
}
Connected to:
LEAF NODE — no outgoing connection. Chatwoot write fires but its response is not used in the data chain.

NOTE: This node used to connect to the merge, which meant the Chatwoot API response replaced the order context before reaching the AI agent. Fixed 2026-04-29 — see CREATE DRAFT Data Flow Rule above.

32. Merge - Draft Result With Reply Context
Receives two inputs via combineByPosition:
- Input [0]: from Code - Decide Order Route fan-out → full customer context (order_state, memory, etc.)
- Input [1]: from `Code - Store Draft Order Context` with the `1.2` result and created `order_id`
Fields from [1] override matching fields from [0]. order_id is correctly available after the merge.
Connected to:
Code - Slim Sales Agent User Context

Superseded Option A note:

The following nodes were removed before going live because create+sync ownership belongs in `1.2`, not `1.0`:

- `IF - Draft Has Requested Items`
- `Code - Build Sync New Draft Lines Payload`
- `Call 1.2 - Sync New Draft Lines`
- `Code - Restore Draft Sync Result`

UPDATED HEADERS ONLY
28. Code - Build Enrich Existing Draft Payload
const item = $json || {};
const state = item.order_state || {};

const existingOrderId = String(state.existing_order_id || "").trim();

if (!existingOrderId) {
  throw new Error("existing_order_id is required for enrich update.");
}

const enrichPayload = {
  action: "update_order",
  order_id: existingOrderId,
  changed_by: "Sam"
};

if (state.requested_quantity !== undefined && state.requested_quantity !== null && String(state.requested_quantity).trim() !== "") {
  enrichPayload.requested_quantity = state.requested_quantity;
}

if (state.requested_category !== undefined && state.requested_category !== null && String(state.requested_category).trim() !== "") {
  enrichPayload.requested_category = String(state.requested_category).trim();
}

if (state.requested_weight_range !== undefined && state.requested_weight_range !== null && String(state.requested_weight_range).trim() !== "") {
  enrichPayload.requested_weight_range = String(state.requested_weight_range).trim();
}

if (state.requested_sex !== undefined && state.requested_sex !== null && String(state.requested_sex).trim() !== "") {
  enrichPayload.requested_sex = String(state.requested_sex).trim();
}

if (state.collection_location !== undefined && state.collection_location !== null && String(state.collection_location).trim() !== "") {
  enrichPayload.collection_location = String(state.collection_location).trim();
}

if (state.notes !== undefined && state.notes !== null && String(state.notes).trim() !== "") {
  enrichPayload.notes = String(state.notes).trim();
}

if (state.detected_payment_method === "Cash" || state.detected_payment_method === "EFT") {
  enrichPayload.payment_method = state.detected_payment_method;
}

const sentFieldCount =
  (enrichPayload.requested_quantity !== undefined ? 1 : 0) +
  (enrichPayload.requested_category !== undefined ? 1 : 0) +
  (enrichPayload.requested_weight_range !== undefined ? 1 : 0) +
  (enrichPayload.requested_sex !== undefined ? 1 : 0) +
  (enrichPayload.collection_location !== undefined ? 1 : 0) +
  (enrichPayload.notes !== undefined ? 1 : 0) +
  (enrichPayload.payment_method !== undefined ? 1 : 0);

if (sentFieldCount === 0) {
  throw new Error("No enrichable non-empty fields were available to update the existing draft.");
}

return [
  {
    json: {
      ...item,
      enrich_payload: enrichPayload,
      action: enrichPayload.action,
      order_id: enrichPayload.order_id,
      requested_quantity: enrichPayload.requested_quantity ?? null,
      requested_category: enrichPayload.requested_category ?? null,
      requested_weight_range: enrichPayload.requested_weight_range ?? null,
      requested_sex: enrichPayload.requested_sex ?? null,
      collection_location: enrichPayload.collection_location ?? null,
      timing_preference: state.timing_preference ?? "",
      timing_type: state.timing_type ?? "",
      timing_raw: state.timing_raw ?? "",
      notes: enrichPayload.notes ?? null,
      payment_method: enrichPayload.payment_method ?? null,
      changed_by: enrichPayload.changed_by
    }
  }
];

29. Set - Enrich Existing Draft Payload
action = string = {{$json.enrich_payload.action}}
order_id = string = {{$json.enrich_payload.order_id}}
requested_quantity = string = {{$json.enrich_payload.requested_quantity || ""}}
requested_category = string = {{$json.enrich_payload.requested_category || ""}}
requested_weight_range = string = {{$json.enrich_payload.requested_weight_range || ""}}
requested_sex = string = {{$json.enrich_payload.requested_sex || ""}}
notes = string = {{$json.enrich_payload.notes || ""}}
payment_method = string = {{$json.enrich_payload.payment_method || ""}}

30. HTTP - Set Conversation Context After Update
Writes the full Chatwoot attribute snapshot after `update_order` succeeds. This is required because the update/enrich path does not use `HTTP - Set Conversation Order Context`.

Important value priority:

- new value from `Code - Build Enrich Existing Draft Payload.payment_method`
- existing value from `Code - Normalize Incoming Message.PaymentMethod`
- blank

Required body shape:

{
  "custom_attributes": {
    "order_id": "{{ $('Code - Normalize Incoming Message').item.json.ExistingOrderId }}",
    "order_status": "{{ $('Code - Normalize Incoming Message').item.json.ExistingOrderStatus }}",
    "conversation_mode": "AUTO",
    "pending_action": "{{ $('Code - Normalize Incoming Message').item.json.PendingAction }}",
    "payment_method": "{{ $('Code - Build Enrich Existing Draft Payload').item.json.payment_method || $('Code - Normalize Incoming Message').item.json.PaymentMethod || '' }}"
  }
}

Live verification:

- `Cash` and `EFT` update `ORDER_MASTER.Payment_Method`
- Chatwoot `custom_attributes.payment_method` updates on the same turn
- next-turn `Code - Normalize Incoming Message.PaymentMethod` reads the stored value
changed_by = string = {{$json.enrich_payload.changed_by}}

30. Call 1.2 - Update Existing Draft
Connected to
Merge - Final Reply Context input 2

31. Merge - Final Reply Context
Connected to
Code - Slim Sales Agent User Context

UPDATED HEADERS AND LINES
28. Code - Build Sync Existing Draft Payload
const item = $json || {};
const state = item.order_state || {};

const existingOrderId = String(state.existing_order_id || "").trim();

if (!existingOrderId) {
  throw new Error("existing_order_id is required for sync order lines.");
}

if (!Array.isArray(state.requested_items) || state.requested_items.length === 0) {
  throw new Error("requested_items is required for sync order lines.");
}

const syncPayload = {
  action: "sync_order_lines_from_request",
  order_id: existingOrderId,
  changed_by: "Sam",
  requested_items: state.requested_items
};

return [
  {
    json: {
      ...item,
      sync_payload: syncPayload
    }
  }
];

29. Set - Sync Existing Draft Payload
action = string = {{$json.sync_payload.action}}
order_id = string = {{$json.sync_payload.order_id}}
changed_by = string = {{$json.sync_payload.changed_by}}
requested_items = array = {{$json.sync_payload.requested_items}}


30. Call 1.2 - Sync Order Lines
Connected to 
Merge - Final Reply Context input 2


31a. Code - Slim Sales Agent User Context
Runs immediately before the Sales Agent on all four main input paths (CLARIFY, Merge - Final Replay Context, Merge - Draft Result With Reply Context, REPLY_ONLY branch of `Switch - Route Order Action`).
Produces two new fields:
- `sam_order_state_slim`: whitelist copy of `order_state` — `customer_name`, `customer_language`, `existing_order_id`, `existing_order_status`, `conversation_mode`, `pending_action` (if set), `payment_method` (Cash/EFT only, from detected or header), request fields (`requested_quantity`, `requested_category`, `requested_weight_range`, `requested_sex`, `timing_preference`, `collection_location`), intent flags (`quote_intent`, `order_commitment_intent`, `conversation_commitment_intent`, `cancel_order_intent`, `send_for_approval_intent`, `has_existing_draft` when present), and `requested_items_compact` (max 5 × `{ qty, sex, category, weight_range }`). Order route is **not** duplicated here; Sam still receives **`OrderAction`** from top-level `order_route` in the agent user prompt.
- `sam_steward_result_compact`: when steward-related fields exist — `success`, truncated `message`, `backend_success`, truncated `backend_error`, and optional `had_errors` + `summary` from `results[]` (sync line outcomes). Top-level `order_id` / `order_status` remain on the item for the template lines `OrderID` / `FinalOrderStatus`.
The full item is merged onto the output (`Object.assign`) so downstream behavior is unchanged; only the Sales Agent prompt uses the slim summaries instead of `JSON.stringify(order_state)`.
Connected to:
Ai Agent - Sales Agent

31. (CLARIFY) Ai Agent - Sales Agent
This agent is used to respond to the client based off all the info provided
Model: ChatGPT
Memory: Simple Memory
Tools: Read SALES_STOCK_SUMMARY
Read SALES_STOCK_TOTALS
Read SALES_STOCK_DETAIL
Read SALES_AVAILABILITY
Farm_Info_Doc

32. Code - Clean Final Reply
const currentItem = $json || {};

// Always use output as the single source of truth
let raw = String(currentItem.output || "").trim();

// Failsafe: prevent sending empty messages
if (!raw) {
  raw = "Sorry, something went wrong on our side. Please try again.";
}

// Remove obvious tool/debug noise only if present
let cleaned = raw
  .replace(/^Tool:.*$/gim, "")
  .replace(/^Tools?:.*$/gim, "")
  .replace(/^Observation:.*$/gim, "")
  .replace(/^Thought:.*$/gim, "")
  .replace(/^Action:.*$/gim, "")
  .replace(/^Action Input:.*$/gim, "");

// Tidy blank lines
cleaned = cleaned.replace(/\n{3,}/g, "\n\n").trim();

return [
  {
    json: {
      ...currentItem,
      cleaned_reply: cleaned
    }
  }
];

33. HTTP - Send Chatwoot Reply

---

## Phase 1.2c — Escalation Path Attribute Fix (2026-04-29)

### Problem

The escalation path in 1.0 had two attribute write gaps that could erase order context from Chatwoot:

**Gap 1 — `HTTP - Set Conversation Human Mode`**
When a conversation was escalated, this node wrote only `conversation_mode`, `escalation_ticket_id`, `last_escalated_at`, and `last_human_replay`. It did not include `order_id`, `order_status`, or `pending_action`. If the human did not reply immediately and the customer sent another message, the next turn arrived with no order context — ExistingOrderId was empty and routing broke.

**Gap 2 — `Edit - Keep Chatwoot ID's` missing order fields**
This node was not carrying `existing_order_id`, `existing_order_status`, or `conversation_mode` forward. The Escalation Classifier prompt therefore had no awareness of active orders, and could incorrectly route a cancel request to ESCALATE instead of AUTO.

**Gap 3 — `Ai Agent - Escalation Classifier` blind to order context**
The classifier prompt did not receive ExistingOrderId, ExistingOrderStatus, or PendingAction. With no order context, it had no basis to know that a "cancel order" request should route to AUTO (handled by the cancel workflow) rather than ESCALATE (hand to human).

**Gap 4 — 1.1 `Release Conversation to Auto` erasing order context**
When the human replied via Telegram and 1.1 fired, it reset Chatwoot attributes with only `conversation_mode: AUTO` and cleared escalation fields. `order_id`, `order_status`, and `pending_action` were not included, erasing them. The customer's next message after a human reply had no order context.

---

### Fixes Applied

**1.0 — `HTTP - Set Conversation Human Mode`**
Now writes all seven Chatwoot fields on escalation: `order_id`, `order_status`, `conversation_mode`, `pending_action`, `escalation_ticket_id`, `last_escalated_at`, `last_human_replay`. Sources `order_id`/`order_status`/`pending_action` from `Code - Normalize Incoming Message`.

**1.0 — `Edit - Keep Chatwoot ID's`**
Now carries three additional fields: `existing_order_id`, `existing_order_status`, `conversation_mode`. These flow to `If - Is Human Lock Active?` and are available to the Escalation Classifier via `$('If - Is Human Lock Active?').item.json.*`.

**1.0 — `Ai Agent - Escalation Classifier` (user prompt)**
Now includes:
```
ExistingOrderId: {{ $('If - Is Human Lock Active?').item.json.existing_order_id || 'none' }}
ExistingOrderStatus: {{ $('If - Is Human Lock Active?').item.json.existing_order_status || 'none' }}
PendingAction: {{ $('If - Is Human Lock Active?').item.json.pending_action || '' }}
```

**1.0 — `Ai Agent - Escalation Classifier` (system prompt)**
Added cancel routing rule in the AUTO section:
> If ExistingOrderId is present (not empty and not "none") and the customer is asking to cancel their order, treat this as AUTO. The backend cancellation workflow handles this automatically — do not escalate routine order cancellation to a human.

**1.0 — `Edit - Build Ticket Data`**
Now writes three additional fields to the `Sales_HumanEscalations` sheet: `WebOrderId`, `WebOrderStatus`, `WebPendingAction`. This allows 1.1 to read them back when the human replies.

**1.1 — `Release Conversation to Auto`**
Now reads `WebOrderId`, `WebOrderStatus`, `WebPendingAction` from `Get Ticket Detail` (sheet lookup) and includes them in the Chatwoot reset so order context is preserved after the human reply.

JSON body after fix:
```json
{
  "custom_attributes": {
    "order_id": "{{ $('Get Ticket Detail').item.json.WebOrderId }}",
    "order_status": "{{ $('Get Ticket Detail').item.json.WebOrderStatus }}",
    "conversation_mode": "AUTO",
    "pending_action": "{{ $('Get Ticket Detail').item.json.WebPendingAction }}",
    "escalation_ticket_id": "",
    "last_human_replay": "",
    "last_escalated_at": ""
  }
}
```

---

### Required Manual Action

The `Sales_HumanEscalations` Google Sheet must have three new columns added:
- `WebOrderId`
- `WebOrderStatus`
- `WebPendingAction`

These must exist in the sheet header before 1.0's ticket-creation node can write to them. Existing rows without values are fine — they will be blank until a new escalation fires.

Status: columns added to sheet 2026-04-29. Awaiting live import and end-to-end verification.

---

## Phase 5.2 Active Customer Order Lookup Fallback

Added 2026-05-11.

Purpose:

- Recover safe active-order context when Chatwoot does not have `ExistingOrderId`.
- Keep Sam behind backend-filtered order lookup instead of direct sheet access.
- Avoid calling the lookup on normal new sales messages.

Flow:

1. Existing exact-order path remains first: if `ExistingOrderId` exists, `1.0` calls `1.2` action `get_order_context`.
2. If no exact order ID exists, `Code - Skip Order Context Fetch` now detects saved-order review/cancel/document-style wording.
3. `If - Active Customer Lookup Needed` routes only those messages to `1.2`.
4. `Code - Build Active Customer Lookup Payload` sends `action = get_active_customer_order_context` and prefers `conversation_id`; `customer_phone` is sent only when no conversation ID is available.
5. `Call 1.2 - Get Active Customer Order Context` runs the steward lookup.
6. `Code - Attach Active Customer Order Context` injects a single match into the existing order-state context shape, or passes multiple-match/no-match status to Sam as compact review context.

Trigger examples:

- "What is on my order?"
- "Order status"
- "Is my order approved?"
- "Cancel my order"
- "Send my quote"
- "Send my invoice"

Non-trigger example:

- "I want 2 piglets"

Safety rule:

If multiple active orders match, Sam must ask one disambiguation question. If no active order matches, Sam must not invent an order.

Live test note:

- 2026-05-11 clean-conversation test found that `HTTP - Get Conversation Messages` must not build its Chatwoot URL from `conversation.messages[0].account_id` or `conversation.messages[0].conversation_id`, because those fields can be missing on webhook payloads.
- The export now uses the normalized IDs from `Code - Normalize Incoming Message` / `Edit - Keep Chatwoot ID's` for the Chatwoot history URL.

## Phase 5.3 Sam Order-Review Wording Guard

Added 2026-05-11.

Purpose:

- Make current-order review replies safer and clearer.
- Ensure Sam answers from backend/steward context before using conversation memory.
- Prevent Sam from claiming approval, reservation, collection, document links, or document delivery unless backend context confirms it.

Prompt guard:

`Ai Agent - Sales Agent` system prompt now includes `ORDER REVIEW RESPONSE RULES`.

Required behavior:

- Single matched active order: answer about that order only.
- Multiple active matches: ask one short disambiguation question.
- No active match: ask for the order reference instead of inventing an order.
- Missing-detail prompts such as "What is still missing?" trigger active-order lookup when no `ExistingOrderId` is present.
- Draft: not approved, not reserved, not confirmed.
- Pending Approval: submitted/pending, not approved.
- Approved: approved only when backend confirms it.
- Quote/invoice follow-up: do not invent links or say sent unless document context exists.
