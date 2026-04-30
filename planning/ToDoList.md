This file is the scratch list for things noticed during build work. Once an item is added to `docs/00-start-here/NEXT_STEPS.md`, it should be removed from the active scratch list below.

## Moved Into `NEXT_STEPS.md`

- Reject order must release reserved lines: completed and live-verified under Phase 1.1.
- Customer cancel through Sam / `1.2`: completed and live-verified under Phase 1.2.
- First-turn draft creation must sync order lines immediately: completed and live-verified under Phase 1.2c.
- Web app background progress/status messaging: added under Phase 4.
- Reserve Order Lines failures on larger orders: added under Phase 1.3.
- New litter `Purpose = Unknown` and weaning reminder: added under Phase 6.1.
- Pig dropdown tag/pen display and three-digit tag formatting: added under Phase 6.2.
- Weight form current pen helper text: added under Phase 6.3.
- Weight report generation: added under Phase 6.4.
- Dashboard `SOLD THIS MONTH` mismatch: added under Phase 6.5.

## Active Scratch Notes

- Review folder/code structure after order stabilization, especially where large files should be split into clearer modules. Documentation structure is currently stable; implementation structure can be reviewed as a separate refactor pass.
- Confirm `ORDER_LINES.Unit_Price` is written at line creation time — required gate before Phase 2 quote generation can be built.
- Add a customer-safe n8n error reply path for backend `400` guard failures. Example: when backend rejects a Payment_Method change because the order is beyond Draft, Sam must reply with a clear explanation instead of going silent.