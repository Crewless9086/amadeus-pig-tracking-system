This file is the scratch list for things noticed during build work. Once an item is added to `docs/00-start-here/NEXT_STEPS.md`, it should be removed from the active scratch list below.

## Moved Into `NEXT_STEPS.md`

- Reject order must release reserved lines: completed and live-verified under Phase 1.1.
- Customer cancel through Sam / `1.2`: completed and live-verified under Phase 1.2.
- First-turn draft creation must sync order lines immediately: completed and live-verified under Phase 1.2c.
- Web app background progress/status messaging: added under Phase 6.
- Reserve Order Lines failures on larger orders: added under Phase 1.6.
- New litter `Purpose = Unknown` and weaning reminder: added under Phase 8.1.
- Pig dropdown tag/pen display and three-digit tag formatting: added under Phase 8.2.
- Weight form current pen helper text: added under Phase 8.3.
- Weight report generation: added under Phase 8.4.
- Dashboard `SOLD THIS MONTH` mismatch: added under Phase 8.5.
- Customer-safe n8n error reply path for backend `400` guard failures: added under Phase 1.4 / Phase 1.5.
- Approval auto-reservation decision: added under Phase 1.5 and Phase 1.8.
- Customer notification flow after human approval/rejection: added under Phase 1.5 and Phase 1.9.

## Active Scratch Notes

- Review folder/code structure after order stabilization, especially where large files should be split into clearer modules. Documentation structure is currently stable; implementation structure can be reviewed as a separate refactor pass.
- Confirm `ORDER_LINES.Unit_Price` is written at line creation time — required gate before Phase 2 quote generation can be built.
- I need to design a page on the web app that will be used to assist us in printing data from the data. Such as when they weigh they like to print a hard copy and write on it then later they add it to the system. I want us to think and design a page that will allow for this. It needs to be flexible but also have like templates. So they look the same and it's not different everytime. So currently the one to focus on is that every monday we weight the animals still on the farm. The reason I print the full list of animal on the farm is that if they do weight the breeding couples or so they at least have them on the sheet and they don't have to guess. But generally we only need to weigh the once for sale or the once that we think of selling or growing out. But never the less I think we generate the template and then the user can select what he want ons the printable sheet. We can give options to break it down to camps, or split by purpose or select all or just be flexible. Please help me plan this so we can think of the best useful way to do this.
This is currently how I have the Weight-Printable sheet set up: Just so you can see what I mean. 
A1 - row we have the Total on the list and then a date line that is empty as they will write the date they weigh them.
A3 - we have the headers: Some of these headers are in Afrikaans so the workers can understand it better. But we do not need the any of the ID on the sheet I just had them becuase the formulas was carrying over the human data. It needs to be human readable and show the Tag Number, Current Pen, Previous Weight Date, Previous Weight, Nuwe Gewig, Kamp, Nuwe Kamp, Notas
Pig_ID - This is the ID to carry over the correct Pig Tag
Tag Number	- Just the tag number
Current_Pen_ID - THis ID is to populate the "Kamp" column
Vorige Gewig Datum - Good to no the previous weight date
Vorige Gewig - Good to know the previous weight
Nuwe Gewig - This is empty as this is the new weight
Kamp - This is the current Pen they are in according to the system
Nuwe Kamp - This is blank the new pen they might move to if any
Notas - THis is blank and notes get added here. 
I do have a sample if images or doc if you like to se it and understand better. 