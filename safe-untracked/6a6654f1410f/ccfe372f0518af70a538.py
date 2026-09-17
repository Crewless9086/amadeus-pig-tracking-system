"""Least-privilege Tuya readback and state-setting transport for Borehole 1."""
from __future__ import annotations
import hashlib, hmac, json, time
from urllib import parse, request

HOSTS={"EU":"https://openapi.tuyaeu.com","WE":"https://openapi-weaz.tuyaeu.com",
       "US":"https://openapi.tuyaus.com","AZ":"https://openapi.tuyaus.com",
       "UE":"https://openapi-ueaz.tuyaus.com","IN":"https://openapi.tuyain.com"}

class TuyaProvider:
    def __init__(self, environ, http_open=None):
        self.env=environ; self.open=http_open or request.urlopen
        self.client=str(environ.get("TUYA_CLIENT_ID") or ""); self.secret=str(environ.get("TUYA_CLIENT_SECRET") or "")
        self.device=str(environ.get("TUYA_EXPECTED_BOREHOLE1_DEVICE_ID") or "")
        self.host=HOSTS.get(str(environ.get("TUYA_REGION") or "").upper())
        if not all((self.client,self.secret,self.device,self.host)): raise RuntimeError("tuya_binding_incomplete")

    def discover(self):
        token=self._token(); detail=self._call("GET",f"/v1.0/devices/{parse.quote(self.device,safe='')}",token)
        spec=self._call("GET",f"/v1.0/iot-03/devices/{parse.quote(self.device,safe='')}/specification",token)
        state=self._call("GET",f"/v1.0/iot-03/devices/{parse.quote(self.device,safe='')}/status",token)
        d=detail["result"]; statuses={x["code"]:x.get("value") for x in state["result"]}
        functions={x["code"]:x for x in spec["result"]["functions"]}
        if d.get("id")!=self.device or d.get("name") not in {"Borehole 1 Pump","Borehole Pump 1"}: raise RuntimeError("tuya_device_identity_mismatch")
        if "switch_1" not in statuses or "countdown_1" not in functions: raise RuntimeError("tuya_schema_incomplete")
        return {"device_name":d["name"],"device_id_fingerprint":hashlib.sha256(self.device.encode()).hexdigest()[:12],
          "online":d.get("online") is True,"switch":"ON" if statuses["switch_1"] else "OFF",
          "countdown_seconds":statuses.get("countdown_1"),"current_ma":statuses.get("cur_current"),
          "power_deciwatts":statuses.get("cur_power"),"voltage_decivolts":statuses.get("cur_voltage"),
          "fault":statuses.get("fault"),"power_restoration_state":"Unknown",
          "power_restoration_source":"not_exposed_by_provider_specification",
          "provider_observed_at_ms":state.get("t"),"retrieved_at_ms":int(time.time()*1000),
          "response_digest":hashlib.sha256(json.dumps({"d":d.get("id"),"s":statuses},sort_keys=True).encode()).hexdigest(),
          "provider_commands":0}

    def _token(self): return self._call("GET","/v1.0/token?grant_type=1")["result"]["access_token"]
    def _call(self, method, path, token=None, payload=None):
        body=json.dumps(payload,separators=(",",":")).encode() if payload is not None else b""
        ts=str(int(time.time()*1000)); content=hashlib.sha256(body).hexdigest(); canonical=f"{method}\n{content}\n\n{path}"
        sign=hmac.new(self.secret.encode(),(self.client+(token or "")+ts+canonical).encode(),hashlib.sha256).hexdigest().upper()
        headers={"client_id":self.client,"sign":sign,"t":ts,"sign_method":"HMAC-SHA256","Content-Type":"application/json"}
        if token: headers["access_token"]=token
        if method != "GET": raise RuntimeError("tuya_readback_adapter_is_read_only")
        with self.open(request.Request(self.host+path,data=body or None,headers=headers,method=method),timeout=20) as response: value=json.load(response)
        if value.get("success") is not True: raise RuntimeError("tuya_provider_rejected")
        return value
