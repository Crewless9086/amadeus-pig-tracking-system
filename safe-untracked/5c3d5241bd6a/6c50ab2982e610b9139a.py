import json, os
from pathlib import Path
from dotenv import load_dotenv
import psycopg

load_dotenv(Path(r"C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system\.env"), override=True)
with psycopg.connect(os.environ["DATABASE_URL"], options="-c default_transaction_read_only=on", connect_timeout=8) as c:
    with c.cursor() as q:
        q.execute("set transaction read only")
        q.execute("set local statement_timeout='5000ms'")
        q.execute("""select created_at,review_json->'rootline_execution'
          from public.sam_live_stock_conversation_review_events
         where event_source='rootline_irrigation_execution'
           and review_json->'rootline_execution'->>'action'
             in ('record_eligibility','claim_before_on','mark_active','record_completed','record_job_resolution')
         order by created_at,review_event_id""")
        jobs={}
        for created,row in q.fetchall():
            jid=str(row.get("job_id") or "")
            if not jid: continue
            item=jobs.setdefault(jid,{"job_id":jid,"zone_id":row.get("zone_id"),
                "operating_date":row.get("operating_date"),"expected":row.get("expected_segment_count"),
                "requested":row.get("requested_total_duration_seconds"),"events":[]})
            item["events"].append({"created_at":created.isoformat(),"action":row.get("action"),
                "execution_id":row.get("execution_id"),"segment":row.get("segment_number") or row.get("current_segment"),
                "state":row.get("state"),"runtime":row.get("verified_runtime_seconds"),
                "shutdown_verified":row.get("shutdown_verified"),"resolution":row.get("resolution"),
                "reason":row.get("reason")})
print(json.dumps({"jobs":list(jobs.values()),"read_only":True,"secrets_exposed":False},sort_keys=True))
