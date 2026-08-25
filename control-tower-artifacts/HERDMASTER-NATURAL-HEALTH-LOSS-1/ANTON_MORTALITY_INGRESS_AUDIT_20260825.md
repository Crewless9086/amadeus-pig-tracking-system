# Anton mortality ingress audit receipt - 2026-08-25

- Existing lineage: `HERDMASTER-NATURAL-HEALTH-LOSS-1 / OOM-INTAKE-SLICE-1`; no new mission or priority change.
- Original provider evidence: Telegram message `3926`, `2026-08-23T20:29:12Z`, `Vark nr 146 dood op 23 Aug 2026`.
- Original route: GateKeeper execution `66321` and backend relay `66322` succeeded. The backend returned `waiting_for_input`: `Which one do you mean: 23, 146?`, with zero writes.
- Canonical identity: tag 146 uniquely resolves to `PIG-2026-E58B`. It remains Active, on farm and in `PEN-012`, with zero lifecycle, observation, welfare and health/mortality claim rows.
- Historical root cause: the deployed resolver treated date day 23 as a second animal candidate. Existing PR1205 lineage repaired typed marker/date separation; the old message must not be replayed.
- Fresh continuity evidence: Telegram message `4028`, `2026-08-25T07:03:14Z`, contained the same text. GateKeeper execution `66636` failed at Google Sheets node `Get User Info` with HTTP 503 before backend routing. The live node had no retry, and no canonical/provider follow-up was created.
- Bounded repair: retry the exact authorization lookup at most five times with a two-second interval; remain fail-closed if unavailable. This creates no bypass, replay or farm effect.
- Acceptance still required: reviewed workflow deployment, a later genuine Anton report, fully Afrikaans preview, actor-bound confirmation, canonical mortality/welfare/readback and terminal-independent continuity.
- Owner action: none until reviewed workflow readiness is proven.
