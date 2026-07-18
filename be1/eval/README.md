# Eval — đánh giá độ thông minh của agent tư vấn điện máy

## 2 bộ kịch bản

| File | Mục đích |
|---|---|
| `scenarios.jsonl` | Bộ core: routing + regression chống hallucination (chạy bằng `scripts/eval_run.py`) |
| `persona_scenarios.jsonl` | Bộ persona: giả lập 18 kiểu khách thật, multi-turn (chạy bằng `scripts/eval_personas.py`) |

## Bộ persona phủ những kiểu khách nào

- **Non-tech**: bà lớn tuổi mô tả bằng công dụng ("tủ để đồ ăn khỏi thiu"), chú lớn tuổi mua điện thoại "chữ to dễ xài"
- **High-tech**: gamer hỏi RTX/144Hz, chuyên gia điện lạnh hỏi CSPF/gas R32 (bẫy null-honesty)
- **Con gái teen**: teen-speak + emoji ("mún", "hông", 🥺), hỏi màu sắc
- **Trẻ em**: hỏi ngây ngô, đồ chơi ngoài danh mục, để dành 200k
- **Đời thường khó nhằn**: gõ không dấu + viết tắt, phủ định kép ("đừng đắt quá mà đừng rẻ quá"), đổi ý trong 1 câu, mix Anh-Việt
- **Tình huống**: mẹ bận rộn đổi chủ đề rồi quay lại (context switch), khách giận khiếu nại (policy + đồng cảm), mặc cả xin giảm giá, phân vân bắt chốt hộ, mua quà chưa biết mua gì, sinh viên 2 nhu cầu 1 câu, hỏi sản phẩm không có trong kho (enrich)

Mỗi turn có field `check` — mô tả hành vi đúng để judge chấm.

## Chạy

```bash
# cần backend đang chạy (mặc định http://127.0.0.1:8000, đổi bằng --base hoặc BE1_BASE_URL)
python scripts/eval_personas.py --base http://127.0.0.1:8100

python scripts/eval_personas.py --only p05,p08      # chỉ chạy vài kịch bản
python scripts/eval_personas.py --include-core       # chạy kèm bộ core scenarios.jsonl
python scripts/eval_personas.py --judge              # + chấm hallucination (cần JUDGE_API_KEY/LLM_API_KEY)
```

## Output & cách chấm chất lượng

1. **stdout**: transcript trực tiếp — khách nói gì, agent trả lời gì, turn_type, latency, routing ok/FAIL.
2. **`logs/eval_transcript_<tag>.md`**: transcript đầy đủ **kèm rubric chấm điểm ở đầu file**. Chấm bằng 1 trong 2 cách:
   - **LLM ngoài**: gửi nguyên file cho model qua API key của bạn (file tự chứa hướng dẫn chấm).
   - **Claude Code**: mở session và nói *"đọc logs/eval_transcript_<tag>.md và chấm theo rubric trong file"*.
3. **`logs/eval_personas_<tag>.json`**: report máy đọc được (pass/fail routing từng turn) — dùng để diff giữa các lần sửa agent.
4. `--judge` dùng judge có sẵn (`app/judge.py`) chấm hallucination từng claim so với context bot thực sự nhìn thấy.

## Thêm kịch bản mới

Thêm object vào `persona_scenarios.jsonl` (JSONL hoặc JSON pretty-print nối tiếp đều đọc được):

```json
{"id": "p19_...", "persona": "...", "desc": "điều muốn kiểm tra",
 "turns": [{"user": "câu khách nói", "expect_turn_type": ["ask", "compare"],
            "check": "hành vi đúng mà judge cần đối chiếu"}]}
```

`expect_turn_type` viết LỎNG (các nhánh chấp nhận được: `ask/compare/no_match/detail/price_answer/policy/off_topic/enrich/enrich_ask/clarify_category/fulfillment_prompt/fulfillment_check/fulfillment_clarify/catalog_unavailable`) — routing sai nhánh mới tính FAIL; chất lượng câu chữ để judge chấm. Khi bắt được một hội thoại agent trả lời sai ngoài thực tế, dùng skill `/eval-case` để chuyển thành regression case trong `scenarios.jsonl`.
