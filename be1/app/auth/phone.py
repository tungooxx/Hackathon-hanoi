"""Vietnamese phone-number validation and canonical E.164 formatting."""

from __future__ import annotations

import re

import phonenumbers

from app.config import PHONE_ALLOWED_COUNTRY_CODES, PHONE_DEFAULT_REGION

from .exceptions import InvalidPhoneNumber

_PHONE_INPUT_PATTERN = re.compile(r"^[0-9+().\s-]+$")


def normalize_phone(raw_phone: str) -> str:
    """Return a valid allowed-country phone number in E.164 format."""

    if not isinstance(raw_phone, str):
        raise InvalidPhoneNumber("Phone number must be text")

    candidate = raw_phone.strip()
    if (
        not candidate
        or len(candidate) > 32
        or not _PHONE_INPUT_PATTERN.fullmatch(candidate)
    ):
        raise InvalidPhoneNumber("Phone number format is invalid")

    try:
        parsed = phonenumbers.parse(candidate, PHONE_DEFAULT_REGION)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumber("Phone number cannot be parsed") from exc

    if (
        parsed.extension
        or parsed.country_code not in PHONE_ALLOWED_COUNTRY_CODES
        or not phonenumbers.is_possible_number(parsed)
        or not phonenumbers.is_valid_number(parsed)
    ):
        raise InvalidPhoneNumber("Phone number is not valid or supported")

    normalized = phonenumbers.format_number(
        parsed,
        phonenumbers.PhoneNumberFormat.E164,
    )
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", normalized):
        raise InvalidPhoneNumber("Phone number cannot be normalized")
    return normalized


def mask_phone(phone_e164: str) -> str:
    """Mask a canonical phone number while retaining useful context."""

    if len(phone_e164) <= 7:
        return "*" * len(phone_e164)
    prefix_length = min(3, len(phone_e164) - 4)
    return (
        phone_e164[:prefix_length]
        + "*" * (len(phone_e164) - prefix_length - 4)
        + phone_e164[-4:]
    )
