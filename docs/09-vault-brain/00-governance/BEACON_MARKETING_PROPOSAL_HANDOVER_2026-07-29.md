# BEACON marketing proposal source handover

Status: source-only candidate; no integration, deployment, message or public
action has occurred.

## Current truth

The first authenticated private-photo intake is closed and retained only as
regression evidence. The production media intake remains single-image for the
next bounded proof. Existing campaign, media-library and owner-review
foundations do not yet compose one Oom Sakkie proposal loop.

`modules/beacon/marketing_proposal.py` prepares one deterministic, read-only
packet from verified business evidence and private media projections. It
accepts only a server-resolved current-media projection whose current state is
explicitly `library_accepted`; records campaign selection without granting
public use; shape-validates per-image identity, SHA-256, authenticated private
preview reference, private-storage proof and current review-event provenance;
the later adapter remains responsible for resolving those proofs from trusted
server state. The contract deduplicates exact bytes;
supports either one sufficient image or an ordered multi-image candidate; and
rejects unsupported protected claims.

When no suitable accepted image exists, the packet asks Oom Sakkie for one
specific subject, angle, orientation and purpose. It never asks Charl to invent
the marketing content. Every packet has all write, publication, Meta, customer
message, advertising, boosting, spend, public-use and media-record authority
fixed to false.

## Exact later Oom Sakkie adapter edits

The serialized production owner should:

1. In the existing authenticated Oom Sakkie specialist registry, register one
   BEACON read-only intent that invokes `prepare_marketing_proposal`; do not
   create a second registry or route.
2. In the existing Oom Sakkie service, project one current business-evidence
   objective and media rows into the contract. Resolve each asset's latest
   library-review event server-side and include asset ID, SHA-256, private
   storage-readback proof ID, review event ID, tags and suitability. Do not
   accept caller-asserted approval or provenance.
3. Render `missing_media_request.family_message` as one family question, or
   render a `marketing_proposal` as one message containing objective, audience,
   exact thumbnails/media order, caption, CTA, evidence, missing facts,
   channel, protected actions and Approve / Correct / Decline choices.
4. Bind any later decision to `packet_id` and the exact media hashes, text,
   channel and order. Store that decision only in the existing owner-decision
   rail. Approval of the proposal must not write public-use approval, enqueue
   publication or call Meta.
5. Keep multi-image ingestion and adapter grouping disabled in production
   until every supplied image independently passes authenticated intake,
   storage readback, hash, cataloguing and Library Accept review, and an
   integration test proves ordered packet rendering and replay deduplication.
6. Run one supervised read-only proof with an explicitly Library Accepted
   private image. If none supports the chosen evidence-backed objective, send
   exactly one precise missing-media request instead. Do not replay the
   completed intake photo.

Files intentionally not edited: Oom Sakkie registry, routing and service;
Telegram and GateKeeper; Render and n8n; database and bucket code; CI
registration; public-use and publication flows.

## Future production proof

Oom Sakkie presents one evidence-backed BEACON proposal containing a current
explicitly Library Accepted private image, exact draft and separated protected
actions, and Charl approves, corrects or declines it in that single place; or,
if no accepted image fits, Oom Sakkie asks once for the contract's precise
shot. Observation must confirm zero public-use mutation, publication, Meta
call, customer message, advertising, boosting and spend.

Expected measurable marketing outcome: reduce owner input for one viable
organic-post proposal to at most one consolidated approve/correct/decline
response, with zero owner-written caption or shot brief; record proposal to
decision time for the future proof.
