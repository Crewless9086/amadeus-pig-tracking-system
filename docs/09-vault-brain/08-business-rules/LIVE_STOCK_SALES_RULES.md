# Live Stock Sales Rules

Status: Stage 1 authority. These rules block unsafe behavior until backend runtime and owner gates are built.

## Non-Negotiables

- Current stock truth must come from app/Supabase-backed backend reads.
- Legacy n8n and Google Sheet files are reference history only.
- SAM must classify the sales lane before any draft reply, order, or reservation path.
- Meat sales and live-stock sales must stay separate.
- No stock may be invented.
- No animal may be reserved automatically in the first version.
- No customer may be told an animal is held unless backend reservation succeeds.
- No payment may be confirmed from POP alone.
- No breeding-quality animals may be sold without owner approval.
- No sold, exited, reserved, terminal, off-farm, withdrawal-blocked, or source-conflicted animal may be offered.

## Product Categories

Live-stock requests may refer to:

- piglets;
- weaners;
- growers;
- finishers;
- ready-for-slaughter live pigs;
- gilts;
- boars;
- sows;
- breeding animals.

Breeding animals are high-risk and require owner approval.

## Pricing

Initial price-band references exist in `docs/03-google-sheets/sheets/SALES_PRICING.md`, but owner confirmation is required before live launch.

SAM must not present old price-band values as final current pricing until the active backend price source is approved.

## Availability Matching

Matching priority:

1. exact category/weight/sex request;
2. same category with acceptable sex flexibility;
3. adjacent weight band as an option;
4. owner handoff when stock is close but risky;
5. no-stock response when availability cannot support the request.

SAM may offer adjacent stock only as an option, not as a confirmed substitute.

## Draft Order Gate

Draft order creation is a future stage and must require:

- confirmed live-stock lane;
- customer identity;
- quantity;
- category/weight band;
- sex preference or no preference;
- timing;
- location/transport expectation;
- backend availability;
- active order conflict check.

Reservation and quote/send remain owner-gated.

## Source References

- `planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md`
- `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`
- `docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md`
- `docs/09-vault-brain/08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md`
- `docs/03-google-sheets/sheets/SALES_PRICING.md`
