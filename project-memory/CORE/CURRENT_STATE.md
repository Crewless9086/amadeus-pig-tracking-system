1. PURPOSE
This document defines:

What is currently working
What is partially working
What is broken or unstable
What is not yet implemented

It is the live operational truth of the system.

2. SYSTEM STATUS SUMMARY
System Phase: ACTIVE BUILD (Mid-Stage)
Stability: PARTIALLY STABLE
Core Engine: FUNCTIONAL
Risk Level: MEDIUM (due to ongoing changes)


3. WORKING COMPONENTS ✅

3.1 AI Sales Agent (Core Intelligence)
Status: ✅ WORKING WELL
Capabilities:

Understands customer intent
Uses stock logic correctly
Produces high-quality replies
Handles CLARIFY scenarios very well


3.2 Escalation Classifier
Status: ✅ WORKING

Correctly classifies:

AUTO
CLARIFY
ESCALATE


Produces structured JSON output


3.3 Decision Parsing
Status: ✅ STABLE

decision_mode correctly extracted
Routing logic functional


3.4 CLARIFY FLOW (AFTER FIX)
Status: ✅ WORKING (RECENTLY FIXED)
Flow:
AI Sales Agent → Prepare Clarify → Clean → Send

Result:

Strong responses preserved
No composer interference


3.5 Data Structuring
Status: ✅ WORKING
Includes:

order_state
structured_conversation_memory
requested_items


3.6 Google Sheets Data Model
Status: ✅ STRONG FOUNDATION

PIG_MASTER (source of truth)
SALES_AVAILABILITY (correct filtering)
ORDER_MASTER / ORDER_LINES structure correct

3.7 Order Lifecycle Backend (Core Endpoints)
Status: ✅ IMPLEMENTED (2026-04-23)

All order action endpoints are live:
POST /orders/{id}/reserve
POST /orders/{id}/release
POST /orders/{id}/send-for-approval
POST /orders/{id}/approve
POST /orders/{id}/reject
POST /orders/{id}/complete ← NEW: writes pig exit data to PIG_MASTER, marks pigs Sold


4. PARTIALLY WORKING ⚠️

4.1 AUTO RESPONSE QUALITY
Status: ⚠️ INCONSISTENT
Problem:

Composer sometimes overrides good answers
Repeats questions already answered

Example issue:
AI Sales Agent gives full availability
→ Composer replaces with generic question


4.2 ORDER ROUTING
Status: ⚠️ MOSTLY WORKING
Working:

Detects existing draft
Detects intent signals

Issues:

Route selection not always aligned with reality
Some unnecessary CLARIFY triggers


4.3 LINE SYNC LOGIC
Status: ✅ FIXED (2026-04-23)

Structure is correct.
Split-item re-sync bug fixed: secondary split items (e.g. primary_02 females) were returning no_match after a reserve call because their pigs appeared as Reserved in SALES_AVAILABILITY at the time of matching. Fixed by passing own_pig_ids to _get_matching_available_pigs so that pigs already reserved for the current request_item_key are allowed back into the candidate pool.

Remaining watch points:
Verify execution on orders with 3+ split items
Monitor for duplicate lines if sync is called concurrently


5. BROKEN / UNSTABLE ❌

5.1 Composer vs AI Conflict
Status: ❌ MAJOR ISSUE
Problem:

Two competing reply sources:

AI Sales Agent (correct)
Composer (sometimes wrong)



Impact:

degraded replies
repeated questions
lost context


5.2 Output Field Confusion (Previously)
Status: ⚠️ PARTIALLY RESOLVED
Problem:

output overwritten at multiple stages
classifier output leaking into replies

Current state:

improved with normalization
still sensitive to changes


5.3 Merge Node Field Collision
Status: ❌ HIGH RISK
Node:
Merge - Reattach Sales Context After AI

Problem:

output overwritten silently
wrong data passed downstream


6. NOT YET IMPLEMENTED ⛔

6.1 Full Backend Integration
Missing:

stable API usage in all flows

Note: Full order lifecycle control is now implemented (Draft → Approve → Complete).
Remaining gap is connecting n8n flows to use these endpoints reliably.


6.2 Reservation Automation
Not fully connected:

reserve endpoint
release endpoint
sync with ORDER_LINES


6.3 Approval Flow
Missing:

send for approval trigger
approval/rejection handling


6.4 Error Handling Layer
Missing:

fallback replies
retry logic
failure notifications


6.5 Human Escalation Loop
Partially built but not complete:

escalation logging
response return loop


7. CURRENT RISKS 🚨

Risk 1: Overbuilding
You are:

adding nodes too fast
modifying multiple layers at once


Risk 2: Losing Source of Truth
Fields at risk:
output
ai_reply_output
cleaned_reply


Risk 3: Composer Damage
AUTO replies are being degraded by composer

Risk 4: Silent Failures

no clear error handling
issues only seen in output


8. WHAT IS ACTUALLY WORKING WELL (IMPORTANT)
You need to internalize this:
👉 The AI Sales Agent is already VERY strong
👉 Your data model is VERY strong
👉 Your intent detection is GOOD

9. WHAT IS CAUSING MOST PROBLEMS
Not the AI.
👉 The orchestration layer (n8n)
Specifically:

field misuse
merge behavior
composer misuse


10. CURRENT PRIORITY STACK

PRIORITY 1 (CRITICAL)
Fix:
AUTO reply integrity

Goal:
👉 Preserve good answers from AI Sales Agent

PRIORITY 2
Stabilize:
order routing + line sync


PRIORITY 3
Complete:
backend integration


PRIORITY 4
Add:
error handling + monitoring


11. WHAT YOU SHOULD NOT TOUCH RIGHT NOW

❌ AI Sales Agent prompt
❌ Google Sheets structure
❌ Escalation Classifier
❌ Core data flow

12. WHAT YOU SHOULD FOCUS ON

✔ Reply flow integrity
✔ Composer control
✔ Order route accuracy

13. CURRENT SYSTEM TRUTH

👉 You are NOT far off
👉 The system is NOT broken
👉 It is MISALIGNED in a few key areas

14. FINAL REALITY CHECK
Right now:
The intelligence is correct
The data is correct
The structure is correct

The flow control is the problem


15. FINAL RULE
DO NOT BUILD MORE

STABILIZE WHAT EXISTS
