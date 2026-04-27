# PIG_OVERVIEW.md

## Role

Formula-driven pig overview view for display and lookup.

## Write Ownership

Read only. Operational changes belong in `PIG_MASTER`.

## Columns
Pig_ID	Tag_Number	Pig_Name	Status	On_Farm	Animal_Type	Sex	Date_Of_Birth	Age_Days	Age_Weeks	Litter_ID	Mother_Pig_ID	Father_Pig_ID	Maternal_Line	Paternal_Line	Family_Line_Summary	Current_Pen_ID	Purpose	Current_Weight_Kg	Last_Weight_Date	Previous_Weight_Kg	Previous_Weight_Date	Weight_Gain_Since_Last_Kg	Days_Since_Last_Weight	Average_Daily_Gain_Kg	Average_Weekly_Gain_Kg	Overall_Average_Daily_Gain_Kg	Calculated_Stage	Weight_Band	Is_Sale_Ready	Reserved_For_Order_ID	Reserved_Status	Last_Treatment_Date	Last_Treatment_Type	Last_Product_Name	Current_Withdrawal_End_Date	Withdrawal_Clear	Needs_Attention	General_Notes	Last_Updated_From_System

## Formula Logic

Pig_ID	=FILTER(PIG_MASTER!A2:A,PIG_MASTER!A2:A<>"")
Tag_Number	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$B:$B,""))
Pig_Name	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$C:$C,""))
Status	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$D:$D,""))
On_Farm	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$E:$E,""))
Animal_Type	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$F:$F,""))
Sex	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$G:$G,""))
Date_Of_Birth	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$H:$H,""))
Age_Days	=IF($H2="","",TODAY()-$H2)
Age_Weeks	=IF($I2="","",ROUND($I2/7,1))
Litter_ID	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$M:$M,""))
Mother_Pig_ID	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$P:$P,""))
Father_Pig_ID	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$Q:$Q,""))
Maternal_Line	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$T:$T,""))
Paternal_Line	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$U:$U,""))
Family_Line_Summary	=IF($A2="","",TEXTJOIN(" x ",TRUE,$L2,$M2))
Current_Pen_ID	=IF($A2="","",IFERROR(INDEX(SORT(FILTER({ROW(LOCATION_HISTORY!$E$2:$E),LOCATION_HISTORY!$E$2:$E},LOCATION_HISTORY!$B$2:$B=$A2,LOCATION_HISTORY!$E$2:$E<>""),1,FALSE),1,2),XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$X:$X,"")))
Purpose	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$V:$V,""))
Current_Weight_Kg	=IF($A2="","",IFERROR(INDEX(SORT(FILTER({WEIGHT_LOG!$C$2:$C,WEIGHT_LOG!$D$2:$D},WEIGHT_LOG!$B$2:$B=$A2,WEIGHT_LOG!$C$2:$C<>""),1,FALSE),1,2),""))
Last_Weight_Date	=IF($A2="","",IFERROR(INDEX(SORT(FILTER({WEIGHT_LOG!$C$2:$C,WEIGHT_LOG!$D$2:$D},WEIGHT_LOG!$B$2:$B=$A2,WEIGHT_LOG!$C$2:$C<>""),1,FALSE),1,1),""))
Previous_Weight_Kg	=IF($A2="","",IFERROR(INDEX(SORT(FILTER({WEIGHT_LOG!$C$2:$C,WEIGHT_LOG!$D$2:$D},WEIGHT_LOG!$B$2:$B=$A2,WEIGHT_LOG!$C$2:$C<>""),1,FALSE),2,2),""))
Previous_Weight_Date	=IF($A2="","",IFERROR(INDEX(SORT(FILTER({WEIGHT_LOG!$C$2:$C,WEIGHT_LOG!$D$2:$D},WEIGHT_LOG!$B$2:$B=$A2,WEIGHT_LOG!$C$2:$C<>""),1,FALSE),2,1),""))
Weight_Gain_Since_Last_Kg	=IF(OR($S2="",$U2=""),"",ROUND($S2-$U2,2))
Days_Since_Last_Weight	=IF(OR($T2="",$V2=""),"", $T2-$V2)
Average_Daily_Gain_Kg	=IF(OR($W2="",$X2="",$X2=0),"",ROUND($W2/$X2,3))
Average_Weekly_Gain_Kg	=IF($Y2="","",ROUND($Y2*7,2))
Overall_Average_Daily_Gain_Kg	=IF($A2="","",IFERROR(ROUND(
($S2-INDEX(SORT(FILTER({WEIGHT_LOG!$C$2:$C,WEIGHT_LOG!$D$2:$D},WEIGHT_LOG!$B$2:$B=$A2,WEIGHT_LOG!$C$2:$C<>""),1,TRUE),1,2))/
($T2-INDEX(SORT(FILTER({WEIGHT_LOG!$C$2:$C,WEIGHT_LOG!$D$2:$D},WEIGHT_LOG!$B$2:$B=$A2,WEIGHT_LOG!$C$2:$C<>""),1,TRUE),1,1))
,3),""))
Calculated_Stage	=IF($A2="","",
IFS(
$F2="Sow","Sow",
$F2="Boar","Boar",
$F2="Gilt","Gilt",
AND($S2="", $I2<40),"Newborn",
$S2="","",
$S2<=1,"Newborn",
$S2<=6,"Young Piglet",
$S2<=19,"Weaner",
$S2<=49,"Grower",
$S2<=79,"Finisher",
$S2>=80,"Ready for Slaughter",
TRUE,$F2
))
Weight_Band	=IF($A2="","",
IFS(
AND($S2="", $I2<40),"N/A",
$S2="","",
$S2<=1,"0_to_1_Days",
$S2<=4,"2_to_4_Kg",
$S2<=6,"5_to_6_Kg",
$S2<=9,"7_to_9_Kg",
$S2<=14,"10_to_14_Kg",
$S2<=19,"15_to_19_Kg",
$S2<=24,"20_to_24_Kg",
$S2<=29,"25_to_29_Kg",
$S2<=34,"30_to_34_Kg",
$S2<=39,"35_to_39_Kg",
$S2<=44,"40_to_44_Kg",
$S2<=49,"45_to_49_Kg",
$S2<=54,"50_to_54_Kg",
$S2<=59,"55_to_59_Kg",
$S2<=64,"60_to_64_Kg",
$S2<=69,"65_to_69_Kg",
$S2<=74,"70_to_74_Kg",
$S2<=79,"75_to_79_Kg",
$S2<=84,"80_to_84_Kg",
$S2<=89,"85_to_89_Kg",
$S2<=94,"90_to_94_Kg"
))
Is_Sale_Ready	=IF($A2="","",
IF(
AND(
$D2="Active",
$E2="Yes",
$AK2="Yes",
$AF2="Available",
$R2="Sale",
OR(
$AB2="Young Piglet",
$AB2="Weaner",
$AB2="Grower",
$AB2="Finisher",
$AB2="Ready for Slaughter"
)
),
"Yes",
"No"
))
Reserved_For_Order_ID	=IF($A2="","",IFERROR(INDEX(FILTER(ORDER_LINES!$B:$B,ORDER_LINES!$C:$C=$A2,ORDER_LINES!$K:$K="Reserved"),1),""))
Reserved_Status	=IF($A2="","",
IF($D2="Sold","Sold",
IF($D2="Slaughtered","Slaughtered",
IF(OR($D2<>"Active",$E2<>"Yes"),"Not_For_Sale",
IF(OR($R2="Breeding",$R2="Replacement",$R2="House_Use"),"Not_For_Sale",
IF($AE2<>"","Reserved","Available")
)))))
Last_Treatment_Date	=IF($A2="","",IFERROR(INDEX(SORT(FILTER({MEDICAL_LOG!$C$2:$C,MEDICAL_LOG!$D$2:$D,MEDICAL_LOG!$F$2:$F,MEDICAL_LOG!$M$2:$M},MEDICAL_LOG!$B$2:$B=$A2,MEDICAL_LOG!$C$2:$C<>""),1,FALSE),1,1),""))
Last_Treatment_Type	=IF($A2="","",IFERROR(INDEX(SORT(FILTER({MEDICAL_LOG!$C$2:$C,MEDICAL_LOG!$D$2:$D,MEDICAL_LOG!$F$2:$F,MEDICAL_LOG!$M$2:$M},MEDICAL_LOG!$B$2:$B=$A2,MEDICAL_LOG!$C$2:$C<>""),1,FALSE),1,2),""))
Last_Product_Name	=IF($A2="","",IFERROR(INDEX(SORT(FILTER({MEDICAL_LOG!$C$2:$C,MEDICAL_LOG!$D$2:$D,MEDICAL_LOG!$F$2:$F,MEDICAL_LOG!$M$2:$M},MEDICAL_LOG!$B$2:$B=$A2,MEDICAL_LOG!$C$2:$C<>""),1,FALSE),1,3),""))
Current_Withdrawal_End_Date	=IF($A2="","",IFERROR(MAX(FILTER(MEDICAL_LOG!$M$2:$M,MEDICAL_LOG!$B$2:$B=$A2,MEDICAL_LOG!$M$2:$M<>"")),""))
Withdrawal_Clear	=IF($A2="","",
IF(OR($AJ2="",TODAY()>=$AJ2),"Yes","No"))
Needs_Attention	=IF($A2="","",
IF(
OR(
$S2="",
AND($T2<>"",TODAY()-$T2>14),
$AK2="No"
),
"Yes",
"No"
))
General_Notes	=IF($A2="","",XLOOKUP($A2,PIG_MASTER!$A:$A,PIG_MASTER!$AH:$AH,""))
Last_Updated_From_System =IF($A2="","",TODAY())

## Notes
"Age_Days" and	"Age_Weeks" needs to be updated that it stops calculating the days after the animals has died or was sold or exited or is not on farm any more. becuse this become useless for us we just need to know the age when they left the farm and use this for all other things. Otherwise it just keeps aging. 