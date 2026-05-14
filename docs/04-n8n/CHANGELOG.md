# n8n Changelog

## Purpose

Tracks approved n8n workflow documentation and behavior decisions.

## Change Types

- `DOCS`: documentation-only update
- `FIX`: behavior fix
- `IMPROVEMENT`: existing behavior improvement
- `ADD`: new workflow/node/feature
- `REFACTOR`: structure change without intended behavior change
- `REMOVE`: deleted workflow/node/behavior

## Current Entries

### 2026-05-13 - Phase 5.9 intake naming and attribute cleanup start

Type: `REFACTOR`

**Summary:** Started the Phase 5.9 cleanup now that intake-driven create/quote/send is live-verified.

**Behavior:** No intended customer-facing behavior change. `1.0` runtime intake fields and nodes were renamed from shadow naming to primary intake naming. Chatwoot order-context write bodies now prefer the current steward/result item before falling back to existing Chatwoot attributes. `1.2 Code - Format Create With Lines Result` now echoes `payment_method` and `collection_location`, so the create/generate/send path can preserve `payment_method` in Chatwoot after a successful one-turn quote flow.

**Docs:** `WORKFLOW_RULES.md`, `DATA_FLOW.md`, and `CHATWOOT_ATTRIBUTES.md` now document `send_quote` pending action and live `generate_quote` / `send_latest_quote` steward actions.

**Verification:** `1.0` and `1.2` workflow JSON parse successfully, all Code-node JavaScript compiles, `1.0` connection references are intact, and no `intake_shadow` runtime references remain in the active workflow/contracts.

---

### 2026-05-13 - Phase 5.8.1 quote send confirmation path

Type: `FIX`

**Summary:** Wired the customer confirmation after an auto-generated quote into real document delivery.

**Behavior:** Backend now exposes `POST /api/orders/<order_id>/quote/send-latest`, which finds the latest non-voided quote and delegates to the existing document-send path. `1.2 - Amadeus Order Steward` now supports `action = send_latest_quote`. `1.0 - Sam-sales-agent-chatwoot` now stores `pending_action = send_quote` when a generated/current quote is offered, routes a later customer confirmation such as `Yes, please` to `SEND_QUOTE`, clears the pending action after the send call, and only lets Sam say the quote was sent when the backend confirms delivery.

**Verification:** Backend route compiled and a Flask test-client monkeypatch returned `200` with `document_status = Sent`. Both workflow JSON exports parsed successfully, embedded Code-node JavaScript passed syntax checks, and the extractor companion source passed syntax checks.

**Live test still required:** Deploy backend, import `1.2` and `1.0`, create a quote-ready draft, confirm Sam offers to send the generated quote, reply `Yes, please`, and verify `ORDER_DOCUMENTS.Document_Status = Sent` plus the Chatwoot attachment delivery from `1.5`.

**Live smoke result:** After deploy/import, safe conversation `1774` created test order `ORD-2026-DA3EAC` with one Female Grower `35_to_39_Kg` line, Cash, Riversdale. Direct quote generation created `DOC-2026-B05CD6` / `Q-2026-DA3EAC`; direct `POST /api/orders/ORD-2026-DA3EAC/quote/send-latest` returned `success = true`, `delivery_webhook_sent = true`, and `document_status = Sent`. The actual `1.0` confirmation route was then tested with a synthetic `Yes, please` inbound message and `pending_action = send_quote`; it called `1.2` / backend successfully and updated `ORDER_DOCUMENTS.Sent_By = Sam Phase 5.8.1 quote send`, `Sent_At = 13 May 2026 11:05`. Cleanup cancelled the order and closed intake `INTAKE-2026-DE3E83`; active lookup for conversation `1774` returned `no_match`.

**Smoke findings before closing 5.8.1:** The first full synthetic Chatwoot create message created the Draft and active line, but did not auto-generate the quote on that workflow path. Direct backend create-with-lines control then passed: `ORD-2026-7D0692` returned `auto_quote.generated = true` with `DOC-2026-A12EEF`, proving the deployed backend auto-quote service is healthy. A harmless backend PATCH to the earlier Draft updated the note but returned `500`; direct quote generation still worked. Treat the send-confirmation path as live-verified, but keep a follow-up check on the live `1.0`/`1.2` create path or synthetic payload path before calling the whole automatic quote flow fully closed.

**Backend hardening prepared:** `POST /api/orders/<order_id>/quote/send-latest` now self-heals when no quote exists yet: it runs `auto_generate_quote_if_ready()`, returns a clear missing-fields error if the draft is not quote-ready, or sends the newly generated/latest quote if ready. This keeps the customer confirmation path reliable even if create-time auto-quote missed. Local Flask monkeypatch test passed with `quote_ensured = true` and `document_status = Sent`.

**Integrated retest after backend deploy:** Full backend + `1.0` + `1.2` + `1.5` path passed on safe conversation `1774`. First message `I want 1 female grower pig 35-39 kg, collection at Riversdale on Friday at 14:00, cash payment. Please create the draft and send me the quote.` correctly captured item/payment/location and `quote_requested = true`, but did not set `order_commitment = true`; Sam asked whether to create the draft and formal quote. Follow-up `Yes, please create the draft order.` created `ORD-2026-1D782B`, generated quote `DOC-2026-CAA774` / `Q-2026-1D782B`, and wrote Chatwoot custom attributes `order_id = ORD-2026-1D782B`, `pending_action = send_quote`, `payment_method = Cash`. Follow-up `Yes, please` sent the PDF through `1.5`, updated `ORDER_DOCUMENTS.Document_Status = Sent`, stamped `Sent_By = Sam Phase 5.8.1 quote send`, cleared `pending_action`, and Sam replied that the formal quote was sent. Cleanup cancelled the test order, closed intake `INTAKE-2026-782FD8`, cleared Chatwoot attributes, and both active lookup endpoints returned `no_match`.

**Parser edge to fix later:** The phrase `create the draft and send me the quote` did not set `order_commitment = true` because the current regex expects stronger wording such as `create the draft order`. This did not break the flow because Sam asked for confirmation, but it is a natural phrase worth adding to the commitment detector.

**Parser edge fixed in repo:** `1.0 Code - Build Intake Shadow Payload` now treats `create/prepare/make + draft` as order commitment, covering `create the draft and send me the quote`. Local regex simulation confirms this phrase now returns commitment `true`, while quote-only wording such as `send me the quote` and `Can I get a quote?` remains `false`.

**Post-create send patch prepared:** Exact-phrase live check after the parser import created `ORD-2026-89C98E`, proving the commitment fix, but Sam still replied that the quote was not ready because the create result went to the normal draft-reply path. The export now adds `Code - Send Quote After Create Payload` and `Code - Draft Result Unless Send Quote`. For `create_draft_then_quote` / quote-requested create results, the draft-only reply is suppressed and the result calls `Call 1.2 - Send Quote`, relying on backend `send-latest` to generate-if-needed and send. JSON validation and Code-node JavaScript syntax passed. Test order `ORD-2026-89C98E` and intake `INTAKE-2026-960411` were cleaned up.

**Post-create send correction prepared:** After importing that first post-create patch, exact-phrase live check created `ORD-2026-E51675` but the `Call 1.2 - Send Quote` hop still did not deliver a quote, and Sam correctly used the failure wording instead of claiming delivery. The export now removes that fragile immediate post-create handoff and calls backend `POST /api/orders/<order_id>/quote/send-latest` directly from `1.0` for the explicit one-turn `create_draft_then_quote` case. Backend remains the document source of truth and still performs generate-if-needed plus send. Workflow JSON parses successfully; the failed test order and intake were cleaned up. Re-import `1.0` before the next exact-phrase smoke test; no backend deploy is required for this correction.

**Direct-send URL correction prepared:** Live test after the direct-send import created `ORD-2026-BCA758` but still produced no `ORDER_DOCUMENTS` row from the workflow branch, while direct control call to `POST /api/orders/ORD-2026-BCA758/quote/send-latest` immediately generated and sent `DOC-2026-243F86` / `Q-2026-BCA758`. This proves the deployed backend endpoint and `1.5` delivery are healthy, and narrows the fault to the new `1.0` HTTP node. The export now builds the post-create send URL as a single n8n expression instead of mixing expression mode with `{{ }}` templating, and the Chatwoot cleanup URL is expressed the same way. JSON validation and Code-node syntax checks pass. Cleanup cancelled `ORD-2026-BCA758`, closed `INTAKE-2026-E257FA`, cleared Chatwoot attributes, and active lookup returned `no_match`.

**Post-create branch condition correction prepared:** Live test after the URL correction created `ORD-2026-CCD6E4`, but the branch still did not send the quote and Sam replied with pre-create wording. The active intake showed the intent was correct (`next_action = create_draft_then_quote`, `quote_requested = true`), so the export now makes `Code - Draft Result Unless Send Quote` and `Code - Send Quote After Create Payload` read quote intent from multiple sources: route context, attached intake shadow result, original intake payload, and the incoming message text. JSON validation and Code-node syntax checks pass. Cleanup cancelled `ORD-2026-CCD6E4`, closed `INTAKE-2026-23380D`, cleared Chatwoot attributes, and active lookup returned `no_match`.

**Fallback quote-send regex correction prepared:** Live test after the branch-condition import created `ORD-2026-BB29C9` and auto-generated `DOC-2026-C33F42` / `Q-2026-BB29C9`, but did not send it; Chatwoot ended with `pending_action = send_quote`. The remaining fallback text detector used escaped word-boundaries and could miss `send me the quote` when prior node context was unavailable. The export now uses real JavaScript word-boundary regexes for the post-create send intent fallback. JSON validation and Code-node syntax checks pass. Cleanup cancelled `ORD-2026-BB29C9`, closed `INTAKE-2026-3408FA`, and cleared Chatwoot attributes.

**Explicit post-create send flag prepared:** Live test after the regex import created `ORD-2026-A42122` but again did not generate/send a quote; Sam asked for confirmation. The fix now stops relying on old node references after create. `Set - Draft Order Payload` carries a boolean `send_quote_after_create`, and `Code - Store Draft Order Context` copies that flag into the create result. The post-create send branch now keys only on that explicit flag plus `order_id`. JSON validation and Code-node syntax checks pass. Cleanup cancelled `ORD-2026-A42122`, closed `INTAKE-2026-B287B3`, and cleared Chatwoot attributes.

**Backend-owned create-and-send prepared:** Claude review found the post-create send branch was structurally fragile in `1.0`: sibling Chatwoot writes stamped `pending_action = send_quote`, merge nodes could drop the slower send result, and the branch depended on old node reads. The repo now moves ownership into the linear transaction: backend `create-with-lines` accepts `send_quote_if_ready`, auto-generates the quote, calls `send_order_document()` when a quote document exists and `conversation_id` is present, and returns `quote_send`. `send_order_document()` now no-ops successfully for a quote already sent within 10 minutes. `1.2` passes `send_quote_if_ready` into create-with-lines and echoes `quote_send`. `1.0` removed the five post-create fan-out nodes, sends the new flag in the draft payload, clears `pending_action` when `quote_send.success = true`, and gives Sam compact `quote_send` status so Sam only says sent after backend confirmation. JSON validation, Code-node syntax checks, Python compile, and local quote-send helper checks passed. Next required action: deploy backend, import `1.2`, import `1.0`, then run the exact one-turn smoke.

**Retest after upload/deploy:** Exact one-turn smoke still did not close. First retry created `ORD-2026-AA93B5` and delivered the PDF attachment, but `ORDER_DOCUMENTS.Document_Status` remained `Generated`; backend response parsing was hardened to handle nested n8n response bodies. Second retry created `ORD-2026-09E7F7` with correct line/payment/location, but no quote was generated by the live `1.0 -> 1.2` create path and Sam replied that the quote was not ready. Direct backend controls proved quote generation and `send-latest` work for that order. Direct backend `create-with-lines` with `send_quote_if_ready = true` created `ORD-2026-77CF11`, generated and delivered the PDF, but returned `500` and left the document `Generated`, consistent with the document-delivery webhook taking longer than the previous 30-second backend timeout. Repo fix: document delivery webhook timeout increased to 90 seconds. Cleanup cancelled `ORD-2026-AA93B5`, `ORD-2026-09E7F7`, and `ORD-2026-77CF11`, reset intake `1774`, and cleared Chatwoot attributes. Required next action: deploy the timeout/parser backend patch and re-import the current `1.2` export before the next one-turn smoke.

**1.2 linear send correction prepared:** Retest after backend deploy and `1.2` upload showed the one-request backend create/generate/send path still returns `500` after the PDF reaches Chatwoot, and the document can remain `Generated` until a later `send-latest` call marks it `Sent`. To avoid Render/Flask request length and Sheets quota pressure, `1.2` now owns the linear post-create send: create-with-lines no longer passes `send_quote_if_ready` into the backend request, then `1.2` checks the create response for `auto_quote.document.document_id`, calls backend `send-latest` as a second HTTP request, attaches `quote_send`, and only then formats the create result back to `1.0`. This preserves the simple `1.0` path while keeping each backend request short. JSON validation and Code-node syntax checks passed. Cleanup cancelled `ORD-2026-65A33B` and `ORD-2026-CE583C`, reset intake `1774`, and verified no active order remains. Required next action: import updated `1.2` and rerun the exact one-turn smoke.

**Final one-turn smoke passed:** After the final `1.2` import, the exact customer message `I want 1 female grower pig 35-39 kg, collection at Riversdale on Friday at 14:00, cash payment. Please create the draft and send me the quote.` passed end to end on safe conversation `1774`. The workflow created `ORD-2026-D3BB1C`, added one active Female Grower `35_to_39_Kg` line, generated `DOC-2026-E14CB0` / `Q-2026-D3BB1C`, sent the PDF through `1.5`, marked `ORDER_DOCUMENTS.Document_Status = Sent`, stamped `Sent_At = 13 May 2026 17:57` and `Sent_By = Sam Phase 5.7 intake`, cleared Chatwoot `pending_action`, and Sam replied that the formal quote had been sent. Cleanup cancelled the order, closed intake `INTAKE-2026-D9B528`, cleared Chatwoot attributes, and active lookup returned `no_match`.

---

### 2026-05-13 - Phase 5.8 formal quote request first slice

Type: `ADD`

**Summary:** Added the first controlled Sam-to-backend formal quote route.

**Behavior:** `1.2 - Amadeus Order Steward` now supports `action = generate_quote`, calling backend `POST /api/orders/<order_id>/quote` and formatting compact quote document fields. `1.0 - Sam-sales-agent-chatwoot` now routes existing-draft quote requests to `GENERATE_QUOTE`, calls `1.2`, merges the result back into Sam context, and gives Sam explicit wording rules that a generated quote is not the same as a sent quote or an approved order.

**Boundary:** This slice generates the quote only. Sending remains on the existing backend document delivery path and `1.5`. Complete quote requests with no linked draft now trigger safe draft creation via `create_draft_then_quote`, but automatic quote generation immediately after that new draft is still pending.

**Verification:** Workflow JSON parsed successfully, all connection targets exist, and Code-node JavaScript passed syntax checks. Live n8n import and safe-order quote test still required.

**Live test progress:** Temporary test order `ORD-2026-AC3DFF` was created with `ConversationId = 1742`, `Payment_Method = Cash`, and one active Female Grower line. A direct `1.0` webhook quote request returned `ok = true` but did not generate a document. n8n execution detail showed the workflow stopped earlier at `HTTP - Get Conversation Messages` with Chatwoot `404 Resource could not be found`. Backend control call generated quote `DOC-2026-1B44A1` / `Q-2026-AC3DFF`, proving document generation is healthy. Fixes prepared: `HTTP - Get Conversation Messages` now continues on fail so history lookup problems do not stop the current message, `PaymentMethod` is carried through `Edit - Keep Chatwoot ID's`, and quote-intent + order ID routes to `GENERATE_QUOTE` without requiring `1.0` to prove payment first. Backend remains the final guard for payment readiness.

**Retest after import:** The actual Phase 5.8 route passed. `1.0 -> 1.2 -> backend` generated quote `DOC-2026-50E0D5`, `Q-2026-AC3DFF-V2`, total `R1,400.00`, created by `Sam Phase 5.8 quote`. The final `HTTP - Send Chatwoot Reply` then returned Chatwoot `404 Resource could not be found`, so the customer reply failed after the document was already generated. Reply-node URL fallback fix prepared so it can use current item IDs, `Edit - Keep Chatwoot ID's`, or `Code - Normalize Incoming Message` IDs.

**Reply-node retest:** After the URL fallback import, quote generation still passed and created `DOC-2026-ACE2E9`, `Q-2026-AC3DFF-V3`, total `R1,400.00`, but `HTTP - Send Chatwoot Reply` still returned Chatwoot `404`. Next fix prepared: make the final reply node match the live-verified `1.4` send-message pattern with fixed account `147387`, normalized `ConversationId`, and explicit JSON body.

**Final retest:** Passed after correcting the safe test order's `ConversationId` to `1774`. The workflow generated `DOC-2026-001270`, `Q-2026-AC3DFF-V5`, total `R1,400.00`, created by `Sam Phase 5.8 quote`, and Sam successfully replied in Chatwoot: `Charl, your formal quote has been generated with reference Q-2026-AC3DFF-V5. Would you like me to send it to you now?`

**Cleanup:** Temporary test order `ORD-2026-AC3DFF` was cancelled after verification. Final state: `Order_Status = Cancelled`, `Payment_Status = Cancelled`, `active_line_count = 0`, `cancelled_line_count = 1`.

**Direction update:** Phase 5.8 now treats formal quotes as automatic backend artifacts of quote-ready draft orders, not as something customers must ask for with exact wording. Backend mutations now return `auto_quote` after create-with-lines, update, and line sync. `auto_quote` generates only when the draft is ready and skips duplicate versions when the latest quote fingerprint still matches the current draft. `1.2` preserves the field and `1.0` passes it into Sam's compact steward context so Sam can offer to send an already-generated quote.

**Claude review fixes before live import:** Removed volatile `order_line_id` from quote fingerprints, added rendered customer fields to the fingerprint, made manual quote generation stamp fingerprints, made quote readiness use `ORDER_MASTER` truth/fallback instead of relying only on formula-driven `ORDER_OVERVIEW`, and added a defensive skip for partial/incomplete fulfillment results.

**Live smoke:** Backend direct smoke passed on `ORD-2026-2BF6EE`: missing payment blocked auto-quote, patching `Cash` generated `DOC-2026-19D8D0` / `Q-2026-2BF6EE`, and same-item resync returned `latest_quote_current` with no duplicate quote version. Full `1.0 -> 1.2 -> backend` smoke passed on safe conversation `1774`, creating `ORD-2026-BCC742` and auto-generating `DOC-2026-3960F1` / `Q-2026-BCC742`. Sam's reply correctly said the draft was ready, the formal quote had been generated, and asked whether to send it now. Both test orders were cancelled and conversation `1774` returned `no_match`.

---

### 2026-05-12 - Phase 5.7 intake-driven draft creation scaffold

Type: `ADD`

**Summary:** Updated `1.0 - Sam-sales-agent-chatwoot` export so the first controlled intake-driven route can create a Draft order from verified intake state.

**Behavior:** When `intake_shadow_result.ready_for_draft = true`, `next_action = create_draft`, and no draft is linked yet, `Code - Decide Order Route` routes to `CREATE_DRAFT`. `Set - Draft Order Payload` uses backend-confirmed intake facts and calls existing `1.2` `create_order_with_lines`. After `Code - Store Draft Order Context`, the new `Code - Build Intake Draft Link Payload` / `HTTP - Link Intake Draft Order` branch patches the returned `order_id` back to `ORDER_INTAKE_STATE.Draft_Order_ID`. The link branch emits no item unless the draft came from intake readiness, so legacy create behavior does not call intake.

**Live retest correction:** The first import did not create a draft because the intake result was only passed through the escalation classifier path, and classifier output does not reliably preserve all incoming fields. The export now sends `Code - Attach Intake Shadow Result` to both `Ai Agent - Escalation Classifier` and `Merge - Sales Agent Context A`, so `intake_shadow_result` survives to `Code - Decide Order Route`.

**Second retest correction:** Route decision still did not create a draft, so `Code - Decide Order Route` now reads `Code - Attach Intake Shadow Result` directly as a fallback when its input item lacks `intake_shadow_result`. It also reattaches `intake_shadow_result`, `intake_shadow_raw_response`, and `intake_shadow_payload` to its output for `Set - Draft Order Payload`.

**Third retest correction:** The later `Code - Should Create Draft Order?` node can overwrite `should_create_draft` from older memory/missing-fact rules. The export now stamps intake-ready order facts directly in `Code - Attach Intake Shadow Result`, and `Code - Should Create Draft Order?` treats the intake-ready signal as an approved create signal.

**Safety:** Existing 1.2 order creation and line sync remain the only order-writing path. Existing `order_state` routing remains fallback. Formal quote PDF generation is not included in Phase 5.7.

**Verification:** Workflow JSON parsed successfully, all connection targets exist, workflow has 103 nodes, and changed Code-node JavaScript passed syntax checks.

**Live verification:** Completed on 2026-05-12 using safe Chatwoot conversation `1774` and intake `INTAKE-2026-4D7825`. Live webhook message `I want to proceed` created draft `ORD-2026-A822D3`, linked it back to `ORDER_INTAKE_STATE.Draft_Order_ID`, moved intake to `Draft_Created`, and synced one active line `OL-2026-95EC63` for Female Grower `35_to_39_Kg`, unit price `1400`, request item key `item_1`. The order header stored `ConversationId = 1774`, `Payment_Method = Cash`, and `Collection_Location = Riversdale`.

**Regression finding:** A broader live batch on 2026-05-12 exposed a route mismatch before cleanup. Natural commitment wording such as `I would like to proceed` / `create a draft order` can fail the intake readiness gate while the legacy `should_create_draft` path still creates a draft. Test draft `ORD-2026-2B0D8A` was created by the legacy path with zero active lines, then cancelled and conversation `1774` was reset. Fix commitment detection and block header-only legacy creation before running the full 10-case regression or simplifying the workflow.

**Regression fix prepared:** `Code - Build Intake Shadow Payload` now recognizes broader commitment wording, including `I would like to proceed`, `create a draft order`, and `prepare the next step`. `Code - Should Create Draft Order?` now blocks legacy header-only draft creation unless legacy state has active line-ready `requested_items`; intake-ready creation still bypasses that legacy guard. Local simulation confirms the failed wording sets `order_commitment = true`, header-only legacy creation returns `should_create_draft = false`, and line-ready legacy creation still returns `true`.

**Live retest:** After n8n import, the original failed wording created `ORD-2026-1450B2` from intake with 3 active Female Grower `30_to_34_Kg` lines, Riversdale, Cash. The test order was cancelled and the intake was closed.

**Additional wider-batch findings:** Further live regression should pause before cleanup. `ORD-2026-86CA53` created active Weaner `10_to_14_Kg` lines but stored header sex as `Any` when the message requested male. `ORD-2026-21BB6F` created a zero-line Draft for 1 Female Weaner `15_to_19_Kg`, so zero-line prevention must also account for steward/line-sync no-match results after create. All wider-batch test orders were cancelled and conversation `1774` was verified clean. The batch also hit Google Sheets API read quota (`429`), causing temporary Render `500` responses.

**Additional fix prepared:** `1.0 Code - Build Intake Shadow Payload` now overrides stale `Any` item sex with the latest explicit `Male` / `Female` from the customer message. `1.2` create-with-lines now sends `cancel_order_if_no_matches = true` to backend line sync. Backend validation accepts that flag, and `sync_order_lines_from_request` auto-cancels the newly-created Draft when the create path matches zero pigs. `1.2 Code - Format Create With Lines Result` returns `success = false` for that auto-cancel so Sam does not treat a zero-line draft as a valid draft.

**Live targeted retest:** Passed after backend deploy and `1.0` / `1.2` imports. `ORD-2026-8096C6` verified the male sex fix: header `Requested_Sex = Male` and two active Male Weaner `10_to_14_Kg` lines, then cancelled. The old Female Weaner `15_to_19_Kg` no-match case now has live stock and correctly created `ORD-2026-0B3C01` with one active line, then cancelled. A true no-stock Female Weaner `7_to_9_Kg` workflow test left no active order. Direct deployed-backend create+sync verified auto-cancel with `ORD-2026-009333`: `cancelled_empty_order = true`, `fulfillment_status = no_match`, `matched_total = 0`, and final `Order_Status = Cancelled`. Final conversation `1774` cleanup returned no active intake and no active order.

**Atomic create-with-lines fix prepared:** Wider regression showed the previous `1.2` create-with-lines path could still leave an active zero-line Draft if the second HTTP call (`sync-lines`) failed after the header was created. `ORD-2026-CA751C` was the evidence order and was cancelled during cleanup. Backend now exposes `POST /api/master/orders/create-with-lines`, which creates the order, syncs lines, and cancels the new Draft if sync fails or matches zero pigs. `1.2 HTTP - Create With Lines Order` now calls this atomic endpoint directly. The ordinary `create_order` route remains unchanged.

**Atomic create-with-lines live retest:** After deploy/import, WR01 passed with `ORD-2026-A1F319` creating 2 active Male Grower `20_to_24_Kg` lines. WR02 created expected Female Grower `35_to_39_Kg` draft `ORD-2026-63B833`, and WR03 created expected Male Piglet `5_to_6_Kg` draft `ORD-2026-0F3604`. Both were cancelled during cleanup after quota-related 500s interrupted inline validation/cancel. Final conversation `1774` state returned no active intake and no active order. Larger automated live batches still need slower pacing or backend Sheets read caching/retry/backoff.

**Single no-stock regression:** Passed on 2026-05-13. A request for 1 Female Weaner `7_to_9_Kg`, Riversdale, Friday 14:00, EFT linked intake to `ORD-2026-CBAE14`; active customer lookup returned `no_match`, and order detail confirmed `Order_Status = Cancelled`, `Payment_Status = Cancelled`, and `active_line_count = 0`. This verifies the atomic create-with-lines path does not leave an active zero-line Draft for true no-stock requests.

**Cleanup note:** Phase 5.6/5.7 added compatibility paths while proving intake behavior. A planned cleanup pass must remove duplicated shadow/legacy routing once intake-driven draft/update/quote paths are proven.

---

### 2026-05-12 - Phase 5.6 intake shadow mode complete

Type: `ADD`

**Summary:** Updated `1.0 - Sam-sales-agent-chatwoot` export with a shadow-mode backend intake call before the escalation classifier. New nodes: `Code - Build Intake Shadow Payload`, `HTTP - Intake Shadow Update`, and `Code - Attach Intake Shadow Result`.

**Behavior:** The workflow posts a proposed intake patch to `POST /api/order-intake/update`, attaches `intake_shadow_result` / `intake_shadow_raw_response`, and then continues into the existing escalation classifier and AUTO/ESCALATE route switch. Live routing is unchanged; backend intake state is not used as route truth yet.

**Verification:** Workflow JSON parsed successfully, all connection targets exist, the three new nodes are connected in-line, and the new Code-node JavaScript passed syntax checks.

**Live verification:** Completed on 2026-05-12 against safe Chatwoot conversation `1774`. First customer message created intake `INTAKE-2026-4D7825` with item `INTAKEITEM-2026-39BF24`: 1 Female Grower, `35_to_39_Kg`, Riversdale, Friday at 14:00, Cash. Backend returned `quote_requested = true` and only `order_commitment` missing. Follow-up `I want to proceed` updated the same intake to `Ready_For_Draft`, with `missing_fields = []`, `next_action = create_draft`, and `ready_for_draft = true`. Existing live routing remained unchanged; no real draft order was created by Phase 5.6.

**Next:** Phase 5.7 will promote verified intake readiness into controlled draft creation and line sync while keeping the current route as fallback until live-verified.

---

### 2026-05-12 - Phase 5.5 backend intake endpoint scaffold

Type: `ADD`

**Summary:** Added backend-ready persistent order intake endpoints for the upcoming `1.0` shadow-mode integration: `GET /api/order-intake/context`, `POST /api/order-intake/update`, and `POST /api/order-intake/<conversation_id>/reset`. The backend validates proposed intake patches, preserves known facts when blank values arrive, merges item rows by stable `item_key`, computes missing fields/readiness/next action, and keeps closed/removed history instead of deleting it.

**Runtime note:** No n8n workflow behavior has changed yet. Live Google Sheet setup and a direct local-backend smoke test passed on 2026-05-12 using `PHASE55-TEST-20260512`; the test intake was reset/closed. Deployed Render smoke test also passed using `PHASE55-RENDER-TEST-20260512`; intake `INTAKE-2026-FD85E3` and item `INTAKEITEM-2026-2CAC20` were created, read back, and reset/closed. Phase 5.6 will call these endpoints in shadow mode before intake state drives live draft/quote actions.

---

### 2026-05-11 - Persistent order intake state plan

Type: `DOCS`

**Summary:** Planned the next order-conversation architecture change. The agreed direction is a backend-owned persistent order intake state with item-level rows, followed by shadow-mode verification, intake-driven draft creation, formal quote generation, and only then n8n/Chatwoot payload cleanup. This is intended to stop long conversations from losing customer-confirmed order facts and to separate Draft Orders from backend-generated quote PDFs.

**Design progress:** Added the Phase 5.4 backend design document and planned sheet specs for `ORDER_INTAKE_STATE` and `ORDER_INTAKE_ITEMS`. No runtime behavior was changed.

---

### 2026-05-11 - Phase 5.3 Sam order-review wording guard

Type: `IMPROVEMENT`

**Summary:** Added a dedicated `ORDER REVIEW RESPONSE RULES` section to the `1.0 - Sam-sales-agent-chatwoot` Sales Agent system prompt. Sam must now answer current-order review, status, approval, missing-detail, and quote/invoice follow-up questions from backend/steward context first; use one matched order only; ask one disambiguation question for multiple matches; and avoid claiming approval, reservation, collection, document links, or document delivery unless backend context confirms it. The active-order lookup trigger set now includes missing-detail wording such as "What is still missing?".

**Live verification:** Completed on 2026-05-11 using Chatwoot conversation `1774` and temporary order `ORD-2026-DDFEE6`. All five Phase 5.3 prompts were accepted by the live workflow and the project owner confirmed Sam's replies were good. The temporary order was cancelled after verification and active lookup for conversation `1774` returned `no_match`.

---

### 2026-05-11 - Phase 5.2 safe active customer order lookup scaffold

Type: `ADD`

**Summary:** Added the read-only `1.2 - Amadeus Order Steward` branch `get_active_customer_order_context`. The branch calls backend `GET /api/orders/active-customer-context` with `order_id`, `conversation_id`, or `customer_phone`, then formats `lookup_status`, `match_count`, `active_order_context`, and `active_order_matches` for Sam review routing. `1.0 - Sam-sales-agent-chatwoot` now has a conservative fallback path: when no `ExistingOrderId` is available and the customer asks saved-order review/cancel/document-style questions such as "what is on my order?", it calls the steward lookup and injects single-match context into the existing order-state path. Normal new sales messages do not trigger the lookup, and exact `ExistingOrderId` still uses the existing `get_order_context` path.

**Live test note:** First clean-conversation test exposed a `1.0` Chatwoot history fetch URL issue. `HTTP - Get Conversation Messages` was reading `account_id` and `conversation_id` from `conversation.messages[0]`, where those fields can be undefined. The export now builds that URL from the normalized Chatwoot IDs captured by `Code - Normalize Incoming Message`.

**Follow-up correction:** The new `1.2` switch output for `get_active_customer_order_context` must use `={{ $json.action }}` like the other `Switch - Route by Action` branches. A bad `={{ .action }}` expression causes `invalid syntax` before the active lookup branch can run.

**Lookup precision correction:** Conversation ID now takes priority over customer phone for active-order lookup. `1.0` sends phone only when no conversation ID is available, and the backend lookup uses exact `order_id`, then exact `conversation_id`, then phone fallback. This prevents a clean conversation from being diluted by older active orders on the same phone number.

**Live verification:** Completed on 2026-05-11 with clean Chatwoot conversation `1774` and temporary order `ORD-2026-8B7FC8`. Sam replied with the single correct draft order context: 1 male piglet, `5_to_6_Kg`, Riversdale, `R400`. The temporary order was cancelled after the successful test and active lookup for conversation `1774` returned `no_match`.

---

### 2026-05-11 - Phase 4.3 requested item metadata validation

Type: `FIX`

**Summary:** Clarified and enforced the `requested_items[]` metadata contract. Backend sync now validates optional `intent_type` against `primary`, `addon`, `nearby_addon`, and `extractor_slot`; `status` defaults to `active` and any non-`active` value is rejected. This makes `status` explicit instead of silently accepting inactive/cancelled requested rows that backend sync does not know how to skip.

**Live verification:** Completed on 2026-05-11 using temporary Charl N draft `ORD-2026-07F5C8`. Valid direct sync with `intent_type = primary` and `status = active` passed and created no lines because the requested Grower `30_to_34_Kg` Male item had no exact stock match. Invalid direct sync with `status = inactive` returned `400`; invalid direct sync with `intent_type = made_up` returned `400`. The invalid calls did not alter order lines. The test draft was cancelled after verification with zero active lines and zero reserved pigs.

---

### 2026-05-10 - Phase 4.2 partial/no-match fulfillment contract

Type: `FIX`

**Summary:** Tightened partial stock handling across backend and n8n. `sync_order_lines_from_request` now reports `complete_fulfillment`, `fulfillment_status`, aggregate requested/matched/unmatched totals, and `incomplete_items`; `no_match` rows now count as incomplete fulfillment instead of looking like a complete sync. `1.2 - order-steward` passes these fields through direct sync and `create_order_with_lines`. `1.0 - Sam-sales-agent-chatwoot` marks `had_no_match` / `had_incomplete`, expands `partial_stock_detail` for no-match rows, and uses no-match alternatives when rebuilding follow-up offer caps. Live verification created `ORD-2026-011771` for Grower `30_to_34_Kg`, 1 Male + 2 Female: only two Female lines were added, the direct sync returned `complete_fulfillment = false` / `fulfillment_status = partial`, Sam generated correct partial/no-match wording, and the test draft was cancelled after verification.

---

### 2026-05-10 - Phase 4.1 split item sync stabilization

Type: `FIX`

**Summary:** Updated `1.0 - Sam-sales-agent-chatwoot`, `1.2 - order-steward`, and backend create handling for mixed-sex order requests. `Code - Build Order State` now stores mixed split headers as `Requested_Sex = Any` while preserving exact per-sex quantities in `requested_items[]`; memory-confirmed split requests now route to `UPDATE_HEADER_AND_LINES`; and weight parsing no longer misreads `20-24kg` / `30-34kg` as `2_to_4_Kg`. First-turn `create_order_with_lines` now carries `collection_location`, `payment_method`, and `conversation_id` through `1.0`, `1.2`, and backend create. Live retest created `ORD-2026-25CC0D` with header fields and lines correct (`primary_1` Male, `primary_2` Female x2), then cancelled the test draft.

---

### 2026-05-10 - Phase 3.2 daily order summary workflow scaffold

Type: `ADD`

**Summary:** Added and manually verified `1.6 - Daily Order Summary` workflow docs/export. The workflow has a manual test trigger and daily 16:00 Africa/Johannesburg schedule trigger, calls `GET /api/reports/daily-summary` on the backend, formats the returned counts/attention orders, and sends the message to the approved Telegram admin chat. Manual Telegram test passed on 2026-05-10 after setting `parse_mode = HTML` and escaping dynamic text so customer/order values do not break Telegram entity parsing. The workflow must not read order sheets directly.

---

### 2026-05-10 - Phase 2.5 outbound document delivery scaffold

Type: `ADD`

**Summary:** Added and live-verified `1.5 - Outbound Document Delivery` workflow docs/export. Backend remains the source of truth for quote/invoice generation, totals, VAT, document references, Google Drive file IDs, and `ORDER_DOCUMENTS`; n8n only downloads the generated PDF and sends it as a Chatwoot attachment. Live tests used Chatwoot `conversation_id = 1742` only: direct webhook quote send returned `success = true`, `sent = true`; backend invoice send returned `document_status = Sent` and updated `ORDER_DOCUMENTS`.

---

### 2026-05-09 - Phase 1.9 outbound order notification scaffold

Type: `ADD`

**Summary:** Added Phase **1.9** backend-triggered notification contract and draft `1.4 - Outbound Order Notification` workflow docs/export. `ORDER_MASTER.ConversationId` is the Chatwoot lookup key, and backend sends exact approval/rejection message text through `ORDER_NOTIFICATION_WEBHOOK_URL` after successful order transitions. Delivery failures are warnings only; they do not roll back approval or rejection.

---

### 2026-05-07 — Phase 1.7 slim Sales Agent: live verification closed

Type: `DOCS`

**Summary:** Phase **1.7** (`Code - Slim Sales Agent User Context`, `OrderStateSummary` + `StewardCompact`) signed off after WhatsApp minimal checklist (AUTO+draft path + CLARIFY path). **`NEXT_STEPS.md`** §1.7 marked **Complete And Live-Verified**; **`HOW_WE_WORK.md`** working position advanced; next open subsection **§1.8** approval auto-reservation.

---

### 2026-05-09 — Sales agent memory: slaughter/finisher bands + Sam recap + longer history

Type: `FIX` + `IMPROVEMENT`

**Problem:** On long WhatsApp threads, **`Code - Should Create Draft Order?`** stayed **`should_create_draft: false`** even after the customer confirmed (**e.g.** final **“Yes”**) because **`order_state`** had empty **qty / category / weight / timing / location**. Two causes: **`Code - Format Chat History`** only kept the **last 10** messages (early **Customer** lines with full specs dropped off), and **`Code - Build Sales Agent Memory Summary`** had **no weight patterns above 45–49 kg**, did not parse colloquial quantities like **“1 would be fine”**, and did not recover facts from **Sam’s order-recap** lines (safe echo of what the customer already confirmed).

**Changes (re-import `1.0` from repo):**

| Area | Change |
|------|--------|
| **`Code - Format Chat History`** | **`msgs.slice(-10)` → `slice(-25)`** so structured extraction and memory see more of the thread. |
| **`Code - Build Sales Agent Memory Summary`** | Weight bands **50–54 kg … 90–94 kg**; quantity phrases **`N would be fine`** / **`would work`**; **Sam recap fallback** only on **explicit recap hints** in **Sam** lines (**“order is for…”**, **“your order is for…”**, **“request noted for…”**, etc.) — **not** bare **pickup + location** (those matched inventory prompts); fills **only empty** slots; **infer Category** from band for Finisher / Slaughter when category still blank; recap-based **`sex_split`** uses **whitelist tokens** (**`female` / `male` / …**) because **`/male/i.test("female")`** was **true** and produced **1 male + 1 female** for a **single female** pig. |

**Operational note:** Recap fallback stays **narrow** so Sam’s stock lists and “how many for pickup in Riversdale?” prompts are not treated as order confirmation.

**Follow-up (same day):** Fix **false split-sex** (`sex_split` **1 male, 1 female**) from substring **`male` inside `female`**; remove **pickup + location** as sole recap signal.

**Related (not fully closed by the above):** A **grower** thread with **“1 male and 2 females”** + **Riversdale** still needs verification that **`ORDER_MASTER`** receives **`Requested_Sex` / `Collection_Location`** and **`ORDER_LINES`** get correct **per-line sex** (see **`NEXT_STEPS.md` §4.1** incident + regression test). That work spans **Steward `update_order`** / sync and may include **Sam prompt** parity, not memory alone.

---

### 2026-05-08 — Partial-stock multi-band: caps + nearby lines without duplicate regex

Type: `FIX` + `IMPROVEMENT` + `DOCS`

**Problem summary:** WhatsApp confirmations (“make it total 7”) sometimes produced **`requested_items`** with only **`primary_1`** or a single inflated **`nearby_band_1`** so **`sync_order_lines_from_request`** could not allocate across **7–9** and **15–19** kg.

**Root causes fixed:**

| Issue | Fix |
|--------|-----|
| **`reAvail` + `reThereAre`** both matched “there are 2 **available** in the 7–9kg…” | Dropped **`reThereAre`** from **`Code - Build Order State`** and **`Code - Build Sync Existing Draft Payload`** extractors (**`extractAdjacentBandOffersFromTranscript`**). Duplicate hits had **added** qty into one band (**4 × 7–9**), consuming full remainder **before** **15–19**. |
| “**2 more** in **15–19kg ranges**” | **`reQtyInKg`** (**`capsFromSamText`**) and **`rxBareInKg`** (sync/build-order extract) accept optional **`more`** before **`in`** and optional plural **`ranges`**. |
| Bullets **“- 2 weaners in 7–9kg”** (no **`pigs`**) | **`reAnimalsInBand`** / **`rx3`** now match **`pigs? \| weaners? \| piglets?`** before **`in`**. **`last_agent_offer.caps`** was missing alternate bands purely because **`pigs?`** did not fire. |
| **`Code - Build Sync Existing Draft Payload`** skipped enrich when **`base.length !== 1`** | **`enrichPartialMixItems`** rebuilds **`nearby_band_*`** from transcript + **`last_agent_offer.caps`** whenever the nearby **tier signature** changes or qty exceeds band cap (**legacy oversize**). **`sync_payload_nearby_items_enriched`** uses serialized compare, not row-count only. |
| Sam wording drift | **`Ai Agent - Sales Agent`** system prompt — **PARTIAL-STOCK BULLET FORMAT**: one bullet per band, literal pattern **`- Q pigs (or weaners) in LOW–HIGH kg`**. |

**Maintenance scripts** (run from **`extractor-pipeline/`** after editing sources):

- **`apply_extractor_inputs_patch.py`** — injects **`Code-Build-Extractor-Inputs.js`** into **`Code - Build Extractor Inputs`**.
- **`apply_sync_existing_payload_patch.py`** — injects **`Code-Build-Sync-Existing-Draft-Payload.js`** into **`Code - Build Sync Existing Draft Payload`**.
- **`patch_build_order_state_nearby_bands.py`** — reapplies **`Code - Build Order State`** **`extractAdjacentBandOffersFromTranscript`** + **`mergeAdjacentBandsWithOfferCaps`** + transcript merge block (**use after hand-editing** that node, or cherry-pick; backup **`workflow.json`** first).
- **`apply_extractor_patch.py`** — reinstalls entire extractor subgraph (**new node IDs**).

**Operational note:** The **OpenAI extractor** (`Code - Invoke Order Intent Extractor`) can still fail on **n8n Cloud** (**`getCredentials`** unavailable); **deterministic routing** (**Build Order State** + **`last_agent_offer`** from **`sam_text_parse`**) remains the backbone for **`nearby_band_*`** when **`sync_results`** is absent.

---

### 2026-05-08 — Order Intent Extractor (partial-stock comprehension)

Type: `ADD` + `IMPROVEMENT` + `DOCS`

Goal: Short customer replies after a partial-stock WhatsApp offer (e.g. “Yes, please make up the 8”) map to **`order_state.requested_items[]`** reliably without endless regex churn; **`gpt-4.1-mini`** proposes JSON; code validates/clamps against a closed-world **`last_agent_offer`** envelope.

Implementation:

- **New pipeline** (after **`Code - Align Order Logic`**, before **`Code - Should Create Draft Order?`):**  
  **`Code - Build Extractor Inputs`** → **`Code - Should Run Extractor`** → **`Code - Invoke Order Intent Extractor`** (OpenAI Chat Completions, **`response_format: json_object`**, uses **`openAiApi`** credential **`getCredentials`**) → **`Code - Validate Extractor Output`** → **`Code - Merge Extractor Into Order State`**.  
  Source files live in **`docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/extractor-pipeline/`**; re-run **`apply_extractor_patch.py`** after editing them.
- **`last_agent_offer`:** prefer Steward **`results`/`sync_results`** `partial_match` + **`alternatives[]`** caps; fallback regex parse of the **latest `Sam:`** line in **`ConversationHistory`** (see **`extractor-pipeline/README.md`** — **Extractor LLM design contract** and **Sam text fallback**).
- **Rollback:** host env **`EXTRACTOR_ENABLED`** — set to **`false`**, **`0`**, **`off`**, or **`no`** (case-insensitive) to disable the extractor (also checks **`process.env`** on self-hosted n8n).
- **Observability on each execution item:** **`extractor_skip_reason`**, **`extractor_should_run`**, **`extractor_raw_output`**, **`extractor_latency_ms`**, **`extractor_error`**, **`extractor_validation`**, **`extractor_merge_applied`**.

Re-import **`1.0 - Sam-sales-agent-chatwoot/workflow.json`** after pulling this repo.

Design and ops: **`docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/extractor-pipeline/README.md`**.

### 2026-05-08 — Sam partial-stock wording on `create_order_with_lines`

Type: `FIX` + `DOCS`

Issue: first-turn `CREATE_DRAFT` with `create_order_with_lines` returned correct `partial_match` in `sync_results`, but `1.2 Code - Format Create With Lines Result` did not set top-level `partial_fulfillment` / `results`, and `StewardCompact` only exposed a terse `summary`, so Sam defaulted to vague \"limited stock\" wording.

Change:

- **`1.2` `Code - Format Create With Lines Result`:** pass `partial_fulfillment` (from API or inferred from `partial_match` rows), duplicate `results` next to `sync_results` for callers that read `results`.
- **`1.0` `Code - Slim Sales Agent User Context`:** set `partial_fulfillment` when `had_partial`; add **`partial_stock_detail`** string (requested vs `added_to_draft`, band availability, same-category alternative bands from `alternatives[]`).
- **`1.0` Sam system prompt:** hardened **PARTIAL STOCK SYNC** rules (explicit X vs Y, list alternatives, single follow-up question; applies to create-with-lines as well as sync on existing draft).
- **`1.0` `Code - Build Order State` + `Code - Decide Order Route`:** when the customer answers a partial-stock offer (mix / “make it up”) and the draft still has fewer active lines than the requested total, set **enrichment** and route **`UPDATE_HEADER_AND_LINES`**; parse **`N … at X–Y kg`** snippets from **`ConversationHistory`** and append **`nearby_band_*`** `requested_items` so the steward can sync adjacent bands—not **`REPLY_ONLY`** with only a reassurance message.
- **`1.0` `Code - Build Order State`:** quantity patterns recognise **`want total N`** / **`total of N`** (previously **`I want total 8`** did not populate **`msg_quantity`**, blocking **`should_enrich`**).

### 2026-05-07 — `Line_Count` vs active lines (documented + API)

Type: `DOCS` + `IMPROVEMENT`

- **Cause:** `ORDER_OVERVIEW.Line_Count` uses `COUNTIF(ORDER_LINES!$B:$B, order_id)` — it counts **all** line rows, including **`Cancelled`** (common after sync replace). Example: 3 active + 3 cancelled → sheet shows 6. **`send_for_approval`** uses only non-cancelled lines, so behaviour was already correct; the confusion risk is **human/Sam** reading `line_count` as “pigs on the order.”
- **API:** `GET /api/orders/<order_id>` → `order.active_line_count` = count of lines where `line_status !== "Cancelled"` (same rule as approval).
- **`1.2` `get_order_context` formatter:** passes `active_line_count` (falls back to counting slim lines if API not deployed yet) and `line_count_includes_cancelled: true`.
- **Docs:** `ORDER_OVERVIEW.md`, `API_STRUCTURE.md`, `DATA_FLOW.md`.

### 2026-05-07 — Partial sync lines, order context fetch, GET order `payment_method`

Type: `FIX` + `ADD` + `IMPROVEMENT`

**Backend**

- `sync_order_lines_from_request`: `partial_match` now creates `ORDER_LINES` for available pigs (up to requested quantity), not zero lines. Per-item payload includes `available_quantity`; top-level `partial_fulfillment` when any item was short.
- `GET /api/orders/<order_id>`: `order` object now includes `payment_method` from `ORDER_MASTER.Payment_Method` (overview alone does not carry it).

**`1.2 - Amadeus Order Steward`**

- New steward action `get_order_context`: `GET /api/orders/<id>` → `Code - Format Get Order Context Result` returns `order_context_fetch_ok`, `existing_order_context` (slim header + lines).
- `Set - Format Sync Order Lines Result` also passes through top-level `results` and `partial_fulfillment` for downstream Sam merge.

**`1.0 - Sam - Sales Agent - Chatwoot`**

- After `Code - Build Sales Agent Memory Summary`, when a draft `order_id` exists: `If` → `Set - Get Order Context Payload` → `Call 1.2 - Get Order Context` → merge into item → `Switch - Clarify or Auto`.
- `Code - Build Order State` merges fetched header into **empty** fields only; message + Chatwoot attributes win. Sex-only phrases (e.g. “any sex”) now set `should_enrich_existing_draft` without requiring order-intent gates on `msgSex`.
- `Code - Slim Sales Agent User Context` reads `results` or `sync_results`; sets `had_partial` / `partial_fulfillment` in `sam_steward_result_compact`.
- Sam system prompt: **PARTIAL STOCK SYNC** guidance when steward compact shows short allocation.

**Docs:** `DATA_FLOW.md`, `API_STRUCTURE.md`, `ORDER_LOGIC.md`.

Status: implemented in repo exports; **re-import both workflows to n8n** and run live tests (partial stock 6 vs 5, sex-only reply, Cash then send for approval).

### 2026-04-30 - Phase 1.4 Bugfix C — Test C: Sam Still Overstating On Backend 400 Path

Type: `FIX`

Component: `1.0 - SAM - Sales Agent - Chatwoot`, `1.2 - Amadeus Order Steward`

Change:

- `1.2 Set - Format Send for Approval Result` — replaced the `backend_error` expression with an IIFE that correctly parses the `continueOnFail` error format. When n8n `continueOnFail` catches an HTTP 4xx, it passes `{"error": "400 - {JSON_BODY}"}` as a concatenated string — `$json.errors` is absent. The new expression tries `$json.errors[0]` first (success-path JSON), then regex-matches and JSON-parses the `"STATUS - {JSON}"` string from `continueOnFail` to extract `errors[0]`, then falls back to the raw string. Result: `backend_error` now contains a clean customer-safe message like `"Collection location is required before sending for approval."` instead of the raw `"400 - {\"errors\":[...]}"` string.
- `1.2 Set - Format Send for Approval Result` — fixed `order_id` null-on-failure. Added fallback: `$json.order_id || $node["Code - Normalize Order Payload"].json["order_id"]`. When the HTTP node fails, `$json` holds only `{error: "..."}` — `$json.order_id` is undefined. The fallback reads the order_id that was passed into the steward before the HTTP call.
- `1.0 Ai Agent - Sales Agent` user prompt `text` — added five fields after `OrderID`: `BackendSuccess`, `BackendError`, `BackendMessage`, `FinalOrderStatus`, `ReplyInstruction`. Previously these fields were only in the workflow result object but not exposed to Sam in the per-turn prompt, so Sam could not read them and the system prompt rules had no effect.
- `1.0 Ai Agent - Sales Agent` system prompt — replaced the two duplicate SEND_FOR_APPROVAL blocks (first block was weaker, second block was added in Bugfix A but created a duplicate) with a single hardened block. The new block adds: (a) a HARD RULE that explicitly forbids any form of "order was sent" wording when `BackendSuccess` is not exactly `"true"`; (b) instruction to read `BackendError` directly and explain the specific missing field to the customer; (c) instruction to follow `ReplyInstruction` if non-empty.
- `1.0 Set - Restore Send For Approval Result` — added `reply_instruction` field. When `backend_success !== true`, it computes a deterministic instruction string: `"INSTRUCTION: Do not say the order was sent for approval. The backend returned: [backend_error]. Tell the customer what is needed. Do not mention sending for approval."` When `backend_success === true`, the field is empty. This gives Sam an unambiguous per-turn override that does not depend on nuanced rule interpretation.

Root cause:

Three compounding issues:
1. `continueOnFail` wraps the HTTP error as a string `"400 - {JSON}"` — `$json.errors` is undefined, so the Bugfix B fallback chain hit `$json.error` and returned the raw string instead of the clean message.
2. `$json.order_id` is undefined when `continueOnFail` fires — the Format node output contained `order_id: null`, which propagated to Sam and Chatwoot.
3. `BackendSuccess` and `BackendError` existed as workflow fields but were absent from the Sales Agent user prompt `text`, so Sam received no per-turn signal and the system prompt SEND_FOR_APPROVAL rules could not be applied.

Expected outcome:

On a forced backend 400 (e.g., Collection_Location blank): `backend_error` = `"Collection location is required before sending for approval."`, `order_id` = correct order ID (not null), Sam's user prompt contains `BackendSuccess: false` and `BackendError: Collection location...` and `ReplyInstruction: INSTRUCTION: Do not say...`. Sam tells the customer what is missing and does not say the order was sent.

Status: implemented; pending live re-verification of Test C

### 2026-04-30 - Phase 1.4 Bugfix B — Backend 400 Not Handled In 1.2

Type: `FIX`

Component: `1.2 - Amadeus Order Steward`

Change:

- `1.2 HTTP - Send for Approval` — added `continueOnFail: true` at the node root level. `neverError: true` in options alone was not preventing n8n from surfacing the 400 as a workflow error; `continueOnFail` catches it at the execution level as a fallback.
- `1.2 Set - Format Send for Approval Result` — fixed `backend_error` expression to read `$json.errors[0]` (backend route returns `errors: []` array on 400, not `error: ""`) with fallback chain: `$json.errors[0]` → `$json.error.message` (n8n continueOnFail object format) → `$json.error` (string) → `$json.message` → `""`. Fixed `success` expression to always return `"true"` or `"false"` rather than `"undefined"` when n8n error format omits the field.

Root cause:

Two separate issues combined to silence Sam on 400:
1. `neverError: true` did not prevent the HTTP node from throwing; downstream Format node never ran.
2. Backend route returns `{"success": false, "errors": ["..."]}` (plural array) but the Format node read `$json.error` (singular string) — always undefined even if the response was received.

Expected outcome:

When backend returns 400 (e.g., Collection_Location missing), the Format node runs, `backend_success = false`, `backend_error` contains the first error string from the backend, and Sam can tell the customer what is missing.

Status: implemented; needs live re-verification of Test C (forced backend 400 path)

### 2026-04-30 - Phase 1.4 Bugfix — SEND_FOR_APPROVAL Intent Detection And Sam Reply Guard

Type: `FIX`

Component: `1.0 - SAM - Sales Agent - Chatwoot`

Change:

- `1.0 Code - Build Order State` — replaced single-regex `sendForApprovalIntent` with a multi-pattern check that covers natural phrasings including "send it for approval", "send this for approval", "send it through", "send this through", "submit it", "submit this", "submit my order", "go ahead and submit", "ready for approval", "ready to submit", "finalise it/this/the order", "confirm the order/my order/this order". Previous regex only matched "send for approval" as a complete phrase and missed any phrasing with "it" or "this" inserted.
- `1.0 Code - Decide Order Route` — moved SEND_FOR_APPROVAL check to before UPDATE_HEADER_AND_LINES and UPDATE_HEADER_ONLY in the route priority chain. Previously SEND_FOR_APPROVAL was the last check before REPLY_ONLY; if the message carried enrichable order data (e.g., from memory hydration), it could incorrectly route to an update instead of approval submission.
- `1.0 Ai Agent - Sales Agent` system prompt — added explicit SEND_FOR_APPROVAL case to the ORDER ACTION CONTEXT section. Sam must: (a) on `backend_success=true` say the order has been sent for approval but NOT approved; (b) on `backend_success=false` explain what is missing using `backend_error`; (c) on `OrderAction=REPLY_ONLY` when customer asked to send for approval, not claim any submission happened — instead explain what is needed or say the details need to be confirmed first.

Reason:

Live test with "Yes, please send it for approval" showed `send_for_approval_intent = false` because the previous regex required the exact phrase "send for approval" without any intervening words. Sam routed to REPLY_ONLY and incorrectly told the customer "Your draft order will be sent for approval now" — a false statement since no backend action ran.

Expected outcome:

"Yes, please send it for approval", "send it through", "please submit my order" and similar phrasings all set `send_for_approval_intent = true`. If all prerequisites are met, the route goes to SEND_FOR_APPROVAL. Sam only confirms approval submission after backend confirms success.

Status: live-reverified 2026-04-30. Test phrase "Yes, please send it for approval" set `send_for_approval_intent = true`, routed to `SEND_FOR_APPROVAL`, returned `backend_success = true`, wrote Chatwoot `order_status = Pending_Approval`, and Sam replied that the order was sent for approval without saying it was approved.

### 2026-04-29 - Phase 1.4 — Wire Send For Approval From Sam

Type: `ADD`

Component: `modules/orders/order_service.py`, `1.0 - SAM - Sales Agent - Chatwoot`, `1.2 - Amadeus Order Steward`

Change:

- `modules/orders/order_service.py send_order_for_approval` — replaced the three separate status-block checks with a single `old_status != "Draft"` guard. Added prerequisite validation: `Payment_Method` must be `Cash` or `EFT`; `Customer_Name` must be non-empty; `Collection_Location` must be non-empty; at least one non-cancelled `ORDER_LINE` must exist for the order.
- `1.2 HTTP - Send for Approval` — added `neverError: true` to options so `400` backend errors are returned as data instead of throwing an exception and silencing Sam.
- `1.2 Set - Format Send for Approval Result` — changed `order_status` from hardcoded `"Pending_Approval"` to `$json.success === true ? 'Pending_Approval' : 'Draft'`. Changed `approval_status` to conditional. Added `backend_success` (boolean) and `backend_error` (string) fields so `1.0` can pass error context to Sam.
- `1.0 Code - Build Order State` — added `sendForApprovalIntent` detection from customer phrases (`send for approval`, `submit order`, `finalise order`, `confirm order`, `ready for approval`, `please submit`, `ready to submit`). Added `send_for_approval_intent` to `orderState`.
- `1.0 Code - Decide Order Route` — added `existingOrderStatus`, `paymentMethod`, `paymentMethodSet`, `sendForApprovalIntent`, and `sendForApprovalReady` variables. Added `SEND_FOR_APPROVAL` route: fires when intent is detected, draft exists, order is in Draft status, and payment method is set. If payment method is missing, falls through to `REPLY_ONLY` so Sam can ask the customer for Cash/EFT. Added `debug_send_for_approval_intent`, `debug_send_for_approval_ready`, `debug_payment_method_set` debug fields.
- `1.0 Switch - Route Order Action` — added SEND_FOR_APPROVAL rule at index 6. REPLY_ONLY shifted to index 7.
- `1.0` — four new nodes added: `Set - Build Send For Approval Payload` → `Call 1.2 - Send For Approval` → `HTTP - Set Chatwoot After Send Approval` → `Set - Restore Send For Approval Result` → `Merge - Final Replay Context` (index 1).
- `HTTP - Set Chatwoot After Send Approval` writes full attribute snapshot: uses `order_status` from `1.2` result (conditional: `Pending_Approval` on success, existing status on failure), clears `pending_action`, preserves `payment_method`.

Reason:

Phase 1.3 captured the payment method. Phase 1.4 completes the customer-initiated send-for-approval path. Sam can now route from customer message through `1.2` to the backend, which validates all prerequisites before changing the order status. Backend errors return a customer-safe path — Sam receives `backend_success: false` and `backend_error` and can explain what is missing.

Expected outcome:

When a customer says "please send for approval" (with payment method set, draft active, and order lines present), Sam routes to SEND_FOR_APPROVAL. The backend validates all prerequisites and moves the order to `Pending_Approval`. The Chatwoot attribute is updated to `order_status = Pending_Approval`. If the backend returns a 400 (e.g., payment method missing on the sheet), Sam receives the error message and can tell the customer what is needed. Sam never says the order is approved — only that it has been sent for approval.

Status: happy path live-verified 2026-04-30 with `ORD-2026-377DA3`. Remaining regression checks: missing `Payment_Method`, already `Pending_Approval`, and backend `400` customer-safe reply path.

### 2026-04-29 - Phase 1.3 — Payment Method Capture

Type: `ADD`

Component: `modules/orders/order_service.py`, `1.0 - SAM - Sales Agent - Chatwoot`, `1.2 - Amadeus Order Steward`, `1.1 - SAM - Sales Agent - Escalation Telegram`

Change:

- `modules/orders/order_service.py update_order` — accepts `payment_method` field. Validates value must be `Cash` or `EFT`. Rejects update if `Order_Status` is not `Draft`. Maps to `Payment_Method` column in `ORDER_MASTER`.
- `1.0 Code - Normalize Incoming Message` — reads `payment_method` from `conversation.custom_attributes` and exposes it as `PaymentMethod`.
- `1.0 Code - Build Order State` — detects payment method keywords in the current message (`cash` → `Cash`, `eft`/`bank transfer`/`electronic transfer`/`internet banking` → `EFT`). Adds `payment_method` (from stored attribute) and `detected_payment_method` (from current message) to `order_state`. Includes `detectedPaymentMethod !== ""` in `messageHasNewUsefulInfo`.
- `1.0 Code - Build Enrich Existing Draft Payload` — forwards `detected_payment_method` as `payment_method` in the enrich payload when it is `Cash` or `EFT`. Includes it in `sentFieldCount` and return.
- `1.0` — all Chatwoot attribute write nodes updated to include `payment_method` in every write: `HTTP - Set Conversation Order Context`, `HTTP - Set Conversation Context After Update`, `HTTP - Clear Pending After Cancel`, `HTTP - Set Pending Cancel Action`, `HTTP - Clear Pending Action`, `HTTP - Set Conversation Human Mode`.
- `1.0 HTTP - Set Conversation Context After Update` — new update/enrich-path Chatwoot mirror node. It writes the full attribute snapshot after `update_order`, using the newly captured payment method before falling back to the previously stored Chatwoot value.
- `1.0 Edit - Build Ticket Data` — adds `WebPaymentMethod` field from `Code - Normalize Incoming Message`.
- `1.0 Google Sheet - Append row in sheet` — adds `WebPaymentMethod` to `columns.value` and schema.
- `1.2 Code - Normalize Order Payload` — adds `payment_method: clean(input.payment_method)`.
- `1.2 Code - Build Update Order Payload` — forwards `payment_method` to `patch_body` when it is `Cash` or `EFT`. Includes in `updatableFieldCount`.
- `1.1 Release Conversation to Auto` — adds `payment_method: $('Get Ticket Detail').item.json.WebPaymentMethod || ""` to the Chatwoot attribute snapshot.

Reason:

Payment method (`Cash` or `EFT`) is required before `send_for_approval` (Phase 1.4). It must be captured from the customer conversation, stored on `ORDER_MASTER`, and mirrored to Chatwoot so it survives across escalation and multi-turn conversations. The VAT treatment on quotes and invoices depends on this field.

Expected outcome:

When a customer says "I'll pay cash" or "EFT", Sam detects it via `Code - Build Order State`, routes through `ENRICH_EXISTING_DRAFT`, and the backend stores `Payment_Method = Cash` (or `EFT`) on `ORDER_MASTER`. All Chatwoot attribute writes preserve the value so it is not erased by later turns. The field survives escalation via `WebPaymentMethod` in `Sales_HumanEscalations`.

Status: live-verified 2026-04-29. Cash and EFT capture both update `ORDER_MASTER.Payment_Method` and Chatwoot `payment_method`; next-turn readback works; cancel-pending and escalation preserve the field; backend lock guard returns `400` and leaves the sheet value unchanged once the order is beyond `Draft`; no-draft handling does not write payment method without an active order.

### 2026-04-29 - Fix C Option B1 — Create Order With Lines (Atomic)

Type: `FIX`

Component: `1.0 - SAM - Sales Agent - Chatwoot`, `1.2 - Amadeus Order Steward`

Change:

- `1.0 Set - Draft Order Payload` — `action` field is now a conditional expression: sends `create_order_with_lines` when `order_state.requested_items[]` is non-empty, otherwise sends `create_order`.
- `1.0 Set - Draft Order Payload` — new `requested_items` field forwards `order_state.requested_items` to `1.2`.
- `1.0 Code - Store Draft Order Context` — jsCode reverted to simple pass-through (no cross-node reference). Fans out directly to `HTTP - Set Conversation Order Context` (index 0) and `Merge - Draft Result With Reply Context` (index 1).
- `1.2 Switch - Route by Action` — new rule at index [11] matching `action === create_order_with_lines`, output key `Create Order With Lines`.
- Five new nodes added to `1.2` forming the `create_order_with_lines` branch: `Set - Build Create With Lines Body` → `HTTP - Create With Lines Order` → `Code - Build Sync After Create Payload` → `HTTP - Sync New Draft Lines` → `Code - Format Create With Lines Result`.
- `Code - Format Create With Lines Result` — top-level `success` requires both `create_success === true` AND `syncResp.success === true`. Sam will not confirm the order if sync fails.
- Previous Fix C Option A nodes removed from `1.0`: `IF - Draft Has Requested Items`, `Code - Build Sync New Draft Lines Payload`, `Call 1.2 - Sync New Draft Lines`, `Code - Restore Draft Sync Result`.

Reason:

First-turn committed orders with `requested_items[]` were creating `ORDER_MASTER` only. `ORDER_LINES` were not created until a later update path. Fix C Option A added a post-create sync branch inside `1.0`, but this violated the `1.0`/`1.2` ownership boundary. Option B1 moves the full create+sync operation into `1.2` as a single atomic action, keeping `1.0` as a router only.

Expected outcome:

When Sam routes to `CREATE_DRAFT` and `requested_items` is non-empty, `1.2` creates the draft and syncs order lines atomically. `success=true` guarantees both operations completed. Sam's reply references the order ID and the lines are present in `ORDER_LINES` before Sam replies.

Follow-up (separate, not part of this fix):

The Sales Agent AI receives a large merged payload. A future `Code - Build Sales Reply Context` node could slim this to only what Sam needs for her reply (order_id, order_status, sync_results summary, customer context).

Status: live-verified 2026-04-29. `ORD-2026-879091` created in Draft; `ORDER_LINES` has 3 rows with `exact_match` / `matched_quantity=3` / `request_item_key=primary_1`. Sam's reply referenced the order ID.

### 2026-04-29 - Fix C Option A — Superseded

Type: `REMOVE`

Component: `1.0 - SAM - Sales Agent - Chatwoot`

Change:

Nodes `IF - Draft Has Requested Items`, `Code - Build Sync New Draft Lines Payload`, `Call 1.2 - Sync New Draft Lines`, `Code - Restore Draft Sync Result` were implemented in `1.0` as a post-create sync branch but were removed before going live.

Reason:

Superseded by Fix C Option B1. Placing create+sync logic inside `1.0` violated the `1.0`/`1.2` ownership boundary. Option B1 moves the full operation into `1.2` as a single action.

Status: removed — never live-tested. See Fix C Option B1 above.

### 2026-04-29 - Chatwoot Attribute Register Added

Type: `DOCS`

Component: `docs/04-n8n`

Change:

- Added `CHATWOOT_ATTRIBUTES.md` as the canonical register for Chatwoot conversation attributes, contact attributes, and labels.
- Documented the full-object replacement risk for Chatwoot conversation custom attributes.
- Documented active attribute writes in `1.0` and `1.1`.
- Documented outstanding risks for `1.3` media attribute writes and label endpoint behavior.

Reason:

Live testing showed multiple failures caused by partial Chatwoot custom attribute writes erasing order context. The workflow suite needs one source of truth before adding more order behavior.

Expected outcome:

Future changes can verify Chatwoot labels and custom attributes against one documented contract before import or live testing.

Status: documented; `1.1` expression-safe release verified 2026-04-29

### 2026-04-29 - Phase 1.2c Escalation Path Attribute Fix

Type: `FIX`

Component: `1.0 - SAM - Sales Agent - Chatwoot`, `1.1 - SAM - Sales Agent - Escalation Telegram`

Change:

- Fixed `HTTP - Set Conversation Human Mode` in `1.0` — now writes all seven Chatwoot fields including `order_id`, `order_status`, `pending_action` on escalation. Previously only wrote four escalation-specific fields, erasing order context.
- Fixed `Edit - Keep Chatwoot ID's` in `1.0` — now carries `existing_order_id`, `existing_order_status`, `conversation_mode` forward so the Escalation Classifier has order context.
- Updated `Ai Agent - Escalation Classifier` user prompt in `1.0` — now includes `ExistingOrderId`, `ExistingOrderStatus`, `PendingAction` so the classifier can make order-aware routing decisions.
- Updated `Ai Agent - Escalation Classifier` system prompt in `1.0` — added cancel routing rule: if `ExistingOrderId` is present and customer asks to cancel, route to AUTO (not ESCALATE).
- Updated `Edit - Build Ticket Data` in `1.0` — now writes `WebOrderId`, `WebOrderStatus`, `WebPendingAction` to the `Sales_HumanEscalations` sheet at escalation time.
- Fixed `Release Conversation to Auto` in `1.1` — now reads `WebOrderId`, `WebOrderStatus`, `WebPendingAction` back from the escalation sheet and preserves them in the Chatwoot reset. Previously wrote only `conversation_mode: AUTO`, erasing all order context when the human replied.

Reason:

If a customer was escalated and the human did not immediately reply, the customer's next message arrived with empty order context — `ExistingOrderId` was blank, routing logic could not find the active order, and the system could incorrectly create a new draft instead of recognising the existing order. A cancel request during or after an escalation would also incorrectly route to ESCALATE rather than through the cancel confirmation flow.

Expected outcome:

Order context (`order_id`, `order_status`, `pending_action`) survives through escalation and human reply. The Escalation Classifier will not escalate routine cancel requests when an active order is present.

Status: live-verified 2026-04-29. `Sales_HumanEscalations` preserved `WebOrderId`, `WebOrderStatus`, and `WebPendingAction`; `1.1` restored Chatwoot attributes with real evaluated values; a follow-up customer cancellation routed through `AUTO` and `CANCEL_ORDER` successfully.

### 2026-04-29 - Phase 1.2b Live Test Fixes

Type: `FIX`

Component: `1.0 - SAM - Sales Agent - Chatwoot`, `1.2 - Amadeus Order Steward`

Change:

- Fixed `1.2` Switch node connection array — `cancel_order` was routed to the `add_order_line` path due to incorrect positional indexing. Re-indexed all 11 connections.
- Fixed three cancel-path Chatwoot write nodes in `1.0` (`HTTP - Set Pending Cancel Action`, `HTTP - Clear Pending Action`, `HTTP - Clear Pending After Cancel`) to always write all four core attribute fields, preventing `order_id` erasure.
- Added safety guard in `Code - Decide Order Route` — blocks `CREATE_DRAFT` route when `pending_action = cancel_order` but `existing_order_id` is empty, preventing accidental draft creation during a broken cancel confirm.
- Fixed CREATE_DRAFT order_id data flow — `Code - Store Draft Order Context` now fans out directly to both `HTTP - Set Conversation Order Context` (leaf) and `Merge - Draft Result With Reply Context` (index 1). This ensures `order_id` from the 1.2 result reaches the AI agent prompt. Previously the HTTP node sat between them and replaced `$json` with the Chatwoot API response before the merge.

Reason:

Live test after initial Phase 1.2b wiring revealed four separate bugs: wrong Switch routing in 1.2, order_id erasure on CANCEL_PENDING, order_id absent from AI agent prompt after CREATE_DRAFT, and missing guard for cancel confirm with empty order.

Expected outcome:

Two-turn cancel flow works end-to-end. Sam correctly references order ID in draft creation reply. Cancel confirmation cannot accidentally trigger CREATE_DRAFT.

Status: live-verified. Sam correctly referenced order ID after CREATE_DRAFT. Cancel confirmation cannot accidentally trigger CREATE_DRAFT. Cancel flow was re-tested after escalation fixes and successfully cancelled `ORD-2026-367706`.

### 2026-04-27 - Phase 1.2b Customer Cancel Wired Into n8n

Type: `ADD`

Component: `1.0 - SAM - Sales Agent - Chatwoot`, `1.2 - Amadeus Order Steward`

Change:

- Added `cancel_order` handling to `1.2` with `reason`, backend cancel endpoint call, and formatted cancel result.
- Added guarded customer-cancel routing to `1.0` using `CANCEL_PENDING`, `CANCEL_ORDER`, and `CLEAR_PENDING`.
- Added Chatwoot `pending_action = cancel_order` confirmation state and clear paths.
- Updated protected workflow docs and live action lists to include `cancel_order`.

Reason:

Customer cancellation must be handled through backend truth, not direct sheet edits or unconfirmed Sam replies.

Expected outcome:

Sam asks for one confirmation before cancelling, calls the backend only after confirmation, and only tells the customer the order is cancelled after backend success.

Status: implemented in exports; needs live n8n import and two-turn verification

### 2026-04-27 - Four Workflow Suite Documented

Type: `DOCS`

Component: `docs/04-n8n`

Change:

- Documented the n8n workflow suite as four workflows: `1.0`, `1.1`, `1.2`, and `1.3`.
- Rewrote the root n8n docs around suite flow, data contracts, node responsibilities, workflow rules, and protected logic.
- Confirmed `1.0 - SAM - Sales Agent - Chatwoot` as the customer-facing hub.
- Confirmed `1.1 - SAM - Sales Agent - Escalation Telegram` as the human reply bridge.
- Confirmed `1.2 - Amadeus Order Steward` as the order action worker.
- Confirmed `1.3 - SAM - Sales Agent - Media Tool` as the official media workflow number.

Reason:

The workflow documentation needed to reflect all uploaded workflow exports, not only the original `1.0` flow.

Expected outcome:

Future backend, AI, and n8n changes can use the `04-n8n` docs as the workflow source of truth.

Status: documented

### 2026-04-27 - Media Tool Kept Disabled

Type: `DOCS`

Component: `1.3 - SAM - Sales Agent - Media Tool`

Change:

- Documented `1.3` as the official media tool workflow.
- Documented that `Send_Pictures` should remain disabled until the media workflow is fixed and tested.
- Noted that the raw `1.0` workflow export still contains cached n8n metadata naming the media tool as `1.2`; this should be corrected in n8n on the next workflow update/export.

Reason:

The media tool is useful but not ready for customer use.

Expected outcome:

Sam will not send media until the workflow is explicitly enabled after review.

Status: planned/future fix

### 2026-04-27 - Order Review Direction Confirmed

Type: `DOCS`

Component: `1.0` and `1.2`

Change:

- Documented the preferred future order-review path: Sam should request order context through `1.2 - Amadeus Order Steward` and backend APIs rather than directly reading `ORDER_OVERVIEW` as a production tool.
- Documented direct `ORDER_OVERVIEW` read access as diagnostic or possible fallback, not the preferred build direction.

Reason:

Backend-mediated order review gives better customer matching, filtering, privacy, and testability.

Expected outcome:

Future order context work should add or improve backend/order-steward review actions instead of giving Sam uncontrolled sheet access.

Status: approved direction

### 2026-04-27 - Live Order Steward Actions Scoped

Type: `DOCS`

Component: `1.2 - Amadeus Order Steward`

Change:

Documented only these actions as currently live for `1.0`:

- `create_order`
- `update_order`
- `sync_order_lines_from_request`

Reason:

The steward workflow contains more capability than `1.0` currently uses. The docs should not imply all steward actions are active Sam tools.

Expected outcome:

Future actions can be enabled one at a time with explicit testing and documentation.

Status: documented

### 2026-04-27 - Telegram Cleanup Desired

Type: `IMPROVEMENT`

Component: `1.1 - SAM - Sales Agent - Escalation Telegram`

Change:

Documented Telegram message cleanup after human reply as a desired improvement.

Reason:

The human handoff channel should not remain cluttered after a ticket is answered.

Expected outcome:

Future work should safely delete only the relevant Telegram messages after reply, without deleting unrelated messages.

Status: planned

### 2026-04-27 - Private Repo Export Detail Accepted

Type: `DOCS`

Component: workflow exports

Change:

Confirmed that workflow exports and READMEs may keep full local technical detail because this repository is private.

Reason:

Detailed exports make the system easier to rebuild and debug locally.

Expected outcome:

No redaction pass is required for current private documentation. If the repository is shared or made public, credentials and tokens must be redacted or rotated.

Status: accepted for private repo

## Historical Notes

The older 2026-04 stabilization work focused mainly on `1.0` reply integrity:

- CLARIFY path should preserve the AI Sales Agent response.
- `ai_reply_output` protects useful AI replies from merge/composer overwrites.
- `cleaned_reply` is the safe final outbound field for `1.0` customer replies.
- Merge nodes and the generic `output` field remain high-risk areas.

## Entry Template

```text
Date:
Workflow/component:
Type:
Change:
Reason:
Expected outcome:
Status:
```
