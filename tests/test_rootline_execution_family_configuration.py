from copy import deepcopy
from hashlib import sha256
import json

import pytest

from modules.telemetry.rootline_device_registry import (
    commissioned_irrigation_contract, rootline_device_registry,
)
from modules.telemetry.rootline_execution_authority import (
    _command_mapping, _zone_contracts,
)


def _redigest(row):
    material = {key: value for key, value in row.items() if key != "contract_sha256"}
    row["contract_sha256"] = sha256(json.dumps(material, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()
    return row


def test_existing_b_c_and_auxiliary_outputs_share_one_registry():
    registry = rootline_device_registry()
    zones = _zone_contracts(registry)
    assert {identity: row["channel"] for identity, row in zones.items()} == {
        "B12345": 1, "C12345": 2}
    assert registry["FERTILIZER-INJECTION-CH1"]["channel"] == 1
    assert registry["FERTILIZER-MIXER-CH2"]["channel"] == 2
    assert not ({"FERTILIZER-INJECTION-CH1", "FERTILIZER-MIXER-CH2"} & set(zones))


def test_simulated_future_mother_valve_needs_governed_commissioned_contract():
    registry = rootline_device_registry()
    future = deepcopy(registry["B12345"])
    future.update(identity="MOTHER-VALVE-1", device_id="SIMULATED-MOTHER-CONTROLLER",
        device_name="Unapproved upstream shared-control output", channel=3,
        on_event="simulated_mother_ch3_on", off_event="simulated_mother_ch3_off",
        commissioning_id="ROOTLINE-COMMISSION-SIMULATED-MOTHER",
        commissioning_generation=1, commissioned=True)
    registry[future["identity"]] = _redigest(future)
    resolved = commissioned_irrigation_contract("MOTHER-VALVE-1", registry)
    assert _zone_contracts(registry)["MOTHER-VALVE-1"] == resolved
    assert _command_mapping(resolved) == {
        "channel": 3, "on": "simulated_mother_ch3_on", "off": "simulated_mother_ch3_off"}

    uncommissioned = deepcopy(registry)
    uncommissioned["MOTHER-VALVE-1"] = _redigest({**future,
        "commissioned": False, "commissioning_id": None,
        "commissioning_generation": None})
    with pytest.raises(ValueError, match="rootline_irrigation_output_not_commissioned"):
        commissioned_irrigation_contract("MOTHER-VALVE-1", uncommissioned)
    assert "MOTHER-VALVE-1" not in _zone_contracts(uncommissioned)
