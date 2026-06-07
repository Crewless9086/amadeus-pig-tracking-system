import json
import os
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
    url = os.getenv("OOM_SAKKIE_LLM_ROUTER_URL", "").strip() or "https://api.openai.com/v1/chat/completions"
    model = os.getenv("OOM_SAKKIE_LLM_ROUTER_MODEL", "").strip()
    key = os.getenv("OPENAI_API_KEY", "").strip()
    print("url:", url)
    print("model:", model or "(missing)")
    print("key_present:", bool(key))
    if not model or not key:
        print("SKIP: model or key missing.")
        return 2

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": "Return a JSON object with key ok and value true."}],
        "response_format": {"type": "json_object"},
    }
    req = urllib_request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as response:
            print("HTTP", response.status)
            print(response.read().decode("utf-8")[:1000])
            return 0
    except urllib_error.HTTPError as exc:
        print("HTTP_ERROR", exc.code)
        print(exc.read().decode("utf-8", errors="replace")[:1200])
        return 1
    except Exception as exc:
        print("ERROR", type(exc).__name__, str(exc)[:500])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
