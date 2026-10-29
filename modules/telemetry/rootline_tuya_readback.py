"""Bounded read-only Tuya status for the configured Eskom breaker.

Official contracts: /v1.0/token?grant_type=1, /v1.0/iot-03/devices/{id}
and /status; Tuya's current HMAC-SHA256 stringToSign algorithm. No command API.
"""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
from urllib import request

HOSTS = {"eu":"https://openapi.tuyaeu.com", "us":"https://openapi.tuyaus.com",
    "cn":"https://openapi.tuyacn.com", "in":"https://openapi.tuyain.com",
    "we":"https://openapi-weaz.tuyaeu.com", "ue":"https://openapi-ueaz.tuyaus.com",
    "sg":"https://openapi-sg.iotbing.com"}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class ProviderRefusal(Exception):
    def __init__(self, status):
        self.status=status


def read_eskom_switch(*, configuration, now=None, http_open=None):
    """Return only exact identity, online state and one configured Boolean DP.

    Tokens, local keys and raw provider responses never enter the return value.
    All three reads are bounded, fixed-host HTTPS GETs; no URL override/retry.
    """
    config = configuration or {}; now = now or datetime.now(timezone.utc)
    missing = {"authoritative":False, "state":"Unknown", "status":"eskom_readback_unavailable"}
    device = str(config.get("ROOTLINE_ESKOM_DEVICE_ID") or "")
    code = str(config.get("ROOTLINE_ESKOM_SWITCH_CODE") or "")
    client = str(config.get("TUYA_CLIENT_ID") or ""); secret = str(config.get("TUYA_CLIENT_SECRET") or "")
    host = HOSTS.get(str(config.get("TUYA_REGION") or "").lower())
    if (not host or not client or not secret or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}",device)
            or not re.fullmatch(r"switch(?:_[1-9][0-9]*)?",code) or now.tzinfo is None):
        return {**missing,"status":"eskom_readback_configuration_required"}
    opener = http_open or request.build_opener(NoRedirect).open
    def get(path, token=""):
        stamp = str(int(now.timestamp()*1000))
        signed = "GET\n" + hashlib.sha256(b"").hexdigest() + "\n\n" + path
        signature = hmac.new(secret.encode(), (client+token+stamp+signed).encode(), hashlib.sha256).hexdigest().upper()
        headers = {"client_id":client,"t":stamp,"sign_method":"HMAC-SHA256","sign":signature}
        if token: headers["access_token"] = token
        with opener(request.Request(host+path,headers=headers,method="GET"),timeout=5) as response:
            if response.getcode() != 200 or response.geturl() != host+path:
                raise ValueError("provider_response_invalid")
            raw=response.read(65537)
        if len(raw)>65536: raise ValueError("provider_response_too_large")
        body=json.loads(raw)
        if body.get("success") is not True:
            # Only allowlisted numeric codes become actionable output. Never
            # return provider prose, tokens, request headers or local keys.
            code=str(body.get("code") or "")
            raise ProviderRefusal("eskom_tuya_plan_renewal_required" if code=="28841002"
                else "eskom_tuya_access_refused")
        server_at=datetime.fromtimestamp(body["t"]/1000,timezone.utc)
        if abs((server_at-now).total_seconds())>60: raise ValueError("provider_time_unproven")
        return body["result"],server_at
    try:
        auth,_=get("/v1.0/token?grant_type=1")
        token=auth.get("access_token")
        if not isinstance(token,str) or not token: return missing
        detail,_=get("/v1.0/iot-03/devices/"+device,token)
        if (detail.get("id")!=device or detail.get("name")!="Eskom Grid"
                or detail.get("online") is not True): return missing
        status,at=get("/v1.0/iot-03/devices/"+device+"/status",token)
        values=[row.get("value") for row in status if isinstance(row,dict) and row.get("code")==code]
        if len(values)!=1 or type(values[0]) is not bool: return missing
        result={"authoritative":True,"device_id":device,"device_name":"Eskom Grid",
            "switch_code":code,"online":True,"state":"ON" if values[0] else "OFF",
            "retrieved_at":at.isoformat(),"provider":"tuya_cloud"}
        return {**result,"evidence_id":hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()}
    except ProviderRefusal as exc:
        return {**missing,"status":exc.status}
    except Exception:
        return missing
