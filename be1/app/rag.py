"""RAG cho câu hỏi chính sách.

chunk policy-files/*.md -> embed (OpenAI-compatible, cùng base_url với LLM) ->
lưu/tìm trong Qdrant (vector DB). MOCK_LLM=1 hoặc chưa cấu hình EMBED_MODEL ->
fallback tìm kiếm lexical (token overlap) để luồng vẫn chạy offline, không cần
key lẫn Qdrant.

Index build lazily ở lần hỏi chính sách đầu tiên; marker hash (file + model) ở
logs/policy_qdrant.hash cho biết khi nào cần build lại (đổi file hoặc đổi model).
"""
import hashlib
import re
from dataclasses import dataclass

import httpx

from db.qdrant import qdrant

from .config import (
    EMBED_API_KEY,
    EMBED_BASE_URL,
    EMBED_MODEL,
    MOCK_LLM,
    POLICY_DIR,
    POLICY_HASH_FILE,
    QDRANT_COLLECTION,
    RAG_TOP_K,
)

# tên hiển thị cho citation (fallback: tên file)
_TITLES = {
    "chinh_sach_bao_hanh_doi_tra": "Chính sách bảo hành & đổi trả",
    "chinh_sach_giao_hang_lap_dat": "Chính sách giao hàng & lắp đặt",
    "chinh_sach_khui_hop_apple": "Chính sách khui hộp sản phẩm Apple",
    "chinh_sach_xu_ly_du_lieu_ca_nhan": "Chính sách xử lý dữ liệu cá nhân",
    "dieu-khoang-su-dung": "Điều khoản sử dụng",
    "noi_quy_cua_hang": "Nội quy cửa hàng",
}


def _title(stem: str) -> str:
    return _TITLES.get(stem, stem.replace("_", " ").replace("-", " "))


@dataclass
class Hit:
    text: str       # đã kèm header "[title]" để LLM có ngữ cảnh nguồn
    source: str     # stem của file
    title: str
    score: float


# ---------------- chunking ----------------

CHUNK_CHARS = 800   # gộp các đoạn liền nhau tới ~800 ký tự thì cắt
OVERLAP_PARAS = 1   # mang theo 1 đoạn cuối sang chunk sau (giữ mạch điều kiện)


def _chunk_text(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for p in paras:
        if cur and cur_len + len(p) > CHUNK_CHARS:
            chunks.append("\n\n".join(cur))
            cur = cur[-OVERLAP_PARAS:] if OVERLAP_PARAS else []
            cur_len = sum(len(x) for x in cur)
        cur.append(p)
        cur_len += len(p)
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def _load_chunks() -> list[dict]:
    out: list[dict] = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        title = _title(path.stem)
        for i, ch in enumerate(_chunk_text(path.read_text(encoding="utf-8"))):
            out.append({
                "id": f"{path.stem}#{i}",
                "source": path.stem,
                "title": title,
                "text": f"[{title}]\n{ch}",
            })
    return out


# ---------------- embeddings (OpenAI-compatible qua httpx) ----------------

async def _embed(texts: list[str]) -> list[list[float]]:
    url = EMBED_BASE_URL.rstrip("/") + "/embeddings"
    headers = {"Authorization": f"Bearer {EMBED_API_KEY}"} if EMBED_API_KEY else {}
    out: list[list[float]] = []
    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(0, len(texts), 64):  # batch tránh giới hạn payload
            body = {"model": EMBED_MODEL, "input": texts[i:i + 64]}
            for attempt in range(3):  # kết nối lạnh tới FPT hay timeout lần đầu -> retry
                try:
                    resp = await client.post(url, headers=headers, json=body)
                    resp.raise_for_status()
                    break
                except (httpx.TransportError, httpx.HTTPStatusError):
                    if attempt == 2:
                        raise
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
    return out


def _content_hash(chunks: list[dict]) -> str:
    h = hashlib.sha256()
    h.update(EMBED_MODEL.encode())
    h.update(QDRANT_COLLECTION.encode())
    for c in chunks:
        h.update(c["id"].encode())
        h.update(c["text"].encode("utf-8"))
    return h.hexdigest()[:16]


# ---------------- index vào Qdrant ----------------

_ready = False


async def build_index(force: bool = False) -> int:
    """Build (hoặc dùng lại) collection Qdrant. Cần EMBED_MODEL + Qdrant chạy.

    Trả về số chunk trong collection. Idempotent: hash + count khớp thì bỏ qua embed.
    """
    global _ready
    chunks = _load_chunks()
    want = _content_hash(chunks)
    if not force and _ready:
        return len(chunks)
    have = POLICY_HASH_FILE.read_text().strip() if POLICY_HASH_FILE.exists() else ""
    if not force and have == want and await qdrant.count() == len(chunks):
        _ready = True
        return len(chunks)

    embs = await _embed([c["text"] for c in chunks])
    await qdrant.recreate_collection(vector_size=len(embs[0]))
    await qdrant.upsert([
        {"id": i, "vector": e,
         "payload": {"source": c["source"], "title": c["title"], "text": c["text"]}}
        for i, (c, e) in enumerate(zip(chunks, embs))
    ])
    POLICY_HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    POLICY_HASH_FILE.write_text(want)
    _ready = True
    return len(chunks)


# ---------------- lexical fallback (offline) ----------------

_WORD = re.compile(r"\w+", re.UNICODE)
_LEX_CHUNKS: list[dict] | None = None


def _toks(s: str) -> list[str]:
    return [t for t in _WORD.findall(s.lower()) if len(t) > 1]


def _lexical_search(query: str, k: int) -> list[Hit]:
    global _LEX_CHUNKS
    if _LEX_CHUNKS is None:
        _LEX_CHUNKS = _load_chunks()
    qset = set(_toks(query))
    if not qset:
        return []
    hits: list[Hit] = []
    for c in _LEX_CHUNKS:
        cset = set(_toks(c["text"]))
        overlap = len(qset & cset)
        if not overlap:
            continue
        score = overlap / len(qset)  # tỉ lệ từ khoá trong câu hỏi khớp chunk
        hits.append(Hit(c["text"], c["source"], c["title"], round(score, 4)))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k]


# ---------------- API ----------------

async def search(query: str, k: int = RAG_TOP_K) -> list[Hit]:
    if MOCK_LLM or not (EMBED_MODEL and EMBED_API_KEY):
        return _lexical_search(query, k)
    await build_index()
    qvec = (await _embed([query]))[0]
    results = await qdrant.search(qvec, limit=k)
    hits: list[Hit] = []
    for r in results:
        p = r.get("payload") or {}
        hits.append(Hit(
            p.get("text", ""), p.get("source", ""), p.get("title", ""),
            round(float(r.get("score", 0.0)), 4),
        ))
    return hits
