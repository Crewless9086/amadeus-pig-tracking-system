# Meat Production Batch Workflow

## Purpose

The meat production rail traces a pig from farm departure through legal slaughter, butchery, packed outputs, costs, and final disposition.

It is separate from customer sales. Internal pilots and retained farm meat must not create revenue or distort sales reporting.

## Canonical Records

- `meat_processing_batches`: batch identity, kind, status, providers, dates, disposition.
- `meat_processing_batch_pigs`: canonical pig links and verified live/carcass weights.
- `meat_processing_batch_events`: append-only stage evidence.
- `meat_processing_batch_costs`: actual slaughter, transport, butcher, packaging, storage, labour, and other costs.
- `meat_processing_batch_outputs`: each cut/output, pack count, weight, yield inclusion, and disposition.

The owner workspace is `/sales/meat-production`. Backend routes are owner-session guarded under `/api/sales/meat-production/batches`.

## Stage Flow

1. Planned
2. Selected
3. Sent to abattoir
4. Carcass received
5. At butcher
6. Cutting
7. Packed
8. Completed

Events preserve what happened and when. The batch status is the current operational stage.

## Metrics

- Dressing yield = carcass weight / live weight.
- Packed yield from live = included packed output / live weight.
- Packed yield from carcass = included packed output / carcass weight.
- Cost per carcass kg = recorded cost / carcass weight.
- Cost per packed kg = recorded cost / included packed output.

Head-on carcass yield must be labelled as head included. Packed yield must not be inferred before the butcher outputs are weighed.

## Internal Pilot Rule

An `Internal_Pilot` with `Internal_Use` disposition records `R0.00` revenue. Its margin display is negative recorded cost until a separate scenario calculator compares possible market prices. It does not create a `sales_transactions` row.

## First Live Batch

`MEAT-PILOT-2026-001` is the first production evidence batch:

- canonical pig: `PIG-2026-EFB3`, tag `001`;
- live weight: `63.0 kg` on 2026-07-08;
- abattoir: Bartelsfontein;
- slaughter date: 2026-07-08;
- carcass weight: `46.8 kg`, head included;
- abattoir cost: `R250.00`;
- delivered to butcher / cutting date: 2026-07-13;
- intended disposition: internal use;
- butcher identity, butcher cost, transport cost, packaging cost, and cut outputs remain pending.

The initial head-on dressing yield is `74.3%`. This is not final packed yield.

## Agent Use

- Butcher reads batches, stages, costs, outputs, and yield evidence to identify missing production facts and recommend process improvements.
- Ledger uses completed verified batch evidence for break-even and margin scenarios.
- Herdmaster uses the canonical pig/lifecycle link for historical outcome analysis.
- SAM Meat may use owner-approved, completed yield/cost evidence through backend context. SAM must not invent cut availability or promote pilot results into live prices.
- Beacon may use only owner-approved customer-safe claims. Internal costs and operational exceptions are not public copy by default.

No agent may create revenue, confirm customer fulfilment, change prices, or complete a pig lifecycle action from production evidence alone.
