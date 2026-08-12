from pathlib import Path


def test_audit_workflow_applies_lifecycle_and_exposure_prerequisites_in_order():
    workflow=Path(".github/workflows/oom-sakkie-audit-rails.yml").read_text()
    names=[
        "202606290001_create_farm_canonical_tables.sql",
        "202607210001_create_pig_lifecycle_events.sql",
        "202608110001_create_oom_protected_action_claims.sql",
        "202608120001_create_breeding_exposure_events.sql",
        "202608120002_allow_breeding_protected_claims.sql",
    ]
    positions=[workflow.index(name) for name in names]
    assert positions == sorted(positions)
    assert all(workflow.count(name) == 1 for name in names)
    assert workflow.index("Run pig observation privilege gates") < workflow.index(
        "Run HERDMASTER grouped breeding exposure transaction gates"
    )
    observation_test=Path("tests/test_herdmaster_breeding_observation_postgres.py").read_text()
    assert "202607200001_create_pig_observation_events.sql" in observation_test
