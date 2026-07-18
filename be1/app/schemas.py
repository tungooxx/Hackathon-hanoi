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
    budget_min: Optional[float] = Field(None, description="Ngân sách tối thiểu, đơn vị VND")
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

    ontology_answers: dict[str, Any] = Field(default_factory=dict)
    active_answer_filter: bool | None = Field(
        None, description="Active answer selects an eligible catalog value/range"
    )
    active_answer_preference: Literal["higher", "lower"] | None = Field(
        None, description="Optional soft preference for the active numeric/ordered catalog field"
    )
    active_answer_numeric_value: float | None = Field(
        None, description="Numeric answer converted to the active catalog field's stated unit"
    )
    active_answer_boolean_value: bool | None = Field(
        None, description="Language-independent true/false meaning of an answer to an active boolean question"
    )
    active_answer_skip: bool = Field(False, description="Customer has no preference for the active question")
    active_answer_clarify: bool = Field(False, description="Customer reply is incomplete/ambiguous")
    active_question_override: bool = Field(
        False,
        description="Customer explicitly abandons the active question to change product category or ask policy",
    )

    def slot_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in {
                "budget_max": self.budget_max,
                "budget_min": self.budget_min,
                "area_m2": self.area_m2,
                "brand": self.brand,
                "afternoon_sun": self.afternoon_sun,
                "room_type": self.room_type,
                "province": self.province,
                "needs_heating": self.needs_heating,
                "iron_portable": self.iron_portable,
            }.items()
            # Structured-output providers commonly emit an empty string for
            # an unknown optional field. That is absence, not an executable
            # catalog constraint (and must never appear in the customer funnel).
            if v is not None and not (isinstance(v, str) and not v.strip())
        }


class WebSpec(BaseModel):
    """Thông số 1 sản phẩm lạ trích từ web (LLM call trong fetch_product_specs).

    CHỈ dùng field vô hướng — tránh dict tự do vì nhiều provider OpenAI-compatible không
    điền được object additionalProperties ở chế độ structured output. catalog_slots được
    dựng lại trong code từ các field này (xem to_payload).
    """

    product_name: str
    found: bool = True
    category: Optional[Category] = Field(
        None, description="Loại SP chuẩn của catalog nếu suy ra được: may_lanh, tu_lanh, may_giat"
    )
    brand: Optional[str] = None
    budget_max: Optional[float] = Field(None, description="Giá tham khảo trên web, đơn vị VND")
    area_m2: Optional[float] = Field(None, description="Diện tích phòng phù hợp (m²) suy từ công suất")
    needs_heating: Optional[bool] = Field(None, description="True nếu là máy 2 chiều (có sưởi)")
    key_specs: str = Field("", description="Các thông số chính, mô tả ngắn gọn dạng văn bản")
    summary: str = Field("", description="Tóm tắt 1-2 câu về sản phẩm cho khách")

    def to_payload(self) -> dict[str, Any]:
        """Chuẩn hoá về dict các node dùng, kèm catalog_slots dựng từ field vô hướng."""
        slots: dict[str, Any] = {}
        if self.budget_max is not None:
            slots["budget_max"] = self.budget_max
        if self.area_m2 is not None:
            slots["area_m2"] = self.area_m2
        if self.brand:
            slots["brand"] = self.brand
        if self.needs_heating is not None:
            slots["needs_heating"] = self.needs_heating
        return {
            "product_name": self.product_name, "found": self.found, "category": self.category,
            "brand": self.brand, "catalog_slots": slots,
            "key_specs": self.key_specs, "summary": self.summary,
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
    question_type: str = ""
    possible_answers: str = ""
    value_map: dict[str, list[str]] = Field(default_factory=dict)
    # These are produced from catalog evidence by the runtime-profile
    # compiler.  They are not a per-category rule table.
    operation: str = "equals"
    ordered_values: list[str] = Field(default_factory=list)
    unit: str = ""
    customer_effort: float = 1.0
    boolean_true_values: list[str] = Field(default_factory=list)
    boolean_false_values: list[str] = Field(default_factory=list)


class NextQuestion(BaseModel):
    slot: str
    reason: str                 # cho explainability panel


class SessionContentResult(BaseModel):
    """Structured output from the session-history compression agent."""

    session_content: str = Field(
        min_length=1,
        description="Cumulative conversation context formatted as Markdown",
    )
