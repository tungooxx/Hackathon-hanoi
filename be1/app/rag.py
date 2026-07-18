"""RAG cho câu hỏi chính sách.

chunk policy-files/*.md -> embed (FPT, OpenAI-compatible cùng base_url với LLM) ->
tìm top-k theo cosine. MOCK_LLM=1 hoặc chưa cấu hình EMBED_MODEL -> fallback tìm kiếm
lexical (token overlap) để luồng vẫn chạy offline không cần key.

Index cache ở logs/policy_index.json, gắn hash của (nội dung file + tên model) —
đổi file chính sách hoặc đổi model là tự build lại.
"""
import hashlib
import json
import math
import re
from dataclasses import dataclass

from .config import (
    EMBED_API_KEY,
    EMBED_BASE_URL,
    EMBED_MODEL,
    MOCK_LLM,
    POLICY_DIR,
    POLICY_INDEX,
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


# ---------------- embeddings (OpenAI-compatible) ----------------

async def _embed(texts: list[str]) -> list[list[float]]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=EMBED_BASE_URL, api_key=EMBED_API_KEY, timeout=60)
    out: list[list[float]] = []
    for i in range(0, len(texts), 64):  # batch để tránh giới hạn payload
        resp = await client.embeddings.create(model=EMBED_MODEL, input=texts[i:i + 64])
        out.extend(d.embedding for d in resp.data)
    return out


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _files_hash(chunks: list[dict]) -> str:
    h = hashlib.sha256()
    h.update(EMBED_MODEL.encode())
    for c in chunks:
        h.update(c["id"].encode())
        h.update(c["text"].encode("utf-8"))
    return h.hexdigest()[:16]


_INDEX: dict | None = None


async def build_index(force: bool = False) -> dict:
    """Build (hoặc load cache) index embedding. Cần EMBED_MODEL + network."""
    global _INDEX
    if _INDEX is not None and not force:
        return _INDEX
    chunks = _load_chunks()
    want = _files_hash(chunks)
    if not force and POLICY_INDEX.exists():
        cached = json.loads(POLICY_INDEX.read_text(encoding="utf-8"))
        if cached.get("hash") == want:
            _INDEX = cached
            return _INDEX
    embs = await _embed([c["text"] for c in chunks])
    for c, e in zip(chunks, embs):
        c["embedding"] = e
    _INDEX = {"hash": want, "model": EMBED_MODEL, "chunks": chunks}
    POLICY_INDEX.parent.mkdir(parents=True, exist_ok=True)
    POLICY_INDEX.write_text(json.dumps(_INDEX, ensure_ascii=False), encoding="utf-8")
    return _INDEX


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
    idx = await build_index()
    qvec = (await _embed([query]))[0]
    scored = sorted(
        ((_cos(qvec, c["embedding"]), c) for c in idx["chunks"]),
        key=lambda t: t[0],
        reverse=True,
    )[:k]
    return [Hit(c["text"], c["source"], c["title"], round(s, 4)) for s, c in scored]
