from copy import deepcopy


BEACON_CAMPAIGN_MODE = "beacon_meat_launch_campaign_draft_only"

AUTHORITY_FLAGS = {
    "draft_only": True,
    "customer_public_output_enabled": False,
    "sends_customer_message": False,
    "posts_publicly": False,
    "calls_chatwoot": False,
    "calls_meta": False,
    "calls_n8n": False,
    "creates_quote": False,
    "creates_invoice": False,
    "creates_order": False,
    "changes_stock": False,
    "reserves_carcass": False,
    "books_slaughter": False,
    "books_butcher": False,
    "confirms_payment": False,
    "writes_farm_data": False,
}

FORBIDDEN_ACTIONS = [
    "no_public_post",
    "no_customer_dm",
    "no_chatwoot_send",
    "no_whatsapp_template",
    "no_meta_api_call",
    "no_order_create",
    "no_quote_invoice_create",
    "no_stock_reservation",
    "no_price_promise",
    "no_timing_promise",
    "no_slaughter_booking",
    "no_butcher_booking",
    "no_bank_confirmation",
]

OWNER_REVIEW_CHECKLIST = [
    "Choose which channel goes first: WhatsApp status, WhatsApp channel, Facebook, Instagram, or direct known buyers.",
    "Confirm whether public copy may mention Riversdale delivery/collection or should keep the area broad.",
    "Confirm whether public copy may mention a price/kg or should keep price on request until the pilot is proven.",
    "Choose the approved farm photo or video set before any public post is prepared.",
    "Confirm the first pilot target: how many halves/full carcasses should Sam try to fill before pausing demand.",
    "Confirm who handles delivery-day customer updates for the first pilot run.",
]


def build_meat_launch_campaign_selection(payload=None, approved_assets=None):
    """Return campaign draft/media pairing recommendations without doing any external action."""
    packet = build_meat_launch_campaign_packet(payload)
    approved_assets = approved_assets if isinstance(approved_assets, list) else []
    ranked_assets = _rank_approved_assets(approved_assets)
    channel_pairings = _channel_asset_pairings(packet.get("channel_drafts", []), ranked_assets)
    story_pairings = _channel_asset_pairings(packet.get("story_updates", []), ranked_assets, fallback_channel="story")
    return {
        "success": True,
        "mode": "beacon_meat_launch_campaign_media_selection_review_only",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "campaign": packet.get("campaign", {}),
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "approved_media_count": len(ranked_assets),
        "ranked_media_assets": ranked_assets,
        "channel_draft_pairings": channel_pairings,
        "story_update_pairings": story_pairings,
        "owner_review_checklist": [
            "Choose the exact media asset for each draft before any public post is prepared.",
            "Confirm the chosen channel and campaign cap before posting.",
            "Confirm no private customer, address, invoice, or sensitive farm detail is visible in the selected media.",
            "Public posting still happens only through a later owner-approved posting gate.",
        ],
        "next_gate": "owner_selects_media_and_campaign_draft_before_any_public_post",
    }


def build_meat_launch_campaign_packet(payload=None):
    """Return Beacon's first meat-launch campaign drafts without doing any external action."""
    payload = payload if isinstance(payload, dict) else {}
    pilot_name = _clean_text(payload.get("pilot_name")) or "First pork freezer preorder pilot"
    farm_name = _clean_text(payload.get("farm_name")) or "Amadeus Farm"
    area = _clean_text(payload.get("area")) or "Riversdale and nearby routes"
    product_focus = _clean_text(payload.get("product_focus")) or "half carcass Set A and full carcass pork freezer options"

    packet = {
        "success": True,
        "mode": BEACON_CAMPAIGN_MODE,
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "campaign": {
            "name": pilot_name,
            "status": "draft_only_owner_review_required",
            "farm_name": farm_name,
            "area": area,
            "product_focus": product_focus,
            "primary_goal": "Generate controlled inbound demand for Sam Meat without overpromising stock, price, timing, or delivery.",
        },
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "campaign_angles": _campaign_angles(farm_name, area, product_focus),
        "channel_drafts": _channel_drafts(farm_name, area, product_focus),
        "story_updates": _story_updates(farm_name, area),
        "owner_review_checklist": list(OWNER_REVIEW_CHECKLIST),
        "handoff_to_sam": {
            "inbound_prompt": "When a buyer replies, Sam should collect product, cut set, town, delivery/collection, address/location when delivery is requested, timing, payment preference, budget/target kg where useful, and final booking-review confirmation.",
            "must_not_say": [
                "Your order is confirmed.",
                "Your price is final.",
                "Your deposit is confirmed.",
                "Your carcass is reserved.",
                "Slaughter or butcher booking is confirmed.",
            ],
        },
        "next_gate": "owner_reviews_campaign_before_any_public_or_customer_send",
    }
    validation = validate_meat_launch_campaign_packet(packet)
    packet["validation"] = validation
    return packet


def validate_meat_launch_campaign_packet(packet):
    drafts = _all_draft_texts(packet)
    unsafe = []
    missing_preorder = []
    missing_limited = []
    for draft in drafts:
        text = draft["text"].lower()
        if not _has_preorder_signal(text):
            missing_preorder.append(draft["id"])
        if "limited" not in text:
            missing_limited.append(draft["id"])
        if _has_forbidden_promise(text):
            unsafe.append(draft["id"])

    authority = packet.get("authority") if isinstance(packet.get("authority"), dict) else {}
    unsafe_flags = [
        name for name, value in authority.items()
        if name != "draft_only" and value is True
    ]

    return {
        "success": not unsafe and not missing_preorder and not missing_limited and not unsafe_flags,
        "checked_draft_count": len(drafts),
        "missing_preorder_signal": missing_preorder,
        "missing_limited_signal": missing_limited,
        "unsafe_promise_drafts": unsafe,
        "unsafe_authority_flags": unsafe_flags,
    }


def format_meat_launch_campaign_markdown(packet):
    campaign = packet.get("campaign", {})
    lines = [
        "# Meat Launch Campaign Packet",
        "",
        "## Status",
        "",
        f"- Mode: `{packet.get('mode', '')}`",
        f"- Agent: {packet.get('agent', 'Beacon')}",
        f"- Campaign: {campaign.get('name', '')}",
        f"- Status: {campaign.get('status', '')}",
        f"- Next gate: `{packet.get('next_gate', '')}`",
        "",
        "This packet is draft-only. It does not post publicly, send customer messages, create quotes or invoices, create orders, reserve carcasses, change stock, book slaughter, book a butcher slot, or confirm payments.",
        "",
        "## Campaign Goal",
        "",
        campaign.get("primary_goal", ""),
        "",
        "## Campaign Angles",
        "",
    ]
    for angle in packet.get("campaign_angles", []):
        lines.extend([
            f"### {angle.get('title', '')}",
            "",
            angle.get("summary", ""),
            "",
            f"- Best channel: {angle.get('best_channel', '')}",
            f"- Sam handoff: {angle.get('sam_handoff', '')}",
            "",
        ])

    lines.extend(["## Channel Drafts", ""])
    for draft in packet.get("channel_drafts", []):
        lines.extend([
            f"### {draft.get('label', draft.get('id', 'Draft'))}",
            "",
            f"- Channel: {draft.get('channel', '')}",
            f"- Intent: {draft.get('intent', '')}",
            "",
            "```text",
            draft.get("text", ""),
            "```",
            "",
        ])

    lines.extend(["## Story Updates", ""])
    for update in packet.get("story_updates", []):
        lines.extend([
            f"### {update.get('label', update.get('id', 'Story'))}",
            "",
            "```text",
            update.get("text", ""),
            "```",
            "",
        ])

    lines.extend(["## Owner Review Checklist", ""])
    for item in packet.get("owner_review_checklist", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "## Authority Boundary",
        "",
    ])
    for name, value in sorted((packet.get("authority") or {}).items()):
        lines.append(f"- `{name}`: `{str(value).lower()}`")

    lines.extend([
        "",
        "## Forbidden Actions",
        "",
    ])
    for item in packet.get("forbidden_actions", []):
        lines.append(f"- `{item}`")

    validation = packet.get("validation", {})
    lines.extend([
        "",
        "## Validation",
        "",
        f"- Success: `{str(validation.get('success')).lower()}`",
        f"- Checked drafts: `{validation.get('checked_draft_count', 0)}`",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _campaign_angles(farm_name, area, product_focus):
    return [
        {
            "id": "controlled_freezer_preorder",
            "title": "Controlled Freezer Preorder",
            "summary": f"Position {farm_name} pork as a limited, pre-booked freezer run for households that want to plan ahead instead of buying anonymous supermarket meat.",
            "best_channel": "WhatsApp status and Facebook",
            "sam_handoff": "Ask whether the buyer wants half carcass, full carcass, or cut-set guidance.",
        },
        {
            "id": "set_a_family_pack",
            "title": "Set A Family Freezer Pack",
            "summary": "Explain Set A as the practical family freezer option while keeping price, timing, and final packed weight for the farm confirmation step.",
            "best_channel": "Facebook and direct known buyers",
            "sam_handoff": "Answer what Set A includes, then collect town, delivery/collection, timing, and payment preference.",
        },
        {
            "id": "farm_to_freezer_story",
            "title": "Farm To Freezer Story",
            "summary": f"Show the journey from farm planning to packed pork, with limited availability and pre-booking as part of the story rather than a pressure tactic.",
            "best_channel": "Instagram story and WhatsApp status",
            "sam_handoff": "Invite replies from people who want Sam to check the best fit for their freezer, budget, or target kg.",
        },
        {
            "id": "local_route_pilot",
            "title": "Local Route Pilot",
            "summary": f"Keep the first run focused around {area}, so delivery and collection promises stay controlled while demand is measured.",
            "best_channel": "WhatsApp status and known-buyer share",
            "sam_handoff": "Capture address or shared location when delivery is requested.",
        },
    ]


def _channel_drafts(farm_name, area, product_focus):
    return [
        {
            "id": "whatsapp_status_1",
            "label": "WhatsApp Status 1",
            "channel": "WhatsApp status",
            "intent": "Soft interest check",
            "text": f"{farm_name} is preparing a limited pork freezer preorder run for {area}. Half carcass Set A and full carcass options are pre-booked only; price, timing, and final packed weight are confirmed before booking. Reply if you want Sam to note your interest.",
        },
        {
            "id": "whatsapp_status_2",
            "label": "WhatsApp Status 2",
            "channel": "WhatsApp status",
            "intent": "Explain the offer simply",
            "text": "Limited pork freezer preorders are opening. This is not ready-shelf stock; it is pre-booked farm pork, packed after processing, with final weight confirmed once known. Ask Sam about half carcass Set A, full carcass, delivery, or collection.",
        },
        {
            "id": "whatsapp_channel",
            "label": "WhatsApp Channel Draft",
            "channel": "WhatsApp channel or broadcast draft",
            "intent": "First owner-approved announcement",
            "text": f"We are testing a limited {farm_name} pork freezer preorder run. The focus is {product_focus}. Orders are pre-booked, and the farm confirms price, available timing, deposit steps, and final packed weight before anything is booked. Message Sam if you want to be added to the review list.",
        },
        {
            "id": "facebook_post",
            "label": "Facebook Post Draft",
            "channel": "Facebook",
            "intent": "Public demand generation",
            "text": f"{farm_name} is preparing a limited pork freezer preorder pilot for {area}. We are starting small so that every booking can be handled properly. The first focus is {product_focus}. This is pre-booked farm pork, not unlimited shop stock: price, timing, delivery/collection, deposit steps, and final packed weight are confirmed before the booking is accepted. If you want pork for your freezer, send us a message and Sam will collect the details.",
        },
        {
            "id": "instagram_caption",
            "label": "Instagram Caption Draft",
            "channel": "Instagram",
            "intent": "Story-led launch caption",
            "text": f"A small farm run, planned properly. {farm_name} is opening limited pork freezer preorders, starting with half carcass Set A and full carcass interest. Every order is pre-booked, with price, timing, deposit steps, and final packed weight confirmed before booking. Message Sam if you want to join the first review list.",
        },
        {
            "id": "customer_education",
            "label": "Customer Education Draft",
            "channel": "Facebook/WhatsApp explainer",
            "intent": "Reduce confusion about final weight",
            "text": "How the freezer preorder works: availability is limited, so interest is captured first. The farm then confirms price/kg, timing, delivery or collection, and deposit steps. Packed weight is estimated early, but the final amount is only confirmed after processing, because real carcass and cut yield can vary.",
        },
    ]


def _story_updates(farm_name, area):
    return [
        {
            "id": "story_slide_1",
            "label": "Story Slide 1",
            "text": f"Limited pork freezer preorders are opening soon from {farm_name}. Pre-booked only, starting with the first controlled pilot around {area}.",
        },
        {
            "id": "story_slide_2",
            "label": "Story Slide 2",
            "text": "Half carcass Set A is for families who want practical freezer pork. Limited availability, pre-booked, with final packed weight confirmed after processing.",
        },
        {
            "id": "story_slide_3",
            "label": "Story Slide 3",
            "text": "Sam will collect the details: half or full carcass, town, delivery or collection, timing, payment preference, and any budget or freezer-size target. Limited pre-booked run only.",
        },
        {
            "id": "story_slide_4",
            "label": "Story Slide 4",
            "text": "Want to join the limited preorder review list? Reply and Sam will capture your interest. No booking is final until the farm confirms price, timing, and deposit steps.",
        },
    ]


def _rank_approved_assets(assets):
    ranked = []
    for asset in assets:
        if _asset_status(asset) != "approved":
            continue
        tags = _asset_list(asset.get("subject_tags"))
        relevance = _asset_list(asset.get("sale_stream_relevance"))
        privacy_risk = _clean_text(asset.get("privacy_risk")).lower() or "unknown"
        media_type = _clean_text(asset.get("media_type")).lower() or "unknown"
        quality_score = _safe_int(asset.get("quality_score"), 0)
        score = quality_score
        if media_type == "image":
            score += 20
        if media_type == "video":
            score += 15
        if "meat" in relevance:
            score += 25
        if any(tag in tags for tag in ("pork", "freezer", "set a", "half carcass", "family pack")):
            score += 15
        if privacy_risk in ("high", "medium"):
            score -= 40 if privacy_risk == "high" else 20
        ranked.append({
            "asset_id": asset.get("asset_id", ""),
            "title": asset.get("title") or asset.get("original_filename") or asset.get("asset_id", ""),
            "media_type": media_type,
            "storage_bucket": asset.get("storage_bucket", ""),
            "storage_path": asset.get("storage_path", ""),
            "subject_tags": tags,
            "sale_stream_relevance": relevance,
            "quality_score": asset.get("quality_score"),
            "privacy_risk": privacy_risk,
            "selection_score": max(0, min(score, 160)),
            "public_use_approved": bool(asset.get("effective_public_use_approved") or asset.get("public_use_approved")),
            "why": _asset_why(tags, relevance, media_type, privacy_risk),
        })
    return sorted(ranked, key=lambda item: (-item["selection_score"], item["asset_id"]))[:12]


def _channel_asset_pairings(drafts, ranked_assets, fallback_channel="campaign"):
    pairings = []
    for draft in drafts:
        best = _best_asset_for_draft(draft, ranked_assets)
        pairings.append({
            "draft_id": draft.get("id", ""),
            "draft_label": draft.get("label") or draft.get("id", ""),
            "channel": draft.get("channel") or fallback_channel,
            "intent": draft.get("intent", ""),
            "recommended_asset_id": best.get("asset_id", "") if best else "",
            "recommended_asset_title": best.get("title", "") if best else "",
            "selection_reason": _selection_reason(draft, best),
            "requires_owner_final_selection": True,
        })
    return pairings


def _best_asset_for_draft(draft, ranked_assets):
    if not ranked_assets:
        return {}
    text = f"{draft.get('channel', '')} {draft.get('intent', '')} {draft.get('text', '')}".lower()
    best_asset = ranked_assets[0]
    best_score = -1
    for asset in ranked_assets:
        score = asset.get("selection_score", 0)
        tags = " ".join(asset.get("subject_tags", [])).lower()
        if "story" in text and asset.get("media_type") in ("image", "video"):
            score += 8
        if "family" in text and "family" in tags:
            score += 10
        if "set a" in text and ("set a" in tags or "freezer" in tags):
            score += 10
        if "facebook" in text and asset.get("media_type") == "image":
            score += 5
        if score > best_score:
            best_asset = asset
            best_score = score
    return best_asset


def _selection_reason(draft, asset):
    if not asset:
        return "No owner-approved media asset is available yet. Draft can stay text-only until media is approved."
    return f"Matches {draft.get('label') or draft.get('id')} because it is approved for public-use review, scored {asset.get('selection_score')}, and is tagged {', '.join(asset.get('subject_tags') or ['general'])}."


def _asset_why(tags, relevance, media_type, privacy_risk):
    parts = [f"{media_type or 'unknown'} media"]
    if relevance:
        parts.append(f"relevant to {', '.join(relevance)}")
    if tags:
        parts.append(f"tagged {', '.join(tags[:4])}")
    parts.append(f"privacy risk {privacy_risk}")
    return "; ".join(parts)


def _asset_status(asset):
    return _clean_text(asset.get("effective_approval_status") or asset.get("approval_status")).lower()


def _asset_list(value):
    if isinstance(value, list):
        return [_clean_text(item).lower() for item in value if _clean_text(item)]
    if isinstance(value, str):
        return [_clean_text(item).lower() for item in value.split(",") if _clean_text(item)]
    return []


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _all_draft_texts(packet):
    drafts = []
    for group in ("channel_drafts", "story_updates"):
        for draft in packet.get(group, []):
            drafts.append({"id": draft.get("id", ""), "text": draft.get("text", "")})
    return drafts


def _has_preorder_signal(text):
    return "preorder" in text or "pre-book" in text or "pre booked" in text


def _has_forbidden_promise(text):
    forbidden = [
        "available now",
        "order confirmed",
        "booking confirmed",
        "guaranteed",
        "deposit confirmed",
        "payment confirmed",
        "slaughter booked",
        "butcher booked",
        "free delivery",
        "final price",
        "fixed delivery date",
    ]
    return any(term in text for term in forbidden)


def _clean_text(value):
    return " ".join(str(value or "").strip().split())
