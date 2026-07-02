# Business Map

## Current Operating System

The repo currently supports the Amadeus farm and sales operating system:

- farm records and pig/litter/weight operations;
- meat sales and Sam customer intake;
- Beacon marketing and media review;
- Oom Sakkie farm command room;
- CHARLIE mission control and local runner workflow;
- Supabase migration and backend-owned data rails;
- n8n workflows for Chatwoot, Telegram, alerts, weather, power, irrigation, and order tools.

## Top-Level Departments

| Department | Commander | Purpose | Current state |
| --- | --- | --- | --- |
| Owner Command | CHARLIE | Mission governance, review, build/release oversight | Active but still maturing |
| Farm Operations | Oom Sakkie | Farm command room, summaries, approvals, specialist routing | Active direction, UI exists |
| Meat Sales | SAM | Chatwoot/WhatsApp customer intake and sales conversation handling | Active money-first path |
| Marketing | Beacon | Campaign drafts, media library, approved posting gates | Partially active, controlled |
| Business/Money | Ledger | Pricing, margin, pipeline, opportunity advice | Advisory/planned |
| Herd/Pigs | Herdmaster | Pigs, litters, breeding, growth, purpose review | Active/planned with purpose review |
| Butchery/Meat Pipeline | Butcher | Carcass matching, meat pipeline, overbooking protection | Recommendation/gated |
| Root/Water/Telemetry | Rootline | Irrigation, water, infrastructure signals | Read-only/gated |
| Inventory/Cost | Quartermaster | Feed, supplies, expenses, stock tasks | Planned |
| Transport | FRED | Private transfers and future transport/logistics | Planned, not built |

## Money-First Sequence

The current money-first path is meat sales:

1. Chatwoot/SAM hygiene.
2. Stress-tested Sam conversation intake.
3. Beacon campaign draft and media review.
4. Conversation learning evidence.
5. Owner-approved publish packets.
6. Manual/controlled posting evidence.
7. Performance and boost recommendations.
8. Later controlled posting/spend automation.

Live pig sales, slaughter/abattoir sales, assisted slaughter, custom cuts, and private transfers are important future or parallel income paths, but the first proven agent-money pattern is meat sales.

## Farm Business Rules Captured

- One pig should have one operational truth.
- Purpose/allocation is dynamic and should change with weights, growth, litter quality, demand, and outlet timing.
- Fast growers from strong litters are reviewed first for breeding, then meat, then slaughter/abattoir fallback.
- Slow growers and underperformers should be considered for livestock sale to reduce feed cost.
- Meat candidates should be young and weight-dependent.
- Meat-window pigs that are not pre-sold in time should fall back to slaughter/abattoir.
- Unknown purpose is a data/classification problem, not a silent sale/meat/slaughter decision.

## Future Business Lanes

### Amadeus Private Transfers

FRED is the planned transport/private transfers commander. It is not built yet. No dispatch, quote, payment, customer send, driver assignment, or booking automation is approved.

Before FRED can operate, the Vault Brain needs:

- service definition;
- pricing model;
- vehicle/driver rules;
- booking workflow;
- customer communication rules;
- payment/deposit rules;
- cancellation/refund rules;
- safety and legal/insurance checks;
- source-of-truth data model.

### Beacon As Department

Beacon should become its own marketing department with sub-agents/modules:

- Strategy;
- Creative;
- Media Librarian;
- Scheduler;
- Performance Analyst.

Beacon remains gated by owner approval, approved media, spend caps, channel rules, and backend fulfilment readiness.

## Source References

- `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md`
- `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md`
- `docs/05-ai/AGENT_ROLES.md`
- `docs/05-ai/agents/beacon/BEACON_SCOPE.md`
- `docs/00-start-here/README.md`
- `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md`
