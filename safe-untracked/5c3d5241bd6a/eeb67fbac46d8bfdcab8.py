import json,os
from pathlib import Path
from dotenv import load_dotenv
import psycopg
load_dotenv(Path(r"C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system\.env"),override=True)
execution="ROOTLINE-EXECUTION-CCFAB503B553115FA33B4108"
with psycopg.connect(os.environ["DATABASE_URL"],options="-c default_transaction_read_only=on",connect_timeout=8) as c:
 with c.cursor() as q:
  q.execute("set transaction read only");q.execute("set local statement_timeout='5000ms'")
  q.execute("""select created_at,review_json->'rootline_execution' from public.sam_live_stock_conversation_review_events
   where event_source='rootline_irrigation_execution' and review_json->'rootline_execution'->>'execution_id'=%s
   order by created_at,review_event_id""",(execution,))
  rows=[{"created_at":created.isoformat(),"action":x.get("action"),"state":x.get("state"),
    "shutdown_verified":x.get("shutdown_verified"),"verified_runtime_seconds":x.get("verified_runtime_seconds"),
    "reason":x.get("reason"),"off_state":(x.get("shutdown_evidence") or {}).get("state")}
    for created,x in q.fetchall()]
print(json.dumps({"execution_id":execution,"events":rows,"read_only":True},sort_keys=True))
