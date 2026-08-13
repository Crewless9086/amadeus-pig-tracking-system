# CMQ-20260813-03 canonical claim/executor compatibility

Status: source-prepared; not deployed

Owner: CORE, with OOM SAKKIE authority and HERDMASTER farm-data review

## Audit finding

The deployed typed OOM preview showed the pure canonical rows and digest, but
stored a different legacy payload and digest in the durable protected claim.
The callback and grouped executor were therefore bound to the legacy object,
not to the exact canonical object shown to Charl. Canonical `Unknown` sentinels
also could not safely be interpreted as database or movement identifiers.

This was a real compatibility defect, not a reason to add a preview-only route
or bypass the protected lifecycle.

## Narrow correction

The pure contract now defines its digest over the exact protected action kind
and canonical payload. Typed OOM stores that same payload in the existing
durable claim. Consequently the owner-visible preview digest, claim digest and
executor binding are identical. The claim retains the already computed
evidence-generation identity, owner/private-chat identity, provider message,
expiry and preview-card binding.
The canonical digest uses the established protected-claim JSON serializer, so
non-ASCII tag or note evidence cannot split the displayed and durable identity.
Natural OOM and canonical parsing accept the same Unicode letter/digit and
hyphen identity tokens. Before claim creation the runtime compares every
canonical pig, normalized weight, movement destination and effective date to
the accepted natural preview; a partial or divergent parse fails closed.

The existing executor accepts the canonical contract directly. It preserves
opaque pig and destination-pen identifiers, effective date, numeric weight,
tag and optional notes in the claimed source payload. `Unknown` current pen is
compared to an empty canonical current-pen value, while `Unknown` destination
means no movement; it is never treated as an identifier. Pre-existing active
legacy claims remain executable under their exact legacy digest.

Confirmation still requires the exact active claim and provider/card identity.
The executor recomputes the digest before opening a farm transaction, obtains
claim and per-pig serialization locks, revalidates active/on-farm/current-pen
truth and same-date weight absence, and writes the batch, rows, weight events,
optional movement events and claim completion in one database transaction.
Changed evidence is contained with zero farm effects. A partial database
failure rolls back the group. The exact confirmation receipt can recover an
`executing` claim; after the token lock, durable completed state returns the
stored result as a zero-send, zero-edit, zero-write no-op. Competing
confirmation remains stale.

## Authority boundary

No production input, Telegram send, claim creation, confirmation, executor,
provider or farm write was invoked during this work. No route, UI, voice,
configuration, schema, migration, application adapter, Sheets fallback or
production setting changed. A future genuine acceptance may create exactly
one durable claim and send exactly one preview, but farm effects remain barred
until Charl confirms that exact displayed digest.
