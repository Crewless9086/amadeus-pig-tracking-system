# ROOTLINE Operating Knowledge Policy Review

Status: reviewed candidate only. Migration unapplied. No production proposal,
review or activation exists.

## Decision

ROOTLINE requires a small additive schema. Existing structures are not suitable
as canonical policy authority:

- Beacon campaign-calendar rule versions are Beacon-specific and use a local
  SQLite lifecycle rather than the protected production PostgreSQL owner rail.
- CHARLIE improvement proposals are mission artifacts. They do not provide the
  exact immutable ROOTLINE proposal, owner-review, advice-activation,
  effective-time and replay contract required here.
- The irrigation command ledger stores plan-only command evidence, not
  Operating Knowledge policy.
- The superseded daily-plan migration must not be reused or applied.

## Lifecycle

Every policy snapshot has one stable identity,
`ROOTLINE-OPERATING-KNOWLEDGE`, and an immutable monotonically increasing
version.

1. `proposed`: an owner-admin session records an exact validated snapshot,
   proposal evidence, actor, timestamp, idempotency identity and SHA-256.
2. `owner_reviewed`: a separate append-only event binds the exact latest
   proposal version, owner actor and review evidence. Review does not activate.
3. `active_for_advice`: a second explicit owner-admin event binds the same
   reviewed version, activation evidence and timezone-qualified effective
   time. Only this state can be read as current advice policy.

A later proposal does not replace the currently active version. It must pass
review and activation independently. Once a newer proposal exists, an older
proposal is stale and cannot be reviewed or activated. Replays create nothing;
conflicting reuse of an idempotency identity fails closed. Concurrent proposal
or transition attempts serialize on the stable policy identity.

The version and event tables reject UPDATE and DELETE. Browser roles have no
direct table, sequence or function access. The application service role may
read and invoke only the reviewed append functions.

The shared operations dashboard remains GET-only. It shows only an active
policy summary and links to a separate strictly owner-authenticated policy
page. That page shows lifecycle-appropriate actions only: the latest proposed
version may be reviewed, the latest reviewed version may be explicitly
activated, and active or stale versions are read-only.

## Policy fields

The owner surface explains the safe initial recommendation and consequence for:

- summer/winter boundary dates;
- exact Africa/Johannesburg daylight window per zone;
- minimum useful and maximum continuous valve-open minutes per zone;
- forecast-rain amount in mm, probability percentage and horizon in hours;
- temperature limits in degrees Celsius;
- ordered low/medium/high crop-need bands for B12345 lucerne and C12345
  vegetables;
- physically observed controller power-loss state;
- bounded residual-drainage time and classification.

Every field accepts deliberate `Unknown`. Units, ranges, exact zone identity,
non-cross-midnight windows and internally conflicting values are validated.
Unknown values remain visible and continue suppressing affected Daily Advisor
eligibility or runtime conclusions.

## Advice preview

Preview reports which policy blockers the proposed snapshot would resolve and
which remain Unknown. It never activates the proposal and never emits runtime,
a daily plan or a command. Current weather, forecast and other evidence must
still pass the Daily Advisor's independent evidence gates after future policy
activation.

The supervised C12345 30-second identity canary is not a runtime-policy source.
It is not successful routine irrigation and provides no measured-water value.

## Zero-authority boundary

The candidate has no irrigation transport or hardware consumer. All stored
versions and events database-constrain the following to false:

- plan generation and command creation;
- schedule mutation and workflow activation;
- IFTTT or n8n calls;
- automatic retry and hardware control;
- telemetry/farm-data writes outside the dedicated append-only policy ledger.

This PR does not apply the migration, create a production proposal, review or
activation, generate a production plan or command, change configuration, call
IFTTT/n8n, or operate irrigation hardware.
