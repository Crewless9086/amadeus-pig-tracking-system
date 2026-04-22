NODE_RESPONSIBILITIES.md — AMADEUS SALES WORKFLOW (STRICT)

1. PURPOSE
This file defines the strict contract for each node in the Amadeus Sales workflow.
This document is not descriptive only.
It is a build control document.
Every node must have:

a single clear responsibility
clearly defined inputs
clearly defined outputs
clearly defined ownership of fields
clearly defined non-ownership of fields

If a node changes fields outside its responsibility, that is a workflow violation.

2. GLOBAL RULES
RULE A — SINGLE RESPONSIBILITY
Each node must do one job only.
A node must not:

classify and rewrite
enrich and reroute
compose and sanitize
sanitize and reinterpret

If a node is doing more than one job, split it.

RULE B — FIELD OWNERSHIP
Every important field must have a clear owner.
If two nodes both believe they own the same field, the workflow is unstable.

RULE C — OUTPUT IS DANGEROUS
The field output is high-risk because multiple AI nodes use it.
Therefore:

output must never be treated as universally trustworthy
whenever an AI reply is important, it must be copied into a dedicated locked field
normalization nodes must preserve original source fields before downstream merge nodes


RULE D — CLEAN NODES DO NOT THINK
Any node with the word:

Clean
Normalize
Prepare
Parse

must not invent or reinterpret business meaning.
These nodes only:

rename
preserve
sanitize
structure

They must not perform fresh reasoning.

RULE E — REPLY SOURCE MUST BE EXPLICIT
Before a message is sent to Chatwoot, the workflow must clearly know:

where the reply came from
whether it came from CLARIFY path or AUTO path
whether it was composed by AI Sales Agent or Final Sales Reply Composer

Never rely on “whatever is in output right now” unless that was explicitly locked in the immediately prior node.

3. NODE CONTRACTS

Node: Chatwoot Webhook
Responsibility
Receive inbound message payload from Chatwoot.
Allowed Inputs

Raw Chatwoot webhook body only

Required Outputs
Must preserve raw inbound fields such as:

conversation_id
contact_id
customer_message
conversation metadata
inbox metadata
timestamps
custom attributes if present

Owns

raw inbound event data only

Must Not

infer intent
classify message
clean reply text
create order logic
overwrite business fields

Failure Condition
If inbound payload is incomplete or malformed, stop early and log.
Downstream Dependency
Everything depends on this node being raw and untouched.

Node: Code - Normalize Incoming Message
Responsibility
Standardize incoming message payload into workflow-safe fields.
Allowed Inputs

Raw webhook fields from Chatwoot Webhook

Required Outputs
Normalized inbound fields such as:

customer_message
CustomerMessage
customer_name
customer_channel
conversation_id
contact_id
other stable aliases if used in workflow

Owns

normalized inbound text fields

Must Not

classify escalation
generate replies
infer order intent
create order_state
modify raw payload meaning

Failure Condition
If customer_message becomes blank when source was not blank, this node is broken.
Downstream Dependency
All AI and routing nodes rely on these normalized fields.

Node: Switch - Message Type
Responsibility
Route inbound message by content type.
Allowed Inputs

normalized message payload

Required Outputs
Same payload routed into correct branch.
Owns

routing decision only

Must Not

rewrite message text
classify business meaning
generate replies

Failure Condition
Audio sent into text path without transcription readiness.

Node: HTTP - Transcribe Audio
Responsibility
Convert audio into usable text.
Allowed Inputs

audio message payload

Required Outputs

transcribed text
preserved original message context

Owns

transcription result only

Must Not

classify escalation
answer the customer
interpret order meaning

Failure Condition
Blank transcript on valid audio.

Node: Merge - Combine Message Paths
Responsibility
Rejoin text and audio branches into one common message stream.
Allowed Inputs

normalized text path
transcribed audio path

Required Outputs
Unified payload with a single usable customer message.
Owns

path merge only

Must Not

overwrite valid text with blank text
create business logic
choose reply content

Failure Condition
Merged item loses normalized message fields.

Node: Code - Build Conversation Context
Responsibility
Build the working conversational context for AI nodes.
Allowed Inputs

normalized customer message
conversation metadata
conversation history inputs if available

Required Outputs
Typically:

ConversationHistory
IsFirstTurn
stable chat context fields

Owns

structured conversation context only

Must Not

decide escalation
write order_state
generate final reply

Failure Condition
Conversation history omitted or malformed when source exists.

Node: Escalation Classifier
Responsibility
Decide whether the next mode is:

AUTO
CLARIFY
ESCALATE

Allowed Inputs

customer message
conversation history
current context

Required Outputs
Single JSON string in output containing:

decision
reason
confidence
summary

Owns

escalation decision only

Must Not

produce customer-facing final reply
create order_state
write draft/update logic
overwrite business fields outside escalation decision

Critical Note
Its output is not a customer reply.
It is classifier JSON.
Failure Condition
Anything in output that is not strict parseable JSON.

Node: Code - Normalize Escalation Output
Responsibility
Preserve classifier raw output before downstream collisions.
Allowed Inputs

classifier result

Required Outputs

escalation_raw_output

Owns

safe preserved copy of escalation classifier output

Must Not

parse business meaning
rewrite decision
create reply text

Failure Condition
If classifier output is lost after this point, this node failed its purpose.

Node: Code - Parse Escalation Decision
Responsibility
Convert classifier JSON string into structured routing fields.
Allowed Inputs

escalation_raw_output or classifier output

Required Outputs

decision
decision_mode
route
reason
confidence
summary

Owns

parsed escalation decision fields

Must Not

generate customer reply
modify conversation text
decide order routing
create order_state

Critical Rule
decision_mode must remain the authoritative mode field downstream.
Failure Condition
If CLARIFY is collapsed into AUTO without preserving decision_mode, this node or its logic is wrong.

Node: Switch - Route by Mode
Responsibility
Separate ESCALATE path from non-escalate path.
Allowed Inputs

parsed decision_mode
routing fields

Required Outputs

ESCALATE branch
non-escalate branch

Owns

first routing split only

Must Not

destroy CLARIFY meaning
rewrite decision_mode
create reply text

Critical Rule
AUTO and CLARIFY may continue on shared branch here, but decision_mode must survive unchanged.
Failure Condition
If CLARIFY is treated as AUTO because the switch only understands AUTO/ESCALATE and later nodes cannot distinguish them.

Node: AI Sales Agent
Responsibility
Generate the best immediate conversational answer based on message, tools, and current stage.
Allowed Inputs

normalized customer message
conversation context
decision context
tool results
sales memory if provided

Required Outputs

customer-facing natural-language reply in output

Owns

first real conversational reply draft

Must Not

write final Chatwoot reply directly
decide draft creation backend actions
overwrite parsed escalation fields

Critical Rule
This node often produces the best CLARIFY reply.
Failure Condition
Reply ignores available tool truth or asks already-answered questions.

Node: Code - Normalize AI Reply Output
Responsibility
Preserve AI Sales Agent reply before merge collisions.
Allowed Inputs

AI Sales Agent output

Required Outputs

ai_reply_output

Owns

safe preserved copy of AI Sales Agent reply

Must Not

alter wording
recompose reply
parse escalation
create order_state

Failure Condition
If ai_reply_output does not exactly match AI Sales Agent reply text.

Node: Merge - Reattach Sales Context After AI
Responsibility
Reattach conversation/business context to AI reply stream.
Allowed Inputs

AI branch with ai_reply_output
context branch with metadata and parsed fields

Required Outputs
Merged item containing both:

business/context fields
preserved ai_reply_output

Owns

reattachment only

Must Not

decide which reply source wins
overwrite preserved reply fields
rely on raw output surviving merge

Critical Risk
This is a known collision point for:

output
reply ownership confusion

Failure Condition
If merged item contains classifier output but not usable AI reply source.

Node: Switch - Post AI Mode
Responsibility
Split CLARIFY path from AUTO path after AI response exists.
Allowed Inputs

merged context
decision_mode

Required Outputs

CLARIFY branch
AUTO branch

Owns

post-AI mode split only

Must Not

generate text
modify order state
change decision mode

Critical Rule
This switch exists so CLARIFY can bypass order-processing/composer logic.
Failure Condition
If CLARIFY continues through AUTO composer path.

Node: Code - Prepare Clarify Reply
Responsibility
Lock the best CLARIFY reply as the official outgoing reply.
Allowed Inputs

ai_reply_output
merged context
decision mode

Required Outputs
Must set:

reply_mode = "CLARIFY"
output = ai_reply_output
skip flags:

skip_order_processing
skip_draft_create
skip_draft_update
skip_line_sync



Owns

final clarify reply source lock

Must Not

rephrase the AI reply
compose a new clarify reply
create order_state
call composer logic

Critical Rule
For CLARIFY, this node decides the reply source.
No later node may replace it.
Failure Condition
If output after this node is not exactly the preserved clarify reply.

Node: Code - Build Order State Inputs
Responsibility
Prepare fields required to construct order_state.
Allowed Inputs

merged context
memory
customer message
parsed mode fields

Required Outputs
Stable order-state input bundle.
Owns

order-state prep only

Must Not

compose customer reply
trigger backend actions
finalize routing


Node: Code - Build Order State
Responsibility
Build normalized order intent structure from current turn plus memory.
Allowed Inputs

message fields
sales memory
conversation metadata

Required Outputs
order_state with fields such as:

requested_quantity
requested_category
requested_weight_range
requested_items
timing_preference
collection_location
existing draft flags
sync readiness
intent flags

Owns

order_state

Must Not

send reply
update backend
change escalation decision
choose final reply source

Critical Rule
This node is state-building only, not behavior execution.
Failure Condition
If known memory facts disappear on confirmation turns.

Node: Code - Build Structured Memory
Responsibility
Create structured working memory from conversation and order state.
Allowed Inputs

conversation context
order_state
prior memory

Required Outputs

structured_conversation_memory

Owns

structured memory object only

Must Not

decide backend route
compose final reply
overwrite reply text


Node: Code - Build Replay Truth Flags
Responsibility
Create explicit truth flags about reply source and path logic.
Allowed Inputs

decision_mode
order_state
memory
reply ownership fields

Required Outputs
Flags such as:

whether clarify path is active
whether composer should be bypassed
whether order processing should occur

Owns

replay truth flags only

Must Not

directly write final reply text unless explicitly designed to do so
replace order_state
replace ai_reply_output

Critical Rule
This node exists to stop reply-source confusion.

Node: Code - Should Create Draft Order
Responsibility
Decide whether draft creation is allowed.
Allowed Inputs

order_state
structured memory
effective decision mode

Required Outputs

should_create_draft
debug flags

Owns

draft-create eligibility only

Must Not

create draft itself
sync lines
compose user reply

Failure Condition
Creates drafts on weak/non-committed inquiries.

Node: Code - Decide Order Route
Responsibility
Choose order-processing route.
Allowed Inputs

order_state
should_create_draft
draft flags
sync flags

Required Outputs

order_route
Examples:
CREATE_DRAFT
UPDATE_HEADER_AND_LINES
UPDATE_HEADER_ONLY
REPLY_ONLY

Owns

order processing route only

Must Not

update backend itself
send reply
replace AI reply

Critical Rule
This node must operate only on explicit readiness flags, not vague text impressions.

Node: AI - Final Sales Reply Composer
Responsibility
Compose final customer reply for AUTO/order-processing path.
Allowed Inputs

backend results
order_state
memory
aligned reply seed if used
draft/update/sync outcome

Required Outputs

final AUTO-path customer reply in output

Owns

final AUTO reply only

Must Not

be used for CLARIFY path
overwrite locked clarify reply
re-ask already answered questions unless a new true missing fact exists

Critical Rule
If CLARIFY path has already selected the reply, this node must be bypassed.
Failure Condition
Repeats questions already answered by AI Sales Agent or downgrades a good informational answer.

Node: Code - Clean Final Reply
Responsibility
Sanitize final outgoing reply text only.
Allowed Inputs

final reply source already chosen in output

Required Outputs

cleaned_reply

Owns

sanitized final outgoing text only

Must Not

choose between clarify and auto
invent fallback meaning
rewrite customer message strategy
change reply substance
switch source fields arbitrarily

Critical Rule
This node is a cleaner, not a selector.
Failure Condition
Blanking a valid reply or silently using the wrong upstream field.

Node: HTTP - Send Chatwoot Reply
Responsibility
Send final reply to customer.
Allowed Inputs

cleaned_reply

Required Outputs
Successful send result to Chatwoot.
Owns

transport only

Must Not

transform response logic
choose alternate fields
clean text
compose text

Critical Rule
The content field must point to the single final cleaned reply field only.
Failure Condition
If empty or wrong reply is sent due to reading the wrong source field.

Node: Google Sheets - Log Escalation
Responsibility
Store escalation record for human handling.
Allowed Inputs

escalation summary
conversation metadata
latest customer state

Required Outputs
Logged escalation row.
Owns

escalation persistence only

Must Not

send user reply
update order backend
classify again


4. REPLY SOURCE MATRIX



Scenario
Authoritative reply source
Must be copied into
Must be sent from




CLARIFY
ai_reply_output
output in Code - Prepare Clarify Reply
cleaned_reply


AUTO informational/order
AI - Final Sales Reply Composer.output
output
cleaned_reply


ESCALATE
human/escalation workflow
separate escalation handling
separate path




5. STRICT FIELD OWNERSHIP
output
Allowed owners:

Escalation Classifier → classifier JSON only
AI Sales Agent → first conversational reply
Code - Prepare Clarify Reply → locked clarify reply
AI - Final Sales Reply Composer → locked AUTO reply

No other node may treat output as universally safe without context.

ai_reply_output
Allowed owner:

Code - Normalize AI Reply Output

No later node may overwrite this.

escalation_raw_output
Allowed owner:

Code - Normalize Escalation Output

No later node may overwrite this.

order_state
Allowed owner:

Code - Build Order State

No other node may rebuild it informally.

structured_conversation_memory
Allowed owner:

Code - Build Structured Memory


cleaned_reply
Allowed owner:

Code - Clean Final Reply


6. FORBIDDEN BEHAVIORS
The workflow must never do the following:

Use classifier JSON as a customer-facing reply
Let CLARIFY fall into AUTO composer path
Let AUTO fall into clarify-only lock logic
Let merge nodes decide reply ownership
Let clean nodes invent content
Ask for information already confirmed in memory
Rebuild order details from scratch when memory already holds confirmed facts
Send Chatwoot replies from raw output when cleaned_reply exists


7. DEBUGGING CHECKLIST
When a reply is wrong, check in this order:

What is decision_mode?
What should the reply source have been?
Was that source preserved in its own field?
Did a merge overwrite output?
Did CLARIFY incorrectly pass through AUTO composer?
Did Clean Final Reply sanitize only, or did it accidentally select wrong source?
Did HTTP send cleaned_reply or some other field?


8. FINAL RULE
If a node cannot answer:

what field it owns,
what field it must not touch,
and what downstream node depends on it,

then that node is not safely defined yet.
