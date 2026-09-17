from pathlib import Path


MIGRATION = Path("supabase/migrations/202608170003_seed_rootline_operational_devices.sql")


def test_operational_device_seed_is_identity_only_and_fail_closed():
    sql = MIGRATION.read_text(encoding="utf-8")
    for identity in ("100204e9bc:1", "100204e9bc:2", "100204d497:1", "1002851416:1"):
        assert identity in sql
    assert sql.count('"standing_authority":false') == 4
    assert "standing_active" not in sql
    assert "physical_identity_proven" not in sql
    assert sql.count("'registered'") == 4


def test_injection_and_borehole_dependencies_are_explicit():
    sql = MIGRATION.read_text(encoding="utf-8")
    for dependency in ("verified_water_preflow", "clean_water_flush", "tank_full",
                       "dry_run_protection", "pump_current_protection",
                       "manual_isolation", "power_loss_fail_safe"):
        assert dependency in sql
