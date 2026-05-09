# ORDER_MASTER.md

## Role

Master/source-of-truth sheet for order headers.

## Columns

Order_ID	Order_Date	Customer_Name	Customer_Phone	Customer_Channel	Customer_Language	Order_Source	Requested_Category	Requested_Weight_Range	Requested_Sex	Requested_Quantity	Quoted_Total	Final_Total	Order_Status	Approval_Status	Collection_Method	Collection_Location	Collection_Date	Payment_Status	Reserved_Pig_Count	Notes	Created_By	Created_At	Updated_At	Payment_Method

## Notes

Make sure that column "Notes" get populated becuase this was not populated. 
"Reserved_Pig_Count" need to be updated once the function runs for reserving the pigs.
`Payment_Method` was added manually for Phase 1.3 and is required before sending an order for approval. Valid values are `Cash` and `EFT`. Backend updates this column by header name and locks it once the order is beyond `Draft`.
