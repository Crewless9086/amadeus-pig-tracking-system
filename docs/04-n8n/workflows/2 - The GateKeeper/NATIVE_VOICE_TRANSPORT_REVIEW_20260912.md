# Native voice transport review candidate — 12 September 2026

The published GateKeeper rejects a native Telegram voice note before the backend: its media classifier returns `media_rejected`, and that switch output has no target. The published 2.0B text relay also rejects an empty text field. For typed replies, that relay drops `reply_to_message.message_id`, removing the exact question/card reference.

The read-only inspection matched Telegram's registered webhook to GateKeeper `s8QaxmqT69Z5mhvE`, published version `00c44771-9a6c-4a4e-bcb4-087a0502908e`. It inspected 2.0B `TlKy9kUgJJE0msU4`, published version `b90f2f4d-399b-4d1d-beb2-eb28551105bb`. Both returned their active-version node bodies. An offline JavaScript probe reproduced the defects using synthetic owner and Afrikaans Dad envelopes; it did not execute either cloud workflow or recognize speech.

[The exact patch and inverse values](NATIVE_VOICE_TRANSPORT_PATCH_20260912.json) contain four field edits across those two workflows:

- After the existing authorization branch, a native private voice envelope gets a `family_native_voice` route. The existing raw-update HTTP node forwards it unchanged to `/api/oom-sakkie/channels/telegram/message`. Backend family identity, provenance, audio bounds and transcription checks remain authoritative.
- One switch rule and one corresponding connection use that existing HTTP node. Existing text, photo, album, callback, denial and reply-delivery behavior remains in its current branches. There is no additional trigger, credential, sender, transcription service or automatic retry.
- The typed 2.0B normalizer retains only a valid positive safe-integer native reply message ID. Malformed reply metadata fails closed. The native voice route carries the original full envelope, so the text relay does not manufacture a transcript or its provenance.

The backend voice successor must first be separately reviewed, approved, deployed and verified. Candidate `77227a67` and the currently deployed web do not have that adapter. Neither this patch nor the backend successor has production approval. Apply only the named field edits through the existing GateKeeper UI workflow after approval and fresh comparison of the published versions, exact before values, security branch and HTTP transport. The older repository workflow exports are preserved and must not replace current live workflows.

Each edit records exact before/after values and SHA-256. Reverse an edit only when its current field still matches the recorded after value, restoring its exact before value while preserving unrelated changes. A mismatch requires a newly reviewed inverse. Reversal restores the earlier transport behavior and does not undo a saved farm operation.

Local validation: `python -m unittest tests.test_oom_sakkie_native_voice_transport -v`. These tests execute the proposed Code-node bodies in a network-free Node VM and verify routing, envelope/card identity, malformed inputs, unchanged branches and reversible field identities. They are not hosted n8n execution, actual speech recognition or live Telegram acceptance.
