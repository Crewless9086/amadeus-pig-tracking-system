# CONTROL TOWER FEEDBACK HANDOVER — SAM PR #1163 canonical attribution repair

```json
{
  "contract_version": "core_mission_outcome_handover_v1",
  "handover_id": "SAM-PR1163-CANONICAL-ATTRIBUTION-REPAIR-20260822",
  "mission_id": "existing SAM five-customer livestock recovery mission",
  "reporting_actor_type": "terminal",
  "terminal_disposition": "source_repaired_and_current_main_focused_tests_passed_awaiting_independent_review",
  "requested_lifecycle": "REVIEW_HOLD",
  "technical_milestones": ["source_ready", "tests_passed", "pr_open"],
  "applicability": {
    "operational_actor": "required",
    "genuine_trigger": "required",
    "loaded_revision": "required",
    "canonical_readback": "required",
    "provider_result": "required",
    "physical_or_customer_result": "required",
    "later_independent_cycle": "required",
    "safe_final_state": "required",
    "replay_and_concurrency_containment": "required",
    "automatic_follow_up_or_unresolved_work_ownership": "required",
    "owner_work_removal": "required"
  },
  "evidence": {},
  "next_safe_stage": "different-agent independent review of the exact PR head and BEACON dependency classification",
  "hold": {
    "type": "EXTERNAL_HOLD",
    "owner": "independent SAM reviewer and GitHub exact-head checks",
    "reason": "source repair is not a released or accepted customer outcome",
    "wake_condition": "exact-head CI passes and an independent reviewer accepts the canonical-binding and fail-only-attribution behavior",
    "automatic_continuation_trigger": "Control Tower reassesses the same SAM lineage for the serialized release lane"
  }
}
```

## Governance preflight

- Worktree, branch and implementation HEAD before this packet commit: `C:/tmp/sam-five-customer-recovery-20260822`; `fix/sam-five-customer-recovery-20260822`; `8caa78e41a57113a5f62a8770348f7a068f661bb`.
- Original independently rejected PR head: `d578e8322097258be3b804b3857fb5cd1917ede5`.
- Upstream and ahead/behind current authoritative main: `origin/main=d149e8009c164de95dce16db42d340bf5dead05c`; `0 behind / 3 ahead` at implementation HEAD.
- Mission Standard: tracked blob `3002b94713e286c4eb2019419c438cc378c337fa`; filesystem SHA-256 `44E34C69145B83D2CD5B6A5322A6C2C124789FA647E19F19B3E39A7293A5202B`; 1,127 lines; read completely.
- Control Tower Protocol: tracked blob `8fbd0b9c9160164e31a17a2cbfa51ab88792a909`; filesystem SHA-256 `D4EB4B54A660CE39DFC92CB0FA253B0F2E3D7314462984702602D0F4B66A7E0A`; 319 lines; read completely.
- Runtime Programme: tracked blob `fb44d7f86c47e605c283ed33c28ba2c4267d6edb`; filesystem SHA-256 `721281EEACC33AE11877CE610FE7A76BA06DE6B75DB4573F64933073FD358309`; 278 lines; read completely.
- Feedback template: tracked blob `1233aee625e45821a685614a33b1eb101c666ffd`; 266 lines; read completely.
- Focused authority: Brain Guard, active source map, common governance pack, SAM identity and live-stock workflow/rules, customer response and outbound delivery standards, BEACON identity/campaign/live-stock workflows, marketing rules and media privacy rules; read completely.
- Authoritative-main comparison: the three existing PR commits were rebased cleanly after a fresh fetch onto `d149e800`; focused tests and Brain Guard were rerun after that rebase.
- Worktree status: clean at implementation commit; this tracked packet is the only intended subsequent source-tree addition.
- Feedback observation date: 2026-08-22, Africa/Johannesburg.

## Mission identity and owner outcome

- Existing mission ID: the durable register calls this the existing SAM five-customer mission; no new mission was created or reprioritized.
- Owner-visible outcome: after governed release, a supported genuine Facebook livestock reply retains campaign context only when exact canonical BEACON publication truth verifies it, while an ordinary supported reply continues without campaign attribution when that proof is absent.
- Explicit non-outcomes: source, tests, commit, PR, merge, deployment, health, synthetic input or a terminal-created response are not a customer or owner outcome.
- Lifecycle: `REVIEW_HOLD`; customer outcome achieved: `NONE`; automatic customer sending remains outside this terminal's authority.
- Remaining acceptance: independent review; exact-head CI; serialized merge/deploy decision; exact loaded revision; genuine provider trigger; canonical/provider readback; supported SAM response; follow-up; five-customer proof; later terminal-independent cycle; measured owner-work reduction.
- Strategic class: existing `CURRENT_BLOCKER` lineage; no change to Control Tower WIP priority.
- Exact recurring owner action targeted: manually interpreting a Facebook reply without trustworthy campaign context and manually repeating the relevant product context.
- Current/target manual steps: not yet measured in production; target is one genuine customer message followed by SAM's supported useful response and automatic follow-up.
- Terminal-independent closure proof: a later genuine Meta event and subsequent automatic SAM cycle after all development terminals close.
- Deployed-agent enablement: this terminal changed and tested source only; it did not send a customer response or create provider/canonical business effects.

## Terminal state

- Visible development terminal: active through push and handover, then releasable for independent review.
- Last instruction: repair PR #1163's independent-review blocker on its existing lineage, preserve ordinary Facebook processing and record the BEACON dependency without broadening scope.
- Delivery proof: delivered, acknowledged, source/test progress observed.
- Worktree/current action: dedicated isolated worktree above; exact existing PR branch.
- Last terminal-invoked cycle: local read-only source tests only; no production call, provider send or database write.
- What stops when this terminal closes: editing and local tests only.
- Fresh progress: implementation commit `8caa78e4`; 346 tests passed, 150 subtests passed; deterministic vault alignment passed with zero findings.
- Active-work basis: tracked source/test diff, commit and handover artifact; no background-runtime claim.

## Deployed agent operational reality

- Exact deployed revision: not inspected and not changed by this terminal.
- Web/API health, SAM worker identity, provider trigger, heartbeat, supervisor, last independent cycle, canonical result and next cycle: `Unknown` for this source-only repair.
- Production authority mode: automatic customer sending was reported OFF in the durable register; no authority change was made here.
- Terminal-independence proof: no deployed process depends on this worktree.
- Honest classification: `authority-disabled / repair-not-deployed` for this journey.

## Agent execution ownership

- Operational actor: the deployed SAM livestock runtime, after a governed future release.
- Genuine trigger: a customer-created Facebook/Chatwoot inbound event, `created_by_terminal:false`.
- Customer channel: the existing Facebook/Chatwoot provider rail.
- Terminal-permitted actions: source repair, tests, PR update and handover.
- Terminal-forbidden substitutions: customer message, provider send, lead/order write, production mutation, acceptance manufacture, merge or deployment.
- Required agent-origin proof: exact loaded revision, provider-origin inbound event, canonical BEACON binding when attribution is claimed, SAM provider result, follow-up and later independent cycle.
- Terminal-created operational output: no; fixtures are test evidence only.
- If this terminal closes: the source remains in PR #1163; no customer operation is kept alive.

## Evidence classification

- Documented facts: the independent review rejected exact head `d578e832` because authoritative expected Meta bindings were not supplied at the production call path.
- Source facts: `resolve_canonical_meta_publication_binding` now reads the existing BEACON execution/binding/claim/consumer truth; the evaluator requires successful resolution and exact page, post, attribution and chronology matches; rejected attribution contributes no campaign IDs, text or SAM boundary.
- Runtime-loaded facts: none established.
- Canonical/database facts: no production readback or mutation occurred. Resolver behavior is proven with a read-only fake connection and exact existing-table assertions.
- Provider facts: none newly observed or changed.
- Physical/customer facts: none newly observed or changed.
- Unknown/contradictory: current deployed revision, live binding rows and genuine customer behavior remain Unknown pending release and acceptance.

## Fresh execution epoch

- Historical rejected identity: PR #1163 head `d578e832` remains immutable review evidence and is not acceptance evidence.
- Reusable defect repaired: payload-supplied values can no longer grant attributed campaign context without one exact canonical binding and valid chronology.
- Fresh evidence source/new identity: a future genuine customer-created Meta event after governed deployment.
- Why no replay: this turn used fixtures only and created no provider/customer/business event.
- Later terminal-independent proof: required after release; none claimed.

## Implementation and exact defect closure

- Added `modules/beacon/publication_attribution.py`: a read-only canonical resolver. The inbound post ID is only a lookup candidate; configured page identity and exact existing BEACON execution/claim/consumer or organic-binding truth determine the result.
- Updated `modules/sales/sam_meta_inbound.py`: successful canonical binding plus exact page/post/attribution/publication chronology is mandatory before `status=attributed`; missing, mismatch, stale, pre-publication and invalid chronology all fail attribution closed.
- Updated `modules/sales/sam_live_stock_runtime.py`: the real Chatwoot parser resolves canonical truth, uses canonical BEACON text only when attributed and carries the proven context into the final canonical evidence-to-offer packet.
- Ordinary Facebook preservation: attribution rejection empties only campaign/referral context. Existing provider chronology can still classify the ordinary reply window as `ordinary_reply_allowed`.
- No new ledger, queue, scheduler, authority rail, provider adapter or writable canonical store was added.

## Explicit BEACON dependency — separate smallest follow-up

- Producer: `execute_beacon_facebook_page_post` returns `provider_readback_confirmed=true` inside `outcome_json.facebook_result` (`modules/sales/beacon_campaign.py`).
- Consumer: `protected_publication_worker._record_consumer_event` reads `outcome.get("provider_readback_confirmed")` at the top level (`modules/beacon/protected_publication_worker.py`).
- Consequence: a real protected publication can report successful provider readback yet fail to record a confirmed protected consumer row. The canonical SAM resolver therefore correctly finds no protected binding and refuses to promote campaign context. Ordinary supported Facebook processing remains available.
- Test proof: `test_producer_consumer_readback_shape_mismatch_leaves_attribution_unresolved` simulates the producer/consumer shape and proves zero campaign promotion plus preserved ordinary message processing.
- Smallest separate follow-up recommendation: repair the BEACON publication-result contract in its existing mission so producer and consumer share one canonical readback shape; prove one confirmed consumer row is bound to the exact execution/post/provider readback and add regression coverage. Do not add another store or broaden PR #1163 into publication repair.

## Test and review evidence

- Current-main focused suite: 346 passed, 150 subtests passed, one existing ReportLab deprecation warning.
- Included files: `test_sam_meta_inbound`, `test_sam_whatsapp_provider_identity`, `test_sam_customer_front_door`, `test_sam_live_stock_runtime`, `test_beacon_organic_publication_binding`, `test_beacon_protected_publication_worker`, `test_beacon_campaign`.
- Positive proof: exact resolved attribution reaches front-door context and the final evidence-to-offer packet.
- Negative proof: wrong/missing page, post, attribution, publication time, inbound time, pre-publication, stale chronology and unavailable canonical truth cannot promote context.
- Containment proof: unavailable/mismatched binding rejects only attribution and preserves an ordinary supported Facebook reply window.
- Brain Guard: `python scripts/audit_vault_alignment.py` passed with zero findings.
- Diff hygiene: `git diff --check origin/main...HEAD` passed.
- Full local repository suite: not claimed. Collection is blocked by missing `yaml` in the shared environment for unrelated current-main Green test `tests/test_green_print_home_assistant_app.py`; `requirements.txt` does not install PyYAML although its Green workflow does. A broad run excluding that collector was stopped during slow unrelated tests without an observed failure and is not counted as a pass.

## Effects and authority

- Database/farm/customer/provider/hardware effects: none.
- n8n or Google Sheets authority: none added.
- Protected authority used: none.
- Owner interaction requested: none.
- Governed evidence used instead of owner observation: tracked source, tests, git and GitHub PR metadata.
- Owner-burden defect: existing mission defect; source repair does not yet remove real owner work.
- Owner workload delta this turn: none.
- New recurring owner labour: none.
- Replay/concurrency: evaluator and resolver are deterministic/read-only; duplicate evaluation test passes. Production replay/concurrency proof remains required.

## Closeout and next action

- Owner-facing dispatch banner: `DO NOT SEND — TERMINAL ACTIVE` until exact-head checks and independent review resolve.
- Business result: `NO BUSINESS OUTCOME`.
- Exact blocker/owner: independent reviewer and GitHub exact-head checks; not Charl.
- Safe remaining work: push exact rebased head, observe CI, different-agent review, repair only any accepted blocker, then Control Tower release decision.
- Terminal/worktree closeout: retain the isolated worktree until independent review; no merge or deletion.
- Control Tower classification: `CONTINUE` existing SAM lineage.
- Exact next terminal: SAM LIVESTOCK INDEPENDENT REVIEW TERMINAL.
- Expected future result: genuine supported customer replies retain only verified canonical campaign context; ordinary replies remain usable when attribution is unavailable.
- Serialized release lane: not acquired by this source terminal; Control Tower owns later release sequencing.
- Durable-register proposal: append this source repair and BEACON dependency under the existing SAM five-customer mission without reprioritization; lifecycle stays `REVIEW_HOLD / NO BUSINESS OUTCOME`.

## Mandatory forward mission pipeline

- Intended role: deployed SAM handles eligible genuine livestock customer conversations and follow-up through existing provider/canonical rails.
- Already proven operationally: not reassessed here; source/fixture proof is not deployed-agent proof.
- Current mission: existing SAM five-customer recovery and terminal-independent operation.
- Next mission: no new mission promoted; after #1163 review, repair the smallest BEACON result-shape dependency in its existing publication lineage, subject to Control Tower collision/WIP sequencing.
- Later required stages: release, deployed revision proof, genuine customer acceptance, follow-up, five-customer set and later terminal-independent cycle.
- Dependencies/collisions: PR #1148 is an obsolete duplicate lineage and was inspected only, not touched; BEACON producer/consumer shape repair must remain separate; release lane is serialized.
- Automatic promotion trigger: exact-head CI and independent acceptance of PR #1163 return the lane to Control Tower release assessment.
- Latest owner priority change: none; finding logged without reprioritization.
- Register persistence: proposed to Control Tower; this isolated source terminal does not mutate the canonical register.

## Mandatory all-terminal closure gate

This specialist terminal cannot truthfully sweep the user's other visible terminals. Control Tower must freshly classify CORE, OOM SAKKIE, ROOTLINE, HERDMASTER, SAM, BEACON and CODEX UI. For this lane: SAM repair is active through exact-head CI/review; do not dispatch a duplicate implementation terminal. BEACON dependency is logged but must not pre-empt current Control Tower priority.

Mission lifecycle state: `REVIEW_HOLD`

Owner-visible outcome: none yet; target is useful supported Facebook handling with trustworthy canonical context and autonomous follow-up.

Technical stage reached: source repaired on rebased current main; focused tests and Brain Guard pass; PR push/checks and independent review remain.

Deployed-agent state: repair not deployed; automatic customer sending unchanged.

Last independent cycle: none for the repaired source.

Next automatic stage: exact-head GitHub checks, then independent review.

Terminal independence: no terminal process is required by the source; operational proof remains pending.

Decision: YES — send the exact PR head to a different-agent independent review after CI.

Why: the reviewed blocker is repaired without trusting payload identity, without breaking ordinary Facebook handling and without absorbing the separate BEACON producer/consumer defect.

Send this exact prompt to SAM LIVESTOCK INDEPENDENT REVIEW TERMINAL: Review PR #1163 at the exact head reported by Control Tower after this handover commit. Read the complete Mission Standard, Control Tower protocol and feedback template in a fresh isolated worktree. Independently challenge the read-only canonical BEACON publication resolver, configured page binding, one-row ambiguity handling, page/post/attribution identity, publication/inbound chronology, stale boundary, canonical-text retention and final evidence-to-offer propagation. Prove that every missing, mismatched, invalid or stale attribution case removes only campaign-derived context while preserving ordinary supported Facebook processing. Reproduce the protected-publication producer/consumer readback-shape mismatch as a separate BEACON dependency; do not repair it in #1163. Reconcile obsolete duplicate PR #1148 without modifying it. Run exact-current focused and appropriate wider tests. Return a complete Control Tower handover. Do not merge, deploy, send to a customer/provider, mutate production or call source/tests/PR a business outcome.

Expected business result: after later governed release and genuine acceptance, SAM can answer supported Facebook livestock enquiries with canonical campaign context when proven and without false attribution when it is not.
