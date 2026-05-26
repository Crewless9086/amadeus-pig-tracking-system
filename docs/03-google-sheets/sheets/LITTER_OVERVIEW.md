# LITTER_OVERVIEW.md

## Role

Formula-driven litter overview view for display and lookup.

## Write Ownership

Read only. Operational changes belong in `LITTERS`.

## Columns
Litter_ID	Farrowing_Date	Sow_Pig_ID	Boar_Pig_ID	Sow_Tag_Number	Boar_Tag_Number	Current_Pen_ID	Total_Born	Born_Alive	Stillborn_Count	Mummified_Count	Male_Count	Female_Count	Fostered_In_Count	Fostered_Out_Count	Weaned_Count	Wean_Date	Average_Wean_Weight_Kg	Pig_Master_Row_Count	Active_Pig_Count	On_Farm_Pig_Count	Tagged_Pig_Count	Untagged_Pig_Count	Exited_Pig_Count	Average_Current_Weight_Kg	Youngest_Age_Days	Oldest_Age_Days	Sex_Assigned_Count	Sex_Unassigned_Count	Litter_Status	Needs_Attention	Litter_Notes	Created_At	Attention_Reason

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
Needs_Attention	=IF($A2="","",IF(OR(AND($I2<>"",$S2<>$I2),AND($H2<>"",$I2="",TODAY()-$B2>2),AND($S2>0,$V2=0,TODAY()-$B2>14)),"Yes",""))
Litter_Notes	=IF($A2="","",LITTERS!R2)
Created_At =IF($A2="","",LITTERS!S2)
Attention_Reason	=IF($A2="","",IF($AE2<>"Yes","",IF(AND($I2<>"",$S2<>$I2),"Linked pig records do not match born alive count",IF(AND($H2<>"",$I2="",TODAY()-$B2>2),"Born alive count missing",IF(AND($S2>0,$V2=0,TODAY()-$B2>14),"Piglets need tag numbers","Review litter")))))

## Formula Notes

`Needs_Attention` must compare `Pig_Master_Row_Count` to `Born_Alive`, not `Total_Born`.

Reason: stillborn and mummified piglets are counted in the litter totals, but they should not create live `PIG_MASTER` rows. Example: if 7 are born, 6 are born alive, and 1 is stillborn, the correct `PIG_MASTER` row count is 6.

When migrating this logic to Supabase, preserve this distinction:

- `total_born` = all piglets delivered.
- `born_alive` = piglets that should normally have individual pig records.
- `stillborn_count` and `mummified_count` = litter outcome metrics, not live pig records.
- attention should flag missing pig records only when live pig records do not match `born_alive`.

Piglets that die after live birth should normally have `PIG_MASTER` rows because they were part of the born-alive population. Their later death should be captured on the pig record with status/on-farm/exit date/exit reason, not by deleting the pig record from the litter history.

Suggested current sheet column placement:

- `AE` = `Needs_Attention`
- `AF` = `Litter_Notes`
- `AG` = `Created_At`
- `AH` = `Attention_Reason`

Add `Attention_Reason` at the end of the table rather than inserting it between existing columns. This avoids shifting existing formulas or references that may still expect `Litter_Notes` and `Created_At` in their current positions.
