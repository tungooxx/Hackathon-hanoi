import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { fetchCatalogProducts } from '../lib/catalogApi'
import { formatVnd } from '../lib/chatApi'

const PAGE_SIZE = 12

const FILTER_LABELS = {
  budget_max: 'Ngân sách',
  area_m2: 'Diện tích',
  brand: 'Hãng',
  afternoon_sun: 'Nắng chiều',
  needs_heating: '2 chiều (sưởi)',
  iron_portable: 'Bàn ủi cầm tay',
}

function describeFilter(key, value) {
  const label = FILTER_LABELS[key] || key
  if (key === 'budget_max') return `${label} ≤ ${formatVnd(Number(value))}`
  if (key === 'area_m2') return `${label} ${value}m²`
  return `${label}: ${value}`
}

// Bộ lọc chip hiển thị = search params trừ category + page.
function readFilters(searchParams) {
  const out = []
  for (const [key, value] of searchParams.entries()) {
    if (key === 'category' || key === 'page') continue
    if (value === '') continue
    out.push([key, value])
  }
  return out
}

export default function ProductResults() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  const category = searchParams.get('category')
  const page = Math.max(1, Number(searchParams.get('page')) || 1)
  // Key ổn định để chỉ fetch lại khi category/bộ lọc đổi (không fetch lại khi đổi trang).
  const fetchKey = useMemo(() => {
    const p = new URLSearchParams(searchParams)
    p.delete('page')
    p.sort()
    return p.toString()
  }, [searchParams])

  useEffect(() => {
    if (!category) return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    setError(null)
    fetchCatalogProducts(new URLSearchParams(fetchKey), { signal: controller.signal })
      .then((res) => {
        if (controller.signal.aborted) return
        setData(res)
        setLoading(false)
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        setError(err?.message || 'Không tải được danh sách sản phẩm.')
        setLoading(false)
      })
    return () => controller.abort()
  }, [category, fetchKey])

  const filters = readFilters(searchParams)
  const products = data?.products || []
  const totalPages = Math.max(1, Math.ceil(products.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageItems = products.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  const goToPage = (next) => {
    const params = new URLSearchParams(searchParams)
    if (next <= 1) params.delete('page')
    else params.set('page', String(next))
    setSearchParams(params)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div className="stage stage--catalog">
      <main className="catalog">
      <div className="catalog__bar">
        <button className="catalog__back" onClick={() => navigate('/')}>
          ← Về trang chủ
        </button>
        <div className="catalog__heading">
          <h1 className="catalog__title">{category}</h1>
          {!loading && !error && (
            <span className="catalog__count">
              {data?.count ?? products.length} sản phẩm khớp
              {data?.total != null && <span className="catalog__count-total"> / {data.total} trong danh mục</span>}
            </span>
          )}
        </div>
        {filters.length > 0 && (
          <div className="catalog__filters">
            {filters.map(([key, value]) => (
              <span key={key} className="catalog__chip">
                {describeFilter(key, value)}
              </span>
            ))}
            <Link to="/" className="catalog__chip catalog__chip--clear">
              ✕ Xoá bộ lọc
            </Link>
          </div>
        )}
      </div>

      {loading && <div className="catalog__state">Đang tải sản phẩm…</div>}
      {error && <div className="catalog__state catalog__state--error">{error}</div>}
      {!loading && !error && products.length === 0 && (
        <div className="catalog__state">Không có sản phẩm nào khớp bộ lọc này.</div>
      )}

      {!loading && !error && products.length > 0 && (
        <>
          <div className="catalog__grid">
            {pageItems.map((p) => (
              <ProductCard key={p.sku || p.model_code || p.name} p={p} />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="catalog__pagination">
              <button
                className="catalog__page-btn"
                disabled={currentPage <= 1}
                onClick={() => goToPage(currentPage - 1)}
              >
                ‹ Trước
              </button>
              <span className="catalog__page-info">
                Trang {currentPage} / {totalPages}
              </span>
              <button
                className="catalog__page-btn"
                disabled={currentPage >= totalPages}
                onClick={() => goToPage(currentPage + 1)}
              >
                Sau ›
              </button>
            </div>
          )}
        </>
        )}
      </main>
    </div>
  )
}

function ProductCard({ p }) {
  const area =
    p.area_min_m2 != null && p.area_max_m2 != null
      ? `${p.area_min_m2}-${p.area_max_m2}m²`
      : null
  // Có link trang SP thì card mở tab mới; không thì để div thường.
  const Tag = p.url ? 'a' : 'div'
  const linkProps = p.url
    ? { href: p.url, target: '_blank', rel: 'noopener noreferrer' }
    : {}
  return (
    <Tag className="catalog-card" {...linkProps}>
      <div className="catalog-card__media">
        {p.image_url ? (
          <img
            className="catalog-card__img"
            src={p.image_url}
            alt={p.name}
            loading="lazy"
          />
        ) : (
          <div className="catalog-card__img catalog-card__img--placeholder">📦</div>
        )}
      </div>
      <div className="catalog-card__brand">{p.brand}</div>
      <div className="catalog-card__name">{p.name}</div>
      <div className="catalog-card__price">
        {formatVnd(p.price_sale)}
        {p.price_original > p.price_sale && (
          <span className="catalog-card__price-old">{formatVnd(p.price_original)}</span>
        )}
      </div>
      <div className="catalog-card__specs">
        {p.energy_stars != null && <span>⭐ {p.energy_stars} sao điện</span>}
        {p.noise_db_min != null && <span>🔇 {p.noise_db_min}dB</span>}
        {area && <span>📐 {area}</span>}
        {p.inverter && <span>⚡ Inverter</span>}
      </div>
    </Tag>
  )
}
