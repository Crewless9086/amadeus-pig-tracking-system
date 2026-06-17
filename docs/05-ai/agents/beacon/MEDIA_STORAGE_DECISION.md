# Beacon Media Storage Decision

## Decision

Beacon media files will use Supabase Storage for binary media and Postgres for searchable metadata.

## Storage Layout

Buckets:

- `beacon-raw-intake`
  - Private intake bucket.
  - Farm App uploads, Telegram imports, folder imports, and future WhatsApp media arrive here first.
  - Assets in this bucket are not approved for public use.

- `beacon-approved-media`
  - Private approved-media bucket.
  - Later phase for assets approved by the owner for Beacon campaign suggestions.
  - Public serving, signed URLs, CDN/public buckets, and copy/move workflows are not enabled in Phase 11P/11Q.

## Metadata Layout

Postgres owns the searchable asset library:

- asset id,
- bucket and storage path,
- original filename,
- media type and MIME type,
- file size,
- source,
- uploader/source reference,
- sale-stream relevance,
- subject tags,
- location/context,
- quality score,
- privacy risk,
- safety flags,
- owner approval status,
- campaign usage count,
- review events.

## Current Phase 11P/11Q Authority

Allowed:

- register media metadata,
- upload small files to `beacon-raw-intake` when Supabase Storage envs are configured,
- list assets,
- record owner review events,
- mark approval evidence as an append-only event,
- use `/sales/beacon-media` as the Farm App owner review surface.

Not allowed:

- public posting,
- customer messages,
- Meta/Facebook/Instagram calls,
- n8n sends,
- Chatwoot sends,
- public buckets,
- paid spend,
- automatic campaign use,
- quote/order/stock/reservation changes.

## Env Requirements

Metadata only:

- `DATABASE_URL`

Farm App standard upload:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Do not add `SUPABASE_SERVICE_ROLE_KEY` to browser/client code. It is backend-only.

## Upload Limits

Phase 11P/11Q supports standard backend uploads up to 6MB.

Large videos need a later TUS/resumable upload phase. The metadata schema already supports videos, but the first upload path is intentionally limited so the backend does not become a fragile large-file pipe.

## Current API Surface

- Farm App page: `/sales/beacon-media`
- `GET /api/beacon/media-policy`
- `GET /api/beacon/media-assets`
- `POST /api/beacon/media-assets`
- `POST /api/beacon/media-assets/upload`
- `POST /api/beacon/media-assets/<asset_id>/events`

## Next Gates

Completed:

- `supabase/migrations/202606180002_create_beacon_media_library.sql` applied.
- Private buckets `beacon-raw-intake` and `beacon-approved-media` created.
- Render/local upload envs configured.
- One small Render upload/readback smoke passed.
- Farm App review UI built at `/sales/beacon-media`.

Next:

- Deploy and owner-check `/sales/beacon-media`.
- Connect approved media to Beacon campaign draft selection without enabling public posting or scheduling.
