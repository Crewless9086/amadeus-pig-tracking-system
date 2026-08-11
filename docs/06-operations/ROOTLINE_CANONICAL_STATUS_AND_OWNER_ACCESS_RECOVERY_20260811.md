# ROOTLINE Canonical Status and Owner Access Recovery

Status: owner-approved mission definition. ROOTLINE terminal owns implementation because it crosses scheduler, canonical irrigation state, execution, provider notification and safety boundaries.

## Proven current defect

The dashboard and `/irrigation` page read `/api/telemetry/irrigation/status`. Its service uses `IRRIGATION_STATUS_SOURCE=auto` by default:

1. read `irrigation_daily_plans`, plan items, state snapshots and execution events from Supabase;
2. if the requested date has no Supabase plan rows, fall back actively to Google Sheet `Amadeus_Irrigation_Logs`;
3. return those sheet rows as the dashboard plan.

On 11 August 2026 the public response came from `google_sheets`, was explicitly `read_only`, showed B and C planned for 60 minutes, zero completed minutes, no running zone, hardware control false and a disagreement between state-next C and computed-next B. This is live legacy fallback, not stale data copied into Supabase and not proof of canonical execution.

The detailed page also requests protected ROOTLINE endpoints. Without an owner session they return JSON `403`, while the page renders generic `Unavailable`. `/owner/login` and `/owner/status` exist but the farm navigation exposes neither session status nor a login control.

## Business outcome

The dashboard, irrigation page, scheduler, Telegram and hardware history must tell one canonical story from Supabase and provider-confirmed execution. Charl must be able to log in visibly, understand why watering is planned/held/running, see rainfall credit and fertilizer status, and distinguish a recommendation from an executed segment.

## Canonical irrigation status

- Identify the exact deployed ROOTLINE scheduler artifact, execution eligibility, claim and provider readback tables.
- Reconcile them with `irrigation_daily_plans`, plan items, `irrigation_state_snapshots` and execution-event tables expected by `irrigation_service.py`.
- Choose one canonical projection. Prefer adapting the status UI to the authoritative existing scheduler/execution records over copying legacy rows.
- Create no second plan ledger and manufacture no historical executions.
- Once parity is proven, lock production status to Supabase and remove ordinary Google Sheets fallback from owner-visible current status.
- Preserve an explicitly labelled legacy read-only audit route only if still operationally required.
- Never show a legacy `PLANNED` row as if autonomous execution is scheduled.

For each B/C zone expose:

- recommendation: Run, Hold, Needs Data or Not Due;
- planned duration and feasible execution window;
- effective rainfall credited and remaining supported water need;
- observed-weather evidence and timestamp;
- water/tank evidence and freshness;
- eligibility and exact blocker;
- scheduler ownership and next reassessment;
- claimed/running/completed/failed state;
- provider-confirmed ON/OFF and verified shutdown;
- notification delivery state.

## Owner access journey

- Keep `/owner/login`, `/owner/logout` and `/owner/status` as the existing authority rail.
- Add a visible navigation control on the shared farm navigation: `Log in` when no session exists, and `Owner access` or `Log out` when authenticated.
- Add a small JSON-safe owner-session status endpoint or equivalent server-rendered state; disclose role/status only, never token material.
- When protected irrigation fetches return `401/403`, show one clear login card linking to `/owner/login?next=/irrigation`.
- After successful login, return to the exact requested page and reload protected panels.
- Do not ask Charl to paste owner tokens into Telegram, terminal feedback, URLs or logs.
- Do not weaken protected endpoints merely to make the page load.

## Daily plan and notification reconciliation

- Determine whether today had a canonical plan, Hold or execution attempt.
- Reconcile daily-plan creation, material-change suppression, Start/Completed/Exception notifications and provider receipts.
- Deliver one concise morning plan when a new daily plan becomes current, then notify only meaningful changes and physical execution lifecycle events.
- Silence must be explainable by an unchanged/held decision with durable suppression evidence, not missing wiring.

## Fertilizer closure

- Reconcile deployed CH1 injection 120-second and CH2 mixer 300-second configuration.
- Verify authority flags and the unfinished supervised CH2 proof.
- Do not claim mixing operational until one real five-minute mixer cycle has provider-confirmed ON, native auto-OFF and physical owner observation.
- Enable mixing only after that proof.
- Keep injection disabled until a separately eligible real B/C segment proves preflow, two bounded 120-second pulses, spacing, clean-water flush, provider OFF and no watering interruption.
- Expose fertilizer batch, mixer and injection state on the irrigation page without treating either as a zone.

## Borehole boundary

- Do not combine borehole actuation into this recovery unless canonical irrigation/status and fertilizer commissioning are first released.
- Prepare the later source mission from exact SmartLife scene/event identities, physical plug identity, native safety settings, runtime limit, power-restoration state, tank-full stopping evidence and manual isolation.
- Borehole power depends on energy; gravity-fed B/C valves do not.

## Required verification

- Tests for Supabase-current, no-plan, Hold, planned, running, completed, provider ambiguity and legacy audit cases.
- Tests proving current UI never falls back silently to Sheets.
- Browser tests for logged-out login card, return-to-irrigation login, authenticated loading, expired session and logout.
- Tests for rainfall credit, execution blocker, fertilizer status and notification accounting.
- Independent water operations/CX and backend/security/authority review.
- Exact-head and exact-merge CI and exact deployment lineage.

## Completion proof

Completion requires a fresh real-world loop, not merely deployment:

1. owner opens the irrigation page logged out and sees the login action;
2. owner logs in and returns to the same page;
3. page loads one canonical Supabase ROOTLINE decision with rainfall and eligibility evidence;
4. the same decision is reflected in Telegram without duplication;
5. the next genuinely eligible B/C segment either executes with provider-confirmed Start/OFF/Completed proof or remains Hold for one precise truthful reason;
6. dashboard and detail page agree with execution history;
7. Google Sheets cannot silently supply current operational truth;
8. replay produces zero duplicate plans, notifications, commands or farm writes.

Fertilizer mixing and injection each remain separately incomplete until their physical proofs succeed.

## Expected business result

Charl sees one trustworthy ROOTLINE plan and execution state, can authenticate without hunting for a hidden URL, understands how rain changed irrigation need, and receives concise notifications that match actual valve behavior.
