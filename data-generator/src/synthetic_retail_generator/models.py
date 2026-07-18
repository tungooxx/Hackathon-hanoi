"""Strict Pydantic models for the product catalog."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

FiniteNumber: TypeAlias = Annotated[
    float,
    Field(allow_inf_nan=False),
]


class ProductModel(BaseModel):
    """Shared strict validation for every product category."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )


class TuLanhProduct(ProductModel):
    """Tủ Lạnh (tu_lanh)."""

    model_config = ConfigDict(title="Tủ Lạnh")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand_id: Annotated[StrictStr, Field(title="brand_id")]
    brand: Annotated[StrictStr, Field(title="brand")]
    kieu_dang: Annotated[StrictStr, Field(title="Kiểu dáng")]
    cong_nghe_lam_lanh: Annotated[StrictStr, Field(title="Công nghệ làm lạnh")]
    san_xuat_tai: Annotated[StrictStr, Field(title="Sản xuất tại")]
    thoi_gian_ra_mat: Annotated[StrictInt, Field(title="Thời gian ra mắt")]
    chat_lieu_khay_ngan_lanh: Annotated[StrictStr, Field(title="Chất liệu khay ngăn lạnh")]
    dung_tich_tong: Annotated[StrictStr, Field(title="Dung tích tổng")]
    dung_tich_ngan_da: Annotated[StrictStr, Field(title="Dung tích ngăn đá")]
    dung_tich_ngan_lanh: Annotated[StrictStr, Field(title="Dung tích ngăn lạnh")]
    dien_nang_tieu_thu: Annotated[StrictInt, Field(title="Điện năng tiêu thụ")]
    chat_lieu_than_vo: Annotated[StrictStr, Field(title="Chất liệu thân vỏ")]
    so_nguoi_su_dung: Annotated[StrictStr, Field(title="Số người sử dụng")]
    dung_tich_su_dung: Annotated[StrictStr, Field(title="Dung tích sử dụng")]
    cong_nghe_tiet_kiem_dien: Annotated[StrictStr, Field(title="Công nghệ tiết kiệm điện")]
    cong_nghe_bao_quan_thuc_pham: Annotated[StrictStr, Field(title="Công nghệ bảo quản thực phẩm")]
    tien_ich: Annotated[StrictStr, Field(title="Tiện ích")]
    chat_lieu_dong_co: Annotated[StrictStr, Field(title="Chất liệu động cơ")]
    dung_tich_ngan_chuyen_doi: Annotated[StrictStr, Field(title="Dung tích ngăn chuyển đổi")]
    so_cua: Annotated[StrictStr, Field(title="Số cửa")]
    cao: Annotated[StrictInt, Field(title="Cao")]
    ngang: Annotated[StrictInt, Field(title="Ngang")]
    sau: Annotated[StrictInt, Field(title="Sâu")]
    khoi_luong_may: Annotated[StrictInt, Field(title="Khối lượng máy")]
    lay_nuoc_ngoai: Annotated[StrictStr, Field(title="Lấy nước ngoài")]
    che_do_tu_dong: Annotated[StrictStr, Field(title="Chế độ tự động")]
    gia_goc: Annotated[StrictInt, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr, Field(title="khuyến mãi quà")]


class MayLanhProduct(ProductModel):
    """Máy lạnh (may_lanh)."""

    model_config = ConfigDict(title="Máy lạnh")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand_id: Annotated[StrictStr, Field(title="brand_id")]
    brand: Annotated[StrictStr, Field(title="brand")]
    cong_nghe_lam_lanh: Annotated[StrictStr, Field(title="Công nghệ làm lạnh")]
    san_xuat_tai: Annotated[StrictStr, Field(title="Sản xuất tại")]
    dien_nang_tieu_thu: Annotated[StrictInt, Field(title="Điện năng tiêu thụ")]
    cong_nghe_tiet_kiem_dien: Annotated[StrictStr, Field(title="Công nghệ tiết kiệm điện")]
    tien_ich: Annotated[StrictStr, Field(title="Tiện ích")]
    khoi_luong_may: Annotated[StrictStr | None, Field(title="Khối lượng máy")]
    bao_hanh_bo_phan: Annotated[StrictStr, Field(title="Bảo hành bộ phận")]
    loai_may: Annotated[StrictStr, Field(title="Loại máy")]
    cong_suat_dau_ra: Annotated[StrictStr | None, Field(title="Công suất đầu ra")]
    nhan_nang_luong: Annotated[StrictStr, Field(title="Nhãn năng lượng")]
    dai_ong_dong: Annotated[StrictStr, Field(title="Dài ống đồng")]
    cao_lap_dat: Annotated[StrictStr, Field(title="Cao lắp đặt")]
    chat_lieu_dan_tan_nhiet: Annotated[StrictStr, Field(title="Chất liệu dàn tản nhiệt")]
    do_on: Annotated[StrictStr, Field(title="Độ ồn")]
    dong_dien_vao: Annotated[StrictStr, Field(title="Dòng điện vào")]
    kich_thuoc_ong_dong: Annotated[StrictStr, Field(title="Kích thước ống đồng")]
    so_luong: Annotated[StrictStr, Field(title="Số lượng")]
    dai_phu_kien_chinh: Annotated[StrictInt, Field(title="Dài phụ kiện chính")]
    do_day_phu_kien_chinh: Annotated[StrictInt, Field(title="Độ dày phụ kiện chính")]
    khoi_luong_phu_kien_chinh: Annotated[StrictInt, Field(title="Khối lượng phụ kiện chính")]
    cao_phu_kien_phu: Annotated[StrictInt, Field(title="Cao phụ kiện phụ")]
    dai_phu_kien_phu: Annotated[StrictInt, Field(title="Dài phụ kiện phụ")]
    do_day_phu_kien_phu: Annotated[StrictInt, Field(title="Độ dày phụ kiện phụ")]
    khoi_luong_phu_kien_phu: Annotated[StrictInt, Field(title="Khối lượng phụ kiện phụ")]
    dong_dien_hoat_dong: Annotated[StrictStr, Field(title="Dòng điện hoạt động")]
    chuan_chong_nuoc_bui: Annotated[StrictStr, Field(title="Chuẩn chống nước, bụi")]
    loai_inverter: Annotated[StrictStr, Field(title="Loại Inverter")]
    che_do_gio: Annotated[StrictStr, Field(title="Chế độ gió")]
    dong_san_pham: Annotated[StrictInt, Field(title="Dòng sản phẩm")]
    pham_vi_su_dung: Annotated[StrictStr, Field(title="Phạm vi sử dụng")]
    loai_gas: Annotated[StrictStr, Field(title="Loại Gas")]
    bao_hanh_dong_co: Annotated[StrictStr, Field(title="Bảo hành động cơ")]
    cao_phu_kien_chinh: Annotated[StrictInt, Field(title="Cao phụ kiện chính")]
    cao_phu_kien_chinh_2: Annotated[StrictStr | None, Field(title="Cao phụ kiện chính 2")]
    dai_phu_kien_chinh_2: Annotated[StrictStr | None, Field(title="Dài phụ kiện chính 2")]
    do_day_phu_kien_chinh_2: Annotated[StrictStr | None, Field(title="Độ dày phụ kiện chính 2")]
    gia_goc: Annotated[StrictInt, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr, Field(title="khuyến mãi quà")]


class MayGiatProduct(ProductModel):
    """Máy giặt (may_giat)."""

    model_config = ConfigDict(title="Máy giặt")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand_id: Annotated[StrictStr, Field(title="brand_id")]
    brand: Annotated[StrictStr, Field(title="brand")]
    san_xuat_tai: Annotated[StrictStr | None, Field(title="Sản xuất tại")]
    thoi_gian_ra_mat: Annotated[StrictStr | None, Field(title="Thời gian ra mắt")]
    dien_nang_tieu_thu: Annotated[StrictStr | None, Field(title="Điện năng tiêu thụ")]
    chat_lieu_than_vo: Annotated[StrictStr | None, Field(title="Chất liệu thân vỏ")]
    so_nguoi_su_dung: Annotated[StrictStr | None, Field(title="Số người sử dụng")]
    tien_ich: Annotated[StrictStr | None, Field(title="Tiện ích")]
    cao: Annotated[StrictStr | None, Field(title="Cao")]
    ngang: Annotated[StrictStr | None, Field(title="Ngang")]
    sau: Annotated[StrictStr | None, Field(title="Sâu")]
    khoi_luong_may: Annotated[StrictStr | None, Field(title="Khối lượng máy")]
    so_luong: Annotated[StrictStr | None, Field(title="Số lượng")]
    loai_inverter: Annotated[StrictStr | None, Field(title="Loại Inverter")]
    bao_hanh_dong_co: Annotated[StrictStr | None, Field(title="Bảo hành động cơ")]
    loai_san_pham: Annotated[StrictStr | None, Field(title="Loại sản phẩm")]
    bang_dieu_khien: Annotated[StrictStr | None, Field(title="Bảng điều khiển")]
    chat_lieu_mat: Annotated[StrictStr | None, Field(title="Chất liệu mặt")]
    long_giat: Annotated[StrictStr | None, Field(title="Lồng giặt")]
    khoi_luong_tai_chinh: Annotated[StrictStr | None, Field(title="Khối lượng tải chính")]
    cong_nghe: Annotated[StrictStr | None, Field(title="Công nghệ")]
    chat_lieu_ruot: Annotated[StrictStr | None, Field(title="Chất liệu ruột")]
    toc_do_quay_vat_toi_da: Annotated[StrictStr | None, Field(title="Tốc độ quay vắt tối đa")]
    dong_co: Annotated[StrictStr | None, Field(title="Động cơ")]
    cong_nghe_say: Annotated[StrictStr | None, Field(title="Công nghệ sấy")]
    chuong_trinh: Annotated[StrictStr | None, Field(title="Chương trình")]
    dai_ong_cap_nuoc: Annotated[StrictStr | None, Field(title="Dài ống cấp nước")]
    dai_ong_xa_nuoc: Annotated[StrictStr | None, Field(title="Dài ống xả nước")]
    gia_goc: Annotated[StrictInt | None, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr | None, Field(title="khuyến mãi quà")]


class MaySayQuanAoProduct(ProductModel):
    """Máy sấy quần áo (may_say_quan_ao)."""

    model_config = ConfigDict(title="Máy sấy quần áo")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand_id: Annotated[StrictStr, Field(title="brand_id")]
    brand: Annotated[StrictStr, Field(title="brand")]
    san_xuat_tai: Annotated[StrictStr, Field(title="Sản xuất tại")]
    dien_nang_tieu_thu: Annotated[StrictStr, Field(title="Điện năng tiêu thụ")]
    chat_lieu_than_vo: Annotated[StrictStr | None, Field(title="Chất liệu thân vỏ")]
    so_nguoi_su_dung: Annotated[StrictStr, Field(title="Số người sử dụng")]
    cong_nghe_tiet_kiem_dien: Annotated[StrictStr | None, Field(title="Công nghệ tiết kiệm điện")]
    tien_ich: Annotated[StrictStr, Field(title="Tiện ích")]
    cao: Annotated[StrictInt, Field(title="Cao")]
    ngang: Annotated[StrictInt, Field(title="Ngang")]
    sau: Annotated[StrictInt, Field(title="Sâu")]
    khoi_luong_may: Annotated[StrictInt, Field(title="Khối lượng máy")]
    dong_san_pham: Annotated[StrictInt, Field(title="Dòng sản phẩm")]
    loai_san_pham: Annotated[StrictStr, Field(title="Loại sản phẩm")]
    bang_dieu_khien: Annotated[StrictStr, Field(title="Bảng điều khiển")]
    khoi_luong_tai_chinh: Annotated[StrictInt | StrictStr, Field(title="Khối lượng tải chính")]
    cong_nghe: Annotated[StrictStr | None, Field(title="Công nghệ")]
    chat_lieu_ruot: Annotated[StrictStr, Field(title="Chất liệu ruột")]
    dong_co: Annotated[StrictStr, Field(title="Động cơ")]
    dai_ong_xa_nuoc: Annotated[StrictInt | StrictStr | None, Field(title="Dài ống xả nước")]
    nhiet_do_toi_da: Annotated[StrictStr, Field(title="Nhiệt độ tối đa")]
    dai_ong_thoat_khi: Annotated[StrictInt | None, Field(title="Dài ống thoát khí")]
    chat_lieu_cua: Annotated[StrictStr | None, Field(title="Chất liệu cửa")]
    cam_bien: Annotated[StrictStr | None, Field(title="Cảm biến")]
    gia_goc: Annotated[StrictInt | None, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr | None, Field(title="khuyến mãi quà")]


class MayRuaChenProduct(ProductModel):
    """Máy rửa chén (may_rua_chen)."""

    model_config = ConfigDict(title="Máy rửa chén")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand_id: Annotated[StrictStr, Field(title="brand_id")]
    brand: Annotated[StrictStr, Field(title="brand")]
    san_xuat_tai: Annotated[StrictStr, Field(title="Sản xuất tại")]
    chat_lieu_than_vo: Annotated[StrictStr, Field(title="Chất liệu thân vỏ")]
    tien_ich: Annotated[StrictStr, Field(title="Tiện ích")]
    cao: Annotated[StrictInt, Field(title="Cao")]
    ngang: Annotated[StrictInt, Field(title="Ngang")]
    sau: Annotated[StrictInt, Field(title="Sâu")]
    khoi_luong_may: Annotated[StrictInt, Field(title="Khối lượng máy")]
    cong_suat_dau_ra: Annotated[StrictStr, Field(title="Công suất đầu ra")]
    do_on: Annotated[StrictStr, Field(title="Độ ồn")]
    so_luong: Annotated[StrictStr, Field(title="Số lượng")]
    dong_san_pham: Annotated[StrictInt, Field(title="Dòng sản phẩm")]
    loai_san_pham: Annotated[StrictStr, Field(title="Loại sản phẩm")]
    bang_dieu_khien: Annotated[StrictStr, Field(title="Bảng điều khiển")]
    cong_nghe: Annotated[StrictStr, Field(title="Công nghệ")]
    cong_nghe_say: Annotated[StrictStr, Field(title="Công nghệ sấy")]
    chuong_trinh: Annotated[StrictStr, Field(title="Chương trình")]
    dai_ong_cap_nuoc: Annotated[StrictInt, Field(title="Dài ống cấp nước")]
    dai_ong_xa_nuoc: Annotated[StrictInt, Field(title="Dài ống xả nước")]
    tieu_thu_nuoc: Annotated[StrictStr, Field(title="Tiêu thụ nước")]
    chat_lieu_cua: Annotated[StrictStr, Field(title="Chất liệu cửa")]
    khay_chen: Annotated[StrictStr, Field(title="Khay chén")]
    gia_goc: Annotated[StrictInt | None, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr, Field(title="khuyến mãi quà")]


class TuMatTuDongProduct(ProductModel):
    """Tủ mát, tủ đông (tu_mat_tu_dong)."""

    model_config = ConfigDict(title="Tủ mát, tủ đông")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand_id: Annotated[StrictStr, Field(title="brand_id")]
    brand: Annotated[StrictStr, Field(title="brand")]
    san_xuat_tai: Annotated[StrictStr, Field(title="Sản xuất tại")]
    thoi_gian_ra_mat: Annotated[StrictInt, Field(title="Thời gian ra mắt")]
    dung_tich_tong: Annotated[StrictStr | None, Field(title="Dung tích tổng")]
    dien_nang_tieu_thu: Annotated[StrictStr, Field(title="Điện năng tiêu thụ")]
    cong_nghe_tiet_kiem_dien: Annotated[StrictStr, Field(title="Công nghệ tiết kiệm điện")]
    tien_ich: Annotated[StrictStr, Field(title="Tiện ích")]
    chat_lieu_dong_co: Annotated[StrictStr, Field(title="Chất liệu động cơ")]
    so_cua: Annotated[StrictStr, Field(title="Số cửa")]
    cao: Annotated[StrictInt, Field(title="Cao")]
    ngang: Annotated[StrictInt, Field(title="Ngang")]
    sau: Annotated[StrictInt, Field(title="Sâu")]
    khoi_luong_may: Annotated[StrictInt, Field(title="Khối lượng máy")]
    do_on: Annotated[StrictStr, Field(title="Độ ồn")]
    loai_gas: Annotated[StrictStr, Field(title="Loại Gas")]
    loai_san_pham: Annotated[StrictStr, Field(title="Loại sản phẩm")]
    chat_lieu_mat: Annotated[StrictStr, Field(title="Chất liệu mặt")]
    cong_nghe: Annotated[StrictStr, Field(title="Công nghệ")]
    chat_lieu_ruot: Annotated[StrictStr, Field(title="Chất liệu ruột")]
    dung_tich_ngan_dong_mem: Annotated[StrictStr, Field(title="Dung tích ngăn đông mềm")]
    thuong_hieu_cua: Annotated[StrictStr, Field(title="Thương hiệu của")]
    so_ngan: Annotated[StrictStr, Field(title="Số ngăn")]
    nhiet_do_ngan_dong_do_c: Annotated[StrictStr, Field(title="Nhiệt độ ngăn đông (độ C)")]
    gia_goc: Annotated[StrictInt, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr, Field(title="khuyến mãi quà")]


class MayNuocNongProduct(ProductModel):
    """Máy nước nóng (may_nuoc_nong)."""

    model_config = ConfigDict(title="Máy nước nóng")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand_id: Annotated[StrictStr, Field(title="brand_id")]
    brand: Annotated[StrictStr, Field(title="brand")]
    san_xuat_tai: Annotated[StrictStr, Field(title="Sản xuất tại")]
    chat_lieu_than_vo: Annotated[StrictStr | None, Field(title="Chất liệu thân vỏ")]
    tien_ich: Annotated[StrictStr | None, Field(title="Tiện ích")]
    cao: Annotated[StrictInt, Field(title="Cao")]
    khoi_luong_may: Annotated[StrictInt, Field(title="Khối lượng máy")]
    loai_may: Annotated[StrictStr, Field(title="Loại máy")]
    cong_suat_dau_ra: Annotated[StrictStr, Field(title="Công suất đầu ra")]
    so_luong: Annotated[StrictStr, Field(title="Số lượng")]
    dong_san_pham: Annotated[StrictInt, Field(title="Dòng sản phẩm")]
    chat_lieu_ruot: Annotated[StrictStr, Field(title="Chất liệu ruột")]
    thuong_hieu_cua: Annotated[StrictStr, Field(title="Thương hiệu của")]
    tinh_nang_an_toan: Annotated[StrictStr, Field(title="Tính năng an toàn")]
    tuy_chinh_nhiet_do: Annotated[StrictStr, Field(title="Tùy chỉnh nhiệt độ")]
    ap_luc_nuoc_hoat_dong: Annotated[StrictStr, Field(title="Áp lực nước hoạt động")]
    thoi_gian_su_dung: Annotated[StrictStr, Field(title="Thời gian sử dụng")]
    nhiet_do_lam_nong_toi_da: Annotated[StrictStr, Field(title="Nhiệt độ làm nóng tối đa")]
    loai_tam_thu_nhiet: Annotated[StrictStr, Field(title="Loại tấm thu nhiệt")]
    thoi_gian_giu_nhiet: Annotated[StrictStr, Field(title="Thời gian giữ nhiệt")]
    dai_ong: Annotated[StrictStr, Field(title="Dài ống")]
    chat_lieu_khung_vien: Annotated[StrictStr, Field(title="Chất liệu khung viền")]
    chat_lieu_voi_sen: Annotated[StrictStr, Field(title="Chất liệu vòi sen")]
    chat_lieu_gia_do_voi_sen: Annotated[StrictStr, Field(title="Chất liệu giá đỡ vòi sen")]
    voi_sen: Annotated[StrictStr, Field(title="Vòi sen")]
    rong: Annotated[StrictInt, Field(title="Rộng")]
    dai: Annotated[StrictStr | None, Field(title="Dài")]
    day: Annotated[StrictInt, Field(title="Dày")]
    lop_cach_nhiet: Annotated[StrictStr, Field(title="Lớp cách nhiệt")]
    bom_tro_luc: Annotated[StrictStr, Field(title="Bơm trợ lực")]
    dung_luong_dung_tich: Annotated[StrictStr, Field(title="Dung lượng dung tích")]
    gia_goc: Annotated[StrictInt | None, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr, Field(title="khuyến mãi quà")]


class MicroKaraokeProduct(ProductModel):
    """Micro karaoke (micro_karaoke)."""

    model_config = ConfigDict(title="Micro karaoke")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr | None, Field(title="productidweb")]
    category_code: StrictStr
    brand_id: Annotated[StrictStr, Field(title="brand_id")]
    brand: Annotated[StrictStr, Field(title="brand")]
    san_xuat_tai: Annotated[StrictStr, Field(title="Sản xuất tại")]
    loai_san_pham: Annotated[StrictStr, Field(title="Loại sản phẩm")]
    tan_so_hoat_dong: Annotated[StrictStr, Field(title="Tần số hoạt động")]
    bang_tan: Annotated[StrictStr, Field(title="Băng tần")]
    do_meo_tieng: Annotated[StrictStr, Field(title="Độ méo tiếng")]
    nam_san_xuat: Annotated[StrictInt, Field(title="Năm sản xuất")]
    gia_goc: Annotated[StrictInt | None, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr | None, Field(title="khuyến mãi quà")]


class MicroThuAmDienThoaiProduct(ProductModel):
    """Micro thu âm điện thoại (micro_thu_am_dien_thoai)."""

    model_config = ConfigDict(title="Micro thu âm điện thoại")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand_id: Annotated[StrictStr, Field(title="brand_id")]
    brand: Annotated[StrictStr, Field(title="brand")]
    tinh_nang_co_ban: Annotated[StrictStr, Field(title="Tính năng cơ bản")]
    loai_pin_bo_phat: Annotated[StrictInt | StrictStr, Field(title="Loại pin bộ phát")]
    nhiet_do_hoat_dong_bo_phat: Annotated[StrictInt | StrictStr | None, Field(title="Nhiệt độ hoạt động bộ phát")]
    thoi_gian_hoat_dong_bo_thu: Annotated[StrictInt | None, Field(title="Thời gian hoạt động bộ thu")]
    dung_luong_pin_hop_sac: Annotated[StrictInt, Field(title="Dung lượng pin hộp sạc")]
    sac_day_bo_thu: Annotated[FiniteNumber | StrictStr, Field(title="Sạc đầy bộ thu")]
    chu_ky_sac: Annotated[StrictInt, Field(title="Chu kỳ sạc")]
    khoang_cach_truyen: Annotated[StrictInt | StrictStr, Field(title="Khoảng cách truyền")]
    phu_kien_di_kem: Annotated[StrictStr | None, Field(title="Phụ kiện đi kèm")]
    bang_tan: Annotated[StrictStr, Field(title="Băng tần")]
    nam_san_xuat: Annotated[StrictInt | None, Field(title="Năm sản xuất")]
    cong_sac: Annotated[StrictStr | None, Field(title="Cổng sạc")]
    cong_tai_nghe_headphone: Annotated[StrictStr, Field(title="Cổng tai nghe, headphone")]
    ket_noi: Annotated[StrictStr, Field(title="Kết nối")]
    loai_san_pham: Annotated[StrictStr, Field(title="Loại sản phẩm")]
    san_xuat_tai: Annotated[StrictStr, Field(title="Sản xuất tại")]
    tuong_thich: Annotated[StrictStr, Field(title="Tương thích")]
    thoi_gian_su_dung: Annotated[StrictStr, Field(title="Thời gian sử dụng")]
    thuong_hieu_cua: Annotated[StrictStr, Field(title="Thương hiệu của")]
    khoi_luong_may: Annotated[StrictInt | StrictStr | None, Field(title="Khối lượng máy")]
    loai_pin_hop_sac: Annotated[StrictInt | StrictStr | None, Field(title="Loại pin hộp sạc")]
    dung_luong_pin_bo_phat: Annotated[StrictInt | None, Field(title="Dung lượng pin bộ phát")]
    thoi_gian_hoat_dong_bo_phat: Annotated[StrictInt | None, Field(title="Thời gian hoạt động bộ phát")]
    thoi_gian_sac_bo_phat: Annotated[StrictStr | None, Field(title="Thời gian sạc bộ phát")]
    tan_so_hoat_dong: Annotated[StrictStr | None, Field(title="Tần số hoạt động")]
    loai_pin_bo_thu: Annotated[StrictStr | None, Field(title="Loại pin bộ thu")]
    dung_luong_pin_bo_thu: Annotated[StrictInt | None, Field(title="Dung lượng pin bộ thu")]
    thoi_gian_sac_bo_thu: Annotated[StrictStr | None, Field(title="Thời gian sạc bộ thu")]
    cong_suat_truyen_phat: Annotated[StrictStr | None, Field(title="Công suất truyền / phát")]
    nhiet_do_hoat_dong_bo_thu: Annotated[StrictStr | None, Field(title="Nhiệt độ hoạt động bộ thu")]
    huong_thu_am: Annotated[StrictStr | None, Field(title="Hướng thu âm")]
    ap_suat_am_thanh_spl: Annotated[StrictInt | None, Field(title="Áp suất âm thanh (SPL)")]
    kich_thuoc: Annotated[StrictStr | None, Field(title="Kích thước")]
    sac_day_bo_phat: Annotated[StrictStr | None, Field(title="Sạc đầy bộ phát")]
    phien_ban: Annotated[StrictStr | None, Field(title="Phiên bản")]
    gia_goc: Annotated[StrictInt | None, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr, Field(title="khuyến mãi quà")]


class DongHoThongMinhProduct(ProductModel):
    """Đồng hồ thông minh (dong_ho_thong_minh)."""

    model_config = ConfigDict(title="Đồng hồ thông minh")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand: Annotated[StrictStr, Field(title="brand")]
    cam_bien: Annotated[StrictStr, Field(title="Cảm biến")]
    dinh_vi: Annotated[StrictStr | None, Field(title="Định vị")]
    mon_the_thao: Annotated[StrictStr, Field(title="Môn thể thao")]
    sim: Annotated[StrictStr, Field(title="SIM")]
    thuc_hien_cuoc_goi: Annotated[StrictStr, Field(title="Thực hiện cuộc gọi")]
    tien_ich: Annotated[StrictStr, Field(title="Tiện ích")]
    chuan_chong_nuoc_bui: Annotated[StrictStr, Field(title="Chuẩn chống nước, bụi")]
    theo_doi_suc_khoe: Annotated[StrictStr, Field(title="Theo dõi sức khoẻ")]
    tien_ich_khac: Annotated[StrictStr, Field(title="Tiện ích khác")]
    hien_thi_thong_bao: Annotated[StrictStr, Field(title="Hiển thị thông báo")]
    thoi_gian_su_dung: Annotated[StrictStr, Field(title="Thời gian sử dụng")]
    thoi_gian_sac: Annotated[StrictStr, Field(title="Thời gian sạc")]
    dung_luong_pin: Annotated[StrictStr, Field(title="Dung lượng pin")]
    cong_sac: Annotated[StrictStr, Field(title="Cổng sạc")]
    san_xuat_tai: Annotated[StrictStr, Field(title="Sản xuất tại")]
    thoi_gian_ra_mat: Annotated[StrictStr, Field(title="Thời gian ra mắt")]
    ngon_ngu: Annotated[StrictStr, Field(title="Ngôn ngữ")]
    man_hinh_hien_thi: Annotated[StrictStr, Field(title="Màn hình hiển thị")]
    kich_thuoc_man_hinh: Annotated[FiniteNumber | StrictStr, Field(title="Kích thước màn hình")]
    do_phan_giai: Annotated[StrictStr, Field(title="Độ phân giải")]
    kich_thuoc_mat: Annotated[StrictStr, Field(title="Kích thước mặt")]
    chat_lieu_mat: Annotated[StrictStr, Field(title="Chất liệu mặt")]
    chat_lieu_khung_vien: Annotated[StrictStr, Field(title="Chất liệu khung viền")]
    chat_lieu_day: Annotated[StrictStr, Field(title="Chất liệu dây")]
    do_rong_day: Annotated[StrictStr, Field(title="Độ rộng dây")]
    chu_vi_co_tay: Annotated[StrictStr, Field(title="Chu vi cổ tay")]
    thay_the: Annotated[StrictStr, Field(title="Thay thế")]
    dai: Annotated[StrictInt, Field(title="Dài")]
    ngang: Annotated[StrictInt, Field(title="Ngang")]
    day: Annotated[StrictInt, Field(title="Dày")]
    khoi_luong_may: Annotated[StrictInt, Field(title="Khối lượng máy")]
    thiet_ke: Annotated[StrictStr | None, Field(title="Thiết kế")]
    do_phan_giai_camera_truoc: Annotated[StrictStr, Field(title="Độ phân giải camera trước")]
    chip_xu_ly_cpu: Annotated[StrictStr, Field(title="Chip xử lý (CPU)")]
    bo_nho: Annotated[StrictStr, Field(title="Bộ nhớ")]
    he_dieu_hanh: Annotated[StrictStr, Field(title="Hệ điều hành")]
    tuong_thich: Annotated[StrictStr, Field(title="Tương thích")]
    ung_dung: Annotated[StrictStr, Field(title="Ứng dụng")]
    ket_noi: Annotated[StrictStr, Field(title="Kết nối")]
    duong_kinh: Annotated[StrictStr | None, Field(title="Đường kính")]
    gia_goc: Annotated[StrictInt | None, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr, Field(title="khuyến mãi quà")]


class MayTinhDeBanProduct(ProductModel):
    """Máy tính để bàn (may_tinh_de_ban)."""

    model_config = ConfigDict(title="Máy tính để bàn")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand: Annotated[StrictStr, Field(title="brand")]
    thoi_gian_ra_mat: Annotated[StrictInt, Field(title="Thời gian ra mắt")]
    man_hinh_hien_thi: Annotated[StrictStr | None, Field(title="Màn hình hiển thị")]
    kich_thuoc_man_hinh: Annotated[StrictStr, Field(title="Kích thước màn hình")]
    do_phan_giai: Annotated[StrictStr, Field(title="Độ phân giải")]
    dai: Annotated[StrictInt, Field(title="Dài")]
    day: Annotated[StrictInt, Field(title="Dày")]
    khoi_luong_may: Annotated[StrictInt, Field(title="Khối lượng máy")]
    bo_nho: Annotated[StrictStr, Field(title="Bộ nhớ")]
    he_dieu_hanh: Annotated[StrictStr, Field(title="Hệ điều hành")]
    ho_tro_mainboard: Annotated[StrictStr | None, Field(title="Hỗ trợ mainboard")]
    chat_lieu_than_vo: Annotated[StrictStr | None, Field(title="Chất liệu thân vỏ")]
    ho_tro_o_cung_toi_da: Annotated[StrictStr | None, Field(title="Hỗ trợ ổ cứng tối đa")]
    phu_kien_di_kem: Annotated[StrictStr, Field(title="Phụ kiện đi kèm")]
    den_led: Annotated[StrictStr, Field(title="Đèn LED")]
    tan_nhiet_nuoc: Annotated[StrictStr, Field(title="Tản nhiệt nước")]
    tan_nhiet_cpu: Annotated[StrictStr, Field(title="Tản nhiệt CPU")]
    toc_do_rpm: Annotated[StrictStr, Field(title="Tốc độ (RPM)")]
    cong_ket_noi: Annotated[StrictStr | None, Field(title="Cổng kết nối")]
    cong_giao_tiep: Annotated[StrictStr | None, Field(title="Cổng giao tiếp")]
    wifi: Annotated[StrictStr, Field(title="Wifi")]
    the_nho: Annotated[StrictStr, Field(title="Thẻ nhớ")]
    webcam: Annotated[StrictStr, Field(title="Webcam")]
    tinh_nang_khac: Annotated[StrictStr, Field(title="Tính năng khác")]
    o_dia_quang: Annotated[StrictStr, Field(title="Ổ đĩa quang")]
    rong: Annotated[StrictInt, Field(title="Rộng")]
    nguon_dien: Annotated[StrictStr, Field(title="Nguồn điện")]
    cong_nghe_cpu: Annotated[StrictStr, Field(title="Công nghệ CPU")]
    loai_cpu: Annotated[StrictInt | StrictStr, Field(title="Loại CPU")]
    toc_do_cpu: Annotated[StrictStr, Field(title="Tốc độ CPU")]
    toc_do_toi_da: Annotated[StrictStr, Field(title="Tốc độ tối đa")]
    so_nhan: Annotated[StrictStr | None, Field(title="Số nhân")]
    bo_nho_dem: Annotated[StrictStr, Field(title="Bộ nhớ đệm")]
    socket: Annotated[StrictStr, Field(title="Socket")]
    chipset: Annotated[StrictStr, Field(title="Chipset")]
    ram: Annotated[StrictStr, Field(title="RAM")]
    loai_ram: Annotated[StrictStr, Field(title="Loại RAM")]
    so_khe_ram: Annotated[StrictStr, Field(title="Số khe RAM")]
    ho_tro_ram_toi_da: Annotated[StrictStr, Field(title="Hỗ trợ RAM tối đa")]
    tan_nhiet_ram: Annotated[StrictStr, Field(title="Tản nhiệt RAM")]
    o_cung: Annotated[StrictStr, Field(title="Ổ cứng")]
    chuan_ket_noi_o_cung: Annotated[StrictStr | None, Field(title="Chuẩn kết nối ổ cứng")]
    khe_cam_mo_rong: Annotated[StrictStr, Field(title="Khe cắm mở rộng")]
    man_hinh_cam_ung: Annotated[StrictStr, Field(title="Màn hình cảm ứng")]
    thiet_ke_card: Annotated[StrictStr, Field(title="Thiết kế card")]
    cong_nghe_am_thanh: Annotated[StrictStr, Field(title="Công nghệ âm thanh")]
    model_mainboard: Annotated[StrictStr, Field(title="Model Mainboard")]
    form_factor: Annotated[StrictStr, Field(title="Form Factor")]
    socket_mainboard: Annotated[StrictStr, Field(title="Socket (mainboard)")]
    loai_ram_mainboard: Annotated[StrictStr | None, Field(title="Loại RAM mainboard")]
    so_khe_ram_mainboard: Annotated[StrictStr, Field(title="Số khe RAM mainboard")]
    toc_do_bus_ram_mainboard: Annotated[StrictInt | StrictStr, Field(title="Tốc độ Bus RAM mainboard")]
    ho_tro_ram_toi_da_mainboard: Annotated[StrictStr, Field(title="Hỗ trợ RAM tối đa/mainboard")]
    ho_tro_khe_cam_ssd_m_2_hdd: Annotated[StrictStr | None, Field(title="Hỗ trợ khe cắm SSD M.2/HDD")]
    so_khe_cam_mo_rong: Annotated[StrictStr | None, Field(title="Số khe cắm mở rộng")]
    cong_i_o_mat_sau: Annotated[StrictStr | None, Field(title="Cổng I/O mặt sau")]
    ket_noi_internet: Annotated[StrictStr | None, Field(title="Kết nối Internet")]
    card_do_hoa_onboard: Annotated[StrictStr, Field(title="Card đồ hoạ onboard")]
    model_gpu: Annotated[StrictStr, Field(title="Model GPU")]
    chip_do_hoa_gpu: Annotated[StrictStr, Field(title="Chip đồ họa (GPU)")]
    bus_bo_nho: Annotated[StrictStr, Field(title="Bus bộ nhớ")]
    chuan_giao_tiep: Annotated[StrictStr, Field(title="Chuẩn giao tiếp")]
    bo_nguon_de_xuat: Annotated[StrictStr | None, Field(title="Bộ nguồn đề xuất")]
    ho_tro_oc: Annotated[StrictStr, Field(title="Hỗ trợ OC")]
    yeu_cau_cap_nguon_truc_tiep: Annotated[StrictStr, Field(title="Yêu cầu cấp nguồn trực tiếp")]
    cong_xuat_hinh_anh: Annotated[StrictStr | None, Field(title="Cổng xuất hình ảnh")]
    so_luong_quat: Annotated[StrictStr, Field(title="Số lượng quạt")]
    loai_case: Annotated[StrictStr, Field(title="Loại Case")]
    gia_goc: Annotated[StrictInt, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr, Field(title="khuyến mãi quà")]


class ManHinhMayTinhProduct(ProductModel):
    """Màn hình máy tính (man_hinh_may_tinh)."""

    model_config = ConfigDict(title="Màn hình máy tính")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand: Annotated[StrictStr, Field(title="brand")]
    tien_ich: Annotated[StrictStr, Field(title="Tiện ích")]
    man_hinh_hien_thi: Annotated[StrictStr, Field(title="Màn hình hiển thị")]
    kich_thuoc_man_hinh: Annotated[StrictStr, Field(title="Kích thước màn hình")]
    do_phan_giai: Annotated[StrictStr, Field(title="Độ phân giải")]
    ngang: Annotated[StrictInt, Field(title="Ngang")]
    day: Annotated[StrictInt, Field(title="Dày")]
    khoi_luong_may: Annotated[StrictInt, Field(title="Khối lượng máy")]
    ket_noi: Annotated[StrictStr, Field(title="Kết nối")]
    man_hinh_cam_ung: Annotated[StrictStr, Field(title="Màn hình cảm ứng")]
    tam_nen: Annotated[StrictStr, Field(title="Tấm nền")]
    thoi_gian_dap_ung: Annotated[StrictStr, Field(title="Thời gian đáp ứng")]
    do_phu_mau: Annotated[StrictStr, Field(title="Độ phủ màu")]
    so_luong: Annotated[StrictStr, Field(title="Số lượng")]
    do_sang: Annotated[StrictStr, Field(title="Độ sáng")]
    do_tuong_phan_tinh: Annotated[StrictStr, Field(title="Độ tương phản tĩnh")]
    loa: Annotated[StrictStr, Field(title="Loa")]
    vesa: Annotated[StrictStr, Field(title="Vesa")]
    dien_nang_tieu_thu: Annotated[StrictStr, Field(title="Điện năng tiêu thụ")]
    cao: Annotated[StrictInt, Field(title="Cao")]
    ngang_module_phu: Annotated[StrictInt | StrictStr, Field(title="Ngang module phụ")]
    cao_khong_chan: Annotated[StrictInt | StrictStr, Field(title="Cao không chân")]
    do_day_khong_chan: Annotated[StrictInt | StrictStr, Field(title="Độ dày không chân")]
    loai_man_hinh: Annotated[StrictStr, Field(title="Loại màn hình")]
    gia_goc: Annotated[StrictInt, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr, Field(title="khuyến mãi quà")]


class MayInProduct(ProductModel):
    """Máy in (may_in)."""

    model_config = ConfigDict(title="Máy in")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand: Annotated[StrictStr, Field(title="brand")]
    san_xuat_tai: Annotated[StrictStr, Field(title="Sản xuất tại")]
    thoi_gian_ra_mat: Annotated[StrictInt | None, Field(title="Thời gian ra mắt")]
    man_hinh_hien_thi: Annotated[StrictStr, Field(title="Màn hình hiển thị")]
    dai: Annotated[StrictInt, Field(title="Dài")]
    khoi_luong_may: Annotated[StrictInt | StrictStr, Field(title="Khối lượng máy")]
    bo_nho: Annotated[StrictStr, Field(title="Bộ nhớ")]
    tuong_thich: Annotated[StrictStr, Field(title="Tương thích")]
    ket_noi: Annotated[StrictStr | None, Field(title="Kết nối")]
    phu_kien_di_kem: Annotated[StrictStr, Field(title="Phụ kiện đi kèm")]
    cong_ket_noi: Annotated[StrictStr, Field(title="Cổng kết nối")]
    rong: Annotated[StrictInt, Field(title="Rộng")]
    cao: Annotated[StrictInt, Field(title="Cao")]
    chat_luong_in_do_net: Annotated[StrictStr, Field(title="Chất lượng in (độ nét)")]
    thoi_gian_chu_ky: Annotated[StrictStr, Field(title="Thời gian chu kỳ")]
    toc_do_in: Annotated[StrictStr, Field(title="Tốc độ in")]
    cong_suat_theo_nghiep_vu: Annotated[StrictStr, Field(title="Công suất theo nghiệp vụ")]
    loai_muc_in: Annotated[StrictStr, Field(title="Loại mực in")]
    cong_nghe: Annotated[StrictStr, Field(title="Công nghệ")]
    kich_thuoc_phu_kien: Annotated[StrictStr, Field(title="Kích thước phụ kiện")]
    loai_giay_in: Annotated[StrictStr | None, Field(title="Loại giấy in")]
    khay_chua_giay_da_in: Annotated[StrictStr, Field(title="Khay chứa giấy đã in")]
    khay_nap_giay: Annotated[StrictStr | None, Field(title="Khay nạp giấy")]
    kho_giay: Annotated[StrictStr | None, Field(title="Khổ giấy")]
    cpu_tuong_thich: Annotated[StrictStr, Field(title="CPU tương thích")]
    cong_suat_dau_ra: Annotated[StrictStr, Field(title="Công suất đầu ra")]
    loai_san_pham: Annotated[StrictStr, Field(title="Loại sản phẩm")]
    loai_giay_in_2_mat: Annotated[StrictStr | None, Field(title="Loại giấy in 2 mặt")]
    gia_goc: Annotated[StrictInt | None, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr, Field(title="khuyến mãi quà")]


class MayTinhBangProduct(ProductModel):
    """Máy tính bảng (may_tinh_bang)."""

    model_config = ConfigDict(title="Máy tính bảng")
    category_name: StrictStr
    model_code: Annotated[StrictStr, Field(title="model_code")]
    sku: Annotated[StrictStr, Field(title="sku")]
    productidweb: Annotated[StrictStr, Field(title="productidweb")]
    category_code: StrictStr
    brand: Annotated[StrictStr, Field(title="brand")]
    sim: Annotated[StrictStr | None, Field(title="SIM")]
    thuc_hien_cuoc_goi: Annotated[StrictStr | None, Field(title="Thực hiện cuộc gọi")]
    chuan_chong_nuoc_bui: Annotated[StrictStr | None, Field(title="Chuẩn chống nước, bụi")]
    dung_luong_pin: Annotated[StrictInt | StrictStr | None, Field(title="Dung lượng pin")]
    cong_sac: Annotated[StrictStr | None, Field(title="Cổng sạc")]
    thoi_gian_ra_mat: Annotated[StrictStr | None, Field(title="Thời gian ra mắt")]
    man_hinh_hien_thi: Annotated[StrictStr | None, Field(title="Màn hình hiển thị")]
    kich_thuoc_man_hinh: Annotated[StrictStr | None, Field(title="Kích thước màn hình")]
    do_phan_giai: Annotated[StrictStr | None, Field(title="Độ phân giải")]
    dai: Annotated[StrictInt | None, Field(title="Dài")]
    ngang: Annotated[StrictInt | None, Field(title="Ngang")]
    day: Annotated[StrictInt | None, Field(title="Dày")]
    khoi_luong_may: Annotated[StrictInt | StrictStr, Field(title="Khối lượng máy")]
    chip_xu_ly_cpu: Annotated[StrictStr | None, Field(title="Chip xử lý (CPU)")]
    he_dieu_hanh: Annotated[StrictStr | None, Field(title="Hệ điều hành")]
    ket_noi: Annotated[StrictStr | None, Field(title="Kết nối")]
    chat_lieu_than_vo: Annotated[StrictStr | None, Field(title="Chất liệu thân vỏ")]
    phu_kien_di_kem: Annotated[StrictInt | StrictStr | None, Field(title="Phụ kiện đi kèm")]
    wifi: Annotated[StrictStr | None, Field(title="Wifi")]
    the_nho: Annotated[StrictStr | None, Field(title="Thẻ nhớ")]
    toc_do_cpu: Annotated[StrictStr | None, Field(title="Tốc độ CPU")]
    ram: Annotated[StrictStr | None, Field(title="RAM")]
    chip_do_hoa_gpu: Annotated[StrictStr, Field(title="Chip đồ họa (GPU)")]
    bluetooth: Annotated[StrictStr | None, Field(title="Bluetooth")]
    cong_tai_nghe_headphone: Annotated[StrictStr, Field(title="Cổng tai nghe, headphone")]
    tinh_nang_dac_biet: Annotated[StrictStr | None, Field(title="Tính năng đặc biệt")]
    ghi_am: Annotated[StrictStr, Field(title="Ghi âm")]
    radio: Annotated[StrictStr, Field(title="Radio")]
    loai_pin: Annotated[StrictStr | None, Field(title="Loại pin")]
    cong_nghe_pin: Annotated[StrictStr | None, Field(title="Công nghệ pin")]
    ho_tro_sac_toi_da: Annotated[StrictInt | StrictStr | None, Field(title="Hỗ trợ sạc tối đa")]
    dung_luong_luu_tru: Annotated[StrictStr | None, Field(title="Dung lượng lưu trữ")]
    dung_luong_kha_dung: Annotated[StrictInt | None, Field(title="Dung lượng khả dụng")]
    quay_phim: Annotated[StrictStr | None, Field(title="Quay phim")]
    tinh_nang_camera_sau: Annotated[StrictStr | None, Field(title="Tính năng camera sau")]
    tinh_nang_camera_truoc: Annotated[StrictStr | None, Field(title="Tính năng camera trước")]
    mang_di_dong: Annotated[StrictStr | None, Field(title="Mạng di động")]
    gps: Annotated[StrictStr | None, Field(title="GPS")]
    gia_goc: Annotated[StrictInt | None, Field(title="giá gốc")]
    gia_khuyen_mai: Annotated[StrictInt | None, Field(title="giá khuyến mãi")]
    khuyen_mai_qua: Annotated[StrictStr | None, Field(title="khuyến mãi quà")]


class CategoryCode(StrEnum):
    TU_LANH = "tu_lanh"
    MAY_LANH = "may_lanh"
    MAY_GIAT = "may_giat"
    MAY_SAY_QUAN_AO = "may_say_quan_ao"
    MAY_RUA_CHEN = "may_rua_chen"
    TU_MAT_TU_DONG = "tu_mat_tu_dong"
    MAY_NUOC_NONG = "may_nuoc_nong"
    MICRO_KARAOKE = "micro_karaoke"
    MICRO_THU_AM_DIEN_THOAI = "micro_thu_am_dien_thoai"
    DONG_HO_THONG_MINH = "dong_ho_thong_minh"
    MAY_TINH_DE_BAN = "may_tinh_de_ban"
    MAN_HINH_MAY_TINH = "man_hinh_may_tinh"
    MAY_IN = "may_in"
    MAY_TINH_BANG = "may_tinh_bang"


ProductVariant: TypeAlias = (
    TuLanhProduct
    | MayLanhProduct
    | MayGiatProduct
    | MaySayQuanAoProduct
    | MayRuaChenProduct
    | TuMatTuDongProduct
    | MayNuocNongProduct
    | MicroKaraokeProduct
    | MicroThuAmDienThoaiProduct
    | DongHoThongMinhProduct
    | MayTinhDeBanProduct
    | ManHinhMayTinhProduct
    | MayInProduct
    | MayTinhBangProduct
)


class ProductCatalog(ProductModel):
    """A complete product catalog JSON document."""

    model_config = ConfigDict(title="Retail Product Catalog Schema")
    products: list[ProductVariant]


CATEGORY_MODEL_BY_CODE: dict[CategoryCode, type[ProductModel]] = {
    CategoryCode.TU_LANH: TuLanhProduct,
    CategoryCode.MAY_LANH: MayLanhProduct,
    CategoryCode.MAY_GIAT: MayGiatProduct,
    CategoryCode.MAY_SAY_QUAN_AO: MaySayQuanAoProduct,
    CategoryCode.MAY_RUA_CHEN: MayRuaChenProduct,
    CategoryCode.TU_MAT_TU_DONG: TuMatTuDongProduct,
    CategoryCode.MAY_NUOC_NONG: MayNuocNongProduct,
    CategoryCode.MICRO_KARAOKE: MicroKaraokeProduct,
    CategoryCode.MICRO_THU_AM_DIEN_THOAI: MicroThuAmDienThoaiProduct,
    CategoryCode.DONG_HO_THONG_MINH: DongHoThongMinhProduct,
    CategoryCode.MAY_TINH_DE_BAN: MayTinhDeBanProduct,
    CategoryCode.MAN_HINH_MAY_TINH: ManHinhMayTinhProduct,
    CategoryCode.MAY_IN: MayInProduct,
    CategoryCode.MAY_TINH_BANG: MayTinhBangProduct,
}

CATEGORY_TITLE_BY_CODE: dict[CategoryCode, str] = {
    code: model.model_config["title"]
    for code, model in CATEGORY_MODEL_BY_CODE.items()
}


__all__ = [
    "CATEGORY_MODEL_BY_CODE",
    "CATEGORY_TITLE_BY_CODE",
    "CategoryCode",
    "FiniteNumber",
    "ProductCatalog",
    "ProductModel",
    "ProductVariant",
    "TuLanhProduct",
    "MayLanhProduct",
    "MayGiatProduct",
    "MaySayQuanAoProduct",
    "MayRuaChenProduct",
    "TuMatTuDongProduct",
    "MayNuocNongProduct",
    "MicroKaraokeProduct",
    "MicroThuAmDienThoaiProduct",
    "DongHoThongMinhProduct",
    "MayTinhDeBanProduct",
    "ManHinhMayTinhProduct",
    "MayInProduct",
    "MayTinhBangProduct",
]
