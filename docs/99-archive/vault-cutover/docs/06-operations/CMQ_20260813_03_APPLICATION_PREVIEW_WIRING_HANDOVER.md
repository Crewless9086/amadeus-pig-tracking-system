# CMQ-20260813-03 application preview wiring handover

Status: source-prepared

Owner: CORE, with HERDMASTER farm-data review

The existing application grouped-weight preflight now attaches the canonical
grouped-weight/optional-movement preview after, and only after, the established
preflight accepts rows. The adapter derives its immutable pig/pen snapshot from
those already accepted rows. `Active`/on-farm animal and active destination-pen
values in that derived snapshot are explicit attestations of the immediately
preceding authoritative legacy preflight, not independent observations. Failed
identity or pen evidence passes through unchanged and never reaches the adapter.
The adapter performs no second Supabase or Google Sheets read and invokes no
staging or executor path.

The legacy preflight payload and accepted rows remain present. The new evidence
adds a deterministic preview digest and confirmation requirement. Any mismatch
between accepted evidence and the canonical contract fails the preview closed.
Movement-only rows preserve weight as `Unknown`; missing optional movement and
notes remain `Unknown`; per-row destination pens retain opaque identifiers.
Those movement-only/per-row extensions are restricted to `application_typed`;
OOM typed and prepared browser-voice semantics remain unchanged.

Only the application preview controller is wired. Application staging,
processing, retry and execution remain unchanged. OOM SAKKIE, Telegram, voice,
UI, routes, protected claims, migrations, schema, Supabase/Sheets fallback and
production configuration remain unchanged. This is source evidence only and is
not deployed runtime capability.
