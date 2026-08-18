# CMQ-20260813-05 legacy portfolio classification

This source slice implements Charl's one approved classification of the exact 86-row legacy baseline. It is not a current-mission admission and grants no scheduling, recovery, release, dispatch or Shadow authority.

The sealed private action requires the controlling mission `CMQ-20260813-05`, baseline digest `b31ac806513d8ebd23350bde9f96984a58bf7dbc09f9ba385a35c268cfff5f8d`, and approved-set digest `159db3bf36483cfa9e3a81ad535ef2cf112e9c997fd525312226d651251ccc19`. The final approved counts are 49 `recovery_fragment`, 19 `test_evidence`, 11 `superseded`, and 7 `historical`; row 39's complete order-stream evidence is historical rather than revived work.

The Supabase transaction locks the portfolio, revalidates all identities and unchanged status/source/title/updated-at/event-count evidence, prevalidates every replay, then adds a separate `portfolio_classification` metadata dimension and one deterministic `portfolio_classified` evidence event per legacy mission. It does not update status, timestamps, existing metadata or old events. Exact replay is no-op; any different baseline, set or prior classification fails closed. Generic mission event APIs cannot create this event type.

Any classified legacy record is runtime-ineligible. This also keeps the old `pr_ready` row 85 non-runnable and unavailable to automatic resume, merge or release. CMQ-05 remains the sole bootstrap admission and remains non-runnable `WORKING`. No candidate mission is admitted by this change.

Candidate documentation after owner reconciliation: `UIQ-20260813-02` is excluded as `BUSINESS_COMPLETE`; `RMQ-20260813-04` remains a systemic `WORKING` journey with no owner retry before the full execution-family gate; `HMQ-20260813-05` is `EXTERNAL_HOLD` pending the next natural provider-confirmed morning brief, with no replay or manufactured event.
