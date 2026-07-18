import io
import unittest
from unittest.mock import patch

from app import app


POLICY = {
    "enabled": True,
    "secret": "s" * 32,
    "owner_user_id": "10",
    "owner_chat_id": "10",
    "transcription_enabled": True,
    "transcription_model": "test",
    "tts_enabled": True,
    "tts_provider": "elevenlabs",
    "tts_model": "test",
    "tts_voice_id": "voice",
}


class CharlieLiveRouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("modules.charlie.routes.require_owner_admin_access", return_value=None)
    @patch("modules.charlie.routes.private_policy", return_value=POLICY)
    @patch("modules.charlie.routes.handle_private_telegram_webhook")
    def test_stream_route_is_unbuffered_and_emits_terminal_event(self, handle, _policy, _auth):
        handle.side_effect = lambda *_args, **kwargs: (kwargs["event_sink"]("intent_understood", {"intent_type": "read_core_status"}) or ({"status": "private_charlie_replied", "reply": "CORE is active.", "executive_packet": {"spoken_summary": "CORE is active."}}, 200))
        response = self.client.post("/api/charlie/private/message/stream", json={"text": "status"}, buffered=True)
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")
        self.assertIn("event: turn_started", body)
        self.assertIn("event: intent_understood", body)
        self.assertIn("event: reply_ready", body)
        self.assertIn("event: turn_completed", body)

    @patch("modules.charlie.routes.require_owner_admin_access", return_value=None)
    @patch("modules.charlie.routes.private_policy", return_value=POLICY)
    @patch("modules.charlie.routes.transcribe_web_audio", return_value=({"success": True, "status": "voice_transcribed", "text": "Hello CHARLIE"}, 200))
    def test_transcription_route_accepts_owner_audio(self, transcribe, _policy, _auth):
        response = self.client.post("/api/charlie/private/voice/transcribe", data={"audio": (io.BytesIO(b"voice"), "voice.webm")}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["text"], "Hello CHARLIE")
        self.assertEqual(transcribe.call_args.args[0], b"voice")

    @patch("modules.charlie.routes.require_owner_admin_access", return_value=None)
    @patch("modules.charlie.routes.private_policy", return_value=POLICY)
    @patch("modules.charlie.routes.synthesize_private_speech", return_value=({"success": True, "status": "private_tts_ready", "audio": b"MP3", "content_type": "audio/mpeg"}, 200))
    def test_speech_route_returns_no_store_audio(self, _speech, _policy, _auth):
        response = self.client.post("/api/charlie/private/voice/speech", json={"text": "Hello"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"MP3")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    @patch("modules.charlie.routes.require_owner_admin_access")
    def test_live_routes_keep_owner_gate(self, auth):
        auth.return_value = ({"success": False, "status": "owner_admin_access_denied"}, 403)
        self.assertEqual(self.client.post("/api/charlie/private/message/stream", json={"text": "status"}).status_code, 403)
        self.assertEqual(self.client.post("/api/charlie/private/voice/speech", json={"text": "status"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
