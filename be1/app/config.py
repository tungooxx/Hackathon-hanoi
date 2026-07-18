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

MAX_ASK_TURNS = int(os.getenv("MAX_ASK_TURNS", "3"))
COMPARE_THRESHOLD = int(os.getenv("COMPARE_THRESHOLD", "3"))

TURN_LOG = ROOT / "logs" / "turns.jsonl"
