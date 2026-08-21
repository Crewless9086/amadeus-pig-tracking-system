# Herdmaster Purpose Review Workflow

Purpose review starts after weaning and post-wean weight timing rules.

The allocation-readiness backend is the sole eligibility and recommendation
path. Day 13 remains quiet. At day 14, an unknown-purpose litter/cohort without
a qualifying post-wean weight produces one physical grouped-weighing task; with
qualifying evidence it produces one grouped protected purpose decision. Both
phases retain one stable `herdmaster:purpose-review:<cohort>` work identity in
the shared Oom Sakkie attention lifecycle. A resolved purpose removes the case;
deferment retains reassessment ownership; an unchanged material digest does not
create another Application, Brief or Telegram item.

Herdmaster prepares recommendations using wean weight, latest weight, ADG, litter quality, sow/boar, sex, pen, stored purpose, and missing data.

Owner approves, overrides, defers, or requests recheck. A correction write requires a persisted owner-approved correction batch, execution-time canonical fresh-weight validation, and an atomic operational audit event for every corrected pig. The legacy apply route is preview-only and correction execution has no Google Sheets fallback.

Pig Allocation is the unified owner workspace. Purpose Review is its filtered
decision mode, and `/purpose-review` remains a compatibility deep link into that
mode. Purpose, allocation, reservation, sale and customer availability remain
distinct; approving purpose performs none of the other actions.

Purpose review never silently reclassifies animals to satisfy an order or make a
selector appear fillable. HERDMASTER prepares one grouped evidence preview with
exact, near, projected and unavailable candidates plus the purpose decisions
needed. Customer request, recommendation, reservation and final allocation stay
separate states.

Medical evidence is append-only. Possible duplicate treatment rows remain
distinct until an attributable owner or veterinary fact resolves them through
the governed correction rail; HERDMASTER never chooses which event to retain.
Food-chain withdrawal and live-transfer eligibility remain separate as defined
in `LIVE_STOCK_SALES_RULES.md`.

Focused authority: `docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md` and `docs/09-vault-brain/06-data/FARM_DATA_MODEL.md`.
