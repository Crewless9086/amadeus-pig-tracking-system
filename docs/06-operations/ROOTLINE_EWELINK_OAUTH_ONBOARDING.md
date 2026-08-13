# ROOTLINE eWeLink OAuth onboarding

Status: reviewed onboarding boundary; provider readback and B/C control remain disabled.

## Owner step

ROOTLINE generates one short-lived official eWeLink authorization URL from the
strict owner-admin route. Charl opens that URL privately, signs in to the
eWeLink account that owns device `100204e9bc`, and approves the provider's
combined read/control credential. Passwords, MFA values, authorization codes,
access tokens and refresh tokens must never be copied into chat or Telegram.

## Server boundary

- Exact callback: `https://amadeus-pig-tracking-system.onrender.com/api/rootline/provider/ewelink/oauth/callback`
- Start: `POST /api/rootline/provider/ewelink/oauth/start` (strict owner-admin session)
- Readiness: `GET /api/rootline/provider/ewelink/oauth/readiness` (strict owner-admin session)
- State and nonce are random, HMAC-bound, durable, single-use and expire after
  ten minutes so the owner can complete private login. This is not the code
  lifetime.
- CoolKit issues the callback authorization code and enforces its 30-second
  lifetime. The callback consumes state atomically and starts one synchronous
  exchange with a 15-second network timeout; the application never queues or
  retries a code. It has no provider-issued code timestamp from which to claim
  a second local age. A replay is rejected before any provider request.
- Only the allowlisted CoolKit regional API hosts are accepted.
- The callback performs the token exchange and exactly three read requests:
  family, owned device and current device status.
- The authorized account is pinned on first owner consent. Later account or
  device mismatches fail closed.
- Tokens are AES-GCM encrypted before append-only private persistence. Only
  expiry metadata, field names and digests are returned by the callback.
- Refresh-token generations are retained as encrypted append-only records;
  an expired access token is rotated once through CoolKit's signed
  `POST /v2/user/refresh` contract and the replacement access/refresh pair is
  encrypted before an atomic append. The provider-documented 30-day access and
  60-day refresh lifetimes are retained as expiry metadata. An expired refresh
  generation cannot enable readback; rotation preserves the same pinned
  account/device/region binding and performs zero device-control calls.

## Protected configuration

Required secret names are `EWELINK_CLIENT_ID`, `EWELINK_CLIENT_SECRET`,
`EWELINK_EXPECTED_DEVICE_ID`, `EWELINK_OAUTH_REDIRECT_URI`, and
`EWELINK_OAUTH_STATE_SECRET`. `EWELINK_EXPECTED_ACCOUNT_ID` may pin the expected
provider account before first consent. Values must exist only in the protected
environment and must not appear in logs, artifacts, database JSON, Telegram or
browser responses.

Both `EWELINK_READBACK_ENABLED` and `ROOTLINE_AUTONOMOUS_BC_ENABLED` must remain
false for onboarding. This implementation contains no provider control call.

## Revocation and rollback

Disable both activation flags, revoke the application grant in eWeLink, revoke
or rotate the client credential, and retain the encrypted generations only as
restricted audit evidence. No irrigation execution authority is derived from
an OAuth receipt. Provider readback and autonomous execution require separate
reviewed activation and acceptance proof.
