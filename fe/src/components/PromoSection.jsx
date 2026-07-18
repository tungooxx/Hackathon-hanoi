import { useEffect, useState } from 'react'
import { promoTabs, flashSaleSlots, flashSaleProducts } from '../data/categories'

function useCountdown(initialSeconds) {
  const [seconds, setSeconds] = useState(initialSeconds)

  useEffect(() => {
    const id = setInterval(() => {
      setSeconds((s) => (s > 0 ? s - 1 : 0))
    }, 1000)
    return () => clearInterval(id)
  }, [])

  const h = String(Math.floor(seconds / 3600)).padStart(2, '0')
  const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0')
  const s = String(seconds % 60).padStart(2, '0')
  return `${h}:${m}:${s}`
}

export default function PromoSection() {
  const countdown = useCountdown(2 * 3600 + 59 * 60 + 49)
  const [activeTab, setActiveTab] = useState(0)

  return (
    <section className="promo">
      <div className="promo__header">
        <h2>Khuyến mãi online</h2>
      </div>

      <div className="promo__tabs">
        {promoTabs.map((tab, i) => (
          <button
            key={tab.label}
            className={`promo__tab ${i === activeTab ? 'promo__tab--active' : ''} ${
              tab.highlight ? 'promo__tab--flash' : ''
            }`}
            onClick={() => setActiveTab(i)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="promo__slots">
        {flashSaleSlots.map((slot, i) => (
          <div key={i} className={`promo__slot ${slot.active ? 'promo__slot--active' : ''}`}>
            <span className="promo__slot-time">{slot.time}</span>
            {slot.active ? (
              <span className="promo__slot-countdown">{countdown}</span>
            ) : (
              <span className="promo__slot-label">{slot.label}</span>
            )}
          </div>
        ))}
      </div>

      <div className="promo__products">
        {flashSaleProducts.map((p, i) => (
          <div key={i} className="product-card">
            {p.tag && <div className="product-card__tag">{p.tag}</div>}
            <div className="product-card__image">
              <img src={p.img} alt={p.name} loading="lazy" />
            </div>
            <div className="product-card__name">{p.name}</div>
          </div>
        ))}
      </div>
    </section>
  )
}
