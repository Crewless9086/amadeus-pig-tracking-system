"""Synthetic silence and canned provider replies; no speech-recognition claim."""
import io
import json
import time

OWNER, DAD = "9910001", "9910002"
SECRET = "SYNTHETIC-VOICE-SECRET-" + "s" * 40


def environment():
    return {"OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": OWNER,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": OWNER + "," + DAD,
        "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON": json.dumps([{
            "telegram_user_id": DAD, "role": "farm_manager", "family_key": "dad",
            "permissions": ["farm_observation", "weaning"], "summary_domains": ["herd"],
            "language": "af", "authorization_id": "SYNTHETIC-VOICE-ONLY",
            "authorized_by_user_id": OWNER, "authorized_at": "2026-09-01T00:00:00+00:00"}]),
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "true",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": SECRET,
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "true",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "true",
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": SECRET,
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": "SYNTHETIC-VOICE-BOT",
        "OOM_SAKKIE_STT_ENABLED": "true", "OPENAI_API_KEY": "SYNTHETIC-NO-PROVIDER-KEY"}


def ogg_page(sequence, packets, *, granule=0, flags=0, serial=7711):
    lacing = b"".join(bytes([255]) * (len(packet) // 255) + bytes([len(packet) % 255]) for packet in packets)
    assert len(lacing) <= 255
    page = bytearray(b"OggS\0" + bytes([flags]) + granule.to_bytes(8, "little", signed=True)
        + serial.to_bytes(4, "little") + sequence.to_bytes(4, "little") + b"\0" * 4
        + bytes([len(lacing)]) + lacing + b"".join(packets))
    # Independent bitwise Ogg CRC construction, not the runtime lookup table.
    checksum = 0
    for byte in page:
        checksum ^= byte << 24
        for _ in range(8):
            checksum = ((checksum << 1) ^ (0x04C11DB7 if checksum & 0x80000000 else 0)) & 0xFFFFFFFF
    page[22:26] = checksum.to_bytes(4, "little")
    return bytes(page)


def synthetic_ogg(seconds=1):
    """A complete mono Ogg/Opus silence fixture: no private or spoken audio."""
    header = b"OpusHead\x01\x01\x00\x00" + (48000).to_bytes(4, "little") + b"\x00\x00\x00"
    tags = b"OpusTags" + b"\x00" * 8
    pages = [ogg_page(0, [header], flags=2), ogg_page(1, [tags])]
    packets = [b"\xf8\xff\xfe"] * int(seconds * 50)
    for index in range(0, len(packets), 200):
        batch = packets[index:index + 200]
        end = index + len(batch)
        pages.append(ogg_page(len(pages), batch, granule=end * 960,
                              flags=4 if end == len(packets) else 0))
    return b"".join(pages)


def voice_payload(actor=DAD, message_id=1001, *, audio=None, reply=""):
    audio = synthetic_ogg() if audio is None else audio
    message = {"message_id": message_id, "date": int(time.time()), "from": {"id": int(actor)},
        "chat": {"id": int(actor), "type": "private"},
        "voice": {"file_id": "SYNTHETIC-VOICE-" + str(message_id),
            "file_unique_id": "SYNTHETIC-UNIQUE-" + str(message_id),
            "duration": 1, "file_size": len(audio), "mime_type": "audio/ogg"}}
    if reply:
        message["reply_to_message"] = {"message_id": reply}
    return {"update_id": message_id + 100000, "message": message}


class Response(io.BytesIO):
    def __init__(self, data, url, *, mime="application/json", declared=None):
        super().__init__(data)
        self.url, self.status = url, 200
        self.headers = {"Content-Type": mime, "Content-Length": str(len(data)) if declared is None else declared}

    def geturl(self):
        return self.url


class CannedVoiceProvider:
    """Actual request/bounded response code, with no real HTTP provider calls."""
    def __init__(self, payload, transcript, *, audio=None, language='af'):
        self.payload, self.transcript = payload, transcript
        self.language = language
        self.audio = synthetic_ogg() if audio is None else audio
        self.requests = []
        self.before_open = None

    def open(self, request, timeout):
        if self.before_open:
            self.before_open(request)
        self.requests.append(request)
        assert 0 < timeout <= 10
        url = request.full_url
        if url.endswith("/getFile"):
            voice = self.payload["message"]["voice"]
            assert json.loads(request.data)["file_id"] == voice["file_id"]
            data = json.dumps({"ok": True, "result": {"file_id": voice["file_id"],
                "file_unique_id": voice["file_unique_id"], "file_path": "voice/synthetic.oga",
                "file_size": len(self.audio)}}).encode()
            return Response(data, url)
        if "/file/bot" in url:
            return Response(self.audio, url, mime="audio/ogg")
        assert url == "https://api.openai.com/v1/audio/transcriptions", url
        assert ('name="language"\r\n\r\n' + self.language + '\r\n').encode() in request.data
        assert b'filename="telegram-voice.ogg"' in request.data
        assert b"Content-Type: audio/ogg" in request.data
        return Response(json.dumps({"text": self.transcript}).encode(), url)


def post(client, transport, payload, *, secret=SECRET, bad_auth=False):
    path = "/api/oom-sakkie/channels/telegram/" + ("message" if transport == "gateway" else "direct-webhook")
    header = {"Authorization": "Bearer " + secret} if transport == "gateway" else {
        "X-Telegram-Bot-Api-Secret-Token": secret}
    if bad_auth:
        header = {key: "wrong" for key in header}
    return client.post(path, json=payload, headers=header)
