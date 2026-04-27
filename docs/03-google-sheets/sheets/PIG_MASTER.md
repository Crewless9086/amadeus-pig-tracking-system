# PIG_MASTER.md

## Role

Master/source-of-truth sheet for pig records.

## Write Ownership

Backend-approved logic may write operational updates. Formula-driven views should read from this sheet.

## Columns

To be migrated from the live Google Sheet and `docs/03-google-sheets/SHEET_SCHEMA.md`.
Pig_ID	Tag_Number	Pig_Name	Status	On_Farm	Animal_Type	Sex	Date_Of_Birth	Birth_Month	Birth_Year	Breed_Type	Colour_Markings	Litter_ID	Litter_Size_Born	Litter_Size_Weaned	Mother_Pig_ID	Father_Pig_ID	Mother_Tag_Number	Father_Tag_Number	Maternal_Line	Paternal_Line	Purpose	Current_Stage	Current_Pen_ID	Source	Acquisition_Date	Birth_Weight_Kg	Wean_Date	Wean_Weight_Kg	Exit_Date	Exit_Reason	Exit_Order_ID	Carcass_Weight_Kg	General_Notes	Created_At	Updated_At

## Notes

Track the rule that newborn litter-generated pigs should start with `Purpose = Unknown` until purpose is decided.
"Breed_Type" we can reduce these drops downs to "Large White", "Mix Large White" becuase we do not have the other breeds. IF we could have a page that controls the dropdow values this would be ideal. I have a sheet called "DROPDOWN_LIST" if this is any help. I want to be able to managed everything via the Web Application not to go between all the platforms. 