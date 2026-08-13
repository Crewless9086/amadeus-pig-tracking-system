# Agentic Farm Runtime Phase 0 Dependency and Retirement Register

Status: active Phase 0 discovery register under the Agentic Farm Runtime Programme.

Snapshot: 2026-08-13. Owner: CORE. Scope: repository and tracked operational
evidence only. No workflow, provider, production configuration, secret, farm
record, Telegram route, customer system or hardware was mutated.

## Evidence levels

- **Documented fact:** asserted by tracked documentation or a committed export.
- **Runtime-loaded fact:** a deployed process or configuration was read and its
  loaded state proved. The dated snapshot below records loaded Render lineage,
  direct configuration-name presence and local Windows tasks/processes.
- **Provider-verified fact:** authoritative n8n, Render, Google, Telegram,
  Chatwoot or device-provider readback. The dated snapshot below records n8n,
  Render, Telegram and Chatwoot provider state.
- **Physical fact:** direct owner/site observation of physical equipment or
  effects. None was requested or claimed in this slice.

An export's `active` field is documented fact only. `unknown` means the export
omits that field. It must not be treated as disabled or enabled provider truth.

## Read-only provider/runtime snapshot — 2026-08-13

Observation window: `2026-08-13T08:26:38Z` to `2026-08-13T08:31:06Z`.
Credential values were never recorded. The primary repository supplied
configuration presence for n8n, Render, Chatwoot, Oom Sakkie Telegram and
CHARLIE Telegram; no separate SAM Telegram token was present.

### n8n provider truth

The n8n API returned 31 workflows. This is provider-verified active state, not
proof that every active workflow is safe, needed or producing business effects.

| Provider ID | Workflow | Provider active | Last updated (UTC) | Ownership evidence |
| --- | --- | ---: | --- | --- |
| `1VNdetSbgP0ffNyH` | `2.4.4 - Order Lookup Tool` | yes | 2026-05-19T02:41:00Z | callable only; no execution in latest 100 |
| `2LETWzde7lMDlMnl` | `ALERT - Sunsynk` | no | 2026-05-23T03:14:12Z | inactive schedule |
| `3gUUnTs94kXvq2Xl` | `1. Email Gatekeeper` | yes | 2026-02-11T19:30:03Z | Outlook trigger; not represented by a committed export |
| `4RTDP1ZlBWDdo6Jh` | `1.3 - SAM - Sales Agent - Media Tool` | yes | 2026-04-27T11:24:29Z | callable/manual; contradicts disabled suite doctrine |
| `6UscGE44eTfdLp1A` | `2.0 - OOM SAKKIE - Amadeus Assistant Agent` | yes | 2026-05-23T05:34:53Z | callable |
| `8b14lAqmyrD0LYZz` | `2.4.5 - Document Send Callback Handler` | yes | 2026-05-19T00:18:00Z | callable |
| `DoTVVGjcSsCZOyF1` | `1.6 - Daily Order Summary` | yes | 2026-05-10T14:28:33Z | active schedule/manual trigger |
| `GwWZueB0iyonpscl` | `2.4.1 - Test Caller` | no | 2026-05-19T00:17:06Z | inactive manual trigger |
| `I4D76Gb9ddGFhSP5` | `ALERT - Weather Forecast` | no | 2026-05-23T01:08:58Z | inactive schedule |
| `L4c34rFmN0kUJvWc` | `2.1 - Amadeus Weather Sub-Agent` | yes | 2026-05-22T05:13:21Z | callable |
| `MuEyz3dNaJFTSg7t` | `1.4 - Outbound Order Notification` | yes | 2026-05-09T20:07:56Z | active webhook |
| `QTWhdK6i8DirCPCZ` | `1.5 - Outbound Document Delivery` | yes | 2026-05-10T06:01:48Z | active webhook |
| `T8LLCAtYDLNRPoRx` | `2.4 - Amadeus Orders Sub Agent` | yes | 2026-05-19T00:16:20Z | callable |
| `TlKy9kUgJJE0msU4` | `2.0B - Oom Sakkie Backend Read-Only Relay` | yes | 2026-08-02T16:42:16Z | execution `64125`, success at 06:30:50Z |
| `UNwNmx0TwtFf8mjo` | `2.3.1 - Build Daily Irrigation Plan` | yes | 2026-03-12T16:21:53Z | execution `64055`, success at 22:05:53Z |
| `V73HaIqVpzv44SFc` | `1.0 - SAM - Sales Agent - Chatwoot` | no | 2026-06-16T01:34:56Z | inactive webhook |
| `YDRs6fwde7MzPYn7` | `1.2 - Amadeus Order Steward` | yes | 2026-05-17T05:43:28Z | callable/manual |
| `aij6CO9zokC3IsZY` | `Capture Telegram IDs` | no | 2026-05-19T00:09:22Z | inactive; not represented by a committed export |
| `dAz5VSX9VZaXVTN8` | `1.1 - SAM - Sales Agent – Escalation Telegram` | yes | 2026-04-29T20:29:42Z | active Telegram trigger |
| `f6oPLsaolGH4pMKC` | `2.3.2 - Run Irrigation Controller` | no | 2026-03-12T18:30:00Z | inactive schedule |
| `g0ajlm9gBp7J72Jn` | `ALERT - Local Weather Station` | no | 2026-05-23T01:09:03Z | inactive schedule |
| `jIRPu33UOFCbk2Gx` | `ALERT - Power Backend Delivery` | yes | 2026-08-05T06:36:59Z | 48/100 recent executions; latest `64139` success at 08:15:43Z |
| `k4XVMoJ1hK09PIvT` | `2.4.3 - Order Approval Request Webhook` | no | 2026-05-19T00:17:03Z | inactive webhook |
| `kd5wrJEgBfUNNxnb` | `ALERT - Farm Attention Digest` | yes | 2026-05-30T20:04:01Z | execution `64053`, success at 22:00:40Z |
| `leo7eCFlo2Ilbvk7` | `ALERT - Weather Backend Delivery` | yes | 2026-05-23T00:51:16Z | 48/100 recent executions; latest `64138` success at 08:15:16Z |
| `oyGH9ynKZ38IQY48` | `2.3.3 - Irrigation Status Tool` | yes | 2026-05-23T05:25:02Z | callable |
| `rujGugAcNxmZlv1t` | `SAM Livestock - Autonomous Inbox Operator` | no | 2026-07-29T20:44:50Z | inactive schedule |
| `s8QaxmqT69Z5mhvE` | `2 - The GateKeeper` | yes | 2026-08-12T14:18:24Z | execution `64124`, success at 06:30:48Z |
| `tKVKoCcxhT7CAydT` | `2.2 - Amadeus Sunsynk Sub-Agent` | yes | 2026-05-22T01:09:41Z | callable |
| `vx1lV8aFCG28KSIN` | `2.1.1 - Amadeus Forecast Tool` | no | 2026-05-19T03:53:23Z | inactive callable workflow |
| `y05APXoAq3ejq1gd` | `Research Expert` | no | 2026-05-19T00:09:19Z | inactive; not represented by a committed export |

Provider inventory did not contain committed exports `2.4.2 - Orders Approval
Callback Handler`, `SAM Livestock - Continuous Chatwoot Inbound`, or the three
newer repository `ALERT` exports under those exact names. Absence is not an
inactive-state claim. The provider-only active `1. Email Gatekeeper` is
`retain-temporarily`: disabling it may lose business email intake; CORE owns
discovery, rollback is provider re-enable after sole-trigger verification, and
retirement requires an owner-mapped canonical email adapter with fresh receipt,
readback and zero lost-message proof. Provider-only inactive utilities remain
`historical-evidence` pending export/retention reconciliation.

### Render provider and loaded-lineage truth

| Provider ID | Service | Type / state | Schedule | Command | Configuration presence and lineage |
| --- | --- | --- | --- | --- | --- |
| `srv-d6sijjkhg0os73f7regg` | `amadeus-pig-tracking-system` | web service / not suspended | continuous | provider-default start/build | 20 direct env keys; SAM Meat webhook/autoreply, SAM sales cohort/autonomy, Telegram owner-review and telemetry-ingest names present. Last proven live deploy `dep-d9unuilg1s2s73e3l4fg` at merge `660bf679…`; a newer deploy was in progress during observation and is not claimed loaded. |
| `srv-d25u8ic9c44c73efo920` | `amadeus-backend` | web service / not suspended | continuous | provider-default start/build | two direct env keys; stale service updated 2025-12-13; ownership remains Unknown pending domain confirmation. |
| `crn-d8a8q56l51nc73cif04g` | `amadeus-telemetry-daily-rollups` | cron / not suspended | `15 22 * * *` | `python scripts/telemetry_daily_rollup_plan.py --previous-day --apply` | `DATABASE_URL` name present; deploy `dep-d9uo13e7bikc73b2v5c0` live at `1d98850d…`. |
| `crn-d5cc6sjuibrs73e8pu6g` | `amadeus-localweatherstation-logger` | cron / not suspended | `*/5 * * * *` | `python main.py` | telemetry-ingest key name present; last successful run field loaded; live deploy `dep-d87s7eh9rddc73atie5g`. |
| `crn-d5cb74juibrs73djmn6g` | `amadeus-weatherstation-logger` | cron / suspended | `*/5 * * * *` | `.venv/bin/python main.py` | six config names; historical Elixir-runtime service, live artifact but provider-suspended. |
| `crn-d5a0plhr0fns73837e8g` | `amadeus-forecast-logger` | cron / not suspended | `0 4,16 * * *` | `python main.py` | telemetry-ingest key name present; live deploy `dep-d9ndpj9t0dsc7390slmg`. |
| `crn-d55dlp6mcj7s73f9smtg` | `amadeus-sunsynk-logger` | cron / not suspended | `*/5 * * * *` | `python main.py` | telemetry-ingest key name present; last successful run field loaded; live deploy `dep-d87od8gjs32c73edh9b0`. |

No value was read into this document. Disabling any enabled telemetry cron can
make its evidence stale; replacements, rollback and retirement proofs remain the
per-service obligations already recorded below. The suspended
`amadeus-weatherstation-logger` is the first Render historical-evidence
candidate, but this mission did not retire it.

### Webhook and callback ownership

Telegram provider `getWebhookInfo` returned zero pending updates and no current
error for both configured bots:

- CHARLIE -> Render host, `/api/charlie/build-relay/telegram/webhook`;
- Oom Sakkie -> n8n host, `/webhook/b419b4e9-adf4-40a3-b582-a3e4ca1f3488/webhook`.

Chatwoot provider returned three account webhooks, all owned by the Render host:

- `17850`, `message_updated` ->
  `/api/sales/channels/chatwoot/meat-documents/delivery-status`;
- `18495`, `message_created` ->
  `/api/sales/channels/chatwoot/sam-live-stock/inbound`;
- `17758`, `message_created` ->
  `/api/sales/channels/chatwoot/sam-meat/inbound`.

Therefore `1.0` is not the current Chatwoot inbound owner, while the n8n
GateKeeper remains the current Oom Sakkie Telegram owner. Backend callback
routes that are not registered at the provider are runtime-loaded capability,
not provider-active ownership.

### Local Windows runtime truth

At `2026-08-13T08:29:31Z`:

| Task | Loaded state | Last result | Process ownership |
| --- | --- | ---: | --- |
| `CHARLIE Always-On Executive` | Disabled | `267014` | no matching executive watchdog process found |
| `CHARLIE CORE Runner Watchdog` | Disabled | `0` | no matching runner watchdog process found |
| `CHARLIE Telegram Relay` | Disabled | `2` | one relay parent/child `pythonw.exe` chain was loaded (PIDs 9920/10996) |
| `CHARLIE Telegram Relay Watchdog` | Ready; last run 08:28:54Z, next 08:30:53Z | `0` | periodic watchdog owns the loaded relay chain |

The ready watchdog plus disabled direct relay task is one logical local relay
owner, not two independent relays. Telegram provider truth shows CHARLIE webhook
ownership on Render, so the loaded polling relay is a competing transport even
if its code is expected to self-contain in webhook mode. The first genuinely
duplicated scheduler/transport candidate for later reversible retirement is the
`CHARLIE Telegram Relay Watchdog`, not a production farm scheduler. Do not
disable it until one fresh CHARLIE owner callback is provider-confirmed through
Render, process inspection proves the polling child is unnecessary, and the
documented task re-enable command is verified as rollback.

### Physical facts

None. No device, pump, valve, farm condition, customer effect or on-site state
was observed. Provider and process metadata cannot establish physical truth.

## Owner-visible dependency and retirement register

| Component or family | Exported/discovered state | Classification | Current dependency and disable impact | Canonical replacement and owner | Dependencies / rollback | Exact retirement proof |
| --- | --- | --- | --- | --- | --- | --- |
| n8n `1.0 - SAM - Sales Agent - Chatwoot` | `active=true`; Chatwoot webhook; five Sheets nodes; Telegram node | migrate | Legacy inbound sales, context, escalation and order handoff. Disabling may stop the legacy customer path. | SAM Customer Front Door plus SAM Livestock runtime; owner SAM/CORE | Chatwoot identity/history, canonical stock/pricing, backend order gates. Roll back by re-enabling only after provider state and duplicate webhook ownership are checked. | Five fresh eligible conversations traverse the canonical runtime with provider-confirmed replies/read state, no Sheets-first write and zero duplicate response while `1.0` is disabled through the observation window. |
| n8n `1.1 - SAM - Sales Agent - Escalation Telegram` | `active=true`; Telegram trigger; three Sheets nodes | migrate | Human escalation reply bridge; disabling may strand legacy escalation tickets/replies. | Consolidated Oom Sakkie protected-exception flow; owner SAM/Oom Sakkie | Exact customer/conversation/ticket mapping. Re-enable only if canonical exception delivery/readback fails without duplicate Telegram polling. | Open escalation backlog reconciled; one protected exception round-trip is provider-confirmed through the canonical rail; zero active tickets depend on the sheet bridge. |
| n8n `1.2 - Amadeus Order Steward` | `active=true`; execute-workflow trigger | retain-temporarily | Calls backend order APIs for legacy `1.0`; disabling breaks legacy order actions. | Typed backend order adapter invoked by canonical SAM action; owner SAM/CORE | Backend authority/idempotency and order readback. Keep callable until `1.0` migration. | Every called action has contract/replay tests and provider/canonical readback outside n8n; no enabled caller remains. |
| n8n `1.3 - SAM - Sales Agent - Media Tool` | export says `active=true`; suite documentation says disabled/unapproved | quarantine | Contradictory state; enabling could send unapproved/repeated customer media. | Governed SAM/BEACON media adapter; owner SAM/BEACON | Media approval, contact identity, offset/idempotency. Rollback is remain disabled. | Provider state confirms disabled; replacement proves approved media selection, one send/readback and zero-effect replay. |
| n8n `1.4 - Outbound Order Notification` | `active=unknown`; backend webhook | retain-temporarily | Sends backend-approved order outcome text; disabling may suppress customer approval/rejection notices. | Typed Chatwoot delivery outbox; owner SAM/CORE | `ORDER_NOTIFICATION_WEBHOOK_URL`, backend event identity, Chatwoot receipt. | Backend outbox proves one approval and rejection delivery/readback, replay silence, then provider confirms n8n webhook disabled with no pending events. |
| n8n `1.5 - Outbound Document Delivery` | `active=unknown`; backend webhook | retain-temporarily | Downloads Drive PDF and sends via Chatwoot; disabling may block quote/invoice delivery. | Typed document delivery adapter/outbox; owner SAM/CORE | Document registry, Drive access, Chatwoot attachment receipt. | One governed document delivery has exact provider receipt and replay silence outside n8n; pending delivery queue is empty before disable. |
| n8n `1.6 - Daily Order Summary` | `active=unknown`; scheduled Telegram report | migrate | Duplicate scheduled owner reporting candidate; disabling may remove the legacy daily order summary. | Oom Sakkie consolidated daily manager schedule; owner Oom Sakkie/CORE | Canonical order summary and provider delivery claim. | Consolidated brief includes supported order state on two consecutive due days; provider confirms one message/day and `1.6` disabled. |
| n8n `2 - The GateKeeper` | `active=true`; Telegram trigger; one Sheets node | migrate | Current legacy Telegram ingress/routing; disabling without webhook cutover can remove owner intake. | Authenticated Oom Sakkie direct webhook and unified intake; owner Oom Sakkie/CORE | Sole Telegram webhook ownership, secret gate, callback compatibility, rollback URL. | Provider `getWebhookInfo` identifies canonical endpoint; acceptance covers text/media/callback; zero duplicate consumers; reversible disable observation passes. |
| n8n `2.0 - OOM SAKKIE` | `active=true`; callable; Telegram send | migrate | Legacy assistant/tool dispatch; disabling may break GateKeeper replies/tools. | Oom Sakkie semantic front door plus typed specialist adapters; owner Oom Sakkie | GateKeeper migration and provider delivery/readback. | Representative weather, herd, sales and manager requests complete via unified runtime; no enabled workflow references `2.0`. |
| n8n `2.0B - Backend Read-Only Relay` | `active=false` | historical-evidence | Inactive relay template; disabling has no expected effect. | Existing direct webhook/backend adapter; owner Oom Sakkie | Retain contract lessons only. | Provider confirms inactive and repository references it only as evidence/test; archive classification recorded. |
| n8n `2.1`, `2.1.1`, `2.2`, `2.3.3` read tools | exports: `2.1/2.1.1/2.2 active=true`; `2.3.3 false` | migrate | Weather, forecast, power and irrigation status tools; disabling active callers can break owner questions. | Typed backend specialist reads through Oom Sakkie; owner ROOTLINE/Oom Sakkie | Canonical telemetry endpoints, freshness/provenance, caller inventory. | Each read family passes channel-equivalence and deployed readback; provider confirms no enabled caller/workflow dependency. |
| n8n `2.3.1 - Build Daily Irrigation Plan` | `active=true`; 00:05 schedule; seven Sheets nodes | migrate | Builds legacy daily plan; disabling may remove planned irrigation data used by status/control. | ROOTLINE canonical Supabase plan/scheduler; owner ROOTLINE/CORE | Zone/settings evidence, daily identity, no hardware authority inherited. | Two due-day canonical plans reconcile; all consumers read Supabase; Sheets unavailable test passes; provider schedule disabled. |
| n8n `2.3.2 - Run Irrigation Controller` | `active=false`; scheduled; eleven Sheets nodes | quarantine | Hardware-capable legacy controller. Enabling risks duplicate/unsafe execution. | ROOTLINE governed execution coordinator; owner ROOTLINE | Explicit device authority, provider OFF/readback, interlocks. Rollback is remain disabled. | Provider confirms inactive; no external scheduler calls it; commissioned replacement proves bounded execution, native auto-OFF and replay guard before historical classification. |
| n8n `2.4`, `2.4.3`, `2.4.4`, `2.4.5` order approval/lookup/callback family | exports `active=true` | retain-temporarily | Legacy protected approval, lookup and quote-send callback path; disabling may strand approvals or document sends. | Typed Oom Sakkie/SAM protected-action adapters and backend outbox; owner SAM/Oom Sakkie/CORE | Exact order, owner authority, callback idempotency, Chatwoot receipt. | Pending approvals/callbacks empty; one approve/reject/send/cancel family acceptance has canonical and provider readback; no enabled caller remains. |
| n8n `2.4.1 Test Caller`, `2.4.2 Orders Approval Callback Handler` | `active=false` | historical-evidence | Test/older callback paths; no expected active impact, but `2.4.2` would compete for Telegram updates if enabled. | Current protected callback family; owner CORE | Provider inactive proof. | Provider confirms disabled and no enabled workflow references them; archive banner/source-map classification recorded. |
| n8n `ALERT - Farm Attention Digest`, `ALERT - Power Backend Delivery`, `ALERT - Weather Backend Delivery` | exports `active=false`; schedules | quarantine | Duplicate scheduler candidates. Enabling could duplicate owner alerts/reassessments. | Durable Oom Sakkie manager/reassessment schedules; owner Oom Sakkie/ROOTLINE | Canonical claims, one Telegram delivery owner. | Provider confirms all disabled; canonical schedules prove two due windows with one claim/message and replay silence. |
| n8n `SAM Livestock - Continuous Chatwoot Inbound`, `Autonomous Inbox Operator` | exports `active=false`; webhook and every-minute schedule | quarantine | Competing SAM webhook/poller; enabling risks duplicate customer sends. | One durable SAM inbound adapter and worker; owner SAM/CORE | Sole Chatwoot webhook, conversation claims, provider read state. | Provider confirms both disabled; canonical lane processes five customers continuously with zero duplicate sends. |
| Google Sheets farm master/write family | Backend code reads/writes `PIG_MASTER`, `LITTERS`, `WEIGHT_LOG`, `MEDICAL_LOG`, `MATING_LOG`, `LOCATION_HISTORY`; Supabase-first paths coexist with fallbacks | migrate | Disabling Sheets can still break fallback reads/writes and formula-dependent screens. | Supabase domain events/projections; owner HERDMASTER/CORE | Per-domain reconciliation, Unknown preservation, downstream export. | For each domain: forced Sheets-unavailable acceptance, canonical write/readback/replay, projection parity, no fallback invocation, rollback export retained. |
| Google Sheets order/sales write family | Backend reads/writes order master/lines/status/documents/intake and pig reservation effects | migrate | Disabling may break legacy order lifecycle, reservations, pricing and reports. | Supabase order, reservation, pricing and document ledgers; owner SAM/CORE | Atomic reservation, pricing authority, document/outbox receipts. | Complete quote-to-order lifecycle succeeds with Sheets unavailable; reconciliation is zero-diff or explicitly quarantined; no code write path remains. |
| Google Sheets formula/read family | `PIG_OVERVIEW`, `MATING_OVERVIEW`, `LITTER_OVERVIEW`, `ORDER_OVERVIEW`, sales availability/detail/summary/totals | migrate | Current reports and legacy AI/n8n reads may depend on formulas. | Tested Supabase views/projections; domain owners/CORE | Formula parity fixtures and freshness semantics. | Every caller points to canonical view; forced Sheets-unavailable read suite passes; formula deltas resolved or quarantined. |
| Google Sheets registers/settings | `PEN_REGISTER`, `PRODUCT_REGISTER`, `USERS`, `SALES_PRICING`, `SYSTEM_SETTINGS` retain admin/manual ownership | retain-temporarily | Removing early can break reference, pricing, access or document settings. | Governed Supabase reference tables/admin rails; owner relevant domain/CORE | Owner-approved edit authority and audit. | Named replacement has audited edit/readback, export and rollback; all runtime callers cut over before Sheets becomes downstream-only. |
| Google Sheets irrigation family | `modules/telemetry/irrigation_service.py`, `scripts/irrigation_import_dry_run.py` and `scripts/irrigation_daily_sync.py` read zone, daily-plan, state and log tabs in a named spreadsheet; the sync script can project data | migrate | Disabling Sheets can break legacy irrigation status/plan reads and explicit sync/import tooling; it must not be assumed safe because the n8n controller export is disabled. | ROOTLINE Supabase plan, execution and status projections; owner ROOTLINE/CORE | Exact tab/caller inventory, timezone/date parity, source provenance and dry-run/export rollback. | Every runtime caller uses canonical projections with Sheets unavailable; sync/import tooling is historical or export-only; two daily plans/status readbacks reconcile before the Sheets path is disabled. |
| Local CHARLIE Telegram polling relay/watchdog/Windows task | Scripts and docs show polling relay, watchdog and optional scheduled task; webhook mode is intended to exclude polling | quarantine | If simultaneously active with webhook, can compete for Telegram updates; disabling a genuinely active sole transport would remove CORE owner access. | Hosted authenticated CHARLIE webhook; owner CORE | Provider webhook truth, process/task inventory, owner allowlist. | Telegram provider shows hosted webhook; OS task/process readback shows polling absent/disabled; one owner status callback succeeds; rollback command documented. |
| Local CHARLIE executive watchdog/task | `scripts/install_charlie_executive_watchdog.ps1` and `scripts/charlie_executive_watchdog.py` define a distinct always-on executive watchdog | retain-temporarily | Disabling an active task can stop executive recovery/follow-up supervision; duplicate watchdogs can race the same mission state. | One supervised CORE executive process with durable leases; owner CORE | Windows task/process identity, mission store and heartbeat. | OS readback proves one configured task/process; restart recovery resumes one disposable mission without duplicate command; rollback task definition retained. |
| Local CORE runner watchdog/promotion task | `scripts/install_charlie_runner_watchdog.ps1`, `scripts/promote_charlie_runtime.ps1`, runner/supervisor code and registered runner worktrees define the build-execution plane | retain-temporarily | Stopping an active runner pauses software missions but must not affect farm runtime; duplicate tasks can execute the same mission. | Portable supervised development runtime; owner CORE | Mission queue, claim/lease, promoted source identity and recovery truth. | OS/task/process readback proves singular ownership; restart recovery completes a disposable governed mission; no operational farm route depends on it. |
| CHARLIE build-relay webhook and notification scripts | `modules/charlie/build_relay.py`, `scripts/charlie_build_relay_webhook.py` and `scripts/build_relay_notify.py` expose hosted webhook control and optional notifications | migrate | Disabling a loaded webhook can remove owner mission control; enabling legacy notification/polling aliases can duplicate messages. | CHARLIE private executive webhook/outbox on the canonical mission store; owner CORE | Telegram webhook/provider truth, owner allowlist, inbound idempotency and notification mode. | Provider endpoint and loaded route match canonical runtime; callback/notification readback succeeds once; legacy aliases receive zero events during rollback window. |
| Oom Sakkie morning runtime and reassessment scheduler | Backend-owned date-stable morning claim exists; reassessment contract exists; invocation owner needs provider/runtime confirmation | retain-temporarily | Disabling deployed invocation can remove daily brief/reassessment; duplicate n8n schedules can duplicate messages. | Durable agent runtime scheduler with canonical claims; owner Oom Sakkie/CORE | Process start command, timezone, claim store, provider outbox. | Two consecutive due windows survive restart with exactly one provider message/outcome; n8n duplicates remain disabled. |
| Render Sunsynk logger cron | `TESTING_CHECKLIST.md` records a dashboard-managed Sunsynk logger schedule/command; no Render Blueprint is present | retain-temporarily | Disabling may stop power telemetry ingestion and make ROOTLINE evidence stale. | ROOTLINE durable telemetry ingestion schedule; owner ROOTLINE/CORE | Exact Render job/command/timezone, Sunsynk adapter and canonical ingest receipt. | Two scheduled ingestions have fresh canonical timestamps/readback after restart; Render confirms old job disabled through one rollback window. |
| Render `amadeus-localweatherstation-logger` cron | `SUPABASE_TELEMETRY_PLAN.md` names the local-weather-station logger; testing evidence records cron deployment steps | retain-temporarily | Disabling may stop local observation refresh and make current weather evidence stale. | ROOTLINE durable local-weather ingestion schedule; owner ROOTLINE/CORE | Exact Render command/timezone, station adapter and freshness policy. | Two observation windows populate canonical evidence with freshness/readback; Render confirms this job alone disabled through rollback window. |
| Render `amadeus-forecast-logger` cron | `SUPABASE_TELEMETRY_PLAN.md` names the forecast logger; testing evidence records forecast cron deployment/manual run | retain-temporarily | Disabling may stop forecast refresh and downstream weather alerts/advice while local observations continue. | ROOTLINE durable forecast ingestion schedule; owner ROOTLINE/CORE | Exact Render command/timezone, forecast provider and freshness policy. | Two forecast windows populate canonical evidence with freshness/readback; Render confirms this job disabled and no n8n forecast duplicate enabled. |
| Render `amadeus-telemetry-daily-rollups` cron | `TESTING_CHECKLIST.md` records the named dashboard-managed daily-rollup job and command; no Blueprint source owns it | retain-temporarily | Disabling may stop daily telemetry aggregates used by reports/advice. | Versioned durable rollup schedule in runtime/Farm Node packaging; owner ROOTLINE/CORE | `DATABASE_URL` presence (not value), rollup idempotency and date boundary. | Two due-day rollups and restart replay produce one canonical aggregate/day; Render confirms legacy cron disabled during observation. |
| Backend/provider callbacks | Chatwoot inbound, order notification, document delivery, order approval, Oom Sakkie Telegram direct webhook, CHARLIE Telegram webhook | migrate | Incorrect disable/cutover can lose customer/owner intake or delivery callbacks. | Typed adapters on unified intake/outbox with sole endpoint ownership; owner domain/CORE | Provider endpoint truth, secrets retained, idempotency and correlation. | Each provider reports the canonical endpoint; fresh bounded acceptance and authoritative readback pass; legacy endpoint receives zero events through rollback window. |
| SAM Livestock provider webhook path | `modules/sales/sam_live_stock_runtime.py` and sales transaction routes expose livestock inbound/provider lifecycle paths | migrate | Incorrect disable or duplicate registration can lose or double-send livestock customer responses. | Unified SAM inbound adapter, conversation claim and Chatwoot outbox; owner SAM Livestock/CORE | Exact Chatwoot inbox/webhook, conversation chronology, send/read-state receipt. | Five fresh eligible conversations have one provider-confirmed response/read projection each; provider reports one canonical endpoint and legacy receives zero events. |
| SAM Meat provider webhook path | `modules/sales/sam_meat_runtime.py` and `modules/sales/sales_transaction_routes.py` expose meat inbound/provider lifecycle paths | migrate | Incorrect cutover can lose meat enquiries, duplicate customer sends or detach sales-transaction state. | Unified SAM Customer Front Door/Meat adapter and outbox; owner SAM Meat/CORE | Inbox identity, transaction claim, pricing/stock evidence and provider receipt. | Representative greeting-to-meat and follow-up journeys complete once with provider readback; old endpoint has zero traffic during rollback window. |
| Meat document delivery-status callback | `modules/sales/meat_documents.py` and sales transaction routes expose document provider delivery-status handling | retain-temporarily | Disabling may leave quote/invoice delivery status Unknown or cause unsafe retries. | Canonical document outbox/status adapter; owner SAM Meat/CORE | Document/message identity, provider status chronology and replay claim. | One success and one failure callback update exact canonical document status once; replay is zero-effect; provider reports canonical callback URL before legacy disable. |
| ROOTLINE eWeLink OAuth callback | `modules/telemetry/telemetry_routes.py` exposes `/rootline/provider/ewelink/oauth/callback`, completing provider authorization and token persistence | retain-temporarily | Disabling during authorization prevents ROOTLINE eWeLink credential completion; an incorrect duplicate callback can bind the wrong state or token lineage. | Typed ROOTLINE provider-auth adapter on the canonical secret/configuration boundary; owner ROOTLINE/CORE | Exact redirect URI, nonce/state validation, protected token store and no token values in evidence. | Provider configuration reports the canonical redirect URI; one bounded authorization completes with state validation and protected token-presence readback; rollback URI and credential revocation path are documented before legacy retirement. |

## Contradictory document classifications

| Document | Phase 0 classification | Discovery action |
| --- | --- | --- |
| `docs/01-architecture/SYSTEM_ARCHITECTURE.md` | `historical` | Banner now names the programme, useful legacy evidence, prohibited assumptions, CORE and exact proof. Preserve file. |
| `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md` | `historical` | Banner prohibits its old n8n/Sheets architecture from governing review. Preserve packets as evidence. |
| `docs/04-n8n/WORKFLOW_MAP.md`, `WORKFLOW_RULES.md`, `DATA_FLOW.md`, `NODE_RESPONSIBILITIES.md`, `DO_NOT_CHANGE.md` | `transitional` | Use only to understand/cut over discovered legacy dependencies; programme and current source maps govern new work. |
| `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`, `DATABASE_SCALING_PLAN.md` | `transitional` | Statements retaining Sheets as live truth are migration history unless a current code path in this register proves a narrower dependency. |
| `docs/00-start-here/CURRENT_STATE.md` and older operational evidence logs | `active evidence`, not architecture authority | Preserve dated runtime evidence; current provider/runtime truth must refresh state claims before retirement actions. |

## Prioritized next three implementation slices

1. **Provider/runtime truth snapshot:** read-only n8n active workflow inventory,
   Render service/cron commands and schedules, Telegram/Chatwoot webhook owners,
   and local task/process inventory. Store identities and timestamps, never
   secret values. This converts the largest Unknowns into provider/runtime fact.
2. **Scheduler singularity:** bind the Oom Sakkie morning brief and ROOTLINE
   reassessments to one durable scheduler/claim/outbox owner, prove restart and
   two due windows, then disable only proven duplicate n8n/Render triggers behind
   reversible gates.
3. **Canonical farm write slice:** choose grouped weights/movements as the first
   representative action; prove browser/Telegram parity, Supabase-first atomic
   event/readback/replay and Sheets-unavailable operation, then make Sheets a
   downstream export for that slice.

## Phase 0 completion boundary

This register is reviewable discovery, not retirement authorization. Phase 0
can close only after the provider/runtime truth snapshot fills the Unknowns and
every retained active dependency has a named owner, replacement, rollback and
provider-backed retirement proof. No component listed here may be disabled from
this document alone.
