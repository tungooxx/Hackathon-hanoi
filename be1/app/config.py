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
