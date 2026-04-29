# Business Rules

## Purpose

Defines business rules that protect Google Sheets data integrity and keep backend, n8n, AI agents, and the web app aligned.

## Source-Of-Truth Rules

- Master and log sheets are the source of operational truth.
- Formula sheets are calculated views and must not be treated as write targets.
- If a formula sheet is wrong, fix the source data or formula, not the displayed output.

## Sales Rules

- A pig must not be offered for sale unless the sheet logic marks it as available for sale.
- `SALES_AVAILABILITY` is the main sales gate for sellable animals.
- `SALES_PRICING` is the pricing source. AI and n8n must not invent prices.
- Newborn or `Purpose = Unknown` animals may be visible for information but must not be treated as available for sale.
- Collection-only policy remains active unless explicitly changed in project docs.

## Order Rules

- n8n should request order actions through backend endpoints.
- Backend logic owns draft creation, order updates, order line creation, reservation, release, approval, rejection, cancellation, and completion.
- Do not create duplicate drafts for the same customer when an active draft should be updated.
- Reserved pigs must be released when the approved cancellation/rejection logic requires it.

## Pricing And VAT Rules

- `SALES_PRICING` stores prices **ex-VAT**. All `ORDER_LINES.Unit_Price` values are also ex-VAT.
- `Cash` orders: customer pays the listed ex-VAT price. No VAT is added.
- `EFT` orders: customer pays the listed ex-VAT price **plus 15% VAT** (South African standard rate).
- Quote and invoice documents must apply VAT based on the `PaymentMethod` stored on `ORDER_MASTER` at the time of document generation.
- Backend is the only system that may calculate totals and VAT. Sam and n8n must never invent or calculate pricing.
- `PaymentMethod` must be one of `Cash` or `EFT`. No other values are valid.
- `PaymentMethod` must be captured and stored on `ORDER_MASTER` before `send_for_approval` is called. Backend rejects approval requests without a payment method.
- `PaymentMethod` is locked once `Order_Status` reaches `Pending_Approval` or later. Backend must reject `PaymentMethod` update attempts on orders beyond `Draft`. Admin override is a separate future capability and must not be assumed.
- Quote documents lock and store the VAT rate at the time of quote generation. Invoice documents must match the VAT rate from the corresponding quote, not recalculate it.

## AI And n8n Rules

- AI may explain stock and prices only from documented sheet outputs.
- AI must not promise reservation, availability, or pricing until the backing sheet/backend logic supports it.
- n8n must not directly write operational Google Sheets.
- Field ownership rules in `docs/04-n8n/DATA_FLOW.md` must align with these sheet rules.

## Backend Rules

- Backend writes must target master, log, register, pricing, or user/admin sheets only.
- Backend may read formula sheets for display, availability, matching, and reporting.
- Backend must validate order state and availability before changing reservation state.

## Documentation Rules

- Every sheet must have a matching file under `sheets/`.
- Any column, formula, ownership, or pricing change must update this folder.
- Add a `SHEET_CHANGELOG.md` entry for approved sheet changes.
