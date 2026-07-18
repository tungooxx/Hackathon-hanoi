# BE1 — DMX AI Advisor (core xử lý)

Flow: `intent → retrieve → [hỏi ngược | so sánh top 3] | off-topic`, tối đa **2 lượt LLM/turn**
(NLU structured + phrasing streaming), filter/ranking hoàn toàn deterministic.

## Chạy

```bash
cd be1
cp .env.example .env            # MOCK_LLM=1: chạy không cần API key
# Đặt cùng mật khẩu trong docker/.env.docker và DATABASE_URL trong .env.
docker compose -f docker/docker-compose.yml up -d postgres elasticsearch
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8100
uv run python scripts/smoke.py   # smoke test 4 turn, phải ALL PASS
```

Cắm LLM thật: sửa `.env` → `MOCK_LLM=0` + `LLM_API_KEY` (OpenAI-compatible: Groq/Fireworks/Together).

## PostgreSQL + migrations

PostgreSQL lưu dữ liệu bền vững của ứng dụng; Elasticsearch vẫn chỉ dùng cho
tìm kiếm sản phẩm. Schema hiện tại gồm:

- `users`: danh tính ổn định theo UUID, số điện thoại E.164 là duy nhất.
- `otp_challenges`: chỉ lưu digest của OTP, thời hạn và số lần thử còn lại.
- `auth_sessions`: chỉ lưu digest của refresh token, có thể revoke theo session.

Sau khi đổi model trong `db/models.py`, tạo và kiểm tra migration:

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
uv run alembic current --check-heads
```

## Phone authentication service

The backend service layer is implemented under `app/auth/` and
`app/repositories/`. It currently provides:

- Vietnamese phone normalization to E.164.
- Cryptographically generated OTPs stored only as HMAC digests.
- Resend cooldowns and rolling phone/IP request limits.
- Persisted verification-attempt limits, expiry, and replay prevention.
- Access/refresh JWT pairs bound to a revocable database session.
- Refresh-token rotation with replay detection.
- Access-token authentication and idempotent logout revocation.

`OTP_PROVIDER=console` prints a masked phone number and OTP for local
development. It is rejected when `APP_ENV=production`; configure a real SMS
adapter before deploying. HTTP authentication routes and cookies are added in
the next implementation phase.

Run the service and security tests against the local PostgreSQL container:

```bash
uv run python -m unittest discover -s tests -v
```

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
