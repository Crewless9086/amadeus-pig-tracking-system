# Beacon Data Model

Beacon uses private media asset metadata, review events, campaign draft selections, publish packets, manual post evidence, performance evidence, and Facebook post execution evidence where approved.

Beacon must not use unapproved/private media publicly.

## Organic Media Learning Events

`public.beacon_organic_media_learning_events` is the append-only evidence rail
for media understanding, post understanding, confirmed publication,
performance snapshots, policy evaluations, owner usefulness ratings,
publication reliability and graduation evaluations.

Every event binds a stable event identity, Facebook post identity, channel,
objective, measurement window, evidence key, canonical payload SHA-256 and
canonical JSON payload. Replays with the same identity and payload are
withheld; an altered payload conflicts. Cross-post evidence, incompatible
windows and any mutating authority fail closed. UPDATE and DELETE are blocked,
RLS is enabled, browser roles have no direct access, and the service boundary
has SELECT/INSERT only.

Missing provider metrics remain unavailable rather than numeric zero.
Graduation counts distinct persisted posts, compatible windows, ratings and
reliable runs; caller-supplied aggregate counters are not authority.

Production evidence after the 2026-07-27 canary is four rows for one Facebook
post: media understanding, post understanding, confirmed publication and a
`not_eligible` graduation evaluation. No performance snapshot has been
recorded because the first 24-hour measurement window is not yet due.

## Media Intake Foundation Candidate

`BEACON-MEDIA-INTAKE-1` must bind immutable intake-group and asset identities,
Telegram media-group order, bounded source references, intake and authoritative
capture times separately, original metadata where available, MIME, dimensions,
size, server SHA-256, owner context, qualified observations, duplicate links,
and append-only decision/usage history.

Migration `202607270001_create_beacon_media_intake.sql` is the unapplied
additive candidate. It introduces:

- immutable intake groups, source items and explicit album membership;
- one SHA-256-unique canonical binary with many source links;
- append-only intake/reconciliation, understanding and library/context events,
  with public-use approval/revocation bridged transactionally to the existing
  canonical `beacon_media_asset_events` rail;
- a read-only current-state projection;
- owner/chat identity HMACs, Telegram replay identities, source-message time,
  capture time and intake time as separate evidence; and
- private thumbnail and qualified-observation provenance.

Every table has RLS enabled with no browser policy. PUBLIC, `anon` and
`authenticated` have no table privileges; `service_role` has SELECT/INSERT
only. UPDATE/DELETE triggers enforce append-only evidence, and direct execution
of their enforcement function is revoked from every application role.

The migration is unapplied and no production row exists. Intake receipt,
library acceptance, public-use approval and publication authorization remain
separate evidence states. Historical OneDrive/folder ingestion remains a
separate phase.
