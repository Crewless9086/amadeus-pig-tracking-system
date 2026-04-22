1. PURPOSE
This document maps the exact execution flow of the n8n workflow:

Node sequence
Node purpose
Data responsibility
Routing behavior

This is the authoritative reference for:

debugging
modifying workflows
onboarding AI agents (Cursor)


2. ENTRY POINT
Node: Chatwoot Webhook
Role:
Receives incoming message from Chatwoot.
Creates:

CustomerMessage
ConversationHistory
Metadata (contact, conversation, inbox, etc.)

Rule:
This is the raw input layer. No logic here.

3. NORMALIZATION LAYER

Node: Code - Normalize Incoming Message
Role:
Standardizes incoming message format.
Ensures:

message is always in a usable text format


Node: Switch - Message Type
Role:
Routes based on message type.
Branches:

Text
Audio


Node: HTTP - Transcribe Audio
Role:
Converts audio → text

Node: Merge - Combine Message Paths
Role:
Ensures unified message stream regardless of type

Node: Code - Build Conversation Context
Role:
Builds:

ConversationHistory
structured context for AI


4. ESCALATION LAYER

Node: Escalation Classifier
Role:
AI classification:

AUTO
CLARIFY
ESCALATE

Output:

output (JSON string)


Node: Code - Normalize Escalation Output
Role:
Preserves classifier output
Creates:

escalation_raw_output


Node: Code - Parse Escalation Decision
Role:
Extracts structured decision
Creates:

decision
decision_mode
route
reason
confidence
summary


Node: Switch - Route by Mode
Role:
Routes:

ESCALATE → human flow
AUTO → continue to AI


5. AI RESPONSE LAYER

Node: AI Sales Agent
Role:
Primary conversational AI
Output:

output (natural reply)


Node: Code - Normalize AI Reply Output
Role:
Locks AI reply
Creates:

ai_reply_output

Critical Rule:
This is the first valid reply to user

Node: Merge - Reattach Sales Context After AI
Role:
Reattaches:

escalation data
conversation metadata

Risk:
Field collision on output

6. DECISION SPLIT (POST-AI)

Node: Switch - Post AI Mode
Input:

decision_mode

Branches:

CLARIFY
AUTO


7. CLARIFY PATH

Node: Code - Prepare Clarify Reply
Role:
Finalizes clarify response
Sets:

output = ai_reply_output
reply_mode = CLARIFY

Critical Rule:
This node locks the reply

Node: Code - Clean Final Reply
Role:
Sanitizes reply
Creates:

cleaned_reply


Node: HTTP - Send Chatwoot Reply
Role:
Sends message to user
Uses:

cleaned_reply


8. AUTO PATH (ORDER ENGINE)

Node: Code - Build Order State Inputs
Role:
Extracts structured order signals

Node: Code - Build Order State
Role:
Builds:

order_state


Node: Code - Build Structured Memory
Role:
Creates:

structured_conversation_memory


Node: Code - Align Order Logic
Role:
Adds:

intent flags
readiness logic


Node: Code - Decide Order Route
Role:
Determines:

create draft
update draft
sync lines


Node: AI - Final Sales Reply Composer
Role:
Generates final reply using:

order_state
memory
ai_reply_output

Output:

output

Critical Rule:
ONLY runs in AUTO path

Node: Code - Clean Final Reply
Same as clarify path

Node: HTTP - Send Chatwoot Reply
Sends:

cleaned_reply


9. ESCALATION PATH

Node: Google Sheets - Log Escalation
Role:
Stores escalation record

Node: Send to Human
Role:
Routes conversation to human agent

10. CRITICAL FLOW RULES

RULE 1 — Reply Source Control



Path
Source




CLARIFY
ai_reply_output


AUTO
Final Composer output




RULE 2 — Output Overwrite Control
output can ONLY be overwritten at:

Prepare Clarify Reply
Final Sales Reply Composer


RULE 3 — Clean Node Integrity
Clean node:

MUST NOT change meaning
MUST NOT rephrase
MUST ONLY clean formatting


RULE 4 — Chatwoot Send
Chatwoot must ONLY use:
→ cleaned_reply

11. KNOWN WEAK POINTS

Weak Point 1
Merge node can overwrite output

Weak Point 2
Composer can override good AI responses

Weak Point 3
Clarify path accidentally going through AUTO logic

Weak Point 4
Multiple nodes assuming ownership of reply

12. FINAL EXECUTION RULE

Every message must follow:

ONE decision
ONE reply source
ONE final cleaned message


If more than one exists → system is broken.
