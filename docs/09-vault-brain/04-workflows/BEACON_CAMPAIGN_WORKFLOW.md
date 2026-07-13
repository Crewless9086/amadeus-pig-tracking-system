# Beacon Campaign Workflow

1. Beacon detects opportunity from the owner-read-only Supabase-first scanner; a scanner card is advisory and cannot trigger a campaign or public action.
2. Beacon reads the owner-review operating contract and verifies fresh fulfilment evidence; missing, stale, invalid, or zero capacity stops campaign targeting.
3. Drafts campaign plan/copy/media selection within the channel allowlist and demand ceiling.
4. Owner reviews proposed operating rules and the exact packet separately.
5. Operating-contract approval records a decision only and never posts, schedules, spends, sends, reserves, or writes operational state.
6. Public post/send/spend remains blocked unless its separate exact gate is approved.
7. Manual or controlled execution evidence is recorded.
8. Performance evidence informs future recommendations.

Source reference: `docs/05-ai/agents/beacon/BEACON_SCOPE.md`.

## Creative Studio Evaluation Lane

1. An authenticated owner admin submits an exact prompt, parameters, cost-estimate provenance, and source asset IDs plus SHA-256 hashes.
2. The service verifies source existence, hash integrity, and the latest effective owner public-use approval; missing, hashless, tampered, rejected, or archived sources fail closed.
3. Only the ElevenLabs and Happy Horse 1.0 identifiers are accepted, and their adapters return deterministic provider-disabled mock manifests without network, credential, source-transfer, or spend authority.
4. Job, source lineage, attempt, cost, mock variant, and review evidence are appended as structured records. Mock variants remain private in `beacon-raw-intake`, `needs_review`, and not campaign-selectable.
5. Brand, privacy, safety, animal/product fidelity, provider disclosure, evaluation, and owner public-use decisions are recorded separately by the server-bound authenticated owner identity.
6. Evaluation or public-use approval records evidence only. It cannot enable a provider, spend, post, schedule, send, campaign action, order, stock change, or farm lifecycle write.
