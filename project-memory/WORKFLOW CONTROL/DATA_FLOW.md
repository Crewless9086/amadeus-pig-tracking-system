DATA_FLOW.md
1. PURPOSE
This document defines:

exact data movement across the n8n workflow
field ownership at each stage
allowed vs forbidden mutations
source-of-truth fields for replies, orders, and decisions
exact branch behavior for AUTO, CLARIFY, and ESCALATE

This document is the primary reference for debugging, extending, and protecting the workflow.
This is not a loose overview.
This is a strict contract.

2. CORE PRINCIPLES
2.1 Single Field Ownership
Each important field must have:

one clear creator
clear downstream usage
no silent overwrite
no ambiguous fallback behavior

If two nodes can both “own” the same business field, the workflow is unstable.

2.2 Stage-Based Field Safety
Some fields are safe only at specific stages.
Example:

output is not globally safe
output is only trustworthy if you know which node last wrote it
therefore critical content must be copied into dedicated preserved fields before merge points


2.3 Final Outbound Rule
The system must always have one clear answer to:
Which exact field is sent to the customer?
Answer:

cleaned_reply

No other field may be sent directly to Chatwoot.

3. CRITICAL FIELDS



Field
Purpose
Owner
Notes




output
temporary working output
stage-dependent
dangerous field; must never be assumed globally trustworthy


escalation_raw_output
preserved raw classifier JSON
Code - Normalize Escalation Output
never customer-facing


decision
parsed escalation decision
Code - Parse Escalation Decision
values: AUTO / CLARIFY / ESCALATE


decision_mode
authoritative routing mode
Code - Parse Escalation Decision
downstream switches must trust this


ai_reply_output
preserved AI Sales Agent reply
Code - Normalize AI Reply Output
source-of-truth for CLARIFY reply


order_state
structured order data
Code - Build Order State
order logic only


structured_conversation_memory
carried working memory
Code - Build Structured Memory
context only


cleaned_reply
final sanitized outbound message
Code - Clean Final Reply
only field allowed into Chatwoot content




4. HIGH-LEVEL FLOW
Chatwoot
→ Normalize inbound message
→ Build conversation context
→ Escalation Classifier
→ Normalize classifier output
→ Parse escalation decision
→ AI Sales Agent
→ Normalize AI reply
→ Merge sales context back
→ Switch by post-AI mode
Then:


CLARIFY

Prepare Clarify Reply
Clean Final Reply
Send Chatwoot Reply



AUTO

Build Order State Inputs
Build Order State
Build Structured Memory
Build Replay Truth / order readiness logic
Decide Order Route
run draft / update / sync logic as required
AI - Final Sales Reply Composer
Clean Final Reply
Send Chatwoot Reply



ESCALATE

human escalation handling path




5. FIELD LIFECYCLE
5.1 output
output is a temporary working field and changes meaning by stage.
It may contain:

classifier JSON
AI Sales Agent reply text
locked clarify reply
final AUTO composed reply

Because of this, output must never be treated as safe without checking which node wrote it last.
Allowed owners of output:

Escalation Classifier
AI Sales Agent
Code - Prepare Clarify Reply
AI - Final Sales Reply Composer

No other node should redefine the meaning of output.

5.2 escalation_raw_output
Lifecycle:

created immediately after classifier
preserved through merge
used only for audit/debug/reference
must never be used as customer-facing reply


5.3 ai_reply_output
Lifecycle:

created immediately after AI Sales Agent
preserved through merge
used directly by CLARIFY path
optionally used as reference input in AUTO composer path
must never be overwritten downstream

This field exists specifically because output is unsafe after merge.

5.4 cleaned_reply
Lifecycle:

created only after final reply source has already been chosen
used only for final outbound delivery
must not contain logic, fallback decisioning, or reinterpretation


6. NODE-LEVEL DATA FLOW

6.1 Escalation Classifier
Input

ConversationHistory
CustomerMessage
early context fields

Output

output = strict JSON string:

decision
reason
confidence
summary



Rule
This output is classification data only.
It is not a customer reply.
Forbidden

using this output as the reply to customer


6.2 Code - Normalize Escalation Output
Input

classifier output

Output

escalation_raw_output = classifier output
keep original output unchanged if needed for parse step

Rule
Preserve classifier output before any collision point.
Forbidden

turning classifier JSON into conversational reply
reinterpreting classifier meaning


6.3 Code - Parse Escalation Decision
Input

classifier raw JSON

Output

decision
decision_mode
route
reason
confidence
summary

Rule
This node creates the authoritative routing mode.
Critical rule
Downstream nodes must not invent their own replacement for decision_mode.

6.4 AI Sales Agent
Input

customer message
conversation history
parsed decision context
tools / stock context / sales memory

Output

output = conversational reply

Rule
This is the first genuine customer-facing reply candidate.
Important note
For CLARIFY, this node usually produces the best question or answer.

6.5 Code - Normalize AI Reply Output
Input

AI Sales Agent output

Output

ai_reply_output = output

Rule
This preserves the good AI reply before merge collisions.
Critical rule
This node becomes the owner of ai_reply_output.
Forbidden

altering wording
cleaning or recomposing text
changing tone


6.6 Merge - Reattach Sales Context After AI
Purpose
Reconnects AI reply stream with business/context fields.
Output must include

ai_reply_output
parsed escalation fields
customer context
conversation context
existing draft data if present

Known risk
This is a collision point for output.
Rule
After this merge:

ai_reply_output is trusted
raw output may be unsafe
no node after this merge may assume output still contains the intended AI reply unless explicitly rewritten


7. BRANCHING LOGIC
7.1 Switch - Route by Mode
This switch handles top-level escalation logic.
It may separate:

ESCALATE
non-escalate path

If AUTO and CLARIFY share the same early path here, that is acceptable only if decision_mode survives unchanged.
Critical rule
This switch must not destroy CLARIFY meaning.

7.2 Switch - Post AI Mode
This is the strict split after AI response exists.
Input

decision_mode

Branches

CLARIFY
AUTO

Rule
This is where CLARIFY and AUTO must finally separate.
Critical rule
Once on CLARIFY path, the workflow must bypass:

order processing
draft creation/update
line sync
final AUTO composer


8. CLARIFY PATH (STRICT)
8.1 Code - Prepare Clarify Reply
Input

ai_reply_output
merged context
decision_mode

Output

reply_mode = "CLARIFY"
output = ai_reply_output
skip flags:

skip_order_processing = true
skip_draft_create = true
skip_draft_update = true
skip_line_sync = true



Rule
This node locks the clarify reply as the official outgoing reply.
Critical rule
For CLARIFY, output must now equal the preserved AI Sales Agent reply.
Forbidden

recomposing clarify reply
sending CLARIFY through AI - Final Sales Reply Composer


8.2 Code - Clean Final Reply
Input

output

Output

cleaned_reply

Rule
Only sanitize noise:

tool lines
observation/thought markers
excessive blank lines

Forbidden

changing meaning
changing tone
selecting a different reply source
inventing fallback logic unless reply is truly empty


8.3 HTTP - Send Chatwoot Reply
Input

cleaned_reply

Rule
For CLARIFY, this is the direct outbound path.
Critical rule
Nothing from classifier fields may be sent to customer.

9. AUTO PATH (STRICT)
9.1 Code - Build Order State Inputs
Creates the exact field bundle needed for order-state building.
9.2 Code - Build Order State
Creates order_state.
9.3 Code - Build Structured Memory
Creates structured_conversation_memory.
9.4 Replay truth / order logic nodes
These determine:

commitment strength
draft readiness
sync readiness
route correctness

Examples include:

Build Replay Truth Flags
Should Create Draft
Decide Order Route
related readiness/logic nodes already in workflow

9.5 Draft/update/sync path
Depending on route:

create draft
update header
sync order lines
skip processing

9.6 AI - Final Sales Reply Composer
Input

order_state
structured memory
backend results
aligned reply seed if used
optionally ai_reply_output for context

Output

output = final AUTO reply

Rule
This node is only for AUTO path.
Forbidden

using this node for CLARIFY
downgrading a perfectly good clarify answer into a weaker generic question


9.7 Code - Clean Final Reply
Same sanitize-only rule.
9.8 HTTP - Send Chatwoot Reply
Sends cleaned_reply.

10. REPLY SOURCE OF TRUTH
10.1 CLARIFY source of truth
For CLARIFY turns:

best reply source = ai_reply_output
locked by Code - Prepare Clarify Reply
carried through output
sanitized into cleaned_reply
sent to Chatwoot

10.2 AUTO source of truth
For AUTO turns:

best reply source = AI - Final Sales Reply Composer.output
sanitized into cleaned_reply
sent to Chatwoot

10.3 Never allowed
Never send:

escalation_raw_output
classifier JSON in output
raw merged output after merge without knowing who last wrote it


11. CRITICAL FIELD RULES
11.1 output
Temporary working field only.
Allowed overwrite points:

Escalation Classifier
AI Sales Agent
Code - Prepare Clarify Reply
AI - Final Sales Reply Composer

No other node should redefine reply meaning.

11.2 ai_reply_output
Protected field.
Rules:

created once
never overwritten
primary CLARIFY source
reference field for debugging reply regressions


11.3 decision_mode
Protected routing field.
Rules:

created by parse node
used by switches
must not be silently collapsed into AUTO
must remain visible after merge


11.4 cleaned_reply
This is the only customer outbound field.
HTTP send node must use this field only.

12. PROHIBITED BEHAVIOR
The workflow must never:

use classifier JSON as customer reply
overwrite ai_reply_output
run composer in CLARIFY path
send raw output directly to Chatwoot
let clean node choose reply strategy
let merge node implicitly decide reply ownership
ask the customer something already clearly answered in prior steps
lose decision_mode before post-AI split


13. FAILURE MODES
13.1 Wrong reply sent
Cause:

output overwritten incorrectly
reply source not locked before clean/send

13.2 Weak CLARIFY reply
Cause:

CLARIFY went through composer
ai_reply_output ignored

13.3 Repetitive AUTO reply
Cause:

composer ignored actual sales answer and reverted to generic question

13.4 Empty message sent
Cause:

locked reply source lost before clean/send

13.5 Classifier JSON leaks into final path
Cause:

raw output trusted after merge

13.6 CLARIFY acts like AUTO
Cause:

decision_mode not preserved
post-AI split missing or miswired


14. DEBUG STRATEGY
When something is wrong, debug in this order:

What is decision_mode?
Which branch ran after post-AI split?
What is in ai_reply_output?
What is in output immediately before clean node?
Did CLARIFY path rewrite output = ai_reply_output?
Did AUTO path composer write new output?
What is in cleaned_reply?
What exact field is HTTP send using?


15. DEPENDENCY MAP



Field
Created By
Used By




escalation_raw_output
Normalize Escalation Output
parse/debug only


decision_mode
Parse Escalation Decision
routing switches, logic nodes


ai_reply_output
Normalize AI Reply Output
clarify path, composer reference, debugging


order_state
Build Order State
order logic, composer


structured_conversation_memory
Build Structured Memory
order logic, composer


output
stage-dependent
clean node only after reply source is locked


cleaned_reply
Clean Final Reply
HTTP - Send Chatwoot Reply




16. FINAL RULE
At any point in debugging, the team must be able to answer these questions immediately:

What is the current decision_mode?
Which node last wrote output?
Is the system on CLARIFY or AUTO path?
What exact field will be sent to the customer?

If those answers are not obvious, the workflow is not safe enough yet.
