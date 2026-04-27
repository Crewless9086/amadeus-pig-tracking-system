# LITTER_OVERVIEW.md

## Role

Formula-driven litter overview view for display and lookup.

## Write Ownership

Read only. Operational changes belong in `LITTERS`.

## Columns
Litter_ID	Farrowing_Date	Sow_Pig_ID	Boar_Pig_ID	Sow_Tag_Number	Boar_Tag_Number	Current_Pen_ID	Total_Born	Born_Alive	Stillborn_Count	Mummified_Count	Male_Count	Female_Count	Fostered_In_Count	Fostered_Out_Count	Weaned_Count	Wean_Date	Average_Wean_Weight_Kg	Pig_Master_Row_Count	Active_Pig_Count	On_Farm_Pig_Count	Tagged_Pig_Count	Untagged_Pig_Count	Exited_Pig_Count	Average_Current_Weight_Kg	Youngest_Age_Days	Oldest_Age_Days	Sex_Assigned_Count	Sex_Unassigned_Count	Litter_Status	Needs_Attention	Litter_Notes	Created_At

## Formula Logic

Litter_ID	=IF(LITTERS!A2="","",LITTERS!A2)
Farrowing_Date	=IF($A2="","",LITTERS!B2)
Sow_Pig_ID	=IF($A2="","",LITTERS!C2)
Boar_Pig_ID	=IF($A2="","",LITTERS!D2)
Sow_Tag_Number	=IF($A2="","",LITTERS!E2)
Boar_Tag_Number	=IF($A2="","",LITTERS!F2)
Current_Pen_ID	=IF($A2="","",LITTERS!T2)
Total_Born	=IF($A2="","",LITTERS!G2)
Born_Alive	=IF($A2="","",LITTERS!H2)
Stillborn_Count	=IF($A2="","",LITTERS!I2)
Mummified_Count	=IF($A2="","",LITTERS!J2)
Male_Count	=IF($A2="","",LITTERS!K2)
Female_Count	=IF($A2="","",LITTERS!L2)
Fostered_In_Count	=IF($A2="","",LITTERS!M2)
Fostered_Out_Count	=IF($A2="","",LITTERS!N2)
Weaned_Count	=IF($A2="","",LITTERS!O2)
Wean_Date	=IF($A2="","",LITTERS!P2)
Average_Wean_Weight_Kg	=IF($A2="","",LITTERS!Q2)
Pig_Master_Row_Count	=IF($A2="","",COUNTIF(PIG_MASTER!$M:$M,$A2))
Active_Pig_Count	=IF($A2="","",COUNTIFS(PIG_MASTER!$M:$M,$A2,PIG_MASTER!$D:$D,"Active"))
On_Farm_Pig_Count	=IF($A2="","",COUNTIFS(PIG_MASTER!$M:$M,$A2,PIG_MASTER!$E:$E,"Yes"))
Tagged_Pig_Count	=IF($A2="","",COUNTIFS(PIG_MASTER!$M:$M,$A2,PIG_MASTER!$B:$B,"<>"))
Untagged_Pig_Count	=IF($A2="","",COUNTIFS(PIG_MASTER!$M:$M,$A2,PIG_MASTER!$B:$B,""))
Exited_Pig_Count	=IF($A2="","",COUNTIFS(PIG_MASTER!$M:$M,$A2,PIG_MASTER!$D:$D,"<>Active"))
Average_Current_Weight_Kg	=IF($A2="","",IFERROR(ROUND(AVERAGE(FILTER(PIG_OVERVIEW!$S:$S,PIG_OVERVIEW!$K:$K=$A2,PIG_OVERVIEW!$S:$S<>"")),2),""))
Youngest_Age_Days	=IF($A2="","",IFERROR(MIN(FILTER(PIG_OVERVIEW!$I:$I,PIG_OVERVIEW!$K:$K=$A2,PIG_OVERVIEW!$I:$I<>"")),""))
Oldest_Age_Days	=IF($A2="","",IFERROR(MAX(FILTER(PIG_OVERVIEW!$I:$I,PIG_OVERVIEW!$K:$K=$A2,PIG_OVERVIEW!$I:$I<>"")),""))
Sex_Assigned_Count	=IF($A2="","",COUNTIFS(PIG_OVERVIEW!$K:$K,$A2,PIG_OVERVIEW!$G:$G,"<>"))
Sex_Unassigned_Count	=IF($A2="","",COUNTIFS(PIG_OVERVIEW!$K:$K,$A2,PIG_OVERVIEW!$G:$G,""))
Litter_Status	=IF($A2="","",IF($P2<>"","Weaned",IF($S2=0,"Pending Setup","Active")))
Needs_Attention	=IF($A2="","",IF(OR($S2<>$H2,AND($H2<>"",$I2="",TODAY()-$B2>2),AND($S2>0,$V2=0,TODAY()-$B2>14)),"Yes",""))
Litter_Notes	=IF($A2="","",LITTERS!R2)
Created_At =IF($A2="","",LITTERS!S2)