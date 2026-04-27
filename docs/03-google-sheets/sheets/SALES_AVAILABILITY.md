# SALES_AVAILABILITY.md

## Role

Formula-driven sales availability view.

## Write Ownership

Read only. Do not write to this sheet from backend, n8n, AI agents, or manual operational tooling unless intentionally changing formulas.

## Columns
Pig_ID	Tag_Number	Sex	Date_Of_Birth	Age_Days	Current_Weight_Kg	Last_Weight_Date	Average_Daily_Gain_Kg	Calculated_Stage	Weight_Band	Current_Pen_ID	Status	On_Farm	Withdrawal_Clear	Reserved_Status	Reserved_For_Order_ID	Available_For_Sale	Sale_Category	Suggested_Price_Category	Sales_Notes

## Formula Logic

Pig_ID	=FILTER(
PIG_OVERVIEW!A2:A,
PIG_OVERVIEW!A2:A<>"",
PIG_OVERVIEW!AD2:AD="Yes"
)
Tag_Number	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$B:$B,""))
Sex	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$G:$G,""))
Date_Of_Birth	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$H:$H,""))
Age_Days	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$I:$I,""))
Current_Weight_Kg	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$S:$S,""))
Last_Weight_Date	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$T:$T,""))
Average_Daily_Gain_Kg	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$Y:$Y,""))
Calculated_Stage	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$AB:$AB,""))
Weight_Band	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$AC:$AC,""))
Current_Pen_ID	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$Q:$Q,""))
Status	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$D:$D,""))
On_Farm	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$E:$E,""))
Withdrawal_Clear	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$AK:$AK,""))
Reserved_Status	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$AF:$AF,""))
Reserved_For_Order_ID	=IF($A2="","",XLOOKUP($A2,PIG_OVERVIEW!$A:$A,PIG_OVERVIEW!$AE:$AE,""))
Available_For_Sale	=IF($A2="","",IF(AND($L2="Active",$M2="Yes",$N2="Yes",$O2="Available",OR($I2="Young Piglet",$I2="Weaner",$I2="Grower",$I2="Finisher",$I2="Ready for Slaughter")),"Yes","No"))
Sale_Category	=IF(OR($Q2<>"Yes",$J2=""),"",IFERROR(IFS($J2="0_to_1_Days","Newborn Piglets",OR($J2="2_to_4_Kg",$J2="5_to_6_Kg"),"Young Piglets",OR($J2="7_to_9_Kg",$J2="10_to_14_Kg",$J2="15_to_19_Kg"),"Weaner Piglets",OR($J2="20_to_24_Kg",$J2="25_to_29_Kg",$J2="30_to_34_Kg",$J2="35_to_39_Kg",$J2="40_to_44_Kg",$J2="45_to_49_Kg"),"Grower Pigs",OR($J2="50_to_54_Kg",$J2="55_to_59_Kg",$J2="60_to_64_Kg",$J2="65_to_69_Kg",$J2="70_to_74_Kg",$J2="75_to_79_Kg"),"Finisher Pigs",OR($J2="80_to_84_Kg",$J2="85_to_89_Kg",$J2="90_to_94_Kg"),"Ready for Slaughter"),""))
Suggested_Price_Category	=IF(OR($Q2<>"Yes",$J2=""),"",IFERROR(IFS($J2="0_to_1_Days","Newborn Piglets|N/A",$J2="2_to_4_Kg","Young Piglets|2_to_4_Kg",$J2="5_to_6_Kg","Young Piglets|5_to_6_Kg",$J2="7_to_9_Kg","Weaner Piglets|7_to_9_Kg",$J2="10_to_14_Kg","Weaner Piglets|10_to_14_Kg",$J2="15_to_19_Kg","Weaner Piglets|15_to_19_Kg",$J2="20_to_24_Kg","Grower Pigs|20_to_24_Kg",$J2="25_to_29_Kg","Grower Pigs|25_to_29_Kg",$J2="30_to_34_Kg","Grower Pigs|30_to_34_Kg",$J2="35_to_39_Kg","Grower Pigs|35_to_39_Kg",$J2="40_to_44_Kg","Grower Pigs|40_to_44_Kg",$J2="45_to_49_Kg","Grower Pigs|45_to_49_Kg",$J2="50_to_54_Kg","Finisher Pigs|50_to_54_Kg",$J2="55_to_59_Kg","Finisher Pigs|55_to_59_Kg",$J2="60_to_64_Kg","Finisher Pigs|60_to_64_Kg",$J2="65_to_69_Kg","Finisher Pigs|65_to_69_Kg",$J2="70_to_74_Kg","Finisher Pigs|70_to_74_Kg",$J2="75_to_79_Kg","Finisher Pigs|75_to_79_Kg",$J2="80_to_84_Kg","Ready for Slaughter|80_to_84_Kg",$J2="85_to_89_Kg","Ready for Slaughter|85_to_89_Kg",$J2="90_to_94_Kg","Ready for Slaughter|90_to_94_Kg"),""))
Sales_Notes "no formula" I think this is linked to when we add a note to the order line item and then it might go here? Not sure we need to check this and see if this column has any value. 
