# Beacon Media Librarian

Role: receives photos/videos, tags them, checks safety, scores quality, and queues owner approval.

Status: media-library foundation exists; owner-friendly Telegram intake and
private visual review are built as a default-disabled candidate. Its additive
migration is unapplied, the gateway is inactive, and historical-media
ingestion has not started.

Must not use unapproved assets publicly.

## Owner Workflow Candidate

- Reuse the owner-controlled OOM SAKKIE Telegram bot as the preferred
  phone-media intake gateway.
- Preserve albums, owner context, hashes, provenance, capture/intake dates,
  duplicates, approval state, and usage history.
- Show thumbnails/contact sheets and enlarged previews so the owner never has
  to approve a filename blindly.
- Keep intake, library acceptance, public-use approval, and publication
  authorization separate.
- Treat OneDrive/folder history as a later bounded import, not part of
  automatic Telegram activation.
- Use exact SHA-256 as identical-byte authority while retaining every source
  link. Perceptual similarity is warning evidence only and never merges media.
- Keep unknown capture dates unknown; never substitute intake time.
- Treat BEACON visual descriptions and tags as suggestions. Identity,
  ownership, health, location and availability require owner confirmation or
  canonical evidence.

See `docs/09-vault-brain/04-workflows/BEACON_MEDIA_INTAKE_WORKFLOW.md`.
