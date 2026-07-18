# TECHNIQUE_README — Chi tiết kỹ thuật

Trợ lý AI so sánh & tư vấn điện máy — kiến trúc, thuật toán và cơ chế chống hallucination.
Tài liệu này dành cho người đọc kỹ thuật (giám khảo AI-Native Architecture / Technical Execution).
Luồng nghiệp vụ mức cao xem [`BUSINESS_README.md`](BUSINESS_README.md).

---

## 0. Nguyên tắc thiết kế xuyên suốt

1. **LLM chỉ làm 2 việc: hiểu ngôn ngữ và diễn đạt.** Mọi quyết định lọc / xếp hạng / chọn câu hỏi đều **tất định
   (deterministic)** bằng code — nên có thể giải thích, tái lập, và không bịa.
2. **Tối đa 2 lần gọi LLM/lượt**: (a) NLU structured output trích ý định; (b) phrasing streaming câu trả lời. Một
   lần thứ 3 chỉ thêm khi đổi chủ đề (nén lịch sử) bằng model nhỏ.
3. **Không có số nào do LLM tự nghĩ ra.** Số liệu sản phẩm đến từ Elasticsearch; số liệu chính sách đến từ chunk
   RAG được trích dẫn. Guardrail + judge kiểm tra lại.
4. **Chạy được offline** (`MOCK_LLM=1`): regex/template thay LLM, lexical search thay vector — full luồng vẫn chạy,
   thuận tiện test & chấm không cần key.

---

## 1. Kiến trúc tổng thể

```
┌─────────────┐   SSE stream    ┌──────────────────────────────────────────────┐
│  Frontend   │ ◄────────────── │  FastAPI (be1)                                │
│  React+Vite │  events:        │  ┌────────────────────────────────────────┐  │
│  ChatBubble │  funnel_count   │  │  LangGraph state machine (graph.py)     │  │
│  ProductRes │  question       │  │  intent → history → route → node → END  │  │
└─────────────┘  text_chunk     │  └────────────────────────────────────────┘  │
                 product_cards  │      │           │            │               │
                 policy_sources │  ┌───▼───┐  ┌────▼─────┐  ┌───▼────┐          │
                 tool_call/res  │  │Ontology│  │Decision- │  │  RAG   │          │
                 done           │  │(adaptive)│ │Gap engine│  │ policy │          │
                                │  └───┬───┘  └────┬─────┘  └───┬────┘          │
                                └──────┼───────────┼───────────┼───────────────┘
                                   ┌───▼───┐  ┌────▼─────┐  ┌───▼────┐
                                   │Elastic│  │  Scoring │  │ Qdrant │
                                   │search │  │ (rank3)  │  │ vectors│
                                   └───────┘  └──────────┘  └────────┘
        Postgres: users / auth session / chat_sessions / LangGraph checkpoint
```

Model: **open-weight** Llama 3.3 70B qua endpoint OpenAI-compatible (`LLM_BASE_URL`); embedding FPT AI Factory.

---

## 2. LangGraph multi-agent state machine (`app/graph.py`)

`AgentState` (TypedDict) mang toàn bộ ngữ cảnh lượt: `category`, `slots`, `priorities`, `asked_slots`,
`candidates`, `catalog_products`, `session_content` (tóm tắt nén), `recent_messages`, cờ fulfillment / enrich…

**Các node & định tuyến:**

- `intent_node` → gọi LLM structured (`IntentResult`) trích: `intent_type`, `category`, `budget_max`, `priorities`,
  `product_mentions`, `selected_index`, `ontology_answers`… Sau đó **validate mọi thứ lại bằng catalog thật**
  (category phải là nhãn có trong Elasticsearch; câu trả lời cho câu hỏi đang mở phải "executable" trên catalog
  hiện tại — nếu mơ hồ thì hỏi lại thay vì tạo filter giả).
- `history_control_node` → nén lịch sử khi phát hiện đổi chủ đề (mục 8).
- `route_after_intent` → phân nhánh **tất định**: đang trả lời câu hỏi enrich? đang chờ fulfillment? chọn mẫu cụ
  thể? chính sách? category mơ hồ cần làm rõ? nêu tên sản phẩm lạ? chào hỏi? off-topic?
- `retrieve_node` → lấy sản phẩm theo category, dựng runtime slot-schema từ ontology + spec ES, **áp hard filter
  + ontology filter**, phát `funnel_count` (còn N/M mẫu khớp).
- `route_after_retrieve` → `ask` (hỏi ngược) / `compare` (so sánh top-3) / `detail` (chi tiết 1 mẫu) /
  `price_answer` / `fulfillment_prompt` / `catalog_unavailable`.
- Nhánh **"sản phẩm lạ"**: `product_lookup → enrich → resolve` (mục 6).
- `policy_node` → RAG chính sách (mục 5).
- `greeting_node` / `off_topic_node` / `clarify_category_node` / `fulfillment_*_node`.

Checkpoint qua `AsyncPostgresSaver` → state bền vững qua restart; guest turn compile **không checkpointer**
(stateless theo thiết kế).

---

## 3. Adaptive Decision Ontology — "bộ não" được phép hỏi gì (`app/ontology.py`, `app/adaptive_ontology.py`)

Nguồn: `data/ontology_data.json` sinh từ file Excel chuyên gia ngành hàng ĐMX — **510 concept, 124 câu hỏi,
255 quan hệ, 87 rule, 16+ ngành hàng** (Máy lạnh, Tủ lạnh, Máy giặt, Máy sấy, Tivi/Màn hình, Laptop/Máy tính,
Máy nước nóng, Máy rửa chén, Bàn ủi, Đồng hồ thông minh…).

**Cơ chế:**

- Mỗi `questionNode` có `conceptId`, `category`, `mvpStatus` (Must Have / …), `hardGate` (câu hỏi lọc cứng hay
  ưu tiên mềm), `ask_hint` (câu hỏi tiếng Việt), `question_type` (numeric / boolean / ordinal / choice), và map
  tới `requiredFields` (thông số catalog thật) qua `edges`.
- `get_runtime_slot_schema(category, products)` **compile** schema tại runtime: chỉ giữ câu hỏi (a) thuộc đúng
  category (hoặc "Tất cả"), (b) là Must-Have đã review, (c) có **đúng 1 trường catalog thật** khớp trong spec ES
  hiện có. → Không hỏi về thông số mà catalog không có (chống hallucination từ gốc).

**Adaptive engine (`POST /api/v1/ontology/adapt`):**

- Category trùng seed đã review → `REVIEWED`.
- Category liên quan → `COMPOSED_*` (ghép có kiểm soát từ seed gần nhất).
- Category xa lạ → `GENERATED_DISTANT`, mọi item mới gắn cờ `PROVISIONAL`.
- Module (pin, độ ồn, diện tích…) chỉ **kích hoạt khi có bằng chứng schema/sample** — màn hình không tự bật câu
  hỏi "pin".
- Profile thích ứng lưu ở `be1/data/adaptive_profiles.json`; có `/review/{id}/approve|reject` cho **human-in-the-loop**.
  → Mở rộng sang ngành hàng mới **an toàn, có kiểm soát**, không cần viết code riêng cho từng category.

---

## 4. Decision-Gap Clarification — kỹ thuật lõi để "hỏi ngược thông minh" (`app/decision_gap.py`)

**Vấn đề:** chatbot thường hỏi lan man hoặc hỏi câu vô nghĩa. Ta cần hỏi **đúng câu quan trọng nhất**.

**Ý tưởng:** với mỗi câu hỏi (slot) chưa được trả lời, **mô phỏng** các câu trả lời khả dĩ của khách và đo xem
top-3 sản phẩm **thay đổi bao nhiêu**. Câu hỏi làm top-3 đổi nhiều nhất trên mỗi đơn vị công sức khách bỏ ra =
câu hỏi đáng hỏi nhất.

**Thuật toán (`choose_next_question`):**

1. Tính baseline: `apply_hard_filters` + `apply_ontology_filters` → `rank_top3` → chữ ký `[sku1, sku2, sku3]`.
2. Với mỗi slot chưa hỏi:
   - Sinh `_likely_answers` **từ chính catalog** (ví dụ ngân sách: phân vị 25/55/80 của giá thật; diện tích: các
     ngưỡng công suất thật; boolean: chỉ đề xuất khi kho có cả hai loại).
   - Với mỗi câu trả lời giả định → lọc & xếp hạng lại **bằng đúng executor tất định của luồng thật** → đo
     `_top3_change` (0 = y hệt, 1 = khác hoàn toàn; tính cả thành phần & thứ tự).
   - `expected_change` = trung bình; `utility = expected_change / customer_effort`.
3. Câu hỏi `required` (gate điều kiện) luôn được giữ; còn lại chọn theo `utility` cao nhất.
4. Trả `NextQuestion(slot, reason)` — **`reason` là câu giải thích được**, đẩy lên panel explainability
   ("Decision-gap chọn 'ngân sách': tác động kỳ vọng lên top-3 là 0.62, utility sau chi phí trả lời là 0.62").

→ Không LLM nào "nghĩ ra" câu hỏi. Hỏi ngược **tất định, giải thích được, bám dữ liệu thật**.

---

## 5. RAG chính sách — grounded, có citation, biết thú nhận (`app/rag.py`)

Câu hỏi về **bảo hành / đổi trả / giao hàng-lắp đặt / khui hộp / điều khoản / dữ liệu cá nhân / nội quy** →
`intent=policy` → `policy_node`.

- **Nguồn:** `policy-files/*.md` (6 file chính sách thật, ~85KB).
- **Chunking:** gộp đoạn liền nhau ~800 ký tự, overlap 1 đoạn, gắn tên chính sách vào đầu chunk.
- **Vector DB — Qdrant:** embed (OpenAI-compatible, dùng lại base_url của LLM; `EMBED_MODEL` = model FPT AI Factory)
  → upsert collection `policies` → search cosine top-k. Index build **lazy** ở câu hỏi chính sách đầu tiên; marker
  hash (file + model) biết khi nào cần build lại.
- **Fallback offline:** `MOCK_LLM=1` hoặc `EMBED_MODEL` rỗng → lexical search (token overlap), chạy không cần key/Qdrant.
- **Grounded prompt (`POLICY_SYSTEM`):** trả lời **chỉ trong trích dẫn**; điểm retrieval tốt nhất `< RAG_MIN_SCORE`
  → bot **thú nhận "chưa có thông tin"** thay vì bịa. Kèm event `policy_sources` để FE hiển thị citation (title +
  source + score).
- Khiếu nại sản phẩm đã mua bị lỗi ("mua cái bình đun tuần trước giờ không nóng") cũng route về policy (bảo hành/đổi trả).

---

## 6. Agentic tool-calling cho "sản phẩm lạ" (`app/tools.py`, nhánh `enrich/resolve` trong `graph.py`)

Khách hỏi model **không có trong kho** → không phán "không có" ngay:

1. `product_lookup_node` tra Elasticsearch theo tên/mã trước.
2. Không thấy → `enrich_node`: `fetch_product_specs` (web_search qua Tavily → trích thông số: giá, công suất,
   diện tích phù hợp, độ ồn…) **song song** với hỏi thêm nhu cầu nếu chưa đủ.
3. `resolve_node`: khi có LLM thật → **vòng lặp tool-calling thật** (`run_tool_agent` với `bind_tools`): agent tự
   quyết `web_search` / `search_catalog` / `filter_catalog`, **bounded** (`MAX_ENRICH_ITERS`) chống lặp vô hạn;
   provider lỗi → rơi về orchestration tất định, không sập lượt chat.
4. Kết quả: nếu kho có mẫu đúng → hiện; nếu không → gợi ý **mẫu tương đương hợp nhu cầu nhất**; nếu web xác nhận
   sản phẩm không tồn tại ("Apple không có iPhone 9") → trả **câu chốt web-grounded** thay vì "nới lỏng bộ lọc" vô nghĩa.

FE nhận `tool_call` / `tool_result` / `web_specs` → dựng bảng **"đang suy nghĩ"** (bật/tắt bằng `VITE_DEBUG`).

---

## 7. Scoring & so sánh trade-off (`app/scoring.py`, `compare_node`)

- `rank_top3`: điểm utility theo `priorities` (tiết kiệm điện / ít ồn / giá rẻ) với trọng số giảm dần `1/(i+1)`,
  cộng thêm `catalog_preferences` (ưu tiên khách nói tường minh trên trường catalog bất kỳ, không cần code riêng cho
  từng category). Sản phẩm thiếu giá **không được** hiện như "lựa chọn rẻ" khi có mẫu khác đủ giá.
- **Đa dạng hóa top-3**: `best-fit` + `rẻ hơn` + `cao cấp hơn` → khách có phổ lựa chọn để quyết định.
- `compare_node` phát `product_cards` + `_context` (data LLM nhìn thấy) rồi stream lời diễn giải trade-off bằng
  **ngôn ngữ phổ thông** (prompt `compare`), tập trung lợi ích thực tế thay vì thông số khô khan.

---

## 8. Bộ nhớ hội thoại nén (`app/session_history.py`, `history_control_node`)

Giữ các tin gần nhất ở "raw window"; khi intent xác nhận đổi chủ đề → model nhỏ tóm tắt (`session_content` Markdown
tích lũy), xóa raw window cũ, bắt đầu window mới. LLM các lượt sau chỉ nhận **tóm tắt + window mới** → giữ context
dài, tiết kiệm token. `session_content` được persist owner-scoped trong `chat_sessions`, không bao giờ forward qua SSE.

---

## 9. Anti-hallucination — guardrail + judge harness (`app/judge.py`, `eval/`, `scripts/`)

**Guardrail runtime:**
- Số sản phẩm chỉ từ catalog; số chính sách chỉ từ chunk RAG được trích.
- RAG điểm thấp → thú nhận thiếu thông tin.
- `funnel_count` là con số thật của bộ lọc → prompt không được nói "đang có N mẫu" khi chưa lọc.

**Judge harness (offline eval):**
- `scripts/judge_batch.py` chấm **từng claim** trong mỗi lượt: `SUPPORTED / CONTRADICTED / UNSUPPORTED / SALER_TALK`
  + `null_honesty`, đối chiếu với `context_json` (đúng data LLM thấy — không phải API thô).
- Metrics: **hallucination_rate_turn**, **grounded_rate_claim**, **null_honesty_rate** (target 0 / 1.0 / 1.0).
- Judge dùng **model ngoài mạnh hơn** (`JUDGE_*`); `MOCK_JUDGE=1` chỉ đối chiếu con số, chạy offline.
- **22 kịch bản regression** (`eval/scenarios.jsonl`) khóa lại đúng các lỗi hay gặp: bịa số lượng mẫu, tính sai
  chênh giá, bịa "5 sao/tiết kiệm nhất", bịa % tiết kiệm điện, bịa wifi/bảo hành, sản phẩm ngoài danh mục, chào
  hỏi bị nhầm off-topic, ngân sách hợp lệ bị coi lạc đề… (`scripts/eval_run.py --judge`).
- Tracing: **Langfuse** (bật khi có 2 key) — mỗi LLM call thành trace group theo session; judge push score lên dashboard.

---

## 10. Xử lý ngôn ngữ & context Việt Nam (đáp ứng Phần H đề bài)

- Hiểu tiếng Việt **sai chính tả / không dấu / viết tắt / teen-speak / pha tiếng Anh** ("mya lanh", "air purifier",
  "mún mua máy sấy") và code-switching Việt-Anh trong tên/thông số.
- Chuẩn hóa đơn vị: `10tr` / `10 triệu` → `10000000` VND; hiểu m², HP, BTU, GB, lít, inch.
- Văn phong nhân viên tư vấn Việt: gần gũi, "dạ/ạ", **không dùng thuật ngữ marketing với khách phổ thông**; linh
  hoạt non-tech ↔ high-tech theo cách khách nói.
- Fulfillment theo tỉnh/thành (`app/fulfillment.py`) khi khách chốt mẫu.

---

## 11. Bảo mật & vận hành

- Auth phone/password: chuẩn hóa E.164, hash Argon2 (không lưu plaintext), rate-limit đăng nhập sai (HMAC digest),
  JWT access/refresh gắn session revoke được, refresh rotation + replay detection.
- Cookie HttpOnly + SameSite=Lax (production ép Secure), CORS theo `FRONTEND_ORIGINS` (cấm wildcard khi credentialed).
- `validate_auth_config()` fail-fast khi secret/cấu hình không an toàn ở production.
- Docker hóa toàn stack + CI/CD (GitHub Actions: test → build gate → deploy on main), triển khai **on-premise**.

---

## 12. Roadmap kỹ thuật (chưa hoàn thiện — kiến trúc đã chừa chỗ)

- **Tìm sản phẩm theo ảnh:** thêm tool `search_by_image` (vision embedding → so khớp catalog), cắm vào nhánh
  tool-calling hiện có như một tool mới — không đổi kiến trúc graph.
- **Recommendation System theo feedback/rating:** thêm tầng cá nhân hóa vào `scoring.py` (collaborative / content-
  based trên hành vi + rating), đọc từ store feedback; `catalog_preferences` hiện tại là điểm cắm tự nhiên.
