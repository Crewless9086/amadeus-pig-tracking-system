import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

from modules.sales.chatwoot_history_learning import recover_chatwoot_learning


def main():
    parser = argparse.ArgumentParser(description="Recover private SAM learning evidence from Chatwoot history.")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--apply", action="store_true", help="Append deduplicated evidence. Default is read-only preview.")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()
    load_dotenv(args.env_file)
    result = recover_chatwoot_learning(days=args.days, max_pages=args.max_pages, workers=args.workers, dry_run=not args.apply)
    print(json.dumps(result, indent=2, default=str))
    raise SystemExit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
