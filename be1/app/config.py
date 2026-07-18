import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

MOCK_LLM = os.getenv("MOCK_LLM", "0") == "1"

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
# model nhỏ-nhanh cho NLU, model lớn cho phrasing saler
LLM_MODEL_SMALL = os.getenv("LLM_MODEL_SMALL", "llama-3.3-70b-versatile")
LLM_MODEL_LARGE = os.getenv("LLM_MODEL_LARGE", "llama-3.3-70b-versatile")

# rỗng -> dùng fixture local thay vì gọi BE2 của Kiên
BE2_BASE_URL = os.getenv("BE2_BASE_URL", "")

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://127.0.0.1:9200")
ELASTICSEARCH_INDEX = os.getenv("ELASTICSEARCH_PRODUCTS_INDEX", "products")
ELASTICSEARCH_USERNAME = os.getenv("ELASTICSEARCH_USERNAME", "")
ELASTICSEARCH_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD", "")
ELASTICSEARCH_TIMEOUT_SECONDS = float(
    os.getenv("ELASTICSEARCH_TIMEOUT_SECONDS", "10")
)

# PostgreSQL stores users, OTP challenges, and revocable auth sessions.
# Override this in every deployed environment; the default only matches local dev.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://be1:be1@127.0.0.1:5432/be1",
)
DATABASE_ECHO = os.getenv("DATABASE_ECHO", "0") == "1"
DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "5"))
DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
DATABASE_POOL_RECYCLE_SECONDS = int(
    os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "1800")
)

# Phone OTP + JWT authentication. Development defaults keep local setup simple;
# validate_auth_config() rejects them when APP_ENV is production.
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
PHONE_DEFAULT_REGION = os.getenv("PHONE_DEFAULT_REGION", "VN").strip().upper()
PHONE_ALLOWED_COUNTRY_CODES = frozenset(
    int(code.strip())
    for code in os.getenv("PHONE_ALLOWED_COUNTRY_CODES", "84").split(",")
    if code.strip()
)

OTP_PROVIDER = os.getenv("OTP_PROVIDER", "console").strip().lower()
OTP_HMAC_SECRET = os.getenv(
    "OTP_HMAC_SECRET",
    "dev-only-otp-hmac-secret-change-before-production",
)
OTP_DIGITS = int(os.getenv("OTP_DIGITS", "6"))
OTP_TTL_SECONDS = int(os.getenv("OTP_TTL_SECONDS", "300"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
OTP_RESEND_COOLDOWN_SECONDS = int(
    os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60")
)
OTP_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("OTP_RATE_LIMIT_WINDOW_SECONDS", "3600")
)
OTP_PHONE_RATE_LIMIT_COUNT = int(
    os.getenv("OTP_PHONE_RATE_LIMIT_COUNT", "5")
)
OTP_IP_RATE_LIMIT_COUNT = int(os.getenv("OTP_IP_RATE_LIMIT_COUNT", "20"))

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "dev-only-jwt-signing-secret-change-before-production",
)
AUTH_TOKEN_DIGEST_SECRET = os.getenv(
    "AUTH_TOKEN_DIGEST_SECRET",
    "dev-only-token-digest-secret-change-before-production",
)
JWT_ALGORITHM = "HS256"
JWT_ISSUER = os.getenv("JWT_ISSUER", "dmx-advisor-be1")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "dmx-advisor-web")
JWT_ACCESS_TTL_SECONDS = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "900"))
JWT_REFRESH_TTL_SECONDS = int(
    os.getenv("JWT_REFRESH_TTL_SECONDS", "2592000")
)
JWT_LEEWAY_SECONDS = int(os.getenv("JWT_LEEWAY_SECONDS", "5"))

MAX_ASK_TURNS = int(os.getenv("MAX_ASK_TURNS", "3"))
COMPARE_THRESHOLD = int(os.getenv("COMPARE_THRESHOLD", "3"))

TURN_LOG = ROOT / "logs" / "turns.jsonl"
JUDGMENT_LOG = ROOT / "logs" / "judgments.jsonl"

# judge = model NGOÀI hệ thống, mạnh hơn — rỗng thì fallback về LLM_* ở trên
MOCK_JUDGE = os.getenv("MOCK_JUDGE", "0") == "1"
JUDGE_BASE_URL = os.getenv("JUDGE_BASE_URL", "") or LLM_BASE_URL
JUDGE_API_KEY = os.getenv("JUDGE_API_KEY", "") or LLM_API_KEY
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "") or LLM_MODEL_LARGE

# có đủ 2 key Langfuse -> tự bật tracing (không có -> no-op, không cần cài đặt gì thêm)
LANGFUSE_ENABLED = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def validate_auth_config() -> None:
    """Fail fast when authentication settings are unsafe or inconsistent."""

    positive_values = {
        "OTP_DIGITS": OTP_DIGITS,
        "OTP_TTL_SECONDS": OTP_TTL_SECONDS,
        "OTP_MAX_ATTEMPTS": OTP_MAX_ATTEMPTS,
        "OTP_RESEND_COOLDOWN_SECONDS": OTP_RESEND_COOLDOWN_SECONDS,
        "OTP_RATE_LIMIT_WINDOW_SECONDS": OTP_RATE_LIMIT_WINDOW_SECONDS,
        "OTP_PHONE_RATE_LIMIT_COUNT": OTP_PHONE_RATE_LIMIT_COUNT,
        "OTP_IP_RATE_LIMIT_COUNT": OTP_IP_RATE_LIMIT_COUNT,
        "JWT_ACCESS_TTL_SECONDS": JWT_ACCESS_TTL_SECONDS,
        "JWT_REFRESH_TTL_SECONDS": JWT_REFRESH_TTL_SECONDS,
    }
    invalid = [name for name, value in positive_values.items() if value <= 0]
    if invalid:
        raise RuntimeError(
            f"Authentication settings must be positive: {', '.join(invalid)}"
        )
    if not 4 <= OTP_DIGITS <= 10:
        raise RuntimeError("OTP_DIGITS must be between 4 and 10")
    if JWT_LEEWAY_SECONDS < 0:
        raise RuntimeError("JWT_LEEWAY_SECONDS cannot be negative")
    if not PHONE_ALLOWED_COUNTRY_CODES:
        raise RuntimeError("PHONE_ALLOWED_COUNTRY_CODES cannot be empty")
    if JWT_REFRESH_TTL_SECONDS <= JWT_ACCESS_TTL_SECONDS:
        raise RuntimeError(
            "JWT_REFRESH_TTL_SECONDS must be longer than JWT_ACCESS_TTL_SECONDS"
        )

    if APP_ENV in {"prod", "production"}:
        secrets = {
            "JWT_SECRET_KEY": JWT_SECRET_KEY,
            "OTP_HMAC_SECRET": OTP_HMAC_SECRET,
            "AUTH_TOKEN_DIGEST_SECRET": AUTH_TOKEN_DIGEST_SECRET,
        }
        unsafe = [
            name
            for name, value in secrets.items()
            if len(value.encode()) < 32 or value.startswith("dev-only-")
        ]
        if unsafe:
            raise RuntimeError(
                "Production authentication secrets must be at least 32 bytes "
                f"and cannot use development defaults: {', '.join(unsafe)}"
            )
        if OTP_PROVIDER == "console":
            raise RuntimeError("OTP_PROVIDER=console is forbidden in production")
