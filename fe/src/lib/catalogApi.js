// Duyệt danh sách sản phẩm khớp funnel (khi khách bấm "Còn N/M mẫu khớp").
// Encode funnel (category + slots) <-> URL search params để có thể chia sẻ link,
// back/forward bằng history của trình duyệt, và xoá param là quay lại trang chính.
import { apiRequest } from './apiClient'

// Các slot bộ lọc cứng mà BE /catalog/products hiểu được.
const FILTER_KEYS = [
  'budget_max',
  'area_m2',
  'afternoon_sun',
  'brand',
  'needs_heating',
  'iron_portable',
]

// funnel { category, filters } -> URLSearchParams (?category=...&budget_max=...)
export function funnelToSearchParams(funnel) {
  const params = new URLSearchParams()
  if (!funnel?.category) return params
  params.set('category', funnel.category)
  const filters = funnel.filters || {}
  for (const key of FILTER_KEYS) {
    const value = filters[key]
    if (value != null && value !== '') params.set(key, String(value))
  }
  return params
}

// URLSearchParams -> query gửi BE (chỉ giữ category + slot hợp lệ).
export function fetchCatalogProducts(searchParams, { signal } = {}) {
  const category = searchParams.get('category')
  if (!category) return Promise.resolve(null)
  const query = new URLSearchParams({ category })
  for (const key of FILTER_KEYS) {
    const value = searchParams.get(key)
    if (value != null && value !== '') query.set(key, value)
  }
  return apiRequest(`/catalog/products?${query}`, { signal })
}
