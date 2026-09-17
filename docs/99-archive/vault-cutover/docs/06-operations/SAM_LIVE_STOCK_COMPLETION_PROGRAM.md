# SAM Live Stock Completion Program

## Outcome

For a normal livestock enquiry, SAM must understand the customer, use verified farm facts, choose the next sales action, prepare the order/quote/document work, draft a natural reply in the customer's language, and ask the owner for one decision. The owner handles exceptions instead of manually performing the sale.

## Authority

- Customer autoreply remains off until measured graduation criteria pass.
- Reservations, payment confirmation, stock movement, final order commitment, exact-location sharing, and customer document sends remain owner-gated.
- Stock, price, order, and document facts come from deterministic services. The language model may express facts but may not create them.

## Workstreams

1. Durable conversation state: goal, stage, language, known facts, asked fields, open order, next action, and history.
2. Input understanding: English, Afrikaans, mixed language, slang, emoji, voice-note transcripts, and conservative image classification.
3. Planning: one next-best action chosen before drafting.
4. Human reply generation: action-conditioned LLM plus a fact-aware deterministic fallback.
5. Transaction preparation: stock mix, relationship check, order, quote, loading sheet, movement documents, and approved attachments.
6. Owner control: one clear Telegram decision with current-state revalidation before execution.
7. Learning: capture SAM draft, owner reply, classification, situation, language, stage, outcome, and sale value.
8. Evaluation: historical replay suite and production scorecard.
9. Graduation: authority expands only by reply class after evidence thresholds pass.

## Required Evaluation Thresholds

| Measure | Gate |
|---|---:|
| Stock factual accuracy | 100% |
| Price factual accuracy | 100% |
| Invented commitments | 0 |
| Correct language | at least 95% |
| Correct next action | at least 95% |
| Relevant answer | at least 95% |
| Human voice | at least 90% |
| Owner accepts unchanged | at least 80% |
| Owner accepts unchanged or with minor edit | at least 95% |
| Wrong customer sends | 0 |
| Duplicate order/reservation | 0 |

## Graduation

- `shadow`: draft and score only.
- `owner_review`: every reply/action requires owner approval.
- `narrow_auto_send_candidate`: only a proven reply class with at least 20 consecutive safe accepted drafts may qualify.
- `narrow_auto_send`: requires explicit owner configuration after evaluation passes.
- `managed_sales_agent`: future state; exceptions, negotiation, genetics, stale stock, payment, complaints, large orders, and delivery exceptions remain owner-gated.

No test or model self-report may declare production readiness. Production evidence is required for the final 98% confidence claim.
