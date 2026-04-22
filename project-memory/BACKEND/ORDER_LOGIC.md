1. PURPOSE
This document defines the exact logic for how orders are:

created
updated
structured
synced with pigs
reserved and released

It is the single source of truth for:
👉 order behavior
👉 draft handling
👉 line assignment

2. CORE PRINCIPLE
👉 Orders are state machines, not messages
The system must always reflect:
REAL CUSTOMER INTENT + REAL STOCK + REAL RESERVATIONS

NOT:
❌ conversation guesses
❌ repeated drafts
❌ partial updates

3. ORDER STRUCTURE
Orders consist of:
ORDER_MASTER → Header
ORDER_LINES → Items
ORDER_STATUS_LOG → History


4. ORDER STATES
4.1 Allowed states (ORDER_MASTER.Order_Status)
Draft
Pending_Approval
Approved
Completed
Cancelled

4.2 Allowed line states (ORDER_LINES.Line_Status)
Draft
Reserved
Collected
Cancelled

4.3 State transition flow
Draft → Pending_Approval → Approved → Completed
Draft → Pending_Approval → Cancelled (via Reject)
Draft → Cancelled


4.2 Draft definition
A Draft means:

customer intent is known
order not yet confirmed
pigs may or may not be reserved


5. DRAFT CREATION LOGIC

5.1 Create Draft ONLY if:
has_existing_draft = false
AND
has_commitment_signal = true
AND
hasDraftCoreFields = true
AND
noCriticalMissingCoreFields = true


5.2 Core fields required
requested_quantity
requested_category OR requested_weight_range
timing_preference
collection_location


5.3 Hard rule
❌ NEVER create a draft if one already exists

5.4 Output of creation
Creates:
ORDER_MASTER
→ Order_Status = Draft
→ Requested fields populated


6. EXISTING DRAFT LOGIC

6.1 Detect draft
existing_order_id != ""
AND
existing_order_status = Draft


6.2 Update instead of create
If draft exists:
→ ALWAYS update
→ NEVER create new draft


6.3 Update scope
Update:

requested_quantity
requested_category
requested_weight_range
timing_preference
collection_location


6.4 Rule
👉 Draft must always reflect latest confirmed customer intent

7. REQUESTED ITEMS STRUCTURE

7.1 Source
Built from:
order_state.requested_items


7.2 Example
[
  {
    "category": "Piglet",
    "weight_range": "2_to_4_Kg",
    "sex": "Male",
    "quantity": 2
  },
  {
    "category": "Piglet",
    "weight_range": "2_to_4_Kg",
    "sex": "Female",
    "quantity": 4
  }
]


7.3 Rule
👉 This is the ONLY source of truth for order lines

8. ORDER LINE LOGIC

8.1 Line creation rule
For each requested item:
Create ORDER_LINE entries


8.2 Matching logic
Each line must match:
Sale_Category
Weight_Band
Sex (if specified)

against:
SALES_AVAILABILITY


8.3 Pig assignment rule
Only assign pigs where:
Available_For_Sale = Yes
AND Reserved_Status = Available


8.4 Quantity rule
Assigned pigs must equal:
requested quantity

If not enough:
👉 system must NOT silently fail
👉 system must respond accordingly

9. LINE SYNC LOGIC (CRITICAL)
This is where most systems break. This is where you were looping.

9.1 When to sync
should_sync_order_lines = true


9.2 Sync definition
Sync means:
ORDER_LINES = EXACT MATCH of requested_items


9.3 Steps

Compare existing lines vs requested_items
Identify:

missing lines
extra lines
mismatched lines




9.4 Actions
Add
If requested item not in lines:
→ create line
Remove
If line not in requested_items:
→ delete line
Update
If quantity or attributes changed:
→ update line

9.5 Hard rule
❌ Never duplicate lines
❌ Never partially update

9.6 Split-item re-sync behaviour (fixed 2026-04-23)
When a split-sex order (e.g. primary_01 = males, primary_02 = females) is re-synced after pigs have been reserved, the previously-reserved pigs for each item must be allowed back into the candidate pool.

Problem that was fixed:
SALES_AVAILABILITY shows reserved pigs as Reserved_Status = "Reserved".
The matching function skips Reserved pigs.
sales_rows is fetched BEFORE existing lines for the current item are cancelled.
Therefore, a re-sync after reserve_order_lines would see the current item's own pigs as Reserved → no candidates → no_match → second split item writes nothing.

Fix implemented:
_get_matching_available_pigs accepts own_pig_ids (set of Pig_IDs already on the current request_item_key's active lines).
Pigs in own_pig_ids bypass the Reserved_Status filter — they are reserved for THIS item and should be re-assignable.
This makes re-sync idempotent regardless of whether reserve_order_lines has been called.

10. RESERVATION LOGIC

10.1 Reserve trigger
Reservation happens when:
lines are confirmed
AND pigs are selected


10.2 Reservation action
Update:
ORDER_LINES.Reserved_Status = Reserved
PIG_OVERVIEW.Reserved_Status = Reserved
SALES_AVAILABILITY.Reserved_Status = Reserved


10.3 Release trigger
Release happens when:
line removed
OR order cancelled
OR order rejected


10.4 Release action
Reset:
Reserved_Status = Available
Reserved_For_Order_ID = ""


11. ORDER ROUTING LOGIC

11.1 Routes
CREATE_DRAFT
UPDATE_HEADER
UPDATE_HEADER_AND_LINES
REPLY_ONLY


11.2 Route conditions
CREATE_DRAFT
should_create_draft = true


UPDATE_HEADER
has_existing_draft = true
AND no line changes


UPDATE_HEADER_AND_LINES
has_existing_draft = true
AND should_sync_order_lines = true


REPLY_ONLY
decision_mode = CLARIFY
OR insufficient data


11.3 Rule
👉 Only ONE route per message

12. COMPOSER RULES (AUTO PATH)

12.1 Purpose
Composer is allowed to:

summarise order
confirm details
ask next step


12.2 Hard restrictions
❌ Must NOT:

override factual availability answers
re-ask answered questions
ignore ai_reply_output context


12.3 Input hierarchy
Composer must use:

order_state
structured_memory
ai_reply_output


13. CLARIFY PATH RULE

13.1 Behavior
CLARIFY path:
→ NO order logic
→ NO composer
→ DIRECT reply from AI Sales Agent


13.2 Reason
Because:
👉 AI Sales Agent already has tools
👉 Already answered correctly
👉 Composer degrades response

13. COMPLETION LOGIC

13.1 Trigger
POST /orders/{order_id}/complete
Only callable when Order_Status = "Approved"

13.2 Validation before any write
Order exists
Order_Status = "Approved"
At least one non-Cancelled line exists
All active lines have a valid Pig_ID

13.3 Write sequence (ORDER_LINES first, then PIG_MASTER, then ORDER_MASTER)
For each active (non-Cancelled) ORDER_LINE:
→ Line_Status = "Collected"
→ Updated_At = today

For each pig on those lines (via Pig_ID):
→ PIG_MASTER.Status = "Sold"
→ PIG_MASTER.On_Farm = "No"
→ PIG_MASTER.Exit_Date = today
→ PIG_MASTER.Exit_Reason = "Sold"
→ PIG_MASTER.Exit_Order_ID = order_id
→ PIG_MASTER.Updated_At = today

ORDER_MASTER:
→ Order_Status = "Completed"
→ Updated_At = today

ORDER_STATUS_LOG:
→ full audit entry: "Approved | Approved" → "Completed | Approved"

13.4 Important notes
Carcass_Weight_Kg is left blank — not applicable for live pig sales
This action is irreversible — there is no "un-complete" endpoint
PIG_MASTER is the pig record of truth — once Status = "Sold" and Exit_Date is set, the pig exits the farm system
A confirmation dialog is shown to the user on the Order Detail page before this action fires

14. FAILURE MODES

14.1 Duplicate drafts
Cause:
existing_order_id ignored


14.2 Wrong line sync
Cause:
requested_items mismatch


14.3 Repetitive questions
Cause:
composer ignoring ai_reply_output


14.4 Missing reservations
Cause:
reservation logic not triggered


14.5 Incorrect availability
Cause:
not filtering SALES_AVAILABILITY


15. DEBUG CHECKLIST
When something breaks:

Check existing_order_id
Check decision_mode
Check requested_items
Check should_sync_order_lines
Check route selected
Check ORDER_LINES vs requested_items
Check reservation status


FINAL RULE
👉 At any point, you must be able to answer:
What is the exact state of the order right now?

If not:
👉 The system is broken
