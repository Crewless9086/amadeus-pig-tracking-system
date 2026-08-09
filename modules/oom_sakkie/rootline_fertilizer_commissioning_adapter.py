"""Read-only ROOTLINE adapter for a contextual fertilizer commissioning reply."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

CONTRACT_VERSION = "rootline_fertilizer_commissioning_followup_v1"
DEVICE_ID = "100204d497"
PRESENCE_MAX_AGE_SECONDS = 300
ZERO_AUTHORITY = {"configuration_write": False, "hardware_control": False,
                  "farm_write": False, "telegram_send": False}


def assess_fertilizer_commissioning_reply(context: Mapping[str, Any], *, now=None,
                                           readback_loader=None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if (str(context.get("contract_version") or "") != "oom_sakkie_contextual_specialist_followup_v1"
            or str(context.get("specialist_identity") or "") != "ROOTLINE"
            or not str(context.get("mission_id") or "")
            or str(context.get("card_mission_id") or "") != str(context.get("mission_id") or "")
            or not str(context.get("parent_telegram_message_id") or "")
            or str(context.get("contextual_task_kind") or "") != "fertilizer_commissioning"
            or context.get("authority") != {"readback": True, "configuration_write": False,
                                             "hardware_control": False, "telegram_send": False}):
        return _contained("fertilizer_context_binding_invalid")
    try:
        snapshot = dict((readback_loader or _readback)() or {})
    except Exception:
        return _contained("fertilizer_readback_unavailable")
    channels = {row.get("channel"): row for row in snapshot.get("channels") or ()
                if isinstance(row, Mapping)}
    ch1, ch2 = channels.get(1, {}), channels.get(2, {})
    all_off = len(channels) == 4 and all(row.get("output_state") == "OFF" for row in channels.values())
    restoration_off = len(channels) == 4 and all(
        row.get("power_restoration_state") == "OFF" for row in channels.values())
    config = {
        "device_id": snapshot.get("device_id"),
        "ch1_inching_enabled": ch1.get("native_auto_off_enabled"),
        "ch1_inching_seconds": ch1.get("native_auto_off_seconds"),
        "ch2_inching_enabled": ch2.get("native_auto_off_enabled"),
        "ch2_inching_seconds": ch2.get("native_auto_off_seconds"),
        "all_outputs_off": all_off,
        "power_restoration_off": restoration_off,
        "timers_disabled": snapshot.get("timers_enabled") is False,
        "interlock_disabled": snapshot.get("interlock_enabled") is False,
        "scenes_disabled": snapshot.get("scenes_enabled") is False,
        "interlock_provider_supported": snapshot.get("provider_interlock_supported") is True,
        "scenes_provider_supported": snapshot.get("provider_scenes_supported") is True,
        "provider_control_calls": snapshot.get("provider_control_calls"),
    }
    owner_setup_confirmed = (context.get("owner_confirmed_requested_setup") is True
        and tuple(context.get("required_owner_confirmations") or ())
            == ("interlock_off", "no_enabled_scene")
        and context.get("owner_confirmation_facts")
            == {"interlock_off": True, "no_enabled_scene": True}
        and len(str(context.get("confirmation_prompt_sha256") or "")) == 64)
    interlock_ok = (config["interlock_disabled"]
                    or (not config["interlock_provider_supported"] and owner_setup_confirmed))
    scenes_ok = (config["scenes_disabled"]
                 or (not config["scenes_provider_supported"] and owner_setup_confirmed))
    safe = (snapshot.get("authoritative") is True and snapshot.get("device_id") == DEVICE_ID
        and config["ch1_inching_enabled"] is True and config["ch1_inching_seconds"] == 120
        and config["ch2_inching_enabled"] is True and config["ch2_inching_seconds"] == 300
        and all_off and restoration_off and config["timers_disabled"]
        and interlock_ok and scenes_ok
        and snapshot.get("provider_control_calls") == 0)
    base = {"success": True, "contract_version": CONTRACT_VERSION,
        "authority": dict(ZERO_AUTHORITY), "hardware_commands": 0,
        "controller_readback": config, "configuration_verified": safe,
        "mixing_enabled": False, "injection_enabled": False,
        "writes_farm_data": False, "provider_control_calls": 0}
    if not safe:
        conflicts = []
        if config["ch2_inching_enabled"] is not True:
            conflicts.append("CH2 Inching still reads OFF")
        if config["ch2_inching_seconds"] != 300:
            conflicts.append("CH2 is not set to 300 seconds")
        if not all_off:
            conflicts.append("not every output reads OFF")
        if not restoration_off:
            conflicts.append("power-restoration OFF is not proven")
        if not config["timers_disabled"]:
            conflicts.append("a device timer remains enabled")
        system_gaps = []
        if not config["interlock_provider_supported"] and not owner_setup_confirmed:
            system_gaps.append("ROOTLINE still needs owner evidence that Interlock is OFF")
        elif not config["interlock_disabled"]:
            conflicts.append("Interlock OFF is not proven")
        if not config["scenes_provider_supported"] and not owner_setup_confirmed:
            system_gaps.append("ROOTLINE still needs owner evidence that no Scene is enabled")
        elif not config["scenes_disabled"]:
            conflicts.append("no enabled Scene is not proven")
        af = str(context.get("language") or "").lower() == "af"
        owner_action = "; ".join(conflicts) if conflicts else "None"
        rootline_action = "; ".join(system_gaps) if system_gaps else "ROOTLINE has retained the remaining setup evidence"
        owner_action_text = ("Skakel CH2 Inching aan vir 300 sekondes"
                             if af and conflicts == ["CH2 Inching still reads OFF"]
                             else owner_action)
        answer = (("<b>KUNSMISKONTROLE — EEN OPDATERING NODIG</b>\n\n"
                   f"<b>Jou volgende stap:</b> {owner_action_text}.\n"
                   f"<b>ROOTLINE:</b> {rootline_action}.\n\n"
                   "Maak asseblief net die genoemde verandering en sê wanneer jy weer by die kunsmiskleppe is.")
                  if af else
                  ("<b>FERTILIZER CHECK — ONE UPDATE NEEDED</b>\n\n"
                   f"<b>Your next step:</b> {owner_action}.\n"
                   f"<b>ROOTLINE:</b> {rootline_action}.\n\n"
                   "Please make only the named change and tell me when you are back at the fertilizer valves."))
        return {**base, "status": "waiting_for_input", "safety_conflicts": conflicts,
            "system_evidence_gaps": system_gaps, "answer": answer}
    observed = _time(context.get("provider_timestamp"))
    fresh = observed is not None and 0 <= (now - observed).total_seconds() <= PRESENCE_MAX_AGE_SECONDS
    af = str(context.get("language") or "").lower() == "af"
    if not fresh:
        return {**base, "status": "waiting_for_input",
            "answer": (("<b>KUNSMISKONTROLE — GEREED WANNEER JY IS</b>\n\n"
                        "Die beheerder se veiligheidsopstelling is bevestig. Is jy nog by die kunsmiskleppe en kan jy die menger, pomp, hersirkulasie en ander kanale dophou?")
                       if af else
                       ("<b>FERTILIZER CHECK — READY WHEN YOU ARE</b>\n\n"
                        "The controller safety setup is verified. Are you still at the fertilizer valves and able to observe the mixer, pump, recirculation and unrelated channels?"))}
    return {**base, "status": "specialist_accepted", "ready_for_supervised_proof": True,
        "answer": (("<b>KUNSMISKONTROLE — GEREED</b>\n\n"
                    "Jou huidige teenwoordigheid is aan die bestaande kunsmisopstelling gekoppel en die beheerder se veiligheidskontrole het geslaag. ROOTLINE mag nou slegs die beheerde mengerproef onder toesig begin.")
                   if af else
                   ("<b>FERTILIZER CHECK — READY</b>\n\n"
                    "Your current presence is linked to the existing fertilizer setup and the controller safety readback passed. ROOTLINE may now begin only the governed supervised mixer proof."))}


def _readback():
    from modules.telemetry.rootline_ewelink_oauth_store import PostgresOAuthTokenStore
    from modules.telemetry.rootline_ewelink_readback import read_registered_device
    return read_registered_device(DEVICE_ID, token_store=PostgresOAuthTokenStore())


def _contained(status):
    return {"success": False, "status": status, "contract_version": CONTRACT_VERSION,
        "authority": dict(ZERO_AUTHORITY), "hardware_commands": 0,
        "configuration_verified": False, "mixing_enabled": False,
        "injection_enabled": False, "writes_farm_data": False,
        "provider_control_calls": 0}


def _time(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None
