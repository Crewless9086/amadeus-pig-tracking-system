import hashlib
import unittest

from modules.beacon.organic_publication_authorization import (
    canonical_caption_text,
    caption_sha256,
)
from modules.beacon.weekly_owner_review import (
    EXACT_CAPTION,
    EXPECTED_CAPTION_SHA256,
)
from modules.sales.beacon_campaign import _facebook_post_params


class OrganicPublicationAuthorizationTests(unittest.TestCase):
    def test_exact_two_paragraph_caption_reproduces_approved_hash(self):
        params = _facebook_post_params(
            {"exact_text": EXACT_CAPTION},
            {},
        )
        self.assertEqual(params["exact_text"], EXACT_CAPTION)
        self.assertEqual(
            hashlib.sha256(params["exact_text"].encode("utf-8")).hexdigest(),
            EXPECTED_CAPTION_SHA256,
        )

    def test_crlf_and_cr_canonicalize_to_lf_only(self):
        crlf = EXACT_CAPTION.replace("\n", "\r\n")
        cr = EXACT_CAPTION.replace("\n", "\r")
        self.assertEqual(canonical_caption_text(crlf), EXACT_CAPTION)
        self.assertEqual(canonical_caption_text(cr), EXACT_CAPTION)
        self.assertEqual(caption_sha256(crlf), EXPECTED_CAPTION_SHA256)

    def test_internal_spaces_punctuation_and_unicode_are_preserved(self):
        caption = "Ms. Piggy’s  care — exactly  this.\n\nSecond × paragraph."
        params = _facebook_post_params({"exact_text": caption}, {})
        self.assertEqual(params["exact_text"], caption)
        self.assertIn("  ", params["exact_text"])
        self.assertIn("’", params["exact_text"])
        self.assertIn("—", params["exact_text"])
        self.assertIn("×", params["exact_text"])

    def test_html_is_not_decoded_or_used_as_caption_source(self):
        caption = "Farm <strong>story</strong>\n\nAwareness & care."
        params = _facebook_post_params(
            {"exact_text": caption, "display_html": "changed"},
            {},
        )
        self.assertEqual(params["exact_text"], caption)
        self.assertNotEqual(params["exact_text"], "changed")

    def test_changed_caption_has_different_hash(self):
        self.assertNotEqual(
            caption_sha256(EXACT_CAPTION + " "),
            EXPECTED_CAPTION_SHA256,
        )

    def test_nul_caption_fails_closed(self):
        with self.assertRaises(ValueError):
            canonical_caption_text("unsafe\x00caption")


if __name__ == "__main__":
    unittest.main()
