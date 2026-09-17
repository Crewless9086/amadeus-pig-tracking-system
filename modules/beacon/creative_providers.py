import hashlib
import json


ELEVENLABS = "elevenlabs"
HAPPY_HORSE_1_0 = "happy_horse_1_0"
ALLOWED_CREATIVE_PROVIDERS = frozenset({ELEVENLABS, HAPPY_HORSE_1_0})

DISABLED_PROVIDER_FLAGS = {
    "provider_enabled": False,
    "network_enabled": False,
    "credential_access": False,
    "source_transfer": False,
    "actual_cost": 0,
    "actual_cost_currency": "ZAR",
    "posts_publicly": False,
    "schedules_publication": False,
    "sends_customer_message": False,
    "spends_money": False,
    "creates_order": False,
    "changes_stock": False,
    "writes_farm_data": False,
}


def evaluate_disabled_provider(provider, prompt, parameters, source_lineage):
    """Return a deterministic manifest without contacting or inspecting a provider."""
    provider = str(provider or "").strip().lower()
    if provider not in ALLOWED_CREATIVE_PROVIDERS:
        raise ValueError("creative_provider_not_allowlisted")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("exact_prompt_required")
    if not isinstance(parameters, dict):
        raise ValueError("creative_parameters_must_be_object")
    if not isinstance(source_lineage, list) or not source_lineage:
        raise ValueError("approved_source_lineage_required")

    canonical_input = _canonical_json({
        "provider": provider,
        "prompt": prompt,
        "parameters": parameters,
        "source_lineage": source_lineage,
    })
    digest = hashlib.sha256(canonical_input.encode("utf-8")).hexdigest()
    media_type = "audio" if provider == ELEVENLABS else "video"
    extension = "json"
    manifest = {
        "mode": "beacon_creative_provider_disabled_mock",
        "provider": provider,
        "model_identifier": "provider-disabled-mock-v1",
        "deterministic_digest": digest,
        "output_media_type": media_type,
        "output_mime_type": "application/json",
        "output_extension": extension,
        "mock_variant_count": 1,
        **DISABLED_PROVIDER_FLAGS,
    }
    manifest_bytes = _canonical_json(manifest).encode("utf-8")
    return {
        **manifest,
        "manifest_bytes": manifest_bytes,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
