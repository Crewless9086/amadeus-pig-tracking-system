# BEACON Media Intake Workflow

Status: owner-approved direction, queued after BEACON's current confirmed-publication learning work reaches a clean integration point. Not yet implemented or activated.

## Owner Outcome

Charl must be able to take photos or videos on a phone, send one item or a Telegram media group to the existing owner-controlled OOM SAKKIE bot with a plain-language explanation, and then review the actual media visually in the Farm App. The normal workflow must not require an intermediate OneDrive upload or a second manual Farm App upload.

## Department Boundary

- OOM SAKKIE is the preferred owner intake gateway.
- BEACON Media Librarian owns private storage, cataloguing, media understanding, review state, usage history, and campaign suitability.
- Telegram intake does not grant public-use or publication authority.
- A separate BEACON Telegram bot should be created only if a reviewed technical or security constraint proves the shared owner bot cannot provide safe isolation.

## Target Flow

1. Charl sends a photo, video, or Telegram album to the allowlisted OOM SAKKIE owner chat.
2. Charl's caption is retained as owner-provided context, not as visually proven fact.
3. A bounded, idempotent intake operation downloads every expected item exactly once and fails closed on partial albums.
4. Originals enter the private `beacon-raw-intake` bucket.
5. Server-side hashes detect exact duplicates while preserving every source reference.
6. BEACON prepares media understanding, suggested tags, quality/privacy warnings, campaign-use suggestions, and prior-use evidence.
7. The Farm App presents thumbnails/contact sheets and an enlarged preview instead of asking the owner to approve filenames.
8. Charl may approve, reject, archive, or correct individual assets; album-level decisions are available where safe.
9. Public use and later publication remain separate decisions.

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
- library decision, public-use decision, revocation, and usage history.

Bot credentials, private download URLs, signed storage URLs, unnecessary chat content, and unbounded Telegram metadata must not enter the asset record.

## Approval Model

These gates are deliberately separate:

1. **Intake received:** the private file and provenance were stored successfully.
2. **Library accepted:** the asset may remain in BEACON's managed library.
3. **Public-use approved:** the exact asset may be considered for public campaigns.
4. **Publication authorized:** an exact post, caption, media order, channel, and execution attempt has its required authority.

No earlier gate implies a later gate. Approvals and revocations must be append-only and owner-attributed.

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

BEACON must never identify a person, animal, location, ownership, availability, health outcome, or sale status solely from visual inference. Suggestions remain unconfirmed until linked to canonical evidence or confirmed by the owner.

## Historical Media

Existing OneDrive/folder media requires a separate bounded import phase using the same hashes, provenance, review states, and visual interface. It must:

- preserve original folder and filename evidence;
- keep capture date distinct from import date;
- collapse exact binary duplicates without discarding source provenance;
- leave uncertain dates, subjects, locations, and rights as `Unknown`;
- import into private review state only;
- grant no automatic library, public-use, or publication approval.

The historical import must not begin automatically with Telegram activation.

## Safety and Authority

The intake must fail closed for unauthorized senders, incomplete albums, replay ambiguity, unsupported or oversized media, download failure, hash mismatch, partial persistence, or unavailable storage.

Initial authority excludes:

- customer or public Telegram replies beyond a bounded owner receipt;
- public posting or scheduling;
- Meta writes;
- advertising, boosting, or spending;
- customer messaging;
- animal identity or business-state mutation;
- automatic historical imports.

## Delivery Sequence

1. Finish and safely integrate BEACON's active confirmed-publication learning work.
2. Audit the current OOM SAKKIE Telegram gateway, BEACON media library, storage limits, schemas, privileges, and owner UI.
3. Produce the smallest reviewed implementation with production-shaped security, replay, partial-album, duplicate, mobile visual, privilege, and zero-authority tests.
4. Integrate code and any additive schema separately from activation.
5. Run a zero-state storage/schema canary if required.
6. Activate only for the exact owner allowlist and run one supervised private-media intake canary.
7. Reconcile runtime truth and documentation.
8. Plan historical OneDrive/folder import as a separate phase.

## Success Measure

Charl can send one phone album plus one explanation to OOM SAKKIE and later approve or reject the visible media in the Farm App without using OneDrive or manually uploading the files again. No asset becomes public or publishable merely because it was received.
