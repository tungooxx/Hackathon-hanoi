"""Build/refresh index embedding cho policy-files/. Cần EMBED_MODEL + network.

    python scripts/build_policy_index.py

MOCK_LLM=1 hoặc chưa set EMBED_MODEL -> luồng RAG dùng lexical, không cần index này.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import rag  # noqa: E402
from app.config import EMBED_MODEL, POLICY_INDEX  # noqa: E402


async def main() -> None:
    if not EMBED_MODEL:
        print("EMBED_MODEL rỗng -> luồng RAG chạy lexical (offline), không cần build index.")
        return
    idx = await rag.build_index(force=True)
    print(f"Đã build {len(idx['chunks'])} chunk (model={idx['model']}) -> {POLICY_INDEX}")


if __name__ == "__main__":
    asyncio.run(main())
