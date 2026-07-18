# BUSINESS_README — Luồng logic nghiệp vụ

Trợ lý AI so sánh & tư vấn điện máy — mô tả **hành trình khách hàng** và **logic quyết định** dưới góc nhìn
nghiệp vụ (dành cho giám khảo Problem Relevance / Feasibility / Startup Potential và người không chuyên kỹ thuật).
Chi tiết kỹ thuật xem [`TECHNIQUE_README.md`](TECHNIQUE_README.md).

---

## 1. Bài toán nghiệp vụ

Khách phổ thông mua điện máy (máy lạnh, tủ lạnh, tivi, laptop…) **không đọc nổi bảng thông số**: "313 lít",
"inverter", "9.000 BTU" không cho họ biết máy nào **hợp với hoàn cảnh của mình**. Kết quả:

- Khách mất nhiều thời gian, khó quyết định → **rời web, không chốt đơn**.
- Nhân viên tư vấn phải trả lời lặp lại các câu giống nhau, không scale giờ cao điểm.
- Chatbot thị trường trả lời **chung chung, bịa số, không biết hỏi lại** → mất niềm tin.

**Mục tiêu:** một trợ lý AI cư xử như **nhân viên tư vấn giỏi nhất** — hiểu nhu cầu thật, hỏi đúng câu quan trọng,
so sánh dễ hiểu, và **không bao giờ bịa**.

---

## 2. Hành trình khách hàng (Customer Journey)

```
Khách mở web ĐMX
   │
   ├─► Bấm bong bóng chat 💬  (khách vãng lai dùng được ngay, không cần đăng nhập)
   │
   ▼
[1] Khách nói nhu cầu bằng lời đời thường
     "em muốn mua máy lạnh cho phòng 15m2 tầm 8 triệu, ở được thì tiết kiệm điện"
   │
   ▼
[2] Trợ lý HIỂU  →  category=máy lạnh, diện tích=15m², ngân sách≤8tr, ưu tiên=tiết kiệm điện
     (hiểu cả khi sai chính tả / không dấu / viết tắt / pha tiếng Anh)
   │
   ▼
[3] Trợ lý LỌC KHO thật  →  hiển thị "🔎 Còn 6/40 mẫu khớp · ngân sách ≤ 8.000.000đ, 15m²"
     (bấm vào xem tất cả mẫu khớp trên trang như web ĐMX thật)
   │
   ▼
[4] Còn quá nhiều lựa chọn?  →  HỎI NGƯỢC đúng 1 câu quan trọng nhất
     "Dạ phòng mình là phòng ngủ hay phòng khách ạ? Có bị nắng chiều trực tiếp không?"
     (kèm lý do vì sao hỏi — không hỏi lan man)
   │
   ▼
[5] Đủ thông tin?  →  SO SÁNH TOP 3 bằng ngôn ngữ dễ hiểu
     • Mẫu A — hợp nhất: chạy êm, phù hợp phòng ngủ 15m²
     • Mẫu B — tiết kiệm hơn: hóa đơn điện thấp hơn, giá nhỉnh chút
     • Mẫu C — rẻ hơn: tiết kiệm chi phí ban đầu, đủ dùng
     (mỗi mẫu kèm card bấm xem được + lý do + trade-off; mọi số từ kho thật)
   │
   ├─► Khách hỏi chi tiết "mẫu 1 bảo hành sao?" → trả lời từ dữ liệu sản phẩm
   ├─► Khách hỏi "chính sách đổi trả thế nào?" → RAG chính sách + trích nguồn
   ├─► Khách chốt mẫu → hỏi tỉnh/thành → kiểm tra giao lắp/tồn kho khu vực
   └─► Khách hỏi model lạ không có trong kho → tra web + gợi ý mẫu tương đương
```

---

## 3. Sáu tình huống nghiệp vụ trợ lý xử lý được

| # | Tình huống khách | Trợ lý làm gì |
|---|------------------|---------------|
| 1 | **Nhu cầu mơ hồ** ("anh muốn mua máy lạnh") | Không tư vấn bừa — **hỏi ngược** câu quan trọng nhất trước |
| 2 | **Nhu cầu rõ, nhiều mẫu khớp** | Lọc kho → hỏi thêm để thu hẹp → **so sánh top 3 + trade-off** |
| 3 | **Hỏi chi tiết / bảo hành 1 mẫu** đã gợi ý | Trả lời từ **dữ liệu sản phẩm thật**, không nhầm sang chính sách chung |
| 4 | **Hỏi chính sách** (đổi trả, giao hàng, khui hộp…) | **RAG grounded** + trích nguồn; không có thông tin → **thú nhận** |
| 5 | **Hỏi sản phẩm lạ / ngoài kho** | Tra web → tra lại kho → **gợi ý mẫu tương đương** hoặc chốt trung thực |
| 6 | **Lạc đề / chào hỏi / phó mặc "sao cũng được"** | Đón tiếp lịch sự, kéo về nhu cầu; không hỏi mãi, không "chưa hỗ trợ được" máy móc |

---

## 4. Bốn "luật vàng" nghiệp vụ (khác biệt cạnh tranh)

1. **Hỏi ít nhưng đúng.** Mỗi câu hỏi phải **thu hẹp lựa chọn nhiều nhất** trên công sức khách bỏ ra (thuật toán
   Decision-Gap). Không hỏi cho có.
2. **Nói tiếng của khách.** Diễn giải bằng lợi ích thực tế ("chạy êm cho phòng ngủ", "hóa đơn điện thấp hơn"),
   **không** ném thuật ngữ marketing/kỹ thuật vào mặt khách phổ thông.
3. **Thà nói "chưa có thông tin" còn hơn bịa.** Không bịa giá / tồn kho / khuyến mãi / % tiết kiệm / tính năng.
   Mọi con số đều truy được về nguồn (catalog / chính sách).
4. **Luôn cho phổ lựa chọn.** Top 3 gồm *hợp nhất – rẻ hơn – cao cấp hơn* để khách tự cân nhắc, quyết nhanh hơn.

---

## 5. Vì sao khả thi & có tiềm năng thương mại

- **Bám đúng dữ liệu doanh nghiệp:** cắm thẳng API catalog / giá / tồn kho / khuyến mãi + tài liệu chính sách nội
  bộ. Ontology đã phủ **16+ ngành hàng** điện máy, mở rộng ngành mới **có kiểm soát** (human review) không cần code lại.
- **Rẻ & an toàn để triển khai:** dùng **model open-weight**, chạy **on-premise** — doanh nghiệp Việt kiểm soát chi
  phí và dữ liệu khách, không khóa nhà cung cấp.
- **Đo được giá trị:** giảm tải nhân viên tư vấn, tăng trải nghiệm, **tăng tỉ lệ chuyển đổi** trên kênh online —
  có sẵn eval harness để chứng minh độ đúng thông tin & chống hallucination trước khi ký pilot.
- **Nhanh trong ngưỡng đề bài:** hỏi ngược < 3s, so sánh top 3 < 5s (phần lọc/xếp hạng tất định, tối đa 2 LLM call/lượt).

---

## 6. Lộ trình mở rộng nghiệp vụ (roadmap)

- **Tìm sản phẩm theo ảnh:** khách chụp/gửi ảnh sản phẩm → nhận diện → gợi ý mẫu tương tự trong kho.
- **Gợi ý cá nhân hóa (Recommendation):** học từ feedback, rating, lịch sử để đề xuất hợp gu từng khách.
- **Mở rộng ngành hàng:** kích hoạt thêm category qua ontology thích ứng + review chuyên gia.

*(Hai mục đầu đang phát triển; kiến trúc hiện tại đã chừa sẵn điểm cắm — xem `TECHNIQUE_README.md` mục 12.)*
