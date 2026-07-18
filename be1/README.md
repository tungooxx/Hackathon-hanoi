# BE1 — DMX AI Advisor (core xử lý)

Flow: `intent → retrieve → [hỏi ngược | so sánh top 3] | RAG chính sách | off-topic`, tối đa
**2 lượt LLM/turn** (NLU structured + phrasing streaming), filter/ranking hoàn toàn deterministic.

## Chạy

```bash
cd be1
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # MOCK_LLM=1: chạy không cần API key
.venv/bin/uvicorn app.main:app --port 8100
.venv/bin/python scripts/smoke.py   # smoke test 4 turn, phải ALL PASS
```

Cắm LLM thật: sửa `.env` → `MOCK_LLM=0` + `LLM_API_KEY` (OpenAI-compatible: Groq/Fireworks/Together).

## API cho FE

`POST /chat` body `{"session_id": "...", "message": "..."}` → SSE stream, các event:

| event | data | dùng làm |
|---|---|---|
| `funnel_count` | `{count, total, filters}` | explainability panel (số SP còn khớp) |
| `question` | `{slot, reason}` | đánh dấu turn hỏi ngược + lý do hỏi |
| `text_chunk` | `{content}` | text bot, append dần |
| `product_cards` | `{products: [...]}` | render 3 card sản phẩm |
| `policy_sources` | `{sources: [{title, source, score}]}` | citation cho câu trả lời chính sách (RAG) |
| `done` | `{turn_type: ask\|compare\|no_match\|policy\|off_topic}` | kết thúc turn |

State hội thoại persist theo `session_id` (LangGraph checkpointer) — FE chỉ cần giữ 1 session_id.

## Hợp đồng với BE2 (Kiên)

- `GET {BE2_BASE_URL}/products?category=may_lanh` → JSON list, shape xem `fixtures/may_lanh.json`
  (đã normalize: `price_sale` int VND, `area_min_m2/area_max_m2` float, `noise_db_min` float,
  `energy_stars` int, field thiếu = `null` — **đừng** trả chuỗi "313 lít").
- Chưa có BE2: để `BE2_BASE_URL` rỗng → BE1 tự đọc `fixtures/`.
- Fixture sinh từ excel gốc: `python scripts/make_fixture.py` (chỉ ~10 dòng máy lạnh có giá trong data mẫu).

## RAG chính sách (`app/rag.py`)

Câu hỏi về chính sách (bảo hành, đổi trả, giao hàng, khui hộp, điều khoản, dữ liệu cá nhân, nội quy)
→ intent `policy` → `policy_node`: tìm top-k chunk từ `policy-files/*.md`, trả lời **grounded chỉ
trong trích dẫn** (prompt `POLICY_SYSTEM`), kèm `policy_sources` để FE hiển thị nguồn. Điểm retrieval
tốt nhất < `RAG_MIN_SCORE` → bot thú nhận "chưa có thông tin" thay vì bịa.

- **Chunking**: gộp đoạn liền nhau tới ~800 ký tự, overlap 1 đoạn, gắn tên chính sách vào đầu chunk.
- **Vector DB — Qdrant** (`db/qdrant.py`, cùng phong cách httpx REST với `db/elasticsearch.py`):
  chunk được embed (OpenAI-compatible, cùng `base_url` với LLM — set `EMBED_MODEL` = tên model FPT
  AI Factory) rồi upsert vào collection `policies`. Search = cosine top-k.
- **Fallback**: `MOCK_LLM=1` hoặc `EMBED_MODEL` rỗng → tìm kiếm lexical (token overlap), chạy offline
  không cần key/Qdrant — luồng vẫn hoạt động đầy đủ.

```bash
cd docker && docker compose up -d qdrant   # bật Qdrant (REST :6333)
python scripts/build_policy_index.py       # build/refresh vào Qdrant (cần EMBED_MODEL)
```

Index build **lazily** ở lần hỏi chính sách đầu tiên; marker `logs/policy_qdrant.hash` (hash theo
file + model) cho biết khi nào cần build lại. Thêm/sửa chính sách: bỏ file `.md` vào `policy-files/`
→ hash đổi → tự build lại request kế tiếp. Tên hiển thị cho citation ở `_TITLES` của `app/rag.py`.

## Hợp đồng với ontology (Tùng)

Thay `app/ontology_stub.py` bằng module thật, **giữ nguyên 2 signature**:

```python
get_slot_schema(category) -> list[SlotDef]
suggest_next_question(category, filled_slots, asked_slots, candidates) -> NextQuestion | None
```

`NextQuestion.reason` sẽ hiển thị lên explainability panel — viết cho người đọc.

## Adaptive Decision Ontology Engine

`POST /api/v1/ontology/adapt` builds an adaptive profile from `../data/ontology_data.json` without mutating the reviewed seed. It loads ten reviewed category seeds plus the shared `Tất cả` core.

- Exact seed → `REVIEWED`; related category → guarded `COMPOSED_*`; distant category → `GENERATED_DISTANT` with all new category-specific items marked `PROVISIONAL`.
- Modules activate only when their own schema/sample evidence exists. A display does not automatically activate battery or portability.
- Generated profiles persist in `be1/data/generated_categories.json`; use `/review/{profile_id}/approve` or `/reject` for human review.
- `POST /api/v1/ontology/questions/next` returns at most one eligible Vietnamese question.

Example request:

```json
{"category_name":"Tivi","raw_fields":["Kích thước màn hình","Độ phân giải","Cổng HDMI","Công nghệ âm thanh"]}
```

Run tests with `pytest tests/test_adaptive_ontology.py`.

## Turn log (input cho judge/eval)

Mỗi turn append vào `logs/turns.jsonl`: `query`, `response`, `context_json` (đúng data LLM nhìn thấy
— judge phải đối chiếu với cái này, không phải API thô), `funnel`, `timings_ms` từng stage.

## Judge hallucination + eval harness

```bash
python scripts/judge_batch.py            # chấm mọi turn trong logs/turns.jsonl theo CLAIM
python scripts/eval_run.py               # chạy 10 scenario (eval/scenarios.jsonl) qua HTTP thật
python scripts/eval_run.py --judge       # scenario + chấm hallucination luôn các turn vừa sinh
MOCK_JUDGE=1 python scripts/judge_batch.py   # offline: chỉ đối chiếu con số, không cần key
```

- Judge dùng model **ngoài, mạnh hơn** (env `JUDGE_*`, rỗng thì dùng lại `LLM_*`), chấm từng claim:
  `SUPPORTED / CONTRADICTED / UNSUPPORTED / SALER_TALK` + `null_honesty`.
- Metrics: **hallucination_rate_turn** (turn có ≥1 claim bịa), **grounded_rate_claim**,
  **null_honesty_rate** (target: 0 / 1.0 / 1.0). Turn bị gắn cờ in ra kèm claim + evidence.
- Thêm scenario: append 1 dòng JSON vào `eval/scenarios.jsonl` (kỳ vọng viết lỏng theo
  `expect_turn_type` — chất lượng nội dung để judge chấm, đừng assert cứng vào text).

## Langfuse (tracing)

Điền `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` vào `.env` là tự bật (không có key = no-op):
- Mỗi LLM call (`intent`, `phrase_*`) thành trace, group theo `session_id`.
- `judge_batch.py` push judge traces + scores (`hallucinated_claims`, `grounded`) lên dashboard.
