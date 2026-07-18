from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Priority = Literal["tiet_kiem_dien", "it_on", "gia_re"]
Category = Literal["may_lanh", "tu_lanh", "may_giat", "khac"]


class IntentResult(BaseModel):
    """Output của LLM call #1 — gộp intent + slot extraction + routing."""

    intent_type: Literal["new_topic", "same_topic", "off_topic", "force_answer", "policy"] = Field(
        description="new_topic: hỏi category mới; same_topic: bổ sung thông tin; "
        "off_topic: không liên quan mua sắm điện máy; "
        "force_answer: khách muốn được tư vấn/chốt ngay không trả lời thêm; "
        "policy: hỏi về chính sách/quy định cửa hàng (bảo hành, đổi trả, hoàn tiền, "
        "giao hàng, lắp đặt, khui hộp, điều khoản, dữ liệu cá nhân, nội quy)"
    )
    category: Optional[Category] = None
    budget_max: Optional[float] = Field(None, description="Ngân sách tối đa, đơn vị VND")
    area_m2: Optional[float] = Field(None, description="Diện tích phòng (m²)")
    brand: Optional[str] = Field(None, description="Thương hiệu khách nhắc đến, đã sửa chính tả")
    priorities: list[Priority] = Field(
        default_factory=list, description="Ưu tiên khách nhắc, theo thứ tự nhắc trước->sau"
    )
    product_mentions: list[str] = Field(
        default_factory=list,
        description="Tên/mã sản phẩm khách gõ, CHÉP NGUYÊN VĂN kể cả sai chính tả",
    )

    def slot_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in {
                "budget_max": self.budget_max,
                "area_m2": self.area_m2,
                "brand": self.brand,
            }.items()
            if v is not None
        }


class ChatRequest(BaseModel):
    session_id: str
    message: str


# ---- Interface với Tùng (ontology) — BE1 chỉ gọi 2 hàm theo shape này ----

class SlotDef(BaseModel):
    name: str
    maps_to_field: str          # field trong product JSON đã normalize
    slot_type: Literal["hard", "soft"]
    required: bool
    ask_hint: str


class NextQuestion(BaseModel):
    slot: str
    reason: str                 # cho explainability panel
