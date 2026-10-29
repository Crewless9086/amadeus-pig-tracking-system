"""Exact commissioned Eskom hysteresis on the existing ROOTLINE event rail."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from threading import RLock
from urllib import request, parse
from modules.telemetry.rootline_energy_policy import managed_energy_decision
from modules.telemetry.rootline_tuya_readback import read_eskom_switch, NoRedirect


class EskomObservationCache:
    """Per-process request throttle, never command evidence or authority.

    Reserve before reading so concurrent unchanged cycles share the same limit.
    A changed decision bypasses the interval but still requires a new read.
    Restarting the process loses this optimization, not any durable claim.
    """
    def __init__(self):
        self._lock = RLock()
        self._entries = {}

    def reserve(self, key, intent, now):
        with self._lock:
            old = self._entries.get(key)
            if old and old["intent"] == intent and timedelta(0) <= now-old["at"] < timedelta(minutes=15):
                return dict(old)
            if len(self._entries) >= 16:
                self._entries.pop(next(iter(self._entries)))
            self._entries[key] = {"intent":intent, "at":now,
                "status":"eskom_readback_in_progress", "verified":False}
            return None

    def finish(self, key, intent, now, observed, status):
        with self._lock:
            old = self._entries.get(key)
            if old and old["intent"] == intent and old["at"] == now:
                old.update(status=status, verified=bool(observed))
                if observed:
                    old.update(last_verified_state=observed["state"],
                        last_verified_at=observed["retrieved_at"])


_OBSERVATIONS = EskomObservationCache()


def run_eskom_cycle(*, power, configuration, canonical, store, now=None,
        readback=None, dispatch=None, allow_new_commands=True, clock=None,
        observation_cache=None):
    now=now or datetime.now(timezone.utc); config=configuration or {}
    clock=clock or ((lambda:now) if readback is not None else lambda:datetime.now(timezone.utc))
    device=str(config.get("ROOTLINE_ESKOM_DEVICE_ID") or "")
    decision=managed_energy_decision(power,now=now)
    def result(status, **extra):
        return {"success":True,"status":status,"hardware_commands":0,
            "writes_farm_data":False,"blocks_bc":False,"decision":decision,**extra}
    record=(canonical or {}).get("device_record") or {}
    key="ifttt_smartlife:smartlife_owner_account:"+device+":1"
    envelope=record.get("authority_envelope") or {}
    configured = (bool(re.fullmatch(r"[A-Za-z0-9_-]{8,128}",device))
        and str(config.get("ROOTLINE_ESKOM_ENABLED") or "").lower()=="true"
        and bool(config.get("ROOTLINE_IFTTT_MAKER_KEY"))
        and config.get("ROOTLINE_ESKOM_ON_EVENT")=="eskom_grid_on"
        and config.get("ROOTLINE_ESKOM_OFF_EVENT")=="eskom_grid_off")
    bound=(record.get("device_id")==device and record.get("channel")==1
        and record.get("provider")=="ifttt_smartlife" and record.get("device_type")=="breaker"
        and record.get("provider_account_binding")=="smartlife_owner_account"
        and record.get("commissioning_stage")=="standing_active" and record.get("standing_authority") is True
        and record.get("independent_physical_identity_proven") is True
        and record.get("independent_fail_stop_proven") is True
        and envelope.get("eskom_policy")=="owner_30_on_35_solar_recovery_off"
        and envelope.get("switch_code")==config.get("ROOTLINE_ESKOM_SWITCH_CODE"))
    if not configured or not bound:
        return result("eskom_configuration_or_commissioning_required")
    reader=readback or (lambda:read_eskom_switch(configuration=config,now=clock()))
    readback_status="eskom_switch_readback_unproven"
    def current():
        nonlocal readback_status
        readback_status="eskom_switch_readback_unproven"
        value=reader()
        # Only adapter-defined, sanitized reasons cross the owner-facing boundary.
        if value.get("status") in {"eskom_tuya_plan_renewal_required",
                "eskom_tuya_access_refused", "eskom_readback_configuration_required",
                "eskom_readback_unavailable"}:
            readback_status=value["status"]
        read_at=clock()
        try: at=datetime.fromisoformat(value["retrieved_at"].replace("Z","+00:00"))
        except (KeyError,ValueError,TypeError): return None
        return value if (value.get("authoritative") is True and value.get("device_id")==device
            and value.get("switch_code")==config.get("ROOTLINE_ESKOM_SWITCH_CODE")
            and value.get("online") is True and value.get("state") in {"ON","OFF"}
            and value.get("evidence_id") and at.tzinfo and timedelta(0)<=read_at-at<=timedelta(minutes=2)) else None
    commands=0; writes=False
    try:
        events=store("load_eskom_events",key)
        completed={row["execution_id"] for row in events if row.get("action")=="record_eskom_completed"}
        outcomes={row["execution_id"] for row in events if row.get("action")=="record_eskom_command_outcome"}
        prior_transition=next((row["execution_id"] for row in reversed(events)
            if row.get("action")=="record_eskom_completed"),None)
        pending=[row for row in events if row.get("action")=="claim_eskom_before_command"
            and row.get("execution_id") not in completed]
        if pending and (len(pending)!=1 or pending[0]["execution_id"] not in outcomes):
            return result("eskom_command_reconciliation_required",success=False)
        desired=decision["eskom_requested_state"]
        if not pending and (desired=="UNCHANGED" or not allow_new_commands):
            return result("eskom_current_state_retained",readback_not_requested=True)
        cache=observation_cache if observation_cache is not None else _OBSERVATIONS
        cache_key=(key,config.get("ROOTLINE_ESKOM_SWITCH_CODE"),
            canonical.get("evidence_digest"),prior_transition)
        intent=("reconcile",pending[0]["execution_id"]) if pending else ("decision",desired)
        attempted_at=now
        cached=cache.reserve(cache_key,intent,attempted_at)
        if cached is not None:
            return result("eskom_readback_poll_deferred",success=bool(not pending
                and cached["verified"] and cached.get("last_verified_state")==desired),
                readback_status=cached["status"],
                next_readback_at=(cached["at"]+timedelta(minutes=15)).isoformat(),
                last_verified_state=cached.get("last_verified_state"),
                last_verified_at=cached.get("last_verified_at"),
                current_controller_state="Unknown")
        try:
            observed=current()
        except Exception:
            cache.finish(cache_key,intent,attempted_at,None,"eskom_readback_unavailable")
            raise
        cache.finish(cache_key,intent,attempted_at,observed,
            "eskom_switch_readback_verified" if observed else readback_status)
        if not observed: return result(readback_status,success=False)
        if pending:
            # Matching external state cannot release a sender which has not
            # durably returned. A crash before its outcome stays contained.
            if (len(pending)!=1 or pending[0]["execution_id"] not in outcomes
                    or observed["state"]!=pending[0].get("desired_state")):
                return result("eskom_command_reconciliation_required",success=False)
            saved=store("record_eskom_completed",{**pending[0],"readback":observed})
            return result("eskom_command_reconciled" if saved.get("success") else "eskom_completion_persistence_unproven",
                success=saved.get("success") is True,writes_farm_data=saved.get("created") is True)
        decision=managed_energy_decision(power,now=clock())
        desired=decision["eskom_requested_state"]
        if desired=="UNCHANGED" or desired==observed["state"] or not allow_new_commands:
            return result("eskom_current_state_retained")
        material={"device_key":key,"device_id":device,"desired_state":desired,
            "decision":decision,"power_evidence":power,"previous_readback":observed,
            "expected_transition_id":prior_transition,"baseline_sha256":canonical.get("evidence_digest")}
        identity="ROOTLINE-ESKOM-"+hashlib.sha256(json.dumps(material,sort_keys=True).encode()).hexdigest()[:24].upper()
        claim={**material,"execution_id":identity,"claimed_at":now.isoformat()}
        saved=store("claim_eskom_before_command",claim)
        if saved.get("created") is not True: return result("eskom_claim_already_owned")
        writes=True
        sender=dispatch or (lambda state,identity: _send(config,state,identity))
        def send_at_edge():
            nonlocal commands
            # Recheck after provider latency and lock acquisition, not against
            # the clock captured at the beginning of this worker cycle.
            edge=managed_energy_decision(power,now=clock())
            if not edge["fresh"] or edge["eskom_requested_state"]!=desired:
                return {"accepted_unambiguous":False,"command_not_sent":True}
            commands=1
            try: return sender(desired,identity)
            except Exception: return {"accepted_unambiguous":False}
        stored=store("dispatch_eskom_command_edge",{**claim,"dispatch":send_at_edge})
        if stored.get("dispatched") is not True:
            return result("eskom_command_reconciliation_required",success=False,
                hardware_commands=commands,writes_farm_data=True)
        final=current()
        cache.finish(cache_key,intent,attempted_at,final,
            "eskom_switch_readback_verified" if final else readback_status)
        if not final or final["state"]!=desired or stored.get("success") is not True:
            return result("eskom_command_reconciliation_required",success=False,
                hardware_commands=commands,writes_farm_data=True,readback_status=readback_status)
        saved=store("record_eskom_completed",{**claim,"readback":final})
        return result("eskom_state_verified" if saved.get("success") else "eskom_completion_persistence_unproven",
            success=saved.get("success") is True,hardware_commands=1,writes_farm_data=True)
    except Exception:
        return result("eskom_evidence_or_persistence_unavailable",success=False,
            hardware_commands=commands,writes_farm_data=writes,effects_unknown=commands>0)


def _send(config,state,identity):
    event=config["ROOTLINE_ESKOM_ON_EVENT" if state=="ON" else "ROOTLINE_ESKOM_OFF_EVENT"]
    url="https://maker.ifttt.com/trigger/"+event+"/with/key/"+parse.quote(config["ROOTLINE_IFTTT_MAKER_KEY"],safe="")
    body=json.dumps({"value1":identity}).encode()
    try:
        with request.build_opener(NoRedirect).open(request.Request(url,data=body,
                headers={"Content-Type":"application/json"},method="POST"),timeout=5) as response:
            accepted=200<=response.getcode()<300 and response.geturl()==url
            response.read(4096)
        return {"accepted_unambiguous":accepted}
    except Exception:
        return {"accepted_unambiguous":False}
