import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_image_is_pinned_unprivileged_and_source_bound():
    text = (ROOT / "core_validator" / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM python:3\.12-slim@sha256:[0-9a-f]{64}$", text, re.MULTILINE)
    assert "pytest==8.4.1" in text
    assert "python-dotenv==1.0.1" in text
    assert "apt-get install -y --no-install-recommends git" in text
    assert "safe.directory /source" in text
    assert "USER 65532:65532" in text
    assert 'org.opencontainers.image.revision="${SOURCE_COMMIT}"' in text


def test_publication_is_manual_exact_source_and_immutable():
    text = (ROOT / ".github" / "workflows" / "core-validator-image.yml").read_text(encoding="utf-8")
    for required in (
        "workflow_dispatch:", "expected_source_commit:", "publish:",
        'test "$GITHUB_SHA" = "$EXPECTED_SOURCE_COMMIT"',
        'test "$GITHUB_REF" = "refs/heads/main"',
        "Refusing to overwrite existing", "push-by-digest=true", "platforms: linux/amd64",
        "cosign sign --yes", "actions/attest-build-provenance@", "actions/attest-sbom@",
    ):
        assert required in text


def test_release_receipt_binds_required_evidence():
    text = (ROOT / ".github" / "workflows" / "core-validator-image.yml").read_text(encoding="utf-8")
    for field in (
        "source_commit", "digest", "platform", "linux/amd64",
        "cosign_verified", "slsa_provenance_verified",
        "sbom_attestation_verified", "spdx_sbom_verified",
    ):
        assert field in text
