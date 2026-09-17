import hashlib
import json
import unittest

from modules.oom_sakkie.specialist_owner_decisions import (
    BEACON_CAPTION_SHA256,
    BEACON_CAPTION_UTF8_HEX,
    BEACON_PROPOSAL_ID,
    REJECTED_MUTATED_PROPOSAL_ID,
    beacon_organic_publication_binding,
    render_beacon_card,
    specialist_choice,
    specialist_decision_current,
    validate_specialist_binding,
)


EXPIRY = "2026-08-01T10:00:00+02:00"
NOW = "2026-08-01T07:00:00+02:00"
PREVIEW = "https://example.test/api/private-preview?expires=1&token=opaque"


class SpecialistOwnerDecisionTests(unittest.TestCase):
    def binding(self):
        return beacon_organic_publication_binding(preview_reference=PREVIEW, expires_at=EXPIRY)

    def test_authoritative_utf8_bytes_and_terminal_emoji_survive_json_and_telegram(self):
        binding = self.binding()
        raw = bytes.fromhex(binding["evidence_binding"]["caption_utf8_hex"])
        self.assertEqual(raw.hex(), BEACON_CAPTION_UTF8_HEX)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), BEACON_CAPTION_SHA256)
        self.assertTrue(raw.endswith(b". \xf0\x9f\x90\xb7"))
        restored = json.loads(json.dumps(binding, ensure_ascii=False))
        text, markup = render_beacon_card(restored)
        self.assertIn(raw.decode("utf-8"), text)
        self.assertIn("🐷", text)
        self.assertEqual([row[0]["text"] for row in markup["inline_keyboard"]],
                         ["Approve exact publication", "Request correction", "Decline"])

    def test_deterministic_identity_is_stable_and_mutated_identity_rejected(self):
        first, second = self.binding(), self.binding()
        self.assertEqual(first["deterministic_identity"], BEACON_PROPOSAL_ID)
        self.assertEqual(first["binding_digest"], second["binding_digest"])
        forged = dict(first, deterministic_identity=REJECTED_MUTATED_PROPOSAL_ID)
        with self.assertRaisesRegex(ValueError, "mutated proposal"):
            validate_specialist_binding(forged)

    def test_altered_caption_byte_is_rejected(self):
        forged = self.binding()
        evidence = dict(forged["evidence_binding"])
        evidence["caption_utf8_hex"] = evidence["caption_utf8_hex"][:-2] + "00"
        forged["evidence_binding"] = evidence
        with self.assertRaisesRegex(ValueError, "evidence binding changed"):
            validate_specialist_binding(forged)

    def test_every_beacon_choice_semantic_is_closed(self):
        for field, value in (("label", "Publish now"), ("outcome_code", "published"),
                             ("specialist_callback", "publish_now"), ("next_action_owner", "PUBLIC_BOT")):
            forged = self.binding()
            choices = [dict(row) for row in forged["allowed_owner_choices"]]
            choices[0][field] = value
            forged["allowed_owner_choices"] = choices
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "choices changed"):
                validate_specialist_binding(forged)

    def test_unsupported_specialist_type_fails_closed(self):
        forged = self.binding()
        forged["specialist_identity"] = "BEACON_PUBLIC_BOT"
        with self.assertRaisesRegex(ValueError, "unsupported specialist"):
            validate_specialist_binding(forged)

    def test_stale_chronology_and_expiry_fail_closed(self):
        binding = self.binding()
        self.assertTrue(specialist_decision_current(binding, binding["chronology_binding"], now=NOW))
        changed = dict(binding["chronology_binding"], publication_authorization_count=1)
        self.assertFalse(specialist_decision_current(binding, changed, now=NOW))
        self.assertFalse(specialist_decision_current(binding, binding["chronology_binding"], now=EXPIRY))

    def test_beacon_callback_authority_never_publishes(self):
        binding = self.binding()
        approved = specialist_choice(binding, "approve")
        self.assertEqual(approved["next_action_owner"], "BEACON")
        self.assertEqual(approved["specialist_callback"], "prepare_exact_publication_handover")
        self.assertIn("bounded_publication_handover", approved)
        for key in ("publish", "meta_call", "customer_contact", "advertise", "boost", "spend"):
            self.assertFalse(approved[key])
        for choice in ("correct", "decline"):
            result = specialist_choice(binding, choice)
            self.assertNotIn("bounded_publication_handover", result)
            self.assertFalse(result["publish"])

    def test_callbacks_fit_telegram_and_do_not_expose_full_identity(self):
        binding = self.binding()
        _, markup = render_beacon_card(binding)
        for row in markup["inline_keyboard"]:
            callback = row[0]["callback_data"]
            self.assertLessEqual(len(callback.encode()), 64)
            self.assertNotIn(BEACON_PROPOSAL_ID, callback)


if __name__ == "__main__":
    unittest.main()
