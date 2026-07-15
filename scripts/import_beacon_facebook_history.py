from pathlib import Path
import json
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from modules.sales.beacon_facebook_history import import_beacon_facebook_history


if __name__ == "__main__":
    result, status_code = import_beacon_facebook_history()
    print(json.dumps({**result, "status_code": status_code}, indent=2))
    raise SystemExit(0 if status_code < 400 else 1)
