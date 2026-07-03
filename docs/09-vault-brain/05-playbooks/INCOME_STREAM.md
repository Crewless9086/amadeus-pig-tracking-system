# Income Stream Playbook

Required before build:

- business model;
- customer path;
- pricing/payment rules;
- fulfilment rules;
- legal/privacy/marketing constraints;
- source-of-truth data;
- owner gates;
- launch evidence plan.

## Launch Readiness Lesson 2026-07-03

First-launch income missions must separate code readiness from operational launch readiness.

CHARLIE CORE may mark backend verification as passing only after relevant unit tests, route guards, policy probes, and source-map checks pass. It must still block public/customer launch when operational gates are missing.

For SAM + Beacon Meat Sales, customer/public launch is blocked until all of these are proven:

- required WhatsApp template env names are configured after Meta approval;
- at least one real Beacon media asset is owner-approved for public use;
- Beacon posting remains disabled until the exact post packet is owner-approved;
- the owner selects the first launch channel;
- the owner sets the first pilot cap;
- no customer send, public post, stock reservation, payment confirmation, slaughter, butcher, delivery, or lifecycle movement happens before the matching backend and money gates pass.

Correct blocked outcome: if backend tests pass but these launch gates are missing, the mission should produce an owner-review packet and recommend manual owner-only pilot preparation, not uncontrolled public launch.
