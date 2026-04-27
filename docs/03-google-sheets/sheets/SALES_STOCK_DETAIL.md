# SALES_STOCK_DETAIL.md

## Role

Formula-driven to assist the n8n AI (1.0 - SAM - Sales Agent - Chatwoot) with sales data.

## Write Ownership

Read only. Used by n8n, AI, backend, and web app as a sales display source.

## Columns
Sale_Category	Age_Range	Weight_Average	Weight_Band	Qty_Available	Male_Qty	Female_Qty	Castrated_Male_Qty	Price_Range	Status	Available_Pig_IDs	Available_Tag_Numbers

## Formula Logic
Sale_Category	hard values
Age_Range	hard values
Weight_Average	=IF(OR($A2="",$D2=""),"",IFERROR(ROUND(AVERAGE(FILTER(SALES_AVAILABILITY!$F:$F,SALES_AVAILABILITY!$Q:$Q="Yes",SALES_AVAILABILITY!$R:$R=$A2,SALES_AVAILABILITY!$J:$J=$D2)),2),""))
Weight_Band	hard values
Qty_Available	=IF(OR($A2="",$D2=""),"",
 IF($A2="Newborn",
  COUNTIFS(PIG_OVERVIEW!$AD:$AD,"No",PIG_OVERVIEW!$D:$D,"Active",PIG_OVERVIEW!$AB:$AB,$A2,PIG_OVERVIEW!$AC:$AC,$D2),
  COUNTIFS(SALES_AVAILABILITY!$Q:$Q,"Yes",SALES_AVAILABILITY!$R:$R,$A2,SALES_AVAILABILITY!$J:$J,$D2)
 )
)
Male_Qty	=IF(OR($A2="",$D2=""),"",COUNTIFS(SALES_AVAILABILITY!$Q:$Q,"Yes",SALES_AVAILABILITY!$R:$R,$A2,SALES_AVAILABILITY!$J:$J,$D2,SALES_AVAILABILITY!$C:$C,"Male"))
Female_Qty	=IF(OR($A2="",$D2=""),"",COUNTIFS(SALES_AVAILABILITY!$Q:$Q,"Yes",SALES_AVAILABILITY!$R:$R,$A2,SALES_AVAILABILITY!$J:$J,$D2,SALES_AVAILABILITY!$C:$C,"Female"))
Castrated_Male_Qty	=IF(OR($A2="",$D2=""),"",COUNTIFS(SALES_AVAILABILITY!$Q:$Q,"Yes",SALES_AVAILABILITY!$R:$R,$A2,SALES_AVAILABILITY!$J:$J,$D2,SALES_AVAILABILITY!$C:$C,"Castrated_Male"))
Price_Range	=IF(OR($A2="",$D2=""),"",IFERROR(INDEX(FILTER(SALES_PRICING!$C:$C,SALES_PRICING!$A:$A=$A2,SALES_PRICING!$B:$B=$D2),1),""))
Status	=IF($E3="","",IF($E3=0,"Out of Stock",IF($E3<=2,"Low Stock","Available")))
Available_Pig_IDs	=IF(OR($A2="",$D2=""),"",IFERROR(TEXTJOIN(", ",TRUE,FILTER(SALES_AVAILABILITY!$A:$A,SALES_AVAILABILITY!$Q:$Q="Yes",SALES_AVAILABILITY!$R:$R=$A2,SALES_AVAILABILITY!$J:$J=$D2)),""))
Available_Tag_Numbers =IF(OR($A2="",$D2=""),"",IFERROR(TEXTJOIN(", ",TRUE,FILTER(SALES_AVAILABILITY!$B:$B,SALES_AVAILABILITY!$Q:$Q="Yes",SALES_AVAILABILITY!$R:$R=$A2,SALES_AVAILABILITY!$J:$J=$D2)),""))


## Hard Values in the columns, but if we can make the formula driven even better
"Sale_Category"
Newborn
Young Piglets
Young Piglets
Weaner Piglets
Weaner Piglets
Weaner Piglets
Grower Pigs
Grower Pigs
Grower Pigs
Grower Pigs
Grower Pigs
Grower Pigs
Finisher Pigs
Finisher Pigs
Finisher Pigs
Finisher Pigs
Finisher Pigs
Finisher Pigs
Ready for Slaughter
Ready for Slaughter
Ready for Slaughter

"Age_Range"
Not yet weighed
Piglet
Piglet
Weaner
Weaner
Weaner
Grower
Grower
Grower
Grower
Grower
Grower
Finisher
Finisher
Finisher
Finisher
Finisher
Finisher
Ready for Slaughter
Ready for Slaughter
Ready for Slaughter

"Weight_Band"
N/A
2_to_4_Kg
5_to_6_Kg
7_to_9_Kg
10_to_14_Kg
15_to_19_Kg
20_to_24_Kg
25_to_29_Kg
30_to_34_Kg
35_to_39_Kg
40_to_44_Kg
45_to_49_Kg
50_to_54_Kg
55_to_59_Kg
60_to_64_Kg
65_to_69_Kg
70_to_74_Kg
75_to_79_Kg
80_to_84_Kg
85_to_89_Kg
90_to_94_Kg

"Status" only the newborn is marked as a hard value now becuase I did not want to show them up as sales but want to display them should people want to know about it thus the Status is equal to "Not for Sale" untill we decide what to do with them.