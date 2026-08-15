# Oom Sakkie generic relay provider chronology correction

## Incident

Authenticated Telegram 3174 reached GateKeeper execution 61883 and relay 61884. Normalization succeeded, but the relay flattened text/user/chat and discarded provider message identity and timestamp from `gateway_payload`. The deployed backend correctly returned `health_loss_provider_identity_required` (HTTP 409), wrote no farm fact, and delivered one visible systemic exception as Telegram 3175.

## Source correction

The existing `2.0B - Oom Sakkie Backend Read-Only Relay` now forwards the authenticated GateKeeper message as the backend's native Telegram envelope: exact message ID, provider epoch, text, owner, private chat. All authority-bearing fields come from `raw_update.message`: text/caption, sender, chat, private-chat type, message ID and provider date. Flat fields are equality cross-checks only; raw absence, malformed evidence or any substitution fails closed before HTTP with zero send/write authority. No bot, trigger, router, workflow family, specialist route or send path is added.

## Recovery boundary

After reviewed normal merge, exact-merge CI and exact deployment, update only the existing relay workflow from the committed export. Then recover exact message 3174 under a distinct guard without replaying 3169/3171/3172/3174 through GateKeeper. Bind it to mission `OOM-HERDMASTER-CE45B85C51356B77E087B099` and card 3171, require zero farm writes, and edit the existing card to the consolidated preview. Telegram 3175 remains immutable systemic-exception evidence.

Charl's supported observations at provider epoch 1785673203: standing yes, moving yes, drinking yes, breathing appears normal. Earlier lack of appetite remains unresolved. Diagnosis, suspected cause, treatment and veterinary evidence remain Unknown/none reported. The preview must ask at most one genuinely missing appetite-monitoring question and require exact confirmation before the governed writer.

## Verification

- Provider chronology and sandbox tests: 9 passed, 35 subtests.
- Existing relay contract check: passed.
- Source workflow remains inactive, contains no Telegram trigger/send node, and preserves approved URL/credential policy.
