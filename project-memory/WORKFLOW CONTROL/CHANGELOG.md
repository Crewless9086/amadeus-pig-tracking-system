1. PURPOSE
This document tracks:

All system changes
Why the change was made
What was affected
What the expected outcome was


2. CORE PRINCIPLE
Every change must be intentional, documented, and reversible


3. CHANGE RULES

3.1 Every change MUST include:
Date
Component
Change Type
Description
Reason
Expected Outcome
Status


3.2 Change types
FIX        → repairing broken behavior
IMPROVEMENT → improving existing logic
ADD        → new feature
REMOVE     → deleting logic
REFACTOR   → restructuring without changing behavior


3.3 Status types
TESTING
WORKING
FAILED
ROLLED_BACK


4. CURRENT CHANGE LOG

🔹 2026-04 — SYSTEM STABILISATION PHASE

CHANGE 001
Date: 2026-04
Component: CLARIFY FLOW
Type: FIX
Description:
Separated CLARIFY path from AUTO path after "Merge - Reattach Sales Context After AI"
Reason:
Composer was degrading responses and overriding correct AI answers
Expected Outcome:

CLARIFY uses AI Sales Agent directly
No composer interference

Status: WORKING

CHANGE 002
Date: 2026-04
Component: AI REPLY NORMALISATION
Type: FIX
Description:
Introduced ai_reply_output field via "Code - Normalize AI Reply Output"
Reason:
output field was being overwritten and causing incorrect replies
Expected Outcome:

Stable source of truth for AI responses
Prevent loss of original answer

Status: WORKING

CHANGE 003
Date: 2026-04
Component: CLARIFY REPLY HANDLING
Type: FIX
Description:
Updated "Code - Prepare Clarify Reply" to override output with ai_reply_output
Reason:
Clarify responses were being replaced or lost downstream
Expected Outcome:

Clarify responses remain intact
Stronger customer interaction

Status: WORKING

CHANGE 004
Date: 2026-04
Component: CLEAN FINAL REPLY NODE
Type: FIX
Description:
Restricted cleaning logic to remove only tool/debug noise
Reason:
Previous versions modified actual message content
Expected Outcome:

No change to message meaning
Clean output only

Status: WORKING

CHANGE 005
Date: 2026-04
Component: OUTPUT FIELD CONTROL
Type: FIX
Description:
Defined strict ownership rules for output, ai_reply_output, and cleaned_reply
Reason:
Multiple nodes were overwriting output unpredictably
Expected Outcome:

Clear data flow
Reduced debugging complexity

Status: WORKING

CHANGE 006
Date: 2026-04
Component: MERGE NODE AWARENESS
Type: IMPROVEMENT
Description:
Identified and documented risk of field collision in "Merge - Reattach Sales Context After AI"
Reason:
output was being silently overwritten
Expected Outcome:

Safer handling of merged data
Reliance on correct fields (ai_reply_output)

Status: WORKING

CHANGE 007
Date: 2026-04
Component: REPLY FLOW ARCHITECTURE
Type: REFACTOR
Description:
Established two strict reply paths:
CLARIFY → AI Sales Agent → Clean → Send  
AUTO → Order Logic → Composer → Clean → Send

Reason:
Mixed logic caused degraded responses and confusion
Expected Outcome:

Clear separation of responsibilities
Predictable reply behavior

Status: WORKING

CHANGE 008
Date: 2026-04
Component: DOCUMENTATION SYSTEM
Type: ADD
Description:
Created structured system documentation:

DATA_FLOW.md
BUSINESS_RULES.md
ORDER_LOGIC.md
API_STRUCTURE.md
DO_NOT_CHANGE.md
CURRENT_STATE.md
NEXT_STEPS.md

Reason:
System complexity required structured reference to prevent regression
Expected Outcome:

Faster debugging
Consistent development
Reduced AI misalignment

Status: WORKING

5. KNOWN ISSUES (OPEN)

ISSUE 001 — AUTO RESPONSE DEGRADATION
Component: Composer
Status: OPEN
Problem:
Composer overrides useful AI responses with generic questions
Impact:

weaker replies
repeated questions

Planned Fix:
Improve composer logic to respect ai_reply_output

ISSUE 002 — ORDER ROUTING EDGE CASES
Component: Decide Order Route
Status: OPEN
Problem:
Some scenarios incorrectly trigger CLARIFY or wrong route
Impact:

missed draft creation
unnecessary questions


ISSUE 003 — LINE SYNC VALIDATION
Component: Order Lines
Status: UNVERIFIED
Problem:
Full sync behavior not fully tested

6. ROLLBACK STRATEGY

If something breaks:

Identify last change in this file
Revert that change
Retest previous working state


Rule:
Never debug blindly — always refer to changelog


7. FUTURE ENTRY TEMPLATE
Use this for every change:

CHANGE XXX
Date: YYYY-MM-DD
Component:
Type:
Description:
Reason:
Expected Outcome:
Status: TESTING / WORKING / FAILED

8. FINAL RULE
If a change is not in this file, it does not exist