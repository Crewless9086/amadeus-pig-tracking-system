# Beacon Media Librarian

Role: receives photos/videos, tags them, checks safety, scores quality, and queues owner approval.

Status: media-library foundation exists; owner-friendly Telegram intake,
visual review expansion, and historical-media ingestion are queued, not yet
operational.

Must not use unapproved assets publicly.

## Queued Owner Workflow

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

See `docs/09-vault-brain/04-workflows/BEACON_MEDIA_INTAKE_WORKFLOW.md`.
