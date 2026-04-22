FORMULA_LOGIC.md (SALES_AVAILABILITY — LOCKED VERSION)
PURPOSE
This document defines the logic behind formula-driven sheets.
SALES_AVAILABILITY is a critical system sheet and acts as:
the truth layer for sellable pigs
the bridge between farm data and sales system
the input for AI responses
the input for order matching + reservation logic
CORE PRINCIPLE
👉 SALES_AVAILABILITY is NOT just a view
👉 It is a decision engine disguised as a sheet
FLOW OF LOGIC

PIG_MASTER
   ↓
PIG_OVERVIEW (calculated state)
   ↓
SALES_AVAILABILITY (sales filter + classification)
   ↓
AI + ORDER SYSTEM
CRITICAL LOGIC LAYERS
1. BASE FILTER (ENTRY INTO SALES SYSTEM)
COLUMN: Pig_ID
Excel Formula
=FILTER(
PIG_OVERVIEW!A2:A,
PIG_OVERVIEW!A2:A<>"",
PIG_OVERVIEW!AD2:AD="Yes"
)
Meaning
Only pigs where:
Is_Sale_Ready = Yes
are allowed into the sales system.
🔥 Critical Insight
This is your FIRST GATE.
If a pig is not here:
it does not exist to sales
AI cannot sell it
orders cannot reserve it
2. DATA ENRICHMENT LAYER (XLOOKUPS)
All these fields:
Tag_Number
Sex
DOB
Weight
Stage
etc.
👉 Are pure mirrors from PIG_OVERVIEW
Rule
These are:
read-only
display + logic helpers
must never be manually edited
3. SALE ELIGIBILITY ENGINE
COLUMN: Available_For_Sale
Excel Formula
=IF($A2="","",
IF(
AND(
$L2="Active",
$M2="Yes",
$N2="Yes",
$O2="Available",
OR(
$I2="Young Piglet",
$I2="Weaner",
$I2="Grower",
$I2="Finisher",
$I2="Ready for Slaughter"
)
),
"Yes",
"No"
))
Depends on
Column
Meaning
Status
must be Active
On_Farm
must be Yes
Withdrawal_Clear
must be Yes
Reserved_Status
must be Available
Calculated_Stage
must be valid sale stage
🔥 THIS IS YOUR REAL SALES FILTER
Even if a pig is “sale ready” earlier:
👉 This column decides:
if it is actually sellable now
if AI should include it
if order system can reserve it
4. CATEGORY MAPPING ENGINE
COLUMN: Sale_Category
Maps weight bands → business categories
Example:
2–4 kg → Young Piglets
7–19 kg → Weaner Piglets
20–49 kg → Grower Pigs
🔥 Why this matters
This is what your customer sees
Not:
weight bands
internal stages
But: 👉 “Young Piglets” 👉 “Weaner Piglets”
5. PRICE LINK ENGINE
COLUMN: Suggested_Price_Category
Example output:

Weaner Piglets|10_to_14_Kg
🔥 THIS IS CRITICAL FOR SYSTEM SCALING
This field:
connects to SALES_PRICING
allows dynamic pricing
allows AI to answer price questions correctly