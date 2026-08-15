import modules.oom_sakkie.beacon_media_review_worker as worker
import modules.beacon.media_intake as media_intake


ENV={"BEACON_TELEGRAM_MEDIA_INTAKE_ENABLED":"true",
     "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"100",
     "OOM_SAKKIE_DAILY_MANAGER_OWNER_USER_ID":"100"}


def packet(*, state="pending_or_mixed"):
    return {"success":True,"intake_group_id":"GROUP-BELLA",
        "album_completed_at":"2026-08-15T12:44:52+00:00",
        "album_digest":"d"*64,"library_state":state,"stored_count":8,
        "owner_context":"Bella, eight photos"}


def completed_card(_group):
    return [{"state":"updated","task_state":"completed","mission_id":"GROUP-BELLA",
        "card_mission_id":"GROUP-BELLA","specialist_identity":"BEACON_MEDIA",
        "owner_user_id":"100","chat_id":"100","telegram_message_id":"3637"}]


def presenter(parsed, **kwargs):
    assert parsed["provider_message_id"]=="canonical:album-completed:GROUP-BELLA"
    assert parsed["provider_timestamp"]=="2026-08-15T12:44:52+00:00"
    assert kwargs["album_loader"]()[0]["album_digest"]=="d"*64
    return {"success":True,"status":"private_media_review_presented",
        "mission_id":"GROUP-BELLA:LIBRARY","card_mission_id":"GROUP-BELLA:LIBRARY",
        "callback_token":"opaque","answer":"Library choice",
        "reply_markup":{"inline_keyboard":[]}},200


def test_pending_album_is_presented_on_existing_provider_card_and_bound():
    calls=[]
    def deliver(parsed,result,**kwargs):
        calls.append((parsed,result,kwargs))
        return {"success":True,"status":"family_message_updated",
            "telegram_message_id":"3637","telegram_sends":0,"telegram_edits":1}
    bound=[]
    result=worker.run_private_media_review_cycle(environ=ENV,
        album_loader=lambda **kwargs:(packet(),200),presenter=presenter,
        deliver=deliver,binder=lambda token,message:(bound.append((token,message)) or True),
        lifecycle_loader=completed_card)
    assert result["status"]=="private_media_review_presented"
    assert result["telegram_message_id"]=="3637"
    assert result["telegram_sends"]==0 and result["telegram_edits"]==1
    assert calls[0][2]=={"specialist":"BEACON_MEDIA",
        "mission_id":"GROUP-BELLA:LIBRARY","card_mission_id":"GROUP-BELLA"}
    assert calls[0][1]["owner_visible_completion_policy"]=="verified_edit_or_new_message"
    assert bound==[("opaque","3637")]
    assert result["publishes"] is False and result["n8n_mutations"]==0


def test_decided_album_and_disabled_worker_create_no_presentation():
    invoked=[]
    decided=worker.run_private_media_review_cycle(environ=ENV,
        album_loader=lambda **kwargs:(packet(state="accepted"),200),
        presenter=lambda *args,**kwargs:invoked.append(True),lifecycle_loader=completed_card)
    disabled=worker.run_private_media_review_cycle(environ={},
        album_loader=lambda **kwargs:invoked.append(True))
    assert decided["status"]=="private_media_review_worker_no_pending_library_decision"
    assert disabled["status"]=="private_media_review_worker_disabled"
    assert invoked==[]


def test_unconfirmed_delivery_and_binding_failure_remain_recoverable():
    unconfirmed=worker.run_private_media_review_cycle(environ=ENV,
        album_loader=lambda **kwargs:(packet(),200),presenter=presenter,
        deliver=lambda *args,**kwargs:{"success":False,"status":"provider_ambiguous"},
        lifecycle_loader=completed_card)
    assert unconfirmed["status"]=="private_media_review_worker_delivery_unconfirmed"
    binding=worker.run_private_media_review_cycle(environ=ENV,
        album_loader=lambda **kwargs:(packet(),200),presenter=presenter,
        deliver=lambda *args,**kwargs:{"success":True,"telegram_message_id":"3637"},
        binder=lambda *args:False,lifecycle_loader=completed_card)
    assert binding["status"]=="private_media_review_worker_card_binding_pending"
    assert binding["telegram_message_id"]=="3637"


def test_provider_confirmed_edit_is_bound_even_when_lifecycle_receipt_write_failed():
    bound=[]
    result=worker.run_private_media_review_cycle(environ=ENV,
        album_loader=lambda **kwargs:(packet(),200),presenter=presenter,
        lifecycle_loader=completed_card,
        deliver=lambda *args,**kwargs:{"success":False,
          "status":"family_message_delivery_receipt_persistence_failed",
          "provider_delivery_confirmed":True,"telegram_message_id":"3637"},
        binder=lambda token,message:(bound.append((token,message)) or True))
    assert bound==[("opaque","3637")]
    assert result["status"]=="private_media_review_worker_delivery_unconfirmed"
    assert result["provider_delivery_confirmed"] is True


def test_second_cycle_accepts_its_own_review_event_over_completed_album_card():
    events=completed_card("GROUP-BELLA")+[{**completed_card("GROUP-BELLA")[0],
        "mission_id":"GROUP-BELLA:LIBRARY","task_state":"private_media_review_presented"}]
    result=worker.run_private_media_review_cycle(environ=ENV,
        album_loader=lambda **kwargs:(packet(),200),presenter=presenter,
        lifecycle_loader=lambda group:events,
        deliver=lambda *args,**kwargs:{"success":True,"telegram_message_id":"3637",
          "telegram_sends":0,"telegram_edits":0},binder=lambda *args:True)
    assert result["status"]=="private_media_review_presented"
    assert result["telegram_sends"]==result["telegram_edits"]==0


def test_missing_or_cross_owner_completed_card_fails_before_claim_creation():
    invoked=[]
    result=worker.run_private_media_review_cycle(environ=ENV,
        album_loader=lambda **kwargs:(packet(),200),
        lifecycle_loader=lambda group:[{**completed_card(group)[0],"owner_user_id":"999"}],
        presenter=lambda *args,**kwargs:invoked.append(True))
    assert result["status"]=="private_media_review_worker_completed_card_unproven"
    assert invoked==[]


def test_worker_starts_only_once_when_media_intake_is_enabled(monkeypatch):
    monkeypatch.setattr(worker,"_STARTED",False)
    started=[]
    class Thread:
        def __init__(self,**kwargs): started.append(kwargs)
        def start(self): started.append("started")
    monkeypatch.setattr(worker.threading,"Thread",Thread)
    assert worker.start_private_media_review_worker(environ={},runner=lambda **k:None) is False
    assert worker.start_private_media_review_worker(environ=ENV,runner=lambda **k:None) is True
    assert worker.start_private_media_review_worker(environ=ENV,runner=lambda **k:None) is False
    assert started[-1]=="started"


def test_pending_loader_skips_newer_decided_album_without_starving_bella(monkeypatch):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def execute(self,*args): pass
        def fetchall(self): return [("NEWER-DECIDED",),("GROUP-BELLA",)]
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def cursor(self): return Cursor()
    class Store:
        def __init__(self,*args): pass
        def _connect(self): return Connection()
    monkeypatch.setattr(media_intake,"IntakeStore",Store)
    monkeypatch.setattr(media_intake,"telegram_media_owner_binding",
        lambda *args,**kwargs:{"owner_principal":"OWNER","chat_hmac":"CHAT"})
    monkeypatch.setattr(media_intake,"private_album_review",
        lambda group,**kwargs:({"success":True,"intake_group_id":group,
          "library_state":"accepted" if group=="NEWER-DECIDED" else "pending_or_mixed"},200))
    result,status=media_intake.latest_pending_private_album_review(
        owner_user_id="100",private_chat_id="100")
    assert status==200 and result["intake_group_id"]=="GROUP-BELLA"
