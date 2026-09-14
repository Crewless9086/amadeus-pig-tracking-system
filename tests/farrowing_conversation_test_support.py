"""In-memory fault injection for farrowing conversation unit tests."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from threading import RLock

from modules.oom_sakkie.protected_action_claims import canonical_preview_digest

STAMP = datetime.fromisoformat("2026-08-22T07:30:00+02:00")


class MemoryFarrowingStore:
    def __init__(self, now=STAMP):
        self.now = now
        self.receipts, self.claims, self.cards = [], {}, {}
        self.fail_save = False
        self.lock = RLock()

    def read(self, actor, chat):
        rows = deepcopy([row for row in self.receipts if row["owner_user_id"] == actor
                         and row["private_chat_id"] == chat])
        for row in rows:
            row["_card_ids"] = self.cards.get(row["context_id"], [])
            claim = self.claims.get((row.get("outcome") or {}).get("callback_token"))
            if claim and claim["owner_user_id"] == actor and claim["private_chat_id"] == chat:
                row["_claim_status"], row["_saved_result"] = claim["status"], deepcopy(claim.get("result"))
        return rows

    @contextmanager
    def locked(self, actor, chat):
        with self.lock:
            before = deepcopy((self.receipts, self.claims))
            try:
                yield _MemoryTransaction(self, actor, chat)
            except Exception:
                self.receipts, self.claims = before
                raise

    def create_claim(self, **kwargs):
        token = "preview" + str(len(self.claims) + 1)
        row = {**deepcopy({key: value for key, value in kwargs.items() if key != "connect_factory"}),
               "callback_token": token, "status": "active", "expires_at": self.now + timedelta(minutes=15),
               "preview_digest": canonical_preview_digest(kwargs["action_kind"], kwargs["preview_payload"])}
        self.claims[token] = row
        return row


class _MemoryTransaction:
    def __init__(self, store, actor, chat):
        self.store, self.actor, self.chat = store, actor, chat

    def rows(self):
        return self.store.read(self.actor, self.chat)

    def claim(self, token):
        row = self.store.claims.get(token)
        return row if row and row["owner_user_id"] == self.actor and row["private_chat_id"] == self.chat else None

    def retire(self, context_id):
        rows = [row for row in self.store.claims.values() if row["mission_id"] == context_id
                and row["owner_user_id"] == self.actor and row["private_chat_id"] == self.chat]
        protected = [row for row in rows if row["status"] in ("executing", "completed")]
        if not protected:
            for row in rows:
                if row["status"] == "active":
                    row["status"] = "changed"
        return protected

    @contextmanager
    def connection(self):
        yield None

    def save(self, receipt):
        if self.store.fail_save:
            raise RuntimeError("Synthetic interruption before retained receipt commit")
        assert not any(row["provider_message_id"] == receipt["provider_message_id"] for row in self.rows())
        self.store.receipts.append(deepcopy(receipt))


def canonical(**overrides):
    return {"evidence_generation": "SYNTHETIC-FARROW-GEN", "animals": [
        {"pig_id": "SOW-LINDA", "tag_number": "Linda", "name": None,
         "status": "Active", "on_farm": True, "sex": "Female"},
        {"pig_id": "SOW-BONNIE", "tag_number": "Bonnie", "name": None,
         "status": "Active", "on_farm": True, "sex": "Female"}],
        "matings": [], "litters": [], **overrides}


def message(facts, *, provider=1, seconds=0, continuation=False, text=None, reply="", language="en"):
    return {"telegram_user_id": "42", "telegram_chat_id": "42",
        "provider_message_id": str(provider), "provider_timestamp": (STAMP + timedelta(seconds=seconds)).isoformat(),
        "text": text or str(facts), "reply_to_message_id": reply, "output_language": language,
        "semantic": {"intent": "record_farrowing_litter", "domain": "herd_management",
            "message_kind": "correction" if continuation else "observation", "confidence": 0.97,
            "continuation": continuation, "farrowing_litter": facts}}


def complete_facts(**overrides):
    return {"sow_ref": "Linda", "farrowing_date": "2026-08-22", "total_born": 9,
            "born_alive": 8, "mummified": 1, **overrides}


def saved_readback(preview):
    from modules.oom_sakkie.herdmaster_farrowing_runtime import _operation_ids
    litter, pigs = _operation_ids(preview)
    return {"litter_id": litter, "sow_pig_id": preview["sow_pig_id"],
        "boar_pig_id": preview.get("father_pig_id"), "farrowing_date": preview["farrowing_date"],
        "total_born": preview["counts"]["total_born"], "born_alive": preview["counts"]["born_alive"],
        "stillborn_count": preview["counts"]["stillborn"], "mummified_count": preview["counts"]["mummified"],
        "pig_ids": pigs, "follow_up_case_id": "SYNTHETIC-MANAGER-CASE"}
