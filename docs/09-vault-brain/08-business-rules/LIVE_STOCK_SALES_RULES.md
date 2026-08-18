# Live Stock Sales Rules

Status: Current authority for SAM Live Stock Sales.

## Non-Negotiables

- Claim each exact customer reply once before attempting delivery.
- Never retry a failed or ambiguous outcome automatically.
- Quarantine only the affected conversation and send when its provider outcome
  is failed or ambiguous; continue unrelated exact Level 1 bindings.
- Stop the full cohort only for a systemic provider outage, corrupted claim
  rail, cross-binding identity/chronology collision, or authority breach.
- Count a delivered customer only after provider delivered/read evidence.

- Current stock truth must come from app/Supabase-backed backend reads.
- Legacy n8n and Google Sheet files are reference history only.
- SAM may conduct ordinary general conversation before lane classification.
  It must classify and graduate to `live_stock_sales` before making live-stock
  claims, calling live-stock tools, preparing an order, or entering a
  reservation path.
- Meat sales and live-stock sales must stay separate.
- No stock may be invented.
- SAM may auto-create a draft order only after the live-stock lane is confirmed, required facts are present, backend availability can fully satisfy the request, and active pricing is resolved.
- No customer may be told an animal is held unless backend reservation succeeds.
- No payment may be confirmed from POP alone.
- Breeding/replacement animals are not part of the normal live-stock sale lane.
- Only pigs with purpose `Sale` and source-truth sale availability may be sold through SAM Live Stock.
- No sold, exited, reserved, terminal, off-farm, health/movement-held, or
  source-conflicted animal may be offered. A food-chain medicine withdrawal is
  disclosed and blocks slaughter/food-chain entry for its governed period; it
  does not by itself prove or prohibit live transfer.
- The farm's exact live location must not be shared. Live-stock handover is arranged in Riversdale or Albertinia after the order path is confirmed.
- SAM must not debate or prove the farm's legitimacy to rude, aggressive, or already-decided scam accusations. It should close politely, log/escalate, and stop replying unless the owner reopens.
- SAM must not negotiate pricing or use cheap/budget/discount language unless the owner creates a specific approved pricing rule.
- SAM must not keep a conversation alive just to have the last word. Polite acknowledgement endings may be left unanswered.
- Persisted `Any`, `Unknown`, blank, defaulted, or inferred qualification
  values do not prove a customer preference. Only authoritative customer
  chronology may establish an explicit `either`/no-preference answer.
- Ask only missing facts. If size and sex are both missing, explain the
  customer-facing weight choices and ask both together; do not expose
  unexplained internal category names.
- Missing or stale availability/pricing blocks only those claims. A useful
  claim-free clarification remains eligible under the ordinary Level 1 rail.
- Intake/category defaults must never manufacture weight, sex, or handover
  preferences.
- A customer display name is presentation-only. Safe Unicode, punctuation,
  spacing and emoji may be normalized for a greeting; it never replaces or
  modifies the exact numeric/provider identity binding. Controls, markup,
  unreasonable length and disguised commercial claims fail closed.
- Always-on Livestock Level 1 authority comes only from the latest current
  append-only isolated control event and the exact current inbound evidence.
  Missing storage, a disabled/killed/expired state, a pre-cutoff historical
  event not explicitly carried, or any identity mismatch authorizes no send.
- Always-on activation never grants Meat, retry, quote, negotiation, delivery
  promise, reservation, allocation, order, payment, ownership, animal, stock
  or farm authority.

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

Live-transfer eligibility keeps separate attributable axes for transport
fitness, quarantine, notifiable/infectious disease, veterinary movement stop,
serious health/welfare state, treatment-evidence completeness, purpose,
active/on-farm state and order eligibility. Unknown is not clearance. Treatment
disclosure and acknowledgement prove receipt only; they never certify movement,
health or veterinary clearance. HERDMASTER owns this livestock projection;
SAM/order/document paths consume it without recalculating safety.

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

## Delivery Fee Policy

- Live-stock sales are collection-first. SAM must not openly offer delivery.
- Only when the customer asks about delivery, transport, or drop-off may SAM prepare a non-binding option for owner review.
- The default estimate is R20.00 per one-way kilometre to the drop-off location. This one-way measure recovers the farm round trip and must not be doubled again.
- Every estimate records destination, one-way kilometres, distance source, rate source, eligibility/status, and owner override amount/rate, reason, source, and approval.
- Missing kilometres or distance source produces an incomplete status, never a zero fee.
- Estimates do not authorize customer/quote send, reservation, payment, order, stock, or farm lifecycle writes. Owner review remains mandatory.

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

- `docs/09-vault-brain/04-workflows/SAM_GENERAL_CONVERSATION.md`
- `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`
- `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`
- `docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md`
- `docs/09-vault-brain/08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md`
- `docs/03-google-sheets/sheets/SALES_PRICING.md`
