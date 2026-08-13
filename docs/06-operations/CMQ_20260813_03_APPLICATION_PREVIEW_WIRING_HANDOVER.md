# CMQ-20260813-03 application preview wiring handover

Status: source-prepared

Owner: CORE, with HERDMASTER farm-data review

The existing application grouped-weight preflight now attaches the canonical
grouped-weight/optional-movement preview after, and only after, the established
preflight accepts rows. The adapter derives its immutable pig/pen snapshot from
those already accepted rows; it performs no second Supabase or Google Sheets
read and invokes no staging or executor path.

The legacy preflight payload and accepted rows remain present. The new evidence
adds a deterministic preview digest and confirmation requirement. Any mismatch
between accepted evidence and the canonical contract fails the preview closed.
Movement-only rows preserve weight as `Unknown`; missing optional movement and
notes remain `Unknown`; per-row destination pens retain opaque identifiers.

Only the application preview controller is wired. Application staging,
processing, retry and execution remain unchanged. OOM SAKKIE, Telegram, voice,
UI, routes, protected claims, migrations, schema, Supabase/Sheets fallback and
production configuration remain unchanged. This is source evidence only and is
not deployed runtime capability.
