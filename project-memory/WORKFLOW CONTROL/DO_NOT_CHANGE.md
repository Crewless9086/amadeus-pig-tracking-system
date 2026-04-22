1. PURPOSE
This document defines:
👉 What MUST NEVER be changed without explicit review
👉 What parts of the system are critical and fragile
👉 Where mistakes will cause system-wide failure

2. CORE PRINCIPLE
If it works, DO NOT TOUCH IT without understanding EXACTLY why it works.


3. CRITICAL SYSTEM COMPONENTS
These components are tightly coupled.
Changing one incorrectly WILL break the system.

3.1 Field Ownership System
These fields are strictly controlled:



Field
Owner




ai_reply_output
AI Sales Agent


escalation_raw_output
Escalation Classifier


decision_mode
Parse Node


order_state
Order Builder


structured_conversation_memory
Memory Builder


cleaned_reply
Clean Node




🚫 RULE
❌ NEVER reassign ownership
❌ NEVER duplicate meaning of fields
❌ NEVER introduce alternative versions (e.g. final_output_2)

4. THE output FIELD (HIGH RISK)

4.1 Definition
output = temporary working field


4.2 Allowed overrides ONLY at:

Code - Prepare Clarify Reply
AI - Final Sales Reply Composer


🚫 RULE
❌ NEVER override output in random nodes
❌ NEVER assume output is safe after a merge

5. AI REPLY SOURCE CONTROL

5.1 Source of truth
ai_reply_output = REAL conversational reply


🚫 RULE
❌ NEVER overwrite ai_reply_output
❌ NEVER ignore it in CLARIFY path

6. CLARIFY PATH PROTECTION

6.1 Correct behavior
AI Sales Agent → Clean → Send


🚫 STRICT RULES
❌ DO NOT send CLARIFY through Composer
❌ DO NOT modify wording
❌ DO NOT simplify reply
❌ DO NOT “make it nicer”

Reason
👉 AI Sales Agent already uses tools
👉 It already gives the best answer
👉 Composer degrades it

7. AUTO PATH PROTECTION

7.1 Composer usage
Composer is ONLY allowed in AUTO path

🚫 RULE
❌ NEVER bypass composer in AUTO
❌ NEVER run composer in CLARIFY

8. MERGE NODE RISK (CRITICAL)

Problem
Merge - Reattach Sales Context After AI
can overwrite fields silently

🚫 RULE
❌ NEVER rely on output after merge
❌ ALWAYS use:
ai_reply_output
decision_mode
order_state


9. SWITCH LOGIC

Switch - Post AI Mode
Controls:
CLARIFY vs AUTO


🚫 RULE
❌ NEVER add logic before this switch
❌ NEVER mix paths after this switch

10. CLEAN NODE

Purpose
Remove formatting noise ONLY


🚫 RULE
❌ DO NOT rewrite text
❌ DO NOT rephrase
❌ DO NOT shorten
❌ DO NOT enhance

Allowed
✔ remove tool logs
✔ remove debug text
✔ trim whitespace

11. CHATWOOT SEND NODE

Required field
cleaned_reply


🚫 RULE
❌ NEVER send:

output
ai_reply_output
raw text


12. ORDER SYSTEM PROTECTION

🚫 NEVER:
❌ Create draft if one exists
❌ Modify ORDER_LINES directly from n8n
❌ Assign pigs outside backend
❌ Skip reservation logic

13. GOOGLE SHEETS PROTECTION

🚫 NEVER:
❌ Write to formula sheets:

SALES_AVAILABILITY
PIG_OVERVIEW
ORDER_OVERVIEW


✔ ONLY write to:

PIG_MASTER
ORDER_MASTER
ORDER_LINES
LOG tables


14. BACKEND PROTECTION

🚫 NEVER:
❌ Call endpoints out of order
❌ Skip validation
❌ Send partial payloads

✔ ALWAYS:

validate inputs
use correct endpoint
respect order flow


15. NODE CREATION RULE

🚫 DO NOT:
❌ Add new nodes without purpose
❌ Duplicate logic
❌ Create parallel systems

✔ ALWAYS:
Ask:
Does this already exist in the system?

If YES → use existing
If NO → justify creation

16. COMMON BREAK POINTS

16.1 Duplicate replies
Cause:
multiple reply sources


16.2 Weak responses
Cause:
composer replacing ai_reply_output


16.3 Lost messages
Cause:
output overwritten


16.4 Infinite loops
Cause:
order logic mis-triggered


17. SAFE CHANGE PROCESS

Before changing anything:

Identify node
Identify field ownership
Check DATA_FLOW.md
Check ORDER_LOGIC.md


Then:
✔ make SMALL change
✔ test ONE scenario
✔ confirm no regression

🚫 NEVER:
❌ change multiple nodes at once
❌ “clean up everything”
❌ refactor blindly

18. DEBUG FIRST RULE

If something breaks:
👉 DO NOT FIX IMMEDIATELY
First:
Trace the data
Find where it changed
Identify why
THEN fix


19. FINAL SYSTEM LAW
The system must always have ONE clear:
- reply source
- decision path
- order state

If any of these are unclear:
👉 The system is broken

20. HARD STOP RULE
If you ever feel:

confused
lost in nodes
unsure where data changed

👉 STOP
👉 Go back to:

DATA_FLOW.md
ORDER_LOGIC.md

