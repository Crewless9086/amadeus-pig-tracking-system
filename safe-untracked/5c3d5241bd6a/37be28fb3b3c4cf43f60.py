import json, os, time, urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(r"C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system\.env"), override=True)
service=os.environ["RENDER_SERVICE_ID"]
target="82ef4d7e4d6f6019d71c961de0029cc2bfd8b37a"
headers={"Authorization":f"Bearer {os.environ['RENDER_API_KEY']}","Accept":"application/json"}
deadline=time.monotonic()+600
while True:
    req=urllib.request.Request(f"https://api.render.com/v1/services/{service}/deploys?limit=10",headers=headers)
    with urllib.request.urlopen(req,timeout=30) as response: rows=json.load(response)
    selected=None
    for wrapper in rows:
        deploy=wrapper.get("deploy") or wrapper
        commit=str((deploy.get("commit") or {}).get("id") or deploy.get("commitId") or "")
        if commit==target:
            selected={"id":deploy.get("id"),"status":deploy.get("status"),"commit":commit,
                      "createdAt":deploy.get("createdAt"),"finishedAt":deploy.get("finishedAt")}
            break
    print(json.dumps(selected or {"status":"target_not_visible"},sort_keys=True),flush=True)
    if selected and selected["status"]=="live": break
    if selected and selected["status"] in {"build_failed","update_failed","canceled","deactivated"}: raise SystemExit(2)
    if time.monotonic()>=deadline: raise SystemExit(3)
    time.sleep(15)
