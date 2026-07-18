---
name: eval-case
description: Paste một đoạn hội thoại mà agent trả lời SAI -> chuyển thành 1 test case (scenario) và ghi vào luồng eval (be1/eval/scenarios.jsonl). Dùng khi user muốn "bắt" một lỗi vừa thấy để không tái phát.
trigger: /eval-case
---

# /eval-case

Biến một đoạn hội thoại lỗi (agent bịa / sai) thành một **regression scenario** trong luồng eval hallucination của repo.

## Khi nào dùng
User gọi `/eval-case` rồi paste đoạn chat (câu khách hỏi + câu bot trả lời sai). Nhiệm vụ của bạn: đọc, rút ra pattern lỗi, viết thành 1 dòng scenario JSONL và append vào file.

## File đích
`be1/eval/scenarios.jsonl` — mỗi dòng là 1 scenario JSON:

```json
{"id": "sNN_slug", "desc": "...", "turns": [{"user": "câu khách hỏi", "expect_turn_type": ["ask"]}]}
```

## Bối cảnh luồng eval (bắt buộc hiểu trước khi viết)
- `eval_run.py` chạy từng `turns[].user` qua HTTP `/chat` thật, **chỉ assert `turn_type`** (tầng cứng). Chất lượng nội dung (hallucination) do **judge** (`app/judge.py`) chấm khi chạy `--judge` (tầng mềm).
- `turn_type` hợp lệ: `ask` (hỏi ngược làm rõ), `compare` (đưa ra so sánh sản phẩm), `no_match` (không có sản phẩm phù hợp / sai category), `off_topic` (lạc đề).
- Vì output LLM không cố định, **`expect_turn_type` phải để LỎNG** (list các turn_type chấp nhận được) để không false-fail. KHÔNG assert cứng vào text.
- Data hiện chỉ có category `may_lanh`. Hỏi tủ lạnh/tivi... -> đúng phải `no_match`.
- Judge bắt: `UNSUPPORTED` (bịa số/thông số không có trong context), `CONTRADICTED` (sai số / lệch funnel), và `null_honesty` (field null mà bot bịa thay vì nói "chưa có thông tin").

## Các bước

1. **Đọc đoạn user paste.** Tách ra: (a) (các) câu khách hỏi theo thứ tự, (b) câu bot trả lời sai, (c) *tại sao* sai. Nếu hội thoại nhiều lượt, giữ đúng thứ tự thành mảng `turns` — lỗi thường chỉ xuất hiện ở lượt cuối, nhưng các lượt trước là ngữ cảnh cần thiết để tái hiện.

2. **Xác định pattern lỗi** và judge nên bắt gì. Ví dụ thường gặp trong repo này:
   - Bịa số lượng mẫu ("đang có 10 mẫu") khi chưa lọc -> UNSUPPORTED.
   - "Em chốt 3 lựa chọn" khi funnel < 3 -> CONTRADICTED.
   - Bịa wifi/bảo hành/chuẩn sao/độ bền (field không có trong data) -> UNSUPPORTED hoặc vi phạm null_honesty.
   - Tính sai chênh giá -> CONTRADICTED.
   - Bịa "tiết kiệm hơn X%" không có trong context -> UNSUPPORTED.

3. **Chọn `expect_turn_type`** = hành vi ĐÚNG mà bot nên có ở mỗi lượt. Để lỏng (thường 2-3 giá trị). Nếu không chắc, thêm cả `ask`.

4. **Sinh `id`** duy nhất: `sNN_slug`.
   - `NN` = số thứ tự kế tiếp. Lấy số lớn nhất hiện có rồi +1:
     ```bash
     grep -oE '"id": "s[0-9]+' be1/eval/scenarios.jsonl | grep -oE '[0-9]+' | sort -n | tail -1
     ```
   - `slug` = kebab tiếng Việt không dấu mô tả lỗi, vd `s19_bia_cong_suat`.

5. **Viết `desc`** ngắn gọn, nêu rõ: đây là REGRESSION (hoặc NULL-HONESTY), lỗi gì, judge phải bắt verdict nào. Đây là phần cho người đọc report hiểu case canh cái gì.

6. **Append 1 dòng** vào `be1/eval/scenarios.jsonl` (JSON 1 dòng, `ensure_ascii=false` — giữ tiếng Việt có dấu, KHÔNG escape unicode). Đảm bảo file có newline cuối trước khi append.

7. **Validate** ngay:
   ```bash
   python3 -c "import json;[json.loads(l) for l in open('be1/eval/scenarios.jsonl') if l.strip()];print('OK')"
   ```

8. **Báo lại** cho user: id vừa thêm, `desc`, và verdict mà judge nên bắt. Gợi ý chạy:
   ```bash
   cd be1 && python scripts/eval_run.py --judge   # cần server đang chạy
   ```

## Nguyên tắc
- KHÔNG bịa câu hỏi khách — dùng đúng câu user paste. Chỉ được chuẩn hóa nhẹ (bỏ tên riêng, cắt phần thừa).
- KHÔNG assert cứng vào text bot trả lời. Lỗi nội dung để judge chấm; scenario chỉ tái hiện tình huống + chốt `turn_type` đúng.
- Một đoạn hội thoại -> một scenario. Nếu user paste nhiều lỗi rời rạc, tạo nhiều dòng, mỗi lỗi một `id`.
- Nếu đoạn paste không đủ để suy ra câu khách hỏi hoặc turn_type kỳ vọng, HỎI LẠI user trước khi ghi.
