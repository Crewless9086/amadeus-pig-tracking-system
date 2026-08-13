import json

import pytest

from modules.pig_weights.canonical_grouped_preview import (
    preview_application_typed,
    preview_prepared_owner_text,
)


PIGS = [
    {"pig_id": "PIG-2026-A1-X", "tag_number": "A1", "status": "Active", "on_farm": True, "current_pen_id": "PEN-OLD-1"},
    {"pig_id": "PIG-2026-B2-Y", "tag_number": "B2", "status": "Active", "on_farm": "Yes", "current_pen_id": "PEN-OLD-2"},
]
PENS = [{"pen_id": "PEN-D3-OPAQUE", "pen_name": "D3", "active": True}]
TEXT = "A1 - 47.20 kg, B2 - 118 kg; all moved to pen D3 on 2026-08-13"


def _stable_contract(result):
    return json.dumps({key: result[key] for key in (
        "contract_version", "effective_date", "rows", "confirmation_required", "preview_digest"
    )}, sort_keys=True, separators=(",", ":"))


def test_application_oom_and_prepared_browser_voice_are_byte_equivalent():
    application = preview_application_typed({
        "weight_date": "2026-08-13", "destination_pen": "D3",
        "rows": [{"identity": "A1", "weight_kg": "47.20"}, {"identity": "B2", "weight_kg": 118}],
    }, pigs=PIGS, pens=PENS)
    oom = preview_prepared_owner_text(TEXT, channel="oom_typed", effective_date=None, pigs=PIGS, pens=PENS)
    voice = preview_prepared_owner_text(TEXT, channel="browser_voice_prepared_text", effective_date=None, pigs=PIGS, pens=PENS)
    assert application["success"] and oom["success"] and voice["success"]
    assert _stable_contract(application) == _stable_contract(oom) == _stable_contract(voice)
    assert application["rows"][0]["pig_id"] == "PIG-2026-A1-X"
    assert {row["moved_to_pen_id"] for row in application["rows"]} == {"PEN-D3-OPAQUE"}
    assert application["confirmation_required"] is True


def test_unknowns_are_explicit_and_stable():
    pigs = [{"pig_id": "PIG-OPAQUE", "tag_number": "X1", "status": "Active", "on_farm": True}]
    result = preview_application_typed({"weight_date": "2026-08-13", "rows": [{"identity": "X1", "weight_kg": 12}]}, pigs=pigs, pens=[])
    assert result["rows"][0]["current_pen_id"] == "Unknown"
    assert result["rows"][0]["moved_to_pen_id"] == "Unknown"
    assert result["rows"][0]["condition_notes"] == "Unknown"


@pytest.mark.parametrize("pigs,status", [
    (PIGS + [{**PIGS[0], "pig_id": "PIG-DUP"}], "animal_identity_ambiguous"),
    ([{**PIGS[0], "status": "Sold"}], "animal_not_active_on_farm"),
    ([{**PIGS[0], "on_farm": False}], "animal_not_active_on_farm"),
])
def test_ambiguous_inactive_and_off_farm_identities_fail_closed(pigs, status):
    result = preview_application_typed({"weight_date": "2026-08-13", "rows": [{"identity": "A1", "weight_kg": 47.2}]}, pigs=pigs, pens=PENS)
    assert result["success"] is False and result["status"] == status


def test_duplicate_identity_and_invalid_or_ambiguous_pen_fail_closed():
    duplicate = preview_application_typed({"weight_date": "2026-08-13", "rows": [{"identity": "A1", "weight_kg": 47}, {"identity": "PIG-2026-A1-X", "weight_kg": 48}]}, pigs=PIGS, pens=PENS)
    invalid = preview_prepared_owner_text("A1 47 kg, B2 118 kg; moved to ZZ", channel="oom_typed", effective_date="2026-08-13", pigs=PIGS, pens=PENS)
    ambiguous = preview_prepared_owner_text(TEXT, channel="oom_typed", effective_date=None, pigs=PIGS, pens=PENS + [{"pen_id": "PEN-OTHER", "pen_name": "D3"}])
    assert duplicate["status"] == "duplicate_animal_identity"
    assert invalid["status"] == "destination_pen_invalid"
    assert ambiguous["status"] == "destination_pen_ambiguous"


def test_telegram_voice_is_explicitly_excluded_and_all_results_are_zero_effect():
    rejected = preview_prepared_owner_text(TEXT, channel="telegram_voice", effective_date=None, pigs=PIGS, pens=PENS)
    accepted = preview_prepared_owner_text(TEXT, channel="browser_voice_prepared_text", effective_date=None, pigs=PIGS, pens=PENS)
    assert rejected["status"] == "channel_not_authorized"
    for result in (rejected, accepted):
        assert result["writes_performed"] is False
        assert {result[key] for key in ("database_calls", "provider_calls", "telegram_calls", "google_sheets_calls", "farm_writes")} == {0}


def test_module_import_graph_contains_no_side_effect_adapter_names():
    import ast
    import modules.pig_weights.canonical_grouped_preview as contract
    tree = ast.parse(open(contract.__file__, encoding="utf-8").read())
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(name=node.module or "")])
    }
    assert imports.isdisjoint({"psycopg", "requests", "gspread", "telegram", "supabase", "modules"})
