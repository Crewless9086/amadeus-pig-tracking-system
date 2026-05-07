# ORDER_OVERVIEW.md

## Role

Formula-driven order overview view for display and lookup.

## Write Ownership

Read only. Operational changes belong in `ORDER_MASTER` and `ORDER_LINES`.

## Columns
Order_ID	Order_Date	Customer_Name	Customer_Phone	Customer_Channel	Customer_Language	Order_Source	Requested_Category	Requested_Weight_Range	Requested_Sex	Requested_Quantity	Reserved_Pig_Count	Quoted_Total	Final_Total	Order_Status	Approval_Status	Payment_Status	Collection_Date	Collection_Location	Line_Count	Reserved_Line_Count	Confirmed_Line_Count	Collected_Line_Count	Reserved_Pig_IDs	Reserved_Tag_Numbers	Notes	Created_By	Created_At	Updated_At

## Formula Logic

Order_ID	=IF(ORDER_MASTER!A2="","",ORDER_MASTER!A2) 
Order_Date	=IF($A2="","",ORDER_MASTER!B2)
Customer_Name	=IF($A2="","",ORDER_MASTER!C2)
Customer_Phone	=IF($A2="","",ORDER_MASTER!D2)
Customer_Channel	=IF($A2="","",ORDER_MASTER!E2)
Customer_Language	=IF($A2="","",ORDER_MASTER!F2)
Order_Source	=IF($A2="","",ORDER_MASTER!G2)
Requested_Category	=IF($A2="","",ORDER_MASTER!H2)
Requested_Weight_Range	=IF($A2="","",ORDER_MASTER!I2)
Requested_Sex	=IF($A2="","",ORDER_MASTER!J2)
Requested_Quantity	=IF($A2="","",ORDER_MASTER!K2)
Reserved_Pig_Count	=IF($A2="","",IF(ORDER_MASTER!T2<>"",ORDER_MASTER!T2,COUNTIFS(ORDER_LINES!$B:$B,$A2,ORDER_LINES!$K:$K,"Reserved")))
Quoted_Total	=IF($A2="","",ORDER_MASTER!L2)
Final_Total	    =IF($A2="","",IF(ORDER_MASTER!M2<>"",ORDER_MASTER!M2,SUMIFS(ORDER_LINES!$I:$I,ORDER_LINES!$B:$B,$A2)))
Order_Status	=IF($A2="","",ORDER_MASTER!N2)
Approval_Status	=IF($A2="","",ORDER_MASTER!O2)
Payment_Status	=IF($A2="","",ORDER_MASTER!S2)
Collection_Date	=IF($A2="","",ORDER_MASTER!R2)
Collection_Location	=IF($A2="","",ORDER_MASTER!Q2)
Line_Count	=IF($A2="","",COUNTIF(ORDER_LINES!$B:$B,$A2))

**Semantics:** this counts **every** `ORDER_LINES` row for the order, **including** rows whose `Line_Status` is `Cancelled`. It is a historical row total, not “pigs currently on the order.” For operational counts (e.g. send-for-approval, Sam messaging), use **`active_line_count`** from `GET /api/orders/<order_id>` (computed in the API from line rows where `line_status !== "Cancelled"`), or count non-cancelled lines in tooling.

Reserved_Line_Count	=IF($A2="","",COUNTIFS(ORDER_LINES!$B:$B,$A2,ORDER_LINES!$J:$J,"Reserved"))
Confirmed_Line_Count	=IF($A2="","",COUNTIFS(ORDER_LINES!$B:$B,$A2,ORDER_LINES!$J:$J,"Confirmed"))
Collected_Line_Count	=IF($A2="","",COUNTIFS(ORDER_LINES!$B:$B,$A2,ORDER_LINES!$J:$J,"Collected"))
Reserved_Pig_IDs	=IF($A2="","",IFERROR(TEXTJOIN(", ",TRUE,FILTER(ORDER_LINES!$C:$C,ORDER_LINES!$B:$B=$A2,ORDER_LINES!$K:$K="Reserved")),""))
Reserved_Tag_Numbers	=IF($A2="","",IFERROR(TEXTJOIN(", ",TRUE,FILTER(ORDER_LINES!$D:$D,ORDER_LINES!$B:$B=$A2,ORDER_LINES!$K:$K="Reserved")),""))
Notes	=IF($A2="","",ORDER_MASTER!U2)
Created_By	=IF($A2="","",ORDER_MASTER!V2)
Created_At	=IF($A2="","",ORDER_MASTER!W2)
Updated_At  =IF($A2="","",ORDER_MASTER!X2)
