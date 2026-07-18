from __future__ import annotations

import unittest
import uuid
from datetime import timedelta

from app.auth.exceptions import ExpiredToken, InvalidPhoneNumber, InvalidToken
from app.auth.phone import mask_phone, normalize_phone
from app.auth.security import (
    client_ip_digest,
    create_token_pair,
    decode_token,
    hash_password,
    phone_login_digest,
    refresh_token_digest,
    refresh_token_matches,
    utc_now,
    verify_and_update_password,
    verify_password,
)


class PhoneTests(unittest.TestCase):
    def test_normalizes_vietnamese_phone_formats(self) -> None:
        expected = "+84901234567"
        self.assertEqual(normalize_phone("090 123 4567"), expected)
        self.assertEqual(normalize_phone("+84 90 123 4567"), expected)
        self.assertEqual(mask_phone(expected), "+84*****4567")

    def test_rejects_unsupported_or_embedded_phone_text(self) -> None:
        for value in ("Call me at 0901234567", "+14155552671", "12345"):
            with self.subTest(value=value):
                with self.assertRaises(InvalidPhoneNumber):
                    normalize_phone(value)


class SecurityTests(unittest.TestCase):
    def test_passwords_use_salted_argon2_hashes(self) -> None:
        password = "Correct Horse Battery Staple"
        first = hash_password(password)
        second = hash_password(password)

        self.assertTrue(first.startswith("$argon2"))
        self.assertNotEqual(first, second)
        self.assertNotIn(password, first)
        self.assertTrue(verify_password(password, first))
        self.assertFalse(verify_password("incorrect password", first))
        self.assertFalse(verify_password(password, None))
        self.assertEqual(
            verify_and_update_password(password, "not-a-valid-hash"),
            (False, None),
        )

    def test_rate_limit_and_refresh_values_use_stable_hmac_digests(self) -> None:
        self.assertEqual(
            client_ip_digest("2001:db8::1"),
            client_ip_digest("2001:0db8:0:0:0:0:0:1"),
        )
        phone_digest = phone_login_digest("+84901234567")
        self.assertEqual(len(phone_digest), 64)
        self.assertNotIn("901234567", phone_digest)

        token = "refresh-token-value"
        digest = refresh_token_digest(token)
        self.assertEqual(len(digest), 64)
        self.assertTrue(refresh_token_matches(token, digest))
        self.assertFalse(refresh_token_matches("different", digest))

    def test_jwt_pair_has_bound_type_and_session_claims(self) -> None:
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        tokens = create_token_pair(user_id, session_id)

        access = decode_token(tokens.access_token, "access")
        refresh = decode_token(tokens.refresh_token, "refresh")
        self.assertEqual(access.user_id, user_id)
        self.assertEqual(access.session_id, session_id)
        self.assertEqual(refresh.session_id, session_id)
        self.assertNotEqual(access.token_id, refresh.token_id)

        with self.assertRaises(InvalidToken):
            decode_token(tokens.access_token, "refresh")

        header, payload, signature = tokens.access_token.split(".")
        signature = ("a" if signature[0] != "a" else "b") + signature[1:]
        tampered = ".".join((header, payload, signature))
        with self.assertRaises(InvalidToken):
            decode_token(tampered, "access")

    def test_expired_jwt_is_rejected(self) -> None:
        tokens = create_token_pair(
            uuid.uuid4(),
            uuid.uuid4(),
            now=utc_now() - timedelta(days=40),
        )
        with self.assertRaises(ExpiredToken):
            decode_token(tokens.access_token, "access")


if __name__ == "__main__":
    unittest.main()
