import { quickCategories } from '../data/categories'

export default function QuickCategoryGrid() {
  return (
    <section className="quick-grid">
      {quickCategories.map((cat) => (
        <a key={cat.label} href="#" className="quick-grid__item">
          <div className="quick-grid__icon-wrap">
            {cat.isAll ? (
              <span className="quick-grid__all">☰</span>
            ) : (
              <img className="quick-grid__img" src={cat.img} alt={cat.label} loading="lazy" />
            )}
            {cat.badge && (
              <span className={`quick-grid__badge quick-grid__badge--${cat.badgeType}`}>
                {cat.badge}
              </span>
            )}
          </div>
          <span className="quick-grid__label">{cat.label}</span>
        </a>
      ))}
    </section>
  )
}
