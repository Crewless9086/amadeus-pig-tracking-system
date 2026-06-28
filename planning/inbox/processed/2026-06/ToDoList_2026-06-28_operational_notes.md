# ToDoList 2026-06-28 Operational Notes

Status: processed into `docs/06-operations/OPERATIONAL_FIXES_MASTER_PLAN.md` during OP-1.

Raw owner notes copied from `planning/ToDoList.md`:

## MEAT LEADS

- Explain how leads work. The owner saw three chats, Sinethemba, Pappa G, and Thando, where short one-word messages appeared to become meat leads. This feels too broad and needs investigation before changing the lead creation rules.

## PIG TRACKER IMPROVEMENTS

- Bulk weight add is not reliably adding all weights or movements. The owner saw a run on the 15th where only 60 entries were added when 71 were expected. Investigate whether this is Google Sheets timeout behavior, whether Supabase should become the rail for this workflow, and how to provide logs/trails.
- Meat planning has meat window and abattoir window settings on `/meat-planning`. Owner wants to understand how to edit them and whether meat window should be 60-80kg with abattoir window at 80kg+.
- Pig allocation at `/pig-allocation` shows recommendations but no obvious review/action workflow for assigning purpose. Plan how the owner should inspect and assign a pig purpose.
- Beacon page `/sales/beacon-media` is squeezed into the side and confusing. Owner wants a clearer, full-width Beacon UI.
- Pig detail page `/pig/PIG-2026-92F3` is also narrow and should use the web dashboard width better.
- Sales Overview `/sales-dashboard` has an Available Stock table. Confirm whether it shows meat-ready stock and add planning if it does not.
- Owner wants a current stock value/estimated value view for livestock, meat, slaughter-to-butcher, slow growers, and sales availability planning.
- SAM Meat Sales Command Room `/sales/meat-leads` shows Pilot Control Room readiness as `--%` with `Pilot readiness unavailable: Request failed: 500`. Investigate.
- SAM Meat Sales Command Room logout currently redirects to sign-in. Owner asks whether logout can redirect to the dashboard instead.
