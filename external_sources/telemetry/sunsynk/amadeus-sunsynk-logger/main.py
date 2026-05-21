import os, json, uuid, base64, hashlib, hmac
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import gspread
from google.oauth2.service_account import Credentials

BASE_URL = "https://openapi.sunsynk.net"
ZA_TZ = ZoneInfo("Africa/Johannesburg")


def md5_base64(raw: str) -> str:
    return base64.b64encode(hashlib.md5(raw.encode("utf-8")).digest()).decode()


def hmac_sha256_base64(message: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def build_string_to_sign(method, accept, content_md5, content_type, app_key, nonce, path):
    return (
        f"{method}\n"
        f"{accept}\n"
        f"{content_md5}\n"
        f"{content_type}\n"
        f"\n"
        f"x-ca-key:{app_key}\n"
        f"x-ca-nonce:{nonce}\n"
        f"{path}"
    )


def sunsynk_login(app_key, app_secret, username, password):
    path = "/oauth/token"
    url = f"{BASE_URL}{path}"

    body_obj = {
        "username": username,
        "password": password,
        "grant_type": "password",
        "client_id": "openapi",
    }
    body = json.dumps(body_obj, separators=(",", ":"))

    accept = "application/json"
    content_type = "application/json"
    nonce = str(uuid.uuid4())
    content_md5 = md5_base64(body)

    string_to_sign = build_string_to_sign(
        "POST", accept, content_md5, content_type, app_key, nonce, path
    )
    signature = hmac_sha256_base64(string_to_sign, app_secret)

    headers = {
        "accept": accept,
        "content-type": content_type,
        "Content-MD5": content_md5,
        "X-Ca-Key": app_key,
        "X-Ca-Nonce": nonce,
        "X-Ca-Signature": signature,
        "X-Ca-Signature-Headers": "x-ca-key,x-ca-nonce",
    }

    # Sunsynk support told you to disable SSL verification on openapi.sunsynk.net
    resp = requests.post(url, data=body, headers=headers, verify=False, timeout=30)
    resp.raise_for_status()

    j = resp.json()
    data = j.get("data") or {}
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"No access_token in response: {j}")
    return token


def gsheets_client_from_env():
    sa_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(sa_json)

    creds = Credentials.from_service_account_info(
        info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(creds)


def append_row(sheet_name, tab_name, row):
    gc = gsheets_client_from_env()
    sh = gc.open(sheet_name)
    ws = sh.worksheet(tab_name)
    ws.append_row(row, value_input_option="USER_ENTERED")


def get_json(url, headers, timeout=30):
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def main():
    app_key = os.environ["SUNSYNK_APP_KEY"]
    app_secret = os.environ["SUNSYNK_APP_SECRET"]
    username = os.environ["SUNSYNK_USERNAME"]
    password = os.environ["SUNSYNK_PASSWORD"]

    sheet_name = os.environ["GOOGLE_SHEET_NAME"]
    tab_name = os.getenv("GOOGLE_SHEET_TAB", "Sunsynk_Log")

    inverter_sn = os.environ.get("SUNSYNK_INVERTER_SN", "2111244718")

    token = sunsynk_login(app_key, app_secret, username, password)

    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {token}",
    }

    # These endpoints are on api.sunsynk.net (NOT openapi.sunsynk.net)
    flow_url = f"https://api.sunsynk.net/api/v1/inverter/{inverter_sn}/flow"
    out_url  = f"https://api.sunsynk.net/api/v1/inverter/{inverter_sn}/realtime/output"

    flow = get_json(flow_url, headers=headers)
    output = get_json(out_url, headers=headers)

    flow_data = flow.get("data") or {}
    out_data = output.get("data") or {}

    # ZA timestamp + split columns
    now_za = datetime.now(ZA_TZ)
    timestamp_za = now_za.isoformat(timespec="seconds")
    date_za = now_za.strftime("%Y-%m-%d")
    time_za = now_za.strftime("%H:%M:%S")

    # Extract core values
    soc = flow_data.get("soc")
    batt_power = flow_data.get("battPower")
    load_power = flow_data.get("loadOrEpsPower")
    grid_power = flow_data.get("gridOrMeterPower")
    gen_power = flow_data.get("genPower")

    pv_list = flow_data.get("pv") or []
    pv1 = pv_list[0].get("power") if len(pv_list) > 0 and isinstance(pv_list[0], dict) else ""
    pv2 = pv_list[1].get("power") if len(pv_list) > 1 and isinstance(pv_list[1], dict) else ""

    inv_pinv = out_data.get("pInv")  # often total PV into inverter
    inv_pac = out_data.get("pac")

    # Derived flags (useful for alerts)
    gen_active = bool(flow_data.get("genOn"))

    # "existsGrid" means capability; "grid_active" should mean it's actually being used now
    grid_active = (grid_power not in (None, "", 0))

    # Battery direction: use Sunsynk directional booleans FIRST
    to_bat = bool(flow_data.get("toBat"))   # charging
    bat_to = bool(flow_data.get("batTo"))   # discharging

    battery_charging = to_bat
    battery_discharging = bat_to

    # Safety fallback: if both are false/missing, infer from sign (this endpoint is reversed vs intuition)
    if (not battery_charging) and (not battery_discharging) and isinstance(batt_power, (int, float)):
        # Sunsynk flow: battPower > 0 often means battery supplying load (discharging)
        #               battPower < 0 often means charging
        battery_discharging = batt_power > 0
        battery_charging = batt_power < 0

    raw_json = json.dumps({"flow": flow, "output": output}, separators=(",", ":"))

    # pv_power_w preference:
    # - inv_pinv is usually best "PV into inverter"
    # - if missing, fall back to pv1+pv2 if numeric
    pv_total = inv_pinv
    if pv_total in (None, ""):
        try:
            pv_total = (pv1 or 0) + (pv2 or 0)
        except Exception:
            pv_total = ""

    append_row(sheet_name, tab_name, [
        timestamp_za,
        date_za,
        time_za,
        soc,
        batt_power,
        pv_total,
        pv1,
        pv2,
        load_power,
        grid_power,
        gen_power,
        inv_pinv,
        inv_pac,
        grid_active,
        gen_active,
        battery_charging,
        battery_discharging,
        raw_json,
    ])

    print("OK: Logged Sunsynk flow + output (ZA time + fixed battery/grid flags).")


if __name__ == "__main__":
    main()
