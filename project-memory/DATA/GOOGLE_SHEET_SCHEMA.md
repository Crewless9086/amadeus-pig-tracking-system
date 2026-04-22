This is a solid base. It is much better than the earlier drafts.
What it still needs is tighter control in four areas:

Clear write ownership
Clear read ownership
Explicit relationship rules
A few schema corrections / warnings so future AI does not misuse fields

The biggest risk right now is not missing columns. The biggest risk is that a future AI or developer will read this and still treat a formula sheet like a writable operational table, or assume a display sheet is a transactional source of truth.
Below is the tightened version.
GOOGLE_SHEETS_SCHEMA.md
1. Purpose
This document defines the Google Sheets data model for the Amadeus pig and order system.
It exists to ensure that:

all sheets have a clear role
manual-entry sheets are separated from formula-driven sheets
n8n, backend code, and future app logic write to the correct places
no one accidentally writes into overview sheets that should only calculate
every AI or developer working on the system understands what each sheet is for
transactional truth is separated from reporting truth
formula-driven views are never treated as write targets

This document is the schema reference for:

n8n workflows
Flask/backend code
web app development
AppSheet / admin tooling
AI assistant logic
debugging data mismatches
future system expansion


2. Core Sheet Classification
The sheets fall into four groups.
2.1 Master / source-of-truth sheets
These hold hard data and are the sheets the backend, app, and workflows should write to.
These include:

PIG_MASTER
ORDER_MASTER
ORDER_LINES
LITTERS
WEIGHT_LOG
MEDICAL_LOG
MATING_LOG
ORDER_STATUS_LOG
LOCATION_HISTORY
PEN_REGISTER
PRODUCT_REGISTER
USERS
SALES_PRICING

2.2 Formula-driven operational overview sheets
These are calculated sheets used for viewing, filtering, availability logic, and web app display.
These include:

PIG_OVERVIEW
MATING_OVERVIEW
SALES_AVAILABILITY
ORDER_OVERVIEW
LITTER_OVERVIEW

2.3 Formula-driven sales display sheets
These summarize available sale stock for sales workflows and AI responses.
These include:

SALES_STOCK_DETAIL
SALES_STOCK_TOTALS
SALES_STOCK_SUMMARY

2.4 Templates / presentation sheets
These are not core transactional tables.
These include:

quote template sheet
invoice template sheet


3. Critical Schema Rule
3.1 Write rule
Backend, n8n, AppSheet, Flask app, and any future web app must write only to:

source-of-truth sheets
transaction log sheets
approved register sheets

They must never write directly into:

overview sheets
stock summary sheets
formula display sheets
template / presentation sheets

3.2 Read rule
Formula-driven sheets are valid read surfaces for:

dashboards
AI context
web app display
availability calculations
reporting
order summary views

They are not valid write surfaces.
3.3 Source-of-truth rule
If a formula-driven sheet and a master sheet appear to disagree, the system must trace the underlying source data and formulas. The formula sheet is a computed view, not the original write target.

4. Sheet Definitions

4.1 PIG_OVERVIEW
Type: Formula-driven overview
Purpose: Operational overview of each pig for viewing in the web app and system dashboards.
Write policy: Read-only. Never write directly.
Primary key: Pig_ID
Columns

Pig_ID
Tag_Number
Pig_Name
Status
On_Farm
Animal_Type
Sex
Date_Of_Birth
Age_Days
Age_Weeks
Litter_ID
Mother_Pig_ID
Father_Pig_ID
Maternal_Line
Paternal_Line
Family_Line_Summary
Current_Pen_ID
Purpose
Current_Weight_Kg
Last_Weight_Date
Previous_Weight_Kg
Previous_Weight_Date
Weight_Gain_Since_Last_Kg
Days_Since_Last_Weight
Average_Daily_Gain_Kg
Average_Weekly_Gain_Kg
Overall_Average_Daily_Gain_Kg
Calculated_Stage
Weight_Band
Is_Sale_Ready
Reserved_For_Order_ID
Reserved_Status
Last_Treatment_Date
Last_Treatment_Type
Last_Product_Name
Current_Withdrawal_End_Date
Withdrawal_Clear
Needs_Attention
General_Notes
Last_Updated_From_System

Depends on

PIG_MASTER
WEIGHT_LOG
MEDICAL_LOG
LOCATION_HISTORY
reservation-linked order logic
other derived formula logic

Critical notes

This is the main live operational read view of a pig.
UI may prefer Pig_Name over Tag_Number where present.
Is_Sale_Ready, Weight_Band, and Calculated_Stage are derived fields and must not be manually written by workflows.


4.2 MATING_OVERVIEW
Type: Formula-driven overview
Purpose: Calculated mating and breeding tracking view.
Write policy: Read-only. Never write directly.
Primary key: Mating_ID
Columns

Mating_ID
Sow_Pig_ID
Sow_Tag_Number
Boar_Pig_ID
Boar_Tag_Number
Mating_Date
Mating_Method
Exposure_Group
Expected_Pregnancy_Check_Date
Pregnancy_Check_Date
Pregnancy_Check_Result
Expected_Farrowing_Date
Actual_Farrowing_Date
Mating_Status
Outcome
Linked_Litter_ID
Days_Since_Mating
Is_Open
Is_Overdue_Check
Is_Overdue_Farrowing
Service_Notes
Created_At
Updated_At

Depends on

MATING_LOG
LITTERS
PIG_MASTER

Critical notes

This is a breeding operations view, not a transaction sheet.
All real mating records must be written to MATING_LOG.


4.3 SALES_AVAILABILITY
Type: Formula-driven operational sales sheet
Purpose: Operational source of truth for which pigs are currently sellable and matchable to orders.
Write policy: Read-only. Never write directly.
Primary key: Pig_ID
Columns

Pig_ID
Tag_Number
Sex
Date_Of_Birth
Age_Days
Current_Weight_Kg
Last_Weight_Date
Average_Daily_Gain_Kg
Calculated_Stage
Weight_Band
Current_Pen_ID
Status
On_Farm
Withdrawal_Clear
Reserved_Status
Reserved_For_Order_ID
Available_For_Sale
Sale_Category
Suggested_Price_Category
Sales_Notes

Depends on

PIG_OVERVIEW
reservation-linked order state
SALES_PRICING
formula logic

Critical use
This sheet is used by:

AI Sales Agent stock answers
order matching logic
sync order lines logic
sales availability responses
future website / API stock display

Critical notes

This sheet is the effective sales-readiness read surface.
It should be treated as the operational availability truth for matching and selling.
It is formula-driven and must never be directly edited by workflows.
Available_For_Sale is the final gate for whether a pig can be surfaced or matched.

Schema correction note
Your earlier raw list used StatusOn_Farm, but the formulas you gave clearly separate these into:

Status
On_Farm

That is the cleaner and more correct schema naming. Keep it that way in the doc.

4.4 ORDER_OVERVIEW
Type: Formula-driven order overview
Purpose: Aggregated order dashboard sheet for read operations.
Write policy: Read-only. Never write directly.
Primary key: Order_ID
Columns

Order_ID
Order_Date
Customer_Name
Customer_Phone
Customer_Channel
Customer_Language
Order_Source
Requested_Category
Requested_Weight_Range
Requested_Sex
Requested_Quantity
Reserved_Pig_Count
Quoted_Total
Final_Total
Order_Status
Approval_Status
Payment_Status
Collection_Date
Collection_Location
Line_Count
Reserved_Line_Count
Confirmed_Line_Count
Collected_Line_Count
Reserved_Pig_IDs
Reserved_Tag_Numbers
Notes
Created_By
Created_At
Updated_At

Depends on

ORDER_MASTER
ORDER_LINES
ORDER_STATUS_LOG

Critical use
Used by:

Flask list_orders
Flask get_order_detail
admin dashboards
order workflow reviews

Critical notes

This is a reporting / read surface.
Header edits belong in ORDER_MASTER.
Line edits belong in ORDER_LINES.

Schema correction note
In one earlier version, NotesCreated_By appeared merged by mistake. It must remain two separate columns:

Notes
Created_By


4.5 LITTER_OVERVIEW
Type: Formula-driven litter overview
Purpose: Aggregated operational view of litter performance and status.
Write policy: Read-only. Never write directly.
Primary key: Litter_ID
Columns

Litter_ID
Farrowing_Date
Sow_Pig_ID
Boar_Pig_ID
Sow_Tag_Number
Boar_Tag_Number
Current_Pen_ID
Total_Born
Born_Alive
Stillborn_Count
Mummified_Count
Male_Count
Female_Count
Fostered_In_Count
Fostered_Out_Count
Weaned_Count
Wean_Date
Average_Wean_Weight_Kg
Pig_Master_Row_Count
Active_Pig_Count
On_Farm_Pig_Count
Tagged_Pig_Count
Untagged_Pig_Count
Exited_Pig_Count
Average_Current_Weight_Kg
Youngest_Age_Days
Oldest_Age_Days
Sex_Assigned_Count
Sex_Unassigned_Count
Litter_Status
Needs_Attention
Litter_Notes
Created_At

Depends on

LITTERS
PIG_MASTER
PIG_OVERVIEW


4.6 PIG_MASTER
Type: Source-of-truth master sheet
Purpose: Core entity sheet for all pigs.
Write policy: Writable by app / backend / n8n.
Primary key: Pig_ID
ID format

Pig_ID = PIG-YYYY-####

Columns

Pig_ID
Tag_Number
Pig_Name
Status
On_Farm
Animal_Type
Sex
Date_Of_Birth
Birth_Month
Birth_Year
Breed_Type
Colour_Markings
Litter_ID
Litter_Size_Born
Litter_Size_Weaned
Mother_Pig_ID
Father_Pig_ID
Mother_Tag_Number
Father_Tag_Number
Maternal_Line
Paternal_Line
Purpose
Current_Stage
Current_Pen_ID
Source
Acquisition_Date
Birth_Weight_Kg
Wean_Date
Wean_Weight_Kg
Exit_Date
Exit_Reason
Exit_Order_ID
Carcass_Weight_Kg
General_Notes
Created_At
Updated_At

Controlled values

Status = Active, Sold, Slaughter, Died, Culled, Missing, Archived
On_Farm = Yes, No
Animal_Type = Piglet, Weaner, Grower, Finisher, Gilt, Sow, Boar
Sex = Male, Female, Castrated_Male, Unknown
Breed_Type = Landrace, Large White, Mix (Lan & LRG), Mix Landrace, Mix Large White
Purpose = Breeding, Grow_Out, Sale, Replacement, House_Use, Unknown
Source = Born_On_Farm, Bought_In, Transfer, Unknown
Exit_Reason = Sold, Slaughtered, Died, Culled, Missing, Transfer_Out

Critical notes

This is the base pig entity table.
Systems should write pig master truth here, not to overview sheets.
Current_Stage is a stored field, but operational calculated stage for selling should still be treated from overview/formula logic where applicable.


4.7 ORDER_MASTER
Type: Source-of-truth master sheet
Purpose: Core order header table.
Write policy: Writable by backend / n8n / app.
Primary key: Order_ID
ID format

Order_ID = ORD-YYYY-######

Columns

Order_ID
Order_Date
Customer_Name
Customer_Phone
Customer_Channel
Customer_Language
Order_Source
Requested_Category
Requested_Weight_Range
Requested_Sex
Requested_Quantity
Quoted_Total
Final_Total
Order_Status
Approval_Status
Collection_Method
Collection_Location
Collection_Date
Payment_Status
Reserved_Pig_Count
Notes
Created_By
Created_At
Updated_At

Critical notes

This is the order header truth.
A draft order begins here.
This sheet must not be treated as line-level truth.


4.8 LITTERS
Type: Source-of-truth master sheet
Purpose: Core litter records.
Write policy: Writable by app / backend.
Primary key: Litter_ID
ID format

Litter_ID = LIT-YYYY-####

Columns

Litter_ID
Farrowing_Date
Sow_Pig_ID
Boar_Pig_ID
Sow_Tag_Number
Boar_Tag_Number
Total_Born
Born_Alive
Stillborn_Count
Mummified_Count
Male_Count
Female_Count
Fostered_In_Count
Fostered_Out_Count
Weaned_Count
Wean_Date
Average_Wean_Weight_Kg
Litter_Notes
Created_At
Current_Pen_ID


4.9 WEIGHT_LOG
Type: Transaction log
Purpose: Stores all weight history events.
Write policy: Writable by app / backend.
Primary key: Weight_Log_ID
ID format

Weight_Log_ID = WGT-########

Columns

Weight_Log_ID
Pig_ID
Weight_Date
Weight_Kg
Weighed_By
Scale_Used
Condition_Notes
Stage_At_Weighing
Created_At

Critical notes

This is append-style event history.
Current weight in overview sheets should be derived from this log plus pig logic.


4.10 MEDICAL_LOG
Type: Transaction log
Purpose: Stores treatment and medical events.
Write policy: Writable by app / backend.
Primary key: Medical_Log_ID
ID format

Medical_Log_ID = MED-########

Columns

Medical_Log_ID
Pig_ID
Treatment_Date
Treatment_Type
Product_ID
Product_Name
Dose
Dose_Unit
Route
Reason_For_Treatment
Batch_Lot_Number
Withdrawal_Days
Withdrawal_End_Date
Given_By
Follow_Up_Required
Follow_Up_Date
Medical_Notes
Created_At

Controlled values

Treatment_Type = Vaccination, Deworming, Antibiotic, Iron, Vitamin, Injury_Treatment, Support_Care, Other
Route = Oral, IM, SC, Topical, Other
Follow_Up_Required = Yes, No


4.11 MATING_LOG
Type: Transaction / master hybrid
Purpose: Stores mating records.
Write policy: Writable by app / backend.
Primary key: Mating_ID
ID format

Mating_ID = MAT-YYYY-######

Columns

Mating_ID
Sow_Pig_ID
Sow_Tag_Number
Boar_Pig_ID
Boar_Tag_Number
Mating_Date
Mating_Method
Exposure_Group
Expected_Pregnancy_Check_Date
Pregnancy_Check_Date
Pregnancy_Check_Result
Expected_Farrowing_Date
Actual_Farrowing_Date
Mating_Status
Outcome
Linked_Litter_ID
Days_Since_Mating
Service_Notes
Created_At
Updated_At


4.12 ORDER_STATUS_LOG
Type: Transaction log
Purpose: Audit trail for order status changes.
Write policy: Writable by backend / n8n / app.
Primary key: Order_Status_Log_ID
ID format

Order_Status_Log_ID = OSL-YYYY-######

Columns

Order_Status_Log_ID
Order_ID
Status_Date
Old_Status
New_Status
Changed_By
Change_Source
Notes
Created_At

Critical notes

This is status history, not current status truth.
Current order status lives in ORDER_MASTER.


4.13 LOCATION_HISTORY
Type: Transaction log
Purpose: Tracks pig movement between pens / locations.
Write policy: Writable by app / backend.
Primary key: Move_Log_ID
ID format

Move_Log_ID = MOV-########

Columns

Move_Log_ID
Pig_ID
Move_Date
From_Pen_ID
To_Pen_ID
Reason_For_Move
Moved_By
Group_Batch_ID
Move_Notes
Created_At


4.14 PEN_REGISTER
Type: Register sheet
Purpose: Pen master data.
Write policy: Writable manually or by controlled admin tools.
Primary key: Pen_ID
ID format

Pen_ID = PEN-001 onward

Columns

Pen_ID
Pen_Name
Pen_Type
Capacity
Is_Active
Pen_Notes

Controlled values

Pen_Type = Farrowing, Nursery, Weaner, Grower, Finisher, Gilt, Sow, Boar, Isolation, Holding, Mixed
Is_Active = Yes, No


4.15 PRODUCT_REGISTER
Type: Register sheet
Purpose: Product and medicine master data.
Write policy: Writable manually or by controlled admin tools.
Primary key: Product_ID
ID format

Product_ID = PRD-001 onward

Columns

Product_ID
Product_Name
Product_Category
Default_Dose
Dose_Unit
Default_Withdrawal_Days
Supplier
Batch_Tracking_Required
Is_Active
Product_Notes

Controlled values

Product_Category = Vaccine, Deworm, Antibiotic, Vitamin, Iron, Supplement, Topical, Other
Batch_Tracking_Required = Yes, No
Is_Active = Yes, No

Schema correction note
Use Other consistently, not sometimes other.

4.16 SALES_STOCK_DETAIL
Type: Formula-driven sales display sheet
Purpose: Detailed grouped sales availability view.
Write policy: Read-only. Never write directly.
Columns

Sale_Category
Age_Range
Weight_Average
Weight_Band
Qty_Available
Male_Qty
Female_Qty
Castrated_Male_Qty
Price_Range
Status
Available_Pig_IDs
Available_Tag_Numbers

Depends on

SALES_AVAILABILITY
SALES_PRICING


4.17 SALES_STOCK_TOTALS
Type: Formula-driven sales display sheet
Purpose: Grouped totals by sales category.
Write policy: Read-only. Never write directly.
Columns

Sale_Category
Category_Code
Age_Range
Weight_Range
Qty_Available
Male_Qty
Female_Qty
Castrated_Male_Qty
Price_Range
Status

Depends on

SALES_AVAILABILITY
SALES_PRICING


4.18 SALES_STOCK_SUMMARY
Type: Formula-driven sales display sheet
Purpose: Summary sheet used for AI responses and customer-facing sales summaries.
Write policy: Read-only. Never write directly.
Columns

Sale_Category
Category_Code
Age_Range
Weight_Band
Qty_Available
Male_Qty
Female_Qty
Castrated_Male_Qty
Price_Range
Status

Depends on

SALES_AVAILABILITY
SALES_PRICING

Critical use

Fast AI stock summaries
grouped customer-facing availability responses
summary display logic


4.19 SALES_PRICING
Type: Manual pricing table
Purpose: Pricing source of truth for sales logic.
Write policy: Manual update only.
Primary key: logical composite key of Sale_Category + Weight_Band
Columns

Sale_Category
Weight_Band
Price_Range

Critical rule
This is factual pricing and should only be changed directly by you on the sheet.
Critical notes

AI and workflows may read this.
They must not overwrite it.
Pricing logic should map to this table, not bypass it.


4.20 ORDER_LINES
Type: Source-of-truth child transaction sheet
Purpose: Stores individual pig lines linked to an order.
Write policy: Writable by backend / n8n / app.
Primary key: Order_Line_ID
ID format

Order_Line_ID = OL-YYYY-######

Columns

Order_Line_ID
Order_ID
Pig_ID
Tag_Number
Sale_Category
Weight_Band
Sex
Current_Weight_Kg
Unit_Price
Line_Status
Reserved_Status
Notes
Created_At
Updated_At
Request_Item_Key

Critical use
Used by:

sync order lines logic
reserve / release logic
order detail retrieval
order overview formulas
sales availability reservation logic

Critical notes

This is the line-level truth for an order.
Request_Item_Key is important for split-request synchronization, especially where one customer request creates multiple grouped requested items.


4.21 USERS
Type: Register sheet
Purpose: Future user access and login control.
Write policy: Controlled admin / manual.
Primary key: User_Email
Columns

User_Email
User_Name
User_Surname

Critical notes

This is reserved for access control and future app security.
It should not yet be treated as a full auth system by itself.


5. Relationships Summary
5.1 Pig-centered

PIG_MASTER is the base pig record
WEIGHT_LOG, MEDICAL_LOG, and LOCATION_HISTORY attach event history to pigs
PIG_OVERVIEW calculates the live operational state of the pig
SALES_AVAILABILITY filters and interprets pig sale readiness from that live state
SALES_STOCK_* sheets summarize that availability for display and AI use

5.2 Order-centered

ORDER_MASTER is the header
ORDER_LINES is the detail
ORDER_STATUS_LOG is the audit trail
ORDER_OVERVIEW is the reporting layer

5.3 Breeding-centered

MATING_LOG stores mating/service records
LITTERS stores farrowing/litter records
MATING_OVERVIEW and LITTER_OVERVIEW are formula views

5.4 Register-centered

PEN_REGISTER controls pen metadata
PRODUCT_REGISTER controls treatment/product metadata
USERS controls future access metadata
SALES_PRICING controls manual pricing truth


6. Non-Negotiable Rules

Never write to overview sheets
Never write to sales summary sheets
Never treat formula sheets as the primary source of truth for updates
Use PIG_MASTER, ORDER_MASTER, ORDER_LINES, logs, and registers as write targets
Use overview and summary sheets for reading, filtering, display, and AI context
Treat SALES_AVAILABILITY as the operational sales-read truth for matching, but not as a write target
Treat ORDER_OVERVIEW as a read/reporting layer, not a transaction layer
