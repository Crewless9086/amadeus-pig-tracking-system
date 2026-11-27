"""Read back native HA Store writes; its public save method can swallow errors."""
import json
from pathlib import Path

from .protocol import InvalidObservation, need


class VerifiedStore:
    def __init__(self, native, execute):
        self.native, self.execute = native, execute

    def _read(self):
        try:
            path = Path(self.native.path)
            if not path.exists():
                return None
            with path.open("rb") as handle:
                raw = handle.read(65537)
            need(len(raw) <= 65536, "replay_store_invalid")
            value = json.loads(raw)
            need(isinstance(value, dict) and value.get("key") == self.native.key
                and value.get("version") == 1 and value.get("minor_version") == 1
                and isinstance(value.get("data"), dict), "replay_store_invalid")
            return value["data"]
        except Exception:
            raise InvalidObservation("replay_store_invalid") from None

    async def async_load(self):
        # Native async_load can rename a corrupt file and return None. Preserve
        # the file and fail closed instead of silently resetting anti-replay.
        return await self.execute(self._read)

    async def async_save(self, value):
        await self.native.async_save(value)
        readback = await self.execute(self._read)
        need(readback == value, "replay_store_write_unproven")
