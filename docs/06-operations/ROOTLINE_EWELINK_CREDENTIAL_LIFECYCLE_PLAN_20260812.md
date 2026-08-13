# ROOTLINE eWeLink Credential Lifecycle and Recovery Plan

## Status

Owner-approved preparation plan. No secret mutation, OAuth authorization, deployment, provider call or hardware action is authorized by this document.

## Incident truth

Production retained an encrypted eWeLink OAuth grant while `EWELINK_OAUTH_STATE_SECRET` was absent. The grant therefore became undecryptable. Enabling read-only authority correctly failed closed with `ewelink_token_decryption_failed`.

The original secret was not found in the approved workspace `.env` and ROOTLINE reported no protected recovery copy. A replacement secret cannot decrypt the existing grant. One new authorization is required unless the exact original value is recovered from an approved secret store.

## Required durable lifecycle

1. Generate the encryption/state secret directly into the protected production secret store before authorization starts.
2. Never print, log, transmit in chat or commit the value.
3. Deploy/restart with the exact secret loaded and prove presence without revealing it.
4. Create a one-time, expiring, account- and callback-bound OAuth state.
5. Reject missing, stale, mismatched or replayed state.
6. Exchange the authorization code once and encrypt the grant using the loaded secret.
7. Persist the encrypted grant and immutable authorization metadata atomically.
8. Immediately decrypt the stored envelope and perform a zero-command provider identity/readback check.
9. Declare authorization operational only after post-restart decryption and readback also succeed.
10. Retain the secret while any stored grant depends on it.
11. Rotate secret and grant together through an explicit migration; never rotate only one side.
12. Supersede undecryptable grants without deleting audit history.

## Recovery and monitoring

- Startup health must distinguish missing secret, missing grant, decryption failure, expired grant, provider authorization failure and readback-disabled state.
- Owner status may expose availability and last successful readback, never secret/token contents.
- A periodic read-only health check should detect failure before an irrigation or fertilizer decision requires the provider.
- Oom Sakkie/ROOTLINE should emit one concise actionable incident when material failure first occurs, remain silent when unchanged, and clear it after verified recovery.
- Do not ask the owner to repeat authorization more than once for the same unresolved systemic defect.
- The callback path must be deployed, healthy and actively observed before presenting the owner link.

## Authority separation

`EWELINK_READBACK_ENABLED=true` permits readback only. It must not imply:

- B/C autonomous authority;
- Mixer or Injection authority;
- Borehole authority;
- schedule, timer, scene or interlock mutation; or
- any ON/OFF command.

Each actuation class retains its separate reviewed flag and mission.

## Acceptance

- New protected secret exists in production before authorization.
- Charl uses one valid authorization link once.
- Callback consumes state once and rejects replay.
- Stored grant decrypts immediately and after a restart.
- Provider account/device identity matches the intended eWeLink installation.
- Zero-command readback proves expected devices/channels and OFF state.
- No hardware command, farm write or unrelated configuration change occurs.
- An exact replay creates no second grant or side effect.
- A future missing/mismatched secret produces an immediate clear incident rather than a silent operational blocker.

Only after this succeeds may ROOTLINE resume the separate Mixer commissioning and next eligible B/C acceptance missions.
