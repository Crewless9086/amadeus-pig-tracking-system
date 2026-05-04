This file is the scratch list for things noticed during build work. Once an item is added to `docs/00-start-here/NEXT_STEPS.md`, it should be removed from the active scratch list below.

## Moved Into `NEXT_STEPS.md`

- Reject order must release reserved lines: completed and live-verified under Phase 1.1.
- Customer cancel through Sam / `1.2`: completed and live-verified under Phase 1.2.
- First-turn draft creation must sync order lines immediately: completed and live-verified under Phase 1.2c.
- Web app background progress/status messaging: added under Phase 6.
- Reserve Order Lines failures on larger orders: added under Phase 1.6.
- New litter `Purpose = Unknown` and weaning reminder: added under Phase 9.1.
- Pig dropdown tag/pen display and three-digit tag formatting: added under Phase 9.2.
- Weight form current pen helper text: added under Phase 9.3.
- Weight report generation: added under Phase 9.4.
- Dashboard `SOLD THIS MONTH` mismatch: added under Phase 9.5.
- Customer-safe n8n error reply path for backend `400` guard failures: added under Phase 1.4 / Phase 1.5.
- Approval auto-reservation decision: added under Phase 1.5 and Phase 1.8.
- Customer notification flow after human approval/rejection: added under Phase 1.5 and Phase 1.9.
- Printable weekly weight sheet / farm printouts page: added under Phase 9.6.
- Farm operating system integration for Sam, Oom Sakkie, web app, backend, weather, solar, workflows, and sheets: added under Phase 10.
- Phase 1.4 route/reply preflight review after send-for-approval fixes: completed and documented under Phase 1.4.
- Web app order detail: approve/reject/reserve parity with backend/workflows: added under Phase 6.
- Phase 1.5 lifecycle guards — Complete And Live-Verified: documented under Phase 1 §1.5.

## Active Scratch Notes

- Review folder/code structure after order stabilization, especially where large files should be split into clearer modules. Documentation structure is currently stable; implementation structure can be reviewed as a separate refactor pass.
- Confirm `ORDER_LINES.Unit_Price` is written at line creation time — required gate before Phase 2 quote generation can be built.