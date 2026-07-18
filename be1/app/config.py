import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

MOCK_LLM = os.getenv("MOCK_LLM", "0") == "1"

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
# model nhỏ-nhanh cho NLU, model lớn cho phrasing saler
LLM_MODEL_SMALL = os.getenv("LLM_MODEL_SMALL", "llama-3.3-70b-versatile")
LLM_MODEL_LARGE = os.getenv("LLM_MODEL_LARGE", "llama-3.3-70b-versatile")

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://127.0.0.1:9200")
# ELASTICSEARCH_URL = "https://disprove-empower-stony.ngrok-free.dev"
ELASTICSEARCH_INDEX = os.getenv("ELASTICSEARCH_PRODUCTS_INDEX", "products")
ELASTICSEARCH_USERNAME = os.getenv("ELASTICSEARCH_USERNAME", "")
ELASTICSEARCH_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD", "")
ELASTICSEARCH_TIMEOUT_SECONDS = float(os.getenv("ELASTICSEARCH_TIMEOUT_SECONDS", "10"))

# PostgreSQL stores users, failed-login throttling data, and revocable sessions.
# Override this in every deployed environment; the default only matches local dev.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://be1:be1@127.0.0.1:5432/be1",
)
DATABASE_ECHO = os.getenv("DATABASE_ECHO", "0") == "1"
DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "5"))
DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
DATABASE_POOL_RECYCLE_SECONDS = int(os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "1800"))

# LangGraph uses Psycopg 3 rather than SQLAlchemy's asyncpg driver. Both URLs
# point at the same PostgreSQL database unless explicitly separated.
LANGGRAPH_DATABASE_URL = os.getenv(
    "LANGGRAPH_DATABASE_URL",
    DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1),
)
LANGGRAPH_POOL_MIN_SIZE = int(os.getenv("LANGGRAPH_POOL_MIN_SIZE", "1"))
LANGGRAPH_POOL_MAX_SIZE = int(os.getenv("LANGGRAPH_POOL_MAX_SIZE", "5"))

# Phone/password + JWT authentication. Development defaults keep local setup
# simple; validate_auth_config() rejects unsafe secrets in production.
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
PHONE_DEFAULT_REGION = os.getenv("PHONE_DEFAULT_REGION", "VN").strip().upper()
PHONE_ALLOWED_COUNTRY_CODES = frozenset(
    int(code.strip())
    for code in os.getenv("PHONE_ALLOWED_COUNTRY_CODES", "84").split(",")
    if code.strip()
)

PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "8"))
PASSWORD_MAX_LENGTH = int(os.getenv("PASSWORD_MAX_LENGTH", "128"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "900")
)
LOGIN_PHONE_RATE_LIMIT_COUNT = int(os.getenv("LOGIN_PHONE_RATE_LIMIT_COUNT", "5"))
LOGIN_IP_RATE_LIMIT_COUNT = int(os.getenv("LOGIN_IP_RATE_LIMIT_COUNT", "20"))
AUTH_RATE_LIMIT_SECRET = os.getenv(
    "AUTH_RATE_LIMIT_SECRET",
    "dev-only-rate-limit-secret-change-before-production",
)

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
JWT_REFRESH_TTL_SECONDS = int(os.getenv("JWT_REFRESH_TTL_SECONDS", "2592000"))
JWT_LEEWAY_SECONDS = int(os.getenv("JWT_LEEWAY_SECONDS", "5"))

FRONTEND_ORIGINS = tuple(
    dict.fromkeys(
        origin.strip().rstrip("/")
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    )
)
AUTH_ACCESS_COOKIE_NAME = os.getenv(
    "AUTH_ACCESS_COOKIE_NAME",
    "dmx_access",
).strip()
AUTH_REFRESH_COOKIE_NAME = os.getenv(
    "AUTH_REFRESH_COOKIE_NAME",
    "dmx_refresh",
).strip()
AUTH_COOKIE_SECURE = (
    os.getenv(
        "AUTH_COOKIE_SECURE",
        "1" if APP_ENV in {"prod", "production"} else "0",
    )
    == "1"
)
AUTH_COOKIE_SAMESITE = (
    os.getenv(
        "AUTH_COOKIE_SAMESITE",
        "lax",
    )
    .strip()
    .lower()
)
AUTH_COOKIE_DOMAIN = os.getenv("AUTH_COOKIE_DOMAIN", "").strip() or None
AUTH_ACCESS_COOKIE_PATH = "/"
AUTH_REFRESH_COOKIE_PATH = "/auth"

MAX_ASK_TURNS = int(os.getenv("MAX_ASK_TURNS", "3"))
COMPARE_THRESHOLD = int(os.getenv("COMPARE_THRESHOLD", "3"))
RUNTIME_PROFILE_COMPILE_TIMEOUT_SECONDS = float(
    os.getenv("RUNTIME_PROFILE_COMPILE_TIMEOUT_SECONDS", "20")
)

# --- Web search / enrichment (sản phẩm lạ không có trong catalog) ---
# MOCK_LLM=1 hoặc thiếu TAVILY_API_KEY -> dùng fixture offline, luồng vẫn chạy.
WEB_SEARCH_PROVIDER = os.getenv("WEB_SEARCH_PROVIDER", "tavily")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_BASE_URL = os.getenv("TAVILY_BASE_URL", "https://api.tavily.com")
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
WEB_SEARCH_TIMEOUT_SECONDS = float(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "20"))
# chặn vòng lặp web vô hạn: số lần search-lại-theo-nhu-cầu tối đa mỗi phiên làm giàu
MAX_ENRICH_ITERS = int(os.getenv("MAX_ENRICH_ITERS", "2"))

# --- RAG chính sách: embedding OpenAI-compatible, mặc định dùng lại LLM_* ---
# EMBED_MODEL rỗng (hoặc MOCK_LLM=1) -> fallback lexical, chạy offline không cần key/Qdrant.
EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "") or LLM_BASE_URL
EMBED_API_KEY = os.getenv("EMBED_API_KEY", "") or LLM_API_KEY
EMBED_MODEL = os.getenv("EMBED_MODEL", "")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.3"))

# Vector DB cho chunk chính sách. Khi BE1 chạy trong Compose, dùng QDRANT_URL=http://qdrant:6333
QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_POLICY_COLLECTION", "policies")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_TIMEOUT_SECONDS = float(os.getenv("QDRANT_TIMEOUT_SECONDS", "10"))

POLICY_DIR = ROOT / "policy-files"
# marker lưu hash (file + model) của lần build gần nhất -> biết khi nào cần build lại Qdrant
POLICY_HASH_FILE = ROOT / "logs" / "policy_qdrant.hash"

TURN_LOG = ROOT / "logs" / "turns.jsonl"
JUDGMENT_LOG = ROOT / "logs" / "judgments.jsonl"

# judge = model NGOÀI hệ thống, mạnh hơn — rỗng thì fallback về LLM_* ở trên
MOCK_JUDGE = os.getenv("MOCK_JUDGE", "0") == "1"
ONTOLOGY_REVIEWER_TOKEN = os.getenv("ONTOLOGY_REVIEWER_TOKEN", "")
JUDGE_BASE_URL = os.getenv("JUDGE_BASE_URL", "") or LLM_BASE_URL
JUDGE_API_KEY = os.getenv("JUDGE_API_KEY", "") or LLM_API_KEY
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "") or LLM_MODEL_LARGE

# có đủ 2 key Langfuse -> tự bật tracing (không có -> no-op, không cần cài đặt gì thêm)
LANGFUSE_ENABLED = bool(
    os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
)


def validate_auth_config() -> None:
    """Fail fast when authentication settings are unsafe or inconsistent."""

    positive_values = {
        "PASSWORD_MIN_LENGTH": PASSWORD_MIN_LENGTH,
        "PASSWORD_MAX_LENGTH": PASSWORD_MAX_LENGTH,
        "LOGIN_RATE_LIMIT_WINDOW_SECONDS": LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        "LOGIN_PHONE_RATE_LIMIT_COUNT": LOGIN_PHONE_RATE_LIMIT_COUNT,
        "LOGIN_IP_RATE_LIMIT_COUNT": LOGIN_IP_RATE_LIMIT_COUNT,
        "JWT_ACCESS_TTL_SECONDS": JWT_ACCESS_TTL_SECONDS,
        "JWT_REFRESH_TTL_SECONDS": JWT_REFRESH_TTL_SECONDS,
        "LANGGRAPH_POOL_MIN_SIZE": LANGGRAPH_POOL_MIN_SIZE,
        "LANGGRAPH_POOL_MAX_SIZE": LANGGRAPH_POOL_MAX_SIZE,
        "RUNTIME_PROFILE_COMPILE_TIMEOUT_SECONDS": RUNTIME_PROFILE_COMPILE_TIMEOUT_SECONDS,
    }
    invalid = [name for name, value in positive_values.items() if value <= 0]
    if invalid:
        raise RuntimeError(
            f"Authentication settings must be positive: {', '.join(invalid)}"
        )
    if PASSWORD_MIN_LENGTH < 8:
        raise RuntimeError("PASSWORD_MIN_LENGTH must be at least 8")
    if PASSWORD_MAX_LENGTH < PASSWORD_MIN_LENGTH:
        raise RuntimeError(
            "PASSWORD_MAX_LENGTH must be greater than or equal to PASSWORD_MIN_LENGTH"
        )
    if JWT_LEEWAY_SECONDS < 0:
        raise RuntimeError("JWT_LEEWAY_SECONDS cannot be negative")
    if not PHONE_ALLOWED_COUNTRY_CODES:
        raise RuntimeError("PHONE_ALLOWED_COUNTRY_CODES cannot be empty")
    if not FRONTEND_ORIGINS:
        raise RuntimeError("FRONTEND_ORIGINS cannot be empty")
    if "*" in FRONTEND_ORIGINS:
        raise RuntimeError(
            "FRONTEND_ORIGINS cannot use a wildcard with credentialed CORS"
        )
    invalid_origins = []
    for origin in FRONTEND_ORIGINS:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            invalid_origins.append(origin)
    if invalid_origins:
        raise RuntimeError(
            "FRONTEND_ORIGINS must contain HTTP(S) origins without paths: "
            + ", ".join(invalid_origins)
        )
    if (
        not AUTH_ACCESS_COOKIE_NAME
        or not AUTH_REFRESH_COOKIE_NAME
        or AUTH_ACCESS_COOKIE_NAME == AUTH_REFRESH_COOKIE_NAME
    ):
        raise RuntimeError(
            "Access and refresh cookie names must be non-empty and distinct"
        )
    if AUTH_COOKIE_SAMESITE not in {"lax", "strict"}:
        raise RuntimeError(
            "AUTH_COOKIE_SAMESITE must be lax or strict; cross-site cookies "
            "require a separate CSRF implementation"
        )
    if JWT_REFRESH_TTL_SECONDS <= JWT_ACCESS_TTL_SECONDS:
        raise RuntimeError(
            "JWT_REFRESH_TTL_SECONDS must be longer than JWT_ACCESS_TTL_SECONDS"
        )
    if LANGGRAPH_POOL_MAX_SIZE < LANGGRAPH_POOL_MIN_SIZE:
        raise RuntimeError(
            "LANGGRAPH_POOL_MAX_SIZE must be greater than or equal to "
            "LANGGRAPH_POOL_MIN_SIZE"
        )

    if APP_ENV in {"prod", "production"}:
        secrets = {
            "JWT_SECRET_KEY": JWT_SECRET_KEY,
            "AUTH_TOKEN_DIGEST_SECRET": AUTH_TOKEN_DIGEST_SECRET,
            "AUTH_RATE_LIMIT_SECRET": AUTH_RATE_LIMIT_SECRET,
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
        if not AUTH_COOKIE_SECURE:
            raise RuntimeError("AUTH_COOKIE_SECURE must be enabled in production")
