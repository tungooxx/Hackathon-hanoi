"""Adapter cho model reasoning kiểu GLM — cấu trúc trả về KHÁC gpt-oss-120b.

GLM-5.2 là model reasoning. Hai điểm lệch so với gpt-oss-120b:

1. Structured output: `.with_structured_output(...)` mặc định (json_schema/response_format)
   thường trả `parsed=None` vì phần suy luận chèn trước JSON -> node NLU/judge fail.
   -> ép `method="function_calling"` + `include_raw=True`, và có nhánh dự phòng bóc JSON
   từ content (sau khi bỏ <think>) rồi validate lại bằng schema.

2. Suy luận: nằm ở `reasoning_content` (LangChain đẩy vào additional_kwargs) HOẶC bọc
   trong `<think>...</think>` ngay trong content. Nếu lọt ra khách -> lộ suy luận nội bộ.
   -> `strip_reasoning` (text tĩnh) và `ReasoningStreamFilter` (luồng stream).

Với provider KHÔNG reasoning (gpt-oss-120b) mọi hàm ở đây là no-op an toàn: không có
<think> để cắt, function_calling vốn đã tương thích, parsed luôn có nên không chạm fallback.
"""
import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_OPEN = "<think"
_OPEN_RE = re.compile(r"<think\b[^>]*>", re.IGNORECASE)
_CLOSE_RE = re.compile(r"</think\s*>", re.IGNORECASE)
_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str | None) -> str:
    """Bỏ block suy luận <think>...</think> khỏi văn bản tĩnh (hướng tới khách).

    An toàn với None/rỗng. Cắt cặp thẻ hoàn chỉnh; nếu chỉ có <think> mở mà chưa
    đóng thì cắt từ đó tới hết (phòng trường hợp GLM quên đóng thẻ).
    """
    if not text:
        return ""
    cleaned = _THINK_BLOCK_RE.sub("", text)
    low = cleaned.lower()
    open_idx = low.rfind(_OPEN)
    if open_idx != -1 and "</think" not in low[open_idx:]:
        cleaned = cleaned[:open_idx]
    return cleaned.strip()


def extract_json_object(text: str) -> dict | None:
    """Bóc object JSON đầu tiên trong text (quét ngoặc cân bằng, tôn trọng chuỗi)."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break  # object hỏng -> thử '{' kế tiếp
        start = text.find("{", start + 1)
    return None


async def astructured(base_llm, schema: type[T], messages, config=None) -> T:
    """Structured output chịu được model reasoning (GLM) lẫn model thường (gpt-oss).

    base_llm: ChatOpenAI CHƯA gắn structured output (hàm tự gắn function_calling).
    """
    structured = base_llm.with_structured_output(
        schema, method="function_calling", include_raw=True
    )
    result = await structured.ainvoke(messages, config=config)
    parsed = result.get("parsed") if isinstance(result, dict) else result
    if parsed is not None:
        return parsed
    raw = result.get("raw") if isinstance(result, dict) else None
    content = getattr(raw, "content", "") if raw is not None else ""
    if isinstance(content, list):  # một số provider trả content dạng block list
        content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    data = extract_json_object(strip_reasoning(content))
    if data is not None:
        try:
            return schema.model_validate(data)
        except ValidationError:
            pass
    raise ValueError(
        f"{schema.__name__}: model không trả structured output hợp lệ "
        "(parsed=None và không bóc được JSON từ content)"
    )


def _held_prefix_len(buf: str) -> int:
    """Số ký tự đuôi cần giữ lại vì có thể là phần đầu của '<think' bị cắt giữa chunk."""
    for k in range(min(len(_OPEN), len(buf)), 0, -1):
        if buf[-k:].lower() == _OPEN[:k]:
            return k
    return 0


class ReasoningStreamFilter:
    """Lọc <think>...</think> khỏi luồng token, an toàn khi thẻ bị cắt giữa chunk.

    Nếu provider đẩy reasoning ra field riêng (không dùng <think> trong content) thì
    đây là no-op: mọi ký tự đi thẳng ra ngoài.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    def feed(self, text: str) -> str:
        if not text:
            return ""
        self._buf += text
        out: list[str] = []
        while True:
            if self._in_think:
                m = _CLOSE_RE.search(self._buf)
                if not m:
                    # chưa thấy thẻ đóng: bỏ reasoning, chỉ giữ đuôi ngắn phòng '</think>' bị cắt
                    self._buf = self._buf[-12:] if len(self._buf) > 12 else self._buf
                    break
                self._buf = self._buf[m.end():]
                self._in_think = False
            else:
                m = _OPEN_RE.search(self._buf)
                if m:
                    out.append(self._buf[: m.start()])
                    self._buf = self._buf[m.end():]
                    self._in_think = True
                    continue
                held = _held_prefix_len(self._buf)
                safe = len(self._buf) - held
                out.append(self._buf[:safe])
                self._buf = self._buf[safe:]
                break
        return "".join(out)

    def flush(self) -> str:
        """Cuối stream: đẩy nốt phần an toàn còn lại (bỏ nếu đang trong think dở)."""
        if self._in_think:
            self._buf = ""
            return ""
        out, self._buf = self._buf, ""
        return out
