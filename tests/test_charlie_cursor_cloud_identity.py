import base64
import json
import time
import unittest

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from modules.charlie import cursor_cloud_identity as identity


def b64(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class Response:
    def __init__(self, value): self.value = value
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, _limit=-1): return json.dumps(self.value).encode()


class CursorCloudIdentityTests(unittest.TestCase):
    def setUp(self):
        identity._JWKS_CACHE.update({"expires_at": 0, "keys": {}})
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        numbers = self.private.public_key().public_numbers()
        self.jwk = {"kid": "one", "kty": "RSA", "alg": "RS256",
                    "n": b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
                    "e": b64(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big"))}
        self.now = int(time.time())
        self.claims = {"iss": identity.CURSOR_OIDC_ISSUER, "aud": identity.CURSOR_OIDC_AUDIENCE,
            "iat": self.now, "nbf": self.now - 5, "exp": self.now + 300,
            "agent_runtime": "managed", "cloud_agent_id": "bc-one", "turn_id": "turn-one",
            "repo_url": identity.APPROVED_REPOSITORY, "repo_urls": [identity.APPROVED_REPOSITORY],
            "repo_count": 1, "branch_name": "cursor/one", "source": "API"}

    def token(self, claims=None, kid="one"):
        header = b64({"alg": "RS256", "typ": "JWT", "kid": kid})
        payload = b64(self.claims if claims is None else claims)
        signature = self.private.sign(f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{header}.{payload}.{b64(signature)}"

    def opener(self, _request, timeout=0): return Response({"keys": [self.jwk]})

    def test_valid_managed_single_repo_api_agent(self):
        claims = identity.verify_cursor_oidc_token(self.token(), opener=self.opener, now=self.now)
        self.assertEqual("bc-one", claims["cloud_agent_id"])

    def test_repo_urls_is_exact_even_when_repo_count_is_omitted(self):
        claims = {key: value for key, value in self.claims.items() if key != "repo_count"}
        identity.verify_cursor_oidc_token(self.token(claims), opener=self.opener, now=self.now)
        identity._JWKS_CACHE.update({"expires_at": 0, "keys": {}})
        claims["repo_urls"] = [identity.APPROVED_REPOSITORY, "github.com/other/repo"]
        with self.assertRaisesRegex(identity.CursorIdentityError, "repository_set_invalid"):
            identity.verify_cursor_oidc_token(self.token(claims), opener=self.opener, now=self.now)

    def test_wrong_issuer_audience_runtime_repo_branch_and_source_fail_closed(self):
        mutations = {"iss": "bad", "aud": "bad", "agent_runtime": "self-hosted",
                     "repo_url": "github.com/other/repo", "repo_count": 2, "source": "SLACK"}
        for key, value in mutations.items():
            with self.subTest(key=key):
                claims = {**self.claims, key: value}
                identity._JWKS_CACHE.update({"expires_at": 0, "keys": {}})
                with self.assertRaises(identity.CursorIdentityError):
                    identity.verify_cursor_oidc_token(self.token(claims), opener=self.opener, now=self.now)
        identity._JWKS_CACHE.update({"expires_at": 0, "keys": {}})
        with self.assertRaisesRegex(identity.CursorIdentityError, "audience_invalid"):
            identity.verify_cursor_oidc_token(
                self.token({**self.claims, "aud": [identity.CURSOR_OIDC_AUDIENCE, "other"]}),
                opener=self.opener, now=self.now)

    def test_expired_malformed_and_unknown_kid_fail_closed(self):
        with self.assertRaisesRegex(identity.CursorIdentityError, "time_invalid"):
            identity.verify_cursor_oidc_token(self.token({**self.claims, "exp": self.now - 60}), opener=self.opener, now=self.now)
        identity._JWKS_CACHE.update({"expires_at": 0, "keys": {}})
        with self.assertRaisesRegex(identity.CursorIdentityError, "unknown_kid"):
            identity.verify_cursor_oidc_token(self.token(kid="other"), opener=self.opener, now=self.now)
        with self.assertRaisesRegex(identity.CursorIdentityError, "malformed"):
            identity.verify_cursor_oidc_token("not-a-token", opener=self.opener, now=self.now)

    def test_unknown_kid_refreshes_exactly_once(self):
        calls = []
        def opener(_request, timeout=0): calls.append(1); return Response({"keys": [self.jwk]})
        with self.assertRaisesRegex(identity.CursorIdentityError, "unknown_kid"):
            identity.verify_cursor_oidc_token(self.token(kid="other"), opener=opener, now=self.now)
        self.assertEqual(2, len(calls))


if __name__ == "__main__": unittest.main()
