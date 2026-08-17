from pathlib import Path


def test_campaign_review_action_is_allowed_without_weakening_claim_boundary():
    sql = Path(
        "supabase/migrations/202608170004_allow_beacon_campaign_review_claims.sql"
    ).read_text()
    allowed = {
        "mortality", "grouped_weights", "herdmaster_breeding_grouped",
        "rootline_irrigation_segment", "sam_sale_payment",
        "beacon_private_album_finish", "beacon_media_review",
        "rootline_fertilizer_mixer_commissioning",
        "rootline_fertilizer_mixer_presence_refresh",
        "rootline_delegated_family", "beacon_campaign_review",
    }
    assert all(f"'{action}'" in sql for action in allowed)
    assert "oom_protected_action_claims_action_kind_check" in sql
    assert "revoke all on app_private.oom_protected_action_claims" in sql
    assert "drop constraint" in sql
    assert "add constraint" in sql
