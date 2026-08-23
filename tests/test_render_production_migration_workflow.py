from pathlib import Path


WORKFLOW = Path(".github/workflows/render-production-migrations.yml").read_text(
    encoding="utf-8"
)


def test_legacy_adoption_public_inputs_contain_no_receipt_identities():
    dispatch = WORKFLOW.split("permissions:", 1)[0]
    assert "RENDER_MIGRATION_LEGACY_ADOPTION_JSON" not in dispatch
    assert "legacy_adoption_authorization_id:" in dispatch
    assert "legacy_adoption_packet_sha256:" in dispatch
    assert "receipt_id" not in dispatch


def test_authorization_transport_is_complete_and_strictly_shaped():
    assert '[[ "$supplied" == 0 || "$supplied" == 2 ]]' in WORKFLOW
    assert "legacy-adoption authorization transport is incomplete" in WORKFLOW
    assert "^[0-9a-f]{64}$" in WORKFLOW


def test_receipt_packet_is_not_transported_or_reported_on_job_creation_failure():
    create_step = WORKFLOW.split("- name: Create exact Render one-off migration job", 1)[1].split("- name: Wait for terminal Render job outcome", 1)[0]
    assert "RENDER_MIGRATION_LEGACY_ADOPTION_JSON" not in create_step
    assert "RENDER_MIGRATION_LEGACY_ADOPTION_PACKET_SHA256" in create_step
    assert "--fail-with-body" not in create_step
    assert 'echo "$response"' not in create_step
    assert 'cat "$response_file"' not in create_step
    assert 'Render migration job creation was rejected (HTTP $http_status)' in create_step


def test_existing_serialized_job_rail_and_exact_commit_binding_are_preserved():
    assert "group: render-production-migrations" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW
    assert "RENDER_MIGRATION_EXPECTED_COMMIT=$EXPECTED_SOURCE_COMMIT" in WORKFLOW
    assert "python scripts/run_render_production_migrations.py" in WORKFLOW
