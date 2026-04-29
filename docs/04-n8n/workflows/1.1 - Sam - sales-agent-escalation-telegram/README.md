# Sales Agent Escalation Telegram

## n8n Workflow Name

`1.1 - Sam - Sales Agent - Escalation Telegram`

## Purpose

This is the Escaltion workflow. This was build before using google sheets / forms and tracking but I think this can be simplified. Since we don't use the google forms anymore. I think it's good to log the escalation but then we need to ensure that once this was responded too it gets marked and correctly updated. 

Once the Telegram is send and the response was triggered it would be nice to have the telegram messaged response and the original messaged sent deleted so the chat stay clean. 

The current set up is to only send escalations to me, but when we do set up the users and things it would be good to prepare this one and make it able to send to other users as well not just me. 

## Export File

The current n8n export is stored in `workflow.json`.

## Migration Note

This folder is now the canonical home for the `1.1 - SAM - Sales Agent - Escalation Telegram` workflow notes and export.


## Trigger / Called By
Telegram Escalation Trigger
This has a restriction: Restrict to Chat ID's : 5721652188 (which is my persaonla one)

## Inputs
Fields it expects.

## Outputs
[
  {
    "update_id": 925267964,
    "message": {
      "message_id": 348,
      "from": {
        "id": 5721652188,
        "is_bot": false,
        "first_name": "Charl",
        "last_name": "Nieuwendyk",
        "username": "CharlNPersonal",
        "language_code": "en"
      },
      "chat": {
        "id": 5721652188,
        "first_name": "Charl",
        "last_name": "Nieuwendyk",
        "username": "CharlNPersonal",
        "type": "private"
      },
      "date": 1771756490,
      "text": "AMAD-20260323-185058\nGood evening, we do not offer delivery. All pick ups are done for Riversdale, Western Cape."
    }
  }
]

## Main Flow
1. Telegram Escalation Trigger
This is the trigger node and this is only linked to my personal telegram Id for now. AS I deal with all escalations.

2. Parse Human Replay
// Get the raw text from Telegram
const raw =
  $json.message?.text ??
  $json.body?.message?.text ??
  $json.text ??
  "";

// Normalize newlines + trim
const text = String(raw).replace(/\r\n/g, "\n").trim();

// 1) Try: ticket is the FIRST non-empty line
const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
let ticket = lines[0] || "";

// 2) If the first line isn't a valid ticket, search anywhere in the message
// Adjust the pattern if your ticket format changes.
const match = text.match(/AMAD-\d{8}-\d{6}/);
if (!ticket.match(/AMAD-\d{8}-\d{6}/) && match) {
  ticket = match[0];
}

// 3) Build the reply: remove ticket from the beginning if it’s there,
// otherwise remove only the first occurrence found.
let reply = text;

// If the message starts with the ticket (even with spaces), strip that line
if (lines.length && lines[0].includes(ticket)) {
  reply = text.split("\n").slice(1).join("\n").trim();
} else if (ticket) {
  reply = text.replace(ticket, "").trim();
}

// Final cleanup (remove leftover "This", etc. if it was part of the ticket line)
reply = reply.replace(/^\s*[-–—:]\s*/, "").trim();

return [
  {
    TicketID: ticket,
    HumanReply: reply,
    TelegramUserID: $json.message?.from?.id ?? $json.from?.id ?? $json.TelegramUserID
  }
];

3. Get Ticket Detail
Read: sheet
Operations: Get Ros(s)
Filters: TicketID = {{ $json.TicketID }}
Return only Fist: True

4. Ai Agent - Polish Human Replay
Prompt (User Message): Here is the human-written reply to the customer:

"{{ $('Parse Human Replay').item.json.HumanReply }}"

Please polish this reply according to the system instructions.

System Message: You are the Amadeus Sales Agent reply polisher.
A human from the farm has already written a reply to a customer.
Your ONLY job is to improve grammar, clarity, and tone while keeping:
– all prices, numbers and discounts exactly the same
– all promises, conditions and decisions exactly the same
Do NOT add new information, do NOT change offers, do NOT change meaning.
Return ONLY the final text that should be sent to the customer

5. Send Chatwoot Final Reply
Method: POST
URL: {{ 'https://app.chatwoot.com/api/v1/accounts/' + $node["Get Ticket Detail"].json["WebAccountID"] + '/conversations/' + $node["Get Ticket Detail"].json["WebConversationID"] + '/messages' }}
Send Headers: True
Specify Headers: Using Fields Below
Headers:
api_access_token = 
Content_Type = application/json
Send Body: True
Body Content Type: JSON
Specific Body: Using Fields Below:
content = {{ $json.output }}
message_type = outgoing
private = false

6. Mark Ticket Asnwered
updated sheet
Operation: Update Row
Mapping Column Mode: Mape Each Column Manually
Column to match on: TicketID
Values to Update:
TicketID: {{$node["Get Ticket Detail"].json["TicketID"]}}
Channel: ""
UserID: ""
UserName: ""
UserMessage: ""
BotSummary: ""
ConversationHistory: ""
Status: ANSWERED
CreatedAt: ""
AnsweredAt: {{$now}}
FinalReplaySent: TRUE

7. Mark Replay Processed
updated sheet
Operations: Update Row
Mapping Column Mode: Mape Each Column Manually
Column to match on: TicketID
Values to Update:
TicketID: {{$node["Get Ticket Detail"].json["TicketID"]}}
TimeStamp: ""
UserName: ""
Channel: ""
UserID: ""
YourReplayText: ""
InternalNotes: ""
Priority: ""
Processed: TRUE

8. Release Conversation to Auto
Method: POST
URL: https://app.chatwoot.com/api/v1/accounts/{{ $('Get Ticket Detail').item.json.WebAccountID }}/conversations/{{ $('Get Ticket Detail').item.json.WebConversationID }}/custom_attributes
Send Headers: TRUE
Specify Headers: Using Fields Below
Headers: 
Content_Type = Content-Type
api_access_token = 
Send Body: TRUE
Body Content Type: JSON
Specify Body: Using JSON
JSON:
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

IMPORTANT: Chatwoot custom_attributes is a full object replace. This node must include order_id, order_status, and pending_action so they are not erased when the conversation is returned to AUTO. These values come from WebOrderId, WebOrderStatus, WebPendingAction stored in the Sales_HumanEscalations sheet at escalation time by 1.0's Edit - Build Ticket Data node.

Required sheet columns (must exist in Sales_HumanEscalations):
- WebOrderId
- WebOrderStatus
- WebPendingAction

9. Delete a Chat message
This node was added to ensure the Escalation messages get deleted once done but I want include the actual Escalation messaged generated as well not just the response I send. This way the chat stays clean. 
Credential: Telegram - Sam
Resource: Message
Operation: Delete Chat Message
Chat ID: {{ $('Telegram Escalation Trigger').item.json.message.from.id }}
Message ID: {{ $('Telegram Escalation Trigger').item.json.message.message_id }}

## Tools / Sheets / APIs Used
Sheets, backend endpoints, Telegram, Chatwoot, etc.

## Important Rules
What must not be changed.

## Known Issues / Questions
1. Can we look at compiling escalations, since there can be like 3 happening straight after each other and we just log it as one. If the open Escalations is closed only then a new one is made. This means the Old Escalation messaged gets deleted and a updated versions is given with the updated summary and all. This way the chat is clean and only the latest shows. 
2. Deleting completed escalations. botht the escalation message generated and the response. 