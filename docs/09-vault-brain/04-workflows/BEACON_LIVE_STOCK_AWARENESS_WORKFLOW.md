# Beacon Live Stock Awareness Workflow

Status: Stage 7-9 planning authority. This does not approve public posting.

## Purpose

Beacon may support live-stock sales indirectly by posting normal farm-life content that is truthful, compliant, and not written as a sales advertisement.

The safe approach is awareness first:

- show new litters, piglet growth, farm routines, sow care, weaning, feed work, and healthy farm progress;
- avoid explicit sales words, prices, availability claims, booking language, urgency, or calls to buy;
- let interested people ask naturally;
- route inbound buying questions to SAM Live Stock Sales.
- never reveal or imply the exact farm location.

## Strict Content Rules

For a litter story, public copy identifies the family only by the sow's current
canonical human name. Internal litter IDs, pig IDs and event IDs stay inside the
bound evidence envelope and are never rendered publicly. The story must be a
warm, factual farm-life observation about the sow, her litter or ordinary daily
care. It must not mention or imply stock, availability, sale, price, booking,
reservation, urgency, messaging, contact or any invitation to buy or enquire.

Beacon must not use:

- `for sale`;
- `available`;
- `book now`;
- `order`;
- `price`;
- `special`;
- `discount`;
- `limited stock`;
- `reserve`;
- `buy now`;
- `DM to buy`;
- weight/price sales menus.

Beacon may use:

- `New litter update from Amadeus Farm`;
- `The piglets are growing well`;
- `A quick look at the weaners this week`;
- `Farm update from the piggery`;
- `Strong little group coming along nicely`;
- `Oom Sakkie is keeping an eye on this group`.

## Handoff Rule

If someone asks whether pigs are sold, available, priced, or can be bought, Beacon does not negotiate.

The lead must move to SAM Live Stock Sales, where SAM classifies the lane, captures facts, checks current source truth, and uses owner gates before promises.

Beacon may say the farm is near Riversdale only as normal farm context. Beacon does not post meeting points, order instructions, prices, or availability.

## Media Rule

Use real farm media only.

Do not show:

- sick/injured animals;
- dead animals;
- private people/children without consent;
- license plates or private customer locations;
- misleading old photos as current stock.

## Implementation Rule

Beacon campaign draft selection, publish packets, and media upload/review must carry an explicit campaign lane.

- `live_stock_awareness` is for farm-life, piglet, litter, weaner, sow-care, and awareness content only.
- `meat_launch` is for meat-sales campaign drafts only.
- Missing or invalid campaign lane must block packet generation instead of defaulting into meat-sales copy.
- Piglet, litter, weaner, and farm-life media must not produce meat-launch copy unless the owner explicitly selects the meat lane.

## Owner Approval

Every first live-stock awareness post requires owner review before publishing.

Owner review packet must include:

- selected media;
- caption text;
- confirmation that no direct sales terms are present;
- intended platform;
- expected SAM handoff path;
- pause/rollback instruction.

The concise private owner card must also show unmistakable previews and exact
identities for every selected image, plus protected Approve, Correct and Decline
controls bound to the authenticated owner, private chat, provider card,
campaign packet, generation, digest and expiry. Only media linked to the exact
canonical litter event and carrying current Library Accept, Public Use, byte
hash and storage-readback evidence may be selected. If none exists, no
publication card is prepared: Beacon states one precise missing-media exception
and requests the smallest governed library decision.

Approval authorizes one organic Facebook publication attempt only. It grants no
boost, spend, customer-send or retry authority. The deployed Beacon worker, not
a development terminal or callback handler, must claim the approved generation,
publish exactly once, obtain Meta readback and preserve ambiguity without retry.

## Learning Boundary

Delivery, clicks, messages and engagement may be reported as evidence, but
they cannot reward, graduate or optimize direct or implied livestock-commerce
copy. Every learning case must retain the awareness objective and pass the
public livestock policy. Missing policy evidence blocks graduation; any
policy failure blocks the candidate. Private, independently initiated SAM Live
Stock conversations remain separate.

Queued Telegram intake does not establish animal identity or permission to use
an image publicly. Owner context remains owner-provided evidence; visual
inference cannot replace canonical facts. Library acceptance, public-use
approval, livestock-awareness policy passage and exact publication authority
remain separate.
