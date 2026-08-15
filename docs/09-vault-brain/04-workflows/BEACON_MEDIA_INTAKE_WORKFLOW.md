# BEACON Media Intake Workflow

Status: owner-approved append-only foundation deployed, with the 15 August 2026
four-photo album exposing an inactive Render policy and shared-gateway
precedence defect. BMQ-20260813-02 owns correction and live recovery.

## Owner Outcome

Charl must be able to take photos or videos on a phone, send one item or a
Telegram media group to the existing owner-controlled OOM SAKKIE bot with a
plain-language explanation, and then review the actual media visually in the
Farm App. The normal workflow must not require an intermediate OneDrive upload
or a second manual Farm App upload.

## Department Boundary

- OOM SAKKIE is the preferred owner intake gateway.
- BEACON Media Librarian owns private storage, cataloguing, media
  understanding, review state, usage history, and campaign suitability.
- Telegram intake does not grant library acceptance, public-use or
  publication authority.
- A separate BEACON Telegram bot should be created only if a reviewed technical
  or security constraint proves the shared owner bot cannot provide safe
  isolation.

## Target Flow

1. Charl sends a photo, video, or Telegram album to the allowlisted OOM SAKKIE
   owner chat.
2. Charl's caption is retained as owner-provided context, not as visually
   proven fact.
3. A bounded, idempotent intake operation downloads every expected item
   exactly once and fails closed on partial albums.
4. Originals enter the private `beacon-raw-intake` bucket.
5. Server-side hashes detect exact duplicates while preserving every source
   reference.
6. BEACON prepares media understanding, suggested tags, quality/privacy
   warnings, campaign-use suggestions, and prior-use evidence.
7. The Farm App presents thumbnails/contact sheets and an enlarged preview
   instead of asking the owner to approve filenames.
8. Charl may approve, reject, archive, or correct individual assets;
   album-level decisions are available where safe.
9. Public use and later publication remain separate decisions.

Provider media must enter the typed BEACON intake before generic owner-context
or semantic handling on both the retained GateKeeper gateway and any future
direct webhook. Album members share one HMAC-derived group identity, append
caption/context evidence independently of arrival order, and use the existing
family-message lifecycle for one provider-confirmed receipt and silent replay.
A bounded incident-recovery context supplement is accepted only with a
temporary high-entropy Render token bound to the exact provider media-group;
remove that token immediately after recovery.

## Built Candidate Contract

The `BEACON-MEDIA-INTAKE-1` candidate:

- requires both the existing OOM SAKKIE owner-user allowlist and a separately
  configured exact private-chat allowlist;
- stores only process-keyed/HMAC-derived owner and chat identities in intake
  evidence, never the raw chat or owner identifier;
- validates replay identity before Telegram file access;
- streams JPEG/PNG downloads in 64 KiB chunks through an 8 MiB hard limit,
  ignoring `Content-Length` as authority over the observed byte count;
- validates magic bytes, declared and returned MIME, complete decoding,
  maximum 12,000-pixel dimensions, and a 40-megapixel pixel cap;
- computes SHA-256 during bounded processing and verifies the private object
  by storage readback before final metadata;
- creates one canonical binary for identical bytes while retaining every
  immutable Telegram source reference;
- never uses perceptual similarity to merge assets;
- exposes partial storage/metadata outcomes as failed, quarantined or
  reconciliation-required rather than claiming cross-service atomicity;
- sends one bounded, opaque `/beacon-complete` action for a Telegram album,
  never exposes the provider media-group identifier, and derives immutable
  final order from Telegram message order only after every item is durable;
- supports owner-authenticated private thumbnail/contact-sheet review without
  exposing storage URLs;
- permits whole-album review only after durable explicit completion, and binds
  every owner decision to a stable action identity plus its exact predecessor
  so delayed delivery cannot become a new transition; and
- keeps video visibly unsupported until bounded resumable transport is
  separately designed and reviewed, and sends the owner one bounded
  unsupported receipt without accessing the video file.

The candidate is not operational until its migration and configuration receive
separate authorization.

## Required Evidence

Each asset or intake group should preserve:

- immutable asset and intake-group identities;
- original Telegram media-group order;
- source and bounded source reference;
- Telegram intake time;
- capture time when authoritatively available;
- original filename when available;
- media type, MIME type, dimensions, file size, and server SHA-256;
- owner-provided context;
- BEACON observations and confidence;
- duplicate and source-provenance links;
- library/context decisions on the intake rail; public-use approval/revocation
  on the existing canonical BEACON asset-event rail; and usage history.

Bot credentials, private download URLs, signed storage URLs, unnecessary chat
content, and unbounded Telegram metadata must not enter the asset record.

## Approval Model

These gates are deliberately separate:

1. **Intake received:** the private file and provenance were stored
   successfully.
2. **Library accepted:** the asset may remain in BEACON's managed library.
3. **Public-use approved:** the exact asset may be considered for public
   campaigns.
4. **Publication authorized:** an exact post, caption, media order, channel,
   and execution attempt has its required authority.

No earlier gate implies a later gate. Approvals and revocations must be
append-only and owner-attributed.

## Visual Review Requirement

The owner review surface must be mobile-friendly and show:

- real thumbnails or an album contact sheet;
- enlarged preview;
- owner explanation;
- BEACON description and suggested tags;
- quality, privacy, safety, and unsupported-identity warnings;
- duplicate and prior-use status;
- capture and intake dates;
- suggested campaign uses;
- clear individual and album decisions.

BEACON must never identify a person, animal, location, ownership, availability,
health outcome, or sale status solely from visual inference. Suggestions
remain unconfirmed until linked to canonical evidence or confirmed by the
owner.

## Historical Media

Existing OneDrive/folder media requires a separate bounded import phase using
the same hashes, provenance, review states, and visual interface. It must:

- preserve original folder and filename evidence;
- keep capture date distinct from import date;
- collapse exact binary duplicates without discarding source provenance;
- leave uncertain dates, subjects, locations, and rights as `Unknown`;
- import into private review state only;
- grant no automatic library, public-use, or publication approval.

The historical import must not begin automatically with Telegram activation.

## Safety and Authority

The intake must fail closed for unauthorized senders, incomplete albums,
replay ambiguity, unsupported or oversized media, download failure, hash
mismatch, partial persistence, or unavailable storage.

Initial authority excludes:

- customer or public Telegram replies beyond a bounded owner receipt;
- public posting or scheduling;
- Meta writes;
- advertising, boosting, or spending;
- customer messaging;
- animal identity or business-state mutation;
- automatic historical imports.

The gateway may send at most one bounded receipt to the already-validated
owner private chat after durable single-item or explicitly completed album
intake. That receipt is not general conversation or customer-message
authority.

## Delivery Sequence

1. Audit the current OOM SAKKIE Telegram gateway, BEACON media library,
   storage limits, schemas, privileges, and owner UI.
2. Produce the smallest reviewed implementation with production-shaped
   security, replay, partial-album, duplicate, mobile visual, privilege, and
   zero-authority tests.
3. Integrate code and any additive schema separately from activation.
4. Run a zero-state storage/schema canary if required.
5. Activate only for the exact owner allowlist and run one supervised
   private-media intake canary.
6. Reconcile runtime truth and documentation.
7. Plan historical OneDrive/folder import as a separate phase.

## Success Measure

Charl can send one phone album plus one explanation to OOM SAKKIE and later
approve or reject the visible media in the Farm App without using OneDrive or
manually uploading the files again. No asset becomes public or publishable
merely because it was received.
