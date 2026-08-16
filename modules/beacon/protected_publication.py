"""Local-only owner preview over BEACON's existing canonical publication rails."""
from hashlib import sha256
import html, json, re

CONTRACT="beacon_protected_publication_preview_v1"
UNKNOWN="Unknown"
ZERO={"publish":False,"schedule":False,"meta_call":False,"spend":False,
      "customer_send":False,"farm_write":False,"media_authority_change":False}

def prepare_publication_preview(result, asset_ids, *, owner_id, chat_id,
        card_message_id, page_id, page_name, contact_sheet_url="", timing="immediate", scheduled_at="", media_loader=None):
    result=result if isinstance(result,dict) else {};p=result.get("proposal") if isinstance(result.get("proposal"),dict) else {}
    required=("packet_id","objective","audience","awareness_angle",
              "intended_channel","draft_caption","performance_measurement")
    if any(not _text(p.get(k)) for k in required) or not _text(result.get("result_digest")): raise ValueError("exact_proposal_evidence_required")
    if p["intended_channel"]!="Facebook Page organic": raise ValueError("meta_organic_channel_required")
    if timing not in {"immediate","scheduled"}: raise ValueError("publication_timing_invalid")
    if timing=="scheduled" and not _scheduled(scheduled_at): raise ValueError("publication_schedule_invalid")
    if not all(_text(x) for x in (owner_id,chat_id,card_message_id,page_id,page_name)):
        raise ValueError("owner_chat_card_page_binding_required")
    if asset_ids:
        if media_loader is None:
            from modules.beacon.facebook_media_transport import resolve_server_publication_assets
            media_loader=resolve_server_publication_assets
        loaded,status=media_loader(asset_ids, None)
        if status!=200 or loaded.get("success") is not True: raise ValueError("canonical_current_public_use_projection_required")
        canonical_assets=loaded.get("assets") or []
    else: canonical_assets=[]
    media=[]
    for row in canonical_assets:
        digest=str(row.get("content_sha256") or "").lower()
        if (row.get("projection_authority")!="server_database_private_binary_v1"
                or row.get("content_hash_provenance")!="server_stream_and_storage_readback_verified"
                or row.get("effective_public_use_approved") is not True
                or not row.get("library_accept_event_id") or not row.get("public_use_event_id")
                or not re.fullmatch(r"[0-9a-f]{64}",digest)):
            raise ValueError("canonical_current_public_use_projection_required")
        media.append({k:row[k] for k in ("asset_id","binary_asset_id","content_sha256",
            "library_accept_event_id","public_use_event_id")})
    core={"contract_version":CONTRACT,"proposal_id":p["packet_id"],
        "proposal_digest":result["result_digest"],"objective":p["objective"],
          "audience":p["audience"],"angle":p["awareness_angle"],
          "evidence":p.get("capacity_context") or {},"expected_value":p.get("expected_commercial_value") or UNKNOWN,
          "channel":p["intended_channel"],"copy":p["draft_caption"],
          "copy_version":_digest(p["draft_caption"]),"media":media,
          "owner_id":str(owner_id),"chat_id":str(chat_id),"card_message_id":str(card_message_id),
          "provider":"Meta","page_id":str(page_id),"page_name":str(page_name),"contact_sheet_url":str(contact_sheet_url),"authority_mode":"organic",
          "paid_authority":False,"timing":timing,"scheduled_at":scheduled_at if timing=="scheduled" else ""}
    digest=_digest(core)
    return {**core,"preview_id":"BEACON-PUBLICATION-PREVIEW-"+digest[:24].upper(),
      "review_digest":digest,"decision_options":["approve","correct","decline"],
      "canonical_rails":{"decision":"beacon_weekly_review_decision_events",
        "binding":"beacon_organic_publication_bindings",
        "authorization":"beacon_organic_publication_authorization_events",
        "execution":"beacon_facebook_post_execution_events",
        "performance":"beacon_campaign_performance_events","attribution":"BEACON_SAM_ATTRIBUTION_V1"},
      "rail_translation":{"owner_decision":{"packet_id":p["packet_id"],"canonical_sha256":digest,"caption_sha256":_digest(p["draft_caption"]),"ordered_media_ids":[x["asset_id"] for x in media],"publish":False,"spend":False},
        "execution_packet":{"publish_packet_id":p["packet_id"],"campaign_lane":"live_stock_awareness","selected_draft":{"exact_text":p["draft_caption"]},"selected_assets":media}},
      "decision_semantics":{"approve":"Authorize only this exact digest for one organic publication attempt; it does not authorize spend.",
        "correct":"Create a new immutable proposal/review version; this digest remains unauthorized.",
        "decline":"Record decline on the existing decision rail; create no binding, authorization or publication."},
      "measurement":{k:UNKNOWN for k in ("reach","engagement","qualified_sam_leads","conversions","completed_sales","attributable_gross_profit")},
      "sam_owns_customer_and_sales_truth":True,"authority":dict(ZERO)}

def render_owner_preview(p):
    _valid_preview(p)
    when=p["scheduled_at"] if p["timing"]=="scheduled" else "Publish immediately after exact protected approval"
    media="Text only" if not p["media"] else ", ".join(f"asset {x['asset_id']}" for x in p["media"])
    ev=p["evidence"]; evidence=("Sale availability is not inferred. HERDMASTER capacity: "+str(ev.get("herdmaster_safe_fulfilment_capacity",UNKNOWN))+"; SAM quantified demand: "+str(ev.get("sam_quantified_buyer_demand",UNKNOWN)))
    return "\n".join(["<b>BEACON — PROTECTED PUBLICATION PREVIEW</b>","",
      f"<b>Objective:</b> {html.escape(p['objective'])}",f"<b>Audience:</b> {html.escape(p['audience'])}",
      f"<b>Farm story:</b> {html.escape(p['angle'])}",f"<b>Evidence boundary:</b> {html.escape(evidence)}",
      f"<b>Expected value:</b> {html.escape(str(p['expected_value']))}",
      f"<b>Channel/page:</b> {html.escape(p['channel'])} / {html.escape(p['page_name'])} ({html.escape(p['page_id'])}) (organic; no paid authority)",
      f"<b>Exact copy:</b> {html.escape(p['copy'])}",f"<b>Media:</b> {html.escape(media)}",f"<b>Timing:</b> {html.escape(when)}",
      "<b>Measure later:</b> Reach, engagement, qualified SAM leads, conversions, completed sales and attributable gross profit are Unknown until verified.",
      f"<b>Inspect media:</b> {html.escape(p['contact_sheet_url'] or 'No media; text-only packet')}",
      "<b>Approve:</b> authorize this exact digest for one organic post attempt; no spend.",
      "<b>Correct:</b> create a new immutable version; this version remains unauthorized.",
      "<b>Decline:</b> create no publication binding, authorization or post.",
      "Approval applies only to this exact packet. Public Use, campaign review, publication and spend remain separate authorities. This local preview performs none."])

def _valid_preview(p):
    if not isinstance(p,dict) or p.get("contract_version")!=CONTRACT or p.get("authority")!=ZERO or p.get("authority_mode")!="organic" or p.get("paid_authority") is not False:
        raise ValueError("publication_preview_invalid")
    keys=("contract_version","proposal_id","proposal_digest","objective","audience","angle","evidence","expected_value","channel","copy","copy_version","media","owner_id","chat_id","card_message_id","provider","page_id","page_name","contact_sheet_url","authority_mode","paid_authority","timing","scheduled_at")
    if _digest({k:p[k] for k in keys})!=p.get("review_digest"): raise ValueError("publication_preview_digest_changed")

def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def _text(v): return str(v or "").strip()
def _scheduled(v):
    from datetime import datetime
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).tzinfo is not None
    except (ValueError,TypeError):return False
