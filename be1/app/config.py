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

# ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://127.0.0.1:9200")
ELASTICSEARCH_URL = "https://disprove-empower-stony.ngrok-free.dev"
ELASTICSEARCH_INDEX = os.getenv("ELASTICSEARCH_PRODUCTS_INDEX", "products")
ELASTICSEARCH_USERNAME = os.getenv("ELASTICSEARCH_USERNAME", "")
ELASTICSEARCH_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD", "")
ELASTICSEARCH_TIMEOUT_SECONDS = float(
    os.getenv("ELASTICSEARCH_TIMEOUT_SECONDS", "10")
)

MAX_ASK_TURNS = int(os.getenv("MAX_ASK_TURNS", "3"))
COMPARE_THRESHOLD = int(os.getenv("COMPARE_THRESHOLD", "3"))

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
JUDGE_BASE_URL = os.getenv("JUDGE_BASE_URL", "") or LLM_BASE_URL
JUDGE_API_KEY = os.getenv("JUDGE_API_KEY", "") or LLM_API_KEY
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "") or LLM_MODEL_LARGE

# có đủ 2 key Langfuse -> tự bật tracing (không có -> no-op, không cần cài đặt gì thêm)
LANGFUSE_ENABLED = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))
