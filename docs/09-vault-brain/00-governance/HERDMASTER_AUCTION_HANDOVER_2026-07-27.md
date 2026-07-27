# HERDMASTER Auction Handover — 2026-07-27

## Scope and authority

This handover records the bounded Riversdale Auction state established on
2026-07-27. It does not authorize an animal observation, medical decision,
Auction List Add or Remove, cohort or outlet assignment, reservation, booking,
sale, reminder, customer contact, or farm-state mutation.

PR #530 remains open and must not be merged as current truth. Its base
(`0c4eb404`) predates the current Auction List implementation, production
migration state, connection repair, and newer shared Vault work. This bounded
handover supersedes only PR #530's HERDMASTER Auction assertions; it does not
replace newer SAM, BEACON, ROOTLINE, CORE, `NEXT_STEPS`, source-map, changelog,
or agent-document ownership.

## Deployed persistence and connection truth

- Migration `202607260009_create_riversdale_auction_list_events.sql` is applied
  in production. Persistence availability is distinct from owner selection,
  outlet assignment, booking, reservation, and sale.
- The zero-state first-use proof on 2026-07-27 found exactly zero current
  Auction List members and zero append-only Auction List events.
- PR #536 repaired the Auction List store resolver and merged as
  `be769a7c70cb66858ec27d6894a7960944f76d22`.
- The reader uses the explicit function argument first, a nonblank
  `FARM_SUPABASE_DATABASE_URL` override second, and the application-canonical
  `DATABASE_URL` otherwise. No new required environment variable or credential
  duplication was introduced.
- Render deployed the exact merge. The owner-authenticated GET returned HTTP
  200 with `status=available`, zero members, and no change to the event count.

## Candidate evidence cut

The bounded owner-authenticated evidence cut on 2026-07-27 contained:

- 21 Riversdale candidate-preview animals;
- zero Auction List members;
- zero candidate-review rows;
- zero canonical physical-observation rows;
- all 21 with canonical readiness withdrawal state `cleared`;
- all 21 with canonical medical state `Clear`;
- all 21 blocked from selection because no fresh physical-quality review was
  present.

The previous recommendation projection did not carry the existing canonical
withdrawal state into its candidate evidence. That was a projection defect,
not proof of missing withdrawal evidence. Physical-quality evidence was
genuinely absent. No absence of treatment history may be interpreted as
`not_applicable`, `cleared`, or otherwise safe.

Candidate identities, tags, pens, medical references, and owner notes remain
owner-only and are intentionally omitted here.

## Integrated evidence workflow candidate

PR #537 is the separately reviewed implementation candidate for the existing
Auction Candidates table. It:

- keeps one compact `Details / Review` action per existing row;
- derives withdrawal evidence server-side from canonical medical records;
- records a factual physical-quality observation and append-only candidate
  review using the stable server-derived owner principal;
- reloads candidate membership and evidence under the same transaction used
  for persistence;
- makes missing, stale, conflicting, or unavailable evidence fail closed;
- requires canonical medical state `Clear`, affirmative withdrawal evidence,
  and a fresh `suitable` quality review before selection;
- keeps checkbox selection browser-local;
- keeps review submission separate from the explicit Auction List Add action;
- grants no cohort, outlet, reservation, booking, sale, reminder, customer,
  medical, lifecycle, purpose, or farm mutation authority.

PR #537 merged normally as
`84529cacdc831e474dfa5feaff798dd1bf44fb4a`. Exact-merge CHARLIE CORE,
disposable-PostgreSQL and Playwright checks passed. Render deploy
`dep-d9jkej6q1p3s73bit8o0` reached live at that exact revision and `/health`
returned HTTP 200.

The bounded owner-authenticated post-deploy proof returned HTTP 200 for
`/pig-allocation`, readiness, recommendation and Auction List. It retained 21
candidate-preview animals, zero Auction List members and zero Auction List
events.

## First supervised evidence result

The first owner-admin physical-quality review was recorded once on 2026-07-27.
The subsequent bounded read-only verification established:

- exactly one immutable candidate-review row;
- exactly one linked canonical `body_condition` observation row;
- matching Pig_ID, auction cycle and observation time across both rows;
- quality state `suitable`;
- canonical medical state `Clear`;
- canonical withdrawal state `cleared`;
- stable server-derived owner identity present but not exposed;
- one idempotency identity protected by a unique constraint;
- exact replay would create zero additional rows;
- the reviewed animal became selectable;
- the animal remained absent from the Auction List;
- total Auction List events remained zero.

Private Pig_ID, tag, owner identity and medical references remain available only
on the protected owner surface and are intentionally omitted here. The
verification sent no POST and performed no business or livestock mutation.

## Next controlled owner operation

The next separately authorized operation may use the now-selectable,
owner-visible reviewed row:

1. Open `/pig-allocation` as owner-admin and select `Auction Candidates`.
2. Select only the verified row using its browser-local checkbox.
3. Confirm the selected count is exactly one.
4. Press `Add selected to Auction List` once.
5. Do not select any other animal or perform any outlet, reservation, booking,
   sale, reminder, customer-contact or farm action.
6. Perform a read-only verification that exactly one append-only Add event
   exists, the current list contains exactly that animal, and replay created no
   duplicate.

## Delivery state

- Auction List persistence: applied and available.
- Auction List connection repair: built, merged, deployed, and operationally
  proven read-only.
- Integrated evidence-capture workflow: built, independently reviewed, merged
  and deployed; owner surface operational.
- First candidate physical-quality evidence: recorded once and verified.
- Auction List first Add: not performed.
- Animal/business/protected actions during this work: none.

## First Add canary outcome

Charl authorized a one-animal Add for the single reviewed and affirmatively
selectable candidate. The controlled browser harness reached its total timeout
without returning an Add response. The action was not retried.

The immediate database/API read-only verification proved:

- zero Auction List events for the authorized animal;
- zero Auction List events in total;
- zero current Auction List members;
- the animal remained selectable and unlisted;
- its one candidate review and one linked factual observation were unchanged;
- medical state remained `Clear`;
- withdrawal state remained `cleared`;
- no unrelated livestock, auction or business mutation was evidenced.

Therefore the attempted canary did not persist an Add event and is not
complete. This is a safe zero-state stop, not a successful Auction first use.
A future attempt requires a new exact owner authorization; it must never be
treated as an automatic retry.
