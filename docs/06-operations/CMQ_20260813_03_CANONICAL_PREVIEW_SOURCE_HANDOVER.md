# CMQ-20260813-03 canonical grouped preview source handover

Status: source-prepared

Owner: CORE, with HERDMASTER farm-data review

This slice adds `modules/pig_weights/canonical_grouped_preview.py`, a pure and
currently unwired grouped-weight/optional-movement preview contract. It changes
no public route, executor, UI, protected-action runtime, schema, fallback or
production configuration.

The contract accepts only explicit facts plus caller-supplied pig and pen
snapshots. Application-typed, OOM-typed and prepared browser-voice text adapters
produce byte-equivalent canonical rows, effective date, preview digest and
confirmation requirement. Unknown optional facts stay `Unknown`. Ambiguous,
duplicated, inactive/off-farm animals and invalid/ambiguous destination pens
fail closed. Telegram voice is rejected until transcript routing is proven.

Focused tests prove the module imports no repository, database, HTTP, provider,
Telegram, Supabase or Sheets adapter and reports zero effects. This is
development-terminal source evidence only: no deployed runtime imports the
module, no provider was invoked, and no farm data was read or written.

Next gate: after reviewed integration, separately authorize wiring one existing
preview adapter at a time without changing either executor. No runtime or
Business improvement may be claimed before deployment and genuine acceptance.
