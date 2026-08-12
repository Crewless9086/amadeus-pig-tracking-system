# Owner-Facing Application Performance Mission

Date approved: 2026-08-12  
Owner: Charl Nieuwendyk  
Mission owner: CHARLIE CORE  
Scope: read performance of the farm dashboard and ordinary owner-facing pages

## Owner Outcome

Charl can move between the dashboard, registers and detail pages without long unexplained waits. The interface shows useful content progressively, one slow specialist does not block unrelated panels, and a temporary upstream failure remains visible without turning the whole application into an empty or misleading screen.

This is not a cosmetic loading-spinner mission and it is not permission to weaken canonical truth, authentication, governance, replay protection or farm/hardware safety.

## Initial Evidence

The 2026-08-12 incident established that the web process can return `/health` 200 while owner-facing data routes fail. Missing production environment variables caused canonical database reads to become unavailable; several routes then entered an invalid Google Sheets fallback and returned 500, while telemetry routes returned 503. After configuration restoration, representative endpoints recovered.

The live dashboard starts independent weather, forecast, power, irrigation, herd, breeding, sales and order requests. Some client timeouts allow 30 to 45 seconds. The sales response observed during recovery was materially larger than ordinary summary payloads. These facts justify measurement; they do not yet prove which query or projection dominates normal latency.

## Non-Negotiable Boundaries

1. Supabase/PostgreSQL canonical read models remain authoritative for operational truth.
2. Google Sheets must not silently become the production read path for migrated canonical domains. A deliberately retained legacy dependency must be named, bounded and observable.
3. No cache may conceal a write, confirmation, payment, lifecycle, mating, exposure, irrigation or safety-state change.
4. Authentication and owner authorization must not be bypassed to improve timing.
5. No farm record, Telegram message, customer action, provider mutation or hardware command may be created as performance-test data.
6. Existing dirty worktrees, approved plans and unique branches must be preserved.
7. Server health must distinguish process availability from canonical data readiness.

## Performance Targets

Measure from a South African owner connection and separately at the Render service boundary. Record median and p95 where repeated samples are safe.

| Journey | Owner-facing target | Failure behavior |
|---|---:|---|
| Page shell and navigation | visible within 1 second after connection | shell still renders with explicit unavailable state |
| Ordinary register/summary data | useful first content within 2 seconds; p95 below 3 seconds | bounded error; no legacy timeout chain |
| Dashboard independent panels | each ordinary panel within 2 seconds; full useful dashboard within 3 seconds | slow panel cannot block successful panels |
| Detail pages | core identity/state within 2 seconds; secondary history progressive | details may load separately with source/time shown |
| Heavy reports/analysis | first result or progress within 3 seconds; completed response normally below 5 seconds | explicit long-running state or bounded failure |
| Navigation feedback | immediate, below 100 ms | visible loading state and preserved navigation context |

These are acceptance targets, not reasons to invent data or return incomplete records as complete.

## Mission Sequence

### 1. Establish a production latency baseline

- Inventory every API called by `/`, `/matings`, `/litters`, `/pigs`, pig/litter detail pages, bulk weights, print sheets and breeding attention.
- Record response status, server duration, payload size, database call count and fallback path without logging secrets or private payloads.
- Capture cold deployment, warm service and normal repeated-navigation results separately.
- Identify sequential calls, repeated reads and endpoints returning detail unused by the current screen.
- Produce a ranked latency budget rather than assuming Render size is the cause.

### 2. Correct observability and readiness

- Keep lightweight liveness separate from canonical-data readiness.
- Add safe structured timing for route stages and database projections.
- Make missing canonical configuration fail immediately with a clear typed status; do not wait for an unavailable Sheets credential.
- Surface data source, freshness and unavailable reason to the relevant panel without exposing infrastructure or credentials.

### 3. Repair canonical read paths

- Remove accidental Google Sheets fallback from migrated production domains.
- Inspect query plans for the slowest canonical endpoints and add only evidence-supported indexes.
- Replace repeated whole-domain scans with compact read models or bounded queries.
- Eliminate N+1 reads and duplicate reconciliation performed by several panels in one navigation.
- Keep exact source identities and correction semantics intact.

### 4. Reduce payload and computation

- Define compact list/summary contracts for dashboard and registers.
- Fetch full history, analytics or large evidence sets only when the owner opens the relevant detail.
- Paginate or bound large registers while preserving search and filter correctness.
- Precompute safe rollups for telemetry and expensive read-only summaries when supported by canonical events.

### 5. Add safe short-lived caching

- Cache only read-only projections with explicit keys, source revision/freshness and conservative expiry, normally 15 to 60 seconds.
- Invalidate or bypass caches after relevant confirmed writes.
- Never cache protected previews, confirmation decisions, active hardware state or other time-critical safety facts as if current.
- Permit stale-while-revalidate only where the UI labels the timestamp and stale data cannot authorize action.

### 6. Improve browser behavior

- Preserve independent dashboard loading so successful panels appear immediately.
- Deduplicate concurrent requests for the same resource during one page lifecycle.
- Reuse a recently fetched safe summary across navigation where freshness is explicit.
- Load secondary detail progressively and provide concise skeleton, empty, unavailable and retry states.
- Replace 30–45 second silent waits with endpoint-specific bounded deadlines and clear recovery behavior.

### 7. Prove the owner journey

- Verify desktop Chrome in normal mode and F11 where applicable.
- Exercise dashboard to register to detail and back, plus `/matings` and one heavy report.
- Prove no canonical counts, identities, permissions or protected actions changed.
- Simulate one unavailable telemetry specialist and one unavailable canonical dependency; unrelated panels must remain useful.
- Compare before/after median, p95, payload and query evidence.
- Complete only after Charl experiences the deployed journeys at the agreed speed and confirms they are practically usable.

## Required Deliverables

1. Endpoint and page dependency inventory.
2. Before/after production timing report with payload sizes and failure modes.
3. Ranked root-cause findings tied to evidence.
4. Reviewed source changes and migrations, if any.
5. Browser proof for progressive loading and navigation.
6. Canonical truth, authorization and replay regression proof.
7. Deployment lineage and owner-visible acceptance record.
8. Closeout that removes only clean, merged, non-unique mission worktrees and retains any dirty or unique evidence.

## Completion Definition

CI, a faster local preview, a Render deployment, caching, or one fast curl request is not Business completion. Completion requires fresh deployed owner journeys meeting the targets in ordinary use, with independent panels, honest failure states and unchanged canonical business truth.

## Improvement Challenge

Before implementing each optimization, the mission must ask:

- Is the work removing the true delay or hiding it?
- Can an existing canonical read model serve the result more simply?
- Is the page requesting information the owner cannot see or use?
- Will caching make a current decision appear safer or fresher than it is?
- Can one shared correction improve several pages without creating a second framework?
- What is the smallest reversible change that proves the expected owner benefit?

