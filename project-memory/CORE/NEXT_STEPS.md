1. PURPOSE
This document defines:
👉 Exact execution steps
👉 In strict order
👉 With clear outcomes
Goal:
Stabilise system → Then extend safely


2. CORE RULE BEFORE STARTING
DO NOT BUILD NEW FEATURES UNTIL CORE IS STABLE

If you ignore this → you will loop again.

3. PHASE STRUCTURE

PHASE 1 → Fix Reply System (CRITICAL)
PHASE 2 → Stabilise Order Logic
PHASE 3 → Connect Backend Properly
PHASE 4 → Add Safety + Monitoring
PHASE 5 → Expand Features

🔴 PHASE 1 — REPLY SYSTEM STABILISATION

Goal
👉 Ensure:
User ALWAYS receives the correct message


STEP 1.1 — Lock CLARIFY Path

What to check
In workflow:
Switch - Post AI Mode → CLARIFY


Must be:
AI Sales Agent
→ Normalize AI Reply Output
→ Prepare Clarify Reply
→ Clean Final Reply
→ HTTP Send


Validation test
Send:
"Hello, can I get more info?"


Expected
✔ Full informative answer
✔ No simplification
✔ No repetition

STEP 1.2 — Fix AUTO Reply Integrity

Problem
Composer overrides good answers

Action
Inside:
AI - Final Sales Reply Composer


Fix rule:
👉 If ai_reply_output already contains:

availability
prices
structured info

THEN:
DO NOT REWRITE
ONLY WRAP OR CONFIRM


Expected behavior
Instead of:
❌ “What weight range are you interested in?”
Should be:
✔ Use actual availability already generated

STEP 1.3 — Add Reply Protection Check (MENTAL MODEL)
Before sending:
Ask:
Did we already answer the question?

If YES → do not ask again

DONE WHEN:
✔ No repeated questions
✔ No degraded answers
✔ CLARIFY and AUTO both feel natural

🟠 PHASE 2 — ORDER LOGIC STABILISATION

Goal
👉 Orders behave predictably and correctly

STEP 2.1 — Validate Draft Creation

Test
Customer flow:
“I want 6 piglets, 2–4kg, Riversdale tomorrow”


Expected
✔ ONE draft created
✔ Correct fields filled

Must NOT happen
❌ duplicate drafts
❌ missing fields

STEP 2.2 — Validate Draft Update

Test
Follow-up:
“Make it 8”


Expected
✔ SAME order updated
✔ quantity changed

Must NOT happen
❌ new order created

STEP 2.3 — Validate Line Sync

Test
“2 male, 4 female”
→ change to “3 male, 3 female”


Expected
✔ lines updated correctly
✔ no duplicates


🟡 PHASE 3 — BACKEND CONNECTION

Goal
👉 Move real logic to backend safely

STEP 3.1 — Connect CREATE ORDER
n8n → backend:
POST /master/orders


STEP 3.2 — Connect UPDATE ORDER
PATCH /master/orders/{id}


STEP 3.3 — Connect ORDER LINES

create
update
delete


STEP 3.4 — Connect RESERVATION
POST /orders/{id}/reserve


DONE WHEN
✔ Orders exist in backend
✔ Lines sync correctly
✔ No direct sheet writes

🟢 PHASE 4 — SAFETY LAYER

Goal
👉 System becomes reliable

STEP 4.1 — Add Fallback Reply
If empty:
“Sorry, something went wrong. Please try again.”


STEP 4.2 — Add Logging
Track:

decision_mode
order_route
cleaned_reply


STEP 4.3 — Add Error Detection
Detect:

missing output
failed API calls


🔵 PHASE 5 — EXPANSION (ONLY AFTER ABOVE)

Allowed additions

photos
advanced pricing logic
delivery scenarios
chatbot personality tuning


NOT BEFORE
❌ Phase 1–3 complete

6. TEST SCENARIOS (MANDATORY)
Run these every time:

Scenario 1 — General Inquiry
“Tell me what you have”

✔ Must give availability

Scenario 2 — Clarify
“More info”

✔ Must ask smart question

Scenario 3 — Order Creation
“I want 6 piglets”

✔ Draft created

Scenario 4 — Order Update
“Make it 8”

✔ Same draft updated

Scenario 5 — Mixed Info
“What do you have? I want 4 maybe”

✔ No premature draft
✔ Good reply

7. EXECUTION RULES

DO
✔ One change at a time
✔ Test immediately
✔ Validate output

DO NOT
❌ Change multiple nodes at once
❌ Add new logic mid-debug
❌ Assume anything

8. YOUR CURRENT POSITION
Right now:
👉 You are between Phase 1 and Phase 2

Meaning:
You must:
✔ Finish reply system
✔ THEN move to order logic

9. FINAL COMMAND
When unsure:
STOP
CHECK DATA_FLOW.md
CHECK ORDER_LOGIC.md
