# MATING_OVERVIEW.md

## Role

Formula-driven mating log view for display and lookup.

## Write Ownership

Read only. Operational changes belong in `MATING_LOG`.

## Columns
Mating_ID	Sow_Pig_ID	Sow_Tag_Number	Boar_Pig_ID	Boar_Tag_Number	Mating_Date	Mating_Method	Exposure_Group	Expected_Pregnancy_Check_Date	Pregnancy_Check_Date	Pregnancy_Check_Result	Expected_Farrowing_Date	Actual_Farrowing_Date	Mating_Status	Outcome	Linked_Litter_ID	Days_Since_Mating	Is_Open	Is_Overdue_Check	Is_Overdue_Farrowing	Service_Notes	Created_At	Updated_At

## Formula Logic

Mating_ID	=IF(MATING_LOG!A2="","",MATING_LOG!A2)
Sow_Pig_ID	=IF($A2="","",MATING_LOG!B2)
Sow_Tag_Number	=IF($A2="","",MATING_LOG!C2)
Boar_Pig_ID	=IF($A2="","",MATING_LOG!D2)
Boar_Tag_Number	=IF($A2="","",MATING_LOG!E2)
Mating_Date	=IF($A2="","",MATING_LOG!F2)
Mating_Method	=IF($A2="","",MATING_LOG!G2)
Exposure_Group	=IF($A2="","",MATING_LOG!H2)
Expected_Pregnancy_Check_Date	=IF($A2="","",IF(MATING_LOG!I2<>"",MATING_LOG!I2,IF($F2<>"",$F2+21,"")))
Pregnancy_Check_Date	=IF($A2="","",MATING_LOG!J2)
Pregnancy_Check_Result	=IF($A2="","",IF(MATING_LOG!K2<>"",MATING_LOG!K2,"Pending"))
Expected_Farrowing_Date	=IF($A2="","",IF(MATING_LOG!L2<>"",MATING_LOG!L2,IF($F2<>"",$F2+114,"")))
Actual_Farrowing_Date	=IF($A2="","",MATING_LOG!M2)
Mating_Status	=IF($A2="","",
IF(MATING_LOG!N2<>"",MATING_LOG!N2,
IF($M2<>"","Farrowed",
IF($K2="Pregnant","Confirmed_Pregnant",
IF($K2="Not_Pregnant","Not_Pregnant",
IF(AND($J2="",TODAY()>$I2),"Awaiting_Check","Open"))))))
Outcome	=IF($A2="","",
IF(MATING_LOG!O2<>"",MATING_LOG!O2,
IF($M2<>"","Farrowed",
IF($K2="Pregnant","Pregnant",
IF($K2="Not_Pregnant","Empty","Pending")))))
Linked_Litter_ID	=IF($A2="","",MATING_LOG!P2)
Days_Since_Mating	=IF($A2="","",IF($F2="","",TODAY()-$F2))
Is_Open	=IF($A2="","",IF(OR($N2="Open",$N2="Awaiting_Check",$N2="Confirmed_Pregnant"),"Yes","No"))
Is_Overdue_Check	=IF($A2="","",IF(AND($J2="",TODAY()>$I2,OR($N2="Open",$N2="Awaiting_Check")),"Yes","No"))
Is_Overdue_Farrowing	=IF($A2="","",IF(AND($M2="",TODAY()>$L2,$K2="Pregnant"),"Yes","No"))
Service_Notes	=IF($A2="","",MATING_LOG!R2)
Created_At	=IF($A2="","",MATING_LOG!S2)
Updated_At  =IF($A2="","",MATING_LOG!T2)

## Notes:
"Mating_ID" I think should be a filter formula same as the others that said it the same style through all the overview sheets and we keep the structure, So I thinik this needs to changed. 
"Linked_Litter_ID" should be carried over from MATING_LOG but if the litter was added it should auto updated this when we "Add Litter".