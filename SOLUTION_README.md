# Trợ lý AI so sánh & tư vấn điện máy theo nhu cầu thật — Mô tả giải pháp

> **Tên đề tài:** *HiểuÝ — Trợ lý AI so sánh & tư vấn sản phẩm theo nhu cầu thật của khách hàng*
> **Track:** Năng suất SME · **Đối tác:** Công ty Cổ phần Đầu tư Điện Máy Xanh
> **Câu hỏi trọng tâm:** *Làm thế nào để xây dựng một trợ lý AI hiểu nhu cầu thật của khách, chủ động hỏi thêm thông tin còn thiếu, và so sánh sản phẩm bằng ngôn ngữ dễ hiểu — thay vì chỉ liệt kê thông số kỹ thuật?*

Tài liệu này mô tả **giải pháp tổng thể** và **những gì đã làm được**. Chi tiết kỹ thuật xem
[`TECHNIQUE_README.md`](TECHNIQUE_README.md); luồng nghiệp vụ xem [`BUSINESS_README.md`](BUSINESS_README.md).

---

## 1. Tóm tắt giải pháp (Executive Summary)

Chúng tôi xây dựng một **trợ lý AI bán hàng đa tác tử (multi-agent)** cho website điện máy, giải quyết
đúng nỗi đau trong đề bài: khách phổ thông không đọc nổi bảng thông số, còn chatbot thị trường thì trả lời
chung chung, bịa số và không biết hỏi lại.

Trợ lý của chúng tôi làm 3 việc mà một nhân viên tư vấn giỏi làm:

1. **Hiểu nhu cầu thật** từ câu nói đời thường, tiếng Việt sai chính tả / không dấu / viết tắt / pha tiếng Anh
   ("mya lanh cho fong 15m2 tam 8tr").
2. **Chủ động hỏi ngược đúng câu quan trọng nhất** — không hỏi lan man. Câu hỏi tiếp theo được chọn bằng thuật
   toán **Decision-Gap** (đo câu hỏi nào thu hẹp được nhiều lựa chọn nhất trên mỗi công sức khách bỏ ra), dựa trên
   một **Ontology quyết định** riêng cho ngành điện máy.
3. **So sánh top 3 sản phẩm bằng ngôn ngữ dễ hiểu**, giải thích trade-off ("mẫu này chạy êm hơn cho phòng ngủ,
   mẫu kia tiết kiệm điện hơn"), **mọi con số đều lấy từ catalog/RAG thật — không bịa**.

Toàn bộ chạy trên **model open-weight** (Llama 3.3 70B qua endpoint OpenAI-compatible; embedding từ FPT AI Factory),
**triển khai on-premise dễ dàng tại doanh nghiệp**, không phụ thuộc API đóng.

---

## 2. Cách tiếp cận & kỹ thuật chính

| # | Kỹ thuật | Vai trò trong giải pháp | Trạng thái |
|---|----------|-------------------------|-----------|
| 1 | **LangGraph multi-agent / state machine** | Điều phối luồng `intent → retrieve → (hỏi ngược \| so sánh \| chi tiết \| chính sách \| sản phẩm lạ)`, giữ state qua nhiều lượt (multi-turn), checkpoint bền vững trên PostgreSQL |Đã làm |
| 2 | **Adaptive Decision Ontology** (Ontology quyết định thích ứng) | "Bộ não" quyết định được phép hỏi gì & vì sao; 510 concept, 124 câu hỏi, 16+ ngành hàng; tự thích ứng cho category mới có kiểm soát (REVIEWED / COMPOSED / GENERATED) + human review |Đã làm |
| 3 | **Decision-Gap Clarification (hỏi ngược thông minh)** — *kỹ thuật lõi* | Chọn câu hỏi tiếp theo **tất định** bằng cách mô phỏng tác động của mỗi câu hỏi lên top-3, chống hỏi lan man & chống bịa |Đã làm |
| 4 | **Tool calling để chống hallucination trên dữ liệu sản phẩm** | Số liệu sản phẩm luôn lấy từ Elasticsearch / catalog thật qua tool, không để LLM tự nhớ |Đã làm |
| 5 | **RAG cho chính sách** (bảo hành, đổi trả, giao hàng, khui hộp, dữ liệu cá nhân, nội quy) | Trả lời **grounded trong trích dẫn**, điểm thấp → thú nhận "chưa có thông tin" thay vì bịa; kèm citation nguồn |Đã làm |
| 6 | **Agentic tool-calling cho "sản phẩm lạ"** | Khách hỏi model không có trong kho → agent tự `web_search` → trích thông số → tra lại kho → gợi ý mẫu tương đương; có bounded loop chống lặp vô hạn |Đã làm |
| 7 | **So sánh & diễn giải trade-off bằng prompting nâng cao** | Ngôn ngữ non-tech, tập trung lợi ích thực tế, mỗi đề xuất kèm lý do |Đã làm |
| 8 | **Guardrail chống bịa số + Judge harness** | Chấm từng claim `SUPPORTED / CONTRADICTED / UNSUPPORTED`, đo `hallucination_rate`, `null_honesty`; 22 kịch bản regression |Đã làm |
| 9 | **UX "vừa chat vừa shopping"** | Chat bubble stream nhiều tin ngắn như người thật; card sản phẩm bấm xem được; nút "Còn N/M mẫu khớp" → mở trang lọc như web ĐMX thật; bảng "đang suy nghĩ" show tool calling |Đã làm |
| 10 | **Bộ nhớ hội thoại nén (history compression agent)** | Tự tóm tắt lịch sử khi khách đổi chủ đề, giữ context dài mà tiết kiệm token |Đã làm |
| 11 | **Kiểm tra tồn kho / giao lắp theo khu vực (fulfillment)** | Hỏi tỉnh/thành khi khách chốt mẫu, kiểm tra khả năng phục vụ |Đã làm |
| 12 | **Auth + phiên chat cá nhân hóa** (phone/password, JWT, session) | Lưu lịch sử theo tài khoản; guest chat vẫn dùng được không cần đăng nhập |Đã làm |
| 13 | **Tìm sản phẩm theo ảnh** | Khách gửi ảnh → nhận diện & tra sản phẩm tương tự | Đã làm |
| 14 | **Recommendation System theo feedback / rating** | Gợi ý cá nhân hóa theo hành vi, đánh giá, phản hồi | Đã làm  |

---

## 3. Bám sát tiêu chí chấm điểm của đề bài

| Tiêu chí đặc thù track (30%) | Cách giải pháp đáp ứng |
|---|---|
| **Hiểu nhu cầu & hỏi ngược thông minh (10%)** | Ontology + Decision-Gap: chỉ hỏi câu tác động lớn nhất, nhận diện ngân sách/ràng buộc/ưu tiên; mỗi câu hỏi kèm lý do (`reason`) hiển thị trên panel explainability |
| **So sánh sản phẩm có giải thích trade-off (10%)** | Top-3 đa dạng hóa (best-fit / rẻ hơn / cao cấp hơn) + prompt diễn giải ưu-nhược bằng ngôn ngữ phổ thông |
| **Tính đúng dữ liệu & chống hallucination (10%)** | Tool calling lấy số thật + RAG grounded + guardrail + judge harness; điểm RAG thấp → thú nhận thiếu thông tin |

Các anti-pattern đề bài nêu (bịa giá/tồn kho, không hỏi lại, demo mockup, bắt khách tự đọc thông số, chỉ chạy
với dữ liệu sạch) đều được xử lý trực tiếp — xem [`TECHNIQUE_README.md`](TECHNIQUE_README.md) mục "Anti-hallucination".

---

## 4. Deliverables đã đạt (theo D2 của đề bài)

-**Prototype chatbot web demo được** (React + SSE streaming, chat bubble + trang kết quả sản phẩm).
-**Code repository public** (backend `be1/`, frontend `fe/`, deploy `deploy/`).
-**Kiến trúc AI giải thích được**: RAG/catalog retrieval, product ranking tất định, guardrail chống bịa —
  tài liệu hóa trong `TECHNIQUE_README.md` + `BUSINESS_README.md`.
-**Lộ trình pilot / triển khai thực tế** — mục 6 dưới đây.
-**Dữ liệu catalog mẫu + flow hỏi ngược + so sánh ≥3 sản phẩm + đề xuất top 3 kèm trade-off.**
-**CI/CD + Docker hóa** toàn stack, deploy được on-premise.

---

## 5. Kiến trúc triển khai

- **Backend (`be1/`)**: FastAPI + LangGraph, PostgreSQL (users/session/checkpoint), Elasticsearch (catalog),
  Qdrant (vector chính sách), tối đa **2 lần gọi LLM/lượt** (NLU structured + phrasing streaming) — phần lọc/xếp
  hạng **hoàn toàn tất định**, đảm bảo đáp ứng yêu cầu tốc độ (< 3s hỏi ngược, < 5s so sánh top 3).
- **Frontend (`fe/`)**: React 19 + Vite, giao diện mô phỏng website ĐMX, chat widget stream thời gian thực.
- **Model open-weight**: Llama 3.3 70B (OpenAI-compatible: Groq/Fireworks/Together/FPT AI Factory), embedding
  FPT AI Factory → **on-premise, không khóa nhà cung cấp**.
- **Chế độ MOCK offline** (`MOCK_LLM=1`): chạy full luồng không cần API key — thuận tiện chấm & demo.

---

## 6. Lộ trình pilot (theo D3 của đề bài)

1. **Tuần 1–2:** Cắm catalog + chính sách + tồn kho thật (qua API nội bộ ĐMX) cho 1 nhóm ngành hàng thử nghiệm
   (máy lạnh / tủ lạnh / tivi / laptop). Ontology đã hỗ trợ sẵn 16+ ngành hàng.
2. **Tuần 3–6:** A/B test trên 1.000–10.000 lượt hội thoại; đo tỉ lệ hỏi-đúng-nhu-cầu, độ hài lòng, tỉ lệ chuyển đổi.
3. **Tuần 7–12:** Bật recommendation theo feedback/rating + tìm theo ảnh (roadmap); tinh chỉnh ontology theo phản
   hồi chuyên gia ngành hàng qua cơ chế human-review đã có sẵn.

**Điều kiện ký hợp đồng pilot** (đề bài): demo đạt KPI độ đúng thông tin, không hallucination nghiêm trọng, giao
diện dễ dùng, log nguồn dữ liệu, tích hợp được API catalog/stock/promotion — **toàn bộ đã có trong kiến trúc hiện tại**.

---

## 7. Điểm khác biệt so với giải pháp thị trường

- Không phải "bộ lọc + bảng so sánh thông số" tĩnh: trợ lý **chủ động hội thoại**, hỏi đúng chỗ.
- Không phải chatbot FAQ kịch bản: **hiểu ngôn ngữ tự nhiên** + **grounded trên dữ liệu thật**.
- Câu hỏi hỏi-ngược **tất định & giải thích được** (Decision-Gap), không "hỏi cho có".
- **Chống bịa số có kiểm chứng** bằng judge harness — không chỉ hứa suông.
- **Open-weight, on-premise** — phù hợp doanh nghiệp Việt lo ngại chi phí & bảo mật dữ liệu.
