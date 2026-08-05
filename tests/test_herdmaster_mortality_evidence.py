from datetime import date
import sys
from types import SimpleNamespace

from modules.pig_weights.herdmaster_mortality_evidence import load_current_mortality_evidence, normalize_current_mortality_evidence


def test_loader_preserves_future_undated_and_noncurrent_rows_without_inventing_death_pen():
    result=normalize_current_mortality_evidence(
        deaths=[{"pig_id":"P1","exit_date":"2026-08-06","exit_reason":"Died","litter_id":"L1","initial_pen_id":"PEN-BIRTH","status":"Dead"}],
        historical_deaths=[
            {"pig_id":"P1","exit_date":"2026-08-06","exit_reason":"Died","litter_id":"L1","initial_pen_id":"PEN-BIRTH","status":"Dead"},
            {"pig_id":"P2","exit_date":None,"exit_reason":"Died","litter_id":"L2","initial_pen_id":"PEN-OLD","status":"Dead"},
            {"pig_id":"P3","exit_date":"2026-07-01","exit_reason":"Died","litter_id":"L3","initial_pen_id":"PEN-OLD","status":"Dead"}],
        litters=[],weights=[],weather=[],analysis_end=date(2026,8,5))
    events={row["pig_id"]:row for row in result["mortality_events"]}
    assert events["P1"]["effective_date"]=="2026-08-06"
    assert events["P3"]["canonical_status"]=="superseded"
    assert "pen_id" not in events["P1"] and events["P1"]["initial_pen_id"]=="PEN-BIRTH"
    assert result["undated_identity_accounting"]==[
        {"pig_id":"P2","classification":"insufficient_evidence","effective_date":None}]


def test_duplicate_current_litter_representations_fail_closed_only_for_their_losses():
    litters=[
        {"litter_id":"L-A","farrowing_date":"2026-06-01","sow_pig_id":"S1","boar_pig_id":"B1","born_alive":8,"weaned_count":7},
        {"litter_id":"L-B","farrowing_date":"2026-06-01","sow_pig_id":"S1","boar_pig_id":"B1","born_alive":8,"weaned_count":7}]
    deaths=[
        {"pig_id":"PA","exit_date":"2026-07-01","exit_reason":"Died","litter_id":"L-A","initial_pen_id":"P1","status":"Dead"},
        {"pig_id":"PC","exit_date":"2026-07-02","exit_reason":"Died","litter_id":"L-C","initial_pen_id":"P2","status":"Dead"}]
    result=normalize_current_mortality_evidence(deaths=deaths,historical_deaths=deaths,
        litters=litters,weights=[],weather=[],analysis_end=date(2026,8,5))
    confirmation={row["pig_id"]:row["confirmation"] for row in result["mortality_events"]}
    assert confirmation=={"PA":"conflicting","PC":"confirmed"}


def test_sql_loader_is_read_only_and_historical_query_accepts_mortality_exit_reason(monkeypatch):
    calls=[]
    class Cursor:
        def __init__(self,rows):
            self.rows=rows
            names=(list(rows[0]) if rows else [])
            self.description=[SimpleNamespace(name=name) for name in names]
        def fetchall(self): return [tuple(row[name] for name in [c.name for c in self.description]) for row in self.rows]
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def execute(self,sql,params=None):
            calls.append((sql,params))
            if "current_canonical_pigs" in sql: return Cursor([])
            if "from public.pigs" in sql:
                return Cursor([{"pig_id":"P9","exit_date":"2026-07-01","exit_reason":"Died",
                    "litter_id":"L9","initial_pen_id":"PEN-X","status":"Inactive"}])
            return Cursor([])
    connect_args={}
    def connect(url,**kwargs): connect_args.update(kwargs); return Connection()
    monkeypatch.setitem(sys.modules,"psycopg",SimpleNamespace(connect=connect))
    result=load_current_mortality_evidence(analysis_end=date(2026,8,5),database_url="postgres://example")
    historical_sql=next(sql for sql,_ in calls if "from public.pigs" in sql)
    assert "exit_reason" in historical_sql and "stillborn" in historical_sql
    assert "default_transaction_read_only=on" in connect_args["options"]
    assert result["mortality_events"][0]["pig_id"]=="P9"
    assert result["mortality_events"][0]["canonical_status"]=="superseded"
