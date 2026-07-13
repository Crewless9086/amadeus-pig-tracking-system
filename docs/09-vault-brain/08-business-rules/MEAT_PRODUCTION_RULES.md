# Meat Production Rules

## Source Of Truth

Supabase meat processing batches are the source of truth for slaughter-to-packed production evidence. Sales transactions remain the source of truth for actual customer sales and revenue.

## Required Boundaries

- Internal production is not a sale.
- Internal-use and pilot batches record zero revenue.
- Never infer packed weight from carcass weight.
- Never infer carcass weight from live weight when an actual measurement is expected.
- Record whether the head is included with carcass weight.
- Record actual provider costs; unknown cost is pending, not zero.
- Each cut/output weight must identify whether it counts toward packed yield.
- Waste, bones, fat, head, offal, and other outputs must remain distinguishable.
- Stage events are append-only evidence.
- Pig lifecycle writes require explicit owner/operator authority and must use canonical pig identity.
- A batch does not reserve stock, create an order, create a quote, confirm payment, send a customer message, or publish content.

## Learning Rule

Completed owner-verified batches may improve pricing assumptions, expected yield ranges, cut-set design, operating capacity, and SAM Meat context. One pilot is evidence, not a universal rule. Price-book or autonomy changes remain separately reviewed.

## First Evidence Batch

`MEAT-PILOT-2026-001` is the first internal production pilot. Known evidence is 63.0 kg live, 46.8 kg head-on carcass, R250 abattoir cost, Bartelsfontein slaughter on 2026-07-08, and butcher cutting beginning 2026-07-13. Remaining costs and cut outputs are pending.
