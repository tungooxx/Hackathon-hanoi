from __future__ import annotations

import uuid
import unittest
from datetime import timedelta

from app.auth.exceptions import ExpiredToken, InvalidPhoneNumber, InvalidToken
from app.auth.phone import mask_phone, normalize_phone
from app.auth.security import (
    client_ip_digest,
    create_token_pair,
    decode_token,
    generate_otp,
    otp_digest,
    otp_matches,
    refresh_token_digest,
    refresh_token_matches,
    utc_now,
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
    def test_otp_generation_and_context_bound_digest(self) -> None:
        challenge_id = uuid.uuid4()
        phone = "+84901234567"
        code = generate_otp()

        self.assertRegex(code, r"^[0-9]{6}$")
        digest = otp_digest(challenge_id, phone, code)
        self.assertEqual(len(digest), 64)
        self.assertNotIn(code, digest)
        self.assertTrue(otp_matches(challenge_id, phone, code, digest))
        self.assertFalse(otp_matches(challenge_id, phone, "000000", digest))
        self.assertNotEqual(
            digest,
            otp_digest(uuid.uuid4(), phone, code),
        )

    def test_ip_and_refresh_secrets_use_stable_hmac_digests(self) -> None:
        self.assertEqual(
            client_ip_digest("2001:db8::1"),
            client_ip_digest("2001:0db8:0:0:0:0:0:1"),
        )
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

        tampered = tokens.access_token[:-1] + (
            "a" if tokens.access_token[-1] != "a" else "b"
        )
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
