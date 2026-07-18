# BE1 — DMX AI Advisor (core xử lý)

Flow: `intent → retrieve → [hỏi ngược | so sánh top 3] | off-topic`, tối đa **2 lượt LLM/turn**
(NLU structured + phrasing streaming), filter/ranking hoàn toàn deterministic.

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
| `done` | `{turn_type: ask\|compare\|no_match\|off_topic}` | kết thúc turn |

State hội thoại persist theo `session_id` (LangGraph checkpointer) — FE chỉ cần giữ 1 session_id.

## Hợp đồng với BE2 (Kiên)

- `GET {BE2_BASE_URL}/products?category=may_lanh` → JSON list, shape xem `fixtures/may_lanh.json`
  (đã normalize: `price_sale` int VND, `area_min_m2/area_max_m2` float, `noise_db_min` float,
  `energy_stars` int, field thiếu = `null` — **đừng** trả chuỗi "313 lít").
- Chưa có BE2: để `BE2_BASE_URL` rỗng → BE1 tự đọc `fixtures/`.
- Fixture sinh từ excel gốc: `python scripts/make_fixture.py` (chỉ ~10 dòng máy lạnh có giá trong data mẫu).

## Hợp đồng với ontology (Tùng)

Thay `app/ontology_stub.py` bằng module thật, **giữ nguyên 2 signature**:

```python
get_slot_schema(category) -> list[SlotDef]
suggest_next_question(category, filled_slots, asked_slots, candidates) -> NextQuestion | None
```

`NextQuestion.reason` sẽ hiển thị lên explainability panel — viết cho người đọc.

## Turn log (input cho judge/eval)

Mỗi turn append vào `logs/turns.jsonl`: `query`, `response`, `context_json` (đúng data LLM nhìn thấy
— judge phải đối chiếu với cái này, không phải API thô), `funnel`, `timings_ms` từng stage.
