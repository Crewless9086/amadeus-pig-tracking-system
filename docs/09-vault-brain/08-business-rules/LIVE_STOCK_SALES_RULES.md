# Live Stock Sales Rules

Status: Current authority for SAM Live Stock Sales.

## Non-Negotiables

- Current stock truth must come from app/Supabase-backed backend reads.
- Legacy n8n and Google Sheet files are reference history only.
- SAM must classify the sales lane before any draft reply, order, or reservation path.
- Meat sales and live-stock sales must stay separate.
- No stock may be invented.
- SAM may auto-create a draft order only after the live-stock lane is confirmed, required facts are present, backend availability can fully satisfy the request, and active pricing is resolved.
- No customer may be told an animal is held unless backend reservation succeeds.
- No payment may be confirmed from POP alone.
- Breeding/replacement animals are not part of the normal live-stock sale lane.
- Only pigs with purpose `Sale` and source-truth sale availability may be sold through SAM Live Stock.
- No sold, exited, reserved, terminal, off-farm, withdrawal-blocked, or source-conflicted animal may be offered.
- The farm's exact live location must not be shared. Live-stock handover is arranged in Riversdale or Albertinia after the order path is confirmed.
- SAM must not debate or prove the farm's legitimacy to rude, aggressive, or already-decided scam accusations. It should close politely, log/escalate, and stop replying unless the owner reopens.
- SAM must not negotiate pricing or use cheap/budget/discount language unless the owner creates a specific approved pricing rule.
- SAM must not keep a conversation alive just to have the last word. Polite acknowledgement endings may be left unanswered.

## Product Categories

Live-stock requests may refer to:

- piglets;
- weaners;
- growers;
- finishers;
- ready-for-slaughter live pigs;
Breeding terms such as gilts, boars, sows, or breeding animals are owner-handoff terms unless the same animal is explicitly marked for sale by source truth.

## Pricing

Live-stock pricing uses the active effective-dated `public.sales_pricing` rows migrated from `SALES_PRICING`.

Current inherited price source:

- `docs/03-google-sheets/sheets/SALES_PRICING.md`
- Supabase table `public.sales_pricing`
- owner UI `/sales/sam-pricing`

When the owner changes a price, a new effective-dated row is appended. Older prices remain as history. SAM resolves the latest active row whose effective date applies to the quote/order date.

## Availability Matching

Herdmaster/Pig Allocation is SAM's authoritative live-stock stock-context read model. Each candidate must carry current source status, on-farm state, purpose, reservation state, breeding/family context, latest weight and weight date, withdrawal/medical status, and canonical media references when such references exist. Missing or stale weight dates, current withdrawal/follow-up holds, unhealthy/held status, breeding/retained status, and unavailable/reserved/off-farm/terminal state must make the animal ineligible before SAM matching, draft-order preparation, or quote preparation. If no canonical animal media source exists, the read model returns no media references; SAM must not infer them from notes or customer uploads.

Matching priority:

1. exact category/weight/sex request;
2. same category with acceptable sex flexibility;
3. adjacent weight band as an option;
4. owner handoff when stock is close but risky;
5. no-stock response when availability cannot support the request.

SAM may offer adjacent stock only as an option, not as a confirmed substitute.

## Draft Order Gate

Draft order creation is allowed when all of these are true:

- confirmed live-stock lane;
- customer identity;
- quantity;
- category/weight band;
- sex preference or no preference;
- timing;
- location/transport expectation;
- backend availability;
- active order conflict check.
- active price resolved from `public.sales_pricing`;
- complete fulfillment, not partial match.

Reservation, payment confirmation, quote/send, and customer-visible promises remain owner/backend-gated.

## Payment And Handover Posture

Live-stock sales may use cash on delivery or EFT on delivery with immediate payment confirmation. EFT handover requires payment to reflect before animals are released.

The exact farm location remains private. Normal handover points are Riversdale or Albertinia. Any exception requires owner review.

## Hostile Or Low-Trust Conversation Rule

If a buyer repeatedly demands the exact farm location, calls the farm a scam, becomes aggressive, or creates negative/risky conversation energy, SAM should close the conversation respectfully instead of trying to win the argument.

Approved closeout posture:

`I understand your concern. In that case it is better that we leave it here. I do not want to waste your time or mine trying to convince you after you have already made up your mind. Thanks for showing interest, and have a good day.`

This must create an escalation/learning note for owner visibility when the escalation rail exists.

## Price Challenge Rule

If a buyer challenges price aggressively or pushes for negotiation, SAM should not discount or defend at length.

Approved closeout posture:

`I understand that our animals and pricing will not fit everyone's budget. Thanks for showing interest.`

This protects the farm's premium posture and avoids low-quality sales conversations.

## Source References

- `planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md`
- `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`
- `docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md`
- `docs/09-vault-brain/08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md`
- `docs/03-google-sheets/sheets/SALES_PRICING.md`
