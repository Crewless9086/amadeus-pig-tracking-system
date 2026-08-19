from pathlib import Path


def test_consumer_schema_is_private_unique_and_terminal():
    sql = Path("supabase/migrations/202608190002_create_beacon_protected_publication_consumer.sql").read_text()
    assert "callback_token text not null unique" in sql
    assert "references app_private.oom_protected_action_claims" in sql
    assert "revoke all" in sql
    for status in ("claimed", "confirmed", "contained_failed", "contained_ambiguous"):
        assert status in sql
