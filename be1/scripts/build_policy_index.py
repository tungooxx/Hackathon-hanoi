"""Build/refresh index chính sách vào Qdrant. Cần EMBED_MODEL + Qdrant đang chạy.

    python scripts/build_policy_index.py

MOCK_LLM=1 hoặc chưa set EMBED_MODEL -> luồng RAG dùng lexical, không cần index này.
Bật Qdrant: cd docker && docker compose up -d qdrant
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import rag  # noqa: E402
from app.config import EMBED_MODEL, QDRANT_COLLECTION, QDRANT_URL  # noqa: E402
from db.qdrant import qdrant  # noqa: E402


async def main() -> None:
    if not EMBED_MODEL:
        print("EMBED_MODEL rỗng -> luồng RAG chạy lexical (offline), không cần build index.")
        return
    if not await qdrant.ping():
        print(f"Không kết nối được Qdrant tại {QDRANT_URL}. Chạy: cd docker && docker compose up -d qdrant")
        sys.exit(1)
    n = await rag.build_index(force=True)
    print(f"Đã build {n} chunk vào Qdrant collection '{QDRANT_COLLECTION}' ({QDRANT_URL}).")
    await qdrant.close()


if __name__ == "__main__":
    asyncio.run(main())
