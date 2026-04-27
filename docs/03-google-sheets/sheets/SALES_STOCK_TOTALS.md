# SALES_STOCK_TOTALS.md

## Role

Formula-driven to assist the n8n AI (1.0 - SAM - Sales Agent - Chatwoot) with sales data.

## Write Ownership

Read only. Used by n8n, AI, backend, and web app as a sales display source.

## Columns
Sale_Category	Category_Code	Age_Range	Weight_Band	Qty_Available	Male_Qty	Female_Qty	Castrated_Male_Qty	Price_Range	Status

## Formula Logic
Sale_Category	
Category_Code	
Age_Range	
Weight_Band	
Qty_Available	=IF(OR($A2="",$D2=""),"",
 IF($A2="Newborn",
  COUNTIFS(PIG_OVERVIEW!$AD:$AD,"No",PIG_OVERVIEW!$D:$D,"Active",PIG_OVERVIEW!$AB:$AB,$A2,PIG_OVERVIEW!$AC:$AC,$D2),
  COUNTIFS(SALES_AVAILABILITY!$Q:$Q,"Yes",SALES_AVAILABILITY!$R:$R,$A2,SALES_AVAILABILITY!$J:$J,$D2)
 )
)
Male_Qty	=IF($A2="","",COUNTIFS(SALES_AVAILABILITY!$Q:$Q,"Yes",SALES_AVAILABILITY!$R:$R,$A2,SALES_AVAILABILITY!$C:$C,"Male"))
Female_Qty	=IF($A2="","",COUNTIFS(SALES_AVAILABILITY!$Q:$Q,"Yes",SALES_AVAILABILITY!$R:$R,$A2,SALES_AVAILABILITY!$C:$C,"Female"))
Castrated_Male_Qty	=IF($A2="","",COUNTIFS(SALES_AVAILABILITY!$Q:$Q,"Yes",SALES_AVAILABILITY!$R:$R,$A2,SALES_AVAILABILITY!$C:$C,"Castrated_Male"))
Price_Range	=IF($A2="","",TEXTJOIN(", ",TRUE,UNIQUE(FILTER(SALES_PRICING!$C:$C,SALES_PRICING!$A:$A=$A2))))
Status =IF($E3="","",IF($E3=0,"Out of Stock",IF($E3<=2,"Low Stock","Available")))


## Hard Values in the columns, but if we can make the formula driven even better
"Sale_Category"
Newborn
Young Piglets
Weaner Piglets
Grower Pigs
Finisher Pigs
Ready for Slaughter

"Category_Code"
NBP
YP
WP
GP
FP
RFS

"Age_Range"
Not yet weighed
Piglets
Weaner
Grower
Finisher
Ready for Slaughter

"Weight_Band"
N/A
2_to_6_Kg
7_to_19_Kg
20_to_49_Kg
50_to_79_Kg
80_to_95_Kg

"Status" only the newborn is marked as a hard value now becuase I did not want to show them up as sales but want to display them should people want to know about it thus the Status is equal to "Not for Sale" untill we decide what to do with them.