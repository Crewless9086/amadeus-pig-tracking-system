from modules.beacon.protected_publication import prepare_publication_preview,render_owner_preview

def proposal(): return {"packet_id":"P1","objective":"Build awareness",
 "audience":"Local farm followers","awareness_angle":"Daily care","intended_channel":"Facebook Page organic",
 "draft_caption":"A calm farm moment.","performance_measurement":"Verified later","capacity_context":{"sale_availability_inferred":False}}
def asset(): return {"asset_id":"A","binary_asset_id":"B","content_sha256":"a"*64,
 "library_accept_event_id":"L","public_use_event_id":"U","effective_public_use_approved":True,
 "projection_authority":"server_database_private_binary_v1","content_hash_provenance":"server_stream_and_storage_readback_verified"}
def loader(rows): return lambda ids,db: ({"success":True,"assets":rows},200)
def result(p=None):return {"result_digest":"d"*64,"proposal":p or proposal()}
def build(**kw):
 assets=kw.pop("assets",[asset()]);return prepare_publication_preview(result(),[a["asset_id"] for a in assets],owner_id="42",chat_id="42",card_message_id="7",page_id="PAGE",page_name="Amadeus Farm",contact_sheet_url="https://farm.test/media#P1",media_loader=loader(assets),**kw)

def test_exact_preview_is_zero_effect_and_unknown_safe():
 p=build(); assert set(p["measurement"].values())=={"Unknown"}; assert not any(p["authority"].values())
 assert "<b>Approve:</b>" in render_owner_preview(p) and p["sam_owns_customer_and_sales_truth"]
def test_missing_or_revoked_public_use_fails_closed():
 a=asset();a["effective_public_use_approved"]=False
 try:build(assets=[a]);assert False
 except ValueError as e:assert str(e)=="canonical_current_public_use_projection_required"
def test_changed_copy_or_media_changes_exact_digest():
    a=build(); q=proposal();q["draft_caption"]="Changed"; b=prepare_publication_preview(result(q),["A"],owner_id="42",chat_id="42",card_message_id="7",page_id="PAGE",page_name="Amadeus Farm",media_loader=loader([asset()]))
    assert a["review_digest"]!=b["review_digest"]
    a["copy"]="tampered"
    try:render_owner_preview(a);assert False
    except ValueError as e:assert str(e)=="publication_preview_digest_changed"
def test_scheduled_preview_shows_exact_zoned_time_and_organic_only():
 p=build(timing="scheduled",scheduled_at="2026-08-20T10:00:00+02:00");text=render_owner_preview(p)
 assert "2026-08-20T10:00:00+02:00" in text and p["paid_authority"] is False
def test_existing_rails_remain_canonical_and_no_new_execution_is_added():
 p=build(); assert p["canonical_rails"]["authorization"]=="beacon_organic_publication_authorization_events"
 assert p["decision_semantics"]["decline"].endswith("publication.")
 p["media"][0]["asset_id"]="<a href='bad'>bad</a>"; core={k:p[k] for k in ("contract_version","proposal_id","proposal_digest","objective","audience","angle","evidence","expected_value","channel","copy","copy_version","media","owner_id","chat_id","card_message_id","provider","page_id","page_name","contact_sheet_url","authority_mode","paid_authority","timing","scheduled_at")}; from modules.beacon.protected_publication import _digest; p["review_digest"]=_digest(core)
 assert "<a href" not in render_owner_preview(p)
