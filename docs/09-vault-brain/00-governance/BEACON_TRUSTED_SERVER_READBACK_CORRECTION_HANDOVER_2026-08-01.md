# BEACON trusted server readback correction handover

Status: source-only correction; no runtime, merge, deployment, Telegram, Meta or publication action

## Contained execution is terminal

`BEACON-FB-POST-A3E2BBED0CEA5F93E2` and result
`BEACON-FB-POST-A3E2BBED0CEA5F93E2-RESULT` are permanently consumed,
terminal and non-reusable. The correction must never replay that packet.

## Correction contract

For image execution, the service discards caller media metadata and resolves the
ordered asset identities through an authoritative read-only database projection.
That projection binds the canonical asset, private binary, bucket/object identity,
stored byte count, observed MIME, intake-time storage-readback hash, validation
version, Library Accept event and public-use event. Missing or conflicting lineage
fails before a claim or provider call.

The private object is then fetched through authenticated server credentials. The
server computes SHA-256 and byte length from the returned bytes, captures MIME and
an object version (`ETag` or Supabase version header), and timestamps the readback.
Redirected or non-success responses are rejected and cannot mint readback authority.
Validation accepts only that proof authority. A caller-supplied
`trusted_server_hash`, digest, object path, provenance label or approval cannot
become trust evidence. Missing object version, stale readback, byte/MIME/hash/path
mismatch, changed media or revoked/missing approval fails closed before Meta.

The validation-complete event binds safe digests of object identity/version plus
the binary identity, server-computed hash, byte count, MIME, approval event IDs and
readback time. The existing organic-publication binding continues to bind proposal,
owner decision, exact caption bytes, channel, timing authorization and deterministic
attempt identity. Claim-before-publication, unique execution identity and
no-retry-on-ambiguity remain unchanged.
After the claim, the server re-resolves the current projection and stops before the
provider if lineage or approval evidence changed.

## New execution identity

Prepared successor identity:
`BEACON-PUBLICATION-EXECUTION-928F7D5A9731FFDE3D62CE1A`.

It is deterministic over correction contract
`beacon_server_readback_publication_projection_v1`, proposal
`BEACON-PROPOSAL-18DEAAD8E896A87FE961F45B`, the two terminal execution IDs, asset
`BEACON-ASSET-15EBF5E67DBFD12693`, caption SHA-256
`58a60223599365b90803570909e09f3828c32768d8b27470dc1304ff27fc17d4`,
`facebook_organic`, and zero spend. It is prepared only and grants no authority.
The execution gate binds it to one fresh timing authorization, enforces the exact
asset, caption digest, Facebook organic channel and zero-spend boundary, and
rejects the old claim/result identities before any claim or provider call.
The timing identity must equal the authoritative owner-authorization generation;
the window endpoints are included in the deterministic attempt identity, so a
caller cannot mint a new attempt by supplying another timing label.

## Timing-only Oom Sakkie reauthorization packet

The original window ended at 2026-08-01 09:00 SAST. Do not reopen card `3144` or
restore its buttons. After this correction is deployed and verified, Oom Sakkie may
create one new decision identity bound to the successor execution identity and ask:

> The Bella image, exact caption, Facebook organic channel and R0 spend remain as
> already approved. What single new publication time should BEACON use?

The packet must offer only a specific new time or decline. It must not ask Charl to
repeat the image, caption, channel, content or public-use decision. Choosing a time
authorizes only one new claimed attempt in that new window; no scheduling, boost,
advertising, customer messaging or spend is implied.

## Integration sequence

1. Merge only after exact-head CI and required reviews pass.
2. Deploy through the serialized lane at verified lineage.
3. Run a no-Meta readback proof showing the exact 418,512-byte JPEG resolves to
   SHA-256 `15ebf5e67dbfd12693bab79464c7012d221c4686207a730dac3161e097048b55`
   with current object-version and approval evidence.
4. Prepare and deliver the timing-only Oom Sakkie packet once; do not modify card
   `3144` or the terminal failed execution.
5. Only after fresh timing approval, create one new durable claim for the successor
   identity and use the existing reviewed provider path. Reconcile ambiguous Meta
   completion read-only and never retry it.

Preserve SAM Level 1, conversation 937 quarantine, PR #642, HERDMASTER Zigay
containment, ROOTLINE, Oom Sakkie summary and unrelated configuration.
