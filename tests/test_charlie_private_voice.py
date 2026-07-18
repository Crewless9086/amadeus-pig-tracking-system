import unittest

from modules.charlie.private_voice import synthesize_private_speech, transcribe_web_audio


class FakeResponse:
    def __init__(self, *, payload=None, content=b""): self.payload, self.content = payload or {}, content
    def raise_for_status(self): return None
    def json(self): return self.payload


class FakeClient:
    def __init__(self): self.calls = []
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(payload={"text": "Wat doen CORE nou?"}) if "transcriptions" in url else FakeResponse(content=b"MP3")


class CharliePrivateVoiceTests(unittest.TestCase):
    def test_transcription_is_disabled_without_policy(self):
        result, status = transcribe_web_audio(b"voice", "voice.webm", "audio/webm", {})
        self.assertEqual((status, result["status"]), (503, "voice_transcription_disabled"))

    def test_transcription_uses_configured_model_without_exposing_key(self):
        result, status = transcribe_web_audio(b"voice", "voice.webm", "audio/webm", {"transcription_enabled": True, "transcription_model": "whisper-test"}, environ={"OPENAI_API_KEY": "top-secret"}, http_client=FakeClient())
        self.assertEqual((status, result["text"]), (200, "Wat doen CORE nou?"))
        self.assertNotIn("top-secret", str(result))

    def test_tts_is_provider_gated_and_returns_audio(self):
        policy = {"tts_enabled": True, "tts_provider": "elevenlabs", "tts_voice_id": "VOICE", "tts_model": "MODEL"}
        result, status = synthesize_private_speech("CORE is active.", policy, environ={"ELEVENLABS_API_KEY": "top-secret"}, http_client=FakeClient())
        self.assertEqual((status, result["audio"]), (200, b"MP3"))


if __name__ == "__main__":
    unittest.main()
