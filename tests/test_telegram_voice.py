"""Local boundary tests with synthetic Ogg silence and fake provider responses."""
import copy
import io
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import Mock, patch
import urllib.request

from modules.oom_sakkie import telegram_voice as voice
from modules.oom_sakkie.telegram_gateway import parse_telegram_gateway_payload
from modules.oom_sakkie.telegram_voice_audio import validate_ogg_opus_duration
from modules.oom_sakkie.voice_stt import transcribe_oom_sakkie_voice_audio
from tests.telegram_voice_test_support import (
    CannedVoiceProvider, Response, environment, ogg_page, synthetic_ogg, voice_payload,
)


class VoiceAudioBoundaryTests(unittest.TestCase):
    def test_complete_silence_fixture_has_encoded_duration_without_recognition_claim(self):
        audio = (Path(__file__).parent / 'fixtures/telegram_voice/synthetic_silence_1s.ogg').read_bytes()
        self.assertEqual(audio, synthetic_ogg())
        result = validate_ogg_opus_duration(audio)
        self.assertEqual(result["duration_seconds"], 1)
        self.assertEqual(result["encoded_samples"], 48000)
        self.assertFalse(result["audio_decoded"])

    def test_checksum_truncation_and_chained_streams_are_rejected(self):
        audio = synthetic_ogg()
        corrupt = bytearray(audio); corrupt[-1] ^= 1
        for invalid in (audio[:-1], audio[:20], bytes(corrupt), audio + audio):
            with self.subTest(size=len(invalid)), self.assertRaises(ValueError):
                validate_ogg_opus_duration(invalid)

    def test_encoded_duration_cap_cannot_be_bypassed_by_metadata(self):
        with self.assertRaisesRegex(ValueError, "duration_exceeded"):
            validate_ogg_opus_duration(synthetic_ogg(61))

    def test_broken_sequence_and_opus_frame_count_are_rejected(self):
        audio = synthetic_ogg()
        header_end = 47
        prefix = audio[:header_end] + ogg_page(1, [b"OpusTags" + b"\0" * 8])
        for page in (ogg_page(4, [b"\xf8\xff\xfe"], granule=960, flags=4),
                     ogg_page(2, [b"\xfb\x00"], granule=960, flags=4),
                     ogg_page(2, [b"\xfb\x3f"], granule=960, flags=4)):
            with self.subTest(page=page[:27]), self.assertRaises(ValueError):
                validate_ogg_opus_duration(prefix + page)


class VoiceTransportBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.source = environment()
        self.payload = voice_payload()
        self.parsed = parse_telegram_gateway_payload(self.payload)
        self.principal = voice._authorize_native(self.payload, self.parsed, self.source)

    def test_real_multipart_uses_configured_af_and_retains_canned_transcript_as_reported_input(self):
        provider = CannedVoiceProvider(self.payload, "Vark SYNTHETIC-126 is gister dood.")
        with patch.object(voice.urllib.request, "build_opener", return_value=provider):
            result = voice._bounded_transcription(self.payload, self.principal, self.source)
        self.assertEqual(len(provider.requests), 3)
        self.assertEqual(result["text"], provider.transcript)
        self.assertEqual(result["provenance"]["language"], "af")
        self.assertTrue(result["provenance"]["reported_input_only"])
        self.assertFalse(result["provenance"]["stores_audio"])
        self.assertFalse(result["provenance"]["audio_decoded"])

    def test_declared_duration_and_downloaded_content_must_agree(self):
        self.payload["message"]["voice"]["duration"] = 5
        provider = CannedVoiceProvider(self.payload, "CANNED")
        with patch.object(voice.urllib.request, "build_opener", return_value=provider):
            with self.assertRaisesRegex(voice.VoiceFailure, "duration_mismatch"):
                voice._bounded_transcription(self.payload, self.principal, self.source)
        self.assertEqual(len(provider.requests), 2)

    def test_invalid_relative_file_paths_never_download_or_transcribe(self):
        for path in ("../private", "/absolute", "https://elsewhere/audio", "voice//file.ogg",
                     "voice/%2e%2e/file", "voice/file.ogg?token=x", "voice\\file.ogg"):
            data = json.dumps({"ok": True, "result": {"file_path": path}}).encode()
            provider = Mock()
            provider.open.side_effect = lambda req, timeout: Response(data, req.full_url)
            with self.subTest(path=path), patch.object(voice.urllib.request, "build_opener", return_value=provider):
                with self.assertRaisesRegex(voice.VoiceFailure, "file_path_invalid"):
                    voice._bounded_transcription(self.payload, self.principal, self.source)
            self.assertEqual(provider.open.call_count, 1)

    def test_redirect_handler_refuses_every_redirect_before_requesting_target(self):
        request = urllib.request.Request("https://api.telegram.org/file/botSYNTHETIC/voice/a.ogg")
        with self.assertRaisesRegex(voice.VoiceFailure, "redirect_denied"):
            voice._NoRedirect().redirect_request(request, None, 302, "Found", {}, "https://other.example/a")

    def test_bounded_reader_rejects_oversize_truncation_and_changed_url(self):
        request = urllib.request.Request("https://api.telegram.org/synthetic")
        cases = [Response(b"12345", request.full_url),
                 Response(b"1", request.full_url, declared="3"),
                 Response(b"1", "https://other.example/synthetic")]
        for response in cases:
            with self.subTest(headers=response.headers), patch.object(voice.urllib.request, "build_opener") as opener:
                opener.return_value.open.return_value = response
                with self.assertRaises(voice.VoiceFailure):
                    voice._open_bounded(request, deadline=time.monotonic() + 2, max_bytes=3)

    def test_streamed_body_cannot_evade_size_cap_without_content_length(self):
        request = urllib.request.Request("https://api.telegram.org/synthetic")
        response = Response(b"12345", request.full_url)
        del response.headers["Content-Length"]
        with patch.object(voice.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(voice.VoiceFailure, "body_too_large"):
                voice._open_bounded(request, deadline=time.monotonic() + 2, max_bytes=3)

    def test_hard_deadline_returns_without_allowing_worker_to_dispatch(self):
        release, finished = threading.Event(), threading.Event()
        def delayed(*args):
            release.wait(2)
            finished.set()
            return {"text": "CANNED LATE INPUT"}
        with patch.object(voice, "_download_and_transcribe", side_effect=delayed), \
                patch.object(voice, "_retain_input") as retain:
            started = time.monotonic()
            try:
                with self.assertRaisesRegex(voice.VoiceFailure, "network_deadline"):
                    voice._bounded_transcription(self.payload, self.principal, self.source, timeout=0.02)
                self.assertLess(time.monotonic() - started, 0.5)
            finally:
                release.set()
                self.assertTrue(finished.wait(1))
            retain.assert_not_called()

    def test_disabled_or_invalid_stt_metadata_has_no_provider_call(self):
        upload = io.BytesIO(b"SYNTHETIC"); upload.mimetype = "audio/ogg"
        with patch("urllib.request.urlopen") as provider:
            for source, language in (({}, "af"), (self.source, "unconfigured-language")):
                result, code = transcribe_oom_sakkie_voice_audio(upload, environ=source, language=language)
                self.assertGreaterEqual(code, 400)
            provider.assert_not_called()

    def test_empty_or_oversized_stt_response_is_not_reported_input(self):
        for body in (json.dumps({"text": ""}).encode(), b"x" * (65536 + 1)):
            upload = io.BytesIO(b"SYNTHETIC"); upload.mimetype = "audio/ogg"
            result, code = transcribe_oom_sakkie_voice_audio(upload, environ=self.source,
                language="af", filename="voice.ogg", http_open=lambda *a, **k: io.BytesIO(body))
            self.assertGreaterEqual(code, 400)
            self.assertFalse(result["success"])

    def test_native_user_chat_and_provider_identity_cannot_be_overridden(self):
        for key, value in (("telegram_user_id", "9910003"), ("telegram_chat_id", "9910001"),
                           ("provider_message_id", "99999"), ("provider_timestamp", "2026-01-01T00:00:00+00:00")):
            parsed = {**self.parsed, key: value}
            with self.subTest(key=key), self.assertRaises(voice.VoiceFailure):
                voice._authorize_native(self.payload, parsed, self.source)

    def test_supplied_text_forwarded_and_unsupported_audio_are_explicitly_rejected(self):
        for key, value in (("text", "SUPPLIED TEXT"), ("caption", "SUPPLIED TEXT"),
                           ("forward_origin", {"type": "user"}), ("audio", {}),
                           ("forward_sender_name", "SYNTHETIC forwarded source"), ("sender_chat", {"id": -10042})):
            payload = copy.deepcopy(self.payload)
            payload["message"][key] = value
            with self.subTest(key=key), self.assertRaises(voice.VoiceFailure):
                voice._binding(payload, self.parsed, self.principal)


if __name__ == "__main__":
    unittest.main()
