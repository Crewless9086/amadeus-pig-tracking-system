# SAM + Beacon Meat Sales First Launch Readiness

Date: 2026-07-03
Mission type: supervised income-stream readiness
Scope: SAM Meat Sales, Beacon campaign/media, meat order/sales transactions, document/payment gates

## Decision

Status: not ready for uncontrolled public launch.

The code paths tested for SAM Meat Sales, Beacon campaign drafting, meat operations, fulfilment, reconciliation, sales transactions, orders, and reservation logic are passing. The current blockers are operational launch gates, not a core backend failure.

Controlled owner-supervised pilot is acceptable only after the owner reviews the exact campaign packet, chooses the first channel, and confirms the pilot cap. Public posting and customer messaging automation must stay locked until the missing gates below are cleared.

## Current Readiness

- Backend/code readiness: high.
- Safe public launch readiness: 60%.
- First controlled pilot readiness: possible with owner manual review, no automation, and strict pilot cap.
- Recommended launch mode: draft/review/manual-post evidence only until the Meta template and Beacon media gates are complete.

## Passed Verification

- `python -m unittest tests.test_sam_meat_runtime tests.test_beacon_campaign tests.test_meat_launch_readiness`
  - 82 tests passed.
- `python -m unittest tests.test_meat_ops tests.test_meat_fulfillment tests.test_meat_reconciliation tests.test_meat_price_book tests.test_meat_match_engine`
  - 41 tests passed.
- `python -m unittest tests.test_sales_transaction_read tests.test_sales_transaction_routes tests.test_order_routes tests.test_order_service_reservation`
  - 104 tests passed.
- `node --check static/js/beaconMedia.js`
  - Passed.

## Live Local Smoke Checks

- `/api/sales/meat-pilot-readiness?limit=12`
  - Status 200.
  - Pilot readiness 60%.
  - Next gate: `finish_template_and_payment_gates_before_public_boost`.
- `/api/beacon/facebook-posting-policy`
  - Status 200.
  - Facebook posting disabled.
  - `posts_text_only_now=false`.
  - `posts_media_now=false`.
  - `posts_image_now=false`.
  - `posts_publicly=false`.
  - `calls_meta=false`.
- `/api/beacon/campaign-draft-selection?limit=25`
  - Status 200.
  - Draft selection available.
  - Approved media count 0.
  - Next gate: `owner_selects_media_and_campaign_draft_before_any_public_post`.

## Launch Blockers

1. WhatsApp templates are not configured.
   - `MEAT_SALES_QUOTE_READY_TEMPLATE_NAME`
   - `MEAT_SALES_DEPOSIT_FOLLOWUP_TEMPLATE_NAME`
   - `MEAT_SALES_BOOKING_UPDATE_TEMPLATE_NAME`
   - `MEAT_SALES_DELIVERY_UPDATE_TEMPLATE_NAME`
   - `MEAT_SALES_FINAL_INVOICE_TEMPLATE_NAME`

2. Quote document gate is incomplete.
   - No current launch lead is ready to generate and send an estimated quote.

3. Deposit gate is incomplete.
   - No launch lead has `deposit_confirmed_in_bank`.

4. Fulfilment gate is incomplete.
   - No launch lead has confirmed stock commitment and deposit confirmation.

5. Beacon media gate is incomplete.
   - There are no owner-approved Beacon media assets for public use.
   - The only detected asset is a storage smoke test and must not be used for public launch.

6. Beacon Facebook posting is disabled.
   - This is the safe state until page credentials, owner confirmation, and exact post packet review are completed.

## Fix Applied During This Mission

Beacon Facebook posting policy now separates configured capability from active posting authority.

- `text_posting_configured`, `media_storage_configured`, and `image_posting_configured` describe configuration.
- `posts_text_only_now`, `posts_media_now`, and `posts_image_now` are true only when the Facebook posting gate is enabled and credentials are configured.
- Image post validation now checks storage configuration separately from execution authority.

This prevents the dashboard/API from implying that Beacon can post now when Meta posting is still locked.

Builder send-back fix: meat money-path routes now require owner read access at the route boundary before invoking quote/document, payment-gate, reservation, deposit, fulfilment, delivery, instruction, customer follow-up, booking-confirmation, or draft-order services.

- Added shared route helper `_require_owner_meat_money_path_access()`.
- Added regression coverage proving denied owner access returns before service calls.
- This does not unlock customer sends, public posts, stock reservation, payment confirmation, or lifecycle writes.

## Owner Gates Before First Public Push

1. Pick first launch channel.
   - Recommended first channel: manual owner-approved WhatsApp status or direct known buyers.
   - Avoid broad Facebook boost until templates and media are ready.

2. Set pilot cap.
   - Recommended cap: small first batch only, for example 1 to 2 halves or one full carcass equivalent.

3. Approve first Beacon campaign packet.
   - Exact text must be reviewed.
   - Exact media must be reviewed if using image/video.
   - No public post should be sent by automation yet.

4. Configure WhatsApp template names after Meta approval.

5. Approve at least one real Beacon media asset for public use.

6. Confirm SAM live-chat handling mode.
   - Current deterministic SAM flow is safe.
   - LLM/agent v2/v3 should stay gated until owner approves live-chat risk rules.

## CHARLIE CORE Oversight Notes

For this income-stream class of mission, CHARLIE CORE must always inspect:

- SAM Meat Sales runtime and Chatwoot policy.
- Beacon campaign/media policy.
- Meat pilot readiness endpoint.
- Order and sales transaction schemas.
- Quote/document/payment gates.
- Source-map matched implementation files.
- Owner approval gates before any public/customer output.

The mission should not be considered review-ready if it only changes UI or copy without proving these gates.
