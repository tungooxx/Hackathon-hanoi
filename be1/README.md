# BE1 — DMX AI Advisor (core xử lý)

Flow: `intent → retrieve → [hỏi ngược | so sánh top 3] | RAG chính sách | off-topic`, tối đa
**2 lượt LLM/turn** (NLU structured + phrasing streaming), filter/ranking hoàn toàn deterministic.

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
- `users.password_hash`: Argon2 hash; mật khẩu gốc không được lưu.
- `auth_login_attempts`: chỉ lưu HMAC digest phục vụ giới hạn đăng nhập sai.
- `auth_sessions`: chỉ lưu digest của refresh token, có thể revoke theo session.
- `chat_sessions`: metadata hội thoại thuộc một `users.id`, ánh xạ sang thread
  LangGraph nội bộ do server tạo.

LangGraph stores graph state in its own PostgreSQL checkpoint tables through
`AsyncPostgresSaver`. Its schema is initialized by the checkpointer at app
startup and excluded from Alembic autogeneration; Alembic continues to own all
application tables.

Sau khi đổi model trong `db/models.py`, tạo và kiểm tra migration:

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
uv run alembic current --check-heads
```

## Phone/password authentication service

The backend service layer is implemented under `app/auth/` and
`app/repositories/`. It currently provides:

- Vietnamese phone normalization to E.164.
- Argon2 password hashing through `pwdlib`; plaintext passwords are never stored.
- Registration with phone, password, and password confirmation.
- Generic invalid-credential responses and a dummy-hash check for unknown phones.
- Persisted rolling phone/IP limits for failed login attempts.
- Access/refresh JWT pairs bound to a revocable database session.
- Refresh-token rotation with replay detection.
- Access-token authentication and idempotent logout revocation.

No OTP or SMS provider is required. Password reset/recovery is intentionally
outside the current authentication phase.

Run the service and security tests against the local PostgreSQL container:

```bash
uv run python -m unittest discover -s tests -v
```

### Authentication API

| Endpoint | Body/session | Result |
|---|---|---|
| `POST /auth/register` | Phone, password, password confirmation | Creates the user and sets access/refresh cookies |
| `POST /auth/login` | Phone and password | Verifies credentials and sets access/refresh cookies |
| `POST /auth/refresh` | Refresh cookie | Rotated access/refresh cookies |
| `GET /auth/me` | Access cookie | Current authenticated user |
| `POST /auth/logout` | Refresh cookie when present | Revokes the session and clears both cookies |

JWTs are never returned in JSON. The access cookie is available to the whole
application, while the refresh cookie is restricted to `/auth`. Both are
`HttpOnly` and `SameSite=Lax`; production configuration also requires
`Secure`.

Frontend requests must use `credentials: "include"` and an origin listed in
`FRONTEND_ORIGINS`. During local development, use matching hostnames on both
sides—for example, `http://localhost:5173` with
`http://localhost:8100`—because `localhost` and `127.0.0.1` are different
cookie sites.

Expected authentication errors use:

```json
{
  "error": {
    "code": "invalid_credentials",
    "message": "Số điện thoại hoặc mật khẩu không đúng."
  }
}
```

## Chat API

Persistent chat-session endpoints require a valid access-cookie session. The
server derives ownership exclusively from the JWT `sub`; a request body never
accepts `user_id` or an internal LangGraph thread ID.

| Endpoint | Purpose |
|---|---|
| `POST /chat/guest/messages` | Run one stateless guest turn without authentication |
| `POST /chat/sessions` | Create a server-owned conversation |
| `GET /chat/sessions` | List only the current user's conversations |
| `GET /chat/sessions/{id}` | Read owned conversation metadata |
| `PATCH /chat/sessions/{id}` | Rename an owned conversation |
| `DELETE /chat/sessions/{id}` | Delete metadata and its checkpoints |
| `POST /chat/sessions/{id}/messages` | Stream one assistant turn over SSE |

The message body is `{"message": "..."}`. The response stream contains:

| event | data | dùng làm |
|---|---|---|
| `funnel_count` | `{count, total, filters}` | explainability panel (số SP còn khớp) |
| `question` | `{slot, reason}` | đánh dấu turn hỏi ngược + lý do hỏi |
| `text_chunk` | `{content}` | text bot, append dần |
| `product_cards` | `{products: [...]}` | render 3 card sản phẩm |
| `policy_sources` | `{sources: [{title, source, score}]}` | citation cho câu trả lời chính sách (RAG) |
| `done` | `{turn_type: ask\|compare\|no_match\|policy\|off_topic}` | kết thúc turn |

The API returns only the public `chat_sessions.id`. Every lookup also requires
`chat_sessions.user_id == current_user.id`; another user's UUID returns the
same `404` as an unknown UUID. The private `langgraph_thread_id` is generated
server-side and persists conversation state across restarts.

Authenticated sessions also expose `session_content`, a cumulative Markdown
summary managed by the history-control graph node. The graph keeps completed
messages in a recent raw window. When intent detection confirms a product-topic
change, the node summarizes the previous `session_content` plus that raw window,
persists the new Markdown, clears the compressed raw messages, and starts a new
window with the topic-changing user message. Future LLM calls receive only the
Markdown summary followed by the new raw window.

The old unauthenticated `POST /chat` endpoint and browser-generated
`session_id` contract have been removed.

Guest turns use the same message body and SSE events, but every request is
independent. BE1 does not create a `chat_sessions` row, LangGraph checkpoint,
thread ID, or `logs/turns.jsonl` record for a guest. The browser can display
messages until reload, but the server does not remember earlier guest turns.

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
