# Night Handover - 2026-07-26

Status: owner-directed end-of-day operating record.

Recorded at: 2026-07-26 23:14 SAST.

Repository baseline used for this record:
`bc75a9b56a72e19c07a86aa6e2612c1f3f139e42`.

This record separates implemented code, deployed runtime, production
evidence, prepared work, and future authority. A successful test does not
silently grant an agent broader authority.

## Owner Direction

Charl directed that:

- all agents except CORE stop at a safe, recoverable boundary for the night;
- no unrecorded implementation, migration, customer action, public action,
  hardware action, or business mutation continue overnight;
- new capabilities, decisions, open work, and restart points be preserved in
  the Vault Brain;
- CORE may continue only inside its existing reviewed mission scope and safety
  boundaries;
- the Workforce page should become the canonical owner-facing view of each
  agent's operating status, authority, evidence, blockers, learning, graduation,
  and next action.

## Safe Overnight Boundary

Unless a later owner instruction explicitly supersedes this handover:

- SAM Live Stock: observe only. No further customer send, ownership change,
  template, Telegram action, order, reservation, price, stock, or business
  mutation.
- BEACON: recommendation and code-review work only. No Meta call, publication,
  retry, scheduling, messaging, boost, advertising, or spend.
- HERDMASTER: no migration application, Auction List Add/Remove, animal
  mutation, allocation, booking, reservation, sale, reminder, or customer
  action.
- ROOTLINE: no IFTTT/n8n request, ON/OFF event, irrigation command, scheduler,
  workflow change, production plan, or hardware action.
- all other business and farm agents: no new production execution without a
  fresh owner-authorized packet.
- CORE: may continue working on PR #517 only. It may review, correct, and test
  the bounded ownership-bootstrap candidate. It may not merge, deploy, start
  CORE processes, remove the stop marker, enable the watchdog, execute T0
  missions, or broaden scope without separate owner authority.

## SAM Live Stock

### Business outcome completed

SAM recovered four real unanswered WhatsApp conversations that had been
silently excluded because authoritative ownership was missing:

- conversation 1997;
- conversation 2029;
- conversation 2031;
- conversation 2039.

The deployed owner-work foundation now:

- includes missing or invalid ownership as
  `OWNERSHIP_DECISION_REQUIRED` instead of dropping the conversation;
- displays provider-window evidence without allowing that evidence to override
  missing ownership;
- supports a protected owner-admin ownership decision;
- revalidates exact conversation, contact, inbox, chronology, latest inbound,
  review, and window evidence;
- records append-only claim, result, observation, and recovery evidence;
- withholds replay and concurrency conflicts;
- keeps customer-send, Telegram, template, and unrelated business authority
  separate.

Conversation 1997 was changed to HUMAN during the first bounded operation, but
its first post-write observation failed because the verifier incorrectly
expected ownership-derived event identity to remain unchanged. PR #528
corrected that transition contract and deployed merge
`bc75a9b56a72e19c07a86aa6e2612c1f3f139e42`.

The bounded recovery then:

- appended the missing HUMAN observation for conversation 1997 without a
  second Chatwoot ownership write;
- changed conversations 2029, 2031, and 2039 to HUMAN exactly once;
- placed all four in `WAITING_FOR_OWNER_REPLY`;
- prepared replies for owner review.

Charl approved the revised exact replies. SAM revalidated each conversation
and sent exactly one public outgoing message:

| Conversation | Outgoing message | Provider result |
|---|---:|---|
| 2031 | 761065834 | read |
| 1997 | 761065962 | delivered |
| 2039 | 761066071 | delivered |
| 2029 | 761066176 | delivered |

There were zero automatic retries. No template, Telegram action, order,
reservation, farm/stock write, or unrelated business mutation occurred.

### Owner-facing workflow

The SAM Owner Inbox is:

`/api/sales/channels/chatwoot/sam/owner-inbox/page`

It is an owner work dashboard, not a replacement for Chatwoot. It shows:

- actionable and withheld conversations;
- unanswered count;
- current/stale review state;
- provider reply-window state and Johannesburg expiry;
- ownership exceptions and protected ownership controls;
- sanitized withholding reasons;
- a link to the exact Chatwoot conversation.

Reading or refreshing the page sends nothing. The page currently supports
ownership decisions but does not yet provide the complete
draft/edit/approve/send/delivery workflow inside the page.

### Next safe SAM work

1. Observe the four conversations read-only and confirm the new outgoing
   messages naturally remove them from actionable unanswered work.
2. If a customer replies, prepare a new recommendation or draft for owner
   review; do not auto-send.
3. Design the useful owner workflow directly in the inbox:
   view conversation, review evidence, edit draft, approve exact text, send
   once, and show provider confirmation.
4. Keep automatic ownership and automatic customer replies disabled until
   separately proven and owner-approved.

## BEACON

### Business outcome completed

BEACON completed the first governed organic Facebook publication:

- post:
  `920598737794159_122145593991122163`;
- one authorized publication attempt;
- three approved, hash-verified images in exact order;
- exact approved caption;
- zero retry, scheduling, boost, advertising, or spend.

The Organic Media Intelligence foundation was merged and deployed. Its
production migration was applied through a successful zero-state canary with
RLS, append-only enforcement, denied client access, and service-role
SELECT/INSERT only.

The first learning canary then atomically persisted exactly two events:

- `BEACON-LEARNING-MEDIA-UNDERSTANDING-00629D87CC440238B48091B6`;
- `BEACON-LEARNING-POST-UNDERSTANDING-6397EF93947B81BF19BF3694`.

Replay created no rows, altered identities conflicted, and cross-post
contamination was rejected. All stored action authorities remain false.

The initially prepared graduation event was correctly not persisted because it
was computed before these two rows existed. Graduation remains
`not_eligible`.

### Open BEACON work

PR #529, `fix(beacon): count confirmed delivery reliability`, is open at head
`cd60f0729a7949ff3f4b2c3779b1d1d545e7d318`. It changes two files and all
three exact-head CI gates pass. It must still receive normal independent review
and merge/deploy decisions.

The purpose of the correction is to distinguish:

- a confirmed external publication reference;
- a persisted confirmed-publication learning event;
- one reliable end-to-end operational run;
- performance observations at comparable windows.

No graduation event should be persisted from stale pre-commit counters.

### Next safe BEACON work

1. Review PR #529 independently.
2. Do not merge or deploy overnight unless separately owner-authorized.
3. After an approved correction is live, prepare a canonical
   confirmed-publication learning event from immutable execution evidence.
4. Capture comparable 24-hour, 72-hour, and 7-day read-only performance
   snapshots. Missing metrics remain unavailable, never fabricated as zero.
5. Recompute graduation only from persisted database evidence.
6. Continue recommendation-only learning; no automatic marketing authority.

## HERDMASTER

### Business outcome completed

The Auction workflow was redesigned after owner rejection of the repeated
21-card review interface. The accepted direction is:

- use the existing Readiness Table;
- add `Auction Candidates` and `Auction List` to the Bucket selector;
- put checkboxes in the far-left column;
- keep blocked candidates visible but disabled;
- make selection browser-local until explicit Add/Remove;
- provide compact controls and a printable Auction List;
- preserve clickable canonical pig links;
- keep the workflow separate from cohort, booking, reservation, sale, reminder,
  customer-contact, medical, lifecycle, and farm mutation authority.

PR #518 was merged and deployed. PR #527 corrected the optional Auction List
timeout so candidates render independently and the unavailable persistence
store fails quickly rather than rebuilding the entire readiness model.

### Later confirmed result

After this handover was initially recorded, migration
`202607260009_create_riversdale_auction_list_events.sql`, SHA-256
`62844ec08bfeed3ac9316c8763646da7dc9f1765d967411390c0793f0ed5de2b`, was
applied transactionally under its migration-specific advisory lock. The
schema-only backup and privilege checks passed. The table is RLS-enabled,
append-only, inaccessible to client roles, and grants `service_role` only
SELECT/INSERT. Its initial and 2026-07-27 verified event count is zero.

The persistence rail is therefore applied, but no owner selection, Auction
List membership, cohort/outlet assignment, reservation, booking or sale exists.
First use is still blocked because the production Auction List reader requires
`FARM_SUPABASE_DATABASE_URL`, which the deployed environment does not expose.
Auction Candidates continue to load independently.

### Next safe HERDMASTER work

1. Reconcile the Auction List reader with the canonical deployed database
   connection without weakening its bounded timeout or privilege contract.
2. Re-run owner-authenticated GET verification and require an available empty
   list before first use.
3. Add no animals to the real Auction List without Charl's explicit checkbox
   selection and Add action.

## ROOTLINE

### Business outcome completed

ROOTLINE reconciled the legacy irrigation system and proved that production's
78th irrigation row is a duplicate database representation of one legitimate
operational event. The original provenance rows remain unchanged.

PR #519 added a fail-closed superseded-migration guard. PR #520 repaired
Google Sheet LOG row identity and operational fingerprint handling. Both were
merged with passing post-merge CI.

The unsafe parallel daily-plan migration
`202607260005_create_irrigation_daily_plans` remains superseded and must not be
applied.

### C12345 physical canary

The selected first physical test is:

- zone C12345;
- vegetable drip irrigation;
- logical channel 2;
- ON event `irrigation_1_ch2_on`;
- OFF event `irrigation_1_ch2_off`;
- daylight only;
- Charl physically present;
- manual isolation ready;
- OFF independently prepared before ON;
- one ON attempt;
- no retry;
- hard maximum pulse of 30 seconds.

No physical canary was run because the daylight requirement was not satisfied.

PR #525 contains only the command-inert rehearsal module, tests, and operating
preflight. It is open at head
`0a325e463efc701cde3a09e40993d978ce65ec80`; all three exact-head CI gates
pass. No network, credential, transport, hardware, scheduler, workflow, queue,
or autonomous authority is included.

### Next safe ROOTLINE work

1. Leave hardware untouched overnight.
2. Independently review PR #525 before merge.
3. Do not apply the superseded daily-plan migration.
4. Resume the physical canary only in daylight with fresh weather evidence and
   the exact owner authorization packet.
5. After any ON invocation, issue OFF even if ON acceptance is failed,
   timed-out, or unavailable, unless manual isolation has already physically
   verified safe closure.

## CORE

CORE is the only agent allowed to continue bounded work overnight.

PR #517, `fix(core): bootstrap external process ownership`, is open at head
`2d819f0fdc3f029b32dc7ba908b7a94b0455650f`. It contains ten commits across
eight ownership/control/test files. The current GitHub state is clean and all
three exact-head CI gates pass.

Passing CI is not merge authority. Earlier independent review found critical
stop-marker, direct-start, direct-pickup, process-termination, acknowledgement,
PID identity, and startup-order risks. The current head requires a fresh,
independent final review against those exact findings.

Overnight CORE authority is limited to:

- inspect and correct PR #517;
- run production-shaped tests;
- collect review evidence;
- prepare an owner-review result.

CORE may not:

- remove or bypass the canonical stop marker;
- start the supervisor, runner, watchdog, or T0 missions;
- enable a scheduled task;
- merge, deploy, or promote PR #517;
- mutate mission, queue, lease, artifact, migration, or product state;
- broaden beyond the eight claimed files without a new reviewed scope.

## Workforce Control Room

The owner decided that the Workforce page should display the overall state of
the agentic team rather than only names and static capabilities.

The planned control-room dimensions are:

- Observe;
- Reason;
- Act;
- Verify;
- Learn;
- Graduate.

Each agent must separately display:

- code state;
- deployment state;
- runtime state;
- evidence state;
- current authority;
- blockers;
- owner decisions required;
- next best action;
- learning evidence;
- graduation status;
- source and freshness.

The complete plan is committed on branch
`docs/agent-workforce-control-room-plan` at commit `d684817f` and was local-only
when this handover was recorded. It must be pushed and reviewed before being
treated as repository-main doctrine.

## Repository And Open-Work Truth

- This handover is based on `origin/main` at
  `bc75a9b56a72e19c07a86aa6e2612c1f3f139e42`.
- The owner's original `main` workspace is intentionally dirty and far behind
  `origin/main`. Its unrelated files were not modified or cleaned.
- PR #529: BEACON confirmed-delivery reliability; open; CI green.
- PR #525: ROOTLINE command-inert C12345 rehearsal; open; CI green.
- PR #517: CORE ownership bootstrap; open; CI green; fresh independent review
  still required.
- Numerous older open PRs remain outside this handover's scope and must not be
  inferred to be current work merely because they are open.
- The Workforce control-room documentation is committed locally on its own
  branch and is not yet on `main`.

## Morning Restart Order

1. Read this handover and refresh `origin/main`.
2. Confirm whether HERDMASTER's migration canary produced a later result.
3. Check SAM's Owner Inbox read-only and confirm the four answered
   conversations are no longer actionable.
4. Review BEACON PR #529; preserve recommendation-only authority.
5. Review ROOTLINE PR #525; keep hardware untouched until daylight canary
   authorization.
6. Obtain a fresh independent verdict for exact CORE PR #517 head before any
   merge or runtime start.
7. Push/review the Workforce control-room documentation and use it as the
   implementation brief when the owner is ready.
