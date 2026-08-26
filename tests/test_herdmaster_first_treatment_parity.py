from unittest.mock import patch

from modules.oom_sakkie import herdmaster_litter_first_treatment_runtime as telegram
from modules.pig_weights import pig_weights_controller as application
from modules.pig_weights.herdmaster_litter_first_treatment_action import (
    execute_first_treatment,
    preview_first_treatment,
)


def evidence():
    piglets = [
        {"pig_id": "PIG-1", "tag_number": "L-1", "name": "", "sex": "Male",
         "status": "Active", "on_farm": True},
        {"pig_id": "PIG-2", "tag_number": "L-2", "name": "", "sex": "Female",
         "status": "Active", "on_farm": True},
    ]
    return {
        "evidence_generation": "GEN-1",
        "animals": [{"pig_id": "SOW-LINDA", "tag_number": "Linda", "name": "Linda"}],
        "litters": [{"litter_id": "LIT-LINDA", "sow_pig_id": "SOW-LINDA",
            "litter_status": "Active", "active_count": 2,
            "first_treatment_complete": False, "first_treatment_partial": False,
            "detail": {"mother_pig_id": "SOW-LINDA", "piglets": piglets}}],
        "products": [
            {"product_id": "ECOMECTIN", "product_name": "Ecomectin",
             "default_dose": 1, "dose_unit": "ml", "default_withdrawal_days": 0},
            {"product_id": "PANACUR", "product_name": "Panacur",
             "default_dose": 2, "dose_unit": "ml", "default_withdrawal_days": 0},
        ],
        "settings": {"herdmaster_first_treatment_protocol_v1": {
            "protocol_id": "STOCK-STANDARD-FIRST", "version": "2026-08-25",
            "earmarked": True, "notes": "Normal first-treatment round",
            "treatments": [
                {"role": "antiparasitic", "product_id": "ECOMECTIN",
                 "route": "oral", "batch_lot_number": "ECO-LOT"},
                {"role": "deworming", "product_id": "PANACUR",
                 "route": "oral", "batch_lot_number": "PAN-LOT"},
            ]}},
    }


def facts():
    return {"sow_ref": "Linda", "action_date": "2026-08-25",
            "male_count": 1, "female_count": 1}


def test_application_and_telegram_import_one_shared_backend_operation():
    assert application.preview_first_treatment is preview_first_treatment
    assert telegram.preview_first_treatment is preview_first_treatment
    assert telegram.execute_first_treatment is execute_first_treatment


def test_channel_previews_are_canonically_equivalent_and_derive_protocol():
    with patch.dict("os.environ", {"SECRET_KEY": "test-secret"}):
        app, app_status = preview_first_treatment(
            facts(), actor_id="OWNER", channel="application",
            source_reference="APP-1", evidence_loader=lambda **_: evidence())
        tg, tg_status = preview_first_treatment(
            facts(), actor_id="OWNER", channel="telegram",
            source_reference="TG-1", evidence_loader=lambda **_: evidence())
    assert (app_status, tg_status) == (200, 200)
    assert app["operation_id"] == tg["operation_id"]
    assert app["preview_digest"] == tg["preview_digest"]
    assert app["preview"]["pig_ids"] == ["PIG-1", "PIG-2"]
    assert app["preview"]["protocol"]["protocol_id"] == "STOCK-STANDARD-FIRST"
    assert [
        (row["product_name"], row["dose"], row["route"], row["batch_lot_number"])
        for row in app["preview"]["protocol"]["treatments"]
    ] == [
        ("Ecomectin", 1, "oral", "ECO-LOT"),
        ("Panacur", 2, "oral", "PAN-LOT"),
    ]


def test_shared_execution_requires_bound_preview_and_returns_exact_readback():
    packet = evidence()
    with patch.dict("os.environ", {"SECRET_KEY": "test-secret"}):
        preview, _ = preview_first_treatment(
            facts(), actor_id="OWNER", channel="application",
            source_reference="APP-1", evidence_loader=lambda **_: packet)
        with patch(
            "modules.pig_weights.herdmaster_litter_first_treatment_action."
            "apply_litter_first_treatment_packet",
            return_value={"status": "first_treatment_committed",
                "treatment_rows_created": 4, "medical_readback": [
                    {"medical_event_id": f"MED-{index}"}
                    for index in range(4)]},
        ) as apply_packet, patch(
            "modules.pig_weights.herdmaster_litter_first_treatment_action."
            "farm_supabase_read_service.get_litter_detail",
            return_value={"first_treatment_complete": True,
                          "active_count": 2},
        ):
            result, status = execute_first_treatment(
                facts(), actor_id="OWNER", channel="application",
                source_reference="APP-1",
                confirmation_binding=preview["confirmation_binding"],
                evidence_loader=lambda **_: packet)
    assert status == 201
    assert result["rows_created"] == 4
    assert result["canonical_readback"]["first_treatment_complete"] is True
    sent = apply_packet.call_args.args[0]
    assert sent["pig_ids"] == ["PIG-1", "PIG-2"]
    assert len(sent["treatment_rows"]) == 4


def test_tampered_or_missing_confirmation_cannot_write():
    with patch.dict("os.environ", {"SECRET_KEY": "test-secret"}), patch(
        "modules.pig_weights.herdmaster_litter_first_treatment_action."
        "apply_litter_first_treatment_packet"
    ) as apply_packet:
        result, status = execute_first_treatment(
            facts(), actor_id="OWNER", channel="application",
            source_reference="APP-1", confirmation_binding={},
            evidence_loader=lambda **_: evidence())
    assert status == 409
    assert result["status"] == "exact_preview_confirmation_required"
    apply_packet.assert_not_called()
