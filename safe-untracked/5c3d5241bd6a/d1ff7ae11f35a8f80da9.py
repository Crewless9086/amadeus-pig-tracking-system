import json,os,time
from pathlib import Path
import psycopg
from dotenv import load_dotenv
load_dotenv(Path(r"C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system\.env"),override=True)
deadline=time.monotonic()+1200
while time.monotonic()<deadline:
    with psycopg.connect(os.environ["DATABASE_URL"],connect_timeout=5,
        options="-c default_transaction_read_only=on -c statement_timeout=5000") as c:
        with c.cursor() as q:
            q.execute("""select created_at,review_json->'automatic_reassessment'
              from public.sam_live_stock_conversation_review_events
             where event_source='oom_sakkie_automatic_reassessment'
               and created_at>'2026-08-16 07:53:57+00'
               and review_event_id like '%-OUTCOME'
             order by created_at desc limit 1""")
            row=q.fetchone()
    if row:
        x=row[1]
        print(json.dumps({"created_at":row[0].isoformat(),**{k:x.get(k) for k in (
            "schedule_identity","due_at","invoked_at","status","terminal_outcome",
            "next_due_at","telegram_sends","hardware_commands","writes_farm_data")},
            "read_only":True},sort_keys=True));raise SystemExit(0)
    time.sleep(15)
print(json.dumps({"status":"timeout_waiting_for_provider_scheduler","read_only":True}));raise SystemExit(2)
