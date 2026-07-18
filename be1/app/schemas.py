from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Priority = Literal["tiet_kiem_dien", "it_on", "gia_re"]
Category = str


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
    afternoon_sun: Optional[Literal["low", "medium", "high"]] = None
    room_type: Optional[Literal["bedroom", "living_room", "office", "other"]] = None
    priorities: list[Priority] = Field(
        default_factory=list, description="Ưu tiên khách nhắc, theo thứ tự nhắc trước->sau"
    )
    product_mentions: list[str] = Field(
        default_factory=list,
        description="Tên/mã sản phẩm khách gõ, CHÉP NGUYÊN VĂN kể cả sai chính tả",
    )
    selected_index: Optional[int] = Field(
        None, ge=1, le=3,
        description="Số thứ tự sản phẩm khách chọn từ danh sách vừa hiển thị, ví dụ 'loại 1' -> 1",
    )
    wants_product_details: bool = Field(
        False,
        description="Khách muốn xem thông tin đầy đủ/chi tiết của sản phẩm đã chọn",
    )
    price_order: Optional[Literal["lowest", "highest"]] = Field(
        None,
        description="Khach hoi mau re nhat/gia thap nhat (lowest) hoac dat nhat/gia cao nhat (highest) trong danh sach dang loc",
    )
    province: Optional[str] = Field(
        None,
        description="Tỉnh hoặc thành phố khách nêu để kiểm tra hàng trong bản demo",
    )
    province_candidates: list[str] = Field(
        default_factory=list,
        description="Các tỉnh/thành cần làm rõ khi khách dùng viết tắt mơ hồ, ví dụ QN",
    )
    needs_heating: Optional[bool] = Field(None, description="Khách có cần máy sưởi ấm vào mùa lạnh không")
    iron_portable: Optional[bool] = Field(None, description="Khách ưu tiên bàn ủi nhỏ gọn để mang đi")

    def slot_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in {
                "budget_max": self.budget_max,
                "area_m2": self.area_m2,
                "brand": self.brand,
                "afternoon_sun": self.afternoon_sun,
                "room_type": self.room_type,
                "province": self.province,
                "needs_heating": self.needs_heating,
                "iron_portable": self.iron_portable,
            }.items()
            if v is not None
        }


# ---- Interface với Tùng (ontology) — BE1 chỉ gọi 2 hàm theo shape này ----

class SlotDef(BaseModel):
    name: str
    maps_to_field: str          # field trong product JSON đã normalize
    slot_type: Literal["hard", "soft"]
    required: bool
    ask_hint: str
    question_type: str = ""
    possible_answers: str = ""


class NextQuestion(BaseModel):
    slot: str
    reason: str                 # cho explainability panel
